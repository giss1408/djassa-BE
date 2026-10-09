"""Acceptance tests: business journeys, written in Gherkin (features/*.feature).

Each scenario runs against the real FastAPI app, over HTTP, on a fresh seeded
database, as the people who live it: a shop owner, the demo shop at the
counter, a customer with the app, an admin. The steps below are the only
code; the .feature files are meant to be read and reviewed by anyone.

pytest-bdd steps are plain functions, so each scenario gets its own event loop
(`World.run`) and every API call goes through it.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from pytest_bdd import given, parsers, then, when
from sqlalchemy import select

from app import models
from app.api.layaway import TERMS_VERSION
from app.db import AsyncSessionLocal, Base, engine
from app.main import app
from app.rate_limiter import limiter
from app.seed import seed_sample_data

# Statements need a period at least this long; every sale in a scenario lands today.
STATEMENT_PERIOD = {"from": "2026-01-01T00:00:00"}
ALL_CHECKS = ["called", "wallet_name_matches", "shop_seen"]


class World:
    """What one scenario knows: the client, who is signed in, what happened last."""

    def __init__(self, runner: asyncio.Runner, client: AsyncClient):
        self.runner = runner
        self.client = client
        self.shop = None  # the demo shop's headers
        self.customer_phone = None
        self.customer = None  # the customer app's headers
        self.applicant = None  # a shop owner asking to join: name, phone
        self.response = None
        self.plan = None
        self.statement = None
        self.sale_key = 0

    def run(self, coro):
        return self.runner.run(coro)

    def call(self, method, url, headers=None, **kwargs):
        self.response = self.run(self.client.request(method, url, headers=headers, **kwargs))
        return self.response

    def password_sign_in(self, username, password):
        r = self.call("POST", "/api/token", data={"username": username, "password": password})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def admin(self):
        return self.password_sign_in("admin", "admin123")

    def phone_sign_in(self, phone, app_name):
        """Phone and SMS code, the way the apps sign in. Returns the response."""
        self.run(_age_codes(400))  # skip the resend cooldown rather than wait it out
        code = self.call("POST", "/api/auth/otp/request", json={"phone": phone, "app": app_name})
        assert code.status_code == 202, code.text
        return self.call(
            "POST", "/api/auth/otp/verify", json={"phone": phone, "code": code.json()["dev_code"], "app": app_name}
        )

    def next_key(self, prefix):
        self.sale_key += 1
        return f"{prefix}-{self.sale_key:06d}"

    def demo_venue(self):
        return self.run(_demo_venue())

    def points_for(self, amount):
        """Points a sale of `amount` F earns at the demo shop."""
        return amount // 100 * self.demo_venue().points_per_100


async def _fresh_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await seed_sample_data()


async def _age_codes(seconds):
    async with AsyncSessionLocal() as db:
        for c in (await db.execute(select(models.OtpChallenge))).scalars():
            c.created_at -= timedelta(seconds=seconds)
            c.expires_at -= timedelta(seconds=seconds)
        await db.commit()


async def _demo_venue():
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(select(models.Venue).where(models.Venue.owner_username == "demo"))
        ).scalars().first()


async def _layaway_sales():
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(models.SaleEvent).where(models.SaleEvent.type == "layaway"))).scalars().all()


@pytest.fixture
def world(monkeypatch):
    # Codes come back in the response instead of by SMS.
    monkeypatch.setenv("OTP_SENDER", "console")
    monkeypatch.setenv("OTP_DEV_ECHO", "1")
    monkeypatch.delenv("FIDELIA_ENV", raising=False)
    limiter.enabled = False
    runner = asyncio.Runner()
    runner.run(_fresh_database())
    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    try:
        yield World(runner, client)
    finally:
        runner.run(client.aclose())
        runner.close()
        limiter.enabled = True


# --- Who is there -----------------------------------------------------------------


@given("the demo shop is signed in to Fidelia Pro")
def demo_shop_signed_in(world):
    world.shop = world.password_sign_in("demo", "demo123")


@given(parsers.parse('the customer "{phone}" agrees at the counter to collect points'))
def customer_agrees(world, phone):
    # Consent is given with the first sale; this remembers whose sale it is.
    world.customer_phone = phone


@given(parsers.parse('the customer signs in to the Fidelia app with "{phone}"'))
@when(parsers.parse('the customer signs in to the Fidelia app with "{phone}"'))
def customer_signs_in(world, phone):
    r = world.phone_sign_in(phone, "customer")
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "customer"
    world.customer = {"Authorization": f"Bearer {r.json()['access_token']}"}


# --- Joining Fidelia ------------------------------------------------------------


@given(parsers.parse('{name} asks to join Fidelia for her {category} "{shop}" with the number "{phone}"'))
def asks_to_join(world, name, category, shop, phone):
    code = world.call("POST", "/api/partner-requests/code", json={"phone": phone})
    assert code.status_code == 202, code.text
    body = {
        "phone": phone, "code": code.json()["dev_code"], "contact_name": name, "shop_name": shop,
        "category": category, "commune": "Abobo", "wallet_provider": "wave",
    }
    r = world.call("POST", "/api/partner-requests", json=body)
    assert r.status_code == 202, r.text
    world.applicant = {"name": name, "phone": phone}


def _pending_request(world, admin):
    pending = world.call("GET", "/api/admin/partner-requests", headers=admin).json()
    assert len(pending) == 1
    return pending[0]


@when(parsers.parse('an admin approves the request as "{shop}" after calling her, seeing the shop and checking the wallet name'))
def admin_approves(world, shop):
    admin = world.admin()
    request = _pending_request(world, admin)
    r = world.call(
        "POST", f"/api/admin/partner-requests/{request['id']}/approve",
        json={"name": shop, "points_per_100": 3, "checks": ALL_CHECKS}, headers=admin,
    )
    assert r.status_code == 200, r.text


@when("an admin tries to approve the request without checking the wallet name")
def admin_approves_without_checks(world):
    admin = world.admin()
    request = _pending_request(world, admin)
    world.call(
        "POST", f"/api/admin/partner-requests/{request['id']}/approve",
        json={"checks": ["called", "shop_seen"]}, headers=admin,
    )


@then("the approval is refused because the wallet holder was not checked")
def approval_refused(world):
    assert world.response.status_code == 422
    assert "Nom du titulaire" in world.response.json()["detail"]


@then(parsers.parse("{name} cannot sign in to Fidelia Pro yet"))
def cannot_sign_in(world, name):
    assert world.phone_sign_in(world.applicant["phone"], "merchant").status_code == 403


@then(parsers.parse("{name} can sign in to Fidelia Pro"))
def can_sign_in(world, name):
    r = world.phone_sign_in(world.applicant["phone"], "merchant")
    assert r.status_code == 200, r.text
    world.shop = {"Authorization": f"Bearer {r.json()['access_token']}"}


@then(parsers.parse('her shop "{shop}" has a payment QR'))
def shop_has_qr(world, shop):
    r = world.call("GET", "/api/merchant/pay-code", headers=world.shop)
    assert r.status_code == 200, r.text
    assert r.json()["qr_payload"].startswith("fidelia://pay/")
    venues = world.call("GET", "/api/admin/venues", headers=world.admin()).json()
    assert shop in [v["name"] for v in venues]


# --- Sales and points -------------------------------------------------------------


def _cash_sale(world, amount, phone, consent):
    body = {"amount": str(amount), "currency": "XOF", "type": "sale", "idempotency_key": world.next_key("acc-sale")}
    if phone is not None:
        body |= {"customer_phone": phone, "customer_consent": consent}
    return world.call("POST", "/api/merchant/sales", json=body, headers=world.shop)


@given(parsers.parse("the shop records {count:d} cash sales of {amount:d} F for that customer"))
@when(parsers.parse("the shop records {count:d} cash sales of {amount:d} F for that customer"))
def records_sales(world, count, amount):
    for _ in range(count):
        r = _cash_sale(world, amount, world.customer_phone, consent=True)
        assert r.status_code == 201, r.text


@given(parsers.parse("the shop records a cash sale of {amount:d} F"))
def records_anonymous_sale(world, amount):
    r = _cash_sale(world, amount, None, consent=False)
    assert r.status_code == 201, r.text


@when(parsers.parse('the shop records a cash sale of {amount:d} F for "{phone}" without asking for consent'))
def records_sale_without_consent(world, amount, phone):
    world.customer_phone = phone
    _cash_sale(world, amount, phone, consent=False)


@then("the sale is refused so the shop can ask the customer")
def sale_refused_for_consent(world):
    assert world.response.status_code == 422
    assert "accepte" in world.response.json()["detail"]


@when(parsers.parse("the phone sends the same sale of {amount:d} F twice after a lost connection"))
def same_sale_twice(world, amount):
    op = {"amount": str(amount), "idempotency_key": "acc-offline-000001",
          "customer_phone": world.customer_phone, "customer_consent": True}
    # The second send is recognised as the same sale, not refused.
    for expected in ("accepted", "already_processed"):
        r = world.call("POST", "/api/merchant/sales/sync", json={"operations": [op]}, headers=world.shop)
        assert r.status_code == 200, r.text
        assert r.json()["results"][0]["status"] == expected


def _balance(world):
    r = world.call("POST", "/api/merchant/customers/loyalty", json={"phone": world.customer_phone}, headers=world.shop)
    assert r.status_code == 200, r.text
    return r.json()


@then(parsers.parse("the customer has the points for {amount:d} F at the shop"))
def has_points_for(world, amount):
    assert _balance(world)["points"] == world.points_for(amount)


@then("the customer has no points at the shop")
def has_no_points(world):
    assert _balance(world)["points"] == 0


@then(parsers.parse("the shop has {count:d} sale for that customer"))
def shop_has_sales(world, count):
    async def customer_sales():
        async with AsyncSessionLocal() as db:
            key = "tel:+225" + "".join(c for c in world.customer_phone if c.isdigit())
            return (await db.execute(select(models.SaleEvent).where(models.SaleEvent.customer_id == key))).scalars().all()

    assert len(world.run(customer_sales())) == count


@when("the shop hands over its cheapest reward to the customer")
def hands_over_reward(world):
    balance = _balance(world)
    reward = min(balance["rewards"], key=lambda x: x["cost_points"])
    world.reward_cost, world.points_before = reward["cost_points"], balance["points"]
    r = world.call(
        "POST", "/api/merchant/customers/redeem",
        json={"phone": world.customer_phone, "reward_id": reward["id"]}, headers=world.shop,
    )
    assert r.status_code == 201, r.text


@then("the customer gets a 6-character voucher code")
def gets_voucher(world):
    assert len(world.response.json()["voucher_code"]) == 6


@then("the reward's cost is taken off the customer's points")
def reward_cost_deducted(world):
    assert _balance(world)["points"] == world.points_before - world.reward_cost


@then(parsers.parse("the app shows the points for {amount:d} F at the shop"))
def app_shows_points(world, amount):
    mine = world.call("GET", "/api/customer/loyalty", headers=world.customer).json()
    venue_id = world.demo_venue().id
    assert [v["points"] for v in mine["venues"] if v["venue_id"] == venue_id] == [world.points_for(amount)]


# --- Consent ----------------------------------------------------------------------


@when("the customer withdraws their consent in the app")
def withdraws_consent(world):
    r = world.call("DELETE", "/api/customer/loyalty-consent", headers=world.customer)
    assert r.status_code == 200, r.text


@then(parsers.parse("the app says the points for {amount:d} F at the shop were erased"))
def points_erased(world, amount):
    assert world.response.json()["points_erased"] == world.points_for(amount)


@then("the app shows no points")
def app_shows_no_points(world):
    mine = world.call("GET", "/api/customer/loyalty", headers=world.customer).json()
    assert mine["total_points"] == 0
    consent = world.call("GET", "/api/customer/loyalty-consent", headers=world.customer).json()
    assert consent["active"] is False


@then("the shop must ask the customer again before the next sale earns points")
def must_ask_again(world):
    assert _cash_sale(world, 5000, world.customer_phone, consent=False).status_code == 422
    assert _cash_sale(world, 5000, world.customer_phone, consent=True).status_code == 201


# --- Layaway ----------------------------------------------------------------------


@given("an admin has switched on layaway for the demo shop")
def layaway_on(world):
    r = world.call("PUT", f"/api/admin/venues/{world.demo_venue().id}/layaway", json={"enabled": True}, headers=world.admin())
    assert r.status_code == 200, r.text


def _open_plan(world, item, price, phone, first, accepted):
    due = (datetime.now(timezone.utc) + timedelta(days=60)).isoformat()
    body = {
        "customer_phone": phone, "item": item, "price": price, "due_by": due,
        "terms_version": TERMS_VERSION, "terms_accepted": accepted,
        "first_installment": {"amount": first, "idempotency_key": world.next_key("acc-lay")},
    }
    r = world.call("POST", "/api/merchant/layaway", json=body, headers=world.shop)
    world.customer_phone = phone
    if r.status_code == 201:
        world.plan = r.json()


OPEN_PLAN = 'the shop opens a plan for "{item}" at {price:d} F for "{phone}" with a first payment of {first:d} F'


@when(parsers.parse(OPEN_PLAN + ", after reading the terms to the customer"))
def opens_plan(world, item, price, phone, first):
    _open_plan(world, item, price, phone, first, accepted=True)
    assert world.response.status_code == 201, world.response.text


@when(parsers.parse(OPEN_PLAN + ", without the customer accepting the terms"))
def opens_plan_without_terms(world, item, price, phone, first):
    _open_plan(world, item, price, phone, first, accepted=False)


@then("the plan is refused")
def plan_refused(world):
    assert world.response.status_code == 422


@then("the shop has no layaway plans")
def no_plans(world):
    assert world.call("GET", "/api/merchant/layaway", headers=world.shop).json() == []


@then(parsers.parse("the plan is open with {remaining:d} F left to pay"))
def plan_open(world, remaining):
    assert (world.plan["status"], world.plan["remaining"]) == ("open", remaining)


@when(parsers.parse("the shop records a payment of {amount:d} F"))
def records_installment(world, amount):
    r = world.call(
        "POST", f"/api/merchant/layaway/{world.plan['id']}/installments",
        json={"amount": amount, "idempotency_key": world.next_key("acc-lay")}, headers=world.shop,
    )
    assert r.status_code == 201, r.text
    world.plan = r.json()


@then("the plan is paid and waiting for handover")
def plan_paid(world):
    assert (world.plan["status"], world.plan["remaining"]) == ("completed", 0)


@when("the shop hands over the fridge")
def hands_over_good(world):
    r = world.call("POST", f"/api/merchant/layaway/{world.plan['id']}/deliver", headers=world.shop)
    assert r.status_code == 200, r.text
    world.plan = r.json()


@then("the plan is delivered")
def plan_delivered(world):
    assert world.plan["status"] == "delivered"


@then(parsers.parse("the shop's history has one layaway sale of {amount:d} F"))
def one_layaway_sale(world, amount):
    assert [s.amount for s in world.run(_layaway_sales())] == [amount]


@then("the shop's history has no layaway sale")
def no_layaway_sale(world):
    assert world.run(_layaway_sales()) == []


@then("the customer sees the delivered plan in the Fidelia app")
def customer_sees_plan(world):
    customer_signs_in(world, world.customer_phone)
    plans = world.call("GET", "/api/customer/layaway", headers=world.customer).json()
    assert [(p["item"], p["status"]) for p in plans] == [(world.plan["item"], "delivered")]


@when(parsers.parse("the shop cancels the plan and gives back {amount:d} F"))
def cancels_plan(world, amount):
    r = world.call(
        "POST", f"/api/merchant/layaway/{world.plan['id']}/cancel",
        json={"reason": "le client a change d'avis", "refunded_amount": amount}, headers=world.shop,
    )
    assert r.status_code == 200, r.text
    world.plan = r.json()


@then(parsers.parse("the plan is cancelled with {amount:d} F refunded"))
def plan_cancelled(world, amount):
    assert (world.plan["status"], world.plan["refunded_amount"]) == ("cancelled", amount)


@then("no further payment can be recorded on it")
def no_more_payments(world):
    r = world.call(
        "POST", f"/api/merchant/layaway/{world.plan['id']}/installments",
        json={"amount": 1000, "idempotency_key": world.next_key("acc-lay")}, headers=world.shop,
    )
    assert r.status_code == 409


# --- Revenue statement ------------------------------------------------------------


@given("the demo shop is on the network plan")
def network_plan(world):
    r = world.call(
        "PUT", f"/api/admin/venues/{world.demo_venue().id}/subscription",
        json={"plan": "network", "amount": 25000, "status": "active"}, headers=world.admin(),
    )
    assert r.status_code == 200, r.text


@given(parsers.parse("a customer pays the shop {amount:d} F with Wave"))
def customer_pays_with_wave(world, amount):
    request = world.call("POST", "/api/merchant/payment-requests", json={"amount": amount}, headers=world.shop)
    assert request.status_code == 201, request.text
    paid = world.call(
        "POST", "/api/customer/payments",
        json={"pay_code": request.json()["code"], "wallet_provider": "wave",
              "payer_msisdn": "+2250700000088", "idempotency_key": world.next_key("acc-pay")},
        headers=world.password_sign_in("client", "client123"),
    )
    assert paid.status_code == 201 and paid.json()["status"] == "succeeded", paid.text


@when("the shop downloads its revenue statement")
def downloads_statement(world):
    r = world.call("GET", "/api/merchant/statement", params=STATEMENT_PERIOD, headers=world.shop)
    assert r.status_code == 200, r.text
    world.statement = r.json()


@then(parsers.parse("the statement counts {amount:d} F of turnover"))
def statement_turnover(world, amount):
    assert Decimal(world.statement["payload"]["turnover"]["total"]) == amount


@then("the statement names no customer")
def statement_names_nobody(world):
    text = str(world.statement["payload"])
    assert "+225" not in text and "tel:" not in text and "client" not in text


def _verify(world, payload):
    r = world.call(
        "POST", "/api/statements/verify",
        json={"payload": payload, "signature": world.statement["signature"]["value"]}, headers=world.shop,
    )
    assert r.status_code == 200, r.text
    return r.json()["valid"]


@then("a partner checking the statement finds it genuine")
def statement_genuine(world):
    assert _verify(world, world.statement["payload"]) is True


@then("a partner checking a copy with the turnover inflated finds it forged")
def statement_forged(world):
    payload = world.statement["payload"]
    inflated = {**payload, "turnover": {**payload["turnover"], "total": "400000"}}
    assert _verify(world, inflated) is False
