# Skill: Translation & Localization

Purpose: translate and localize product, technical, support, and partner content while preserving meaning and cultural context.

When to use:
- Translating finished drafts, UI text, or outreach materials.
- Preparing support messages and help content for a country profile.

Guidelines:
- Prefer natural-sounding translations over literal word-for-word conversions.
- Note culturally-specific terms and suggest localized alternatives.
- Preserve variables, identifiers, API paths, currency codes, and placeholders exactly.
- Do not translate regulated product names, provider identifiers, or country codes without a glossary decision.
- Distinguish translated copy from a fallback language; never imply a translation exists when it has not been reviewed.
- Keep the user's selected country and language metadata available for support routing.

Prompt pattern:
- Task: "Localize the following <source language> text for <country/language/channel>, preserve variables and meaning, and list terms requiring native-speaker review."

Contributor notes:
- Include source text, localized text, language, country, channel, reviewer status, and date.
- Technical documentation remains English-first; product source research may remain French with an English decision summary.
