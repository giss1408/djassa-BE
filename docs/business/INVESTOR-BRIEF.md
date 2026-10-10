# Fidelia — Investor Brief

*Pre-seed · Abidjan, Côte d'Ivoire · October 2026* · [Version française](INVESTOR-BRIEF.fr.md)

> **Placeholders.** Everything marked `[PLACEHOLDER]` (company registration, ownership) is dummy data to be replaced before this brief is sent to anyone. Market figures carry their sources in [MARKET.md](MARKET.md) and must be re-checked before contractual use.
>
> Keep this file, its French translation ([INVESTOR-BRIEF.fr.md](INVESTOR-BRIEF.fr.md)) and the web page (`fidelia-Web/public/brief/`) in step: a change to one is a change to all three.

## In one sentence

**Fidelia turns everyday sales at neighbourhood shops into proof: a verified business history that the merchant owns and, with consent, can take to a licensed lender.** Merchants pay for it because it brings their customers back.

## The problem

- Côte d'Ivoire has **25M+ active mobile-money accounts** but a **31.2% strict banking rate** (BCEAO; national indicators 2023). Payment access is largely solved; **proof of business activity is not**.
- A maquis or grocery shop has frequent customers but **no usable sales history**, so no working-capital or stock credit. SMEs are ~20% of GDP and face collateral they cannot provide.
- Customer loyalty lives on paper cards and memory. Nothing brings a regular back on purpose.

## The product

One habit, recording the sale, produces five uses: loyalty, revenue history, tontine regularity, a reliability indicator and a financing case for a licensed partner.

- **One daily cash book from day 1.** Every wallet payment and every cash sale in one daily total, so the merchant no longer reconciles Wave, Orange and MTN by hand. This is what the merchant sees in the first week; loyalty is why they stay.
- **Zero extra effort on mobile money.** Fidelia builds on the wallet the merchant already uses. The merchant's existing QR payments are captured automatically, Wave first, then other operators and the interoperable QR of **PI-SPI**, the central bank's platform that links every bank and mobile wallet in the UEMOA zone ([details](MARKET.md#what-pi-spi-is)). **No extra fee, no new habit.**
- **Cash sales count too.** They take one tap in the merchant app, even offline. With the customer's phone number, the customer earns points.
- **Loyalty the merchant can see.** Points, rewards handed over at the counter, deals, and a weekly "customers who came back" figure.
- **Proof for credit, with consent.** Each sale is labelled *confirmed by the provider* or *declared by the merchant*, and exported only with consent to a licensed MFI or guarantee scheme.
- **New customers for the merchant.** Merchants attract customers today by word of mouth, by being nearby and through social networks. The customer app turns that into a map of nearby maquis and grocery shops, free merchant offers with notifications, and points. On-duty pharmacies give people a daily reason to install it.
- **Three pieces in the pilot:** a merchant app (offline-first, cheap Android), a customer app, and the platform. **The pilot is free for every merchant**; the paid plan is offered when it ends.

**Fidelia never holds funds and never lends.** Licensed institutions keep custody and credit. Fidelia is the technology and distribution partner.

## Why now

- **Merchant payments are taking off:** 2.72M merchant payment points in Côte d'Ivoire in 2024, up from 1.13M. Merchant payments are 23.3% of mobile-money volume, up from 3.3% in 2020 (BCEAO data).
- **Payment acceptance is a commodity** (Wave ~1% for the merchant). What is missing sits on top of it: recognising customers and proving activity.
- **The BCEAO** has opened a workstream on alternative credit scoring and launched **PI-SPI** (interoperable instant payments, mandatory since June 2026). Public programmes (APIF, SGPME, GUDE-PME) are looking for private execution partners.
- **Comparables:** in Nigeria, Moniepoint's loans underwritten from payment data were followed by **+36%** transaction value. In Kenya, Kopo Kopo saw **+42%** transaction growth after cash advances.

## Business model

Merchant software first, financial infrastructure second.

| Stream | When |
|---|---|
| Merchant subscription: capped free plan, then ~5,000 F and ~10,000–15,000 F / month / outlet *(hypotheses to test)* | After the pilot (the pilot is free) |
| Sponsored deals and campaigns: one-off, time-limited placement for a merchant product, service or special offer in the customer app; pricing is to be tested | After the pilot (offers are free during the pilot) |
| Multi-outlet and network contracts | After proof |
| Consented partner commissions (credit, savings, tontine): Fidelia earns distribution fees, never carries credit risk | After partnership |

**Why a merchant pays:** a small maquis earning +5% from returning customers gains about 73,000 F of gross profit a month against a 5,000 F subscription (illustrative; see [BUSINESS-MODEL.md](BUSINESS-MODEL.md)). Routing its payments through a ~3% aggregator would cost it more than that. This is why Fidelia never replaces the merchant's wallet.

## Positioning

Fidelia avoids consumer personal finance (Djamo) and B2B payments (Julaya, Hub2), and partners with payment rails (Wave, Orange, MTN, CinetPay). **Customer loyalty and merchant activity proof** have no dominant Ivorian player.

## Traction

**Pre-pilot. No users, merchants or revenue yet.** What exists is working prototypes (on the `integration` branch):

- A merchant app recording sales offline, tested on a real device, with no duplicates after a dropped connection.
- A customer app for discovery, on-duty pharmacies, deals, sandbox QR payment and points.
- **Points on cash sales by phone**, with balance and rewards handed over at the counter.
- **One sale history** labelled by evidence, sold featured slots, a billing ledger, and an audited consented export.
- A public site built for low bandwidth (~120 KB on first visit, works offline).

## Milestones this round funds

The round funds the six-month pilot, in two tranches. Each tranche pays for one phase; the second is released only when the first phase's exit gate is met.

| Tranche · phase | Evidence required |
|---|---|
| **Tranche 1 · Phase 0: discovery, compliance and production readiness** (months 1–2) | 5–10 interviews with maquis and grocery owners in one Abidjan commune; Wave API access confirmed; regulatory perimeter and ARTCI review; one payment partner; one or two MFIs asked whether they would pay for a consented tool to follow their merchant borrowers' sales |
| **Tranche 2 · Phase 1: free pilot, 5–10 merchants** (months 3–6) | Phone login (OTP), automatic Wave capture, one live payment partner. **Exit:** ≥ 70% of real sales recorded at day 30, rising toward 85% at day 60; the app brings new customers, recorded at the counter; ≥ 40% of merchants accept the paid plan when the free pilot ends |
| **After this round** | A seed round priced on the pilot's results. Then the unit-economics gate before any second commune: acquisition cost below 12 months of gross profit, 3 months of retention, known support and messaging cost per outlet |

No geographic expansion before one commune passes the gate.

## Team

| | Role | Responsible for |
|---|---|---|
| **Stanislas Regisse** | CEO | Technical implementation and security |
| **Bienvenue Kouadio** | Marketing | Partner and investor contact, finances, marketing strategy |

## Company status

| | |
|---|---|
| Legal entity | `[PLACEHOLDER]` Fidelia SAS, Abidjan, Côte d'Ivoire (OHADA) |
| Registration (RCCM) | `[PLACEHOLDER]` CI-ABJ-2026-B-00000 |
| Share capital | `[PLACEHOLDER]` 1,000,000 FCFA |
| Ownership | `[PLACEHOLDER]` Stanislas Regisse 50% · Bienvenue Kouadio 50% |
| Prior funding | `[PLACEHOLDER]` None (founder-funded) |
| IP | `[PLACEHOLDER]` Code and brand assigned to the company |
| Final brand name | To be confirmed legally before public launch |

## The ask

| | |
|---|---|
| Round | Pre-seed **pilot round: XOF 31M (€47,260, about USD 53,000)**. It funds the six-month pilot only, as budgeted in [FINANCE-BUDGET.md](FINANCE-BUDGET.md) |
| Tranche 1, at signing | **XOF 14M (€21,340)** for months 1–2: regulatory and data-protection review, production readiness (phone login, Wave capture, security review), test devices |
| Tranche 2, at the Phase 0 exit gate | **XOF 17M (€25,920)** for months 3–6, the field pilot. Released when a licensed payment partner is confirmed and Wave has answered on API access, 5–10 maquis and grocery owners have signed the pilot agreement, and the production-readiness review has no open critical issue |
| Instrument | BSA AIR adapted to OHADA law (ABAN template, reviewed by OHADA counsel): no interest and no repayment; converts into shares at the next priced round |
| Terms | Valuation cap **USD 1.3M post-money** (about 4% for the full round) · 20% discount on the next round · same terms for both tranches |
| Use of funds | People 29% · legal, regulatory and security 15% · product and infrastructure 15% · test devices 10% · field operations 8% · launch 6% · administration 4% · contingency 13% |
| Runway to | The end of the pilot (month 6), when the Phase 1 exit gate is measured |
| Next round | Seed, priced on the pilot's results, aimed at funds that add capital as agreed KPIs are met |
| Non-dilutive | Grants targeted in parallel (APIF-CI fintech project, AfDB digital financial inclusion facility, develoPPP); a grant lowers the amount raised |

*USD at about €1 = USD 1.13 (October 2026); the CFA franc is fixed to the euro (€1 = XOF 655.957). Terms are a proposal, to be confirmed with OHADA counsel.*

## Red lines

No loan promise. No deposits held by Fidelia. No data shared without consent. No opaque score. No pan-African launch. No reusable biometric database. These shape what we build and what we refuse to sell ([CONCEPT.md § 11](CONCEPT.md#11-red-lines)).

## Contact

Bienvenue Kouadio (partner and investor contact) · contact.fidelia@regisse.com

*Information document. Not an offer of financial services or of securities. Figures from public sources are cited in [MARKET.md](MARKET.md); illustrative economics are labelled as such.*
