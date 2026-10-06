# Hossouko — Market, Regulation and Positioning

The evidence behind [CONCEPT.md](CONCEPT.md). Data compiled September 2026. **Every figure is published with its source. Re-verify figures before contractual or investor use**, because inclusion figures diverge by methodology (see the note at the end).

## 1. The central paradox

Côte d'Ivoire has massive mobile-money access (75–89% depending on source) but low access to credit and formal banking (25–31%). The opportunity lies in that gap between *having a digital wallet* and *being able to save, borrow, insure or prove business activity formally*, not in payment access.

The World Bank's Global Findex now separates **access** (owning an account) from **depth of use** (real digital payments, borrowing, saving). West Africa scores high on access and low on depth.

## 2. Key figures: Côte d'Ivoire

| Indicator | Value | Source / period |
|---|---|---|
| Financial inclusion rate | 58% (World Bank) / up to 84% (local fintech sector) | Global Findex 2025 / Next Fintech Forum 2024 |
| Strict banking rate | 31.2% | National indicators, 2023 |
| Extended banking rate (banks + microfinance) | 43.6% | National indicators, 2023 |
| Active mobile-money accounts | 25M+ for ~28–31M inhabitants | BCEAO, 2024–2026 |
| Mobile-money penetration | ~89%, among the highest worldwide | GSMA |
| Microfinance clients | 2.9M, +14.3% in one quarter | APSFD-CI, Q1 2026 |
| Microfinance credit outstanding (UEMOA) | ~XOF 3,210bn, +12% | BCEAO, end 2025 |
| Bank credit outstanding (UEMOA) | ~XOF 39,000bn, +5.3% | BCEAO, end 2025 |
| SME contribution | ~20% of GDP, ~23% of employment | Ivorian government |
| SMEs under public guarantee | 3,860 SMEs, XOF 114.7bn guaranteed, 24.5% to women | SGPME, 30 April 2026 |

Microfinance is growing fast but concentrated in Abidjan and poorly adapted to small merchants and agriculture.

## 3. Key figures: sub-Saharan Africa

- **40% of adults** held a mobile-money account in 2024, the highest of any region; ~51% had made a digital payment (Global Findex 2025).
- The account-ownership **gender gap** is ~12 points regionally (Togo 25, Nigeria 22). In low- and middle-income countries, women were 36% less likely than men to own a mobile-money account in 2024, versus 30% in 2021. The gap has *widened* (GSMA, Findex 2025).
- About half of mobile-money users have no PIN or do not know how to change it. This is a security and digital-literacy issue.
- About 70% of West African adults have no bank account while more than 80% own a mobile phone (BCEAO).

## 4. Regulatory framework

### Regional: UEMOA / BCEAO

- Any fintech operating in UEMOA needs a BCEAO status: **electronic money institution (EME)**, **payment institution (EP)**, or technical partner of a licensed institution. Hossouko operates as a **technology and distribution partner** of licensed institutions and holds no licence itself.
- 2023 regulation encourages fintechs to target unbanked populations and eases multi-country expansion under common rules. About 200 fintechs were registered by BCEAO at the time.
- **PI-SPI**, the BCEAO's instant-payment interoperability platform, connects every bank, mobile-money operator and MFI in the zone. Connection has been mandatory since 30 June 2026 (see [What PI-SPI is](#what-pi-spi-is) below).
- BCEAO has an open workstream on **credit scoring** and has discussed a **regulatory sandbox**. Any third-party scoring must go through that route rather than launch in a grey zone.

### What PI-SPI is

**PI-SPI** stands for *Plateforme d'Interopérabilité du Système de Paiement Instantané*: the instant-payment interoperability platform run by the **BCEAO**, the central bank shared by the eight UEMOA countries (Côte d'Ivoire, Senegal, Mali, Burkina Faso, Niger, Togo, Benin, Guinea-Bissau).

**What it does**

- **Connects everyone.** Banks, mobile-money operators (Wave, Orange Money, MTN, Moov…) and microfinance institutions are linked, so money moves instantly between any two of them, even across operators or countries in the zone.
- **Instant, 24/7.** Payments settle in real time, around the clock.
- **Interoperable merchant QR.** A merchant can display **one QR code** and accept payment from any wallet or bank account, whatever app the customer uses. Today a merchant usually needs one QR per operator.

**Timeline**

| Date | Milestone |
|---|---|
| 30 September 2025 | Officially launched by the BCEAO in Dakar |
| March 2026 | Progressive onboarding continues, e.g. four more institutions authorised in Togo |
| 30 June 2026 | Deadline for every financial institution in UEMOA to connect |
| To confirm | How far merchant QR adoption has actually spread in Côte d'Ivoire (a Phase 0 check) |

**Why it matters for Hossouko**

- **It ends the "which operator?" question.** It is step 3 of the operator-neutral order ([CONCEPT.md § 3](CONCEPT.md#3-the-idea-one-habit-five-uses)): Wave first, then MTN or Orange, then PI-SPI. With one interoperable QR, Hossouko would no longer need a separate integration per operator.
- **Hossouko cannot connect directly.** Only licensed financial institutions can. Hossouko would reach it through a licensed partner (a bank or payment institution), consistent with its role as a technology partner.
- **It is a partner requirement.** Any payment partner Hossouko signs must be PI-SPI-connected.
- **Roadmap:** Phase 0 checks its status in Côte d'Ivoire and identifies a licensed participant; Phase 2 adds it through that partner ([ROADMAP.md](ROADMAP.md)).

Sources: [AllAfrica, PI-SPI launch](https://fr.allafrica.com/stories/202602120405.html) · [Ecofin, 30 June deadline](https://www.ecofinagency.com/news-finances/0404-54418-bceao-imposes-june-30-deadline-to-complete-instant-payments-integration) · [CDPI, interoperable QR](https://docs.cdpi.dev/fr/notes-techniques/payments/code-qr-interoperable) · [AllAfrica, Togo onboarding](https://fr.allafrica.com/stories/202603060731.html)

### National: Côte d'Ivoire

- **APIF-CI** runs the National Financial Inclusion Strategy and financial-education programmes. It is studying a technology innovation office with private partners.
- **GUDE-PME** (SME one-stop shop, since Dec. 2022) has supported 20,000+ SMEs, ~1,100 of them in seeking finance.
- **SGPME** provides partial portfolio guarantees on bank credit to SMEs (figures above).
- May 2026: a USD 10.7M credit-guarantee programme with Bridge Microfinance targeting SMEs, agriculture, transport and women-led businesses.
- June 2026: a EUR 30M (XOF 19.68bn) loan from British International Investment to NSIA Banque for SME credit, at least 30% reserved for women-led businesses (2X Challenge criteria).
- **ARTCI** is the personal-data protection authority. Consent, retention and data-transfer rules must be confirmed with it before identity or data-export features.
- National digital strategy: five 2026 priorities (connectivity, digital payments, skills, cybersecurity, innovation), a ministry budget up 37%, and a "zero paper" government target for 2030.

**Strategic reading:** public programmes and funders (APIF, GUDE-PME, SGPME, BII, GIZ, EIB) are looking for private execution partners for data, distribution and technology rather than running everything in-house. That is a real window, provided we work with the guarantee and co-financing mechanisms rather than around them.

## 5. Competitive landscape and our position

| Segment | Established players | Hossouko's stance | Why |
|---|---|---|---|
| Consumer personal finance | **Djamo**: USD 17M raised (Apr. 2025, Janngo, Partech, Oikocredit, YC), USD 4.5bn processed | **Avoid** | Established regional leader; no edge for a generalist entrant |
| B2B payments and SME treasury | **Julaya** (debt-financed, USD 1.4M from CDC-CI Capital), **Hub2** (55 infrastructure clients incl. Djamo, Julaya, CinetPay) | **Avoid** | Already funded and structured |
| Payment aggregation | **CinetPay**, Hub2 | **Partner** | We integrate these rails; we do not rebuild them |
| Mesofinance | **Cofina** (EUR 25M EIB partnership for cocoa cooperatives) | **Partner** (agriculture horizon) | Lender, not competitor |
| Merchant activity proof, merchant loyalty, digital tontine | **No dominant Ivorian player** | **Our place** | Locally vacant, aligned with BCEAO's alternative-scoring workstream |

Operator merchant offers (e.g. Orange Money Business) are payment tools for one operator. Hossouko is operator-neutral and builds history and loyalty on top of all of them.

## 6. Digital tontines: a validated model, locally vacant

The tontine (rotating community savings) remains the most-used and most-trusted financial mechanism among the unbanked. Digitisation brings automated contributions via mobile money, traceability that can serve as **proof of solvency**, and a path to micro-insurance or locked savings.

Regional precedents: **E-Tontine** (Senegal, since 2015, goods purchase; economically validated but modest revenue), **Djangui** (Cameroon, since 2016, remote participation), **MaTontine, Sooretul, Kobiri** (Senegal, connected to credit and micro-insurance). No Ivorian player dominates, despite local mobile-money maturity.

## 7. SME and agricultural finance: the persistent friction

- SMEs face collateral requirements most cannot meet. Public programmes (SGPME, GUDE-PME, GIZ ProFinA) explicitly look for alternatives.
- Alternative data (sales history, mobile-money payments) is identified as a possible **partial substitute for physical collateral**. That is Hossouko's core thesis.
- Transaction-data-based cash advances are proven elsewhere in Africa (e.g. Kopo Kopo, Kenya) but not yet captured in Côte d'Ivoire.
- Agricultural finance is the most documented weak point despite ~6% growth (2024). It is a later horizon for Hossouko (see [ROADMAP.md](ROADMAP.md)).

## 8. Opportunity map

| Opportunity | Maturity / competition | Institutional alignment | Hossouko |
|---|---|---|---|
| Merchant activity proof and loyalty | Low | Strong | **Core (now)** |
| Digital tontines | Low in Côte d'Ivoire | Strong | Phase 3 |
| Scoring from mobile-money and tontine data | Very low; BCEAO workstream open | Strong | Phase 4, sandbox route |
| Agricultural finance via alternative data | Low; donor-led | Strong | Horizon |
| B2B payments / SME treasury | Medium–high | Medium | Avoid |
| Consumer personal finance | High (Djamo) | Weak for a new entrant | Avoid |
| Embedded financial education | Low as a standalone product | Strong | Built into every phase |

## 9. Evidence for the Hossouko model

External research gathered on 30 September 2026 to test the two things that matter most: **earning money** and **building customer loyalty**.

### Merchant payments in Côte d'Ivoire: the rails already exist

| Fact | Figure | Source |
|---|---|---|
| Registered merchant payment points, Côte d'Ivoire | **2.72M** in 2024 (1.13M in 2023) | BCEAO data via Launch Base Africa, Mar. 2026 |
| Merchant payments as a share of mobile-money volume | **23.3%** in 2024 (3.3% in 2020) | Same |
| Wave's share of UEMOA mobile-money value / volume | 38.2% / 23% (2024), rising; Orange 41.3% / 38.4%, falling | Same |
| Wave CI QR merchants | ~300,000 in 2024 (from 600 in 2022); ~1M reported in 2026 | OSIRIS; Kolonell 2026 |
| Merchant fee: Wave | **~1%**, next-day payout | Kolonell, Boldrails 2026 |
| Merchant fee: telecom operators (Orange, MTN, Moov) | 1.5–2.5% | Kolonell 2026 |
| Merchant fee: CinetPay aggregator | **~3% + 50 F** (mobile money), J+2 payout | Kolonell 2026 |
| Mobile money's share of takings, digitised Abidjan businesses | 55–65% | Kolonell 2026 |
| Average basket | Maquis ~4,000 F · pharmacy ~8,000 F · shop ~15,000 F | Kolonell 2026 |
| Private pharmacies (officines), Côte d'Ivoire | **1,217** (Aug. 2025); 80–90% of medicine supply | economie-ivoirienne.ci |
| Wave Business API | Checkout, QR and signed webhooks in CI, including `merchant.payment_received` with amount, fee, **sender phone number** and time | docs.wave.com |

**Implications:** payment acceptance is a commodity, and the cheapest rail (Wave) is winning. Hossouko must **not** try to become the merchant's payment rail: routing a maquis's takings through an aggregator would add about 2 points of cost, which is more than any loyalty uplift can repay. Hossouko's value is what sits **on top of** the rails: recognising customers, bringing them back, and turning payments into proof. Wave's webhook makes this possible with no new habit for the merchant, subject to confirming access and consent in Phase 0. No source found shows Wave offering loyalty or customer-retention tools to its merchants.

### Other rails: Hossouko is operator-neutral

| Rail | What it offers Hossouko | Merchant cost | Source |
|---|---|---|---|
| **Orange Money CI**, direct merchant API | Checkout started by the merchant's system: OAuth token, transaction, redirect, server-to-server callback (verified with a notification token, not HMAC). OM Pay launched for simpler mobile payments | ~1–2%; 1–3 weeks to activate | Kolonell 2026; FinDev Gateway |
| **MTN MoMo**, Collections API (Côte d'Ivoire supported) | "Request to pay": the customer approves on their own phone. Asynchronous callback over HTTPS, **no retry**, so status must also be polled | Negotiated | MTN MoMo developer docs |
| **PI-SPI** (BCEAO) | Instant-payment interoperability platform, live since 30 Sept. 2025; all UEMOA financial institutions had to connect by 30 June 2026. Its **interoperable QR** lets one merchant QR accept any wallet or bank account | To be confirmed | AllAfrica 2026; Ecofin; CDPI |

**Implication:** Wave is the first rail, not the only one. Each operator is an adapter behind the same event stream, and the interoperable PI-SPI QR, reached through a licensed participant, is the long-term operator-neutral rail.

### What worked elsewhere

| Comparable | What happened | Lesson for Hossouko |
|---|---|---|
| **Moniepoint** (Nigeria) | Payments to 6M+ businesses, then credit underwritten from payment data: over ₦1 trillion (~USD 721M) lent to small businesses by 2025, a **36% rise in transaction value after loans**, ~30% repeat loans, low NPLs. | Payments are the hook and credit is the engine. Payment data is what makes merchant credit safe. Hossouko reaches the same data through partners rather than by becoming an acquirer. |
| **Kopo Kopo Grow** (Kenya) | Merchant cash advance repaid as a % of daily digital takings: USD 2M+ lent to 500–600 merchants; **42% higher transaction growth** afterwards. Merchants doubled digital transactions before applying, re-borrowed after a median of 3 days, and took the maximum offered. | The partner-credit model works, but it needs responsible-lending safeguards: help merchants choose the amount, show cost against expected return, and avoid perpetual borrowing. |
| **Safaricom Bonga** (Kenya) | Points redeemable at **140,000+ Lipa na M-Pesa merchants**; 1 billion points redeemed in two months during a campaign. | Customers value points they can spend widely. A merchant network (coalition) is the long-term loyalty moat, once regulation allows. |
| **Bumpa** (Nigeria) | Free tier (25 products, 50 orders a month), paid subscriptions above that, plus transaction commissions and a 20% reseller programme; 50,000+ businesses. | Freemium with a usage cap converts; partner or reseller commissions lower acquisition cost. |
| **CGAP merchant research** | Payment acceptance alone does not drive adoption. Merchants want records, **loyalty and CRM**, store credit, supplier payments and working capital. Digital must be "decidedly better than cash". | Hossouko's bundle (records, loyalty, proof for credit) matches what merchants ask for. |

### What failed

| Comparable | What happened | Lesson |
|---|---|---|
| **Kippa** (Nigeria) | Bookkeeping app for merchants; raised USD 14.3M; closed in 2024. Did not convert traction into revenue; its payment and POS arm collapsed under hardware import costs after the naira devaluation. | Charge from the start (paid pilot). Avoid hardware. Keep costs in local currency where possible (hosting, SMS). |
| **Wider merchant and lending failures** (Lidya, Okra and others) | USD-denominated costs, premature expansion, weak follow-on funding. | Stay in one corridor until unit economics are proven, which is the existing gate. |

### Loyalty design evidence

- **Endowed progress:** in a field experiment, 34% of customers given a card with two of ten stamps already filled completed it, against 19% given an empty eight-stamp card. The required effort was identical (Nunes & Drèze, *Journal of Consumer Research*, 2006).
- **Retention economics:** repeat customers spend on average 67% more than new ones, and acquiring a customer costs several times more than keeping one. These are general small-business figures and must be tested locally in the pilot.
- **Direction of the African market:** smaller merchants increasingly join loyalty through wallet, bank or **coalition networks** rather than building their own programmes (ResearchAndMarkets, Africa Loyalty Programs 2025–2026).

### Evidence gaps to close in Phase 0

- Wave Business API and webhook access for small merchants, and whether customer phone numbers may be used for loyalty (Wave terms and ARTCI).
- Whether Orange Money and MTN MoMo can notify payments to a merchant's static QR, as Wave's webhook does; only flows started by the merchant's system were found.
- Actual PI-SPI merchant-QR adoption in Côte d'Ivoire, and a licensed participant willing to connect Hossouko.
- WhatsApp Business rates for Côte d'Ivoire, and local bulk SMS rates. These drive the cost per loyalty notification.
- Number of maquis and small restaurants in the target corridor; no reliable source was found.
- Merchant willingness to pay, measured in the paid pilot rather than estimated.

## Methodology note

Inclusion rates differ between the World Bank (58%) and the local fintech sector (up to 84%) because of different methods and collection periods. This is heterogeneity, not contradiction. Always cite the figure with its source, never a single aggregate.

## Sources

World Bank, *Global Findex Database 2025* · GSMA Mobile for Development · BCEAO (UEMOA regulation, PI-SPI, credit scoring, sandbox) · APSFD-CI · APIF-CI (gouv.ci) · SGPME · GUDE-PME · TechCabal, Financial Afrik, CFNews Afrique, AllAfrica · OSIRIS (Senegal) · Ivorian national indicators 2023.

Section 9 sources:

- [Wave edges closer to dethroning Orange in West Africa](https://launchbaseafrica.com/2026/03/24/the-267bn-crown-wave-edges-closer-to-dethroning-orange-in-west-africa/), Launch Base Africa, Mar. 2026
- [Wave CI payment by sector, Abidjan 2026](https://kolonell.com/en/blog/wave-ci-payment-by-sector-abidjan-2026) · [CinetPay tarifs 2026](https://kolonell.com/fr/blog/cinetpay-integration-tarifs-commissions-cote-ivoire-2026) · [Mobile money fees CI 2026](https://kolonell.com/en/blog/mobile-money-fees-cote-ivoire-comparison-2026), Kolonell
- [Best payment gateways in Côte d'Ivoire 2026](https://boldrails.com/blog/best-payment-gateways-cote-divoire), Boldrails
- [Les paiements marchands de Wave](https://osiris.sn/le-paiements-marchands-de-wave-un-nouveau-levier-pour-accelerer-l-inclusion.html), OSIRIS
- [Wave webhooks documentation](https://docs.wave.com/webhook)
- [Orange Money CI merchant API](https://kolonell.com/fr/blog/orange-money-ci-api-marchand-abidjan-integration-2026) · [Orange Money web payment](https://kolonell.com/fr/blog/orange-money-web-payment-integration-cote-ivoire-2026), Kolonell · [Orange CI launches OM Pay](https://www.findevgateway.org/fr/actualites/orange-cote-divoire-lance-om-pay-pour-simplifier-les-paiements-mobiles), FinDev Gateway
- [MTN MoMo API callbacks](https://momodeveloper.mtn.com/content/html_widgets/0a5av.html), MTN MoMo developer
- [PI-SPI: la BCEAO fait entrer l'Afrique de l'Ouest dans l'ère du paiement intégré](https://fr.allafrica.com/stories/202602120405.html), AllAfrica · [BCEAO sets 30 June deadline](https://www.ecofinagency.com/news-finances/0404-54418-bceao-imposes-june-30-deadline-to-complete-instant-payments-integration), Ecofin · [Code QR interopérable](https://docs.cdpi.dev/fr/notes-techniques/payments/code-qr-interoperable), CDPI
- [Santé privée: officines](https://economie-ivoirienne.ci/activites-sectorielles/sante-privee.html), economie-ivoirienne.ci
- [Moniepoint: from PoS scale to full-stack lock-in](https://techcabal.com/?p=180023), TechCabal · [Moniepoint 2025 report](https://techpoint.africa/news/moniepoint-2025-report/), Techpoint
- [Responsible digital credit for merchants: insights from Kenya](https://www.cgap.org/blog/responsible-digital-credit-for-merchants-insights-kenya) · [How to drive merchant payments](https://cgap.org/node/2637), CGAP
- [Kopo Kopo case study](https://www.gsma.com/mobilefordevelopment/wp-content/uploads/2016/02/Case_Study_-Kopo_Kopo_04_2014.pdf), GSMA
- [Bonga points](https://www.safaricom.co.ke/personal/value-added-services/bonga-points/bonga-points), Safaricom · [1 billion points redeemed](https://www.capitalfm.co.ke/business/?p=67091), Capital FM
- [Bumpa raises USD 4M](https://techcrunch.com/2022/10/19/nigerian-retail-automation-platform-bumpa-raises-4m-led-by-base10-partners), TechCrunch · [Bumpa subscription launch](https://techcabal.com/?p=101822), TechCabal
- [Kippa profile](https://www.startuplist.africa/startups/kippa), Startuplist Africa · [20 failed African fintech startups](https://thecondia.com/failed-african-fintech-startups-ideas/), The Condia
- [Endowed progress effect](https://knowledge.wharton.upenn.edu/podcast/knowledge-at-wharton-podcast/the-lowdown-on-customer-loyalty-programs-which-are-the-most-effective-and-why/), Knowledge at Wharton · [summary](https://coglode.com/nuggets/endowed-progress-effect)
- [Customer retention statistics](https://smallbiztrends.com/customer-retention-statistics/), Small Business Trends
- [Africa loyalty programs market 2025](https://www.businesswire.com/news/home/20250303176697/en/Africa-Loyalty-Programs-Market-Future-Growth-Dynamics-2025-Fintech-and-Mobile-Wallet-based-Loyalty-Programs-Dominate-Retail-and-Supermarket-driven-Programs-Gaining-Traction---ResearchAndMarkets.com), ResearchAndMarkets

The original French research notes are preserved in git history (`docs/Recherche approfondie : Inclusion fina.md`, `docs/dkassa-inclusion-financiere.md`, before this consolidation).
