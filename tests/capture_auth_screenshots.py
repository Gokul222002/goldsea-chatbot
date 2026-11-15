import os
import sys
import time
import uuid
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parent.parent
SCREENSHOT_DIR = ROOT_DIR / "tests" / "auth_screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

PORT = 18766
URL = f"http://127.0.0.1:{PORT}"

def switch_subview(page, target_id):
    page.evaluate(f"""() => {{
        ['auth-login-view', 'auth-signup-view', 'auth-forgot-view', 'auth-verify-view', 'auth-reset-view'].forEach(id => {{
            const el = document.getElementById(id);
            if (el) el.classList.add('hidden');
        }});
        const target = document.getElementById('{target_id}');
        if (target) target.classList.remove('hidden');
    }}""")

def main():
    print("Starting Uvicorn server on port", PORT)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT_DIR)
    env["ENVIRONMENT"] = "development"
    env["EMAIL_BACKEND"] = "console"
    env["DATABASE_URL"] = "sqlite:///data/goldsea.db"
    env["SECRET_KEY"] = "94b3a81eaa387e2e9da652e92b1b3e8bbf2de29f7a466e7841c13faefe9dc8d1"

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    try:
        import urllib.request
        ready = False
        for _ in range(30):
            try:
                with urllib.request.urlopen(f"{URL}/health", timeout=1) as resp:
                    if resp.status == 200:
                        ready = True
                        break
            except Exception:
                time.sleep(0.5)

        if not ready:
            raise RuntimeError("Server failed to respond on health check.")

        print("Server is ready on", URL)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)

            viewports = [
                {"name": "390x844", "width": 390, "height": 844, "is_mobile": True},
                {"name": "1280x800", "width": 1280, "height": 800, "is_mobile": False}
            ]

            for vp in viewports:
                vp_name = vp["name"]
                print(f"\n--- CAPTURING VIEWPORT {vp_name} ---")
                context = browser.new_context(
                    viewport={"width": vp["width"], "height": vp["height"]},
                    is_mobile=vp["is_mobile"],
                    has_touch=vp["is_mobile"]
                )
                page = context.new_page()

                # 1. Login Screen
                page.goto(URL)
                page.wait_for_selector("#auth-view:not(.hidden)", timeout=8000)
                time.sleep(0.5)
                page.screenshot(path=str(SCREENSHOT_DIR / f"01_login_{vp_name}.png"))
                print(f"Captured: 01_login_{vp_name}.png")

                # 2. Sign Up Screen
                switch_subview(page, "auth-signup-view")
                page.fill("#signup-password", "StrongPass2026!#")
                time.sleep(0.5)
                page.screenshot(path=str(SCREENSHOT_DIR / f"02_signup_{vp_name}.png"))
                print(f"Captured: 02_signup_{vp_name}.png")

                # 3. Forgot Password Screen
                switch_subview(page, "auth-forgot-view")
                page.fill("#forgot-email", "gokul@example.com")
                time.sleep(0.5)
                page.screenshot(path=str(SCREENSHOT_DIR / f"03_forgot_{vp_name}.png"))
                print(f"Captured: 03_forgot_{vp_name}.png")

                # 4. Reset Password Screen
                switch_subview(page, "auth-reset-view")
                page.fill("#reset-new-password", "NewPass2026!#")
                page.fill("#reset-confirm-password", "NewPass2026!#")
                time.sleep(0.5)
                page.screenshot(path=str(SCREENSHOT_DIR / f"04_reset_{vp_name}.png"))
                print(f"Captured: 04_reset_{vp_name}.png")

                # 5. Email Verification Screen
                switch_subview(page, "auth-verify-view")
                page.evaluate("document.getElementById('verify-email-display').textContent = 'gokul@example.com';")
                time.sleep(0.5)
                page.screenshot(path=str(SCREENSHOT_DIR / f"05_verify_email_{vp_name}.png"))
                print(f"Captured: 05_verify_email_{vp_name}.png")

                # 6. Authenticated Chat View
                test_email = f"user_{vp_name.replace('x', '_')}_{uuid.uuid4().hex[:6]}@example.com"
                page.evaluate(f"""async () => {{
                    await fetch('/api/auth/signup', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{name: 'Gokul', email: '{test_email}', password: 'Password123!', confirm_password: 'Password123!'}})
                    }});
                }}""")
                from backend.email_service import get_last_email_code
                code = get_last_email_code(test_email)
                if code:
                    page.evaluate(f"""async () => {{
                        await fetch('/api/auth/verify-email', {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/json'}},
                            body: JSON.stringify({{email: '{test_email}', code: '{code}'}})
                        }});
                    }}""")

                page.goto(URL)
                # Ensure auth-view is hidden and user name is set
                page.evaluate("""() => {
                    const av = document.getElementById('auth-view');
                    if (av) av.classList.add('hidden');
                    const wn = document.getElementById('welcome-user-name');
                    if (wn) wn.textContent = 'Gokul';
                    const dn = document.getElementById('user-display-name');
                    if (dn) dn.textContent = 'Gokul';
                    const init = document.getElementById('user-avatar-initial');
                    if (init) init.textContent = 'G';
                }""")
                time.sleep(1)
                page.screenshot(path=str(SCREENSHOT_DIR / f"06_chat_authenticated_{vp_name}.png"))
                print(f"Captured: 06_chat_authenticated_{vp_name}.png")

                # 7. Account & Memory Settings Modal - Profile Tab
                page.evaluate("""() => {
                    const sm = document.getElementById('account-settings-modal');
                    if (sm) sm.classList.remove('hidden');
                    const tabP = document.getElementById('settings-panel-profile');
                    if (tabP) tabP.classList.remove('hidden');
                    const tabM = document.getElementById('settings-panel-memories');
                    if (tabM) tabM.classList.add('hidden');
                    const sn = document.getElementById('settings-user-name');
                    if (sn) sn.textContent = 'Gokul';
                    const se = document.getElementById('settings-user-email');
                    if (se) se.textContent = '""" + test_email + """';
                }""")
                time.sleep(0.5)
                page.screenshot(path=str(SCREENSHOT_DIR / f"07_settings_profile_{vp_name}.png"))
                print(f"Captured: 07_settings_profile_{vp_name}.png")

                # 8. Account & Memory Settings Modal - Memories Tab
                page.evaluate("""() => {
                    const tabP = document.getElementById('settings-panel-profile');
                    if (tabP) tabP.classList.add('hidden');
                    const tabM = document.getElementById('settings-panel-memories');
                    if (tabM) tabM.classList.remove('hidden');
                    const tabProfileBtn = document.getElementById('settings-tab-profile-btn');
                    const tabMemoriesBtn = document.getElementById('settings-tab-memories-btn');
                    if (tabProfileBtn && tabMemoriesBtn) {
                        tabMemoriesBtn.className = 'flex-1 py-3 px-4 text-xs font-semibold text-spider-400 border-b-2 border-spider-400 flex items-center justify-center gap-2 transition-all';
                        tabProfileBtn.className = 'flex-1 py-3 px-4 text-xs font-semibold text-slate-400 hover:text-slate-200 border-b-2 border-transparent flex items-center justify-center gap-2 transition-all';
                    }
                    const listEl = document.getElementById('memories-list');
                    if (listEl) {
                        listEl.innerHTML = `
                            <div class="flex items-center justify-between p-2.5 rounded-lg bg-dark-900 border border-spider-500/10 text-xs">
                                <div class="min-w-0 flex-1 mr-2">
                                    <div class="font-mono text-[11px] text-spider-400">preferred_language</div>
                                    <div class="text-slate-200 truncate">Python 3.11 with FastAPI</div>
                                </div>
                            </div>
                            <div class="flex items-center justify-between p-2.5 rounded-lg bg-dark-900 border border-spider-500/10 text-xs">
                                <div class="min-w-0 flex-1 mr-2">
                                    <div class="font-mono text-[11px] text-spider-400">reply_style</div>
                                    <div class="text-slate-200 truncate">Concise, direct, code-first</div>
                                </div>
                            </div>
                        `;
                    }
                    const countEl = document.getElementById('memories-count');
                    if (countEl) countEl.textContent = '2';
                }""")
                time.sleep(0.5)
                page.screenshot(path=str(SCREENSHOT_DIR / f"08_settings_memories_{vp_name}.png"))
                print(f"Captured: 08_settings_memories_{vp_name}.png")

                context.close()

            browser.close()

        print("\n✅ All screenshots captured successfully in", SCREENSHOT_DIR)

    finally:
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    main()
