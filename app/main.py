from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import init_db, engine, async_session_factory
from app.utils.exceptions import AppError
from app.utils.logging import setup_logging, get_logger, request_id_var, user_id_var
from app.routers import auth, users, llm_configs, system_configs, system_prompts, prompt_templates, meta_tasks, task_instances, task_results, sse, exports

settings = get_settings()
setup_logging()
logger = get_logger(__name__)


import asyncio
import shutil

_disk_monitor_task: asyncio.Task | None = None
_last_disk_alert_time: float = 0

_background_workers: list[asyncio.Task] = []


async def _disk_monitor_loop():
    """每分钟检查磁盘空间，低于阈值时记录告警。"""
    global _last_disk_alert_time
    threshold_gb = int(getattr(settings, "disk_alarm_threshold_gb", 10))
    while True:
        try:
            usage = shutil.disk_usage(settings.data_dir)
            free_gb = usage.free / (1024 ** 3)
            if free_gb < threshold_gb:
                import time
                now = time.time()
                if now - _last_disk_alert_time > 86400:
                    logger.warning(f"磁盘空间不足: 剩余 {free_gb:.1f} GB（阈值 {threshold_gb} GB）")
                    _last_disk_alert_time = now
        except Exception as e:
            logger.error(f"磁盘监控异常: {e}")
        await asyncio.sleep(60)


async def _start_worker(queue_type: str, concurrency: int):
    """启动一个后台 worker 协程。"""
    from app.task_queue.worker import BaseWorker

    cls_map = {
        "cnki": ("app.worker.cnki_worker", "run_cnki_search"),
        "llm": ("app.worker.llm_worker", "run_llm_analysis"),
        "download": ("app.worker.download_worker", "run_download"),
        "export": ("app.worker.export_worker", "run_export"),
    }
    mod_path, func_name = cls_map.get(queue_type, (None, None))
    if not mod_path:
        logger.error(f"Unknown worker type: {queue_type}")
        return

    class _Worker(BaseWorker):
        async def process(self, db, item_id: int, params_json: str) -> None:
            from importlib import import_module
            fn = getattr(import_module(mod_path), func_name)
            await fn(db, item_id, params_json)

    worker = _Worker(queue_type=queue_type, session_factory=async_session_factory, concurrency=concurrency)
    await worker.run()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _disk_monitor_task, _background_workers
    logger.info("Starting up...")
    await init_db()
    logger.info("Database initialized")
    _disk_monitor_task = asyncio.create_task(_disk_monitor_loop())
    auto_workers = settings.auto_start_workers
    if auto_workers:
        worker_configs = [
            ("cnki", 1),
            ("llm", 5),
            ("download", 1),
            ("export", 2),
        ]
        for queue_type, concurrency in worker_configs:
            task = asyncio.create_task(_start_worker(queue_type, concurrency), name=f"worker-{queue_type}")
            _background_workers.append(task)
            logger.info(f"Auto-started worker [{queue_type}] (concurrency={concurrency})")
    yield
    logger.info("Shutting down...")
    for task in _background_workers:
        task.cancel()
    if _background_workers:
        await asyncio.gather(*_background_workers, return_exceptions=True)
    if _disk_monitor_task:
        _disk_monitor_task.cancel()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_context_middleware(request: Request, call_next):
    import uuid
    rid = str(uuid.uuid4())[:8]
    request_id_var.set(rid)
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if token:
        try:
            from app.dependencies import decode_token
            payload = decode_token(token)
            user_id_var.set(payload.get("sub"))
        except Exception:
            pass
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "request_id": request_id_var.get("")},
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": "Internal server error", "request_id": request_id_var.get("")},
    )


app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(llm_configs.router, prefix="/api/v1/llm-configs", tags=["LLM Configs"])
app.include_router(system_configs.router, prefix="/api/v1/system", tags=["System Configs"])
app.include_router(system_prompts.router, prefix="/api/v1/system-prompts", tags=["System Prompts"])
app.include_router(prompt_templates.router, prefix="/api/v1/prompt-templates", tags=["Prompt Templates"])
app.include_router(meta_tasks.router, prefix="/api/v1/meta-tasks", tags=["Meta Tasks"])
app.include_router(task_instances.router, prefix="/api/v1/task-instances", tags=["Task Instances"])
app.include_router(task_results.router, prefix="/api/v1/task-results", tags=["Task Results"])
app.include_router(sse.router, prefix="/api/v1/tasks", tags=["SSE"])
app.include_router(exports.router, prefix="/api/v1", tags=["Exports"])


@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}
