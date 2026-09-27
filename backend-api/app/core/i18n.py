MESSAGES = {
    "support_received": {
        "en": "Your support request has been received.",
        "fr": "Votre demande d'assistance a bien ete recue.",
    },
}


def message(key: str, language: str) -> str:
    translations = MESSAGES.get(key, {})
    return translations.get(language, translations.get("en", key))
