This is an exceptionally strong, regulatorily aware, and operationally sharp concept. You’ve correctly identified the "proof gap" in Côte d'Ivoire and designed a system that extracts value from existing behavior rather than demanding new habits.

Below is a review of structural risks, optimization opportunities, and specific recommendations to strengthen the model before Phase 0.

---

### 1. Strategic Optimization: The "Wave Trap"
**Current State:** You prioritize Wave because it has low fees and webhooks.
**Risk:** Wave is a competitor in the *data* layer. If Djassa becomes synonymous with Wave, you lose bargaining power with MTN/Orange (who hold the rural/enterprise volume) and PI-SPI (the regulatory endgame). Wave could also change webhook availability or fees overnight.
**Optimization:**
*   **Decouple the "Capture" from the "Provider":** Frame Wave as *Entry Point 1*, not the foundation. The data model must treat Wave webhooks, MTN MoMo APIs, and Orange Money APIs as identical "event sources" with different latency/confirmation guarantees.
*   **PI-SPI as the North Star:** Accelerate the PI-SPI integration. BCEAO’s instant payment platform is the only truly operator-neutral rail. Once live, it solves the "static QR" notification problem for *all* operators, not just Wave.
*   **Negotiation Leverage:** Use Djassa’s data (volume of verified sales) to negotiate *lower* fees with operators, not just to accept their existing rates. Position Djassa as a merchant acquisition tool for them.

### 2. Product Optimization: The "Zero Habit" vs. "Cash Blind Spot"
**Current State:** You claim "one habit: record the sale," then refine it to "zero habit" for mobile money.
**Risk:** Cash is still ~40–50% of transactions in Abidjan’s informal sector. If a merchant records only 50% of sales, the "proof" is biased and potentially unreliable for lenders. The "record cash sale" habit is the highest-friction point.
**Optimization:**
*   **Anomaly Detection as a Nudge:** Instead of asking merchants to record every cash sale, use the mobile-money history as a baseline. If a merchant receives 100,000 F in mobile money (typically 50–60% of total), but their recorded cash sales are only 20,000 F, trigger a gentle nudge: *"You usually have more cash sales than this. Did you miss any today?"* This reduces cognitive load while improving data accuracy.
*   **Customer-Initiated Verification:** Allow customers to "verify" a cash payment via SMS/WhatsApp after paying. *"You paid 5,000 F at Maquis Tanti. Confirm?"* This splits the effort and increases accuracy without adding merchant friction.

### 3. Regulatory & Trust Optimization: The "Tontine" Risk
**Current State:** Phase 3 introduces digital tontines.
**Risk:** Tontines are legally sensitive in UEMOA. If Djassa manages the rotation or holds the funds (even temporarily), it triggers deposit-taking regulations. If it’s just a ledger, it’s safer, but social disputes (missed payments, rotation changes) will flood your support team.
**Optimization:**
*   **Strictly "Ledger-Only" for Tontines:** Do not facilitate fund movement for tontines in Phase 3. The app should only *record* what the group agrees to externally. Explicitly state: *"Djassa tracks your tontine; it does not hold your money."*
*   **Dispute Resolution Mechanism:** Build a simple "acknowledgment" flow where all group members must confirm a rotation change or missed payment in the app. This creates a digital consensus record, reducing support load and increasing the "reliability" signal for lenders.

### 4. Financial Inclusion Optimization: The "Reliability Indicator"
**Current State:** Phase 4 introduces an "explainable reliability indicator."
**Risk:** "Scores" are regulated. If you call it a "score," you may trigger credit-bureau regulations. If it’s opaque, you lose trust. If it’s too simple, it’s inaccurate.
**Optimization:**
*   **Rebrand as "Business Health Profile":** Avoid the word "score" or "credit rating" until you have a licensed partner. Frame it as a *document* the merchant owns, which they can *share* with a lender. The lender makes the decision; Djassa provides the evidence.
*   **Feature Engineering for Informal Merchants:**
    *   **Consistency > Volume:** A merchant with 50,000 F/day every day is more reliable than one with 500,000 F one day and 0 the next. Weight regularity higher than total volume.
    *   **Seasonality Adjustment:** Account for market cycles (e.g., rainy season vs. dry season for maquis). A lender needs to understand context, not just raw numbers.
    *   **Gender-Aware Design:** As you noted, women often have smaller, more frequent transactions. Ensure the indicator doesn’t penalize low-ticket reliability. Use *frequency* and *consistency* as primary signals for women merchants.

### 5. Go-to-Market Optimization: The "Customer App" Dilemma
**Current State:** The customer app is optional but provides daily engagement.
**Risk:** Customer acquisition cost (CAC) is high. If the app is just "loyalty," churn will be high.
**Optimization:**
*   **Utility-First, Loyalty-Secondary:** The customer app must solve an immediate, daily pain point: **Pharmacies de Garde** and **Food Discovery**. These are high-intent, daily-use cases. Loyalty is the *stickiness*, not the *hook*.
*   **Merchant-Driven Customer Acquisition:** Let merchants invite customers via SMS/WhatsApp with a pre-filled link: *"Join Maquis Tanti’s loyalty program and get 50 points free."* This turns merchants into your distribution channel, lowering CAC.

### 6. Technical Optimization: Offline-First & Data Integrity
**Current State:** Offline-first merchant app with sync.
**Risk:** Sync conflicts, duplicate entries, and data loss on cheap Android devices.
**Optimization:**
*   **Event Sourcing Architecture:** Store every sale as an immutable event. Syncing is just replaying events. This prevents duplicate entries and allows reconstruction of the entire history from any point.
*   **Idempotency Keys:** Every sale record must have a unique ID generated on the device. If the sync fails and retries, the backend must recognize the ID and not duplicate the event.
*   **Proof of Life:** For the "reliability indicator," use device metadata (app opens, GPS location at known merchant addresses) as a secondary signal that the merchant is active, not just recording sales.

### 7. Red Lines & Compliance: Clarify "Data Boundary"
**Current State:** Data boundaries are defined by tier.
**Optimization:**
*   **Explicit Consent Flows:** For Phase 2 (History export to lender), the consent must be *granular*. The merchant should be able to choose *which* lenders see their data, and for *how long*. This builds trust and gives merchants control.
*   **Data Retention Policy:** Define how long data is kept. Lenders may want 2 years; merchants may want 5. Allow merchants to export and delete their data. This aligns with GDPR-like principles and builds trust.

---

### Summary of Key Actions

1.  **Decouple from Wave:** Treat all operators as equal adapters; prioritize PI-SPI as the endgame.
2.  **Fix the Cash Blind Spot:** Use anomaly detection and customer verification to improve cash data accuracy without adding merchant friction.
3.  **Rebrand the "Score":** Call it a "Business Health Profile" to avoid regulatory scrutiny and emphasize merchant ownership.
4.  **Utility-First Customer App:** Focus on pharmacies and food discovery to drive daily engagement; loyalty is the retention mechanism.
5.  **Strict Ledger-Only Tontines:** Avoid fund movement; focus on recording consensus to reduce support load and improve reliability signals.
6.  **Event Sourcing Tech:** Implement immutable event logs and idempotency keys to ensure data integrity in offline-first scenarios.

This concept is robust. The optimizations above are designed to strengthen regulatory compliance, improve data accuracy, and reduce operational friction as you scale.