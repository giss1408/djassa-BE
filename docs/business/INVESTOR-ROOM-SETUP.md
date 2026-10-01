# Djassa — Investor Room Setup

*Implementation and operations guide · 1 October 2026*

The investor room is an invite-only page at `/investor`, backed by Supabase Auth, Postgres Row Level Security (RLS), and a **private** Storage bucket. The website contains only the interface. Documents and financial chart values are fetched after successful sign-in and MFA. The Supabase service-role key must never be put in the website, build variables, or browser.

## Security boundaries

- Supabase Auth accounts are created by an administrator; public sign-up is disabled.
- TOTP multi-factor authentication is mandatory. Database functions and every investor read policy require the JWT assurance level `aal2`, an active membership row, and document-specific permission where applicable.
- Files are stored in the private `investor-room` bucket. RLS checks the user's active membership, MFA, document permission, and exact storage path on each download.
- Document reviews are private to the investor. The checkboxes mean “reviewed”, “discuss with Djassa”, and “include in my local download pack”; they are not signatures, agreement to terms, or legal acceptance.
- Sessions are kept in memory only. Refreshing the page requires sign-in again. Use HTTPS and do not test with real investor documents until the project is configured and policies have been verified.
- This is access control, not DRM: an authorized investor can save a document after download. Share only approved files and use a signed NDA where appropriate.

## Configure Supabase

1. Create a dedicated Supabase project for the investor room. Do not reuse the Djassa demo-app login or its demo credentials.
2. In Authentication settings, disable public sign-ups. Configure SMTP and the site URL / redirect allowlist for `https://djassa.co/investor.html` and local development at `http://localhost:5173/investor.html`.
3. Keep MFA enrollment available. The page enrolls a TOTP authenticator on first access and verifies it on later sign-ins. The SQL policies enforce `aal2`, so a password-only session cannot read room data even if the UI is bypassed.
4. Run [`../../scripts/investor-room-schema.sql`](../../scripts/investor-room-schema.sql) in the Supabase SQL editor as project owner. Confirm the `investor-room` bucket is private.
5. Create investor accounts using the Supabase Auth admin invitation flow. Do not expose an account-creation endpoint on the public website.
6. For each invited account, insert one active row in `investor_room_members`, then insert one `investor_room_permissions` row for every document that investor may see. Access is denied unless both membership and document permission are active.
7. Upload each approved file to the private bucket. Insert matching metadata in `investor_room_documents`; `storage_path` must exactly match the uploaded object path. Start with non-sensitive test files and test with two accounts that have different permissions.
8. Insert approved chart values in `investor_room_metrics`. Values are not seeded in the frontend or repository. Mark assumptions as assumptions in labels/notes, and do not publish draft values as verified results.

Example administrative SQL (run only after inviting the user and uploading the file):

```sql
insert into public.investor_room_members (user_id, display_name, organization, active)
values ('SUPABASE_AUTH_USER_UUID', 'Investor name', 'Organization', true);

insert into public.investor_room_documents
    (title, description, category, version, file_name, storage_path, required, sort_order, active)
values
    ('Investor brief', 'Approved overview', 'Overview', '2026-10', 'investor-brief.pdf', 'approved/investor-brief.pdf', true, 10, true)
returning id;

insert into public.investor_room_permissions (user_id, document_id, active)
values ('SUPABASE_AUTH_USER_UUID', 'RETURNED_DOCUMENT_UUID', true);

insert into public.investor_room_metrics (section_key, label, numeric_value, currency, note, sort_order, active)
values ('Launch budget', 'Six-month funding envelope', 30820000, 'XOF', 'Planning estimate; supplier quotes pending.', 10, true);
```

Use the SQL editor/dashboard for membership, permissions, document metadata, and chart data. Do not grant investors write access to these tables or share the service-role key.

## Configure the website

Set these **build-time** variables on the Render static-site service and in a local, untracked `djassa-Web/.env.local` for development:

```text
VITE_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
VITE_SUPABASE_ANON_KEY=YOUR_SUPABASE_PUBLISHABLE_OR_ANON_KEY
```

The anon/publishable key is expected to be visible in the browser; it is safe only because RLS is enabled and verified. **Never use `SUPABASE_SERVICE_ROLE_KEY` or any secret key in a `VITE_` variable.** After configuring variables in Render, trigger a fresh build. The room stays in a “not configured” state until both values exist.

The static-site configuration marks `/investor.html` `no-store`, `noindex`, and `no-referrer`; `/investor` rewrites to this separate HTML entry. Its interface is excluded from service-worker offline caching. Do not put private files in `public/`, `src/`, or any static website directory.

## Release checks

Before inviting real investors:

- Test an unauthenticated browser: documents, metrics, reviews, and Storage objects must return no data.
- Test an authenticated password-only session: all protected tables and files must remain inaccessible until TOTP verification produces `aal2`.
- Test investor A and investor B with different document permissions; each must see/download only assigned files, and cannot read or change the other's checklist.
- Revoke a member and a document permission; confirm access is denied immediately on subsequent requests.
- Confirm public sign-up is disabled, SMTP delivery works, the invitation redirect is correct, and rate limits/abuse protection are configured in Supabase Auth.
- Confirm the Supabase service-role key is absent from the web bundle, Render static environment, Git, and browser requests.
- Upload only approved, appropriately redacted versions. Obtain local legal review for NDA wording and electronic-signature requirements; the checklist is not a signature.

The browser-generated ZIP contains only documents currently assigned to the signed-in investor and selected by that investor. It is generated locally from authorized downloads; no archive is uploaded back to Djassa.