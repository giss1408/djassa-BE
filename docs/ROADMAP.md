# Djassa Product Roadmap

This roadmap connects the business idea to measurable delivery. A phase is complete only when real users validate it, not when code has merely been deployed.

## Phase 0: Discovery and compliance

**Goal:** Confirm that the problem, users, partners, and legal perimeter are real.

Deliverables:

- Five to ten merchant interviews.
- A narrow pilot agreement.
- One target corridor, merchant segment, and acquisition channel.
- Payment-provider sandbox access.
- Data inventory and consent design.
- Identity and KYC boundary review with the mobile-money/payment partner.
- Regulatory review for planned payment and data features.
- Baseline metrics and support process.

Exit criteria:

- A clear pilot user and partner are identified.
- No unresolved blocker for the MVP data flow.

## Phase 1: Merchant loyalty MVP

**Goal:** Record useful activity and create repeat usage.

Deliverables:

- Merchant and customer identity.
- Tier 0 phone/operator-linked identity for loyalty.
- Loyalty rules and points.
- Transaction history.
- Merchant reporting.
- Consent-controlled exports.
- Secure authentication and ownership checks.
- Offline transaction queue and synchronization.
- Country profile and localized support workflow.

Measure:

- Active merchants.
- Transactions per merchant.
- Customer repeat rate.
- Merchant retention.
- Cost per active merchant.
- Paid conversion and renewal rate.
- Support cost per active outlet.
- Data consumed per active user.

Identity gate:

- Do not require biometric or national-ID verification for basic loyalty.
- Define the operator identity signal and consent before relying on it.
- Test account-duplication prevention without exposing unnecessary personal data.

## Phase 2: Merchant operations and network expansion

**Goal:** Make the core merchant product valuable and repeatable in the first corridor before adding financial complexity.

Deliverables:

- Campaigns, customer reactivation, and merchant reporting.
- Merchant referral and association onboarding.
- Country-specific payment/support adapters.
- Progressive verification workflow and fraud-review queue, only where the partner and regulator approve it.
- Repeatable onboarding and support playbook.

Exit criteria:

- Merchants pay or renew.
- Acquisition and support economics are understood.
- The product works under low-connectivity conditions.

## Phase 3: Digital tontine

**Goal:** Help existing community groups track contributions and schedules.

Deliverables:

- Closed groups and membership controls.
- Contribution schedule and reminders.
- Payment-provider integration.
- Idempotent webhook processing.
- Reconciliation and dispute workflow.

Do not begin until the merchant product has validated willingness to pay and the platform has stable identity, audit logging, authorization, consent, payment-state, and reconciliation controls.

## Phase 4: Explainable reliability indicator

**Goal:** Provide a transparent internal signal based on regular activity.

Deliverables:

- Documented scoring inputs.
- User-visible explanation.
- Correction and appeal workflow.
- Bias and outcome monitoring.
- No third-party sharing without consent and legal review.
- Verification tier and identity evidence are visible to the user.

## Phase 5: Partner financial services

**Goal:** Connect eligible users to regulated savings or credit partners.

Deliverables:

- Written partner agreement.
- Partner-approved KYC and identity-data sharing contract.
- Consent and data-sharing contract.
- Direct fund flow to the regulated provider.
- Referral and outcome tracking.
- Reconciliation, support, and incident procedures.

Djassa remains a technology and distribution partner unless its regulatory status changes.

## Phase 6: Geographic and product expansion

Possible extensions include a second UEMOA country, rural merchant networks, agriculture, and insurance. Each extension requires separate user research, local payment/support adapters, partner validation, and regulatory review. Expansion should reuse technical components while localizing commercial operations.

## Strategic horizon: federated identity trust layer

This is a long-term platform direction, not an MVP commitment.

Potential capabilities:

- Provider-issued identity attestations.
- Consent and purpose management.
- Assurance-level mapping across mobile-money, KYC, and financial partners.
- Privacy-preserving partner verification.
- Revocation, audit, and dispute workflows.
- Interoperability APIs for approved institutions.

Entry conditions:

- Proven Tier 0 and partner-managed Tier 1/Tier 2 verification flows.
- Written governance and data-sharing agreements.
- Regulatory and privacy review with relevant Côte d'Ivoire authorities and licensed partners.
- A clear liability model for incorrect, stale, or fraudulent identity claims.
- Independent security and privacy assessment.

## Roadmap governance

For every proposed feature, record:

- User problem and evidence.
- Expected business value.
- Data collected and purpose.
- Partner or regulatory dependency.
- Security and authorization impact.
- Success metric.
- Rollback or shutdown condition.

Related documents:

- [Product concept](PRODUCT-CONCEPT.md)
- [Business model](BUSINESS-MODEL.md)
- [Technical guide](TECHNICAL-GUIDE.md)
