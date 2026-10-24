"""WhatsApp message links.

The team sends codes by hand: the admin app opens this link, WhatsApp shows the
message already written, and the admin taps Send. Moving to the WhatsApp Cloud
API later means changing only this function.
"""

from urllib.parse import quote


def whatsapp_link(e164: str, message: str) -> str:
    return f"https://wa.me/{e164.lstrip('+')}?text={quote(message, safe='')}"
