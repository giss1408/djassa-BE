# Djassa Product Concept — v2: The Event as the Core Primitive

## One-sentence definition

Djassa is one habit — recording a verified transaction — that automatically activates everything else: loyalty, community savings, a reliability score, and eventually credit access. It is not five features shipped in sequence. It is one primitive with five views built on top of it.

Djassa is the product and technology initiative. Dkassa refers to the financial-inclusion product direction within the initiative. The final brand name remains to be confirmed.

## The activator: the transaction event

Everything in this product — loyalty points, merchant revenue history, tontine regularity, the reliability score, the credit export to a partner lender — is downstream of the exact same event:

> **A verified transaction: who, where, how much, when.**

```
                    THE EVENT
         (verified transaction: who, where,
              how much, when)
                       │
     ┌─────────┬───────┼────────────┬───────────────┐
     ▼         ▼       ▼            ▼                ▼
  Points   Merchant  Tontine      Score           Credit
  issued   revenue   regularity  (reliability    export
 (loyalty)  history  (community   input)        (to partner
            (proof)   savings)                     IMF)
```

The merchant does **one thing**: scan a QR code or enter a phone number at checkout. Every downstream benefit — loyalty, revenue proof, community savings tracking, reliability signal, eventual credit case — is generated automatically from that single recorded action, at zero extra effort. Loyalty, tontine, savings, and credit are not four roadmap phases. They are four things that become *visible* once enough of that one event has accumulated.

This reframing exists to solve a specific failure pattern observed across comparable African merchant-tools startups: strong early traction (thousands of active users) that never converts into durable engagement or revenue, because the product asked merchants to adopt several separate habits instead of compounding value from one. Djassa asks for one habit, and layers value on top of it without asking for more.

## The problem

Small merchants and informal businesses often have:

- Frequent customer activity but no usable digital sales history.
- Limited access to bank credit because revenue is difficult to prove.
- Existing customer relationships managed through paper cards, memory, or messaging apps.
- Strong community savings practices that are difficult to track and secure digitally.
- Access to mobile money, but limited access to structured savings, credit, and business tools.

Customers also need a simple way to earn benefits from repeat purchases without installing a heavy application or managing a separate account for every merchant.

## Identity strategy: inherit trust, do not rebuild it

Djassa should reuse a compliant identity signal from an existing mobile-money account where the operator and licensed partners make that possible. A phone number alone is not proof of identity, and Djassa must not assume that operator KYC data can be copied or reused without an explicit legal, technical, and consent agreement.

Use progressive verification rather than one high-friction onboarding flow:

- **Tier 0 — loyalty:** phone or operator-linked identifier only.
- **Tier 1 — tontine or partner savings:** phone verification plus approved lightweight liveness/selfie verification where legally permitted.
- **Tier 2 — credit export:** national-ID capture and partner-approved cross-check before sharing a history with a regulated lender.

The purpose is to reduce duplicate accounts and reward abuse without building a general-purpose biometric database. Prefer a provider-issued verification result or attestation over storing raw biometric material. Verify all requirements with the mobile-money partner, ARTCI, BCEAO, and qualified local counsel before implementation.

## The one metric that matters

Every other metric is downstream of this one: **the % of a merchant's real daily transactions that actually get recorded through Djassa.**

If that number is low, nothing downstream works — not the loyalty perception, not the score, not the eventual credit conversation — no matter how well any individual feature is built. This is the single number the team should look at before any other roadmap decision. A merchant who records 90% of their sales for 60 days is a fundamentally different, more valuable outcome than ten merchants who each record 10% for a week.

## The commercial wedge

Djassa should not launch as a general African fintech. The first paying customer is the merchant, and the first paid problem is:

> Help a merchant bring customers back and understand daily business activity using a phone, even when connectivity is unreliable — by making it effortless to record every sale.

The initial target is a dense local cluster of independent merchants with repeat-purchase behavior: neighborhood groceries, pharmacies, restaurants, salons, and service shops. A cluster is more valuable than isolated merchants because customers can recognize the product across nearby outlets, and because visible peer adoption drives the recording habit harder than any individual sales pitch.

## The first product: recording the event, seen as loyalty

The first release is a lightweight loyalty service — but the real product being built underneath it is the transaction-recording habit itself. Loyalty is simply the first, most immediately visible view of the event stream.

### Merchant workflow

1. The merchant registers an outlet and configures a loyalty rule.
2. A customer identifies themselves with a QR code or phone number.
3. The merchant records a transaction — **this is the only new habit being asked of them** — and the customer receives points or another benefit as an automatic side effect.
4. The merchant sees repeat visits, transaction volume, and customer activity, generated automatically from the same recorded events.
5. The customer can view their own points and transaction history.

The first product must work on low-cost phones and unreliable connectivity. SMS, WhatsApp, QR codes, USSD-compatible workflows, and mobile money matter more than complex native-app features at the beginning. The merchant must be able to record a sale offline and synchronize it later without creating a duplicate — because if recording ever fails or feels unreliable, the entire event stream underneath every future feature breaks with it.

## The long-term financial-inclusion path: new views, not new habits

Loyalty is the entry point, not the final business. With explicit consent and strong privacy controls, the same accumulated event stream — with no new merchant habit required — can support:

1. **Digital tontines** with scheduled contributions and reminders — the same transaction event, applied to a community savings cycle instead of a single sale.
2. **Explainable reliability indicators** based on regular recorded behavior — a score is just a read of the event stream over time, never a separate data-collection exercise.
3. **Merchant revenue-history exports** for a partner lender — the accumulated event stream, formatted for a specific partner's underwriting needs.
4. **Goal-based savings** held directly by a regulated partner — contributions are themselves transaction events, routed to a partner's account, never held by Djassa.
5. **Financial education** delivered at the moment it is useful — triggered by specific events in the stream (first tontine cycle completed, first score improvement), not a standalone module.

Djassa should facilitate access to financial services. It should not present itself as a bank, hold customer deposits, or lend directly unless the required regulatory status exists. Financial products must follow proven merchant usage of the core recording habit; they should not be used as an unverified acquisition promise.

## Product principles

- Start with a small merchant pilot before building broad financial features.
- Treat the recorded transaction as the only primitive — every new feature must be a view on existing events, not a new data-collection habit, unless there is no other way to get the signal.
- Make every score explainable to the person affected by it.
- Let users see and correct their own data.
- Support low-bandwidth channels and local-language service workflows.
- Keep customer and merchant data separate and permissioned.
- Use regulated financial institutions for custody, lending, and payment settlement.
- Treat women, rural users, and low-income users as primary users, not edge cases.
- Validate real usage — measured as % of transactions recorded — before expanding the roadmap.
- Enter one country and one operating corridor at a time; reuse the platform, not assumptions about customers or regulation.
- Charge for measurable merchant value before monetizing regulated financial referrals.

## Current scope and non-scope

### In scope for the first pilot

- Merchant and customer identity.
- The transaction-recording primitive itself: QR/phone-number capture, offline queue, sync without duplication.
- Loyalty rules and points, as the first view on the event stream.
- Transaction history and basic merchant reporting.
- Consent-controlled data export.
- Secure mobile-money integration where approved.
- Country capability discovery and localized support requests.

### Not in scope without additional validation

- Any new feature that requires a second, separate habit from the merchant beyond recording the transaction.
- Direct lending by Djassa.
- Djassa holding savings funds.
- Opaque credit scoring.
- Public resale of personal transaction data.
- Cash-out or financial products without regulatory and partner approval.
- A pan-African launch without a country-specific partner, support, payment, and compliance plan.

## Success signal

The first proof of value is not the number of features shipped. It is:

1. Whether merchants record a high and growing share of their real transactions, consistently, for 60+ days.
2. Whether customer repeat-visit rate increases as a visible consequence.
3. Whether merchants pay or renew based on that recorded history alone — before any financial-inclusion feature exists.
4. Whether the resulting event stream is complete and trustworthy enough to support a credible partner conversation (IMF, guarantee scheme) without additional data cleanup.

If merchants do not consistently record transactions and do not pay for the operating value that creates, every feature built on top of that stream — tontine, score, credit — is premature, regardless of how well any one of them is designed in isolation.
