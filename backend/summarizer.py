from typing import List, Dict, Any, Tuple
import re

def extractive_summary(messages: List[Dict[str, Any]]) -> str:
    """Fast, reliable summary generator for chat history compression."""
    points = []
    for msg in messages:
        role = msg.get("role", "user").capitalize()
        content = msg.get("content", "").strip()
        # Grab first 1-2 key sentences
        first_sentence = re.split(r"(?<=[.!?])\s+", content)[0]
        if len(first_sentence) > 120:
            first_sentence = first_sentence[:117] + "..."
        points.append(f"{role}: {first_sentence}")
        
    summary = "Summary of earlier discussion: " + "; ".join(points)
    if len(summary) > 600:
        summary = summary[:597] + "..."
    return summary

def compress_chat_history(
    messages: List[Dict[str, Any]],
    existing_summary: str = "",
    threshold_turns: int = 8,
    keep_recent: int = 4
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    If total messages exceed threshold_turns, compresses older messages into summary,
    keeping only the most recent turns active in context.
    """
    if len(messages) <= threshold_turns:
        return existing_summary, messages
        
    older_messages = messages[:-keep_recent]
    recent_messages = messages[-keep_recent:]
    
    new_older_summary = extractive_summary(older_messages)
    combined_summary = f"{existing_summary} | {new_older_summary}".strip(" |")
    if len(combined_summary) > 800:
        combined_summary = combined_summary[-800:]
        
    return combined_summary, recent_messages
