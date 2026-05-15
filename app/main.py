from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import init_db, engine
from app.utils.exceptions import AppError
from app.utils.logging import setup_logging, get_logger, request_id_var, user_id_var
from app.routers import auth, users, llm_configs, system_configs, system_prompts, meta_tasks, task_instances, task_results, sse, exports

settings = get_settings()
setup_logging()
logger = get_logger(__name__)


import asyncio
import shutil

_disk_monitor_task: asyncio.Task | None = None
_last_disk_alert_time: float = 0


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _disk_monitor_task
    logger.info("Starting up...")
    await init_db()
    logger.info("Database initialized")
    _disk_monitor_task = asyncio.create_task(_disk_monitor_loop())
    yield
    logger.info("Shutting down...")
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
app.include_router(meta_tasks.router, prefix="/api/v1/meta-tasks", tags=["Meta Tasks"])
app.include_router(task_instances.router, prefix="/api/v1/task-instances", tags=["Task Instances"])
app.include_router(task_results.router, prefix="/api/v1/task-results", tags=["Task Results"])
app.include_router(sse.router, prefix="/api/v1/tasks", tags=["SSE"])
app.include_router(exports.router, prefix="/api/v1", tags=["Exports"])


@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}
