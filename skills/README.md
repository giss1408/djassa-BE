# Djassa Skills

This folder defines the project-specific skills and contributor instructions for Djassa. Use these files when planning, implementing, reviewing, researching, or documenting changes.

Structure:

- `research.md`, `writing.md`, `translation.md`, `technical.md` — research, writing, localization, and reproducibility.
- `implementation/` — implementation guidance and templates:
	- `implementation/backend.md`
	- `implementation/frontend.md`
	- `templates/` — reusable templates for API endpoints and UI components.

Add new skills or templates here to keep implementation guidance centralized and discoverable.

Usage: reference these skill files when assigning tasks, opening issues, or preparing prompts for contributors and automation.

## Required reading by task

| Task | Read |
|---|---|
| Backend endpoint or data change | `implementation/backend.md`, `templates/api-endpoint-template.md` |
| Frontend or mobile workflow | `implementation/frontend.md`, `templates/component-template.md` |
| Country or language change | `translation.md`, `technical.md` |
| Architecture or deployment | `technical.md`, `../Architecture/README.md` |
| Product or partner research | `research.md`, `writing.md` |

## Project principles

- Design for intermittent connectivity and expensive data.
- Derive ownership from authenticated identity, never request-body identity.
- Use migrations for schema changes and add negative authorization tests.
- Keep country rules and provider integrations behind configuration/adapters.
- Treat English as the technical documentation language; retain French product research where it is the source context.
