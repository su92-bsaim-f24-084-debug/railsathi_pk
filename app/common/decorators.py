"""Security decorators and redirect validators for RailSathi PK."""
from functools import wraps
from urllib.parse import urlparse, urljoin
from flask import request, abort, redirect, url_for, flash
from flask_login import current_user
from app.extensions import login_manager


def is_safe_url(target: str) -> bool:
    """Validate that a redirect target URL is safe and points strictly to the same host."""
    if not target or target.startswith(("//", "\\\\")):
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ("http", "https") and ref_url.netloc == test_url.netloc


def roles_required(*role_names: str):
    """Enforce role-based access control (RBAC).
    
    If unauthenticated: triggers Flask-Login unauthorized handler (redirects to login).
    If authenticated but role mismatch: aborts with HTTP 403 Forbidden.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()

            if not current_user.has_role(*role_names):
                abort(403)

            return fn(*args, **kwargs)
        return wrapper
    return decorator

