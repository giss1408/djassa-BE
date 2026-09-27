# API Endpoint Template

Title: <HTTP VERB> <path>

Summary: One-sentence summary of the endpoint purpose.

Status: Implemented / Partial / Target

Request:
- Path: 
- Method: 
- Query params:
- Body schema (JSON):
- Authentication and ownership rule:
- Idempotency/retry behavior:
- Country/language behavior, if applicable:

Response (200):
- Body schema (JSON):

Errors:
- 400: validation error
- 401: unauthorized
- 403: ownership or role denied
- 409: idempotency or state conflict
- 422: supported-country/language/channel validation error
- 500: internal error

Tests:
- unit test outline
- integration test outline
- unauthorized and cross-user test outline
- retry/duplicate request test outline

Migration/Schema changes:
- table changes, migrations needed
