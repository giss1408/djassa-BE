# Fidelia — Investor Brief

*Pre-seed · Abidjan, Côte d'Ivoire · October 2026* · [Version française](INVESTOR-BRIEF.fr.md)

> **Placeholders.** Everything marked `[PLACEHOLDER]` (company registration, ownership, the round) is dummy data to be replaced before this brief is sent to anyone. Market figures carry their sources in [MARKET.md](MARKET.md) and must be re-checked before contractual use.
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
- **The pilot product:** a merchant app (offline-first, cheap Android) and the platform. Customers are recognised by phone number at the counter and receive their points by WhatsApp or SMS. The customer app exists as a prototype and returns once one area has enough merchants.

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
| Merchant subscription: capped free plan, then ~5,000 F and ~10,000–15,000 F / month / outlet *(hypotheses to test)* | Pilot |
| Sponsored deals and campaigns: one-off, time-limited placement for a merchant product, service or special offer in the customer app; pricing is to be tested | After the pilot, when the customer app returns |
| Multi-outlet and network contracts | After proof |
| Consented partner commissions (credit, savings, tontine): Fidelia earns distribution fees, never carries credit risk | After partnership |

**Why a merchant pays:** a small maquis earning +5% from returning customers gains about 73,000 F of gross profit a month against a 5,000 F subscription (illustrative; see [BUSINESS-MODEL.md](BUSINESS-MODEL.md)). Routing its payments through a ~3% aggregator would cost it more than that. This is why Fidelia never replaces the merchant's wallet.

## Positioning

Fidelia avoids consumer personal finance (Djamo) and B2B payments (Julaya, Hub2), and partners with payment rails (Wave, Orange, MTN, CinetPay). **Customer loyalty and merchant activity proof** have no dominant Ivorian player.

## Traction

**Pre-pilot. No users, merchants or revenue yet.** What exists is working prototypes (on the `integration` branch):

- A merchant app recording sales offline, tested on a real device, with no duplicates after a dropped connection.
- A customer app for discovery, deals, sandbox QR payment and points, frozen during the pilot.
- **Points on cash sales by phone**, with balance and rewards handed over at the counter.
- **One sale history** labelled by evidence, sold featured slots, a billing ledger, and an audited consented export.
- A public site built for low bandwidth (~120 KB on first visit, works offline).

## Milestones this round funds

| Gate | Evidence required |
|---|---|
| **Phase 0: discovery and compliance** | 5–10 interviews with maquis and grocery owners in one Abidjan commune; Wave API access confirmed; regulatory perimeter and ARTCI review; one payment partner; one or two MFIs asked whether they would pay for a consented tool to follow their merchant borrowers' sales |
| **Phase 1: pilot, 5–10 merchants** | Phone login (OTP), automatic Wave capture, one live payment partner. **Exit:** merchants record most real sales for 60+ days and pay or renew |
| **Unit-economics gate** | Acquisition cost below 12 months of gross profit; 3 months of retention; known support and messaging cost per outlet |

No geographic expansion before one corridor passes the gate.

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
| Round | `[PLACEHOLDER]` Pre-seed |
| Amount | `[PLACEHOLDER]` USD 000,000 |
| Instrument | `[PLACEHOLDER]` SAFE / convertible note, cap to be agreed |
| Use of funds (12–18 months) | `[PLACEHOLDER]` Pilot operations and field team ~35% · product (OTP login, wallet capture, second operator) ~35% · legal, regulatory and security review ~15% · marketing and partnerships ~15% |
| Runway to | Phase 1 exit gate: a pilot corridor showing retention and paid renewal |

## Red lines

No loan promise. No deposits held by Fidelia. No data shared without consent. No opaque score. No pan-African launch. No reusable biometric database. These shape what we build and what we refuse to sell ([CONCEPT.md § 11](CONCEPT.md#11-red-lines)).

## Contact

Bienvenue Kouadio (partner and investor contact) · contact.fidelia@regisse.com

*Information document. Not an offer of financial services or of securities. Figures from public sources are cited in [MARKET.md](MARKET.md); illustrative economics are labelled as such.*
