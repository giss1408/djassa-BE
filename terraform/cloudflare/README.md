# Cloudflare in front of Fidelia

What [PRODUCTION.md § 3](https://github.com/giss1408/fidelia-docs/blob/main/docs/technical/PRODUCTION.md#3-cloudflare-in-front)
describes, as Terraform: TLS settings, the API hostnames, the origin-secret
header, cache rules, the webhook skip rule, the `/incoming/` block, the edge
rate limit on sign-in codes, and the R2 media bucket with its domain and
lifecycle rule.

All environments on the domain (production, and test if it goes behind
Cloudflare) live in **one** configuration: Cloudflare allows one ruleset per
phase per zone, so two states would overwrite each other's rules.

## What you need

1. The domain already added to Cloudflare, its nameservers switched at the
   registrar.
2. An API token (*My Profile → API Tokens → Create Token → Custom*), limited
   to this account and zone:
   * Zone → Zone Settings: Edit · DNS: Edit · Zone WAF: Edit ·
     Transform Rules: Edit · Cache Rules: Edit
   * Account → Workers R2 Storage: Edit

   A 403 during `apply` names the missing permission.
3. The API's `CLOUDFLARE_ORIGIN_SECRET` for each environment (Render → the API
   service → Environment).

Terraform does not need to be installed; the commands below run it in Docker.

```bash
cd terraform/cloudflare
alias tf='docker run --rm -it -v "$PWD:/w" -w /w -e CLOUDFLARE_API_TOKEN -e TF_VAR_origin_secrets hashicorp/terraform:1.9.8'
```

## First apply

```bash
cp terraform.tfvars.example terraform.tfvars   # fill in IDs and hostnames
export CLOUDFLARE_API_TOKEN=...
export TF_VAR_origin_secrets='{"prod":"<the API'"'"'s CLOUDFLARE_ORIGIN_SECRET>"}'
tf init
tf plan      # read it: 12 resources for prod alone
tf apply
```

1. Apply with `proxied = false`: Render must see its own CNAME to verify the
   custom domain and issue a certificate.
2. When Render → fidelia-api-prod → *Custom Domains* shows **Verified** and the
   certificate, set `proxied = true` and apply again.
3. Set `MEDIA_PUBLIC_BASE_URL` on the API and the worker to the
   `media_base_urls` output, and the installer site's `VITE_FIDELIA_API_BASE`
   to the `api_urls` output.
4. Check (PRODUCTION.md § 3, step 9): the onrender.com address answers 403,
   `https://api.<domain>` answers 200, a test Wave payment is confirmed.

Not managed here: **Bot Fight Mode** (*Security → Bots*) must stay **off**. On
the Free plan it cannot be skipped for the webhook paths and would challenge
Wave's servers.

## Things to know

* **The state holds the origin secrets** (inside the transform rule). It is
  kept locally and ignored by git; do not commit it or paste it anywhere. Keep
  a copy in the password manager, or move it to an encrypted remote backend.
* **Rules created by hand first.** If someone already added custom, cache,
  transform or rate-limiting rules in the dashboard, the zone already has that
  phase's ruleset and `apply` fails. Delete them in the dashboard (this
  configuration recreates what is needed), or import the ruleset.
* **An existing bucket.** Set `create_bucket = false` for it; the domain and
  lifecycle rule are still managed. The bucket itself has `prevent_destroy`:
  deleting it deletes every shop's media.
* **Zone settings** (TLS) stay as set even after `destroy`; Cloudflare has no
  "unset" for them.
* **Rotating the origin secret**: set `new,old` in the API's
  `CLOUDFLARE_ORIGIN_SECRET` and deploy, apply here with `new`, then set `new`
  alone on the API.
* **Putting test behind Cloudflare**: give the test API its own
  `CLOUDFLARE_ORIGIN_SECRET` first, then add a `test` entry to `environments`
  and to `origin_secrets`. Behind Cloudflare without the secret, the API would
  see every caller as one of a few Cloudflare addresses and rate-limit them
  together.
