# Fidelia — Partners and Outreach

Who to contact, why, when, and what to bring. It merges the outreach plan and the institution directory. **Verify current names, mandates and contacts on official websites before any formal contact.** No direct contact details are kept here, because they go stale.

Phase references point to [ROADMAP.md](ROADMAP.md). The one-sentence pitch per audience is in [CONCEPT.md § 9](CONCEPT.md#9-explaining-fidelia-to-each-audience).

## Recommended contact order

1. **Merchants first.** Interview 5 to 10 merchants in the pilot corridor before approaching large institutions.
2. **APIF-CI and APSFD-CI.** Validate strategic alignment and get one entry point to many MFIs.
3. **CIFA.** Join the fintech ecosystem and follow regulatory change.
4. **Mobile-money operators, Wave first** (Business and developer teams). With Wave, confirm webhook access for small merchants and the loyalty use of payer phone numbers: this decides the zero-habit capture route. With MTN and Orange, confirm whether payments to a merchant's static QR can be notified, and their merchant rates. Then **CinetPay** (or another licensed aggregator) as the fallback payment route.
5. **Fin'ELLE plus one or two generalist MFIs** (UNACOOPEC-CI, Advans). Prepare the Phase 3–5 partnerships.
6. **BCEAO or qualified regulatory counsel.** Before any feature that moves money beyond merchant payments, holds funds, produces a score for third parties, or involves credit, to confirm whether Fidelia acts as technology provider, agent, payment facilitator or another regulated role.

## Institution directory

### 1. Regulators and public institutions

*They set the frame Fidelia operates in, or share its mission.*

| Institution | Role | Why contact | When |
|---|---|---|---|
| **BCEAO** | Licences EME/EP, credit-scoring workstream, PI-SPI (instant-payment interoperability platform, [what it is](MARKET.md#what-pi-spi-is)) | Unavoidable for any e-money or scoring feature; ask about the regulatory sandbox and about reaching the PI-SPI interoperable merchant QR through a licensed participant | Before any financial launch; PI-SPI from Phase 0 |
| **ARTCI** | Personal-data protection authority | Consent, retention, data transfer, identity data | Phase 0 |
| **APIF-CI** | Runs the National Financial Inclusion Strategy and financial education | Near-identical mission, including gender and rural inclusion; natural institutional partner | Now |
| **SGPME** | Partial guarantee on bank and MFI credit to SMEs | Lowers the risk an MFI partner takes on merchants without bank history | Phase 5 |
| **GUDE-PME** | SME one-stop shop for finance | Understand the support ecosystem; relay to Fidelia merchants | Monitor now |
| **Ministry of Digital Transition** | National digital strategy, public-service interoperability | Relevant if Fidelia extends to public services | Opportunistic |

### 2. Microfinance (MFIs)

*The licensed partners that actually hold savings and grant credit. Fidelia is the intermediary; they are the regulated custodians.*

| Institution | Profile | Why contact | When |
|---|---|---|---|
| **APSFD-CI** | Federation of the ~45 licensed MFIs | One approach reaches the whole sector | Pilot |
| **Fin'ELLE** | MFI dedicated to women entrepreneurs | Gender priority; natural partner for women-led tontines | **Priority**, Phase 3 |
| **UNACOOPEC-CI** | Largest savings and credit cooperative network | Strong coverage outside Abidjan | Phases 2–5 |
| **Advans Côte d'Ivoire** | Micro and small business MFI | Experience with alternative scoring | Phases 4–5 |
| **Baobab Côte d'Ivoire** | Urban and peri-urban MFI | Already digitising its own operations | Phases 4–5 |
| **PAMF-CI** | Strong rural presence | When Fidelia leaves Abidjan | Phase 6 |
| **Cofina Côte d'Ivoire** | Mesofinance, cocoa cooperatives | Agriculture horizon | Phase 6 |

### 3. Payments and fintech infrastructure

*They supply the rails or work in adjacent segments. They are not direct competitors.*

| Institution | Role | Why contact | When |
|---|---|---|---|
| **CinetPay** | Multi-operator aggregator most used by Ivorian SMEs | One API for Wave, Orange Money, MTN MoMo, Moov | MVP |
| **Hub2** | Payment infrastructure for fintechs | Alternative or complement; UEMOA cross-border later | Phase 2+ |
| **Julaya** | B2B payments to mobile money | Merchant treasury and supplier payments | Phase 5 |
| **CIFA** | Fintech association: regulators, fintechs, investors | Visibility and regulatory awareness | Now |

### 4. Mobile-money operators

| Operator | Why it matters | When |
|---|---|---|
| **Wave CI** | ~1% merchant fee, ~1M QR merchants, Business API with `merchant.payment_received` webhooks. Fidelia's loyalty layer sits on top of its QR; pitch: repeat customers mean more Wave volume | **Phase 0, first technical partner** |
| **Orange Money CI** (OM Business) | Historic leader, densest agent network. Direct merchant API (checkout with confirmation callback), ~1–2%, 1–3 weeks to activate | Phase 0 check, Phase 2 adapter |
| **MTN MoMo CI** | Second operator. MoMo API "request to pay": the customer approves on their own phone, which suits a counter; callbacks are not retried, so status must also be polled | Phase 0 check, Phase 2 adapter |
| **Moov Africa CI** | Price-sensitive and peri-urban segments | Phase 2+ |

### 5. Funders and guarantee programmes

*They mostly fund the MFIs and guarantee schemes Fidelia partners with. Useful for structuring an MFI partnership or indirect co-funding.*

| Institution | Why | When |
|---|---|---|
| **British International Investment (BII)** | Funded an SME credit line via NSIA with a women-entrepreneur share | Phase 5 |
| **Bridge Microfinance guarantee programme** | SMEs, transport, women-led businesses | Phase 5 |
| **GIZ Côte d'Ivoire** (ProFinA) | Agricultural finance | Phase 6 |
| **African Development Bank** | APIF partner on rural inclusion | Rural expansion |
| **World Bank** (CI office) | Finances inclusion studies and programmes | Opportunistic |

## Funders for Fidelia

*Section 5 lists funders of our partners. This section lists institutions that could fund **Fidelia itself**: the six-month pilot envelope of XOF 30.82M ([FINANCE-BUDGET.md](FINANCE-BUDGET.md)) and the later pre-seed round ([INVESTOR-BRIEF.md](INVESTOR-BRIEF.md)).*

> **Status checked by web search on 10 October 2026.** Calls open and close and programmes change. Check each one on its official website before applying. Most require a registered company, so register the company and fill the investor-brief placeholders first ([FINANCE-VALIDATION.md § 5](FINANCE-VALIDATION.md)). For every application, decide whether you are asking for a grant, equity or a loan.

### Grants and public programmes

| Institution | What it offers | Why it fits Fidelia | Status / when |
|---|---|---|---|
| **APIF-CI: fintech sector support project** (with PACACI) | Support for fintech development and competitiveness; launched 6 October 2026 in Abidjan | Same mission as Fidelia. APIF-CI is already our priority institutional contact | **Now.** No call for applications published yet; ask APIF-CI directly |
| **African Development Bank: Africa Digital Financial Inclusion Facility (ADFI)** | Grants up to USD 1M per country; up to USD 1.5M blended grant and loan (Lot 1) | Pillar 1 covers digital registries and alternative credit scoring, which is Fidelia's proof layer. Women, youth and small businesses are the targets | Call published June 2026; deadline not confirmed. Probably needs an MFI or institutional co-applicant |
| **develoPPP Ventures** (German development cooperation) | Matched growth funding for startups; Côte d'Ivoire is eligible | Funds a pilot-stage startup, if Fidelia can provide matching funds | Calls about twice a year, near the end of Q2 and Q4; check for a Q4 2026 window |
| **Label Startup Numérique** (Loi n° 2023-901) | Three years of tax exemptions (finance law 2026, art. 35); access to public contracts and funding | Not cash, but required for state startup programmes | Apply through the startup portal once the company is registered |
| **Ivoire Tech Next 15** (Ministry of Digital Transition) | 24-month accelerator for 15 digital startups: financier network, state-funded AI agents, UEMOA expansion | Later target | 2026 call closed 13 September. Requires a startup active for 1+ year, 20%+ growth, 5+ employees and at least XOF 65.6M raised, so it fits after the pre-seed round |
| **Interledger Local Impact Mini-Grant** | USD 500–3,000 | Small top-up for merchant field sessions | Closing date not confirmed |

### Pre-seed investors

*Approach them once the pilot shows that merchants record most of their sales and keep using Fidelia ([ROADMAP.md](ROADMAP.md) Phase 1 exit). Present the funds-flow diagram early: deal flow in UEMOA is thin in 2026, and BCEAO licensing uncertainty makes investors cautious. "Fidelia never holds funds" answers that concern.*

| Investor | Profile | Why contact |
|---|---|---|
| **Saviu Ventures** | Among the most active early-stage investors in Francophone Africa | Stage and region fit |
| **Launch Africa Ventures** | Pan-African seed fund with a fintech-heavy portfolio; active in 2026 | Fintech focus; sees regional interoperability (PI-SPI) as a driver |
| **Breega** | Paris-based VC; tickets USD 100k–2M; Côte d'Ivoire among its markets | Pre-seed ticket size |
| **Daba Finance** (angel network) | Tickets USD 5k–200k | Ticket size matches the pilot envelope |
| **Janngo Capital**, **Comoé Capital** (I&P), **Digital Africa**, **Orange Ventures** | Francophone Africa early-stage funds | 2026 activity not confirmed; verify before contact |

### Accelerators with funding or investor access

| Programme | What it offers | Status / when |
|---|---|---|
| **Visa Africa Accelerator** | Fintech accelerator for startups with an MVP, from seed to Series A | 2026 cohort closed 17 May; target the 2027 cohort |
| **Orange Corners Côte d'Ivoire** and **Orange Corners Innovation Fund** (Netherlands embassy) | Incubation and access to an innovation fund | No 2026 Côte d'Ivoire call found; monitor |
| **Hub1040**, **Seedspace Abidjan** | Coworking, support programmes and investor introductions for digital and fintech startups | Ongoing |
| **Village Capital**, **Founders Factory Africa**, **GrowthAfrica** | Investment-readiness programmes; listed as active in Abidjan | Check current cohorts |

### Later phases: funders who work through MFIs

These funders rarely give money to a startup directly. Approach them with a licensed MFI partner when tontine, savings or credit features are ready (Phases 3–5).

| Institution | Note |
|---|---|
| **Mastercard Foundation** | No unsolicited proposals; watch its Expressions of Interest and RFPs |
| **FSD Africa** | Tenders through its supplier portal (since 13 July 2026) |
| **UNCDF** | 2026–2029 strategy focuses on MSME finance; calls are country-specific |
| **Gates Foundation** (Inclusive Financial Systems) | Priority on inclusive instant payments in Africa; direct work in this area ends in 2030 |
| **SGPME**, **BII**, **AfDB** | See sections 1 and 5 |

**Application angle for all of them:** financial inclusion for informal merchants, consented data (never sold), funds always held by licensed institutions, and gender as a design constraint (usage tracked by gender, partnership with Fin'ELLE). Never present a loan or approval as an outcome for the merchant ([Outreach guardrails](#outreach-guardrails)).

## Acquisition channels

Trusted channels cost less than consumer advertising. Test in this order:

1. Merchant associations and cooperatives (maquis and grocery owners for the pilot).
2. Payment aggregators and mobile-money merchant networks.
3. Distributors serving grocery shops and maquis (drinks, food staples).
4. MFIs already serving the target merchants.
5. Telecom or messaging partnerships once the workflow is proven.

Per channel, measure merchants activated, merchants active after 30/90 days, support cost, and revenue per acquired outlet. A partnership is valuable only if it lowers acquisition or support cost while preserving user trust.

## Meeting kit

Bring to every meeting:

- The problem in one paragraph, and the audience pitch ([CONCEPT.md § 9](CONCEPT.md#9-explaining-fidelia-to-each-audience)).
- Target users and geography: maquis and grocery shops in one Abidjan commune, pilot volume ([CONCEPT.md § 12](CONCEPT.md#12-pilot-boundaries)).
- What is **actually** built ([ROADMAP.md § Where we stand](ROADMAP.md#where-we-stand)) and a working demo of both apps.
- A simple data-flow and funds-flow diagram showing money going from wallet to merchant wallet, never through Fidelia.
- The proposed role of the partner, the revenue model and fee transparency.
- Privacy, consent, security and incident controls.
- Pilot duration, success metrics, exit criteria.
- The specific decision or introduction you are asking for.
- The [investor brief](INVESTOR-BRIEF.md) (fill its placeholders first); the public site for context.
- A letter of interest to sign at the end of the meeting, for merchants and MFIs ([templates](LETTERS-OF-INTEREST.md); the French version is the one to sign).

## Questions to ask

**Regulatory:** Which activities need a licence or a licensed institution? Can the pilot run in a sandbox or controlled test framework? What consent, retention, audit and data-transfer requirements apply?

**Technical:** Is there a sandbox? How are signatures, retries, idempotency, reconciliation and settlement handled? What uptime, support and incident commitments exist? Which identifiers are stable across retries and channels? Is the partner PI-SPI-connected?

**Commercial:** Who pays which fee, and when? Minimum volume or contract term? What happens when a customer withdraws consent? Which outcomes define a successful pilot?

## Contact record template

```text
Institution:
Category:
Official website:
Person and role:
Date contacted:
Purpose:
Documents shared:
Response:
Next action and owner:
Regulatory or commercial assumptions to verify:
```

## Outreach guardrails

- Never claim Fidelia provides loans, or promise approval, better rates or savings returns.
- Present Fidelia as an accelerator of existing credit routes, never as a condition for credit.
- Never send real customer data in a first meeting. Use synthetic or anonymised data until a written data-sharing agreement exists.
- Verify every public statistic and contact before publishing.
- Never describe a continent-wide rollout. Present a specific country, corridor, segment and pilot volume.
- The federated identity direction is always labelled a hypothesis.

## Related documents

[CONCEPT.md](CONCEPT.md) · [MARKET.md](MARKET.md) · [BUSINESS-MODEL.md](BUSINESS-MODEL.md) · [ROADMAP.md](ROADMAP.md)
