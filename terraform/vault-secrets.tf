provider "vault" {
  address = var.vault_addr
  token   = var.vault_token
}

resource "vault_policy" "hossouko_read" {
  name   = "hossouko-read"
  policy = file("../vault/demo-policy.hcl")
}

resource "vault_generic_secret" "hossouko_database" {
  path = "secret/data/hossouko/database"
  data_json = jsonencode({
    url = var.database_url
  })
}

resource "vault_generic_secret" "hossouko_mobile_money" {
  path = "secret/data/hossouko/mobile_money"
  data_json = jsonencode({
    secret = var.mobile_money_secret
  })
}
