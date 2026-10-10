"""Issuing and verifying the revenue statement.

The artifact a merchant shows a microfinance institution. Three properties it has
that the CSV dump did not (docs/optimization_claude_fidelia.md, optimization C):

1. **Reviewable.** Aggregates a credit officer reads in a minute, not 10,000 rows.
2. **Tamper-evident.** Signed, so an edited figure fails verification.
3. **Attributable.** Every issue writes an `export_audit` row, like every other
   data transfer out of the system (W2-1).

Gated to a paid plan, because the reporting a merchant shows a lender is exactly
the kind of value a plan may charge for -- unlike recording a sale, which is never
gated (app/core/entitlements.py). The free `pilot` plan includes it too: a
pilot merchant shares it with a partner MFI (docs/business/PROPOSITION-PILOTE-FINELLE.fr.md).
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..core.entitlements import Feature, plan_allows
from ..core.security import get_current_user, require_role
from ..db import get_db
from ..services import revenue as revenue_service
from ..services import statement as statement_service
from .customer import utcnow
from .payment_requests import _my_venue

router = APIRouter()

# A statement over a very short window says nothing about regularity, which is
# half of what it is for. Refused rather than issued as a misleading document.
MIN_PERIOD_DAYS = 28
MAX_PERIOD_DAYS = 730


class StatementVerifyIn(BaseModel):
    """A statement someone received, as they received it."""

    payload: dict
    signature: str


def _window(from_: datetime | None, to: datetime | None, now: datetime) -> tuple[datetime, datetime]:
    until = to or now
    since = from_ or (until - timedelta(days=180))
    if since >= until:
        raise HTTPException(status_code=422, detail="La date de debut doit preceder la date de fin")
    days = (until.date() - since.date()).days + 1
    if days < MIN_PERIOD_DAYS:
        raise HTTPException(
            status_code=422,
            detail=f"Une attestation couvre au moins {MIN_PERIOD_DAYS} jours: une periode plus courte ne dit rien de la regularite",
        )
    if days > MAX_PERIOD_DAYS:
        raise HTTPException(status_code=422, detail=f"Periode trop longue (maximum {MAX_PERIOD_DAYS} jours)")
    if until > now:
        # A statement covering the future would attest to nothing and would look
        # exactly as official as one that does not.
        until = now
    return since, until


@router.get("/merchant/statement")
async def issue_statement(
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("merchant")),
):
    """Issue a signed statement for the merchant's own venue and period.

    Contains no customer identifier -- only counts and a concentration ratio --
    so it needs no customer's consent, which is what makes it the artifact to
    hand over rather than the per-customer export.
    """
    venue = await _my_venue(db, user, require_wallet=False)
    from .billing import subscription_for  # local: billing imports _my_venue from here

    subscription = await subscription_for(db, venue.id)
    if not plan_allows(subscription, Feature.REVENUE_STATEMENT):
        raise HTTPException(
            status_code=402,
            detail=(
                "L'attestation de revenus est incluse dans la formule Reseau et dans le pilote. "
                "Vos donnees restent exportables en CSV sur votre formule actuelle."
            ),
        )

    now = utcnow()
    since, until = _window(from_, to, now)
    try:
        document, profile = await statement_service.build(
            db, venue=venue, since=since, until=until, issued_at=now, issued_to=user["username"]
        )
    except statement_service.StatementSecretMissing as exc:
        # Fail closed: an unsigned statement would be handed to a lender looking
        # exactly as official as a signed one.
        raise HTTPException(status_code=503, detail="Signature indisponible: attestation non emise") from exc
    except revenue_service.TooManyEvents as exc:
        # The worst case this code has: a truncated total, signed, understating a
        # merchant's turnover in the document a lender decides on.
        raise HTTPException(
            status_code=413,
            detail="Periode trop dense pour une attestation. Demandez une periode plus courte.",
        ) from exc

    db.add(
        models.ExportAudit(
            exported_by=user["username"],
            venue_id=venue.id,
            merchant_id=venue.merchant_id,
            kind="revenue_statement",
            subject_count=0,
            row_count=profile.count,
            period_start=since,
            period_end=until,
            occurred_at=now,
        )
    )
    await db.commit()
    return document


@router.post("/statements/verify")
async def verify_statement(body: StatementVerifyIn, user=Depends(get_current_user)):
    """Check a statement is the document Fidelia issued, unedited.

    Open to any authenticated account, not just the issuing merchant: the point
    of verification is that the *recipient* can perform it. It reveals nothing --
    the caller already holds the payload, and the answer is one bit.
    """
    valid = statement_service.verify(body.payload, body.signature)
    return {
        "valid": valid,
        "algorithm": statement_service.ALGORITHM,
        "schema_version": body.payload.get("schema_version"),
        "detail": (
            "Attestation authentique et non modifiee"
            if valid
            else "Signature invalide: le document a ete modifie ou n'a pas ete emis par Fidelia"
        ),
    }


@router.get("/admin/venues/{venue_id}/statement")
async def issue_statement_for_venue(
    venue_id: int,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(require_role("admin")),
):
    """The same statement, issued by an admin for a venue.

    For the pilot: a partner conversation happens with Fidelia in the room, and a
    merchant on the starter plan still needs their history to exist. Not plan
    gated -- an admin is not a customer of the plan -- but audited identically,
    because who issued an attestation about someone's business is exactly what a
    partner asks later.
    """
    venue = await db.get(models.Venue, venue_id)
    if venue is None:
        raise HTTPException(status_code=404, detail="venue not found")

    now = utcnow()
    since, until = _window(from_, to, now)
    try:
        document, profile = await statement_service.build(
            db, venue=venue, since=since, until=until, issued_at=now, issued_to=user["username"]
        )
    except statement_service.StatementSecretMissing as exc:
        raise HTTPException(status_code=503, detail="Signature indisponible: attestation non emise") from exc
    except revenue_service.TooManyEvents as exc:
        raise HTTPException(
            status_code=413,
            detail="Periode trop dense pour une attestation. Demandez une periode plus courte.",
        ) from exc

    db.add(
        models.ExportAudit(
            exported_by=user["username"],
            venue_id=venue.id,
            merchant_id=venue.merchant_id,
            kind="revenue_statement",
            subject_count=0,
            row_count=profile.count,
            period_start=since,
            period_end=until,
            occurred_at=now,
        )
    )
    await db.commit()
    return document
