"""Marketplace: browse/install/run declarative stress-test blueprints, plus a no-code Studio
for drafting and test-running new ones before submitting them for publishing. Blueprints here
are bundled YAML data (see services/marketplace_catalog.py) — never third-party executable
code — so installing one never means running someone else's Python in this app.
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import get_marketplace_config
from app.database import get_db
from app.deps import get_current_user
from app.models import MarketplaceBlueprintRun, MarketplaceDataGrant, MarketplaceInstalledBlueprint, User
from app.schemas import (
    BlueprintCatalogEntryOut,
    BlueprintRunExportOut,
    BlueprintRunFeedbackIn,
    BlueprintRunOut,
    BlueprintRunResult,
    BlueprintScopesOut,
    DemoLicenseOut,
    GrantScopesIn,
    InstallBlueprintIn,
    InstalledBlueprintOut,
    StudioDraftIn,
)
from app.services import (
    ai_provider,
    marketplace_catalog,
    marketplace_feedback,
    marketplace_license,
    marketplace_runner,
    wealth_scopes,
)
from app.services.marketplace_catalog import BlueprintDefinition, BlueprintScenario

router = APIRouter(prefix="/marketplace", tags=["marketplace"])


def _requested_scopes(definition: BlueprintDefinition) -> list[str]:
    return [f for f in definition.inputs if f in wealth_scopes.known_scope_ids()]


def _get_grant(blueprint_id: str, user: User, db: Session) -> MarketplaceDataGrant | None:
    return (
        db.query(MarketplaceDataGrant)
        .filter(MarketplaceDataGrant.user_id == user.id, MarketplaceDataGrant.blueprint_id == blueprint_id)
        .first()
    )


def _catalog_out(definition: BlueprintDefinition) -> BlueprintCatalogEntryOut:
    return BlueprintCatalogEntryOut(
        id=definition.id,
        name=definition.name,
        publisher=definition.publisher,
        version=definition.version,
        tier=definition.tier,
        price_usd=definition.price_usd,
        category=definition.category,
        summary=definition.summary,
        inputs=definition.inputs,
        tags=definition.tags,
        scenarios=[{"id": s.id, "description": s.description} for s in definition.scenarios],
    )


def _get_definition_or_404(blueprint_id: str) -> BlueprintDefinition:
    try:
        return marketplace_catalog.get_blueprint(blueprint_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown blueprint") from None


@router.get("/catalog", response_model=list[BlueprintCatalogEntryOut])
def catalog(user: User = Depends(get_current_user)):
    return [_catalog_out(d) for d in marketplace_catalog.load_catalog()]


@router.get("/installed", response_model=list[InstalledBlueprintOut])
def installed(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(MarketplaceInstalledBlueprint)
        .filter(MarketplaceInstalledBlueprint.user_id == user.id)
        .order_by(MarketplaceInstalledBlueprint.installed_at.desc())
        .all()
    )


@router.post("/install", response_model=InstalledBlueprintOut)
def install(payload: InstallBlueprintIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    definition = _get_definition_or_404(payload.blueprint_id)

    if definition.tier == "paid":
        secret = get_marketplace_config().get("demo_license_secret")
        if not payload.license_token or not secret:
            raise HTTPException(
                status_code=402,
                detail=f"{definition.name} is a paid blueprint (${definition.price_usd}) — a license token is required.",
            )
        try:
            license_ = marketplace_license.verify(payload.license_token, secret)
        except marketplace_license.EntitlementError as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from exc
        if license_["blueprint_id"] != definition.id:
            raise HTTPException(status_code=402, detail="License token does not match this blueprint.")

    row = (
        db.query(MarketplaceInstalledBlueprint)
        .filter(
            MarketplaceInstalledBlueprint.user_id == user.id,
            MarketplaceInstalledBlueprint.blueprint_id == definition.id,
        )
        .first()
    )
    if row is None:
        row = MarketplaceInstalledBlueprint(user_id=user.id, blueprint_id=definition.id)
        db.add(row)
    row.version = definition.version
    row.tier = definition.tier
    row.license_token = payload.license_token
    db.commit()
    db.refresh(row)
    return row


@router.delete("/installed/{blueprint_id}")
def uninstall(blueprint_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = (
        db.query(MarketplaceInstalledBlueprint)
        .filter(
            MarketplaceInstalledBlueprint.user_id == user.id,
            MarketplaceInstalledBlueprint.blueprint_id == blueprint_id,
        )
        .first()
    )
    if row:
        db.delete(row)
        db.commit()
    return {"status": "ok"}


@router.get("/blueprints/{blueprint_id}/scopes", response_model=BlueprintScopesOut)
def get_scopes(blueprint_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """What this blueprint is requesting (human-readable) plus what's currently granted — the
    data-sharing consent screen renders directly off this, always fetched fresh (never cached
    client-side across sessions) so it reflects the blueprint's current declared inputs."""
    definition = _get_definition_or_404(blueprint_id)
    grant = _get_grant(blueprint_id, user, db)
    granted = json.loads(grant.granted_scopes_json) if grant else []
    return BlueprintScopesOut(
        blueprint_id=definition.id,
        blueprint_version=definition.version,
        requested=[d.__dict__ for d in wealth_scopes.describe(_requested_scopes(definition))],
        granted=granted,
    )


@router.post("/blueprints/{blueprint_id}/grant", response_model=BlueprintScopesOut)
def grant_scopes(
    blueprint_id: str,
    payload: GrantScopesIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Records the user's EXPLICIT consent for exactly which data categories this blueprint may
    receive. Only known scope ids that the blueprint actually declares can be granted — anything
    else in the payload is silently dropped, so a confused/buggy client can never widen a grant
    beyond what the blueprint is even asking for."""
    definition = _get_definition_or_404(blueprint_id)
    allowed = set(_requested_scopes(definition))
    scopes = sorted({s for s in payload.scopes if s in allowed})

    grant = _get_grant(blueprint_id, user, db)
    if grant is None:
        grant = MarketplaceDataGrant(user_id=user.id, blueprint_id=definition.id)
        db.add(grant)
    grant.blueprint_version = definition.version
    grant.granted_scopes_json = json.dumps(scopes)
    db.commit()

    return BlueprintScopesOut(
        blueprint_id=definition.id,
        blueprint_version=definition.version,
        requested=[d.__dict__ for d in wealth_scopes.describe(sorted(allowed))],
        granted=scopes,
    )


@router.post("/blueprints/{blueprint_id}/run", response_model=BlueprintRunResult)
def run(blueprint_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = (
        db.query(MarketplaceInstalledBlueprint)
        .filter(
            MarketplaceInstalledBlueprint.user_id == user.id,
            MarketplaceInstalledBlueprint.blueprint_id == blueprint_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Blueprint is not installed")

    definition = _get_definition_or_404(blueprint_id)
    grant = _get_grant(blueprint_id, user, db)
    granted_scopes = json.loads(grant.granted_scopes_json) if grant else []
    missing = [s for s in _requested_scopes(definition) if s not in granted_scopes]
    if missing:
        raise HTTPException(
            status_code=412,
            detail="Data-sharing consent is required or out of date for this blueprint.",
        )

    run_log = MarketplaceBlueprintRun(
        user_id=user.id, blueprint_id=blueprint_id, blueprint_version=definition.version, tier=definition.tier
    )

    try:
        outcome = marketplace_runner.run_blueprint(db, user, definition, granted_scopes=granted_scopes)
        run_log.status = "ok"
        run_log.facts_json = json.dumps(outcome.facts, default=str)
        run_log.result = outcome.result
        run_log.shared_scopes_json = json.dumps(outcome.shared_scopes)
        db.add(run_log)
        db.commit()
        return BlueprintRunResult(blueprint_id=blueprint_id, status="ok", result=outcome.result)
    except marketplace_runner.ConsentRequiredError as exc:
        # Defense in depth: the pre-check above should already have caught this. Not logged as a
        # run since no data was gathered/sent — the request is rejected outright either way.
        raise HTTPException(status_code=412, detail=str(exc)) from exc
    except ai_provider.AIProviderError as exc:
        run_log.status = "error"
        run_log.facts_json = "{}"
        run_log.shared_scopes_json = "[]"
        run_log.error = str(exc)
        db.add(run_log)
        db.commit()
        return BlueprintRunResult(blueprint_id=blueprint_id, status="error", error=str(exc))


@router.get("/history", response_model=list[BlueprintRunOut])
def history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(MarketplaceBlueprintRun)
        .filter(MarketplaceBlueprintRun.user_id == user.id)
        .order_by(MarketplaceBlueprintRun.created_at.desc())
        .limit(200)
        .all()
    )


@router.get("/blueprints/{blueprint_id}/history", response_model=list[BlueprintRunOut])
def blueprint_history(blueprint_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(MarketplaceBlueprintRun)
        .filter(MarketplaceBlueprintRun.user_id == user.id, MarketplaceBlueprintRun.blueprint_id == blueprint_id)
        .order_by(MarketplaceBlueprintRun.created_at.desc())
        .limit(50)
        .all()
    )


def _get_run_or_404(run_id: str, user: User, db: Session) -> MarketplaceBlueprintRun:
    run_log = (
        db.query(MarketplaceBlueprintRun)
        .filter(MarketplaceBlueprintRun.id == run_id, MarketplaceBlueprintRun.user_id == user.id)
        .first()
    )
    if not run_log:
        raise HTTPException(status_code=404, detail="Run not found")
    return run_log


@router.post("/runs/{run_id}/feedback", response_model=BlueprintRunOut)
def rate_run(
    run_id: str,
    payload: BlueprintRunFeedbackIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Records the user's own private rating/note on a past run — never shared with the
    blueprint's publisher unless the user separately calls the export endpoint below."""
    run_log = _get_run_or_404(run_id, user, db)
    run_log.user_rating = payload.rating
    run_log.user_note = payload.note
    db.commit()
    db.refresh(run_log)
    return run_log


@router.post("/runs/{run_id}/export", response_model=BlueprintRunExportOut)
def export_run(run_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Builds a precision-reduced, de-identified bundle of one run for the user to download and
    OPTIONALLY send to the blueprint's publisher themselves — nothing is sent automatically or
    server-side; there is no hosted publisher-analytics service yet (see the marketplace
    architecture doc in the localagents repo)."""
    run_log = _get_run_or_404(run_id, user, db)
    if run_log.status != "ok" or not run_log.result:
        raise HTTPException(status_code=400, detail="Only a successful run can be exported.")

    bundle = marketplace_feedback.build_export_bundle(
        blueprint_id=run_log.blueprint_id,
        blueprint_version=run_log.blueprint_version,
        tier=run_log.tier,
        facts=json.loads(run_log.facts_json),
        result=run_log.result,
        user_rating=run_log.user_rating,
        user_note=run_log.user_note,
    )
    run_log.shared_with_publisher_at = datetime.utcnow()
    db.commit()
    return BlueprintRunExportOut(**bundle)


@router.post("/dev/demo-license", response_model=DemoLicenseOut)
def demo_license(payload: InstallBlueprintIn, user: User = Depends(get_current_user)):
    """Issues a signed demo license standing in for a real purchase flow — see
    docs/architecture/blueprint-marketplace.md in the localagents repo. Only available while
    marketplace.demo_mode is on; there is no payment step behind this yet."""
    cfg = get_marketplace_config()
    if not cfg.get("demo_mode", True):
        raise HTTPException(status_code=403, detail="Demo licensing is disabled.")
    secret = cfg.get("demo_license_secret")
    if not secret:
        raise HTTPException(status_code=500, detail="marketplace.demo_license_secret is not configured.")

    definition = _get_definition_or_404(payload.blueprint_id)
    token = marketplace_license.sign(definition.id, definition.version, user.id, secret)
    return DemoLicenseOut(blueprint_id=definition.id, license_token=token)


@router.post("/studio/test-run", response_model=BlueprintRunResult)
def studio_test_run(payload: StudioDraftIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Runs a draft blueprint (not persisted, not added to the catalog) against the CURRENT
    user's own snapshot — lets a creator sanity-check a blueprint before submitting it. No
    separate consent screen here: the creator typed `inputs` into the Studio form themselves,
    so it's auto-granted for exactly what they declared — same rule as any other blueprint,
    just already explicit by construction."""
    definition = BlueprintDefinition(
        id=payload.id or "draft.blueprint",
        name=payload.name,
        publisher=payload.publisher,
        version="0.0.0-draft",
        tier=payload.tier,
        price_usd=payload.price_usd,
        category=payload.category,
        summary=payload.summary,
        inputs=payload.inputs,
        tags=payload.tags,
        scenarios=[BlueprintScenario(id=s.id, description=s.description) for s in payload.scenarios],
    )
    try:
        outcome = marketplace_runner.run_blueprint(db, user, definition, granted_scopes=payload.inputs)
        return BlueprintRunResult(blueprint_id=definition.id, status="ok", result=outcome.result)
    except ai_provider.AIProviderError as exc:
        return BlueprintRunResult(blueprint_id=definition.id, status="error", error=str(exc))
