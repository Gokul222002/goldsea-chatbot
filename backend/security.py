import os
import hmac
import hashlib
import secrets
import re
import time
from typing import Optional, Tuple, Dict, List
from fastapi import Request, HTTPException, status, Response
from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError, InvalidHashError

from backend.config import SECRET_KEY, ENVIRONMENT

# Initialize Argon2id password hasher (RFC 9106 recommended parameters)
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MB
    parallelism=4,
    hash_len=32,
    type=Type.ID  # Argon2id
)

SESSION_COOKIE_NAME = "goldsea_session"
CSRF_COOKIE_NAME = "goldsea_csrf"
CSRF_HEADER_NAME = "X-CSRF-Token"
SESSION_MAX_AGE = 7 * 24 * 3600  # 7 days in seconds

# ------------------------------------------------------------------------------
# Password Hashing & Verification
# ------------------------------------------------------------------------------

def hash_password(plain_password: str) -> str:
    """Hashes a plain-text password using Argon2id. Never stores or logs plain passwords."""
    if not plain_password or len(plain_password) < 8:
        raise ValueError("Password must be at least 8 characters long.")
    return _hasher.hash(plain_password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain-text password against an Argon2id hash in constant time."""
    if not plain_password or not hashed_password:
        return False
    try:
        return _hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception:
        return False

# ------------------------------------------------------------------------------
# 6-Digit Cryptographic Verification / Reset Codes
# ------------------------------------------------------------------------------

def generate_six_digit_code() -> str:
    """Generates a cryptographically secure 6-digit numeric string."""
    return f"{secrets.randbelow(1000000):06d}"

def hash_code(code: str) -> str:
    """
    Hashes a 6-digit code using HMAC-SHA256 with the server SECRET_KEY.
    Ensures plain-text codes are never stored in the database.
    """
    clean_code = str(code).strip()
    key_bytes = SECRET_KEY.encode("utf-8")
    return hmac.new(key_bytes, clean_code.encode("utf-8"), hashlib.sha256).hexdigest()

def verify_code(code: str, expected_hash: str) -> bool:
    """Verifies a 6-digit code against its stored HMAC-SHA256 hash in constant time."""
    computed = hash_code(code)
    return hmac.compare_digest(computed, expected_hash)

# ------------------------------------------------------------------------------
# Session Tokens & Cookies
# ------------------------------------------------------------------------------

def generate_session_token() -> str:
    """Generates a cryptographically random session token (URL-safe, 256 bits of entropy)."""
    return secrets.token_urlsafe(32)

def hash_session_token(token: str) -> str:
    """Hashes a session token with SHA-256 before saving/lookup in the database."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def set_session_cookie(response: Response, token: str) -> None:
    """
    Sets a secure, httpOnly, SameSite=Lax session cookie.
    Never stores tokens in localStorage.
    """
    is_prod = (ENVIRONMENT == "production")
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=is_prod,
        path="/"
    )

def clear_session_cookie(response: Response) -> None:
    """Clears the session cookie on logout."""
    is_prod = (ENVIRONMENT == "production")
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=is_prod
    )

# ------------------------------------------------------------------------------
# CSRF Protection
# ------------------------------------------------------------------------------

def generate_csrf_token() -> str:
    """Generates a random CSRF token for the double-submit cookie pattern."""
    return secrets.token_urlsafe(24)

def set_csrf_cookie(response: Response, token: Optional[str] = None) -> str:
    """Sets the non-httpOnly CSRF cookie readable by the frontend application."""
    csrf_token = token or generate_csrf_token()
    is_prod = (ENVIRONMENT == "production")
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=SESSION_MAX_AGE,
        httponly=False,  # JavaScript must read this to include in the X-CSRF-Token header
        samesite="lax",
        secure=is_prod,
        path="/"
    )
    return csrf_token

def verify_csrf(request: Request) -> None:
    """
    Validates CSRF token on state-changing HTTP requests.
    Exempts safe methods (GET, HEAD, OPTIONS).
    Raises HTTP 403 Forbidden on mismatch or missing token.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return

    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get(CSRF_HEADER_NAME)

    if not cookie_token or not header_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing from request cookie or header."
        )

    if not hmac.compare_digest(cookie_token, header_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token validation failed."
        )

# ------------------------------------------------------------------------------
# In-Memory Rate Limiting & Lockout
# ------------------------------------------------------------------------------

# Store for rate limiting: key -> list of float timestamps
_RATE_LIMITS: Dict[str, List[float]] = {}
# Store for failed login tracking: key -> list of float timestamps
_LOGIN_FAILURES: Dict[str, List[float]] = {}

def check_rate_limit(key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int]:
    """
    Sliding window rate limiter.
    Returns (is_allowed, retry_after_seconds).
    """
    now = time.time()
    timestamps = _RATE_LIMITS.get(key, [])
    # Filter timestamps within the window
    valid_timestamps = [t for t in timestamps if now - t < window_seconds]

    if len(valid_timestamps) >= max_requests:
        oldest = valid_timestamps[0]
        retry_after = int(window_seconds - (now - oldest)) + 1
        _RATE_LIMITS[key] = valid_timestamps
        return False, max(1, retry_after)

    valid_timestamps.append(now)
    _RATE_LIMITS[key] = valid_timestamps
    return True, 0

def clear_rate_limits() -> None:
    """Clears all sliding window rate limit counters (useful for test isolation)."""
    _RATE_LIMITS.clear()
    _LOGIN_FAILURES.clear()

def record_login_failure(email: str, ip: str) -> None:
    """Records a failed login attempt for both the email and the client IP."""
    now = time.time()
    for k in (f"fail_email:{email.lower()}", f"fail_ip:{ip}"):
        if k not in _LOGIN_FAILURES:
            _LOGIN_FAILURES[k] = []
        _LOGIN_FAILURES[k].append(now)

def is_login_locked(email: str, ip: str, max_failures: int = 5, lock_duration: int = 900) -> Tuple[bool, int]:
    """
    Checks if login attempts are locked due to 5+ failures in the last 15 minutes.
    Returns (is_locked, remaining_seconds).
    """
    now = time.time()
    for k in (f"fail_email:{email.lower()}", f"fail_ip:{ip}"):
        timestamps = _LOGIN_FAILURES.get(k, [])
        recent = [t for t in timestamps if now - t < lock_duration]
        _LOGIN_FAILURES[k] = recent
        if len(recent) >= max_failures:
            remaining = int(lock_duration - (now - recent[0])) + 1
            return True, max(1, remaining)
    return False, 0

def clear_login_failures(email: str, ip: str) -> None:
    """Clears failed login counter upon successful authentication."""
    _LOGIN_FAILURES.pop(f"fail_email:{email.lower()}", None)
    _LOGIN_FAILURES.pop(f"fail_ip:{ip}", None)

def get_client_ip(request: Request) -> str:
    """Extracts client IP considering X-Forwarded-For header from Render/proxies."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"

# ------------------------------------------------------------------------------
# Sensitive Memory Protection Filter
# ------------------------------------------------------------------------------

# Patterns to strictly block from entering persistent user memory
SENSITIVE_PATTERNS = [
    # Credit Card numbers (13 to 19 digits)
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    # US SSN (xxx-xx-xxxx)
    re.compile(r"\b\d{3}[-\s]\d{2}[-\s]\d{4}\b"),
    # Passwords / Tokens / Keys
    re.compile(r"(?:my\s+)?(?:password|passwd|pwd|secret|api[_\s-]?key|bearer|token|pin)\s*(?:is|[:=])\s*\S+", re.IGNORECASE),
    re.compile(r"\b(?:password|passwd|secret_key|api_key|access_token)\b", re.IGNORECASE),
    # CVV / CVC
    re.compile(r"\b(?:cvv|cvc|security code)\s*[:=]?\s*\d{3,4}\b", re.IGNORECASE),
    # Government IDs / Cards
    re.compile(r"\b(?:ssn|social security|aadhaar|passport number)\b", re.IGNORECASE),
]

SENSITIVE_KEYWORDS = [
    "password", "passwd", "pwd", "secret_key", "api_key", "bearer ",
    "access_token", "private_key", "credit_card", "debit_card", "cvv", "cvc",
    "social security", "aadhaar", "passport number"
]

def contains_sensitive_data(text: str) -> bool:
    """Checks whether text contains credit card numbers, SSNs, passwords, or secrets."""
    if not text:
        return False
    lower = text.lower()
    if any(kw in lower for kw in SENSITIVE_KEYWORDS):
        return True
    for pat in SENSITIVE_PATTERNS:
        if pat.search(text):
            return True
    return False
