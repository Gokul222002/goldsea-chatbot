from typing import List, Dict, Any, Optional
from backend.config import TARGET_USER_NAME
from backend.database import get_all_memories

SYSTEM_PROMPT = """You are GoldSea AI, a personal all-in-one assistant for Gokul. Answer any question and help with any problem: coding, study, career, health, food, money, travel, writing, emotions, daily life. Always give the real, complete answer immediately. Never reply with generic filler, templates, or 'let me know your goal'. Ask a clarifying question only if truly impossible to answer without it; otherwise assume sensibly and answer. Code requests: complete working code in a code block plus a short explanation. How-to: numbered steps. Simple questions: 1-3 sentences. Emotional messages: warm and empathetic first, then gentle suggestions. Health symptoms: give practical guidance and clearly state warning signs that need urgent medical care or a hospital; never dismiss. Recommendations: 3-5 specific options. Use web search for current info. Be honest, never invent facts. Use conversation history. Match the user's language and tone."""

def build_system_prompt(memories: Optional[List[Dict[str, Any]]] = None, custom_instructions: Optional[str] = None) -> str:
    prompt = SYSTEM_PROMPT
    
    all_memories = memories if memories is not None else get_all_memories()
    if all_memories:
        memory_lines = []
        for mem in all_memories:
            key = mem.get('key')
            val = mem.get('value')
            if key and val:
                memory_lines.append(f"- {key}: {val}")
        if memory_lines:
            prompt += "\n\nUser Context & Preferences:\n" + "\n".join(memory_lines)
            
    if custom_instructions:
        prompt += f"\n\nSession Directive: {custom_instructions}"
        
    return prompt
