"""Removes a shop and everything that hangs off it: the super admin's way to
clear test and pilot shops before production.

Unlike a customer's deletion (account_delete), nothing is kept: the shop's
sales, payments, points, deals, photos, staff, subscription and pilot record
go with it, found by following every foreign key that leads to the venue, so
a new table that points at a shop is covered without touching this file. The
owner's and cashiers' logins go too, unless they still run or work in another
shop or belong to the team.
"""

import json
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..db import Base
from . import account_delete

# Logins that are the team's, never removed with a shop.
TEAM_ROLES = {"admin", "superadmin", "agent"}


def _children(table_name: str):
    """(table, foreign key column) pairs pointing at `table_name`."""
    for table in Base.metadata.sorted_tables:
        for fk in table.foreign_keys:
            if fk.column.table.name == table_name:
                yield table, fk.parent


async def _rows_reached(db: AsyncSession, venue_id: int) -> dict[str, set]:
    """Primary keys of every row that leads to the venue, table by table."""
    reached: dict[str, set] = {"venues": {venue_id}}
    frontier = ["venues"]
    while frontier:
        parent = frontier.pop()
        for table, column in _children(parent):
            ids = (await db.execute(select(table.c.id).where(column.in_(reached[parent])))).scalars().all()
            new = set(ids) - reached.get(table.name, set())
            if new:
                reached.setdefault(table.name, set()).update(new)
                frontier.append(table.name)
    return reached


async def _logins(db: AsyncSession, venue: models.Venue) -> set[str]:
    keys = {venue.owner_username} if venue.owner_username else set()
    keys |= set((await db.execute(select(models.VenueStaff.user_key).where(models.VenueStaff.venue_id == venue.id))).scalars())
    return {k for k in keys if k.startswith("tel:")}


async def _still_needed(db: AsyncSession, key: str, user: models.User) -> bool:
    if user.role_set() & TEAM_ROLES:
        return True
    other_shop = await db.execute(select(models.Venue.id).where(models.Venue.owner_username == key).limit(1))
    other_post = await db.execute(
        select(models.VenueStaff.id).where(models.VenueStaff.user_key == key, models.VenueStaff.removed_at.is_(None)).limit(1)
    )
    return other_shop.first() is not None or other_post.first() is not None


async def delete_shop(db: AsyncSession, venue: models.Venue, now: datetime, decided_by: str) -> tuple[dict[str, int], list[str]]:
    """Deletes the shop and its rows, then the logins only it needed. Returns
    rows deleted per table, and the media storage keys for the caller to
    remove once committed. The caller commits."""
    logins = await _logins(db, venue)
    media_keys = [
        v["key"]
        for variants in (await db.execute(select(models.VenueMedia.variants).where(models.VenueMedia.venue_id == venue.id))).scalars()
        if variants
        for v in json.loads(variants).values()
    ]
    reached = await _rows_reached(db, venue.id)
    counts: dict[str, int] = {}
    # Children before parents: the reverse of the dependency order.
    for table in reversed(Base.metadata.sorted_tables):
        ids = reached.get(table.name)
        if ids:
            await db.execute(delete(table).where(table.c.id.in_(ids)))
            counts[table.name] = len(ids)
    db.expire_all()

    for key in logins:
        user = (await db.execute(select(models.User).where(models.User.phone_e164 == key[4:]))).scalar_one_or_none()
        if user is None or await _still_needed(db, key, user):
            continue
        try:
            await account_delete.delete_account(db, user, now, staff=True, decided_by=decided_by)
        except account_delete.LayawayInProgress:
            # Their own purchases elsewhere are not this shop's to cancel.
            continue
        counts["users"] = counts.get("users", 0) + 1
    return counts, media_keys
