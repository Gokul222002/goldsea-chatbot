import os
import json
import re
import asyncio
import base64
from typing import List, Dict, Any, Tuple, AsyncGenerator, Optional
import httpx

from backend.config import (
    GEMINI_API_KEY, GEMINI_MODEL,
    GROQ_API_KEY, GROQ_MODEL,
    OPENAI_API_KEY, OPENAI_MODEL,
    OPENROUTER_API_KEY, OPENROUTER_MODEL,
    TARGET_USER_NAME
)
from backend.prompt_engine import build_system_prompt
from backend.search_tool import should_trigger_search, perform_web_search
from backend.database import get_conversation, update_conversation, save_message, get_conversation_messages, get_all_memories
from backend.memory_engine import extract_and_save_memories

# Try importing google-genai
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except Exception:
    GENAI_AVAILABLE = False

SUGGESTIONS_REGEX = re.compile(r"<<<SUGGESTIONS>>>(.*?)<<<END_SUGGESTIONS>>>", re.DOTALL)

def extract_suggestions(text: str) -> Tuple[str, List[str]]:
    """Extract optional follow-up suggestions from model text or generate dynamic chips."""
    match = SUGGESTIONS_REGEX.search(text)
    chips = []
    cleaned_text = text
    if match:
        raw_json = match.group(1).strip()
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, list):
                chips = [str(c).strip() for c in parsed if c][:3]
        except Exception:
            chips = [c.strip().strip('"\'') for c in raw_json.replace('[', '').replace(']', '').split(',') if c.strip()][:3]
        cleaned_text = SUGGESTIONS_REGEX.sub("", text).strip()
        
    if not chips:
        if "```" in cleaned_text:
            chips = ["Explain code line-by-line", "Add error handling", "Optimize code"]
        elif any(w in cleaned_text.lower() for w in ["step", "1.", "recipe", "options", "plan"]):
            chips = ["Make it shorter", "Give more details", "What are common pitfalls?"]
        else:
            chips = ["Tell me more", "Make shorter", "Give a concrete example"]
            
    return cleaned_text, chips

async def call_gemini_api(
    system_prompt: str,
    history_messages: List[Dict[str, Any]],
    query: str,
    images: Optional[List[Dict[str, Any]]] = None
) -> Tuple[Optional[str], Optional[str]]:
    """Calls Gemini API using REST v1beta with multimodal vision support and resilient model failover."""
    if not GEMINI_API_KEY:
        return None, "GEMINI_API_KEY not configured"

    candidate_models = [GEMINI_MODEL]
    for alt in ["gemini-3-flash-preview", "gemini-3.1-flash-lite-preview"]:
        if alt not in candidate_models:
            candidate_models.append(alt)

    contents_payload = []
    # Include past history turns with their attachments for multi-turn vision memory
    for m in history_messages:
        role = "user" if m.get("role") == "user" else "model"
        parts = []
        if "attachments" in m and isinstance(m["attachments"], list):
            for att in m["attachments"]:
                if att.get("type") == "image" and att.get("data"):
                    parts.append({
                        "inlineData": {
                            "mimeType": att.get("mime_type", "image/png"),
                            "data": att["data"]
                        }
                    })
                for pimg in att.get("page_images", []):
                    if pimg.get("data"):
                        parts.append({
                            "inlineData": {
                                "mimeType": pimg.get("mime_type", "image/png"),
                                "data": pimg["data"]
                            }
                        })
        m_content = m.get("content", "")
        if m_content:
            parts.append({"text": m_content})
        elif not parts:
            parts.append({"text": ""})
        contents_payload.append({"role": role, "parts": parts})

    # Current turn
    current_parts = []
    if images:
        for img in images:
            if img.get("data"):
                current_parts.append({
                    "inlineData": {
                        "mimeType": img.get("mime_type", "image/png"),
                        "data": img["data"]
                    }
                })
    current_parts.append({"text": query if query else "Please analyze the attached image/file."})
    contents_payload.append({"role": "user", "parts": current_parts})

    body = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents_payload,
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 2048
        }
    }

    last_error = ""
    async with httpx.AsyncClient(timeout=35.0) as client:
        for model in candidate_models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
                resp = await client.post(url, json=body)
                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates and "content" in candidates[0]:
                        parts = candidates[0]["content"].get("parts", [])
                        if parts and "text" in parts[0]:
                            return parts[0]["text"].strip(), None
                else:
                    err_msg = resp.text
                    last_error = f"{model} ({resp.status_code}): {err_msg[:120]}"
                    if resp.status_code == 429:
                        await asyncio.sleep(1.0)
                        continue
            except Exception as e:
                last_error = f"{model} connection: {str(e)}"
                continue

    return None, last_error or "Gemini API call failed"

async def call_groq_api(
    system_prompt: str,
    history_messages: List[Dict[str, Any]],
    query: str,
    images: Optional[List[Dict[str, Any]]] = None
) -> Tuple[Optional[str], Optional[str]]:
    """Calls Groq Cloud API."""
    if not GROQ_API_KEY:
        return None, "GROQ_API_KEY not configured"

    try:
        messages = [{"role": "system", "content": system_prompt}]
        for m in history_messages:
            messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})
        messages.append({"role": "user", "content": query})

        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }
        body = {
            "model": GROQ_MODEL,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.3
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=body)
            if resp.status_code == 200:
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                return text.strip(), None
            else:
                return None, f"Groq error {resp.status_code}: {resp.text}"
    except Exception as e:
        return None, f"Groq connection error: {str(e)}"

async def call_openai_api(
    system_prompt: str,
    history_messages: List[Dict[str, Any]],
    query: str,
    images: Optional[List[Dict[str, Any]]] = None
) -> Tuple[Optional[str], Optional[str]]:
    """Calls OpenAI API with vision content blocks."""
    if not OPENAI_API_KEY:
        return None, "OPENAI_API_KEY not configured"

    try:
        messages = [{"role": "system", "content": system_prompt}]
        for m in history_messages:
            content = []
            if "attachments" in m and isinstance(m["attachments"], list):
                for att in m["attachments"]:
                    if att.get("type") == "image" and att.get("data"):
                        mime = att.get("mime_type", "image/png")
                        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{att['data']}"}})
            content.append({"type": "text", "text": m.get("content", "")})
            messages.append({"role": m.get("role", "user"), "content": content if len(content) > 1 else m.get("content", "")})

        curr_content = []
        if images:
            for img in images:
                if img.get("data"):
                    mime = img.get("mime_type", "image/png")
                    curr_content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img['data']}"}})
        curr_content.append({"type": "text", "text": query if query else "Please analyze the attached image/file."})
        messages.append({"role": "user", "content": curr_content})

        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        body = {
            "model": OPENAI_MODEL,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.3
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=body)
            if resp.status_code == 200:
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                return text.strip(), None
            else:
                return None, f"OpenAI error {resp.status_code}: {resp.text}"
    except Exception as e:
        return None, f"OpenAI connection error: {str(e)}"

async def call_openrouter_api(
    system_prompt: str,
    history_messages: List[Dict[str, Any]],
    query: str,
    images: Optional[List[Dict[str, Any]]] = None
) -> Tuple[Optional[str], Optional[str]]:
    """Calls OpenRouter API with vision blocks."""
    if not OPENROUTER_API_KEY:
        return None, "OPENROUTER_API_KEY not configured"

    try:
        messages = [{"role": "system", "content": system_prompt}]
        for m in history_messages:
            messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})

        curr_content = []
        if images:
            for img in images:
                if img.get("data"):
                    mime = img.get("mime_type", "image/png")
                    curr_content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img['data']}"}})
        curr_content.append({"type": "text", "text": query if query else "Please analyze the attached image/file."})
        messages.append({"role": "user", "content": curr_content})

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        body = {
            "model": OPENROUTER_MODEL,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.3
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body)
            if resp.status_code == 200:
                data = resp.json()
                text = data["choices"][0]["message"]["content"]
                return text.strip(), None
            else:
                return None, f"OpenRouter error {resp.status_code}: {resp.text}"
    except Exception as e:
        return None, f"OpenRouter connection error: {str(e)}"

async def call_llm(
    system_prompt: str,
    history_messages: List[Dict[str, Any]],
    query: str,
    images: Optional[List[Dict[str, Any]]] = None
) -> Tuple[Optional[str], Optional[str]]:
    """
    Executes live LLM completion across configured providers:
    1. Gemini (primary multimodal vision & text)
    2. Groq (secondary)
    3. OpenAI (tertiary)
    4. OpenRouter (quaternary)
    Returns (raw_response_text, error_message)
    """
    errors = []
    
    # Primary: Gemini
    if GEMINI_API_KEY:
        text, err = await call_gemini_api(system_prompt, history_messages, query, images=images)
        if text:
            return text, None
        errors.append(f"Gemini: {err}")
        
    # Secondary: Groq (if text-only or fallback)
    if GROQ_API_KEY and not images:
        text, err = await call_groq_api(system_prompt, history_messages, query, images=images)
        if text:
            return text, None
        errors.append(f"Groq: {err}")
        
    # Tertiary: OpenAI (supports vision)
    if OPENAI_API_KEY:
        text, err = await call_openai_api(system_prompt, history_messages, query, images=images)
        if text:
            return text, None
        errors.append(f"OpenAI: {err}")

    # Quaternary: OpenRouter (supports vision)
    if OPENROUTER_API_KEY:
        text, err = await call_openrouter_api(system_prompt, history_messages, query, images=images)
        if text:
            return text, None
        errors.append(f"OpenRouter: {err}")
        
    if not (GEMINI_API_KEY or GROQ_API_KEY or OPENAI_API_KEY or OPENROUTER_API_KEY):
        return None, "NO_API_KEY_CONFIGURED: Please set GEMINI_API_KEY (or GROQ_API_KEY / OPENAI_API_KEY) in your environment variables or Render dashboard."

    return None, "; ".join(errors)

async def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/webm") -> Tuple[Optional[str], Optional[str]]:
    """
    Transcribes audio bytes to text using Gemini multimodal audio (primary)
    with Groq Whisper and OpenAI Whisper fallbacks.
    """
    if not audio_bytes:
        return None, "No audio data provided"

    # 1. Primary: Gemini Multimodal Audio
    if GEMINI_API_KEY:
        try:
            b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
            # Map common audio mimes
            norm_mime = mime_type.lower()
            if "webm" in norm_mime:
                norm_mime = "audio/webm"
            elif "wav" in norm_mime:
                norm_mime = "audio/wav"
            elif "mp3" in norm_mime or "mpeg" in norm_mime:
                norm_mime = "audio/mp3"
            elif "ogg" in norm_mime:
                norm_mime = "audio/ogg"
            elif "m4a" in norm_mime or "mp4" in norm_mime:
                norm_mime = "audio/mp4"
            else:
                norm_mime = "audio/webm"

            candidate_models = [GEMINI_MODEL, "gemini-3-flash-preview", "gemini-3.1-flash-lite-preview"]
            body = {
                "contents": [{
                    "role": "user",
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": norm_mime,
                                "data": b64_audio
                            }
                        },
                        {
                            "text": "Transcribe the spoken audio verbatim. Return only the exact spoken words with punctuation. Do not add commentary, notes, or explanations."
                        }
                    ]
                }],
                "generationConfig": {
                    "temperature": 0.0,
                    "maxOutputTokens": 1024
                }
            }
            async with httpx.AsyncClient(timeout=30.0) as client:
                for model in candidate_models:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
                    resp = await client.post(url, json=body)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates and "content" in candidates[0]:
                            parts = candidates[0]["content"].get("parts", [])
                            if parts and "text" in parts[0]:
                                text = parts[0]["text"].strip()
                                return text, None
        except Exception as e:
            pass

    # 2. Secondary: Groq Whisper
    if GROQ_API_KEY:
        try:
            headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
            files = {"file": ("recording.webm", audio_bytes, mime_type)}
            data = {"model": "whisper-large-v3"}
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, files=files, data=data)
                if resp.status_code == 200:
                    text = resp.json().get("text", "").strip()
                    return text, None
        except Exception:
            pass

    # 3. Tertiary: OpenAI Whisper
    if OPENAI_API_KEY:
        try:
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
            files = {"file": ("recording.webm", audio_bytes, mime_type)}
            data = {"model": "whisper-1"}
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post("https://api.openai.com/v1/audio/transcriptions", headers=headers, files=files, data=data)
                if resp.status_code == 200:
                    text = resp.json().get("text", "").strip()
                    return text, None
        except Exception:
            pass

    return None, "Unable to transcribe audio. Please verify microphone settings or API key configuration."

async def generate_chat_response(
    query: str,
    conversation_id: Optional[str] = None,
    custom_instruction: Optional[str] = None,
    enable_search: bool = True,
    attachments: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Generates genuine AI response unwrapped from LLM:
    1. Extracts memories
    2. Performs live web search if needed
    3. Processes attachments (images & document text)
    4. Retrieves full conversation history with multimodal context
    5. Sends prompt + images to LLM
    6. Returns clean response with chips
    """
    # 1. Update memories from query text
    try:
        if query and query.strip():
            extract_and_save_memories(query)
    except Exception:
        pass
    all_memories = get_all_memories()

    # 2. Process attachments into document text & images
    doc_blocks = []
    current_images = []
    for att in (attachments or []):
        att_type = att.get("type", "document")
        if att_type == "image":
            current_images.append(att)
        elif att_type == "document":
            name = att.get("name", "Document")
            extracted = att.get("extracted_text", "")
            if extracted:
                doc_blocks.append(f"The user attached a file named '{name}'. Extracted content:\n\"\"\"\n{extracted}\n\"\"\"")
            for pimg in att.get("page_images", []):
                current_images.append(pimg)

    # 3. Compose final query with strict document grounding block
    if doc_blocks:
        doc_header = (
            "The user attached the following document(s):\n\n"
            + "\n\n".join(doc_blocks)
            + "\n\n[Instructions for attached document(s)]:\n"
            "1. Answer the user's questions strictly based on the extracted document content and visual page images provided.\n"
            "2. If a specific field, detail, or answer is NOT found in the document, state: 'I can't find that in the file' instead of guessing or assuming.\n"
            "3. Maintain high factual accuracy for names, numbers, dates, and tables."
        )
        if query and query.strip():
            llm_query = f"{query.strip()}\n\n{doc_header}"
        else:
            llm_query = f"Please summarize the main content and key takeaways of the attached file.\n\n{doc_header}"
    else:
        llm_query = query.strip() if query and query.strip() else ("Please analyze the attached image in detail." if current_images else "")

    # 4. Live search grounding (only if search enabled, not purely document-grounded)
    sources = []
    search_context = ""
    if enable_search and query and not doc_blocks and should_trigger_search(query):
        try:
            search_context, sources = await perform_web_search(query)
        except Exception:
            pass

    # 5. Retrieve full conversation history
    history_messages = []
    if conversation_id:
        history_messages = get_conversation_messages(conversation_id)

    # 6. Build system prompt
    system_prompt = build_system_prompt(memories=all_memories, custom_instructions=custom_instruction)
    if search_context:
        system_prompt += f"\n\n[Live Search Grounding Information (Verified Sources)]:\n{search_context}"

    # 7. Call LLM directly with multimodal image parts
    raw_response, error_info = await call_llm(system_prompt, history_messages, llm_query, images=current_images)

    # 8. Return explicit error if call failed
    if not raw_response:
        error_msg = error_info or "LLM generation failed."
        return {
            "text": f"Error: {error_msg}",
            "follow_up_chips": [],
            "sources": sources,
            "error": True
        }

    # 9. Clean text and extract chips
    clean_text, chips = extract_suggestions(raw_response)

    return {
        "text": clean_text,
        "follow_up_chips": chips,
        "sources": sources,
        "error": False
    }

async def stream_chat_response(
    query: str,
    conversation_id: str,
    custom_instruction: Optional[str] = None,
    enable_search: bool = True,
    attachments: Optional[List[Dict[str, Any]]] = None
) -> AsyncGenerator[str, None]:
    """Generates Server-Sent Events (SSE) stream for real-time typewriter UI with multimodal attachments."""
    try:
        result = await generate_chat_response(
            query=query,
            conversation_id=conversation_id,
            custom_instruction=custom_instruction,
            enable_search=enable_search,
            attachments=attachments
        )

        if result.get("error"):
            yield f"data: {json.dumps({'type': 'error', 'message': result['text'], 'can_retry': True})}\n\n"
            return

        # Stream sources first if present
        if result.get("sources"):
            yield f"data: {json.dumps({'type': 'sources', 'sources': result['sources']})}\n\n"
            await asyncio.sleep(0.05)

        # Stream text in smooth chunks
        full_text = result.get("text", "")
        words = full_text.split(" ")
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield f"data: {json.dumps({'type': 'token', 'token': chunk})}\n\n"
            await asyncio.sleep(0.015)

        # Stream follow up chips
        yield f"data: {json.dumps({'type': 'follow_up_chips', 'chips': result.get('follow_up_chips', [])})}\n\n"

        # Save assistant message in DB
        assistant_msg_id = f"msg_{os.urandom(6).hex()}"
        save_message(
            msg_id=assistant_msg_id,
            conv_id=conversation_id,
            role="assistant",
            content=full_text,
            sources=result.get("sources", []),
            follow_up_chips=result.get("follow_up_chips", []),
            attachments=[]
        )

        yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_msg_id})}\n\n"

    except Exception as e:
        error_payload = {
            "type": "error",
            "message": f"Assistant error: {str(e)}",
            "can_retry": True
        }
        yield f"data: {json.dumps(error_payload)}\n\n"
