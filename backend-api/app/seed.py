"""Sample maquis, pharmacies, shops and deals for development and demos.

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
from .core.phone import phone_key
from .db import DATABASE_URL, AsyncSessionLocal

DEV_MERCHANT_PHONE = "+2250700000002"
# A cashier at the merchant's maquis, and a field agent (djassa-installer).
DEV_CASHIER_PHONE = "+2250700000003"
DEV_AGENT_PHONE = "+2250700000004"
# Phone sign-in for djassa-installer in development (sample data only).
DEV_ADMIN_PHONE = "+2250700000009"

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

# Other retailers: category, name, commune, address, what they sell, hours, payout.
_SHOPS = [
    ("superette", "Superette Bon Prix (exemple)", "Cocody", "Angre 8e tranche", "Riz, huile, lait, produits frais", "7h - 22h", ("wave", "+2250700000021")),
    ("superette", "Alimentation Chez Moussa (exemple)", "Abobo", "Abobo Baoule", "Epicerie, boissons, recharges", "6h - 23h", ("orange", "+2250700000022")),
    ("mode", "Wax & Style (exemple)", "Treichville", "Marche de Treichville", "Pagnes wax, couture sur mesure", "9h - 19h", ("mtn", "+2250500000023")),
    ("mode", "Sneakers Plateau (exemple)", "Plateau", "Rue du Commerce", "Baskets, sacs, accessoires", "9h - 20h", None),
    ("beaute", "Salon Belle Tresse (exemple)", "Yopougon", "Selmer", "Tresses, perruques, manucure", "8h - 20h", ("wave", "+2250700000025")),
    ("telephonie", "Adjame Phone Center (exemple)", "Marcory", "Boulevard VGE", "Telephones, reparations, accessoires", "8h - 20h", ("moov", "+2250100000026")),
]

_REWARDS = {
    "maquis": [("Une boisson offerte", 50), ("Un alloco offert", 80), ("-2000 FCFA sur l'addition", 200)],
    "pharmacy": [("Livraison gratuite", 60), ("-1000 FCFA sur la prochaine ordonnance", 150)],
    "superette": [("Un pack d'eau offert", 80), ("-1000 FCFA sur les courses", 150)],
    "mode": [("Retouche offerte", 60), ("-10% sur un pagne", 200)],
    "beaute": [("Soin des mains offert", 100), ("-3000 FCFA sur une coiffure", 250)],
    "telephonie": [("Protection d'ecran offerte", 80), ("Diagnostic gratuit", 40)],
}

# Deals: venue name, title, description, discount %, price, original price,
# days left, featured (the paid publicity slot).
_DEALS = [
    ("Maquis Le Baobab (exemple)", "Poulet braise + attieke a 3 500 F", "Tous les jeudis soir.", None, 3500, 5000, 5, True),
    ("Superette Bon Prix (exemple)", "-20% sur le riz parfume 25 kg", "Dans la limite des stocks.", 20, None, None, 3, True),
    ("Wax & Style (exemple)", "Pagne 6 yards a 7 500 F", "Nouvelle collection.", None, 7500, 10000, 10, True),
    ("Salon Belle Tresse (exemple)", "-30% sur les tresses le mardi", None, 30, None, None, 14, False),
    ("Adjame Phone Center (exemple)", "Changement d'ecran des 15 000 F", "Garantie 3 mois.", None, 15000, 25000, 7, False),
    ("Chez Tantie Awa (exemple)", "Garba + boisson a 1 000 F", "Le midi en semaine.", None, 1000, 1300, 2, False),
    ("Pharmacie Riviera 3 (exemple)", "-15% sur la parapharmacie", "Hors medicaments.", 15, None, None, 6, False),
]


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
    # Phone sign-in for the merchant app: 07 00 00 00 02 runs the second
    # sample maquis. Locally the code comes back in the API response
    # (OTP_DEV_ECHO=1), so the app can be driven without a SIM.
    tantie = (
        await db.execute(select(models.Venue).where(models.Venue.name == _MAQUIS[1][0], models.Venue.owner_username.is_(None)))
    ).scalar_one_or_none()
    if tantie is not None:
        tantie.owner_username = phone_key(DEV_MERCHANT_PHONE)
        if (await db.execute(select(models.User).where(models.User.phone_e164 == DEV_MERCHANT_PHONE))).scalar_one_or_none() is None:
            db.add(models.User(phone_e164=DEV_MERCHANT_PHONE, roles="merchant", disabled=False,
                               created_at=datetime.now(timezone.utc).replace(tzinfo=None)))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for phone, role in ((DEV_ADMIN_PHONE, "admin"), (DEV_AGENT_PHONE, "agent")):
        if (await db.execute(select(models.User).where(models.User.phone_e164 == phone))).scalar_one_or_none() is None:
            db.add(models.User(phone_e164=phone, roles=role, disabled=False, created_at=now))
    # The cashier works at whichever venue the dev merchant runs, also on a
    # database seeded before cashiers existed.
    await db.flush()
    merchant_venue = (
        await db.execute(select(models.Venue.id).where(models.Venue.owner_username == phone_key(DEV_MERCHANT_PHONE)))
    ).scalars().first()
    cashier_key = phone_key(DEV_CASHIER_PHONE)
    has_cashier = (
        await db.execute(select(models.VenueStaff.id).where(models.VenueStaff.user_key == cashier_key))
    ).scalars().first()
    if merchant_venue is not None and has_cashier is None:
        db.add(models.VenueStaff(venue_id=merchant_venue, user_key=cashier_key, name="Caissier (exemple)",
                                 role="cashier", added_by=phone_key(DEV_MERCHANT_PHONE), created_at=now))
        if (await db.execute(select(models.User).where(models.User.phone_e164 == DEV_CASHIER_PHONE))).scalar_one_or_none() is None:
            db.add(models.User(phone_e164=DEV_CASHIER_PHONE, roles="cashier", disabled=False, created_at=now))
    await db.commit()


async def _seed_shops_and_deals(db) -> None:
    """Other retailers and sample deals. Idempotent, so a dev database seeded
    before these existed gets them on its next start."""
    has_shops = (
        await db.execute(select(func.count(models.Venue.id)).where(models.Venue.category == _SHOPS[0][0]))
    ).scalar_one()
    if not has_shops:
        for i, (category, name, commune, address, specialties, hours, payout) in enumerate(_SHOPS):
            venue = models.Venue(
                category=category,
                name=name,
                commune=commune,
                address=address,
                specialties=specialties,
                opening_hours=hours,
                phone=f"+225 00 00 00 30 {i:02d}",
                description="Commerce fictif, donnees de demonstration.",
                points_per_100=1,
                payout_provider=payout[0] if payout else None,
                payout_account=payout[1] if payout else None,
                is_sample=True,
            )
            venue.rewards = [models.LoyaltyReward(title=t, cost_points=c) for t, c in _REWARDS[category]]
            db.add(venue)
        await db.flush()

    if not (await db.execute(select(func.count(models.Deal.id)))).scalar_one():
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        venues = {v.name: v for v in (await db.execute(select(models.Venue).where(models.Venue.is_sample.is_(True)))).scalars()}
        for name, title, description, percent, price, original, days, featured in _DEALS:
            venue = venues.get(name)
            if venue is None:
                continue
            deal = models.Deal(
                venue_id=venue.id,
                title=title,
                description=description,
                discount_percent=percent,
                price=price,
                original_price=original,
                # Demo variety for the corner banner: the shortest deals are
                # flash sales, percentage ones wear the promo sticker.
                ribbon="flash" if days <= 1 else ("promo" if percent else "bon_plan"),
                starts_at=now - timedelta(days=1),
                ends_at=now + timedelta(days=days),
                is_featured=featured,
                active=True,
                created_at=now,
            )
            db.add(deal)
            if featured:
                # A featured sample deal gets a sample placement behind it:
                # `is_featured` is derived from a sold slot now, so seeding the
                # flag alone would create demo data the expiry sweep undoes.
                await db.flush()
                db.add(
                    models.DealPlacement(
                        deal_id=deal.id,
                        venue_id=venue.id,
                        starts_at=deal.starts_at,
                        ends_at=deal.ends_at,
                        price=0,  # demo data: nothing was really sold
                        currency="XOF",
                        status="active",
                        created_by="seed",
                        created_at=now,
                    )
                )
    await db.commit()


async def seed_sample_data() -> None:
    if not seeding_enabled():
        return
    async with AsyncSessionLocal() as db:
        if (await db.execute(select(func.count(models.Venue.id)))).scalar_one():
            await _seed_shops_and_deals(db)
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
        await _seed_shops_and_deals(db)
        await _backfill_pay_codes(db)
