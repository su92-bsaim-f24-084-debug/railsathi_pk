import random
import string
import secrets


def generate_pnr() -> str:
    """
    Generates a unique 10-character alphanumeric PNR for railway bookings.
    Format: 3 letters + 7 uppercase alphanumeric digits (e.g. PR9X7K2M4P).
    """
    prefix = "PR"
    body = "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"{prefix}{body}"


def generate_ticket_token() -> str:
    """
    Generates a secure 32-byte (43-char URL-safe base64) cryptographic token
    used to verify tickets via the digital QR code.
    """
    return secrets.token_urlsafe(32)

