import re
import asyncio
from typing import List, Dict, Any, Tuple
from duckduckgo_search import DDGS
import httpx

SEARCH_TRIGGER_PATTERNS = [
    r"\b(latest|recent|news|current|today|yesterday|this week|this month)\b",
    r"\b(price|prices|stock|market|valuation|cost|rates)\b",
    r"\b(version|release|changelog|update|roadmap)\b",
    r"\b(who won|who is currently|who is the current|election|olympics|sports score)\b",
    r"\b(artemis|spacex|gemini|openai|anthropic|nvidia|apple|google)\b",
    r"\b(2024|2025|2026|2027)\b"
]

def should_trigger_search(query: str) -> bool:
    q = query.lower()
    for pat in SEARCH_TRIGGER_PATTERNS:
        if re.search(pat, q):
            return True
    return False

def clean_query_for_search(query: str) -> str:
    cleaned = re.sub(r"^(what is|who is|tell me about|can you search for|search for|what are the)\s+", "", query, flags=re.I)
    cleaned = re.sub(r"[?!.,]+$", "", cleaned)
    return cleaned.strip() or query

async def perform_web_search(query: str, max_results: int = 4) -> Tuple[str, List[Dict[str, str]]]:
    """Performs live web search using DuckDuckGo with fallback, returning context string and sources list."""
    search_query = clean_query_for_search(query)
    sources: List[Dict[str, str]] = []
    snippets: List[str] = []
    
    # Run DDGS in thread pool since it's synchronous
    def _run_ddgs():
        results = []
        try:
            with DDGS(timeout=8) as ddgs:
                ddg_gen = ddgs.text(search_query, max_results=max_results)
                for r in ddg_gen:
                    results.append(r)
        except Exception as e:
            pass
        return results

    raw_results = await asyncio.to_thread(_run_ddgs)
    
    if raw_results:
        for item in raw_results:
            title = item.get("title", "Source")
            url = item.get("href") or item.get("link") or ""
            body = item.get("body") or item.get("snippet") or ""
            if url:
                sources.append({"title": title, "url": url, "snippet": body})
                snippets.append(f"- [{title}]({url}): {body}")
                
    # Fallback to DuckDuckGo instant API if no results
    if not sources:
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                res = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": search_query, "format": "json", "no_html": "1", "skip_disambig": "1"}
                )
                if res.status_code == 200:
                    data = res.json()
                    abstract = data.get("AbstractText")
                    abstract_url = data.get("AbstractURL")
                    if abstract and abstract_url:
                        sources.append({"title": data.get("Heading", "Instant Answer"), "url": abstract_url, "snippet": abstract})
                        snippets.append(f"- [{data.get('Heading', 'Source')}]({abstract_url}): {abstract}")
        except Exception:
            pass
            
    context_text = ""
    if sources:
        context_text = "\n### Grounded Live Web Search Findings:\n" + "\n".join(snippets) + "\n\n(Use these verified facts and cite these sources with markdown links [Title](URL))."
        
    return context_text, sources
