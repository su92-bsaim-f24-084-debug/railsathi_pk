"""Centralized audit logging module with recursive field redaction and transaction integration."""
import json
from datetime import datetime, date
from typing import Any
from flask import g, request, has_request_context
from app.extensions import db
from app.models.governance import AuditLog

# Sensitive keys that must always be masked in audit trail snapshots
SENSITIVE_KEYS = {
    "password",
    "password_hash",
    "raw_password",
    "confirm_password",
    "new_password",
    "current_password",
    "old_password",
    "token",
    "secret",
    "csrf_token",
    "cvv",
    "pin",
    "api_key",
}


def sanitize_audit_data(data: Any) -> Any:
    """Recursively mask sensitive values in dictionaries and lists."""
    if isinstance(data, dict):
        sanitized = {}
        for key, val in data.items():
            key_str = str(key).lower()
            if any(s in key_str for s in SENSITIVE_KEYS):
                sanitized[key] = "***REDACTED***"
            else:
                sanitized[key] = sanitize_audit_data(val)
        return sanitized
    elif isinstance(data, (list, tuple, set)):
        return [sanitize_audit_data(item) for item in data]
    elif isinstance(data, (datetime, date)):
        return data.isoformat()
    return data


def log_audit_event(
    action: str,
    entity_name: str,
    entity_id: str | int,
    user_id: int | None = None,
    old_values: dict | None = None,
    new_values: dict | None = None,
    ip_address: str | None = None,
) -> AuditLog | None:
    """Record an audit trail log in the current database session.
    
    Guarantees:
    1. Automatic redaction of passwords, tokens, and secrets.
    2. Recursion prevention guard against cascaded audit loops.
    3. Transaction integration: added to db.session so business changes and audit log
       commit or roll back together atomically in the same transaction.
    """
    # Recursion guard: never audit AuditLog itself
    if entity_name == "AuditLog":
        return None

    if has_request_context():
        if getattr(g, "in_audit_logging", False):
            return None
        g.in_audit_logging = True

    try:
        # Determine client IP address
        if ip_address is None and has_request_context():
            ip_address = request.headers.get("X-Forwarded-For", request.remote_addr)
            if ip_address and "," in ip_address:
                ip_address = ip_address.split(",")[0].strip()
            if ip_address:
                ip_address = ip_address[:45]

        # Sanitize and serialize values
        sanitized_old = None
        if old_values is not None:
            sanitized_old = json.dumps(sanitize_audit_data(old_values), default=str)

        sanitized_new = None
        if new_values is not None:
            sanitized_new = json.dumps(sanitize_audit_data(new_values), default=str)

        audit_entry = AuditLog(
            user_id=user_id,
            action=action[:50],
            entity_name=entity_name[:50],
            entity_id=str(entity_id)[:50],
            ip_address=ip_address,
            old_values=sanitized_old,
            new_values=sanitized_new,
        )
        db.session.add(audit_entry)
        return audit_entry
    finally:
        if has_request_context():
            g.in_audit_logging = False

