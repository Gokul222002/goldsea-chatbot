import uuid
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import PlainTextResponse
from backend.models import CreateConversationRequest, UpdateConversationRequest
from backend.database import (
    list_conversations,
    create_conversation,
    get_conversation,
    get_conversation_messages,
    update_conversation,
    delete_conversation
)

router = APIRouter(prefix="/api/conversations", tags=["Conversations"])

@router.get("")
async def get_all_conversations():
    return list_conversations()

@router.post("")
async def create_new_conversation(request: CreateConversationRequest):
    conv_id = f"conv_{uuid.uuid4().hex[:12]}"
    conv = create_conversation(conv_id, title=request.title or "New Conversation")
    return conv

@router.get("/{conv_id}")
async def get_single_conversation(conv_id: str):
    conv = get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = get_conversation_messages(conv_id)
    return {**conv, "messages": messages}

@router.patch("/{conv_id}")
async def update_single_conversation(conv_id: str, request: UpdateConversationRequest):
    conv = get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    update_conversation(conv_id, title=request.title, summary=request.summary)
    return get_conversation(conv_id)

@router.delete("/{conv_id}")
async def delete_single_conversation(conv_id: str):
    conv = get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    delete_conversation(conv_id)
    return {"success": True, "deleted": conv_id}

@router.get("/{conv_id}/export")
async def export_conversation(conv_id: str, format: str = Query("md")):
    if format not in ["md", "json", "txt"]:
        format = "md"
    conv = get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = get_conversation_messages(conv_id)
    
    if format == "json":
        return {
            "conversation": conv,
            "messages": messages
        }
    elif format == "txt":
        lines = [f"=== Conversation: {conv['title']} ===", f"Exported: {conv['updated_at']}\n"]
        for m in messages:
            lines.append(f"[{m['role'].upper()}]: {m['content']}\n")
        return PlainTextResponse("\n".join(lines), media_type="text/plain")
    else:  # Markdown
        lines = [f"# {conv['title']}\n", f"*Last Updated: {conv['updated_at']}*\n", "---\n"]
        for m in messages:
            role_badge = "**User (Gokul)**" if m["role"] == "user" else "**GoldSea AI**"
            lines.append(f"{role_badge}:\n\n{m['content']}\n")
            if m.get("sources"):
                lines.append("\n**Sources:**\n")
                for s in m["sources"]:
                    lines.append(f"- [{s['title']}]({s['url']})")
                lines.append("\n")
            lines.append("---\n")
        return PlainTextResponse("\n".join(lines), media_type="text/markdown")
