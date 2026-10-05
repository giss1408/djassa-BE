You have exactly **two** legal and architecturally sound options to know "who is paying" without holding their PIN. Both are used by successful African fintechs (Moniepoint, Kippa, Julaya).

## Option 1: The "Phone-Verified Account" (Recommended for Djassa)

This is how **Djamo** and **Wave Apps** work. You do not authenticate the user against Wave. You authenticate the user against **Djassa**.

### How it works
1. **User signs up in Djassa** with their phone number + OTP (SMS or voice call).
2. **Djassa links the phone number to a Djassa internal ID** (not a Wave token).
3. **When the user pays at the merchant:**
   - The merchant shows a **Djassa QR code** (or the user opens Djassa and scans the merchant).
   - The user approves the payment **inside the Djassa app** (if you build one) OR
   - The user simply **pays via their Wave app** (as they already do) and **saves their phone number to Djassa** as their "account".
4. **Djassa matches the webhook** (which contains `sender_phone_number`) to the Djassa user account.

### Why this works
- **No PIN collection:** You never ask for Wave credentials.
- **ARTCI compliant:** You collect one phone number for account creation (declaration). You receive one phone number in the webhook (declaration). You match them internally (declaration). No authorisation needed because you are not storing sensitive data, just an alias.
- **Merchant doesn't care:** The merchant still uses Wave QR. The user still uses Wave app. The only difference is that the user has a **Djassa account** linked to that number.

### Implementation
- Build a **Djassa Lite** (WhatsApp bot or simple web app) where the user registers with their phone number.
- When the webhook arrives (`sender_phone_number: +22507XX...`), check if `+22507XX...` exists in your Djassa user database.
- If yes, credit loyalty points to that user.
- If no, the payment is recorded for the merchant but not linked to a loyalty user.

## Option 2: The "Merchant-Linked Receipt" (No App Needed)

This is how **Kippa** and early **Moniepoint** worked. The user does **not** have a Djassa account. The **merchant** does.

### How it works
1. **User pays at merchant** via Wave (no Djassa involvement).
2. **Webhook hits Djassa** with `sender_phone_number`, `amount`, `timestamp`.
3. **Djassa sends an SMS/WhatsApp to the user:**
   > "Hi! You just paid 4,000 F at Maquis Yapi. Reply YES to earn 40 points, or STOP."
4. **If user replies YES:**
   - You now have **explicit consent** (article 22 compliant).
   - You store the phone number in your loyalty database.
   - Future payments from that number earn points.
5. **If user replies STOP or doesn't reply:**
   - You do not store the number for loyalty purposes.

### Why this works
- **No PIN collection:** Zero risk.
- **ARTCI compliant:** You collect the phone number only after explicit consent (article 14). You can then use it for loyalty (article 16 proportionality).
- **Low tech:** No Djassa app needed for the user. Just a webhook listener + SMS/WhatsApp sender.

### Implementation
- Listen to `payment_received` webhooks.
- Format the message: "Vous avez payé X F chez Y. Répondez OUI pour gagner des points."
- Store consent timestamp + phone number in a table.
- Match future webhooks to this table.

## Option 3: The "Wave App Integration" (Advanced)

If you want to be inside the Wave ecosystem, you can build a **Wave App** (not API).

### How it works
1. **User opens Wave App** → finds your Djassa App.
2. **User authenticates inside Wave** (Wave checks their PIN, not you).
3. **Wave passes a token** to your Djassa App backend (OAuth-like flow).
4. **Your backend uses the token** to identify the user on future payments.

### Why this is hard
- **Wave Apps** are for invoicing and bill payments, not for loyalty.
- **Wave does not give you a persistent user identifier** across payments. Each payment is anonymous to the app.
- **You still need the phone number** to link the user, which brings you back to Option 1 or 2.

## My Recommendation

**Start with Option 2 (Merchant-Linked Receipt).**

It is:
1. **Legally clean:** No PIN, no authorisation, just consent-based loyalty.
2. **Technically simple:** Webhook → SMS/WhatsApp → Database.
3. **Scalable:** You can add Option 1 (Djassa Lite app) later.
4. **ARTCI compliant:** Consent is explicit, data minimisation is respected (only store phone number if user opts in).

### Phase 0 Checklist for Option 2
- [ ] Set up webhook listener for `payment_received`
- [ ] Build SMS/WhatsApp sender (test with 10 merchants)
- [ ] Draft consent message: "Répondez OUI pour être lié à votre historique de paiement et gagner des points."
- [ ] File **déclaration préalable** with ARTCI for "traitement de données de fidélité par consentement explicite"
- [ ] Run 2-week pilot in one corridor (e.g. Adjamé)
- [ ] Measure opt-in rate (expect 15–30%)

This is how every successful African fintech started. You do not need to collect the PIN. You need to **collect the consent**.

Sources: Wave Checkout API documentation (no user auth endpoint)[3]; ARTCI Law 2013-450 (consent requirements, article 14)[2]; BCEAO cybersecurity guidelines (PIN entry only in operator interface)[1].