import io
import csv
import json
import base64
from typing import Dict, Any, List, Tuple, Optional
from PIL import Image

# Import document processors
try:
    import pymupdf as fitz
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

try:
    import docx
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False


MAX_IMAGE_EDGE = 1568
MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB limit
MAX_TEXT_CHARS = 100_000  # 100k chars ~ 25k tokens for safe model context


def optimize_image(image_bytes: bytes, mime_type: str = "image/png") -> Dict[str, Any]:
    """
    Safely resizes oversized images (long edge <= 1568px) and returns base64 data and metadata.
    Preserves aspect ratio and high fidelity.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size
        
        # Calculate resize if necessary
        max_edge = max(width, height)
        if max_edge > MAX_IMAGE_EDGE:
            scale = MAX_IMAGE_EDGE / float(max_edge)
            new_width = max(1, int(width * scale))
            new_height = max(1, int(height * scale))
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            width, height = new_width, new_height

        # Normalize format for delivery
        output_buffer = io.BytesIO()
        target_mime = mime_type.lower()
        if target_mime in ["image/jpeg", "image/jpg"]:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(output_buffer, format="JPEG", quality=90, optimize=True)
            norm_mime = "image/jpeg"
        elif target_mime == "image/webp":
            img.save(output_buffer, format="WEBP", quality=90)
            norm_mime = "image/webp"
        elif target_mime == "image/gif":
            img.save(output_buffer, format="GIF")
            norm_mime = "image/gif"
        else:
            img.save(output_buffer, format="PNG", optimize=True)
            norm_mime = "image/png"

        b64_data = base64.b64encode(output_buffer.getvalue()).decode("utf-8")
        return {
            "mime_type": norm_mime,
            "data": b64_data,
            "width": width,
            "height": height,
            "size": len(output_buffer.getvalue()),
            "preview": f"data:{norm_mime};base64,{b64_data}"
        }
    except Exception as e:
        raise ValueError(f"Failed to process image: {str(e)}")


def parse_pdf(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """
    Robust PDF extraction pipeline:
    1. PyMuPDF text extraction preserving reading order, headings, bullets, tables.
    2. Detect scanned pages (page with little or no text) and layout-heavy pages (resumes, forms, tables).
    3. Render scanned/layout-heavy pages to 200+ DPI images for multimodal vision verification.
    4. Handles multi-page documents safely.
    """
    if not FITZ_AVAILABLE:
        raise RuntimeError("PyMuPDF (fitz) is not installed.")

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as e:
        raise ValueError(f"Corrupt or invalid PDF file: {str(e)}")

    if doc.is_encrypted:
        raise ValueError(f"PDF '{filename}' is password-protected. Please unlock or upload an unencrypted version.")

    total_pages = len(doc)
    extracted_pages = []
    page_images = []
    total_text_length = 0

    for page_idx in range(total_pages):
        page = doc[page_idx]
        page_num = page_idx + 1

        # Extract text blocks
        page_text = page.get_text("text").strip()
        word_count = len(page_text.split())

        # Determine if page is scanned/image-only or layout-heavy
        # Low word count (< 30 words) indicates scanned document or image slide
        is_scanned = word_count < 30
        # If document is short (<= 5 pages), also render pages as images for layout/visual cross-checking (resumes, forms, charts)
        is_layout_heavy = is_scanned or total_pages <= 5 or ("\t" in page_text or "  " in page_text)

        extracted_pages.append(f"--- Page {page_num} ---\n{page_text if page_text else '[No selectable text on this page - scanned or graphic content]'}")
        total_text_length += len(page_text)

        # Render page to 200 DPI image if scanned or layout-heavy
        # Limit rendered pages to maximum first 6 pages to stay within token/payload constraints
        if (is_scanned or is_layout_heavy) and len(page_images) < 6:
            try:
                pix = page.get_pixmap(dpi=200)
                img_png_bytes = pix.tobytes("png")
                optimized = optimize_image(img_png_bytes, "image/png")
                page_images.append({
                    "page": page_num,
                    "mime_type": "image/png",
                    "data": optimized["data"]
                })
            except Exception:
                pass

    doc.close()

    full_text = "\n\n".join(extracted_pages)
    if len(full_text) > MAX_TEXT_CHARS:
        full_text = full_text[:MAX_TEXT_CHARS] + "\n\n[Document truncated for length...]"

    return {
        "text": full_text,
        "page_count": total_pages,
        "page_images": page_images,
        "is_scanned": total_text_length < 50
    }


def parse_docx(file_bytes: bytes, filename: str) -> str:
    """Extracts text, headings, bullet lists, and tables from DOCX using python-docx."""
    if not DOCX_AVAILABLE:
        raise RuntimeError("python-docx is not installed.")

    try:
        doc = docx.Document(io.BytesIO(file_bytes))
        parts = []

        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue
            if p.style.name.startswith("Heading"):
                parts.append(f"\n### {text}")
            elif p.style.name.startswith("List"):
                parts.append(f"- {text}")
            else:
                parts.append(text)

        # Extract tables
        for table in doc.tables:
            table_md = []
            for row_idx, row in enumerate(table.rows):
                row_cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
                table_md.append("| " + " | ".join(row_cells) + " |")
                if row_idx == 0:
                    table_md.append("| " + " | ".join(["---"] * len(row_cells)) + " |")
            if table_md:
                parts.append("\n" + "\n".join(table_md) + "\n")

        full_text = "\n\n".join(parts)
        if len(full_text) > MAX_TEXT_CHARS:
            full_text = full_text[:MAX_TEXT_CHARS] + "\n\n[Document truncated...]"
        return full_text
    except Exception as e:
        raise ValueError(f"Corrupt or invalid DOCX file '{filename}': {str(e)}")


def parse_xlsx(file_bytes: bytes, filename: str) -> str:
    """Extracts spreadsheets into clean markdown tables using openpyxl."""
    if not OPENPYXL_AVAILABLE:
        raise RuntimeError("openpyxl is not installed.")

    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
        parts = []

        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]
            rows = list(sheet.iter_rows(values_only=True))
            if not rows:
                continue

            parts.append(f"### Sheet: {sheet_name}")
            table_md = []
            header_set = False

            for row_idx, row in enumerate(rows[:500]):  # cap to 500 rows per sheet
                if not any(cell is not None for cell in row):
                    continue
                cell_strs = [str(cell).strip().replace("\n", " ") if cell is not None else "" for cell in row]
                table_md.append("| " + " | ".join(cell_strs) + " |")
                if not header_set:
                    table_md.append("| " + " | ".join(["---"] * len(cell_strs)) + " |")
                    header_set = True

            if table_md:
                parts.append("\n".join(table_md))

        wb.close()
        full_text = "\n\n".join(parts)
        if len(full_text) > MAX_TEXT_CHARS:
            full_text = full_text[:MAX_TEXT_CHARS] + "\n\n[Spreadsheet truncated...]"
        return full_text
    except Exception as e:
        raise ValueError(f"Corrupt or invalid XLSX file '{filename}': {str(e)}")


def parse_csv(file_bytes: bytes, filename: str) -> str:
    """Extracts CSV data into formatted markdown table."""
    try:
        text_content = None
        for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
            try:
                text_content = file_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if text_content is None:
            raise ValueError("Unable to decode CSV with UTF-8 or Latin-1.")

        reader = csv.reader(io.StringIO(text_content))
        table_md = []
        header_set = False

        for row_idx, row in enumerate(reader):
            if row_idx > 500:
                table_md.append(f"... and {row_idx} more rows")
                break
            if not row:
                continue
            cleaned = [c.strip().replace("\n", " ") for c in row]
            table_md.append("| " + " | ".join(cleaned) + " |")
            if not header_set:
                table_md.append("| " + " | ".join(["---"] * len(cleaned)) + " |")
                header_set = True

        return "\n".join(table_md)
    except Exception as e:
        raise ValueError(f"Corrupt or invalid CSV file '{filename}': {str(e)}")


def parse_plain_text_or_json(file_bytes: bytes, filename: str) -> str:
    """Extracts TXT, JSON, code, or markdown files safely."""
    text_content = None
    for enc in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
        try:
            text_content = file_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if text_content is None:
        raise ValueError(f"Unable to read text file '{filename}' (unsupported encoding).")

    # If JSON, format nicely
    if filename.lower().endswith(".json"):
        try:
            data = json.loads(text_content)
            return json.dumps(data, indent=2)
        except Exception:
            return text_content

    if len(text_content) > MAX_TEXT_CHARS:
        return text_content[:MAX_TEXT_CHARS] + "\n\n[File truncated for length...]"
    return text_content


def process_uploaded_file(file_bytes: bytes, filename: str, content_type: Optional[str] = None) -> Dict[str, Any]:
    """
    Unified entry point for any uploaded file.
    Detects mime type / extension and routes to the appropriate parser.
    Returns structured dictionary with metadata, clean text, and any vision images.
    """
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise ValueError(f"File '{filename}' exceeds maximum allowed size (25MB).")

    fn_lower = filename.lower()
    ct_lower = (content_type or "").lower()

    # 1. Images
    image_extensions = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"]
    if any(fn_lower.endswith(ext) for ext in image_extensions) or ct_lower.startswith("image/"):
        norm_mime = ct_lower if ct_lower.startswith("image/") else f"image/{fn_lower.split('.')[-1]}"
        img_info = optimize_image(file_bytes, norm_mime)
        return {
            "name": filename,
            "type": "image",
            "mime_type": img_info["mime_type"],
            "size": len(file_bytes),
            "data": img_info["data"],
            "preview": img_info["preview"],
            "width": img_info["width"],
            "height": img_info["height"],
            "extracted_text": f"[Image attached: {filename}]",
            "page_images": []
        }

    # 2. PDF Documents
    if fn_lower.endswith(".pdf") or "pdf" in ct_lower:
        pdf_res = parse_pdf(file_bytes, filename)
        return {
            "name": filename,
            "type": "document",
            "mime_type": "application/pdf",
            "size": len(file_bytes),
            "page_count": pdf_res["page_count"],
            "extracted_text": pdf_res["text"],
            "page_images": pdf_res["page_images"],
            "is_scanned": pdf_res["is_scanned"]
        }

    # 3. DOCX Documents
    if fn_lower.endswith(".docx") or "wordprocessingml" in ct_lower:
        text = parse_docx(file_bytes, filename)
        return {
            "name": filename,
            "type": "document",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "size": len(file_bytes),
            "extracted_text": text,
            "page_images": []
        }

    # 4. XLSX Spreadsheets
    if fn_lower.endswith(".xlsx") or "spreadsheetml" in ct_lower:
        text = parse_xlsx(file_bytes, filename)
        return {
            "name": filename,
            "type": "document",
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "size": len(file_bytes),
            "extracted_text": text,
            "page_images": []
        }

    # 5. CSV Spreadsheets
    if fn_lower.endswith(".csv") or "csv" in ct_lower:
        text = parse_csv(file_bytes, filename)
        return {
            "name": filename,
            "type": "document",
            "mime_type": "text/csv",
            "size": len(file_bytes),
            "extracted_text": text,
            "page_images": []
        }

    # 6. TXT / JSON / Code Files / Markdown
    text = parse_plain_text_or_json(file_bytes, filename)
    return {
        "name": filename,
        "type": "document",
        "mime_type": ct_lower or "text/plain",
        "size": len(file_bytes),
        "extracted_text": text,
        "page_images": []
    }
