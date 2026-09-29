"""The featured-slot expiry sweep.

`Deal.is_featured` is what the apps read, but a placement is what is sold. This
runs the reconciliation periodically so a campaign leaves the carousel when its
window closes even if nobody touches the admin API. Reads are defended anyway
(`list_deals` filters on live placements), so a missed sweep shows nothing stale
to a customer — it only leaves the boolean briefly out of date.
"""

from ..db import AsyncSessionLocal


async def expire_finished_placements() -> int:
    """Expire placements past their window. Returns how many changed."""
    from ..api.deals import refresh_featured_flags  # local: avoids an import cycle

    async with AsyncSessionLocal() as session:
        expired = await refresh_featured_flags(session)
        await session.commit()
        return expired


def expire_finished_placements_sync() -> int:
    import asyncio

    return asyncio.run(expire_finished_placements())
