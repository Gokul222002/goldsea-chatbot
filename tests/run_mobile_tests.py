import os
import sys
import time
import json
import math
import sqlite3
import subprocess
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple

from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright

ROOT_DIR = Path(__file__).resolve().parent.parent
TEST_DB_PATH = Path(__file__).resolve().parent / "mobile_test_temp.db"
SCREENSHOT_DIR = Path(__file__).resolve().parent / "mobile_screenshots"
BASELINE_DIR = SCREENSHOT_DIR / "baseline"
AFTER_DIR = SCREENSHOT_DIR / "after"

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 18765
BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"


def seed_test_database() -> str:
    """Creates a clean temporary SQLite DB with a realistic long conversation."""
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()

    os.environ["DATABASE_PATH"] = str(TEST_DB_PATH)
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))

    from backend.database import init_db, create_conversation, save_message

    init_db()

    conv_id = "conv_mobile_test_01"
    create_conversation(conv_id, title="Very Long Mobile Responsive Engineering Test Conversation Title That Truncates")

    # Seed extra sidebar conversations for drawer testing
    create_conversation("conv_mobile_test_02", title="Python Async FastAPI Optimization")
    create_conversation("conv_mobile_test_03", title="Render Deployment Notes")

    # Message 1: Long normal user message (for >= 25 chars/line test on 360px)
    save_message(
        msg_id="msg_u1",
        conv_id=conv_id,
        role="user",
        content=(
            "Hey GoldSea AI, can you explain how Flexbox min-width zero works in responsive mobile web layouts, "
            "and also include a Python example, a markdown comparison table, and a long reference URL?"
        ),
    )

    # Message 2: Assistant message with long prose, long unbreakable URL, code block, table, sources, chips
    long_assistant_md = (
        "When building a full-height chat layout with a sidebar and a main column, the main flex container must specify "
        "`min-width: 0` so long child elements never force the flex column wider than the phone screen.\n\n"
        "Reference specification link for deep review:\n"
        "https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_flexible_box_layout/Controlling_ratios_of_flex_items_along_the_main_axis_very_long_token_1234567890\n\n"
        "### Wide Code Example\n"
        "```python\n"
        "def verify_responsive_viewport_layout(viewport_width: int, drawer_open: bool, element_selectors: list[str]) -> dict:\n"
        "    return {'viewport_width': viewport_width, 'drawer_open': drawer_open, 'status': 'verified_no_horizontal_overflow'}\n"
        "```\n\n"
        "### Responsive Breakpoints Comparison\n"
        "| Device Class | Viewport Width | Sidebar Mode | Bubble Max Width | Input Button Size | Keyboard Handling |\n"
        "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
        "| Small Android | 360px | Fixed Overlay Drawer | 92% Width | 44x44px Touch | visualViewport Resize |\n"
        "| Standard Phone | 390px | Fixed Overlay Drawer | 92% Width | 44x44px Touch | visualViewport Resize |\n"
        "| Large Phone | 430px | Fixed Overlay Drawer | 92% Width | 44x44px Touch | visualViewport Resize |\n"
        "| Tablet / Desktop | 768px+ | Persistent Left Rail | 672px Centered | Compact Icon Bar | Standard Flow |\n"
    )
    save_message(
        msg_id="msg_a1",
        conv_id=conv_id,
        role="assistant",
        content=long_assistant_md,
        sources=[
            {"title": "MDN CSS Flexbox Guide", "url": "https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_flexible_box_layout"},
            {"title": "VisualViewport API Spec", "url": "https://developer.mozilla.org/en-US/docs/Web/API/VisualViewport"},
        ],
        follow_up_chips=[
            "Show visualViewport listener code",
            "Explain CSS safe-area-inset-bottom",
            "How to test touch swipe gestures?",
        ],
    )

    # Message 3 & 4: Additional message pair to make conversation scrollable
    save_message(
        msg_id="msg_u2",
        conv_id=conv_id,
        role="user",
        content="Does wrapping code blocks and tables inside overflow-x auto keep the outer chat column locked cleanly inside 360px?",
    )
    save_message(
        msg_id="msg_a2",
        conv_id=conv_id,
        role="assistant",
        content=(
            "Yes! As long as every flex ancestor has `min-width: 0` and the root container uses `overflow-x: hidden; max-width: 100vw`, "
            "each individual `<pre>` code block and table wrapper scrolls horizontally inside its own container while the page stays locked cleanly to the screen width."
        ),
        follow_up_chips=["Summarize mobile checklist", "Verify desktop unchanged", "Explain PWA cache busting"],
    )

    return conv_id


def start_server() -> subprocess.Popen:
    env = os.environ.copy()
    env["DATABASE_PATH"] = str(TEST_DB_PATH)
    env["HOST"] = SERVER_HOST
    env["PORT"] = str(SERVER_PORT)

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", SERVER_HOST, "--port", str(SERVER_PORT)],
        cwd=str(ROOT_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    import urllib.request
    for _ in range(40):
        try:
            with urllib.request.urlopen(f"{BASE_URL}/health", timeout=1.0) as resp:
                if resp.status == 200:
                    return proc
        except Exception:
            time.sleep(0.25)

    proc.terminate()
    raise RuntimeError("Local test server failed to start within 10s.")


def measure_avg_chars_per_line(page, selector: str) -> float:
    """Uses DOM Range getClientRects to measure actual visual wrapped line lengths inside a message bubble."""
    return page.evaluate(
        """(sel) => {
            const el = document.querySelector(sel);
            if (!el) return 0;
            const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
            let targetNode = null;
            let bestLen = 0;
            while (walker.nextNode()) {
                const txt = walker.currentNode.textContent.trim();
                if (txt.length > bestLen && !txt.includes('http')) {
                    bestLen = txt.length;
                    targetNode = walker.currentNode;
                }
            }
            if (!targetNode) return 0;

            const text = targetNode.textContent;
            const range = document.createRange();
            const lines = [];
            let currentTop = null;
            let currentLineChars = 0;

            for (let i = 0; i < text.length; i++) {
                range.setStart(targetNode, i);
                range.setEnd(targetNode, i + 1);
                const rects = range.getClientRects();
                if (!rects.length) continue;
                const top = Math.round(rects[0].top);
                if (currentTop === null) {
                    currentTop = top;
                } else if (Math.abs(top - currentTop) > 4) {
                    if (currentLineChars > 0) lines.push(currentLineChars);
                    currentTop = top;
                    currentLineChars = 0;
                }
                if (text[i].trim() !== '' || currentLineChars > 0) {
                    currentLineChars++;
                }
            }
            if (currentLineChars > 0) lines.push(currentLineChars);
            if (lines.length <= 1) return lines[0] || text.trim().length;
            // Exclude last partial line when averaging full wrapped lines
            const fullLines = lines.slice(0, -1);
            const sum = fullLines.reduce((a, b) => a + b, 0);
            return sum / fullLines.length;
        }""",
        selector,
    )


def _diff_region_pct(crop_a: Image.Image, crop_b: Image.Image) -> float:
    diff = ImageChops.difference(crop_a, crop_b)
    pixels = diff.get_flattened_data() if hasattr(diff, "get_flattened_data") else diff.getdata()
    changed = sum(1 for r, g, b in pixels if (r > 12 or g > 12 or b > 12))
    total = crop_a.size[0] * crop_a.size[1]
    return (changed / total) * 100.0 if total else 0.0


def compute_desktop_visual_diff(img_a_path: Path, img_b_path: Path) -> Dict[str, Any]:
    """Compares fixed desktop chrome strictly and scrollable message viewport with scroll-offset alignment."""
    img_a = Image.open(img_a_path).convert("RGB")
    img_b = Image.open(img_b_path).convert("RGB")
    if img_a.size != img_b.size:
        img_b = img_b.resize(img_a.size)

    raw_diff_pct = _diff_region_pct(img_a, img_b)

    # Fixed UI Chrome regions on 1280x800: sidebar (0..288), top header (288..1280, 0..56), input dock (288..1280, 698..800)
    chrome_boxes = [
        (0, 0, 288, 800),
        (288, 0, 1280, 56),
        (288, 698, 1280, 800),
    ]
    chrome_changed = 0
    chrome_total = 0
    for box in chrome_boxes:
        ca = img_a.crop(box)
        cb = img_b.crop(box)
        diff = ImageChops.difference(ca, cb)
        pixels = diff.get_flattened_data() if hasattr(diff, "get_flattened_data") else diff.getdata()
        chrome_changed += sum(1 for r, g, b in pixels if (r > 12 or g > 12 or b > 12))
        chrome_total += ca.size[0] * ca.size[1]
    chrome_diff_pct = (chrome_changed / chrome_total) * 100.0

    # Scrollable chat pane excluding scrollbar gutter (x: 288..1264, y: 56..698)
    top, bottom = 56, 698
    left, right = 288, 1264
    pane_h = bottom - top
    pane_w = right - left

    # Coarse scan over dy in [-260, 260] using 1/4-scale grayscale crops (<0.05s)
    small_a = img_a.crop((left, top, right, bottom)).convert("L").resize((pane_w // 4, pane_h // 4))
    small_b = img_b.crop((left, top, right, bottom)).convert("L").resize((pane_w // 4, pane_h // 4))
    from PIL import ImageStat
    coarse_best_dy = 0
    coarse_best_mean = 999.0
    sw, sh = small_a.size
    for sdy in range(-65, 66):
        s_top = max(0, -sdy)
        s_bot = min(sh, sh - sdy)
        d_top = s_top + sdy
        d_bot = s_bot + sdy
        if (s_bot - s_top) < sh // 2:
            continue
        ca = small_a.crop((0, s_top, sw, s_bot))
        cb = small_b.crop((0, d_top, sw, d_bot))
        mean_diff = ImageStat.Stat(ImageChops.difference(ca, cb)).mean[0]
        if mean_diff < coarse_best_mean:
            coarse_best_mean = mean_diff
            coarse_best_dy = sdy * 4

    # Fine 1px full-resolution refinement around coarse_best_dy
    best_content_diff = 100.0
    best_dy = coarse_best_dy
    for dy in range(coarse_best_dy - 8, coarse_best_dy + 9):
        src_top = max(top, top - dy)
        src_bottom = min(bottom, bottom - dy)
        dst_top = src_top + dy
        dst_bottom = src_bottom + dy
        if (src_bottom - src_top) < pane_h // 2:
            continue
        ca = img_a.crop((left, src_top, right, src_bottom))
        cb = img_b.crop((left, dst_top, right, dst_bottom))
        pct = _diff_region_pct(ca, cb)
        if pct < best_content_diff:
            best_content_diff = pct
            best_dy = dy

    return {
        "raw_diff_pct": round(raw_diff_pct, 2),
        "chrome_diff_pct": round(chrome_diff_pct, 2),
        "content_scroll_aligned_diff_pct": round(best_content_diff, 2),
        "scroll_offset_dy_px": best_dy,
    }


def run_viewport_checks(playwright, conv_id: str, out_dir: Path, is_baseline: bool) -> List[Dict[str, Any]]:
    viewports = [
        {"name": "mobile_360", "width": 360, "height": 800, "is_mobile": True, "has_touch": True},
        {"name": "mobile_390", "width": 390, "height": 844, "is_mobile": True, "has_touch": True},
        {"name": "mobile_430", "width": 430, "height": 932, "is_mobile": True, "has_touch": True},
        {"name": "tablet_768", "width": 768, "height": 1024, "is_mobile": True, "has_touch": True},
        {"name": "desktop_1280", "width": 1280, "height": 800, "is_mobile": False, "has_touch": False},
    ]

    browser = playwright.chromium.launch(headless=True)
    report = []

    try:
        for vp in viewports:
            name = vp["name"]
            width = vp["width"]
            height = vp["height"]
            is_mobile_bp = width < 768

            context = browser.new_context(
                viewport={"width": width, "height": height},
                is_mobile=vp["is_mobile"],
                has_touch=vp["has_touch"],
            )
            page = context.new_page()

            # Pre-seed localStorage active conversation BEFORE navigation so the long chat loads immediately
            page.add_init_script(f"localStorage.setItem('goldsea_active_conv', '{conv_id}');")
            page.goto(BASE_URL, wait_until="networkidle")
            page.wait_for_selector("#msg-msg_a1", timeout=10000)
            page.wait_for_timeout(400)

            metrics = page.evaluate(
                """() => {
                    const sw = document.documentElement.scrollWidth;
                    const iw = window.innerWidth;
                    const ih = window.innerHeight;
                    const sidebar = document.getElementById('sidebar');
                    const main = document.querySelector('main');
                    const sRect = sidebar ? sidebar.getBoundingClientRect() : null;
                    const mRect = main ? main.getBoundingClientRect() : null;
                    const sStyle = sidebar ? getComputedStyle(sidebar) : null;

                    const btnIds = ['attach-file-btn', 'voice-input-btn', 'send-btn'];
                    const buttons = btnIds.map(id => {
                        const el = document.getElementById(id);
                        if (!el) return {id, exists: false};
                        const r = el.getBoundingClientRect();
                        const st = getComputedStyle(el);
                        return {
                            id,
                            exists: true,
                            visible: st.display !== 'none' && st.visibility !== 'hidden' && r.width > 0 && r.height > 0,
                            width: Math.round(r.width * 10) / 10,
                            height: Math.round(r.height * 10) / 10,
                            inViewport: r.left >= -1 && r.right <= iw + 1 && r.top >= -1 && r.bottom <= ih + 1
                        };
                    });

                    const inp = document.getElementById('chat-input');
                    const iRect = inp ? inp.getBoundingClientRect() : null;
                    const userBubble = document.querySelector('#msg-msg_u1 > div');
                    const asstProse = document.querySelector('#msg-msg_a1 .prose');
                    const asstBubble = document.querySelector('#msg-msg_a1 > div');
                    const headerBtns = ['open-sidebar-btn', 'open-quick-actions-btn', 'header-new-chat-btn'].map(id => {
                        const el = document.getElementById(id);
                        if (!el) return {id, exists: false};
                        const r = el.getBoundingClientRect();
                        const st = getComputedStyle(el);
                        return {
                            id,
                            visible: st.display !== 'none' && r.width > 0 && r.height > 0,
                            width: Math.round(r.width * 10) / 10,
                            height: Math.round(r.height * 10) / 10
                        };
                    });
                    const quickTextVisible = Array.from(document.querySelectorAll('#open-quick-actions-btn span')).some(sp => getComputedStyle(sp).display !== 'none');
                    const enterHintVisible = Array.from(document.querySelectorAll('.touch-hide')).some(el => getComputedStyle(el).display !== 'none');
                    const preEl = document.querySelector('#msg-msg_a1 pre');
                    const tableWrapEl = document.querySelector('#msg-msg_a1 .table-scroll-wrap');
                    const viewportMeta = document.querySelector('meta[name="viewport"]')?.content || '';

                    return {
                        scrollWidth: sw,
                        innerWidth: iw,
                        innerHeight: ih,
                        sidebarRect: sRect ? {left: sRect.left, right: sRect.right, width: sRect.width, position: sStyle.position, bg: sStyle.backgroundColor} : null,
                        mainRect: mRect ? {left: mRect.left, right: mRect.right, width: mRect.width} : null,
                        buttons,
                        headerBtns,
                        quickTextVisible,
                        enterHintVisible,
                        viewportMeta,
                        userBubbleWidth: userBubble ? Math.round(userBubble.getBoundingClientRect().width) : 0,
                        userFontSize: userBubble ? getComputedStyle(userBubble).fontSize : null,
                        asstBubbleWidth: asstBubble ? Math.round(asstBubble.getBoundingClientRect().width) : 0,
                        asstProseFontSize: asstProse ? getComputedStyle(asstProse).fontSize : null,
                        preOverflowContained: preEl ? (preEl.getBoundingClientRect().width <= (mRect?.width || iw) + 1 && getComputedStyle(preEl).overflowX === 'auto') : false,
                        tableOverflowContained: tableWrapEl ? (tableWrapEl.getBoundingClientRect().width <= (mRect?.width || iw) + 1 && getComputedStyle(tableWrapEl).overflowX === 'auto') : false,
                        input: iRect ? {
                            width: Math.round(iRect.width),
                            height: Math.round(iRect.height),
                            left: Math.round(iRect.left),
                            right: Math.round(iRect.right),
                            bottom: Math.round(iRect.bottom),
                            inViewport: iRect.left >= 0 && iRect.right <= iw + 1 && iRect.bottom <= ih + 1 && iRect.width > 50,
                            fontSize: getComputedStyle(inp).fontSize
                        } : null
                    };
                }"""
            )

            avg_chars_user = measure_avg_chars_per_line(page, "#msg-msg_u1 div")
            avg_chars_asst = measure_avg_chars_per_line(page, "#msg-msg_a1 .prose p")
            metrics["avg_chars_user"] = round(avg_chars_user, 1)
            metrics["avg_chars_asst"] = round(avg_chars_asst, 1)

            # Screenshot initial state (closed drawer on mobile, normal on tablet/desktop)
            page.screenshot(path=str(out_dir / f"{name}_closed.png"))

            drawer_checks = {}
            if is_mobile_bp and not is_baseline:
                # 1) Scroll up slightly to inspect code block & table screenshot on 360
                if name == "mobile_360":
                    page.locator("#msg-msg_a1 pre").scroll_into_view_if_needed()
                    page.wait_for_timeout(200)
                    page.screenshot(path=str(out_dir / "mobile_360_long_chat_code.png"))
                    page.evaluate("document.getElementById('messages-container').scrollTop = document.getElementById('messages-container').scrollHeight;")

                # 2) Open drawer with hamburger
                page.click("#open-sidebar-btn")
                page.wait_for_timeout(300)
                open_rect = page.evaluate("""() => {
                    const s = document.getElementById('sidebar').getBoundingClientRect();
                    const b = document.getElementById('sidebar-backdrop');
                    const m = document.querySelector('main').getBoundingClientRect();
                    return {
                        sidebarLeft: s.left,
                        sidebarRight: s.right,
                        sidebarWidth: s.width,
                        backdropVisible: !b.classList.contains('hidden'),
                        mainWidthWhileOpen: m.width
                    };
                }""")
                drawer_checks["opened"] = open_rect
                if name == "mobile_360":
                    page.screenshot(path=str(out_dir / "mobile_360_open_drawer.png"))

                # 3) Close by clicking backdrop
                page.click("#sidebar-backdrop", position={"x": width - 10, "y": height // 2})
                page.wait_for_timeout(300)
                closed_after_backdrop = page.evaluate("document.getElementById('sidebar').getBoundingClientRect().right <= 1")
                drawer_checks["closed_by_backdrop"] = closed_after_backdrop

                # 4) Reopen & test swipe-left gesture to close
                page.click("#open-sidebar-btn")
                page.wait_for_timeout(300)
                page.evaluate("""() => {
                    const sb = document.getElementById('sidebar');
                    const tStart = new Touch({identifier: 1, target: sb, clientX: 220, clientY: 200});
                    const tMove = new Touch({identifier: 1, target: sb, clientX: 80, clientY: 200});
                    const tEnd = new Touch({identifier: 1, target: sb, clientX: 60, clientY: 200});
                    sb.dispatchEvent(new TouchEvent('touchstart', {touches: [tStart], changedTouches: [tStart], bubbles: true}));
                    sb.dispatchEvent(new TouchEvent('touchmove', {touches: [tMove], changedTouches: [tMove], bubbles: true}));
                    sb.dispatchEvent(new TouchEvent('touchend', {touches: [], changedTouches: [tEnd], bubbles: true}));
                }""")
                page.wait_for_timeout(300)
                closed_by_swipe = page.evaluate("document.getElementById('sidebar').getBoundingClientRect().right <= 1")
                drawer_checks["closed_by_swipe"] = closed_by_swipe

                # 5) Keyboard-open simulation on 360x800 (shrink height to 460px to emulate soft keyboard)
                if name == "mobile_360":
                    page.set_viewport_size({"width": 360, "height": 460})
                    page.focus("#chat-input")
                    page.wait_for_timeout(250)
                    kb_metrics = page.evaluate("""() => {
                        const inp = document.getElementById('chat-input').getBoundingClientRect();
                        const send = document.getElementById('send-btn').getBoundingClientRect();
                        return {
                            scrollWidth: document.documentElement.scrollWidth,
                            innerWidth: window.innerWidth,
                            innerHeight: window.innerHeight,
                            inputBottom: inp.bottom,
                            sendBottom: send.bottom,
                            visibleAboveKeyboard: inp.bottom <= window.innerHeight + 1 && send.bottom <= window.innerHeight + 1
                        };
                    }""")
                    drawer_checks["keyboard_open"] = kb_metrics
                    page.screenshot(path=str(out_dir / "mobile_360_keyboard.png"))

                    # 6) Reopen drawer at normal size & tap another conversation to verify auto-close on chat selection
                    page.set_viewport_size({"width": 360, "height": 800})
                    page.click("#open-sidebar-btn")
                    page.wait_for_timeout(300)
                    other_conv = page.locator("#conversations-list > div", has_text="Python Async FastAPI Optimization").first
                    other_conv.click()
                    page.wait_for_timeout(350)
                    closed_on_select = page.evaluate("""() => {
                        const s = document.getElementById('sidebar').getBoundingClientRect();
                        const title = document.getElementById('active-chat-title').textContent.trim();
                        return { right: s.right, title };
                    }""")
                    drawer_checks["closed_on_chat_select"] = closed_on_select

                    # 7) Verify Quick Actions icon opens quick-actions modal cleanly & check /sw.js + /manifest.json
                    page.click("#open-quick-actions-btn")
                    page.wait_for_timeout(150)
                    qa_open = page.evaluate("!document.getElementById('quick-actions-modal').classList.contains('hidden')")
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(100)
                    pwa_meta = page.evaluate("""async () => {
                        const swRes = await fetch('/sw.js');
                        const swText = await swRes.text();
                        const manRes = await fetch('/manifest.json');
                        const manJson = await manRes.json();
                        return {
                            swStatus: swRes.status,
                            hasCacheV2: swText.includes('goldsea-v2'),
                            hasSkipWaiting: swText.includes('skipWaiting'),
                            hasClientsClaim: swText.includes('clients.claim'),
                            hasCacheDelete: swText.includes('caches.delete'),
                            manifestStatus: manRes.status,
                            display: manJson.display,
                            iconsCount: (manJson.icons || []).length
                        };
                    }""")
                    drawer_checks["quick_actions_modal_opens"] = qa_open
                    drawer_checks["pwa_assets"] = pwa_meta

            metrics["drawer_checks"] = drawer_checks

            # Evaluate pass/fail assertions if not baseline
            failures = []
            if not is_baseline:
                if metrics["scrollWidth"] > metrics["innerWidth"]:
                    failures.append(f"Horizontal overflow: scrollWidth={metrics['scrollWidth']} > innerWidth={metrics['innerWidth']}")

                if is_mobile_bp:
                    if not metrics["sidebarRect"] or metrics["sidebarRect"]["right"] > 1:
                        failures.append(f"Sidebar not closed on first load: {metrics['sidebarRect']}")
                    if not metrics["mainRect"] or metrics["mainRect"]["width"] < width * 0.90:
                        failures.append(f"Main chat column < 90% width: {metrics['mainRect']}")
                    if not drawer_checks.get("opened") or drawer_checks["opened"]["sidebarLeft"] < -1 or drawer_checks["opened"]["sidebarWidth"] > min(width * 0.85, 320) + 2:
                        failures.append(f"Opened drawer sizing wrong: {drawer_checks.get('opened')}")
                    if abs(drawer_checks["opened"]["mainWidthWhileOpen"] - metrics["mainRect"]["width"]) > 2:
                        failures.append("Drawer pushed/resized <main> instead of overlaying")
                    if not drawer_checks.get("closed_by_backdrop"):
                        failures.append("Backdrop click failed to close drawer")
                    if not drawer_checks.get("closed_by_swipe"):
                        failures.append("Swipe-left failed to close drawer")
                    if "viewport-fit=cover" not in metrics.get("viewportMeta", "") or "width=device-width" not in metrics.get("viewportMeta", ""):
                        failures.append(f"Viewport meta incomplete: {metrics.get('viewportMeta')}")
                    if metrics.get("quickTextVisible"):
                        failures.append("Quick Actions label / Ctrl+K hint visible on mobile top bar")
                    if metrics.get("enterHintVisible"):
                        failures.append("Desktop Enter/Shift+Enter hint visible on mobile touch viewport")
                    if metrics.get("userFontSize") != "16px" or metrics.get("asstProseFontSize") != "16px":
                        failures.append(f"Mobile message font size != 16px: user={metrics.get('userFontSize')}, asst={metrics.get('asstProseFontSize')}")
                    if metrics.get("input", {}).get("fontSize") != "16px":
                        failures.append(f"Mobile textarea fontSize != 16px: {metrics.get('input', {}).get('fontSize')}")
                    if metrics.get("userBubbleWidth", 0) > width * 0.92 + 2 or metrics.get("asstBubbleWidth", 0) > width * 0.92 + 2:
                        failures.append(f"Bubble exceeds 92% width: user={metrics.get('userBubbleWidth')}, asst={metrics.get('asstBubbleWidth')} vs 92%={width*0.92:.1f}")
                    if not metrics.get("preOverflowContained") or not metrics.get("tableOverflowContained"):
                        failures.append(f"Code/table horizontal scroll wrapper issue: pre={metrics.get('preOverflowContained')}, table={metrics.get('tableOverflowContained')}")
                    for hb in metrics.get("headerBtns", []):
                        if not (hb.get("visible") and hb.get("width", 0) >= 44 and hb.get("height", 0) >= 44):
                            failures.append(f"Header button {hb.get('id')} < 44px or hidden on mobile: {hb}")

                    if name == "mobile_360":
                        if avg_chars_user < 25 or avg_chars_asst < 25:
                            failures.append(f"Narrow wrapping detected (avg chars: user={avg_chars_user}, asst={avg_chars_asst})")
                        if not drawer_checks.get("keyboard_open", {}).get("visibleAboveKeyboard"):
                            failures.append(f"Input bar cut off during keyboard open: {drawer_checks.get('keyboard_open')}")
                        sel = drawer_checks.get("closed_on_chat_select", {})
                        if not sel or sel.get("right", 99) > 1 or "Python Async" not in sel.get("title", ""):
                            failures.append(f"Drawer did not close on chat selection: {sel}")
                        if not drawer_checks.get("quick_actions_modal_opens"):
                            failures.append("Quick Actions icon did not open quick-actions-modal on mobile")
                        pwa = drawer_checks.get("pwa_assets", {})
                        if not (pwa.get("swStatus") == 200 and pwa.get("hasCacheV2") and pwa.get("hasSkipWaiting") and pwa.get("hasClientsClaim") and pwa.get("hasCacheDelete") and pwa.get("manifestStatus") == 200 and pwa.get("display") == "standalone" and pwa.get("iconsCount", 0) >= 2):
                            failures.append(f"PWA service worker / manifest assertion failed: {pwa}")

                    for b in metrics["buttons"]:
                        if not (b["visible"] and b["inViewport"] and b["width"] >= 44 and b["height"] >= 44):
                            failures.append(f"Button {b['id']} failed mobile check (>=44px & visible): {b}")
                else:
                    # Tablet/Desktop >= 768px: persistent sidebar visible
                    if not metrics["sidebarRect"] or metrics["sidebarRect"]["width"] < 200 or metrics["sidebarRect"]["left"] < 0:
                        failures.append(f"Desktop/tablet persistent sidebar missing: {metrics['sidebarRect']}")
                    for b in metrics["buttons"]:
                        if not (b["visible"] and b["inViewport"]):
                            failures.append(f"Button {b['id']} not visible on desktop: {b}")

                if not metrics["input"] or not metrics["input"]["inViewport"]:
                    failures.append(f"Textarea input not properly inside viewport: {metrics['input']}")

                if name == "desktop_1280":
                    baseline_desktop = BASELINE_DIR / "desktop_1280_closed.png"
                    if baseline_desktop.exists():
                        diff_info = compute_desktop_visual_diff(baseline_desktop, out_dir / f"{name}_closed.png")
                        metrics["desktop_pixel_diff"] = diff_info
                        if diff_info["chrome_diff_pct"] > 1.5 or diff_info["content_scroll_aligned_diff_pct"] > 2.5:
                            failures.append(
                                f"Desktop 1280 screenshot diff too high: chrome={diff_info['chrome_diff_pct']}%, "
                                f"content_aligned={diff_info['content_scroll_aligned_diff_pct']}% (dy={diff_info['scroll_offset_dy_px']}px)"
                            )

            report.append({"viewport": name, "width": width, "height": height, "metrics": metrics, "failures": failures})
            context.close()
    finally:
        browser.close()

    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", action="store_true", help="Capture baseline 'before' screenshots on main without failing assertions")
    args = parser.parse_args()

    out_dir = BASELINE_DIR if args.baseline else AFTER_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    conv_id = seed_test_database()
    server_proc = start_server()

    try:
        with sync_playwright() as p:
            report = run_viewport_checks(p, conv_id, out_dir, is_baseline=args.baseline)
    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except Exception:
            server_proc.kill()
        if TEST_DB_PATH.exists():
            try:
                TEST_DB_PATH.unlink()
            except Exception:
                pass

    mode_label = "BASELINE (BEFORE)" if args.baseline else "MOBILE FIX VERIFICATION (AFTER)"
    print("=" * 75)
    print(f"GOLDSEA AI PLAYWRIGHT SUITE - {mode_label}")
    print("=" * 75)

    all_ok = True
    for item in report:
        m = item["metrics"]
        fails = item["failures"]
        status = "PASS" if not fails else "FAIL"
        if fails:
            all_ok = False
        print(
            f"[{status}] {item['viewport']:<13} | "
            f"scrollW={m['scrollWidth']}/{m['innerWidth']} | "
            f"mainW={round(m['mainRect']['width']) if m['mainRect'] else 0} | "
            f"sidebarRight={round(m['sidebarRect']['right']) if m['sidebarRect'] else 'N/A'} | "
            f"chars/line(u/a)={m['avg_chars_user']}/{m['avg_chars_asst']}"
        )
        if "desktop_pixel_diff" in m:
            d = m["desktop_pixel_diff"]
            print(
                f"       Desktop 1280 diff vs baseline: chrome={d['chrome_diff_pct']}%, "
                f"content_aligned={d['content_scroll_aligned_diff_pct']}% (dy={d['scroll_offset_dy_px']}px, raw={d['raw_diff_pct']}%)"
            )
        for f in fails:
            print(f"       -> FAILURE: {f}")

    report_file = out_dir / "report.json"
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("=" * 75)
    print(f"Screenshots & JSON report saved to: {out_dir}")
    if not args.baseline and not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
