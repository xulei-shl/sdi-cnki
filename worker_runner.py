"""Worker process entry point. Runs specified queue worker."""

import asyncio
import sys

from app.database import async_session_factory
from app.task_queue.worker import BaseWorker
from app.utils.logging import setup_logging, get_logger

setup_logging()
logger = get_logger("worker_runner")


class CnkiWorker(BaseWorker):
    async def process(self, db, item_id: int, params_json: str) -> None:
        logger.info(f"[CNKI] Task {item_id}: {params_json}")
        from app.worker.cnki_worker import run_cnki_search
        await run_cnki_search(db, item_id, params_json)


class LlmWorker(BaseWorker):
    async def process(self, db, item_id: int, params_json: str) -> None:
        logger.info(f"[LLM] Task {item_id}: {params_json}")
        from app.worker.llm_worker import run_llm_analysis
        await run_llm_analysis(db, item_id, params_json)


class DownloadWorker(BaseWorker):
    async def process(self, db, item_id: int, params_json: str) -> None:
        logger.info(f"[DOWNLOAD] Task {item_id}: {params_json}")
        from app.worker.download_worker import run_download
        await run_download(db, item_id, params_json)


class ExportWorker(BaseWorker):
    async def process(self, db, item_id: int, params_json: str) -> None:
        logger.info(f"[EXPORT] Task {item_id}: {params_json}")
        from app.worker.export_worker import run_export
        await run_export(db, item_id, params_json)


WORKER_MAP = {
    "cnki": CnkiWorker,
    "llm": LlmWorker,
    "download": DownloadWorker,
    "export": ExportWorker,
}

if __name__ == "__main__":
    queue_type = sys.argv[1] if len(sys.argv) > 1 else "cnki"
    concurrency = int(sys.argv[2]) if len(sys.argv) > 2 else {"cnki": 1, "download": 1, "llm": 5, "export": 2}.get(queue_type, 1)
    worker_cls = WORKER_MAP.get(queue_type)
    if not worker_cls:
        print(f"Unknown queue type: {queue_type}. Choose from: cnki, llm, download, export")
        sys.exit(1)
    worker = worker_cls(queue_type=queue_type, session_factory=async_session_factory, concurrency=concurrency)
    asyncio.run(worker.run())
