# Djassa Documentation

> **Djassa turns everyday sales at neighbourhood shops into proof: a verified business history that the merchant owns and, with consent, can take to a licensed lender.**

## Business: what Djassa is and why it will work

| Document | Answers |
|---|---|
| [Concept](business/CONCEPT.md) | What Djassa is, the one-habit idea, the four products, how money moves, identity, the financial-inclusion path, **how to explain it to each audience**, red lines. *Start here.* |
| [Market](business/MARKET.md) | Sourced figures, regulation (BCEAO, PISPI, ARTCI), competitive landscape and positioning, tontine and SME finance evidence. |
| [Business model](business/BUSINESS-MODEL.md) | Who pays, revenue streams in order, pricing experiment, unit economics, decision gates. |
| [Roadmap](business/ROADMAP.md) | Where we stand today, phases 0–6 with exit gates, strategic horizon. |
| [Partners](business/PARTNERS.md) | Institution directory, contact order, acquisition channels, meeting kit, guardrails. |

## Planning: reviews and action plans

| Document | Answers |
|---|---|
| [Concept review and optimization proposals](planning/optimization_claude_djassa.md) | Independent review of the concept as documented and as implemented, revenue options, optimization proposals. Written before the Wave-first revenue decision; where they differ, [Business model](business/BUSINESS-MODEL.md) wins. |
| [Implementation action plan](planning/action_plan_claude_djassa.md) | Ordered workstreams, per-step file changes, test criteria, decision gates and sequencing for the review's findings. |

## Technical: how it is built and run

| Document | Answers |
|---|---|
| [Technical guide](technical/TECHNICAL-GUIDE.md) | Repository map, local development, sync, payments, identity API, configuration, production gaps. |
| [VPS test server](technical/VPS-TEST-SERVER.md) | Ubuntu VPS setup and automated test deployment. |
| [Architecture](../Architecture/README.md) | Topology, application and container security, secrets, Kubernetes. |
| [Contributing](../CONTRIBUTING.md) | Branches, tests, security checklist, pull requests. |
| [Monitoring alerts](../monitoring/ALERTS.md) | Operational thresholds and access rules. |

App-specific docs live with each app: [merchant app architecture](../../djassa-App-retailer/ARCHITECTURE.md), [public site](../../djassa-Web/README.md).

## Reading paths by audience

| You are… | Read |
|---|---|
| **A merchant or user-facing team member** | Concept §§ 3–6 and § 9 |
| **An investor** | Concept → Market → Business model → Roadmap |
| **An institution or regulator** | Concept §§ 6–8 and § 11 → Market § 4 → Roadmap |
| **A financial or payment partner** | Concept §§ 3, 6 and 9 → Business model → Partners |
| **A developer** | Concept → Roadmap § Where we stand → Technical guide |

## Keeping documents in sync

- These business documents are the **source of truth**. The public site copy (`djassa-Web/src/content/fr.js` and `en.js`) and app wording must follow them.
- The roadmap's "Where we stand" table must be updated when a capability ships or a gate is passed.
- Market figures always carry their source and must be re-verified before external or contractual use.
- The original French research and the "Dkassa" instruction notes were consolidated into these documents on 30 September 2026. The originals remain in git history.
