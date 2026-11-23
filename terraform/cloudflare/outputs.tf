output "api_urls" {
  description = "Put these in the apps and the installer site (VITE_FIDELIA_API_BASE, build-release.sh)."
  value       = { for name, e in var.environments : name => "https://${e.api_hostname}" }
}

output "media_base_urls" {
  description = "MEDIA_PUBLIC_BASE_URL for the API and the worker of each environment."
  value       = { for name, m in local.media : name => "https://${m.hostname}" }
}
