# UI Component Template

Name: <ComponentName>

Purpose: Short description.

Props:
- `propName: type` — description

Behavior:
- What the component does, states, events.
- Offline states: pending, syncing, synced, failed, retrying.
- Low-bandwidth behavior: payload size, lazy loading, polling policy.
- Country/language behavior: configuration source, fallback language, channel.

Accessibility:
- ARIA roles, keyboard behavior.

Testing:
- Unit tests to assert rendering and behavior.
- E2E flows to exercise component in real scenarios.
- Offline/reconnect and duplicate-submit tests.

Story/Example:
- Minimal usage example.
