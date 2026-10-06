"""App error reports: accepted without sign-in, scrubbed, grouped per bug."""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import models
from app.api.client_events import fingerprint, scrub, scrub_tokens
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.rate_limiter import limiter

STACK = "#0      DealsTab.build (package:hossouko_user/features/deals_tab.dart:42:7)\n#1      StatelessElement.build"


@pytest_asyncio.fixture
async def client():
    limiter.enabled = False
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    limiter.enabled = True


def _batch(**overrides):
    body = {
        "app": "user", "app_version": "0.1.0+1", "platform": "android", "os_version": "Android 5.1",
        "events": [{
            "kind": "error", "message": "Null check operator used on a null value",
            "stack": STACK, "count": 3, "occurred_at": datetime.now(timezone.utc).isoformat(),
        }],
    }
    body.update(overrides)
    return body


async def _admin(ac):
    r = await ac.post("/api/token", data={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.mark.asyncio
async def test_reports_are_accepted_without_sign_in_and_grouped(client):
    assert (await client.post("/api/client-events", json=_batch())).status_code == 202
    # Same bug, another build and line number: still one group.
    other = _batch(app_version="0.1.1+2")
    other["events"][0]["stack"] = STACK.replace(":42:7", ":45:9")
    assert (await client.post("/api/client-events", json=other)).status_code == 202

    groups = (await client.get("/api/admin/client-events", headers=await _admin(client))).json()
    assert len(groups) == 1
    assert groups[0]["occurrences"] == 6
    assert groups[0]["reports"] == 2
    assert groups[0]["latest_version"] == "0.1.1+2"

    metrics = (await client.get("/metrics")).text
    assert 'hossouko_client_events_total{app="user"' in metrics


@pytest.mark.asyncio
async def test_personal_data_is_scrubbed(client):
    body = _batch()
    body["events"][0]["message"] = "Payment failed for +225 07 12 34 56 78 amount 1500000 token eyJhbGc.eyJzdWIi.sig"
    await client.post("/api/client-events", json=body)
    async with AsyncSessionLocal() as db:
        row = (await db.execute(select(models.ClientEvent))).scalar_one()
    assert "0712" not in row.message.replace(" ", "")
    assert "1500000" not in row.message
    assert "eyJ" not in row.message


@pytest.mark.asyncio
async def test_bounds(client):
    assert (await client.post("/api/client-events", json=_batch(app="other"))).status_code == 422
    # Free-form versions would explode Prometheus label cardinality.
    assert (await client.post("/api/client-events", json=_batch(app_version="nightly-abc"))).status_code == 422
    too_many = _batch()
    too_many["events"] = too_many["events"] * 21
    assert (await client.post("/api/client-events", json=too_many)).status_code == 422


@pytest.mark.asyncio
async def test_only_admin_reads_reports(client):
    r = await client.post("/api/token", data={"username": "client", "password": "client123"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.get("/api/admin/client-events", headers=h)).status_code == 403


def test_obfuscated_stacks_group_by_frame_and_stay_symbolizable():
    header = "*** *** ***\npid: 4321, tid: 4400, name 1.ui\nbuild_id: 'f00dbeef'\n"
    a = header + "#00 abs 000000723d4b1e33 virt 00000000001b5e33 _kDartIsolateSnapshotInstructions+0x1a5e33"
    b = header + "#00 abs 000000723d4c0000 virt 00000000001c0000 _kDartIsolateSnapshotInstructions+0x1b0000"
    same_bug_other_run = a.replace("000000723d4b1e33", "000000611a0b1e33").replace("4321", "999")
    assert fingerprint("user", "crash", "x", a) != fingerprint("user", "crash", "x", b)
    assert fingerprint("user", "crash", "x", a) == fingerprint("user", "crash", "x", same_bug_other_run)
    assert scrub_tokens(a) == a


def test_helpers():
    assert scrub("call 0712345678") == "call <num>"
    assert scrub("Authorization: Bearer abc.def") == "Authorization: Bearer <token>"
    assert fingerprint("user", "error", "x", STACK) == fingerprint("user", "error", "y", STACK.replace(":42:7", ":1:1"))
