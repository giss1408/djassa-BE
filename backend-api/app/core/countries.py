from dataclasses import asdict, dataclass
from typing import Dict


@dataclass(frozen=True)
class CountryProfile:
    code: str
    name: str
    currency: str
    phone_prefixes: tuple[str, ...]
    languages: tuple[str, ...]
    support_channels: tuple[str, ...]
    payment_providers: tuple[str, ...]


COUNTRIES: Dict[str, CountryProfile] = {
    "CI": CountryProfile(
        code="CI",
        name="Cote d'Ivoire",
        currency="XOF",
        phone_prefixes=("+225",),
        languages=("fr", "dioula"),
        support_channels=("whatsapp", "sms", "phone"),
        payment_providers=("orange_money_ci", "wave_ci", "mtn_momo_ci", "moov_money_ci"),
    ),
    "GH": CountryProfile(
        code="GH",
        name="Ghana",
        currency="GHS",
        phone_prefixes=("+233",),
        languages=("en", "tw", "ee", "ga"),
        support_channels=("whatsapp", "sms", "phone"),
        payment_providers=("mtn_momo_gh", "vodafone_cash_gh", "airteltigo_money_gh"),
    ),
    "NG": CountryProfile(
        code="NG",
        name="Nigeria",
        currency="NGN",
        phone_prefixes=("+234",),
        languages=("en", "ha", "yo", "ig"),
        support_channels=("whatsapp", "sms", "phone"),
        payment_providers=("opay_ng", "paga_ng", "moniepoint_ng"),
    ),
    "KE": CountryProfile(
        code="KE",
        name="Kenya",
        currency="KES",
        phone_prefixes=("+254",),
        languages=("en", "sw"),
        support_channels=("whatsapp", "sms", "phone"),
        payment_providers=("mpesa_ke", "airtel_money_ke"),
    ),
}


def get_country(code: str) -> CountryProfile | None:
    return COUNTRIES.get(code.upper())


def country_dict(profile: CountryProfile) -> dict:
    return asdict(profile)
