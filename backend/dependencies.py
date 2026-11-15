from typing import Optional
from fastapi import Request, HTTPException, status, Depends
from backend.database import get_session_and_user, User
from backend.security import (
    SESSION_COOKIE_NAME,
    hash_session_token,
    verify_csrf
)

async def verify_csrf_token(request: Request) -> None:
    """FastAPI dependency to enforce CSRF token validation on state-changing requests."""
    verify_csrf(request)

async def get_current_user(request: Request) -> User:
    """
    FastAPI dependency to authenticate requests via the secure httpOnly session cookie.
    Validates token in database and ensures the user's email has been verified.
    Raises HTTP 401 if unauthenticated or session expired.
    Raises HTTP 403 if email is not yet verified.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in."
        )

    token_hash = hash_session_token(token)
    res = get_session_and_user(token_hash)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or is invalid. Please log in again."
        )

    session_obj, user = res

    if not user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required before accessing GoldSea AI."
        )

    return user

async def get_optional_user(request: Request) -> Optional[User]:
    """Returns the authenticated user if session is valid, or None without raising 401."""
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    token_hash = hash_session_token(token)
    res = get_session_and_user(token_hash)
    if not res:
        return None
    _, user = res
    return user
