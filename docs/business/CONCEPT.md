# Djassa — The Concept

> **Djassa turns everyday sales at neighbourhood shops into proof: a verified business history that the merchant owns and, with consent, can take to a licensed lender.**
>
> Public tagline: *Proof infrastructure for local commerce.*

This is the canonical definition of Djassa. The website, the two mobile apps, pitch material and partner notes must say the same thing as this document. When a claim changes here, change it in [`djassa-Web/src/content`](../../../djassa-Web/src/content/) too.

## 1. The name

**Djassa** /dja.sa/ is Nouchi, the street language of Abidjan. It means the informal street market, and by extension the daily hustle of the informal economy. We build for the merchants of the djassa, whose activity is real but leaves no proof behind.

Some early source documents call the financial-inclusion direction **Dkassa**. That name is retired: it is one product, Djassa. The final brand name still has to be confirmed legally before a public launch.

## 2. The problem

In Côte d'Ivoire, more than 25 million mobile-money accounts coexist with a strict banking rate of about 31% (sources in [MARKET.md](MARKET.md)). **Payment access is largely solved, but proof of business activity is not.**

A neighbourhood merchant (a maquis, a pharmacy, a grocery, a salon) typically has:

- Frequent customers but no usable digital sales history.
- No way to show a bank or microfinance institution (MFI) that the business is stable, so no working-capital or stock credit.
- Customer loyalty managed on paper cards, from memory, or in WhatsApp.
- Savings kept in tontines that are hard to track and secure.

The customer, meanwhile, has a mobile-money wallet but no single place to find where to eat, which pharmacy is open tonight, or what they have earned from being a regular.

## 3. The idea: one habit, five uses

Most merchant tools fail because each feature asks for a new habit. Djassa asks for **one**: record the sale. Everything else is a different view of the same event.

```text
                       THE EVENT
        a verified transaction: who · where · how much · when
                           │
   ┌──────────┬────────────┼─────────────┬──────────────┐
   ▼          ▼            ▼             ▼              ▼
 Loyalty    Revenue      Tontine      Reliability     Financing
 points     history      regularity   indicator       case sent to a
 (Phase 1)  (Phase 1)    (Phase 3)    (Phase 4)       licensed partner (Phase 5)
```

Loyalty, tontine, savings and credit are not five products shipped one after another. They become *visible* as the same event stream accumulates.

**Design rule:** a feature that would need a second habit from the merchant is out of scope, unless there is no other way to get the signal.

### Three ways an event is created

| Entry point | Who acts | Extra effort for the merchant | Extra fee | Strength of evidence |
|---|---|---|---|---|
| **1. Wallet payment, captured automatically** *(preferred)* | The customer pays the merchant's **existing** wallet QR as usual, and the operator notifies Djassa. Wave first: its `merchant.payment_received` webhook carries the amount, fee, customer phone and time. | **None** | None; the merchant keeps their current rate (~1% on Wave) | Confirmed by the provider |
| **2. Recorded sale** | The merchant records a cash sale in the merchant app, even offline; it syncs later without duplicates | One tap, plus the customer's phone for points | None | Declared by the merchant |
| **3. Djassa payment** | The customer scans the Djassa QR in the customer app, or approves a request on their phone, through an operator API (MTN MoMo request-to-pay, Orange Money) or a licensed aggregator | None | Operator rate (~1–2%) or aggregator fee (~3% + 50 F) | Confirmed by the provider |

All three feed the same history. **Entry point 1 is the strategic priority.** In Abidjan, 55–65% of a digitised merchant's takings already arrive by mobile money, and Wave charges merchants about 1% while an aggregator charges about 3% (see [MARKET.md § 9](MARKET.md#9-evidence-for-the-djassa-model)). Asking a merchant to move payments to a more expensive rail would destroy the value we sell. Instead, Djassa sits **on top of** the wallets merchants already use: their existing payments become the recorded history and earn customer points automatically. The merchant app handles cash, and the Djassa payment route is kept for merchants or wallets without direct integration.

This turns the concept's "one habit" into **zero habit** for mobile-money sales. It is the strongest answer to the failure pattern of African merchant tools (see [MARKET.md § 9](MARKET.md#9-evidence-for-the-djassa-model)). Access to Wave's Business API for small merchants, and the consent rules for customer phone numbers, must be confirmed in Phase 0.

### Operator-neutral by design

Djassa is **not tied to Wave**. It builds on whichever wallet the merchant already uses, and each operator is an adapter behind the same event stream:

| Order | Rail | Why this order |
|---|---|---|
| 1 | **Wave**: automatic capture of payments to the merchant's existing QR | Most small merchants, lowest merchant fee (~1%), and a confirmed webhook that notifies payments Djassa did not start |
| 2 | **MTN MoMo** (request-to-pay) and **Orange Money** (merchant API) | For merchants mainly on those networks. Both confirm payments Djassa starts; whether they can also notify payments to a merchant's static QR is to be confirmed |
| 3 | **PI-SPI interoperable QR**, the BCEAO's instant-payment platform linking every bank and wallet in UEMOA ([what it is](MARKET.md#what-pi-spi-is)), through a licensed partner | One QR that accepts any wallet or bank in UEMOA. When it is live for merchants in Côte d'Ivoire, it becomes the single operator-neutral rail and removes the question |
| Always | **Cash sale + phone number** | Works with any wallet or with cash, today; recorded as merchant-declared |

Whatever the rail, every sale lands in the same history with its evidence label, and the merchant never pays more for a payment than they do today.

## 4. The product today: four pieces

| Piece | Repository | Who uses it | What it does |
|---|---|---|---|
| **Merchant app** | `djassa-App-retailer` | Merchant, at the counter | Record a sale in seconds on a cheap Android phone, offline first; see the day's total; publish deals ("bons plans"). |
| **Customer app** | `djassa-App-user` | Customers in Abidjan | Find a maquis by dish or commune; see on-duty pharmacies ("pharmacies de garde") with a call button; browse deals; **pay by scanning the merchant's QR code** with Wave, Orange Money, MTN MoMo or Moov; earn points and redeem rewards at that merchant. |
| **Platform** | `djassa-BE` | Both apps, later partners | API, offline sync with idempotency, payments orchestration, loyalty ledger, deals, tontine and consent foundations, monitoring. |
| **Public site** | `djassa-Web` | Investors, institutions, partners | French and English presentation of this concept. |

The customer app is **optional**. A customer without it still identifies at the counter with a phone number or QR code, on the merchant's device. The app gives customers a daily reason to open it: food, a pharmacy tonight, a deal, a payment. Each of those daily reasons can create a payment-confirmed event.

What is actually built and what is not is tracked in [ROADMAP.md § Where we stand](ROADMAP.md#where-we-stand). Everything here is a **prototype**. Nothing moves real money yet.

## 5. Customer loyalty: how Djassa brings customers back

Loyalty is what the merchant pays for first, so its design is a business decision, not a detail.

- **The customer is recognised by phone number.** No card, no app required. A Wave payment, or a phone number typed at the counter, is enough. An SMS or WhatsApp message confirms the points ("+12 points at Maquis Chez Tanti — 3 visits to a free drink").
- **Rewards are funded by the merchant and cost them little:** a drink, a side dish, a discount, free delivery, priority service. They are never cash. The merchant sets the rule (points per 100 F) and the rewards, as the customer app already supports.
- **Start customers with progress already made.** A new customer joins with a few points already earned. In a field study, pre-stamped cards were completed 34% of the time against 19% for empty cards with the same effort required (endowed progress effect, see [MARKET.md](MARKET.md#9-evidence-for-the-djassa-model)).
- **Short distance to the first reward.** The first reward is reachable within 3–5 visits for a maquis and within 2–3 for a pharmacy, whose purchases are less frequent. Progress is always visible.
- **Win back lapsed customers.** The merchant sees who has not returned for N days and sends an offer (Phase 2). This turns the history into revenue the merchant can see.
- **Deals bring new customers.** Customer app deals and the paid featured slot bring first visits; points bring the second and third.
- **Network later.** Once a corridor has enough merchants, points could be earned at one merchant and spent at another, as Safaricom's Bonga points are redeemable at 140,000+ M-Pesa merchants. This needs clear merchant settlement rules and a regulatory check, because transferable points start to look like stored value. Until then, points stay per merchant.

What the merchant sees each week is a single number: **how many customers came back, and what they spent.** That number justifies the subscription.

## 6. How money moves, and how it does not

- A customer payment goes **directly from the customer's wallet to the merchant's own wallet**, through a licensed aggregator (such as CinetPay). **Djassa never holds the money.** The app tells the customer this at the moment of payment.
- The customer enters their PIN in the operator's app, never in Djassa's.
- Loyalty points are a merchant reward (a drink, a discount, a delivery). **They are not converted into cash** unless a BCEAO-compliant framework and licensed partner are in place.
- Savings (later) go from the user's wallet straight to an account held by a licensed partner. There is no transit account at Djassa, not even technically. A transit account would amount to deposit-taking.
- Credit (later) is granted and carried by a licensed MFI, bank or guarantee scheme. Djassa provides the consented history and the distribution channel, never the loan.

## 7. Identity: inherit trust, do not rebuild it

Verification follows the risk of the feature. Nobody goes through a full identity check to collect loyalty points.

| Tier | Use case | Minimum verification | Data boundary |
|---|---|---|---|
| **Tier 0** | Loyalty, deals, payments | Phone number or operator-linked identifier | No financial movement beyond the payment itself, no credit export |
| **Tier 1** | Tontine, partner savings | Phone verification plus lightweight liveness check where legally permitted | Biometric evidence verifies; it never becomes an identity database |
| **Tier 2** | History export to a licensed lender | Tier 1 plus national-ID capture and partner-approved cross-check | Only explicitly consented fields, for the stated purpose |

Djassa prefers a provider-issued verification result to storing raw identity or biometric data. A phone number alone is not proof of identity, and operator KYC is not reused without a legal, technical and consent agreement.

**Strategic horizon (a hypothesis, not a promise):** the event stream and these tiers could later found a *federated identity trust layer* for Côte d'Ivoire. It would orchestrate consent and normalise assurance levels between operators, KYC providers and licensed institutions, without owning national identity or copying any KYC database. This needs a separate legal and governance programme with ARTCI, BCEAO, operators and counsel. It is always presented as downstream of the merchant product.

## 8. The path to financial inclusion

Djassa is an **accelerator, not a gate**. It makes the route to credit faster and simpler. It is never presented as the only way to get credit ("no Djassa, no loan"). That framing would be coercive, would erode trust, and would draw regulatory concern.

In order, each step unlocked only when the previous one is proven by real use:

1. **Recorded history** (now): every sale structured so it can later support a solvency case; merchant and customer can always see their own history.
2. **Digital tontine**: existing groups track contributions, rotation order and reminders, with the existing social rules (closed group, fixed amount, turn order) respected. Each completed cycle becomes proof of regularity.
3. **Explainable reliability indicator**: built from purchase regularity, tontine cycles, savings regularity and seniority. The person affected can see what improves it. It is used internally first (e.g. deferred payment at a partner merchant).
4. **Partner financial services**: consented revenue-history export to an MFI or guarantee scheme for stock or working-capital credit or a revenue advance; goal-based savings held by a licensed partner.
5. **Financial education, in context**: a plain-language explanation at the moment it matters (first tontine cycle completed, first indicator improvement), never a standalone course nobody opens.

**Gender is a primary design constraint, not an option.** Women's usage is tracked on every financial feature. Scores must not penalise smaller transaction amounts, which reflect less access to capital, not less reliability.

## 9. Explaining Djassa to each audience

| Audience | In one sentence | What they get | What we never say |
|---|---|---|---|
| **Merchants** | "Record every sale in a few seconds, even without signal. Bring your customers back, and build the history of your business." | Loyalty and deals without building software; daily totals; a revenue history they own and can show a lender. | "Djassa will give you a loan." |
| **Customers** | "Find where to eat or which pharmacy is open, pay with your own wallet, and earn points where you shop." | A useful daily app, clear rewards, a view of their own activity. Their money never passes through Djassa. | "Your points are cash." |
| **Investors** | "A merchant SaaS wedge that compounds into the proof layer financial institutions lack, in a market with high mobile-money use but low credit access." | A paying first customer (the merchant), a data moat built from consented events, and numeric exit gates per phase. See [BUSINESS-MODEL.md](BUSINESS-MODEL.md). | "Pan-African super-app." |
| **Institutions and regulators** (APIF, BCEAO, ARTCI) | "Private execution for the national financial-inclusion strategy: structured, consented activity data for small merchants, with licensed institutions holding all funds." | Alignment with public programmes, a clear regulated perimeter, explainable indicators, gender tracking. | "We hold deposits" or "we score people opaquely." |
| **Financial partners** (MFIs, guarantee schemes) | "A distribution channel into small merchants, with consented, structured revenue histories you can assess." | Lower acquisition and assessment cost; referral model; direct fund flows to them. | "Guaranteed repayment." |
| **Payment partners** (aggregators, operators) | "Merchant QR payments that bring new, repeat volume onto your rails." | Transaction volume, merchant onboarding, no competition on custody. | "We are a wallet." |

The merchant message that must appear in every sales conversation:

> **Every sale you record with Djassa builds the proof of your business, the history a lender can assess when you need stock or working capital.**

It is a possible benefit, never a guaranteed loan and never a condition for credit.

## 10. Principles

- One country, one corridor (Abidjan first), one merchant segment at a time.
- Validate real usage before expanding. The master metric is the **% of a merchant's real sales recorded through Djassa**. One merchant recording 90% of sales for 60 days is a result; ten recording 10% for a week is noise.
- Low bandwidth and old phones are the target, not edge cases (Android 5, ~1 GB RAM, prepaid data). SMS and WhatsApp come before push notifications.
- Charge for merchant value before monetising financial referrals.
- **Never make a payment cost the merchant more than it does today.** Djassa builds on the wallets merchants already use; it does not compete with them for the payment.
- **Operator-neutral.** No dependency on a single wallet: Wave first, other operators next, the interoperable PI-SPI QR as the target.
- Users can see and correct their data; every score is explainable; merchant and customer data are separated and permissioned.
- Licensed institutions handle custody, lending and settlement.
- Women, rural users and low-income users are primary users.

## 11. Red lines

Djassa does **not**:

1. Promise loans, approval, rates or savings returns.
2. Hold deposits or savings, even temporarily, or lend without authorisation.
3. Share or resell identifiable data without a stated purpose and revocable consent.
4. Build an opaque score.
5. Launch cash-out, credit or any money movement beyond merchant payments without regulatory validation and a licensed partner.
6. Keep a reusable biometric database.
7. Launch pan-African; each new country needs its own partner, support, payment and compliance plan.
8. Target consumer personal finance. Djamo already leads that segment (see [MARKET.md](MARKET.md)).
9. Collect data that does not directly serve the person who generates it.

## Related documents

[MARKET.md](MARKET.md) · [BUSINESS-MODEL.md](BUSINESS-MODEL.md) · [ROADMAP.md](ROADMAP.md) · [PARTNERS.md](PARTNERS.md)
