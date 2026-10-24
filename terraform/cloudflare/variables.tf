variable "account_id" {
  description = "Cloudflare account ID (dashboard → any domain → Overview, right column)."
  type        = string
}

variable "zone_id" {
  description = "Zone ID of the Fidelia domain (same place)."
  type        = string
}

variable "environments" {
  description = <<-EOT
    Every Fidelia environment served through this zone, by name (e.g. prod,
    test). They share one configuration because Cloudflare allows one ruleset
    per phase per zone: two separate states would overwrite each other's rules.
  EOT
  type = map(object({
    # The public API hostname, e.g. api.example.ci.
    api_hostname = string
    # The Render service's own address, the CNAME target Render shows under
    # Settings → Custom Domains, e.g. fidelia-api-prod.onrender.com.
    render_hostname = string
    # false until Render shows the custom domain verified with a certificate
    # (PRODUCTION.md § 3, step 1), then true.
    proxied = optional(bool, true)
    # Shop media on R2 under its own hostname. Leave out for an environment
    # whose media stays on the r2.dev address.
    media = optional(object({
      hostname = string
      bucket   = string
      # "eu" for production (ARTCI.md § 4). Fixed when the bucket is created.
      jurisdiction = optional(string, "eu")
      # false when the bucket already exists and is not managed here.
      create_bucket = optional(bool, true)
    }))
  }))

  validation {
    condition     = alltrue([for e in values(var.environments) : !endswith(e.render_hostname, var.zone_name)])
    error_message = "render_hostname is the onrender.com address, not a hostname in this zone."
  }
}

variable "zone_name" {
  description = "The domain itself, e.g. example.ci. Only used to catch a render_hostname typed as the public one."
  type        = string
}

variable "origin_secrets" {
  description = <<-EOT
    The API's CLOUDFLARE_ORIGIN_SECRET for each environment, by the same names
    as `environments` (`openssl rand -hex 32`, also set on the API in Render). Every
    environment behind Cloudflare needs one, and the API must have it set:
    without it the API would count all callers as a handful of Cloudflare
    addresses and rate-limit them together.
  EOT
  type        = map(string)
  sensitive   = true

  validation {
    condition     = alltrue([for name in keys(var.environments) : length(lookup(var.origin_secrets, name, "")) >= 32])
    error_message = "origin_secrets needs a value of at least 32 characters for every environment (the API's CLOUDFLARE_ORIGIN_SECRET)."
  }
}

variable "login_rate_limit" {
  description = "Sign-in, sign-up and password-reset requests allowed per IP per 10 seconds at the edge, before the API's own limits."
  type        = number
  default     = 5
}
