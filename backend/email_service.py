import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, Dict, List
import httpx

from backend.config import (
    EMAIL_BACKEND,
    EMAIL_FROM,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASS,
    SMTP_TLS,
    RESEND_API_KEY,
    BREVO_API_KEY,
    ENVIRONMENT
)

# In-memory code capture for automated tests and development inspection
_SENT_CODES: Dict[str, List[Dict[str, str]]] = {}

def get_last_email_code(email: str, purpose: Optional[str] = None) -> Optional[str]:
    """Retrieves the most recent verification or reset code sent to an email (used in automated tests)."""
    normalized = email.strip().lower()
    items = _SENT_CODES.get(normalized, [])
    if not items:
        return None
    if purpose:
        filtered = [x for x in items if x.get("purpose") == purpose]
        return filtered[-1]["code"] if filtered else None
    return items[-1]["code"]

def clear_test_emails():
    """Clears the captured test email store."""
    _SENT_CODES.clear()

def _record_test_code(email: str, code: str, purpose: str):
    normalized = email.strip().lower()
    if normalized not in _SENT_CODES:
        _SENT_CODES[normalized] = []
    _SENT_CODES[normalized].append({"code": code, "purpose": purpose})

def _build_html_email(name: str, code: str, purpose_title: str, purpose_desc: str) -> str:
    user_name = name or "there"
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{purpose_title}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #060d09; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e2e8f0;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #060d09; padding: 40px 15px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" style="max-width: 500px; background-color: #0a140e; border: 1px solid rgba(34, 197, 94, 0.2); border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.5);">
          <!-- Header -->
          <tr>
            <td style="padding: 30px 30px 20px 30px; border-bottom: 1px solid rgba(34, 197, 94, 0.1); background: linear-gradient(180deg, #0f2317 0%, #0a140e 100%);">
              <table role="presentation" width="100%">
                <tr>
                  <td>
                    <h1 style="margin: 0; font-size: 22px; font-weight: 800; color: #ffffff; letter-spacing: -0.5px;">
                      GoldSea <span style="background-color: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.3); font-size: 11px; padding: 2px 7px; border-radius: 4px; vertical-align: middle; text-transform: uppercase;">AI</span>
                    </h1>
                    <p style="margin: 4px 0 0 0; font-size: 12px; color: #94a3b8;">Personal AI Assistant with Private Cloud Storage</p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="padding: 30px;">
              <h2 style="margin: 0 0 12px 0; font-size: 18px; font-weight: 700; color: #f8fafc;">
                {purpose_title}
              </h2>
              <p style="margin: 0 0 20px 0; font-size: 14px; line-height: 1.6; color: #cbd5e1;">
                Hello {user_name},<br>
                {purpose_desc} Use the 6-digit code below to proceed:
              </p>
              
              <!-- Verification Code Box -->
              <div style="background-color: #060d09; border: 1px solid #16a34a; border-radius: 12px; padding: 18px; text-align: center; margin: 25px 0;">
                <span style="font-family: 'Courier New', Courier, monospace; font-size: 34px; font-weight: 800; letter-spacing: 8px; color: #4ade80; display: inline-block;">
                  {code}
                </span>
              </div>

              <p style="margin: 0 0 10px 0; font-size: 12px; color: #94a3b8; text-align: center;">
                ⏱️ This verification code is valid for <strong>10 minutes</strong> and can only be used once.
              </p>
              <div style="margin-top: 25px; padding-top: 20px; border-top: 1px solid rgba(255, 255, 255, 0.08); font-size: 12px; line-height: 1.5; color: #64748b;">
                If you did not request this verification code, please ignore this email. Your GoldSea AI account remains completely secure.
              </div>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="padding: 16px 30px; background-color: #060d09; text-align: center; font-size: 11px; color: #475569; border-top: 1px solid rgba(255, 255, 255, 0.05);">
              &copy; GoldSea AI &bull; Encrypted & Private Cloud Intelligence
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""

def _build_text_email(name: str, code: str, purpose_title: str, purpose_desc: str) -> str:
    user_name = name or "there"
    return f"""GoldSea AI — {purpose_title}

Hello {user_name},

{purpose_desc}

Your 6-digit code is: {code}

This code is valid for 10 minutes and can only be used once.

If you did not request this verification code, please ignore this email. Your GoldSea AI account remains completely secure.

GoldSea AI — Private Cloud Intelligence
"""

async def send_verification_email(email: str, name: str, code: str) -> bool:
    """Sends a 6-digit email verification code."""
    subject = f"GoldSea AI — Verification Code: {code}"
    purpose_title = "Verify Your Email Address"
    purpose_desc = "Welcome to GoldSea AI! Please verify your email to activate your account and access your private cloud workspace."
    return await send_email(email=email, name=name, subject=subject, code=code, purpose="verification", purpose_title=purpose_title, purpose_desc=purpose_desc)

async def send_password_reset_email(email: str, name: str, code: str) -> bool:
    """Sends a 6-digit password reset code."""
    subject = f"GoldSea AI — Password Reset Code: {code}"
    purpose_title = "Reset Your Password"
    purpose_desc = "We received a request to reset the password for your GoldSea AI account."
    return await send_email(email=email, name=name, subject=subject, code=code, purpose="password_reset", purpose_title=purpose_title, purpose_desc=purpose_desc)

async def send_email(
    email: str,
    name: str,
    subject: str,
    code: str,
    purpose: str,
    purpose_title: str,
    purpose_desc: str
) -> bool:
    """Dispatches email via the configured backend (SMTP, Resend API, Brevo API, or console)."""
    # Always record the code in memory for test verification
    _record_test_code(email=email, code=code, purpose=purpose)

    html_content = _build_html_email(name=name, code=code, purpose_title=purpose_title, purpose_desc=purpose_desc)
    text_content = _build_text_email(name=name, code=code, purpose_title=purpose_title, purpose_desc=purpose_desc)

    backend = EMAIL_BACKEND.lower()

    if backend == "console" or (ENVIRONMENT != "production" and not (SMTP_HOST or RESEND_API_KEY or BREVO_API_KEY)):
        print("\n" + "=" * 65)
        print(f" [EMAIL DISPATCH: CONSOLE / TEST BACKEND]")
        print(f" To:      {name} <{email}>")
        print(f" Subject: {subject}")
        print(f" Purpose: {purpose}")
        print(f" CODE:    >>> {code} <<<")
        print(f" Expiry:  10 minutes")
        print("=" * 65 + "\n")
        return True

    # 1. Resend API
    if backend == "resend" or (RESEND_API_KEY and not SMTP_HOST):
        try:
            headers = {
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "from": EMAIL_FROM,
                "to": [email],
                "subject": subject,
                "html": html_content,
                "text": text_content
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post("https://api.resend.com/emails", headers=headers, json=payload)
                if resp.status_code in (200, 201):
                    return True
                print(f"[EMAIL ERROR - Resend HTTP {resp.status_code}]: {resp.text}")
                return False
        except Exception as e:
            print(f"[EMAIL ERROR - Resend Exception]: {e}")
            return False

    # 2. Brevo API
    if backend == "brevo" or (BREVO_API_KEY and not SMTP_HOST):
        try:
            headers = {
                "api-key": BREVO_API_KEY,
                "Content-Type": "application/json"
            }
            payload = {
                "sender": {"email": EMAIL_FROM, "name": "GoldSea AI"},
                "to": [{"email": email, "name": name or "User"}],
                "subject": subject,
                "htmlContent": html_content,
                "textContent": text_content
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post("https://api.brevo.com/v3/smtp/email", headers=headers, json=payload)
                if resp.status_code in (200, 201):
                    return True
                print(f"[EMAIL ERROR - Brevo HTTP {resp.status_code}]: {resp.text}")
                return False
        except Exception as e:
            print(f"[EMAIL ERROR - Brevo Exception]: {e}")
            return False

    # 3. SMTP (e.g. Gmail App Password, SendGrid, Mailgun)
    if SMTP_HOST and SMTP_USER and SMTP_PASS:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"GoldSea AI <{EMAIL_FROM}>"
            msg["To"] = email

            part1 = MIMEText(text_content, "plain", "utf-8")
            part2 = MIMEText(html_content, "html", "utf-8")
            msg.attach(part1)
            msg.attach(part2)

            if SMTP_PORT == 465:
                server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15)
            else:
                server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
                if SMTP_TLS:
                    server.starttls()

            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(EMAIL_FROM, [email], msg.as_string())
            server.quit()
            return True
        except Exception as e:
            print(f"[EMAIL ERROR - SMTP Exception]: {e}")
            return False

    print(f"[EMAIL ERROR]: No valid email provider configured for {email}.")
    return False
