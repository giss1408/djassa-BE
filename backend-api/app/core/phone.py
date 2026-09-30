"""Customer phone numbers, as typed at a counter.

A merchant types what the customer says: "07 12 34 56 78", "0712345678",
"+225 07 12 34 56 78". Loyalty points are keyed on the number, so every form of
the same number must land on the same key, and anything that is not a number
must be refused rather than stored as a second, unreachable customer.

Côte d'Ivoire has used ten-digit national numbers since 2021 (E.164:
`+225` followed by ten digits). Other countries accept only the full
international form, checked against the country's prefixes in
`app/core/countries.py`, until someone who knows their local formats adds them.
"""

import re

from .countries import get_country

_SEPARATORS = re.compile(r"[\s.\-()/]")

# Keyed customer ids live in the same column as account usernames
# (`loyalty_entries.customer_id`), so they are namespaced: a username can never
# look like a phone key, and a phone key can never be mistaken for a login.
PHONE_KEY_PREFIX = "tel:"


class InvalidPhone(ValueError):
    pass


def normalize_phone(raw: str, country_code: str = "CI") -> str:
    """Return the E.164 form of `raw`, or raise `InvalidPhone`."""
    digits = _SEPARATORS.sub("", raw or "")
    if digits.startswith("00"):
        digits = "+" + digits[2:]

    if country_code.upper() == "CI":
        if re.fullmatch(r"\+225\d{10}", digits):
            return digits
        if re.fullmatch(r"0\d{9}", digits):
            return "+225" + digits
        raise InvalidPhone("Numero ivoirien attendu : 10 chiffres, par ex. 07 12 34 56 78")

    country = get_country(country_code)
    if country is None:
        raise InvalidPhone("Pays non pris en charge")
    if re.fullmatch(r"\+[1-9]\d{7,14}", digits) and digits.startswith(country.phone_prefixes):
        return digits
    raise InvalidPhone("Numero international attendu, par ex. " + country.phone_prefixes[0] + "...")


def phone_key(e164: str) -> str:
    return PHONE_KEY_PREFIX + e164


def mask_phone(e164: str) -> str:
    """"+2250712345678" -> "07 •• •• 56 78": enough for the merchant to confirm
    they typed the right number, without the full number travelling back into
    every response and log line."""
    national = e164[4:] if e164.startswith("+225") else e164
    if len(national) < 6:
        return "••••"
    pairs = [national[i : i + 2] for i in range(0, len(national), 2)]
    return " ".join([pairs[0]] + ["••"] * (len(pairs) - 3) + pairs[-2:])
