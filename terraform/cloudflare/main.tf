# Cloudflare in front of the Fidelia API: what PRODUCTION.md § 3 describes,
# applied from here instead of clicked in the dashboard. README.md says how.

provider "cloudflare" {
  # Reads CLOUDFLARE_API_TOKEN from the environment (README.md: permissions).
}

locals {
  api_hosts   = sort([for e in values(var.environments) : e.api_hostname])
  media       = { for name, e in var.environments : name => e.media if e.media != null }
  media_hosts = sort([for m in values(local.media) : m.hostname])

  api_host_set   = join(" ", [for h in local.api_hosts : format("%q", h)])
  media_host_set = join(" ", [for h in local.media_hosts : format("%q", h)])
}

# --- TLS -------------------------------------------------------------------

# Full (strict): Cloudflare to Render is encrypted and Render's certificate
# checked, so nobody between the two can read or change traffic.
resource "cloudflare_zone_setting" "ssl" {
  zone_id    = var.zone_id
  setting_id = "ssl"
  value      = "strict"
}

resource "cloudflare_zone_setting" "always_use_https" {
  zone_id    = var.zone_id
  setting_id = "always_use_https"
  value      = "on"
}

resource "cloudflare_zone_setting" "min_tls_version" {
  zone_id    = var.zone_id
  setting_id = "min_tls_version"
  value      = "1.2"
}

# --- API hostnames ---------------------------------------------------------

resource "cloudflare_dns_record" "api" {
  for_each = var.environments

  zone_id = var.zone_id
  name    = each.value.api_hostname
  type    = "CNAME"
  content = each.value.render_hostname
  proxied = each.value.proxied
  ttl     = 1 # automatic
  comment = "Fidelia API (${each.key}), Render. Managed by terraform/cloudflare."
}

# Adds Cloudflare's proof of passage to every request it forwards to the API
# (backend-api/app/edge.py). "set" replaces whatever a caller sent.
resource "cloudflare_ruleset" "origin_secret" {
  zone_id = var.zone_id
  name    = "Fidelia origin secret"
  kind    = "zone"
  phase   = "http_request_late_transform"

  rules = [for name, e in var.environments : {
    ref         = "fidelia_origin_secret_${name}"
    description = "X-Origin-Auth for ${e.api_hostname}"
    expression  = "(http.host eq \"${e.api_hostname}\")"
    action      = "rewrite"
    action_parameters = {
      headers = {
        "X-Origin-Auth" = {
          operation = "set"
          value     = var.origin_secrets[name]
        }
      }
    }
  }]
}

# --- Cache -----------------------------------------------------------------

resource "cloudflare_ruleset" "cache" {
  zone_id = var.zone_id
  name    = "Fidelia cache"
  kind    = "zone"
  phase   = "http_request_cache_settings"

  rules = concat(
    [{
      ref               = "fidelia_api_no_cache"
      description       = "API answers are personal: never cached"
      expression        = "(http.host in {${local.api_host_set}})"
      action            = "set_cache_settings"
      action_parameters = { cache = false }
    }],
    length(local.media_hosts) == 0 ? [] : [{
      ref               = "fidelia_media_cache"
      description       = "Media files never change once written (one-year immutable Cache-Control)"
      expression        = "(http.host in {${local.media_host_set}})"
      action            = "set_cache_settings"
      action_parameters = { cache = true }
    }],
  )
}

# --- WAF -------------------------------------------------------------------

# Leave Bot Fight Mode off (Security → Bots): on the Free plan it cannot be
# skipped per path, and it would challenge Wave's servers.
resource "cloudflare_ruleset" "firewall" {
  zone_id = var.zone_id
  name    = "Fidelia firewall"
  kind    = "zone"
  phase   = "http_request_firewall_custom"

  rules = concat(
    [{
      ref         = "fidelia_webhooks_pass"
      description = "Provider callbacks (Wave payments, Orange SMS receipts): no challenge, no edge rate limit (protected by their token or signature)"
      expression  = "(http.host in {${local.api_host_set}} and (starts_with(http.request.uri.path, \"/webhooks/wave/\") or starts_with(http.request.uri.path, \"/webhooks/orange/\") or http.request.uri.path eq \"/api/webhooks/mobile-money\"))"
      action      = "skip"
      action_parameters = {
        ruleset = "current"
        phases  = ["http_ratelimit", "http_request_firewall_managed"]
      }
      logging = { enabled = true }
    }],
    length(local.media_hosts) == 0 ? [] : [{
      ref         = "fidelia_block_incoming"
      description = "Originals waiting for the video worker (GPS included) are never served"
      expression  = "(http.host in {${local.media_host_set}} and starts_with(http.request.uri.path, \"/incoming/\"))"
      action      = "block"
    }],
  )
}

# The Free plan allows one rate-limiting rule, a 10-second period, and counts
# per IP and Cloudflare data centre.
resource "cloudflare_ruleset" "rate_limit" {
  zone_id = var.zone_id
  name    = "Fidelia rate limits"
  kind    = "zone"
  phase   = "http_ratelimit"

  rules = [{
    ref         = "fidelia_otp_request"
    description = "Sign-in codes: each one is an SMS paid for"
    expression  = "(http.host in {${local.api_host_set}} and http.request.uri.path eq \"/api/auth/otp/request\")"
    action      = "block"
    ratelimit = {
      characteristics     = ["cf.colo.id", "ip.src"]
      period              = 10
      requests_per_period = var.otp_rate_limit
      mitigation_timeout  = 10
    }
  }]
}

# --- Media on R2 -----------------------------------------------------------

resource "cloudflare_r2_bucket" "media" {
  for_each = { for name, m in local.media : name => m if m.create_bucket }

  account_id   = var.account_id
  name         = each.value.bucket
  jurisdiction = each.value.jurisdiction

  lifecycle {
    # Deleting the bucket deletes every shop's photos and videos.
    prevent_destroy = true
  }
}

resource "cloudflare_r2_custom_domain" "media" {
  for_each = local.media

  account_id   = var.account_id
  zone_id      = var.zone_id
  bucket_name  = each.value.bucket
  jurisdiction = each.value.jurisdiction
  domain       = each.value.hostname
  enabled      = true
  min_tls      = "1.2"

  depends_on = [cloudflare_r2_bucket.media]
}

# Staged originals (backend-api/app/services/media_jobs.py) are deleted by the
# worker within minutes; this catches any a crash left behind.
resource "cloudflare_r2_bucket_lifecycle" "media" {
  for_each = local.media

  account_id   = var.account_id
  bucket_name  = each.value.bucket
  jurisdiction = each.value.jurisdiction

  rules = [{
    id         = "expire-incoming"
    enabled    = true
    conditions = { prefix = "incoming/" }
    delete_objects_transition = {
      condition = { type = "Age", max_age = 86400 }
    }
    abort_multipart_uploads_transition = {
      condition = { type = "Age", max_age = 86400 }
    }
  }]

  depends_on = [cloudflare_r2_bucket.media]
}
