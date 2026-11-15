import re
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request, Response, status, Depends
from backend.models import (
    SignUpRequest,
    VerifyEmailRequest,
    ResendCodeRequest,
    LoginRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ChangePasswordRequest,
    UpdateProfileRequest,
    DeleteAccountRequest
)
from backend.database import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    update_user_password,
    update_user_profile,
    update_user_last_login,
    verify_user_email,
    delete_user_account,
    create_email_code,
    get_latest_email_code,
    increment_code_attempts,
    mark_code_used,
    count_recent_email_sends,
    get_last_code_created_at,
    create_session,
    delete_session,
    delete_all_user_sessions,
    User
)
from backend.security import (
    hash_password,
    verify_password,
    generate_six_digit_code,
    hash_code,
    verify_code,
    generate_session_token,
    hash_session_token,
    set_session_cookie,
    clear_session_cookie,
    generate_csrf_token,
    set_csrf_cookie,
    verify_csrf,
    check_rate_limit,
    record_login_failure,
    is_login_locked,
    clear_login_failures,
    get_client_ip,
    SESSION_COOKIE_NAME
)
from backend.email_service import send_verification_email, send_password_reset_email
from backend.dependencies import get_current_user, get_optional_user

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

def validate_email_format(email: str):
    if not email or not EMAIL_REGEX.match(email.strip()):
        raise HTTPException(status_code=400, detail="Invalid email address format.")

# ------------------------------------------------------------------------------
# CSRF Token Endpoint
# ------------------------------------------------------------------------------

@router.get("/csrf")
async def get_csrf_token(request: Request, response: Response):
    """Issues or refreshes the CSRF token cookie."""
    token = request.cookies.get("goldsea_csrf") or generate_csrf_token()
    set_csrf_cookie(response, token)
    return {"csrf_token": token}

# ------------------------------------------------------------------------------
# Session / Profile Info Endpoint
# ------------------------------------------------------------------------------

@router.get("/me")
async def get_me(request: Request, response: Response):
    """Returns the authenticated user or 401."""
    user = await get_optional_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    # Ensure CSRF cookie is fresh
    token = request.cookies.get("goldsea_csrf") or generate_csrf_token()
    set_csrf_cookie(response, token)

    return {
        "authenticated": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "email_verified": user.email_verified,
            "created_at": user.created_at.isoformat() if user.created_at else ""
        }
    }

# ------------------------------------------------------------------------------
# Sign Up
# ------------------------------------------------------------------------------

@router.post("/signup")
async def sign_up(req: SignUpRequest, request: Request, response: Response):
    client_ip = get_client_ip(request)

    # Rate limiting: max 5 signups per hour per IP
    allowed, retry_after = check_rate_limit(f"signup:{client_ip}", max_requests=5, window_seconds=3600)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many accounts created from this network. Please try again in {retry_after // 60 + 1} minutes."
        )

    # Validate inputs
    validate_email_format(req.email)
    name = req.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Name must be at least 2 characters long.")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")
    if req.password != req.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    email_clean = req.email.strip().lower()
    existing_user = get_user_by_email(email_clean)

    # Check if already registered and verified
    if existing_user and existing_user.email_verified:
        # Generic response to prevent user enumeration
        return {
            "success": True,
            "email": email_clean,
            "message": "Verification code sent to your email. Please check your inbox (and spam folder)."
        }

    pwd_hash = hash_password(req.password)

    if existing_user and not existing_user.email_verified:
        user = existing_user
        update_user_password(user.id, pwd_hash)
        update_user_profile(user.id, name)
    else:
        user = create_user(
            email=email_clean,
            password_hash=pwd_hash,
            name=name,
            email_verified=False
        )

    # Generate 6-digit verification code
    code = generate_six_digit_code()
    code_hash_val = hash_code(code)
    create_email_code(user_id=user.id, code_hash=code_hash_val, purpose="verification", expires_in_minutes=10)

    # Dispatch email
    await send_verification_email(email=email_clean, name=name, code=code)

    # Set CSRF cookie
    set_csrf_cookie(response)

    return {
        "success": True,
        "email": email_clean,
        "message": "Verification code sent to your email. Please check your inbox (and spam folder)."
    }

# ------------------------------------------------------------------------------
# Verify Email Code
# ------------------------------------------------------------------------------

@router.post("/verify-email")
async def verify_email(req: VerifyEmailRequest, request: Request, response: Response):
    client_ip = get_client_ip(request)

    email_clean = req.email.strip().lower()
    code_clean = req.code.strip()

    if not code_clean.isdigit() or len(code_clean) != 6:
        raise HTTPException(status_code=400, detail="Verification code must be exactly 6 digits.")

    user = get_user_by_email(email_clean)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code.")

    if user.email_verified:
        # Already verified: issue session
        token = generate_session_token()
        token_hash = hash_session_token(token)
        create_session(user_id=user.id, token_hash=token_hash, user_agent=request.headers.get("user-agent", ""), ip_address=client_ip)
        set_session_cookie(response, token)
        set_csrf_cookie(response)
        return {
            "success": True,
            "message": "Email verified successfully.",
            "user": {"id": user.id, "email": user.email, "name": user.name}
        }

    latest_code = get_latest_email_code(user.id, purpose="verification")
    if not latest_code:
        raise HTTPException(status_code=400, detail="No active verification code found. Please request a new code.")

    # Check expiration
    now = datetime.now(timezone.utc)
    code_expires = latest_code.expires_at
    if code_expires.tzinfo is None:
        code_expires = code_expires.replace(tzinfo=timezone.utc)

    if code_expires <= now:
        mark_code_used(latest_code.id)
        raise HTTPException(status_code=400, detail="Verification code has expired. Please request a new code.")

    # Check attempt limit
    if latest_code.attempts >= 5:
        mark_code_used(latest_code.id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification code has been invalidated due to too many failed attempts. Please request a new code."
        )

    # Verify code hash
    if not verify_code(code_clean, latest_code.code_hash):
        attempts_now = increment_code_attempts(latest_code.id)
        remaining = max(0, 5 - attempts_now)
        if remaining == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification code has been invalidated due to too many failed attempts. Please request a new code."
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid verification code. {remaining} attempt(s) remaining."
        )

    # Code matches! Mark used and activate account
    mark_code_used(latest_code.id)
    verify_user_email(user.id)
    update_user_last_login(user.id)

    # Log user in: create session and set cookie
    token = generate_session_token()
    token_hash = hash_session_token(token)
    create_session(
        user_id=user.id,
        token_hash=token_hash,
        user_agent=request.headers.get("user-agent", ""),
        ip_address=client_ip
    )
    set_session_cookie(response, token)
    set_csrf_cookie(response)

    return {
        "success": True,
        "message": "Email verified successfully. Welcome to GoldSea AI!",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name
        }
    }

# ------------------------------------------------------------------------------
# Resend Verification / Reset Code
# ------------------------------------------------------------------------------

@router.post("/resend-code")
async def resend_code(req: ResendCodeRequest, request: Request, response: Response):
    client_ip = get_client_ip(request)
    email_clean = req.email.strip().lower()
    purpose = req.purpose.strip().lower()
    if purpose not in ("verification", "password_reset"):
        purpose = "verification"

    user = get_user_by_email(email_clean)
    if not user:
        # Generic response to prevent enumeration
        return {
            "success": True,
            "message": "If an account is eligible, a new verification code has been sent."
        }

    # If verifying and already verified, skip
    if purpose == "verification" and user.email_verified:
        return {
            "success": True,
            "message": "Your email is already verified. You can log in directly."
        }

    # 1. 60-second cooldown rule
    last_created = get_last_code_created_at(user.id, purpose=purpose)
    if last_created:
        now = datetime.now(timezone.utc)
        if last_created.tzinfo is None:
            last_created = last_created.replace(tzinfo=timezone.utc)
        elapsed = (now - last_created).total_seconds()
        if elapsed < 60:
            remaining = int(60 - elapsed) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {remaining} second(s) before requesting another code."
            )

    # 2. Maximum 5 sends per hour rule
    recent_count = count_recent_email_sends(user.id, purpose=purpose, hours=1)
    if recent_count >= 5:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum hourly code request limit reached. Please try again in an hour."
        )

    # Generate new code
    new_code = generate_six_digit_code()
    new_code_hash = hash_code(new_code)
    create_email_code(user_id=user.id, code_hash=new_code_hash, purpose=purpose, expires_in_minutes=10)

    # Dispatch email
    if purpose == "password_reset":
        await send_password_reset_email(email=email_clean, name=user.name, code=new_code)
    else:
        await send_verification_email(email=email_clean, name=user.name, code=new_code)

    return {
        "success": True,
        "message": "A new verification code has been sent to your email."
    }

# ------------------------------------------------------------------------------
# Login
# ------------------------------------------------------------------------------

@router.post("/login")
async def login(req: LoginRequest, request: Request, response: Response):
    client_ip = get_client_ip(request)
    email_clean = req.email.strip().lower()

    # Check repeated failure lockout (per IP and per email)
    locked, remaining_seconds = is_login_locked(email=email_clean, ip=client_ip, max_failures=5, lock_duration=900)
    if locked:
        mins = (remaining_seconds // 60) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Account temporarily locked. Please try again in {mins} minute(s)."
        )

    user = get_user_by_email(email_clean)

    # Validate password
    if not user or not verify_password(req.password, user.password_hash):
        record_login_failure(email=email_clean, ip=client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password."
        )

    # Check if email is verified
    if not user.email_verified:
        # Prompt user to verify email
        code = generate_six_digit_code()
        code_hash_val = hash_code(code)
        create_email_code(user_id=user.id, code_hash=code_hash_val, purpose="verification", expires_in_minutes=10)
        await send_verification_email(email=email_clean, name=user.name, code=code)

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "email_not_verified",
                "email": user.email,
                "message": "Please verify your email address before logging in. A new 6-digit code has been sent."
            }
        )

    # Clear failure counters
    clear_login_failures(email=email_clean, ip=client_ip)
    update_user_last_login(user.id)

    # Issue session
    token = generate_session_token()
    token_hash = hash_session_token(token)
    create_session(
        user_id=user.id,
        token_hash=token_hash,
        user_agent=request.headers.get("user-agent", ""),
        ip_address=client_ip
    )

    set_session_cookie(response, token)
    set_csrf_cookie(response)

    return {
        "success": True,
        "message": "Logged in successfully.",
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name
        }
    }

# ------------------------------------------------------------------------------
# Logout
# ------------------------------------------------------------------------------

@router.post("/logout")
async def logout(request: Request, response: Response):
    verify_csrf(request)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        delete_session(hash_session_token(token))
    clear_session_cookie(response)
    set_csrf_cookie(response)
    return {"success": True, "message": "Logged out successfully."}

@router.post("/logout-all")
async def logout_all_devices(request: Request, response: Response, current_user: User = Depends(get_current_user)):
    verify_csrf(request)
    delete_all_user_sessions(current_user.id)
    clear_session_cookie(response)
    set_csrf_cookie(response)
    return {"success": True, "message": "Successfully logged out of all devices."}

# ------------------------------------------------------------------------------
# Forgot & Reset Password
# ------------------------------------------------------------------------------

@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, request: Request, response: Response):
    client_ip = get_client_ip(request)
    email_clean = req.email.strip().lower()
    validate_email_format(email_clean)

    user = get_user_by_email(email_clean)
    if user and user.email_verified:
        # Check cooldown
        last_created = get_last_code_created_at(user.id, purpose="password_reset")
        if last_created:
            now = datetime.now(timezone.utc)
            if last_created.tzinfo is None:
                last_created = last_created.replace(tzinfo=timezone.utc)
            if (now - last_created).total_seconds() < 60:
                # Silently accept or rate limit
                return {
                    "success": True,
                    "message": "If an account exists with this email, a reset code has been sent."
                }

        # Check hourly limit
        if count_recent_email_sends(user.id, purpose="password_reset", hours=1) < 5:
            code = generate_six_digit_code()
            code_hash_val = hash_code(code)
            create_email_code(user_id=user.id, code_hash=code_hash_val, purpose="password_reset", expires_in_minutes=10)
            await send_password_reset_email(email=email_clean, name=user.name, code=code)

    # Generic response
    return {
        "success": True,
        "message": "If an account exists with this email, a reset code has been sent."
    }

@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest, request: Request, response: Response):
    email_clean = req.email.strip().lower()
    code_clean = req.code.strip()

    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters long.")
    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    user = get_user_by_email(email_clean)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset code.")

    latest_code = get_latest_email_code(user.id, purpose="password_reset")
    if not latest_code:
        raise HTTPException(status_code=400, detail="No active password reset code found.")

    now = datetime.now(timezone.utc)
    code_expires = latest_code.expires_at
    if code_expires.tzinfo is None:
        code_expires = code_expires.replace(tzinfo=timezone.utc)

    if code_expires <= now:
        mark_code_used(latest_code.id)
        raise HTTPException(status_code=400, detail="Password reset code has expired. Please request a new one.")

    if latest_code.attempts >= 5:
        mark_code_used(latest_code.id)
        raise HTTPException(status_code=400, detail="Reset code invalidated due to too many failed attempts.")

    if not verify_code(code_clean, latest_code.code_hash):
        attempts = increment_code_attempts(latest_code.id)
        rem = max(0, 5 - attempts)
        raise HTTPException(status_code=400, detail=f"Invalid reset code. {rem} attempt(s) remaining.")

    # Match! Update password and invalidate all sessions
    mark_code_used(latest_code.id)
    new_hash = hash_password(req.new_password)
    update_user_password(user.id, new_hash)
    delete_all_user_sessions(user.id)

    clear_session_cookie(response)
    set_csrf_cookie(response)

    return {
        "success": True,
        "message": "Password reset successful. Please log in with your new password."
    }
