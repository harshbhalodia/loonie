"""Credit card / bank statement import: single-file synchronous parse (legacy), plus multi-file
queued upload -> review -> apply flow.

Unlike the wealth agents (which only interpret pre-computed, trusted numbers), extracting
transactions from a raw PDF has no deterministic alternative here — the LLM does the actual
extraction. To keep categorization consistent, the user's own `wealth_category_rules` keyword
mappings are applied as a deterministic override on top of the model's best-guess category.
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User, WealthAccount, WealthJob, WealthStatementImport
from app.schemas import (
    StatementApplyIn,
    StatementApplyResult,
    StatementImportDetail,
    StatementImportOut,
)
from app.services import ai_provider, job_queue, reminders, statement_parsing, statement_store
from app.services.statement_apply import apply_statement_transactions

router = APIRouter(prefix="/wealth/statements", tags=["wealth:statements"])


@router.post("/parse-pdf")
async def parse_pdf_statement(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Synchronous single-file parse — kept for backward compatibility with the existing
    review-and-bulk-insert UI flow. New multi-file uploads should use `/upload` instead."""
    try:
        transactions = statement_parsing.parse_pdf_to_transactions(db, user.id, await file.read())
    except ai_provider.AIProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"transactions": transactions}


@router.post("/upload", response_model=list[StatementImportOut])
async def upload_statements(
    account_id: str,
    files: list[UploadFile] = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Accepts one or more PDF statements for an account, saves each to disk, and queues one
    parse job per file — safe to upload 10 at once, they're processed strictly one at a time."""
    account = db.get(WealthAccount, account_id)
    if not account or account.user_id != user.id:
        raise HTTPException(status_code=404, detail="Account not found")

    created: list[WealthStatementImport] = []
    for file in files:
        data = await file.read()
        stored_path = statement_store.save_statement_file(user.id, account_id, file.filename or "statement.pdf", data)

        stmt_import = WealthStatementImport(
            user_id=user.id,
            account_id=account_id,
            file_name=file.filename or "statement.pdf",
            stored_path=stored_path,
            source_type="pdf",
            status="queued",
        )
        db.add(stmt_import)
        db.flush()

        job = WealthJob(
            user_id=user.id,
            job_type="statement_parse",
            status="queued",
            payload_json=json.dumps({"import_id": stmt_import.id}),
        )
        db.add(job)
        db.commit()
        db.refresh(stmt_import)

        job_queue.enqueue_job(job.id)
        created.append(stmt_import)

    return created


@router.get("/imports", response_model=list[StatementImportOut])
def list_statement_imports(
    account_id: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(WealthStatementImport).filter(WealthStatementImport.user_id == user.id)
    if account_id:
        query = query.filter(WealthStatementImport.account_id == account_id)
    return query.order_by(WealthStatementImport.created_at.desc()).all()


def _get_owned_import(db: Session, user: User, import_id: str) -> WealthStatementImport:
    stmt_import = db.get(WealthStatementImport, import_id)
    if not stmt_import or stmt_import.user_id != user.id:
        raise HTTPException(status_code=404, detail="Statement import not found")
    return stmt_import


@router.get("/imports/{import_id}", response_model=StatementImportDetail)
def get_statement_import(import_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt_import = _get_owned_import(db, user, import_id)
    transactions = json.loads(stmt_import.transactions_json) if stmt_import.transactions_json else []
    return {**stmt_import.__dict__, "transactions": transactions}


@router.post("/imports/{import_id}/apply", response_model=StatementApplyResult)
def apply_statement_import(
    import_id: str,
    payload: StatementApplyIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt_import = _get_owned_import(db, user, import_id)
    if stmt_import.status not in ("parsed", "applied"):
        raise HTTPException(status_code=409, detail=f"Import is not ready to apply (status={stmt_import.status})")

    inserted_count, updated_count, candidate_count = apply_statement_transactions(
        db, user.id, stmt_import.account_id, stmt_import.id, payload.transactions
    )

    account = db.get(WealthAccount, stmt_import.account_id)
    if account and account.type == "credit_card":
        stmt_import.statement_balance = payload.statement_balance
        stmt_import.minimum_due = payload.minimum_due
        stmt_import.due_date = payload.due_date

    stmt_import.inserted_count = inserted_count
    stmt_import.updated_count = updated_count
    stmt_import.status = "applied"
    stmt_import.applied_at = datetime.utcnow()
    db.add(stmt_import)
    db.commit()

    reminders.mark_account_statement_uploaded(db, stmt_import.account_id)

    return {
        "import_id": stmt_import.id,
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "candidate_count": candidate_count,
    }


@router.delete("/imports/{import_id}", status_code=204)
def delete_statement_import(import_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stmt_import = _get_owned_import(db, user, import_id)
    statement_store.delete_statement_file(stmt_import.stored_path)
    db.delete(stmt_import)
    db.commit()

