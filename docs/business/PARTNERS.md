# Djassa — Partners and Outreach

Who to contact, why, when, and what to bring. It merges the outreach plan and the institution directory. **Verify current names, mandates and contacts on official websites before any formal contact.** No direct contact details are kept here, because they go stale.

Phase references point to [ROADMAP.md](ROADMAP.md). The one-sentence pitch per audience is in [CONCEPT.md § 9](CONCEPT.md#9-explaining-djassa-to-each-audience).

## Recommended contact order

1. **Merchants first.** Interview 5 to 10 merchants in the pilot corridor before approaching large institutions.
2. **APIF-CI and APSFD-CI.** Validate strategic alignment and get one entry point to many MFIs.
3. **CIFA.** Join the fintech ecosystem and follow regulatory change.
4. **Wave Côte d'Ivoire** (Business and developer team). Confirm webhook access for small merchants and the loyalty use of payer phone numbers. This decides the zero-habit capture route. Then **CinetPay** (or another licensed aggregator) as the fallback payment route.
5. **Fin'ELLE plus one or two generalist MFIs** (UNACOOPEC-CI, Advans). Prepare the Phase 3–5 partnerships.
6. **BCEAO or qualified regulatory counsel.** Before any feature that moves money beyond merchant payments, holds funds, produces a score for third parties, or involves credit, to confirm whether Djassa acts as technology provider, agent, payment facilitator or another regulated role.

## Institution directory

### 1. Regulators and public institutions

*They set the frame Djassa operates in, or share its mission.*

| Institution | Role | Why contact | When |
|---|---|---|---|
| **BCEAO** | Licences EME/EP, credit-scoring workstream, PISPI interoperability | Unavoidable for any e-money or scoring feature; ask about the regulatory sandbox | Before any financial launch |
| **ARTCI** | Personal-data protection authority | Consent, retention, data transfer, identity data | Phase 0 |
| **APIF-CI** | Runs the National Financial Inclusion Strategy and financial education | Near-identical mission, including gender and rural inclusion; natural institutional partner | Now |
| **SGPME** | Partial guarantee on bank and MFI credit to SMEs | Lowers the risk an MFI partner takes on merchants without bank history | Phase 5 |
| **GUDE-PME** | SME one-stop shop for finance | Understand the support ecosystem; relay to Djassa merchants | Monitor now |
| **Ministry of Digital Transition** | National digital strategy, public-service interoperability | Relevant if Djassa extends to public services | Opportunistic |

### 2. Microfinance (MFIs)

*The licensed partners that actually hold savings and grant credit. Djassa is the intermediary; they are the regulated custodians.*

| Institution | Profile | Why contact | When |
|---|---|---|---|
| **APSFD-CI** | Federation of the ~45 licensed MFIs | One approach reaches the whole sector | Pilot |
| **Fin'ELLE** | MFI dedicated to women entrepreneurs | Gender priority; natural partner for women-led tontines | **Priority**, Phase 3 |
| **UNACOOPEC-CI** | Largest savings and credit cooperative network | Strong coverage outside Abidjan | Phases 2–5 |
| **Advans Côte d'Ivoire** | Micro and small business MFI | Experience with alternative scoring | Phases 4–5 |
| **Baobab Côte d'Ivoire** | Urban and peri-urban MFI | Already digitising its own operations | Phases 4–5 |
| **PAMF-CI** | Strong rural presence | When Djassa leaves Abidjan | Phase 6 |
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
| **Wave CI** | ~1% merchant fee, ~1M QR merchants, Business API with `merchant.payment_received` webhooks. Djassa's loyalty layer sits on top of its QR; pitch: repeat customers mean more Wave volume | **Phase 0, first technical partner** |
| **Orange Money CI** (OM Business) | Historic leader, densest agent network; its merchant offer is our positioning reference | MVP |
| **MTN MoMo CI** | Second operator; needed for full coverage, via the aggregator | Phase 2 |
| **Moov Africa CI** | Price-sensitive and peri-urban segments | Phase 2+ |

### 5. Funders and guarantee programmes

*They mostly fund the MFIs and guarantee schemes Djassa partners with. Useful for structuring an MFI partnership or indirect co-funding.*

| Institution | Why | When |
|---|---|---|
| **British International Investment (BII)** | Funded an SME credit line via NSIA with a women-entrepreneur share | Phase 5 |
| **Bridge Microfinance guarantee programme** | SMEs, transport, women-led businesses | Phase 5 |
| **GIZ Côte d'Ivoire** (ProFinA) | Agricultural finance | Phase 6 |
| **African Development Bank** | APIF partner on rural inclusion | Rural expansion |
| **World Bank** (CI office) | Finances inclusion studies and programmes | Opportunistic |

## Acquisition channels

Trusted channels cost less than consumer advertising. Test in this order:

1. Merchant associations and cooperatives (including pharmacy groups).
2. Payment aggregators and mobile-money merchant networks.
3. Distributors serving pharmacies, groceries, salons and restaurants.
4. MFIs already serving the target merchants.
5. Telecom or messaging partnerships once the workflow is proven.

Per channel, measure merchants activated, merchants active after 30/90 days, support cost, and revenue per acquired outlet. A partnership is valuable only if it lowers acquisition or support cost while preserving user trust.

## Meeting kit

Bring to every meeting:

- The problem in one paragraph, and the audience pitch ([CONCEPT.md § 9](CONCEPT.md#9-explaining-djassa-to-each-audience)).
- Target users and geography: one Abidjan corridor, one segment, pilot volume.
- What is **actually** built ([ROADMAP.md § Where we stand](ROADMAP.md#where-we-stand)) and a working demo of both apps.
- A simple data-flow and funds-flow diagram showing money going from wallet to merchant wallet, never through Djassa.
- The proposed role of the partner, the revenue model and fee transparency.
- Privacy, consent, security and incident controls.
- Pilot duration, success metrics, exit criteria.
- The specific decision or introduction you are asking for.
- A two-page concept note; the public site for context.

## Questions to ask

**Regulatory:** Which activities need a licence or a licensed institution? Can the pilot run in a sandbox or controlled test framework? What consent, retention, audit and data-transfer requirements apply?

**Technical:** Is there a sandbox? How are signatures, retries, idempotency, reconciliation and settlement handled? What uptime, support and incident commitments exist? Which identifiers are stable across retries and channels? Is the partner PISPI-connected?

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

- Never claim Djassa provides loans, or promise approval, better rates or savings returns.
- Present Djassa as an accelerator of existing credit routes, never as a condition for credit.
- Never send real customer data in a first meeting. Use synthetic or anonymised data until a written data-sharing agreement exists.
- Verify every public statistic and contact before publishing.
- Never describe a continent-wide rollout. Present a specific country, corridor, segment and pilot volume.
- The federated identity direction is always labelled a hypothesis.

## Related documents

[CONCEPT.md](CONCEPT.md) · [MARKET.md](MARKET.md) · [BUSINESS-MODEL.md](BUSINESS-MODEL.md) · [ROADMAP.md](ROADMAP.md)
