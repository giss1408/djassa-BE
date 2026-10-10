# Fidelia — Investor Brief

*Pre-seed · Abidjan, Côte d'Ivoire · October 2026* · [Version française](INVESTOR-BRIEF.fr.md)

> **Placeholders.** Everything marked `[PLACEHOLDER]` (company registration, ownership) is dummy data to be replaced before this brief is sent to anyone. Market figures carry their sources in [MARKET.md](MARKET.md) and must be re-checked before contractual use.
>
> Keep this file, its French translation ([INVESTOR-BRIEF.fr.md](INVESTOR-BRIEF.fr.md)) and the web pages (`backend-api/app/investor_brief/`, served behind the investor password at `<API>/brief/`) in step: a change to one is a change to all three.

## In one sentence

**Fidelia helps neighbourhood shops bring their customers back, and turns their everyday sales into proof a lender can trust.**

## The opportunity

- **2.72M merchant payment points** in Côte d'Ivoire in 2024, up from 1.13M a year earlier (BCEAO data). Merchants are going digital, fast.
- Accepting payments now costs almost nothing (Wave charges merchants ~1%). What is missing sits on top: recognising customers, bringing them back, proving activity.
- Banks and MFIs want to lend to small merchants but cannot assess them: the strict banking rate is **31.2%** (BCEAO; national indicators 2023). Public programmes (APIF, SGPME, GUDE-PME) are looking for private partners to close that gap.

## The product

| When | What the merchant gets |
|---|---|
| Day 1 | A cash book: cash and mobile-money sales in one daily total |
| Week 1 | Loyalty by phone number, and each week the number of customers who came back and of new customers brought by the Fidelia app |
| Month 3 and after | A sales history the merchant owns, shown to a licensed lender only with their consent |

Fidelia plugs into the wallet the merchant already uses (Wave first, then other operators and the interoperable **PI-SPI** QR, [details](MARKET.md#what-pi-spi-is)): no new payment rail, no extra fee. Two apps (merchant and customer) and the platform exist as working prototypes.

**Fidelia never holds funds and never lends.** Licensed institutions keep custody and credit.

## Traction

**Pre-pilot. No users, merchants or revenue yet.**

| Built (prototypes, `integration` branch) | Evidence expected from Phase 0 |
|---|---|
| Sign-in by phone number and SMS code | Interviews with 5–10 maquis and grocery owners in one commune |
| Offline sales, synced without duplicates, tested on a real phone | Signed letters of interest: merchants and one MFI ([templates](LETTERS-OF-INTEREST.md)) |
| Points and rewards; deal alerts; "Client venu" at the counter | Wave's answer on API access |
| Capture of the merchant's Wave payments, in test | A first merchant in real conditions |

## The market

| Level | Outlets | Value per year | How it is built |
|---|---:|---:|---|
| Total: merchants accepting QR in Côte d'Ivoire | ~1,000,000 | ~XOF 90bn | Wave CI QR merchants, ~1M reported in 2026 ([MARKET.md](MARKET.md)) × 7,500 F × 12 |
| Reachable: maquis and grocery outlets in Abidjan | ~120,000 | ~XOF 10.8bn (€16.5M) | × 40% in Abidjan × 30% food, drink and grocery *(assumptions)* |
| Three-year goal: paying Fidelia merchants | 1,800 | ~XOF 171M ARR | 1.5% of the reachable market |

*Top-down estimate: no reliable count of maquis and grocery shops in Abidjan exists. To verify in Phase 0.*

## Business model

| Stream | When |
|---|---|
| Merchant subscription: capped free plan, then ~5,000 F and ~10,000–15,000 F / month / outlet, paid in mobile money *(hypotheses to test)* | After the pilot (the pilot is free) |
| Sponsored deals: one-off, time-limited placement in the customer app; pricing to be tested | From year 2 |
| Multi-outlet and network contracts | After proof |
| Consented partner commissions (credit, savings): Fidelia earns distribution fees, never carries credit risk. **Not in the forecast** | After partnership |

**Why a merchant pays:** a small maquis earning +5% from returning customers gains about 73,000 F of gross profit a month against a 5,000–7,500 F subscription (illustrative; see [BUSINESS-MODEL.md](BUSINESS-MODEL.md)).

## Competition

| Today | What is missing | Fidelia |
|---|---|---|
| Paper notebook and loyalty cards | No totals, no customer recognised, no proof | A faster cash book, loyalty without cards |
| Wallet merchant apps (Wave, Orange Money, MTN MoMo) | One operator each, no cash, no loyalty tool found | Every wallet plus cash; partner, not competitor |
| WhatsApp Business and Facebook | No sales recorded, no measure of who came back | Offers by notification, measured at the counter |
| Point-of-sale apps with loyalty | Not connected to mobile money, no proof for a lender | Wallet capture, offline, consented proof |
| Payment aggregators (CinetPay) | ~3% + 50 F per payment, no loyalty | Never reroutes payments |

Main risk: an operator adds loyalty. Answer: be the only tool that covers every wallet and cash, and the proof MFIs accept.

## Three-year forecast

| XOF millions | Year 1 | Year 2 | Year 3 |
|---|---:|---:|---:|
| Paying merchants at year end | 100 | 600 | 1,800 |
| Revenue | 2.1 | 29.2 | 105.5 |
| Total costs (year 1 includes the 30.8 pilot) | 47.2 | 73.5 | 164.0 |
| **Net result** | **−45.1** | **−44.4** | **−58.6** |
| Cumulative funding need | 45.1 | 89.5 | 148.1 |

Fixed costs are covered from about **1,250 paying merchants**, reached in year 3. The total need, about **XOF 148M**, is funded in two rounds: this pilot round, then a seed round of about XOF 120M priced on the pilot's results.

*A forecast, not results. Assumptions: average subscription 7,500 F; sponsored deals +400 F per merchant from year 2; 40% of pilot merchants paying; acquisition cost 40,000 F per new merchant; variable cost 1,500 F a month per merchant; fixed costs XOF 2M a month after the pilot, then 4M (year 2) and 8M (year 3); no partner commissions.*

## Milestones this round funds

The round funds the six-month pilot, in two tranches. Each tranche pays for one phase; the second is released only when the first phase's exit gate is met.

| Tranche · phase | Evidence required |
|---|---|
| **Tranche 1 · Phase 0: discovery, compliance and production readiness** (months 1–2) | 5–10 interviews with maquis and grocery owners in one Abidjan commune; Wave API access confirmed; regulatory perimeter and ARTCI review; one payment partner; one or two MFIs asked whether they would pay for a consented tool to follow their merchant borrowers' sales |
| **Tranche 2 · Phase 1: free pilot, 5–10 merchants** (months 3–6) | **Exit:** ≥ 70% of real sales recorded at day 30, rising toward 85% at day 60; the app brings new customers, recorded at the counter; ≥ 40% of merchants accept the paid plan when the free pilot ends |
| **After this round** | A seed round priced on the pilot's results. Then the unit-economics gate before any second commune: acquisition cost below 12 months of gross profit, 3 months of retention, known support and messaging cost per outlet |

## Team

| | Role | Responsible for |
|---|---|---|
| **Stanislas Regisse** | CEO | Product, technology and security |
| **Bienvenue Kouadio** | Marketing | Partner and investor contact, finances, marketing strategy |
| Field lead | Hiring, funded by this round | Merchant onboarding and support |
| Advisors | Being recruited | Microfinance, mobile money, UEMOA law |

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

## How investors get their return

The pilot round converts into shares at the seed round, with a discount. Long-term value comes from a network of merchants and their consented histories, which interests operators, banks and MFIs, and regional fintechs (Moniepoint built its lending on the same kind of data, [MARKET.md](MARKET.md)). No exit is promised; these are the plausible paths.

## Risks

| Risk | Mitigation |
|---|---|
| Wave refuses API access | A cash sale with the customer's phone number works without Wave; stop-or-change rule if merchants also refuse ([CONCEPT.md § 12](CONCEPT.md#12-pilot-boundaries)) |
| Merchants stop recording | A cash book from day 1; the share of sales recorded is measured weekly and decides every next step |
| Regulation | Fidelia never holds funds or lends; licensed partners do; ARTCI and legal review in Phase 0 |
| Small team | Field lead hired during the pilot; advisors; spending tied to gates |

**Red lines:** no loan promise, no deposits held by Fidelia, no data shared without consent, no opaque score, no pan-African launch, no reusable biometric database ([CONCEPT.md § 11](CONCEPT.md#11-red-lines)).

## Contact

Bienvenue Kouadio (partner and investor contact) · contact.fidelia@regisse.com

*Information document. Not an offer of financial services or of securities. Figures from public sources are cited in [MARKET.md](MARKET.md); illustrative economics are labelled as such.*
