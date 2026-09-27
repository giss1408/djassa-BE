# Djassa Product Concept

## One-sentence definition

Djassa is a low-bandwidth merchant operating layer for African markets. It helps informal and small merchants record sales, retain customers, communicate with them, and build a verifiable business history. Regulated financial services are an expansion path delivered through partners, not the first product.

Djassa is the product and technology initiative. Dkassa refers to the financial-inclusion product direction within the initiative. The final brand name remains to be confirmed.

## The problem

Small merchants and informal businesses often have:

- Frequent customer activity but no usable digital sales history.
- Limited access to bank credit because revenue is difficult to prove.
- Existing customer relationships managed through paper cards, memory, or messaging apps.
- Strong community savings practices that are difficult to track and secure digitally.
- Access to mobile money, but limited access to structured savings, credit, and business tools.

Customers also need a simple way to earn benefits from repeat purchases without installing a heavy application or managing a separate account for every merchant.

## Identity strategy: inherit trust, do not rebuild it

Djassa should anchor identity to an existing mobile-money account where the operator and licensed partners can legally and technically provide verification. A Wave, Orange Money, MTN MoMo, or equivalent account may already have completed operator-level onboarding; Djassa should not force a second full identity-creation process when a compliant verification signal can be reused.

This is a design direction, not an assumption that a phone number alone proves identity. Before launch, confirm with the operator, payment provider, ARTCI, BCEAO, and qualified local counsel what identity attributes may be shared, for which purposes, and under what consent and data-retention rules.

### Progressive verification tiers

Verification should match the risk and benefit of the feature:

| Tier | Use case | Minimum verification | Data boundary |
|---|---|---|---|
| **Tier 0** | Loyalty and basic rewards | Phone number or operator-linked identifier | No financial movement, no credit export |
| **Tier 1** | Tontine or partner savings workflow | Phone verification plus a lightweight liveness/selfie check where legally approved | Biometric evidence is used for verification, not treated as a general-purpose identity database |
| **Tier 2** | Credit-history export to a regulated partner | Tier 1 plus national-ID capture and partner-approved cross-check | Share only the fields and purpose explicitly consented to |

Users should not be forced through Tier 2 to use basic loyalty. Higher verification is triggered by higher-risk actions and must be explained in plain language. Biometric capture must be optional where required by law, processed by an approved provider, encrypted, access-controlled, and deleted or retained only under a documented policy.

The anti-fraud goal is to prevent one person from creating many accounts to farm rewards or manufacture a financial history, while avoiding unnecessary surveillance of low-risk users.

## Strategic direction: a federated identity trust layer for Côte d'Ivoire

Djassa can become the premise for a **federated identity manager** for Côte d'Ivoire: a consent-driven trust layer that connects existing identity authorities rather than replacing them. The network could connect mobile-money operators, licensed KYC providers, banks, microfinance institutions, merchants, and approved public or ecosystem partners.

Djassa's role would be to:

- Request verification for a specific purpose.
- Obtain a provider-issued attestation or verification result.
- Normalize assurance levels across providers.
- Let the user view, consent to, and revoke data-sharing permissions.
- Provide partners with the minimum identity claim required for a transaction or service.
- Detect duplicate or contradictory identity signals without exposing unnecessary raw data.

Djassa must not become the owner of the national identity system, copy every operator's KYC database, or issue a government identity. The long-term product is a **federation and consent layer**, with authoritative operators and licensed institutions retaining responsibility for the original verification.

This direction requires a separate legal, governance, interoperability, privacy, and security program with ARTCI, BCEAO, mobile-money operators, identity providers, and qualified local counsel. It is a strategic opportunity, not a current product claim.

## The commercial wedge

Djassa should not launch as a general African fintech. The first paying customer is the merchant, and the first paid problem is:

> Help a merchant bring customers back and understand daily business activity using a phone, even when connectivity is unreliable.

The initial target is a dense local cluster of independent merchants with repeat-purchase behavior: neighborhood groceries, pharmacies, restaurants, salons, and service shops. A cluster is more valuable than isolated merchants because customers can recognize the product across nearby outlets and Djassa can acquire merchants through associations, distributors, aggregators, and payment partners.

## The first product: merchant loyalty

The first release is a lightweight loyalty service for independent retailers such as neighborhood shops, restaurants, pharmacies, and small supermarkets.

### Merchant workflow

1. The merchant registers an outlet and configures a loyalty rule.
2. A customer identifies themselves with a QR code or phone number.
3. The merchant records a transaction and the customer receives points or another benefit.
4. The merchant sees repeat visits, transaction volume, and customer activity.
5. The customer can view their own points and transaction history.

The first product must work on low-cost phones and unreliable connectivity. SMS, WhatsApp, QR codes, USSD-compatible workflows, and mobile money are more important than complex native-app features at the beginning. The merchant must be able to record a sale offline and synchronize it later without creating a duplicate.

## The long-term financial-inclusion path

Loyalty is the entry point, not the final business. With explicit consent and strong privacy controls, structured activity can support:

1. Digital tontines with scheduled contributions and reminders.
2. Explainable reliability indicators based on regular behavior.
3. Merchant revenue-history exports for a partner lender.
4. Goal-based savings held directly by a regulated partner.
5. Financial education delivered at the moment it is useful.

Djassa should facilitate access to financial services. It should not present itself as a bank, hold customer deposits, or lend directly unless the required regulatory status exists. Financial products must follow proven merchant usage; they should not be used as an unverified acquisition promise.

## Product principles

- Start with a small merchant pilot before building broad financial features.
- Make every score explainable to the person affected by it.
- Let users see and correct their own data.
- Support low-bandwidth channels and local-language service workflows.
- Keep customer and merchant data separate and permissioned.
- Match identity verification and data collection to the risk of the requested feature.
- Never store a reusable biometric database when a one-time verification result is sufficient.
- Use regulated financial institutions for custody, lending, and payment settlement.
- Treat women, rural users, and low-income users as primary users, not edge cases.
- Validate real usage before expanding the roadmap.
- Enter one country and one operating corridor at a time; reuse the platform, not assumptions about customers or regulation.
- Charge for measurable merchant value before monetizing regulated financial referrals.

## Current scope and non-scope

### In scope for the first pilot

- Merchant and customer identity.
- Tier 0 phone/operator-linked identity for loyalty.
- Loyalty rules and points.
- Transaction history.
- Basic merchant reporting.
- Consent-controlled data export.
- Secure mobile-money integration where approved.
- Offline transaction queue and synchronization.
- Country capability discovery and localized support requests.

### Not in scope without additional validation

- Direct lending by Djassa.
- Djassa holding savings funds.
- Opaque credit scoring.
- Public resale of personal transaction data.
- Cash-out or financial products without regulatory and partner approval.
- A pan-African launch without a country-specific partner, support, payment, and compliance plan.
- Biometric or national-ID verification without legal, partner, security, and retention approval.

## Success signal

The first proof of value is not the number of features. It is whether merchants record transactions consistently, customer repeat visits increase, merchants pay or renew, and the resulting history is useful enough to support a credible partner conversation. If merchants do not pay for the operating value, financial expansion is premature.

Related documents:

- [Business model](BUSINESS-MODEL.md)
- [Partner and outreach plan](PARTNERS-AND-OUTREACH.md)
- [Product roadmap](ROADMAP.md)
- [Technical guide](TECHNICAL-GUIDE.md)
