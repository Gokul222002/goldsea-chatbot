import os
import json
import re
import asyncio
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

async def call_gemini_api(system_prompt: str, history_messages: List[Dict[str, Any]], query: str) -> Tuple[Optional[str], Optional[str]]:
    """Calls Gemini API using google-genai SDK or direct REST fallback with max_output_tokens=2048."""
    if not GEMINI_API_KEY:
        return None, "GEMINI_API_KEY not configured"

    # 1. Try google-genai SDK
    if GENAI_AVAILABLE:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            contents = []
            for m in history_messages:
                role = "user" if m.get("role") == "user" else "model"
                contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
            contents.append({"role": "user", "parts": [{"text": query}]})

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.3,
                    max_output_tokens=2048
                )
            )
            if response and response.text:
                return response.text.strip(), None
        except Exception as e:
            err = str(e)
            if "quota" in err.lower() or "429" in err:
                return None, f"Gemini quota exceeded: {err}"
            # Fall through to REST attempt

    # 2. Direct REST fallback
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        contents_payload = []
        for m in history_messages:
            role = "user" if m.get("role") == "user" else "model"
            contents_payload.append({"role": role, "parts": [{"text": m.get("content", "")}]})
        contents_payload.append({"role": "user", "parts": [{"text": query}]})

        body = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": contents_payload,
            "generationConfig": {
                "temperature": 0.3,
                "maxOutputTokens": 2048
            }
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=body)
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return text.strip(), None
            else:
                return None, f"Gemini REST error {resp.status_code}: {resp.text}"
    except Exception as e:
        return None, f"Gemini connection error: {str(e)}"

async def call_groq_api(system_prompt: str, history_messages: List[Dict[str, Any]], query: str) -> Tuple[Optional[str], Optional[str]]:
    """Calls Groq Cloud API (fast Llama 3.3 70B inference)."""
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

async def call_openai_api(system_prompt: str, history_messages: List[Dict[str, Any]], query: str) -> Tuple[Optional[str], Optional[str]]:
    """Calls OpenAI API."""
    if not OPENAI_API_KEY:
        return None, "OPENAI_API_KEY not configured"

    try:
        messages = [{"role": "system", "content": system_prompt}]
        for m in history_messages:
            messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})
        messages.append({"role": "user", "content": query})

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

async def call_openrouter_api(system_prompt: str, history_messages: List[Dict[str, Any]], query: str) -> Tuple[Optional[str], Optional[str]]:
    """Calls OpenRouter API."""
    if not OPENROUTER_API_KEY:
        return None, "OPENROUTER_API_KEY not configured"

    try:
        messages = [{"role": "system", "content": system_prompt}]
        for m in history_messages:
            messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})
        messages.append({"role": "user", "content": query})

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

async def call_llm(system_prompt: str, history_messages: List[Dict[str, Any]], query: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Executes live LLM completion across configured providers:
    1. Gemini (primary)
    2. Groq (secondary)
    3. OpenAI (tertiary)
    4. OpenRouter (quaternary)
    Returns (raw_response_text, error_message)
    """
    errors = []
    
    # Primary: Gemini
    if GEMINI_API_KEY:
        text, err = await call_gemini_api(system_prompt, history_messages, query)
        if text:
            return text, None
        errors.append(f"Gemini: {err}")
        
    # Secondary: Groq
    if GROQ_API_KEY:
        text, err = await call_groq_api(system_prompt, history_messages, query)
        if text:
            return text, None
        errors.append(f"Groq: {err}")
        
    # Tertiary: OpenAI
    if OPENAI_API_KEY:
        text, err = await call_openai_api(system_prompt, history_messages, query)
        if text:
            return text, None
        errors.append(f"OpenAI: {err}")

    # Quaternary: OpenRouter
    if OPENROUTER_API_KEY:
        text, err = await call_openrouter_api(system_prompt, history_messages, query)
        if text:
            return text, None
        errors.append(f"OpenRouter: {err}")
        
    if not (GEMINI_API_KEY or GROQ_API_KEY or OPENAI_API_KEY or OPENROUTER_API_KEY):
        return None, "NO_API_KEY_CONFIGURED: Please set GEMINI_API_KEY (or GROQ_API_KEY / OPENAI_API_KEY) in your environment variables or Render dashboard."

    return None, "; ".join(errors)

async def generate_chat_response(
    query: str,
    conversation_id: Optional[str] = None,
    custom_instruction: Optional[str] = None,
    enable_search: bool = True
) -> Dict[str, Any]:
    """
    Generates genuine AI response unwrapped from LLM:
    1. Extracts memories
    2. Performs live web search if needed
    3. Retrieves full conversation history
    4. Sends unwrapped prompt to LLM
    5. Returns direct LLM response as-is (no fallback templates)
    """
    # 1. Update memories
    try:
        extract_and_save_memories(query)
    except Exception:
        pass
    all_memories = get_all_memories()

    # 2. Live search grounding
    sources = []
    search_context = ""
    if enable_search and should_trigger_search(query):
        try:
            search_context, sources = await perform_web_search(query)
        except Exception:
            pass

    # 3. Retrieve full conversation history
    history_messages = []
    if conversation_id:
        history_messages = get_conversation_messages(conversation_id)

    # 4. Build system prompt
    system_prompt = build_system_prompt(memories=all_memories, custom_instructions=custom_instruction)
    if search_context:
        system_prompt += f"\n\n[Live Search Grounding Information (Verified Sources)]:\n{search_context}"

    # 5. Call LLM directly - unwrapped user message
    raw_response, error_info = await call_llm(system_prompt, history_messages, query)

    # 6. If LLM call failed or no API key, return explicit error (NEVER return fake template responses)
    if not raw_response:
        error_msg = error_info or "LLM generation failed."
        return {
            "text": f"Error: {error_msg}",
            "follow_up_chips": [],
            "sources": sources,
            "error": True
        }

    # 7. Clean text and extract chips
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
    enable_search: bool = True
) -> AsyncGenerator[str, None]:
    """Generates Server-Sent Events (SSE) stream for real-time typewriter UI."""
    try:
        result = await generate_chat_response(
            query=query,
            conversation_id=conversation_id,
            custom_instruction=custom_instruction,
            enable_search=enable_search
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
            follow_up_chips=result.get("follow_up_chips", [])
        )

        yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_msg_id})}\n\n"

    except Exception as e:
        error_payload = {
            "type": "error",
            "message": f"Assistant error: {str(e)}",
            "can_retry": True
        }
        yield f"data: {json.dumps(error_payload)}\n\n"
