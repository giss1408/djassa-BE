# Djassa — Finance Validation Pack

*Working document · 1 October 2026 · Côte d'Ivoire · [French version](FINANCE-VALIDATION.fr.md) · [English budget](FINANCE-BUDGET.md) · [French budget](FINANCE-BUDGET.fr.md)*

Use this pack to replace budget assumptions with supplier quotes, cash receipts, and observed results. **No supplier quote or commercial result is treated as verified here.** Do not present blank fields as commitments or evidence.

Euro equivalents use the fixed peg **€1 = XOF 655.957**. XOF is the primary currency. Cash-flow amounts are shown in **XOF millions**; for example, 0.50000 means XOF 500,000.

## 1. Supplier quote register

The budget amounts below are planning allowances, not supplier offers. Collect two comparable quotes where possible. Archive the source document and note whether the price includes VAT, delivery, installation, maintenance, transfer fees, and any withholding taxes.

| Item to quote | Budget allowance | Quote 1: supplier / price | Quote 2: supplier / price | Status / supporting document |
|---|---:|---|---|---|
| Test fleet: phones, tablets, laptops, and accessories | XOF 3,050,000 (€4,649.70) | To collect | To collect | Unverified |
| Specialist integration and production hardening | XOF 2,400,000 (€3,658.78) | To collect | To collect | Unverified |
| Hosting, domain, backups, and monitoring | XOF 900,000 (€1,372.04) for 6 months | To collect | To collect | Unverified |
| OTP, SMS/WhatsApp, and payment tests | XOF 600,000 (€914.69) | To collect | To collect | Confirm unit rates and monthly minimums |
| Company and brand registration | XOF 800,000 (€1,219.59) | To collect | To collect | Reduce if already paid |
| Legal, data-protection, and regulatory counsel | XOF 1,800,000 (€2,744.08) | To collect | To collect | Unverified |
| Independent security audit | XOF 1,500,000 (€2,286.74) | To collect | To collect | Confirm scope and retest |
| Payment-partner contract and integration | XOF 500,000 (€762.25) | To collect | To collect | Partner minimum fees excluded until quoted |
| Transport, field work, and pilot support | XOF 2,600,000 (€3,963.67) | To collect | To collect | Confirm days and trips |
| Launch materials and acquisition | XOF 2,000,000 (€3,048.98) | To collect | To collect | Separate one-off spend from cost per merchant |
| Accounting, banking, communications, and software | XOF 1,200,000 (€1,829.39) | To collect | To collect | Unverified |

For each quote, record the supplier's legal name and contact details · quote date and validity period · currency · price before and including tax · delivery/installation fees · payment schedule and method · warranty and maintenance · cancellation terms · approver · link or location of the supporting document. Add omitted costs to the budget and recalculate the 15% contingency.

## 2. 24-month cash-flow forecast

This scenario follows the budget assumptions: XOF 30.82M of initial funding in month 1; XOF 30.82M of launch and pilot spending across months 1–6; no pilot revenue counted; 10 paying merchants at the end of month 6; and **25 net new paying merchants each month** from month 7. Assumed average subscription price is XOF 7,500/month; 10% of subscription receipts are variable service costs, leaving a 90% contribution margin; post-pilot fixed costs are XOF 2M/month.

Months 1–6 spending is phased provisionally to illustrate the timing of cash outflows. Months 7–24 include XOF 2M in fixed costs plus variable costs equal to 10% of subscription receipts. The initial funding includes **no additional financing after month 1**.

| Month | Paying merchants | Funding received | Subscription receipts | Total cash outflow | Net cash change | Cumulative cash without new funding |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | — | 30.82000 | 0.00000 | 8.00000 | 22.82000 | 22.82000 |
| 2 | — | 0.00000 | 0.00000 | 6.00000 | -6.00000 | 16.82000 |
| 3 | — | 0.00000 | 0.00000 | 5.00000 | -5.00000 | 11.82000 |
| 4 | — | 0.00000 | 0.00000 | 4.50000 | -4.50000 | 7.32000 |
| 5 | — | 0.00000 | 0.00000 | 3.80000 | -3.80000 | 3.52000 |
| 6 | 10 | 0.00000 | 0.00000 | 3.52000 | -3.52000 | 0.00000 |
| 7 | 35 | 0.00000 | 0.26250 | 2.02625 | -1.76375 | -1.76375 |
| 8 | 60 | 0.00000 | 0.45000 | 2.04500 | -1.59500 | -3.35875 |
| 9 | 85 | 0.00000 | 0.63750 | 2.06375 | -1.42625 | -4.78500 |
| 10 | 110 | 0.00000 | 0.82500 | 2.08250 | -1.25750 | -6.04250 |
| 11 | 135 | 0.00000 | 1.01250 | 2.10125 | -1.08875 | -7.13125 |
| 12 | 160 | 0.00000 | 1.20000 | 2.12000 | -0.92000 | -8.05125 |
| 13 | 185 | 0.00000 | 1.38750 | 2.13875 | -0.75125 | -8.80250 |
| 14 | 210 | 0.00000 | 1.57500 | 2.15750 | -0.58250 | -9.38500 |
| 15 | 235 | 0.00000 | 1.76250 | 2.17625 | -0.41375 | -9.79875 |
| 16 | 260 | 0.00000 | 1.95000 | 2.19500 | -0.24500 | -10.04375 |
| 17 | 285 | 0.00000 | 2.13750 | 2.21375 | -0.07625 | **-10.12000** |
| 18 | 310 | 0.00000 | 2.32500 | 2.23250 | 0.09250 | -10.02750 |
| 19 | 335 | 0.00000 | 2.51250 | 2.25125 | 0.26125 | -9.76625 |
| 20 | 360 | 0.00000 | 2.70000 | 2.27000 | 0.43000 | -9.33625 |
| 21 | 385 | 0.00000 | 2.88750 | 2.28875 | 0.59875 | -8.73750 |
| 22 | 410 | 0.00000 | 3.07500 | 2.30750 | 0.76750 | -7.97000 |
| 23 | 435 | 0.00000 | 3.26250 | 2.32625 | 0.93625 | -7.03375 |
| 24 | 460 | 0.00000 | 3.45000 | 2.34500 | 1.10500 | **-5.92875** |

Amounts are in XOF millions. A negative balance does not assume a bank overdraft; it shows the additional funding needed to pay the planned costs. In this scenario, monthly costs are covered from month 18, but the cash need reaches **XOF 10.12M (€15,427.84)** in month 17. At least that amount of bridge funding is needed before then, in addition to the initial envelope; include a safety reserve before seeking financing. At the end of month 24, the cumulative deficit is still **XOF 5.93M (€9,038.32)** without additional funding.

This projection assumes subscriptions are collected in the same month, net growth of 25 merchants is achieved every month, and fixed costs do not increase with volume. It excludes taxes, bad debt, late payments, refunds, additional hires, fundraising costs, and partner revenue. Replace the provisional month 1–6 spending schedule with actual quote and invoice payment dates before making a funding decision.

### Optional sponsored-deal revenue sensitivity

Sponsored placements could add cash, but neither the price nor merchant demand has been tested. The table below is a **what-if only**, layered onto the cash-flow scenario above; it does not reduce the XOF 30.82M funding request. Assume a 7-day placement, all fees are paid in the month sold, sales begin in month 7 and continue at the same rate, and 20% of placement revenue is used for variable selling and delivery costs (80% contribution). The XOF 1,000–3,000 prices and 10–50 monthly bookings are test inputs, not local market evidence.

| Scenario | Paid 7-day placements/month | Test price/placement | Gross receipts/month | Contribution/month after assumed 20% variable cost | Peak additional cash need | Cumulative deficit at month 24 |
|---|---:|---:|---:|---:|---:|---:|
| Low | 10 | XOF 1,000 (€1.52) | XOF 10,000 (€15.24) | XOF 8,000 (€12.20) | XOF 10,032,000 (€15,293.69), month 17 | XOF 5,784,750 (€8,818.79) |
| Base | 25 | XOF 2,000 (€3.05) | XOF 50,000 (€76.22) | XOF 40,000 (€60.98) | XOF 9,680,000 (€14,757.06), month 17 | XOF 5,208,750 (€7,940.69) |
| High | 50 | XOF 3,000 (€4.57) | XOF 150,000 (€228.67) | XOF 120,000 (€182.94) | XOF 8,843,750 (€13,482.21), month 16 | XOF 3,768,750 (€5,745.42) |

Even the base case reduces the modeled peak bridge need by only XOF 440,000 versus no sponsored placements; the high case reduces it by about XOF 1.28M. This can help supplement the budget, but it does **not** replace the need for financing. In the high case, monthly operating costs are covered in month 17 instead of month 18; the cumulative cash trough still occurs in month 16. Count these receipts in an actual forecast only after there are paid bookings, collected payments, and measured placement costs.

## 3. Evidence to collect: merchant growth

The assumption of **25 net new paying merchants per month after the pilot is unverified**. It is ambitious relative to an initial pilot of 5–10 merchants. Do not present it as a confirmed forecast or commitment.

| Assumption | Evidence to collect | Calculation or check | Current status |
|---|---|---|---|
| 5–10 outlets can join the pilot | Named outlet list, segment/corridor, written agreement, and onboarding date | Count outlets that are genuinely active, separately from leads | To confirm |
| Merchants will pay XOF 5,000–15,000/month | Accepted price, first invoice, and receipt for each outlet | Paid conversion = merchants who paid ÷ eligible active merchants | Unverified |
| Merchants renew | Receipts and invoices across consecutive months; cancellation reasons | Renewal and cancellation rates at 30/60/90 days | Unverified |
| Acquisition of 25 net new paying merchants/month | Monthly log of leads, demos, sign-ups, first payments, cancellations, and acquisition channel | New paying merchants less cancellations; also track cost per new paying merchant | Unverified |
| Growth can repeat beyond the first cohort | Results by corridor, segment, and channel over multiple periods | Require at least three consecutive months of observed results before using this rate in the base scenario | Unverified |

For every merchant, record contact date, referral source, acquisition cost, activation date, price actually paid, renewal dates, sales recorded, and reason for leaving if applicable. A free trial, unpaid registration, or letter of interest does not count as a paying merchant.

## 4. Evidence to collect: price and margin

The XOF 7,500/month average price and 90% margin are modeling assumptions, **not observed results**. Here, margin means that about XOF 6,750 remains from XOF 7,500 billed after costs directly caused by delivering the service, before monthly fixed costs.

| Assumption | Records and data needed | Check formula | Current status |
|---|---|---|---|
| Average price actually collected: XOF 7,500/month | Tested price list, invoices, receipts, discounts, and overdue days | Subscription cash collected ÷ paying merchants; calculate the average price actually received | Untested assumption |
| Paid sponsored-deal demand and price | Booking records for 7-day slots at XOF 1,000/2,000/3,000; invoices and receipts; placement-delivery record; direct staff/creative costs | Count placements both booked and paid per month; cash received less direct delivery cost. Do not count interest or uncollected invoices as revenue. | Untested pilot hypothesis |
| Margin after variable costs: 90% | OTP/SMS/WhatsApp invoices, variable cloud costs, payment fees paid by Djassa, variable commissions, and measured support time | (Cash revenue − directly attributable variable costs) ÷ cash revenue | Unverified |
| Notification cost is affordable | Local channel quotes and invoices; actual messages per outlet | Notification spend ÷ active outlets and ÷ useful messages delivered | To measure in pilot |
| Fixed costs remain near XOF 2M/month after pilot | Monthly contracts and invoices for team, hosting, accounting, travel, and tools | Total monthly recurring fixed costs, separate from variable costs | To confirm |

Do not count payment or lender commissions without a signed contract, confirmed receipt, valid consent, and regulatory clearance. Do not count money paid directly from a customer's wallet to a merchant as Djassa revenue.

### Monthly margin record

| Month / cohort | Active paying merchants | Subscription cash received (XOF) | Notifications and other variable costs (XOF) | Total variable cost (XOF) | Margin after variable costs | Data source |
|---|---:|---:|---:|---:|---:|---|
| To complete | To complete | To complete | To complete | To calculate | To calculate | Invoices + receipt register |

Formula: **margin after variable costs = (subscription cash received − variable costs) ÷ subscription cash received**. Track monthly and by cohort; do not substitute the 90% assumption for missing data.

## 5. Before sharing with a funder

1. Replace significant supplier allowances with dated, comparable, archived quotes; recalculate the total, applicable VAT, and contingency.
2. Update the forecast with actual payment dates, cash receipts, and required bridge funding; specify whether funding is a grant, equity, loan, or another instrument.
3. Attach anonymized pilot invoices and receipts, acquisition and renewal records, messaging quotes, and the monthly margin calculation.
4. Separate observed facts, supplier quotes, assumptions, and targets. Keep every unverified item clearly labeled.

## Plain-language definitions

- **Paid subscription month:** one merchant paying for one month counts as one.
- **Margin after variable costs:** what remains from the subscription after costs that rise with usage, before salaries and other fixed costs.
- **Cash need:** the money required to pay expenses before enough customer payments have arrived.