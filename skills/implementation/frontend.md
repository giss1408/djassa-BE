# Skill: Implementation — Frontend

Purpose: implement user-facing frontend components, pages, and interactions with accessibility and responsive design in mind.

When to use:
- Building web UI, dashboards, merchant tools, mobile/PWA workflows, support screens, and client-side synchronization for Djassa.

Recommended guidance:
- Use the frontend framework already selected by the product; do not add a second framework without a decision record.
- Prefer TypeScript, semantic HTML, accessible forms, and a small dependency footprint.
- Use a service worker or platform storage for offline queues where supported.
- Keep server state separate from local pending operations.
- Use the backend country configuration endpoint instead of hard-coded country/provider rules.
- Route support requests with country code, language, channel, and category metadata.

Key deliverables:
- Small component library and storybook-like examples (or docs) for shared components.
- Accessible forms and validation with clear error states.
- Integration examples showing API calls to backend endpoints with mock server or MSW.
- Offline queue with visible `pending`, `synced`, and `failed` states.
- Retry-safe calls using a stable `Idempotency-Key` per operation.
- Low-bandwidth mode with compressed assets, pagination, lazy loading, and no unnecessary polling.

Prompt patterns:
- Task: "Create an offline-capable transaction form that stores pending operations locally, syncs through `/api/transactions/sync`, preserves idempotency keys across retries, and shows accepted, already-processed, and rejected results."

Contributor notes:
- Include design tokens and breakpoints in a central file. Write clear props documentation.
- Design for low-end devices and intermittent connectivity first.
- Keep the primary merchant action usable in a few taps and with minimal data transfer.
- Never discard a pending operation silently; explain failures and allow retry or correction.
- Test offline, slow-network, duplicate-submit, reconnect, and partial-sync states.
