"""Checks the Orange SMS setup with the real credentials, before production.

    ORANGE_CLIENT_ID=... ORANGE_CLIENT_SECRET=... python scripts/orange_sms_check.py
    ... python scripts/orange_sms_check.py --send +2250701020304

Without --send: gets a token and prints the Côte d'Ivoire bundle (units left,
expiry). Costs nothing. With --send: also sends one test SMS to that number
through the same code the API uses (one unit of the bundle). Set
ORANGE_SENDER_NAME to test an approved sender name.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.otp_sender import ORANGE_API, OrangeSender  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--send", metavar="+225...", help="also send one test SMS to this number (E.164)")
    args = parser.parse_args()

    client_id, secret = os.getenv("ORANGE_CLIENT_ID"), os.getenv("ORANGE_CLIENT_SECRET")
    if not client_id or not secret:
        print("Set ORANGE_CLIENT_ID and ORANGE_CLIENT_SECRET (Orange Developer → My Apps → the app).")
        return 2
    sender = OrangeSender(client_id, secret, os.getenv("ORANGE_SENDER_NAME") or None)

    async with httpx.AsyncClient(base_url=ORANGE_API, timeout=10) as client:
        token = await sender._token(client)
        print("Token: OK")
        r = await client.get("/sms/admin/v1/contracts", params={"country": "CIV"},
                             headers={"Authorization": f"Bearer {token}"})
        if r.status_code != 200:
            print(f"Bundle: Orange answered {r.status_code}: {r.text[:200]}")
        else:
            contracts = r.json() if isinstance(r.json(), list) else [r.json()]
            if not contracts:
                print("Bundle: none. Buy one in My Apps before sending.")
            for c in contracts:
                print(f"Bundle: {c.get('availableUnits')} SMS left of {c.get('requestedUnits')}, "
                      f"{c.get('status')}, expires {c.get('expirationDate')}")

    if args.send:
        if not args.send.startswith("+225"):
            print("--send takes an Ivorian number in E.164, e.g. +2250701020304")
            return 2
        await sender.send(args.send, "Fidelia : SMS de test. Si vous le recevez, Orange est bien configure.")
        print(f"Test SMS: accepted by Orange for {args.send[:6]}****{args.send[-2:]}. Check the phone.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
