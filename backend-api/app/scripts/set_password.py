"""Gives an existing account a password: how the first admin gets in.

    python -m app.scripts.set_password +2250700000000

The number must already exist (grant the admin role first). The script asks
for the password twice, refuses weak ones, marks the number verified, and
clears the forced change and any lockout.
"""

import asyncio
import getpass
import sys

from sqlalchemy import select

from app import models
from app.api.auth import utcnow
from app.core import passwords
from app.core.phone import InvalidPhone, normalize_phone
from app.db import AsyncSessionLocal


async def run(argv, input=getpass.getpass) -> int:
    if len(argv) != 1:
        print("Usage : python -m app.scripts.set_password +225XXXXXXXXXX")
        return 2
    try:
        phone = normalize_phone(argv[0], "CI")
    except InvalidPhone as exc:
        print(exc)
        return 1

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(models.User).where(models.User.phone_e164 == phone))).scalar_one_or_none()
        if user is None:
            print("Numero inconnu. Accordez d'abord le role admin.")
            return 1
        first = input("Mot de passe : ")
        if first != input("Confirmez le mot de passe : "):
            print("Les deux mots de passe different.")
            return 1
        try:
            passwords.check_rules(first)
        except ValueError as exc:
            print(exc)
            return 1
        user.password_hash = passwords.hash_password(first)
        user.phone_verified_at = utcnow()
        user.must_change_password = False
        user.failed_logins = 0
        user.locked_until = None
        await db.commit()
    print("Mot de passe enregistre.")
    return 0


def main(argv=None, input=getpass.getpass) -> int:
    return asyncio.run(run(sys.argv[1:] if argv is None else argv, input=input))


if __name__ == "__main__":
    sys.exit(main())
