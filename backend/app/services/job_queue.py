"""Single-worker in-process job queue.

Guarantees statement-parse jobs (which call the local AI endpoint) run strictly one at a time —
never concurrently — so uploading many statements at once never sends overlapping requests to
LM Studio/Ollama/etc, and each request is built completely fresh with no shared context between
jobs (ai_provider.generate() is already a single stateless call per job).

In-memory queue: jobs are re-queued from any row still `queued`/`processing` at startup (e.g.
after a restart mid-processing), but are otherwise not persisted across process restarts beyond
that recovery pass.
"""
from __future__ import annotations

import json
import queue
import threading
from datetime import datetime

from app.database import SessionLocal
from app.models import WealthJob, WealthStatementImport
from app.services import statement_parsing, statement_store

_queue: "queue.Queue[str]" = queue.Queue()
_worker_thread: threading.Thread | None = None
_lock = threading.Lock()


def enqueue_job(job_id: str) -> None:
    _queue.put(job_id)


def _fail_job(db, job: WealthJob, message: str) -> None:
    db.rollback()
    job.status = "error"
    job.error = message
    job.finished_at = datetime.utcnow()
    db.add(job)

    if job.job_type == "statement_parse":
        try:
            payload = json.loads(job.payload_json)
            stmt_import = db.get(WealthStatementImport, payload["import_id"])
            if stmt_import:
                stmt_import.status = "error"
                stmt_import.error = message
                db.add(stmt_import)
        except Exception:
            pass
    db.commit()


def _process_statement_parse(db, job: WealthJob) -> None:
    payload = json.loads(job.payload_json)
    stmt_import = db.get(WealthStatementImport, payload["import_id"])
    if not stmt_import:
        raise RuntimeError("Statement import record not found")

    stmt_import.status = "processing"
    db.add(stmt_import)
    db.commit()

    data = statement_store.read_statement_file(stmt_import.stored_path)
    transactions = statement_parsing.parse_pdf_to_transactions(db, stmt_import.user_id, data)

    stmt_import.transactions_json = json.dumps(transactions)
    stmt_import.transaction_count = len(transactions)
    stmt_import.statement_period = statement_parsing.derive_statement_period(transactions)
    stmt_import.status = "parsed"
    db.add(stmt_import)
    db.commit()


def _run_job(job_id: str) -> None:
    db = SessionLocal()
    try:
        job = db.get(WealthJob, job_id)
        if not job:
            return

        job.status = "processing"
        job.started_at = datetime.utcnow()
        db.add(job)
        db.commit()

        try:
            if job.job_type == "statement_parse":
                _process_statement_parse(db, job)
            else:
                raise ValueError(f"Unknown job type: {job.job_type}")
            job.status = "done"
            job.finished_at = datetime.utcnow()
            db.add(job)
            db.commit()
        except Exception as exc:  # noqa: BLE001 - the worker must never die, always record the error
            _fail_job(db, job, str(exc))
    finally:
        db.close()


def _worker_loop() -> None:
    while True:
        job_id = _queue.get()
        try:
            _run_job(job_id)
        finally:
            _queue.task_done()


def start_worker() -> None:
    """Starts the single background worker thread (idempotent) and re-queues any job left
    queued/processing from a previous run (e.g. the app was restarted mid-upload)."""
    global _worker_thread
    with _lock:
        if _worker_thread and _worker_thread.is_alive():
            return
        _worker_thread = threading.Thread(target=_worker_loop, name="wealth-job-worker", daemon=True)
        _worker_thread.start()

    db = SessionLocal()
    try:
        pending = db.query(WealthJob).filter(WealthJob.status.in_(["queued", "processing"])).order_by(WealthJob.created_at).all()
        for job in pending:
            job.status = "queued"
            db.add(job)
        db.commit()
        for job in pending:
            enqueue_job(job.id)
    finally:
        db.close()
