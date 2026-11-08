import re
from typing import List, Dict, Any, Optional
from backend.database import save_memory, get_all_memories

MEMORY_EXTRACTION_RULES = [
    # Name patterns: strictly "my name is X" or "call me X" with capitalized alphabetic name
    (r"(?:my name is|call me)\s+([A-Z][a-zA-Z]{1,20}(?:\s+[A-Z][a-zA-Z]{1,20})?)", "user_name", "profile"),
    # Direct preference statements
    (r"(?:i prefer|my preference is)\s+([^.,;\n]{3,80})", "preference", "preference"),
    (r"(?:i always want|always give me|please always)\s+([^.,;\n]{3,80})", "formatting_rule", "preference"),
    # Tone & style preferences
    (r"(?:keep replies short|i like short answers|be concise|concise replies only)", "reply_length", "concise"),
    (r"(?:i code in|my main programming language is|favorite language is)\s+([a-zA-Z#+]{1,20})", "preferred_language", "preference"),
    (r"(?:i work as a?|my job is a?)\s+([a-zA-Z\s]{3,40})", "profession", "profile"),
]

def extract_and_save_memories(message: str) -> List[Dict[str, str]]:
    saved = []
    text = message.strip()
    
    for pattern, key_prefix, category in MEMORY_EXTRACTION_RULES:
        match = re.search(pattern, text, re.I)
        if match:
            if category == "concise":
                key = "reply_style"
                val = "concise and direct"
            elif match.groups():
                captured = match.group(1).strip()
                # Clean captured value
                captured = re.sub(r"^(to|that)\s+", "", captured, flags=re.I)
                key = key_prefix
                if key == "preference":
                    key = f"pref_{captured[:20].lower().replace(' ', '_')}"
                val = captured
            else:
                continue
                
            save_memory(key=key, value=val, category=category)
            saved.append({"key": key, "value": val, "category": category})
            
    return saved
