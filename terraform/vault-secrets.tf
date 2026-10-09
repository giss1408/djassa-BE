provider "vault" {
  address = var.vault_addr
  token   = var.vault_token
}

resource "vault_policy" "fidelia_read" {
  name   = "fidelia-read"
  policy = file("../vault/demo-policy.hcl")
}

resource "vault_generic_secret" "fidelia_database" {
  path = "secret/data/fidelia/database"
  data_json = jsonencode({
    url = var.database_url
  })
}

resource "vault_generic_secret" "fidelia_mobile_money" {
  path = "secret/data/fidelia/mobile_money"
  data_json = jsonencode({
    secret = var.mobile_money_secret
  })
}
