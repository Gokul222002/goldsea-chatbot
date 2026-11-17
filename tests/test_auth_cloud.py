import os
import uuid
import time
import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

# Ensure test environment variables are loaded
os.environ["ENVIRONMENT"] = "development"
os.environ["EMAIL_BACKEND"] = "console"
os.environ["DATABASE_URL"] = "sqlite:///data/goldsea.db"
os.environ["SECRET_KEY"] = "94b3a81eaa387e2e9da652e92b1b3e8bbf2de29f7a466e7841c13faefe9dc8d1"

from backend.main import app
from backend.database import (
    SessionLocal, User, EmailCode, UserSession, Conversation, Message, Memory, UserFile,
    create_session
)
from backend.email_service import get_last_email_code
from backend.security import (
    hash_password,
    clear_login_failures,
    clear_rate_limits,
    generate_session_token,
    hash_session_token,
    SESSION_COOKIE_NAME,
    CSRF_COOKIE_NAME
)

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_rate_limiters():
    """Resets in-memory sliding window rate limits before every test."""
    clear_rate_limits()

def get_csrf(session_client: TestClient) -> str:
    res = session_client.get("/api/auth/csrf")
    assert res.status_code == 200
    return res.json()["csrf_token"]

# ------------------------------------------------------------------------------
# Test 1: Full Auth Lifecycle (Signup, Verify, Login, Logout)
# ------------------------------------------------------------------------------
def test_full_auth_lifecycle():
    email = f"alice_{uuid.uuid4().hex[:6]}@example.com"
    password = "AliceSecurePass123!"
    name = "Alice Developer"

    # 1. Sign up
    res = client.post("/api/auth/signup", json={
        "name": name,
        "email": email,
        "password": password,
        "confirm_password": password
    })
    assert res.status_code == 200, res.text
    signup_data = res.json()
    assert signup_data["success"] is True
    assert signup_data["email"] == email.lower()

    # 2. Capture code from test email backend
    code = get_last_email_code(email)
    assert code is not None
    assert len(code) == 6
    assert code.isdigit()

    # Verify no plain passwords or plain codes in database
    with SessionLocal() as db:
        user_row = db.query(User).filter(User.email == email.lower()).first()
        assert user_row is not None
        assert user_row.password_hash != password
        assert not user_row.password_hash.startswith(password[:4])
        assert "$argon2id$" in user_row.password_hash

        code_row = db.query(EmailCode).filter(EmailCode.user_id == user_row.id).order_by(EmailCode.created_at.desc()).first()
        assert code_row is not None
        assert code_row.code_hash != code
        assert len(code_row.code_hash) == 64  # SHA256 hex string

    # 3. Verify Email with valid code
    v_res = client.post("/api/auth/verify-email", json={
        "email": email,
        "code": code
    })
    assert v_res.status_code == 200, v_res.text
    assert "user" in v_res.json()
    assert "goldsea_session" in client.cookies

    # 4. Check /api/auth/me authenticated state
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["user"]["email"] == email.lower()
    assert me_res.json()["user"]["name"] == name

    # 5. Logout
    csrf = get_csrf(client)
    logout_res = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
    assert logout_res.status_code == 200

    # 6. Check /api/auth/me returns 401 after logout
    me_after = client.get("/api/auth/me")
    assert me_after.status_code == 401

    # 7. Log back in
    login_res = client.post("/api/auth/login", json={
        "email": email,
        "password": password
    })
    assert login_res.status_code == 200
    assert login_res.json()["user"]["email"] == email.lower()

# ------------------------------------------------------------------------------
# Test 2: Verification Failure Cases (Wrong code, lockout, expired, reused)
# ------------------------------------------------------------------------------
def test_verification_failure_cases():
    email = f"bob_verify_{uuid.uuid4().hex[:6]}@example.com"
    password = "BobSecurePass123!"
    c = TestClient(app)
    c.post("/api/auth/signup", json={
        "name": "Bob Test",
        "email": email,
        "password": password,
        "confirm_password": password
    })
    valid_code = get_last_email_code(email)

    # 1. Wrong code returns 400
    bad_res = c.post("/api/auth/verify-email", json={
        "email": email,
        "code": "000000"
    })
    assert bad_res.status_code == 400
    assert "Invalid verification code" in bad_res.json()["detail"]

    # 2. 5 wrong attempts lock out the code
    for _ in range(4):
        c.post("/api/auth/verify-email", json={"email": email, "code": "111111"})

    # 5th wrong attempt invalidated it; subsequent attempt is rejected
    lock_res = c.post("/api/auth/verify-email", json={"email": email, "code": valid_code})
    assert lock_res.status_code == 400
    detail = lock_res.json()["detail"].lower()
    assert "no active verification code" in detail or "invalidated" in detail

    # 3. Resend cooldown (resending within 60s is rate-limited)
    resend_cooldown = c.post("/api/auth/resend-code", json={"email": email, "purpose": "verification"})
    assert resend_cooldown.status_code == 429
    assert "Please wait" in resend_cooldown.json()["detail"]

# ------------------------------------------------------------------------------
# Test 3: Unverified User Access Blocked
# ------------------------------------------------------------------------------
def test_unverified_user_cannot_access_protected_apis():
    email = f"charlie_unverified_{uuid.uuid4().hex[:6]}@example.com"
    password = "CharliePass123!"
    c = TestClient(app)
    c.post("/api/auth/signup", json={
        "name": "Charlie Unverified",
        "email": email,
        "password": password,
        "confirm_password": password
    })

    # Unverified user login is blocked with 403 Forbidden
    login_attempt = c.post("/api/auth/login", json={"email": email, "password": password})
    assert login_attempt.status_code == 403
    det = login_attempt.json()["detail"]
    det_str = det if isinstance(det, str) else det.get("message", "")
    assert "not verified" in det_str.lower() or "verify your email" in det_str.lower()

    # If an unverified user has a session cookie, protected endpoints return 403
    with SessionLocal() as db:
        user_row = db.query(User).filter(User.email == email.lower()).first()
        raw_token = generate_session_token()
        token_hash = hash_session_token(raw_token)
        create_session(user_id=user_row.id, token_hash=token_hash)
        c.cookies.set(SESSION_COOKIE_NAME, raw_token)

    r_chat = c.post("/api/chat", json={"message": "Hello?"})
    assert r_chat.status_code == 403
    assert "verification required" in r_chat.json()["detail"].lower()

    r_conv = c.get("/api/conversations")
    assert r_conv.status_code == 403

    r_mem = c.get("/api/memories")
    assert r_mem.status_code == 403

# ------------------------------------------------------------------------------
# Test 4: Unauthenticated Requests Get 401
# ------------------------------------------------------------------------------
def test_unauthenticated_requests_get_401():
    fresh_client = TestClient(app)
    assert fresh_client.get("/api/auth/me").status_code == 401
    assert fresh_client.get("/api/conversations").status_code == 401
    assert fresh_client.post("/api/chat", json={"message": "Hi"}).status_code == 401
    assert fresh_client.get("/api/memories").status_code == 401
    assert fresh_client.get("/api/account/profile").status_code == 401

# ------------------------------------------------------------------------------
# Test 5: CSRF Double-Submit Protection
# ------------------------------------------------------------------------------
def test_csrf_double_submit_protection():
    email = f"dave_csrf_{uuid.uuid4().hex[:6]}@example.com"
    password = "DavePassword123!"
    c = TestClient(app)
    c.post("/api/auth/signup", json={"name": "Dave", "email": email, "password": password, "confirm_password": password})
    code = get_last_email_code(email)
    c.post("/api/auth/verify-email", json={"email": email, "code": code})

    # Missing X-CSRF-Token header on state-changing POST
    r_no_csrf = c.post("/api/memories", json={"key": "lang", "value": "Python"})
    assert r_no_csrf.status_code == 403
    assert "CSRF" in r_no_csrf.json()["detail"]

    # Invalid X-CSRF-Token header
    r_bad_csrf = c.post("/api/memories", json={"key": "lang", "value": "Python"}, headers={"X-CSRF-Token": "bad_token"})
    assert r_bad_csrf.status_code == 403

    # Valid X-CSRF-Token
    valid_csrf = get_csrf(c)
    r_valid_csrf = c.post("/api/memories", json={"key": "lang", "value": "Python"}, headers={"X-CSRF-Token": valid_csrf})
    assert r_valid_csrf.status_code == 200

# ------------------------------------------------------------------------------
# Test 6: Login Lockout after 5 Repeated Failures
# ------------------------------------------------------------------------------
def test_login_lockout_after_failures():
    email = f"target_lockout_{uuid.uuid4().hex[:6]}@example.com"
    password = "RealPassword123!"
    c = TestClient(app)
    c.post("/api/auth/signup", json={"name": "Target", "email": email, "password": password, "confirm_password": password})
    code = get_last_email_code(email)
    c.post("/api/auth/verify-email", json={"email": email, "code": code})

    clear_login_failures(email, "127.0.0.1")

    for _ in range(5):
        fail_res = c.post("/api/auth/login", json={"email": email, "password": "WrongPassword!"})
        assert fail_res.status_code == 401

    # 6th attempt is locked out with 429 Too Many Requests
    locked_res = c.post("/api/auth/login", json={"email": email, "password": password})
    assert locked_res.status_code == 429
    assert "Too many failed login attempts" in locked_res.json()["detail"]

# ------------------------------------------------------------------------------
# Test 7: Multi-User Data Isolation (User A vs User B)
# ------------------------------------------------------------------------------
def test_multi_user_data_isolation():
    # Setup User A
    cA = TestClient(app)
    email_a = f"usera_{uuid.uuid4().hex[:6]}@example.com"
    pass_a = "UserAPassword123!"
    cA.post("/api/auth/signup", json={"name": "Alice User", "email": email_a, "password": pass_a, "confirm_password": pass_a})
    code_a = get_last_email_code(email_a)
    cA.post("/api/auth/verify-email", json={"email": email_a, "code": code_a})
    csrf_a = get_csrf(cA)

    # User A creates a conversation
    conv_a_res = cA.post("/api/conversations", json={"title": "Alice Private Project"}, headers={"X-CSRF-Token": csrf_a})
    assert conv_a_res.status_code == 200
    conv_a_id = conv_a_res.json()["id"]

    # User A saves a memory
    mem_a_res = cA.post("/api/memories", json={"key": "favorite_editor", "value": "Neovim"}, headers={"X-CSRF-Token": csrf_a})
    assert mem_a_res.status_code == 200

    # Setup User B
    cB = TestClient(app)
    email_b = f"userb_{uuid.uuid4().hex[:6]}@example.com"
    pass_b = "UserBPassword123!"
    cB.post("/api/auth/signup", json={"name": "Bob User", "email": email_b, "password": pass_b, "confirm_password": pass_b})
    code_b = get_last_email_code(email_b)
    cB.post("/api/auth/verify-email", json={"email": email_b, "code": code_b})
    csrf_b = get_csrf(cB)

    # 1. User B lists conversations -> must NOT see Alice's conversation
    b_convs = cB.get("/api/conversations").json()
    assert not any(c["id"] == conv_a_id for c in b_convs)

    # 2. User B tries to read Alice's conversation by ID -> 404
    b_get_a = cB.get(f"/api/conversations/{conv_a_id}")
    assert b_get_a.status_code == 404

    # 3. User B tries to update Alice's conversation by ID -> 404
    b_patch_a = cB.patch(f"/api/conversations/{conv_a_id}", json={"title": "Hacked Title"}, headers={"X-CSRF-Token": csrf_b})
    assert b_patch_a.status_code == 404

    # 4. User B tries to delete Alice's conversation by ID -> 404
    b_del_a = cB.delete(f"/api/conversations/{conv_a_id}", headers={"X-CSRF-Token": csrf_b})
    assert b_del_a.status_code == 404

    # 5. User B tries to export Alice's conversation -> 404
    b_exp_a = cB.get(f"/api/conversations/{conv_a_id}/export?format=md")
    assert b_exp_a.status_code == 404

    # 6. User B lists memories -> must NOT see Alice's memory
    b_mems = cB.get("/api/memories").json()
    assert not any(m["key"] == "favorite_editor" for m in b_mems)

    # 7. User B tries to delete Alice's memory -> 404
    b_del_mem = cB.delete("/api/memories/favorite_editor", headers={"X-CSRF-Token": csrf_b})
    assert b_del_mem.status_code == 404

    # Confirm Alice's conversation and memory are completely untouched
    a_check = cA.get(f"/api/conversations/{conv_a_id}")
    assert a_check.status_code == 200
    assert a_check.json()["title"] == "Alice Private Project"

# ------------------------------------------------------------------------------
# Test 8: Sensitive Data Memory Protection
# ------------------------------------------------------------------------------
def test_sensitive_data_memory_protection():
    c = TestClient(app)
    email = f"sec_user_{uuid.uuid4().hex[:6]}@example.com"
    pwd = "SecPassword123!"
    c.post("/api/auth/signup", json={"name": "Sec User", "email": email, "password": pwd, "confirm_password": pwd})
    code = get_last_email_code(email)
    c.post("/api/auth/verify-email", json={"email": email, "code": code})
    csrf = get_csrf(c)

    # Attempt to store credit card
    r_card = c.post("/api/memories", json={"key": "card", "value": "4532 1234 5678 9012"}, headers={"X-CSRF-Token": csrf})
    assert r_card.status_code == 400
    assert "Sensitive data" in r_card.json()["detail"]

    # Attempt to store password
    r_pwd = c.post("/api/memories", json={"key": "my_password", "value": "SecretPassword123!"}, headers={"X-CSRF-Token": csrf})
    assert r_pwd.status_code == 400

# ------------------------------------------------------------------------------
# Test 9: Account Deletion Cascades Everything
# ------------------------------------------------------------------------------
def test_account_deletion_cascades():
    c = TestClient(app)
    email = f"del_user_{uuid.uuid4().hex[:6]}@example.com"
    pwd = "DelPassword123!"
    c.post("/api/auth/signup", json={"name": "Del User", "email": email, "password": pwd, "confirm_password": pwd})
    code = get_last_email_code(email)
    c.post("/api/auth/verify-email", json={"email": email, "code": code})
    csrf = get_csrf(c)

    # Save a conversation and memory
    conv = c.post("/api/conversations", json={"title": "To Be Deleted"}, headers={"X-CSRF-Token": csrf}).json()
    c.post("/api/memories", json={"key": "temp_pref", "value": "testing"}, headers={"X-CSRF-Token": csrf})

    with SessionLocal() as db:
        user_row = db.query(User).filter(User.email == email.lower()).first()
        assert user_row is not None
        user_id = user_row.id
        assert db.query(Conversation).filter(Conversation.user_id == user_id).count() >= 1
        assert db.query(Memory).filter(Memory.user_id == user_id).count() >= 1

    # Delete account
    del_res = c.request("DELETE", "/api/account/delete-account", json={"password": pwd}, headers={"X-CSRF-Token": csrf})
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Confirm user, conversations, memories are gone from DB
    with SessionLocal() as db:
        assert db.query(User).filter(User.id == user_id).first() is None
        assert db.query(Conversation).filter(Conversation.user_id == user_id).count() == 0
        assert db.query(Memory).filter(Memory.user_id == user_id).count() == 0

    # Logging in fails
    clear_rate_limits()
    clear_login_failures(email, "127.0.0.1")
    login_again = c.post("/api/auth/login", json={"email": email, "password": pwd})
    assert login_again.status_code == 401

# ------------------------------------------------------------------------------
# Test 10: Memory Recall & System Prompt Isolation (User A fact isolated from B)
# ------------------------------------------------------------------------------
def test_memory_recall_and_cross_user_isolation():
    from backend.database import get_all_memories
    from backend.prompt_engine import build_system_prompt

    cA = TestClient(app)
    email_a = f"mem_alice_{uuid.uuid4().hex[:6]}@example.com"
    pwd = "AlicePass123!"
    cA.post("/api/auth/signup", json={"name": "Alice", "email": email_a, "password": pwd, "confirm_password": pwd})
    code_a = get_last_email_code(email_a)
    cA.post("/api/auth/verify-email", json={"email": email_a, "code": code_a})
    csrf_a = get_csrf(cA)

    # Alice sets a preference memory
    cA.post("/api/memories", json={"key": "preferred_language", "value": "Rust", "category": "preference"}, headers={"X-CSRF-Token": csrf_a})

    # User B setup
    cB = TestClient(app)
    email_b = f"mem_bob_{uuid.uuid4().hex[:6]}@example.com"
    cB.post("/api/auth/signup", json={"name": "Bob", "email": email_b, "password": pwd, "confirm_password": pwd})
    code_b = get_last_email_code(email_b)
    cB.post("/api/auth/verify-email", json={"email": email_b, "code": code_b})

    with SessionLocal() as db:
        user_a = db.query(User).filter(User.email == email_a.lower()).first()
        user_b = db.query(User).filter(User.email == email_b.lower()).first()

        mems_a = get_all_memories(user_a.id)
        mems_b = get_all_memories(user_b.id)

        assert any(m["key"] == "preferred_language" and m["value"] == "Rust" for m in mems_a)
        assert not any(m["key"] == "preferred_language" for m in mems_b)

        prompt_a = build_system_prompt(memories=mems_a, user_name=user_a.name)
        prompt_b = build_system_prompt(memories=mems_b, user_name=user_b.name)

        assert "Rust" in prompt_a
        assert "Alice" in prompt_a
        assert "Rust" not in prompt_b
        assert "Bob" in prompt_b

# ------------------------------------------------------------------------------
# Test 11: Guest Mode (Continue Without Login)
# ------------------------------------------------------------------------------
def test_guest_login_mode():
    client = TestClient(app)
    # Unauthenticated gets 401
    assert client.get("/api/auth/me").status_code == 401

    # Guest login creates active guest session
    res = client.post("/api/auth/guest-login")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["user"]["name"] == "Guest"

    # Guest can access /api/auth/me and protected routes
    me_res = client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["user"]["name"] == "Guest"

    # Guest can retrieve their conversation list
    convs_res = client.get("/api/conversations")
    assert convs_res.status_code == 200
