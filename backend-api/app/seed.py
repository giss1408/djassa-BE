"""Sample maquis and pharmacies for development and demos.

Everything here is invented: every name ends in "(exemple)", every phone number
is a 00-prefixed placeholder, and every row has `is_sample=True` so the app can
say so. Real on-duty pharmacy data must come from the official weekly rotation
(entered through POST /api/admin/pharmacies/{id}/duties), never from this file.

Runs only when DJASSA_SEED_SAMPLE is truthy, which defaults to on for the
SQLite dev database and off for anything else.
"""

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from . import models
from .db import DATABASE_URL, AsyncSessionLocal

_MAQUIS = [
    # name, commune, address, specialties, hours, points_per_100, payout
    ("Maquis Le Baobab (exemple)", "Cocody", "Riviera 2, pres du carrefour", "Poulet braise, attieke poisson, alloco", "12h - 2h", 2, ("wave", "+2250700000001")),
    ("Chez Tantie Awa (exemple)", "Yopougon", "Rue Princesse", "Garba, poisson braise, kedjenou", "11h - 1h", 1, ("orange", "+2250700000002")),
    ("Le Grin du Plateau (exemple)", "Plateau", "Avenue Chardy", "Brochettes, placali, sauce graine", "11h - 23h", 1, ("mtn", "+2250500000003")),
    ("Maquis La Lagune (exemple)", "Marcory", "Zone 4, bord lagune", "Poisson braise, attieke, bangui", "17h - 3h", 3, ("moov", "+2250100000004")),
    ("Espace Doh (exemple)", "Treichville", "Avenue 16", "Kedjenou de poulet, foutou banane", "12h - 0h", 1, None),
]

_PHARMACIES = [
    ("Pharmacie Riviera 3 (exemple)", "Cocody", "Riviera 3, face au marche", ("wave", "+2250700000011")),
    ("Pharmacie des Deux Plateaux (exemple)", "Cocody", "Boulevard Latrille", ("orange", "+2250700000012")),
    ("Pharmacie Siporex (exemple)", "Yopougon", "Carrefour Siporex", None),
    ("Pharmacie du Port (exemple)", "Treichville", "Boulevard de Marseille", ("mtn", "+2250500000014")),
    ("Pharmacie Zone 4 (exemple)", "Marcory", "Rue du Dr Blanchard", ("wave", "+2250700000015")),
    ("Pharmacie Abobo Gare (exemple)", "Abobo", "Gare d'Abobo", None),
]

_REWARDS = {
    "maquis": [("Une boisson offerte", 50), ("Un alloco offert", 80), ("-2000 FCFA sur l'addition", 200)],
    "pharmacy": [("Livraison gratuite", 60), ("-1000 FCFA sur la prochaine ordonnance", 150)],
}



def seeding_enabled() -> bool:
    default = "1" if DATABASE_URL.startswith("sqlite") else "0"
    return os.getenv("DJASSA_SEED_SAMPLE", default).lower() in ("1", "true", "yes")


async def _backfill_pay_codes(db) -> None:
    from .api.customer import new_pay_code

    missing = (
        await db.execute(
            select(models.Venue).where(
                models.Venue.is_sample.is_(True),
                models.Venue.pay_code.is_(None),
                models.Venue.payout_account.is_not(None),
            )
        )
    ).scalars().all()
    for venue in missing:
        venue.pay_code = new_pay_code()
    # The merchant app's demo login runs the first sample maquis, so it can
    # show payment QR codes out of the box.
    baobab = (
        await db.execute(select(models.Venue).where(models.Venue.name == _MAQUIS[0][0], models.Venue.owner_username.is_(None)))
    ).scalar_one_or_none()
    if baobab is not None:
        baobab.owner_username = "demo"
    await db.commit()


async def seed_sample_data() -> None:
    if not seeding_enabled():
        return
    async with AsyncSessionLocal() as db:
        if (await db.execute(select(func.count(models.Venue.id)))).scalar_one():
            await _backfill_pay_codes(db)
            return

        for i, (name, commune, address, specialties, hours, rate, payout) in enumerate(_MAQUIS):
            venue = models.Venue(
                category="maquis",
                name=name,
                commune=commune,
                address=address,
                specialties=specialties,
                opening_hours=hours,
                phone=f"+225 00 00 00 10 {i:02d}",
                description="Etablissement fictif, donnees de demonstration.",
                points_per_100=rate,
                payout_provider=payout[0] if payout else None,
                payout_account=payout[1] if payout else None,
                is_sample=True,
            )
            venue.rewards = [models.LoyaltyReward(title=t, cost_points=c) for t, c in _REWARDS["maquis"]]
            db.add(venue)

        # On duty: the week-long rotation runs Saturday 08:00 to Saturday 08:00
        # (UTC = Abidjan time). Alternate pharmacies are on duty this week and
        # next, so the screen shows a realistic subset rather than everyone.
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        days_since_saturday = (now.weekday() - 5) % 7
        week_start = (now - timedelta(days=days_since_saturday)).replace(hour=8, minute=0, second=0, microsecond=0)
        if week_start > now:
            week_start -= timedelta(days=7)

        for i, (name, commune, address, payout) in enumerate(_PHARMACIES):
            venue = models.Venue(
                category="pharmacy",
                name=name,
                commune=commune,
                address=address,
                phone=f"+225 00 00 00 20 {i:02d}",
                opening_hours="8h - 20h (24h/24 quand de garde)",
                description="Pharmacie fictive, donnees de demonstration.",
                points_per_100=1,
                payout_provider=payout[0] if payout else None,
                payout_account=payout[1] if payout else None,
                is_sample=True,
            )
            venue.rewards = [models.LoyaltyReward(title=t, cost_points=c) for t, c in _REWARDS["pharmacy"]]
            offset = 0 if i % 2 == 0 else 7
            start = week_start + timedelta(days=offset)
            venue.duties = [models.PharmacyDuty(starts_at=start, ends_at=start + timedelta(days=7))]
            db.add(venue)

        await db.commit()
        await _backfill_pay_codes(db)
