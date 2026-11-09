import os
import io
import sys
import re
import csv
import json
import wave
import struct
import asyncio
from typing import Dict, Any, List, Tuple
from pathlib import Path

# Ensure root directory is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from PIL import Image, ImageDraw, ImageFont
import pymupdf as fitz
import docx
import openpyxl
import httpx

from backend.main import app


# Directory for temporary test assets
TEST_DIR = Path(__file__).resolve().parent / "test_assets"
TEST_DIR.mkdir(parents=True, exist_ok=True)


def create_test_resume_pdf() -> bytes:
    """Generates synthetic resume PDF with PyMuPDF."""
    doc = fitz.open()
    page = doc.new_page()

    content = (
        "Aarav Sharma\n"
        "Email: aarav.sharma.dev@gmail.com | Phone: +1-555-019-2834\n"
        "Location: Seattle, WA | GitHub: github.com/aaravsharma\n\n"
        "EDUCATION\n"
        "B.Tech in Computer Science, State University\n"
        "Graduation Year: 2024 | CGPA: 9.2\n\n"
        "TECHNICAL SKILLS\n"
        "Languages & Frameworks: Python, FastAPI, PyTorch, React, PostgreSQL, Docker\n\n"
        "PROJECTS\n"
        "1. NeuralSearch: Semantic vector search engine utilizing bi-encoder models with sub-20ms latency.\n"
        "2. CryptoPulse: Real-time cryptocurrency latency monitor processing 50k WebSocket events/sec.\n"
        "3. CloudShield: Kubernetes automated security scanner detecting CVE vulnerabilities in cluster pods."
    )
    rect = fitz.Rect(50, 50, 550, 750)
    page.insert_textbox(rect, content, fontsize=11, fontname="helv")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_test_report_pdf() -> bytes:
    """Generates 3-page synthetic corporate report PDF."""
    doc = fitz.open()
    
    # Page 1
    p1 = doc.new_page()
    p1.insert_text(fitz.Point(50, 80), "QUARTERLY PERFORMANCE REPORT - PAGE 1", fontsize=14, fontname="helv")
    p1.insert_text(fitz.Point(50, 130), "Executive Summary:\nTotal revenue achieved was $42.5 million, exceeding budget targets.", fontsize=11, fontname="helv")

    # Page 2
    p2 = doc.new_page()
    p2.insert_text(fitz.Point(50, 80), "OPERATIONAL INFRASTRUCTURE METRICS - PAGE 2", fontsize=14, fontname="helv")
    p2.insert_text(fitz.Point(50, 130), "Core Systems Reliability:\nCloud server uptime across all datacenters was verified at 99.98%.", fontsize=11, fontname="helv")

    # Page 3
    p3 = doc.new_page()
    p3.insert_text(fitz.Point(50, 80), "FORWARD PROJECTION & EXPANSION - PAGE 3", fontsize=14, fontname="helv")
    p3.insert_text(fitz.Point(50, 130), "Engineering Hiring Roadmap:\nPlanned headcount growth targets hiring 150 new engineers in Q3.", fontsize=11, fontname="helv")

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_test_table_pdf() -> bytes:
    """Generates PDF with sales data table."""
    doc = fitz.open()
    p = doc.new_page()
    p.insert_text(fitz.Point(50, 60), "REGIONAL ANNUAL SALES REPORT", fontsize=14, fontname="helv")

    table_text = (
        "Region     | Q1 Sales | Q2 Sales | Q3 Sales | Q4 Sales\n"
        "----------------------------------------------------\n"
        "North      | 120      | 145      | 160      | 210\n"
        "South      | 90       | 110      | 130      | 175\n"
        "East       | 80       | 95       | 105      | 140\n"
        "West       | 150      | 170      | 190      | 240\n"
    )
    p.insert_textbox(fitz.Rect(50, 90, 550, 300), table_text, fontsize=11, fontname="courier")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_test_scanned_pdf() -> bytes:
    """
    Generates an image-only / scanned PDF.
    Contains zero selectable text in the PDF stream; all text is rendered into a raster bitmap image.
    """
    img = Image.new("RGB", (800, 450), color=(248, 249, 250))
    draw = ImageDraw.Draw(img)
    # Draw border
    draw.rectangle([(20, 20), (780, 430)], outline=(30, 41, 59), width=3)
    # Draw text
    draw.text((40, 50), "CERTIFICATE OF EXCELLENCE", fill=(15, 23, 42))
    draw.text((40, 110), "This honor is awarded to Dr. Elena Vance", fill=(30, 41, 59))
    draw.text((40, 160), "for Breakthrough Quantum Telemetry Research.", fill=(30, 41, 59))
    draw.text((40, 230), "Date of Issuance: October 14, 2025", fill=(71, 85, 105))
    draw.text((40, 280), "Verification ID: QT-88492", fill=(15, 23, 42))

    img_buf = io.BytesIO()
    img.save(img_buf, format="PNG")
    img_bytes = img_buf.getvalue()

    doc = fitz.open()
    page = doc.new_page(width=600, height=350)
    # Insert bitmap image as only content (no font/text objects)
    page.insert_image(fitz.Rect(0, 0, 600, 350), stream=img_bytes)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def create_test_text_screenshot() -> bytes:
    """Generates server console screenshot image."""
    img = Image.new("RGB", (700, 300), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)
    draw.text((30, 30), "[SYSTEM DIAGNOSTICS DASHBOARD]", fill=(56, 189, 248))
    draw.text((30, 80), "Server Status: OK", fill=(74, 222, 128))
    draw.text((30, 130), "Database Latency: 4.2ms", fill=(251, 191, 36))
    draw.text((30, 180), "Active Cluster Nodes: 64", fill=(248, 250, 252))
    draw.text((30, 230), "System Memory Usage: 38%", fill=(248, 250, 252))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_test_chart() -> bytes:
    """Generates clear bar chart image."""
    img = Image.new("RGB", (650, 350), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((40, 25), "Fruit Inventory Distribution (Units)", fill=(15, 23, 42))
    
    # Apples: 45
    draw.rectangle([(60, 180), (160, 280)], fill=(239, 68, 68))
    draw.text((75, 290), "Apples: 45", fill=(15, 23, 42))

    # Bananas: 70
    draw.rectangle([(220, 120), (320, 280)], fill=(234, 179, 8))
    draw.text((230, 290), "Bananas: 70", fill=(15, 23, 42))

    # Cherries: 25
    draw.rectangle([(380, 220), (480, 280)], fill=(168, 85, 247))
    draw.text((385, 290), "Cherries: 25", fill=(15, 23, 42))

    # Baseline axis
    draw.line([(40, 280), (520, 280)], fill=(100, 116, 139), width=2)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_test_drawing() -> bytes:
    """Generates system diagram image with colored shapes."""
    img = Image.new("RGB", (700, 320), color=(241, 245, 249))
    draw = ImageDraw.Draw(img)
    
    # Blue circle: Client
    draw.ellipse([(60, 100), (180, 220)], fill=(59, 130, 246), outline=(29, 78, 216), width=2)
    draw.text((95, 150), "Client", fill=(255, 255, 255))

    # Arrow
    draw.line([(185, 160), (275, 160)], fill=(100, 116, 139), width=3)

    # Green box: API Gateway
    draw.rectangle([(280, 100), (440, 220)], fill=(34, 197, 94), outline=(21, 128, 61), width=2)
    draw.text((310, 150), "API Gateway", fill=(255, 255, 255))

    # Arrow
    draw.line([(445, 160), (515, 160)], fill=(100, 116, 139), width=3)

    # Orange rounded cylinder: Redis Cache
    draw.rectangle([(520, 100), (660, 220)], fill=(249, 115, 22), outline=(194, 65, 12), width=2)
    draw.text((545, 150), "Redis Cache", fill=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_test_handwriting() -> bytes:
    """Generates handwriting-style note image."""
    img = Image.new("RGB", (750, 280), color=(254, 252, 232)) # yellow sticky note tint
    draw = ImageDraw.Draw(img)
    draw.text((40, 40), "IMPORTANT TEAM MEETING NOTE", fill=(113, 63, 18))
    draw.text((40, 100), "Submit quarterly tax filing by Friday 4 PM to John Doe.", fill=(66, 32, 6))
    draw.text((40, 160), "Please make sure receipts are signed and audited.", fill=(66, 32, 6))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_test_code_screenshot() -> bytes:
    """Generates code screenshot image."""
    img = Image.new("RGB", (700, 320), color=(30, 30, 30))
    draw = ImageDraw.Draw(img)
    code = (
        "# Tiered Pricing Calculator\n"
        "def compute_discount(price: float, tier: str) -> float:\n"
        "    if tier == 'VIP':\n"
        "        return price * 0.25\n"
        "    elif tier == 'PREMIUM':\n"
        "        return price * 0.15\n"
        "    return price * 0.05\n"
    )
    draw.text((30, 40), code, fill=(220, 220, 220))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_test_docx() -> bytes:
    """Generates DOCX file."""
    doc = docx.Document()
    doc.add_heading("Project Falcon Architecture", level=1)
    doc.add_paragraph("Project Falcon is our next-generation cloud synchronization engine.")
    doc.add_heading("Key Project Milestones", level=2)
    doc.add_paragraph("Milestone Alpha: Prototype launch on March 15", style="List Bullet")
    doc.add_paragraph("Milestone Beta: Public beta on June 20", style="List Bullet")
    doc.add_paragraph("Milestone Production: Enterprise rollout on October 1", style="List Bullet")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def create_test_xlsx() -> bytes:
    """Generates XLSX spreadsheet."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Inventory"

    headers = ["Item Name", "SKU Code", "Quantity", "Unit Price"]
    ws.append(headers)
    ws.append(["Widget A", "WID-001", 520, "$12.50"])
    ws.append(["Widget B", "WID-002", 310, "$24.00"])
    ws.append(["Sensor Pro", "SEN-990", 85, "$150.00"])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def create_test_csv() -> bytes:
    """Generates CSV document."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Name", "Department", "Job Title", "Salary"])
    writer.writerow(["Alice", "Engineering", "Lead Architect", "145000"])
    writer.writerow(["Bob", "Marketing", "Campaign Manager", "95000"])
    writer.writerow(["Charlie", "Security", "Penetration Tester", "120000"])
    return buf.getvalue().encode("utf-8")


def create_test_txt() -> bytes:
    """Generates plain text note."""
    text = (
        "GoldSea Office Network Configuration:\n"
        "SSID: GoldSea-Guest\n"
        "Security: WPA3-Enterprise\n"
        "Password: SeaBreeze#2026\n"
        "Default Gateway: 192.168.1.1\n"
    )
    return text.encode("utf-8")


def create_test_audio_wav() -> bytes:
    """Generates a valid 1-second 16kHz mono PCM WAV audio file with a synthesized sine tone."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        # 16000 samples of quiet 440Hz tone
        import math
        samples = []
        for i in range(16000):
            val = int(3000 * math.sin(2 * math.pi * 440 * i / 16000))
            samples.append(val)
        data = struct.pack("<" + "h" * len(samples), *samples)
        wf.writeframes(data)
    return buf.getvalue()


def check_answer(response_text: str, expected_phrases: List[str]) -> bool:
    """Checks if the response contains any of the expected key phrases (case-insensitive)."""
    resp_lower = response_text.lower().replace(",", "").replace("-", " ")
    for phrase in expected_phrases:
        p_lower = phrase.lower().replace(",", "").replace("-", " ")
        if p_lower in resp_lower:
            return True
        # Also check word-by-word if phrase has multiple words
        words = p_lower.split()
        if len(words) > 1 and all(w in resp_lower for w in words):
            return True
    return False


async def run_all_tests():
    print("=" * 70)
    print("🚀 STARTING GOLDSEA AI COMPREHENSIVE TEST SUITE")
    print("=" * 70)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=45.0) as client:
        
        test_results = []

        # =====================================================================
        # CATEGORY 1: PDF TESTS (Resume, Multi-page report, Table, Scanned)
        # =====================================================================
        print("\n--- CATEGORY 1: PDF DOCUMENT TESTS ---")
        
        # 1. Resume PDF
        resume_bytes = create_test_resume_pdf()
        res = await client.post("/api/chat/upload", files={"file": ("resume.pdf", resume_bytes, "application/pdf")})
        assert res.status_code == 200, f"Upload failed: {res.text}"
        resume_att = res.json()

        resume_questions = [
            ("What is the email address in the resume?", ["aarav.sharma.dev@gmail.com"]),
            ("What is the CGPA of Aarav Sharma?", ["9.2"]),
            ("How many projects are listed in the resume?", ["3", "three"]),
            ("What is the phone number listed?", ["+1-555-019-2834", "555-019-2834", "555 019 2834"]),
            ("What is the name of the Kubernetes automated security scanner project?", ["CloudShield"]),
        ]
        for q, expected in resume_questions:
            chat_res = await client.post("/api/chat", json={
                "message": q,
                "attachments": [resume_att]
            })
            ans = chat_res.json().get("content", "")
            passed = check_answer(ans, expected)
            test_results.append({"category": "PDF (Resume)", "question": q, "passed": passed, "answer": ans[:100], "expected": expected})
            print(f"[{'PASS' if passed else 'FAIL'}] PDF Resume -> {q}")
            if not passed:
                print(f"   Model answered: {ans}")

        # 2. Multi-page Report PDF
        report_bytes = create_test_report_pdf()
        res = await client.post("/api/chat/upload", files={"file": ("report.pdf", report_bytes, "application/pdf")})
        assert res.status_code == 200
        report_att = res.json()

        report_questions = [
            ("What was the total revenue reported in the executive summary?", ["$42.5 million", "42.5 million", "42.5"]),
            ("What is the cloud server uptime reported on page 2?", ["99.98%", "99.98"]),
            ("How many new engineers are planned to be hired according to page 3?", ["150"]),
        ]
        for q, expected in report_questions:
            chat_res = await client.post("/api/chat", json={
                "message": q,
                "attachments": [report_att]
            })
            ans = chat_res.json().get("content", "")
            passed = check_answer(ans, expected)
            test_results.append({"category": "PDF (Multi-page)", "question": q, "passed": passed, "answer": ans[:100], "expected": expected})
            print(f"[{'PASS' if passed else 'FAIL'}] PDF Multi-page -> {q}")

        # 3. Table PDF
        table_bytes = create_test_table_pdf()
        res = await client.post("/api/chat/upload", files={"file": ("sales_table.pdf", table_bytes, "application/pdf")})
        assert res.status_code == 200
        table_att = res.json()

        table_questions = [
            ("What were the sales for the North region in Q4?", ["210"]),
            ("Which region had the highest sales in Q1?", ["West"]),
        ]
        for q, expected in table_questions:
            chat_res = await client.post("/api/chat", json={
                "message": q,
                "attachments": [table_att]
            })
            ans = chat_res.json().get("content", "")
            passed = check_answer(ans, expected)
            test_results.append({"category": "PDF (Table)", "question": q, "passed": passed, "answer": ans[:100], "expected": expected})
            print(f"[{'PASS' if passed else 'FAIL'}] PDF Table -> {q}")

        # 4. Scanned Image-only PDF
        scanned_bytes = create_test_scanned_pdf()
        res = await client.post("/api/chat/upload", files={"file": ("scanned_certificate.pdf", scanned_bytes, "application/pdf")})
        assert res.status_code == 200
        scanned_att = res.json()

        scanned_questions = [
            ("Who was the certificate of excellence awarded to?", ["Elena Vance", "Dr. Elena Vance"]),
            ("What is the exact verification ID printed on the certificate?", ["QT-88492", "QT 88492"]),
        ]
        for q, expected in scanned_questions:
            chat_res = await client.post("/api/chat", json={
                "message": q,
                "attachments": [scanned_att]
            })
            ans = chat_res.json().get("content", "")
            passed = check_answer(ans, expected)
            test_results.append({"category": "PDF (Scanned/OCR)", "question": q, "passed": passed, "answer": ans[:100], "expected": expected})
            print(f"[{'PASS' if passed else 'FAIL'}] PDF Scanned -> {q}")
            if not passed:
                print(f"   Model answered: {ans}")

        # =====================================================================
        # CATEGORY 2: IMAGE VISION TESTS (Screenshot, Chart, Drawing, Handwriting, Code)
        # =====================================================================
        print("\n--- CATEGORY 2: IMAGE VISION UNDERSTANDING TESTS ---")

        # 1. Screenshot
        ss_bytes = create_test_text_screenshot()
        res = await client.post("/api/chat/upload", files={"file": ("screenshot.png", ss_bytes, "image/png")})
        assert res.status_code == 200
        ss_att = res.json()

        ss_questions = [
            ("What is the database latency shown in the screenshot?", ["4.2ms", "4.2"]),
            ("How many active cluster nodes are shown?", ["64"]),
        ]
        for q, expected in ss_questions:
            chat_res = await client.post("/api/chat", json={"message": q, "attachments": [ss_att]})
            ans = chat_res.json().get("content", "")
            passed = check_answer(ans, expected)
            test_results.append({"category": "Image (Screenshot)", "question": q, "passed": passed, "answer": ans[:100], "expected": expected})
            print(f"[{'PASS' if passed else 'FAIL'}] Image Screenshot -> {q}")

        # 2. Chart
        chart_bytes = create_test_chart()
        res = await client.post("/api/chat/upload", files={"file": ("chart.png", chart_bytes, "image/png")})
        assert res.status_code == 200
        chart_att = res.json()

        chart_questions = [
            ("Which fruit has the highest value in the chart?", ["Bananas", "Banana", "70"]),
            ("What is the exact count for Apples in the chart?", ["45"]),
        ]
        for q, expected in chart_questions:
            chat_res = await client.post("/api/chat", json={"message": q, "attachments": [chart_att]})
            ans = chat_res.json().get("content", "")
            passed = check_answer(ans, expected)
            test_results.append({"category": "Image (Chart)", "question": q, "passed": passed, "answer": ans[:100], "expected": expected})
            print(f"[{'PASS' if passed else 'FAIL'}] Image Chart -> {q}")

        # 3. Diagram Drawing
        diag_bytes = create_test_drawing()
        res = await client.post("/api/chat/upload", files={"file": ("diagram.png", diag_bytes, "image/png")})
        assert res.status_code == 200
        diag_att = res.json()

        diag_questions = [
            ("What color is the Client circle?", ["blue"]),
            ("What component is in the orange box on the right?", ["Redis", "Redis Cache"]),
        ]
        for q, expected in diag_questions:
            chat_res = await client.post("/api/chat", json={"message": q, "attachments": [diag_att]})
            ans = chat_res.json().get("content", "")
            passed = check_answer(ans, expected)
            test_results.append({"category": "Image (Diagram)", "question": q, "passed": passed, "answer": ans[:100], "expected": expected})
            print(f"[{'PASS' if passed else 'FAIL'}] Image Diagram -> {q}")

        # 4. Handwriting-style Note
        hw_bytes = create_test_handwriting()
        res = await client.post("/api/chat/upload", files={"file": ("note.png", hw_bytes, "image/png")})
        assert res.status_code == 200
        hw_att = res.json()

        hw_questions = [
            ("By what day and time must the quarterly tax filing be submitted?", ["Friday", "4 PM", "4:00 PM"]),
            ("Who must the filing be submitted to according to the note?", ["John Doe", "John"]),
        ]
        for q, expected in hw_questions:
            chat_res = await client.post("/api/chat", json={"message": q, "attachments": [hw_att]})
            ans = chat_res.json().get("content", "")
            passed = check_answer(ans, expected)
            test_results.append({"category": "Image (Handwriting)", "question": q, "passed": passed, "answer": ans[:100], "expected": expected})
            print(f"[{'PASS' if passed else 'FAIL'}] Image Handwriting -> {q}")

        # 5. Code Screenshot
        code_bytes = create_test_code_screenshot()
        res = await client.post("/api/chat/upload", files={"file": ("code.png", code_bytes, "image/png")})
        assert res.status_code == 200
        code_att = res.json()

        code_questions = [
            ("What discount rate is given for the VIP tier in the code?", ["0.25", "25%"]),
            ("What is the function name in the code screenshot?", ["compute_discount"]),
        ]
        for q, expected in code_questions:
            chat_res = await client.post("/api/chat", json={"message": q, "attachments": [code_att]})
            ans = chat_res.json().get("content", "")
            passed = check_answer(ans, expected)
            test_results.append({"category": "Image (Code)", "question": q, "passed": passed, "answer": ans[:100], "expected": expected})
            print(f"[{'PASS' if passed else 'FAIL'}] Image Code -> {q}")

        # 6. Multi-turn Image Memory Persistence Test
        print("\n--- MULTI-TURN IMAGE PERSISTENCE TEST ---")
        turn1_res = await client.post("/api/chat", json={
            "message": "I am uploading this fruit chart for reference.",
            "attachments": [chart_att]
        })
        conv_id = turn1_res.json()["conversation_id"]
        # Follow-up turn WITHOUT re-attaching the chart image
        turn2_res = await client.post("/api/chat", json={
            "conversation_id": conv_id,
            "message": "Looking at the chart I previously uploaded in this conversation, what was the count for Cherries?"
        })
        turn2_ans = turn2_res.json().get("content", "")
        passed_turn2 = check_answer(turn2_ans, ["25"])
        test_results.append({
            "category": "Multi-turn Image Memory",
            "question": "What was the count for Cherries (follow-up without re-attaching)?",
            "passed": passed_turn2,
            "answer": turn2_ans[:100],
            "expected": ["25"]
        })
        print(f"[{'PASS' if passed_turn2 else 'FAIL'}] Multi-turn Image Memory -> {turn2_ans[:80]}")

        # =====================================================================
        # CATEGORY 3: DOCX, XLSX, CSV, TXT TESTS
        # =====================================================================
        print("\n--- CATEGORY 3: DOCX, XLSX, CSV, TXT PARSING TESTS ---")

        # 1. DOCX
        docx_bytes = create_test_docx()
        res = await client.post("/api/chat/upload", files={"file": ("falcon.docx", docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
        assert res.status_code == 200
        docx_att = res.json()
        chat_res = await client.post("/api/chat", json={
            "message": "What is the date for Prototype launch in Project Falcon?",
            "attachments": [docx_att]
        })
        ans = chat_res.json().get("content", "")
        passed = check_answer(ans, ["March 15"])
        test_results.append({"category": "DOCX", "question": "Date for Prototype launch?", "passed": passed, "answer": ans[:100], "expected": ["March 15"]})
        print(f"[{'PASS' if passed else 'FAIL'}] DOCX -> {ans[:80]}")

        # 2. XLSX
        xlsx_bytes = create_test_xlsx()
        res = await client.post("/api/chat/upload", files={"file": ("inventory.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert res.status_code == 200
        xlsx_att = res.json()
        chat_res = await client.post("/api/chat", json={
            "message": "What is the unit price of Widget B in the spreadsheet?",
            "attachments": [xlsx_att]
        })
        ans = chat_res.json().get("content", "")
        passed = check_answer(ans, ["$24.00", "24.00", "24"])
        test_results.append({"category": "XLSX", "question": "Unit price of Widget B?", "passed": passed, "answer": ans[:100], "expected": ["$24.00", "24"]})
        print(f"[{'PASS' if passed else 'FAIL'}] XLSX -> {ans[:80]}")

        # 3. CSV
        csv_bytes = create_test_csv()
        res = await client.post("/api/chat/upload", files={"file": ("employees.csv", csv_bytes, "text/csv")})
        assert res.status_code == 200
        csv_att = res.json()
        chat_res = await client.post("/api/chat", json={
            "message": "What is the job title of Alice in the CSV file?",
            "attachments": [csv_att]
        })
        ans = chat_res.json().get("content", "")
        passed = check_answer(ans, ["Lead Architect"])
        test_results.append({"category": "CSV", "question": "Job title of Alice?", "passed": passed, "answer": ans[:100], "expected": ["Lead Architect"]})
        print(f"[{'PASS' if passed else 'FAIL'}] CSV -> {ans[:80]}")

        # 4. TXT
        txt_bytes = create_test_txt()
        res = await client.post("/api/chat/upload", files={"file": ("wifi.txt", txt_bytes, "text/plain")})
        assert res.status_code == 200
        txt_att = res.json()
        chat_res = await client.post("/api/chat", json={
            "message": "What is the Wi-Fi password in the notes?",
            "attachments": [txt_att]
        })
        ans = chat_res.json().get("content", "")
        passed = check_answer(ans, ["SeaBreeze#2026"])
        test_results.append({"category": "TXT", "question": "Wi-Fi password?", "passed": passed, "answer": ans[:100], "expected": ["SeaBreeze#2026"]})
        print(f"[{'PASS' if passed else 'FAIL'}] TXT -> {ans[:80]}")

        # =====================================================================
        # CATEGORY 4: MIC FALLBACK AUDIO ENDPOINT TEST
        # =====================================================================
        print("\n--- CATEGORY 4: AUDIO TRANSCRIBE ENDPOINT TEST ---")
        audio_wav_bytes = create_test_audio_wav()
        audio_res = await client.post("/api/chat/transcribe", files={"file": ("audio.wav", audio_wav_bytes, "audio/wav")})
        print(f"Audio transcription endpoint HTTP status: {audio_res.status_code}")
        # Audio endpoint should respond with 200 (or 400 if pure tone has no spoken words)
        audio_passed = audio_res.status_code in [200, 400]
        test_results.append({
            "category": "Audio Fallback Endpoint",
            "question": "POST /api/chat/transcribe responds gracefully",
            "passed": audio_passed,
            "answer": str(audio_res.status_code),
            "expected": ["200 or 400"]
        })
        print(f"[{'PASS' if audio_passed else 'FAIL'}] Audio Transcribe Endpoint -> {audio_res.status_code}")

        # =====================================================================
        # CATEGORY 5: REGRESSION TESTS (20 DIVERSE CHAT QUESTIONS)
        # =====================================================================
        print("\n--- CATEGORY 5: 20 REGRESSION CHAT QUESTIONS ---")
        regression_questions = [
            ("Hello! Who are you?", ["GoldSea", "assistant", "agent"]),
            ("What is 17 * 19?", ["323"]),
            ("Write a Python one-liner to reverse a list called nums.", ["nums[::-1]", "reverse"]),
            ("What is the capital of France?", ["Paris"]),
            ("Explain the difference between a process and a thread in 2 sentences.", ["process", "thread", "memory"]),
            ("What is the speed of light in vacuum?", ["299792458", "300000", "3 x 10^8", "300,000", "186000"]),
            ("What does HTML stand for?", ["Hypertext Markup Language", "HyperText Markup Language"]),
            ("Convert 100 Celsius to Fahrenheit.", ["212"]),
            ("Who proposed the theory of general relativity?", ["Einstein", "Albert Einstein"]),
            ("What is the time complexity of binary search on a sorted array?", ["O(log n)", "O(logn)", "logarithmic"]),
            ("What is the chemical formula for water?", ["H2O", "H₂O"]),
            ("What year did the Apollo 11 mission land on the moon?", ["1969"]),
            ("Give me 3 synonyms for the word 'innovative'.", ["creative", "novel", "groundbreaking", "inventive", "original", "fresh"]),
            ("What is a REST API?", ["Representational State Transfer", "HTTP", "endpoint", "architecture"]),
            ("How many days are in a leap year?", ["366"]),
            ("What is the square root of 144?", ["12"]),
            ("Name the four terrestrial (rocky) planets in our solar system.", ["Mercury", "Venus", "Earth", "Mars"]),
            ("What does CSS stand for?", ["Cascading Style Sheets"]),
            ("What is the purpose of Docker?", ["container", "containers", "packaging", "isolation"]),
            ("If I have 5 apples and eat 2, how many remain?", ["3", "three"])
        ]

        for idx, (rq, exp) in enumerate(regression_questions, 1):
            r_res = await client.post("/api/chat", json={"message": rq, "enable_search": False})
            r_ans = r_res.json().get("content", "")
            r_pass = check_answer(r_ans, exp)
            test_results.append({
                "category": "Regression Chat",
                "question": f"Q{idx}: {rq}",
                "passed": r_pass,
                "answer": r_ans[:80],
                "expected": exp
            })
            print(f"[{'PASS' if r_pass else 'FAIL'}] Regression {idx}/20: {rq[:40]}...")
            if not r_pass:
                print(f"   Model answered: {r_ans}")

        # =====================================================================
        # SUMMARY & SCORING
        # =====================================================================
        total_tests = len(test_results)
        passed_tests = sum(1 for t in test_results if t["passed"])
        score_pct = (passed_tests / total_tests) * 100.0

        # File & Image specific score
        file_image_tests = [t for t in test_results if t["category"] not in ["Regression Chat", "Audio Fallback Endpoint"]]
        file_image_passed = sum(1 for t in file_image_tests if t["passed"])
        file_image_score_pct = (file_image_passed / len(file_image_tests)) * 100.0

        # Regression specific score
        regression_tests = [t for t in test_results if t["category"] == "Regression Chat"]
        regression_passed = sum(1 for t in regression_tests if t["passed"])
        regression_score_pct = (regression_passed / len(regression_tests)) * 100.0

        print("\n" + "=" * 70)
        print("📊 TEST RUN SUMMARY RESULTS")
        print("=" * 70)
        print(f"Total Tests Executed: {total_tests}")
        print(f"Overall Passed:       {passed_tests}/{total_tests} ({score_pct:.1f}%)")
        print(f"File & Image Tests:   {file_image_passed}/{len(file_image_tests)} ({file_image_score_pct:.1f}%) [Target >= 95%]")
        print(f"Regression Tests:     {regression_passed}/{len(regression_tests)} ({regression_score_pct:.1f}%)")
        print("=" * 70)

        # Save results to JSON file
        report_data = {
            "total": total_tests,
            "passed": passed_tests,
            "overall_score_pct": score_pct,
            "file_image_score_pct": file_image_score_pct,
            "regression_score_pct": regression_score_pct,
            "tests": test_results
        }
        report_path = Path(__file__).resolve().parent / "file_tests_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2)

        return file_image_score_pct, regression_score_pct


if __name__ == "__main__":
    asyncio.run(run_all_tests())
