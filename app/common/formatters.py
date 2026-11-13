"""Formatting and normalization utilities for RailSathi PK."""
import re


def normalize_phone_number(raw_phone: str) -> str:
    """Normalize Pakistani phone numbers to canonical 03XX-XXXXXXX format.
    
    Accepts:
    - 03001234567 -> 0300-1234567
    - 0300-1234567 -> 0300-1234567
    - +923001234567 -> 0300-1234567
    - +92-300-1234567 -> 0300-1234567
    - +92 300 1234567 -> 0300-1234567
    """
    if not raw_phone:
        return ""
    digits = re.sub(r"\D", "", raw_phone)
    if digits.startswith("92") and len(digits) == 12:
        digits = "0" + digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        pass
    elif len(digits) == 10 and digits.startswith("3"):
        digits = "0" + digits

    if len(digits) == 11 and digits.startswith("03"):
        return f"{digits[:4]}-{digits[4:]}"
    return raw_phone.strip()

