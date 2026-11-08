import os
import uuid
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from backend.models import ChatRequest, QuickActionRequest, PerReplyActionRequest
from backend.llm_service import generate_chat_response, stream_chat_response
from backend.database import create_conversation, get_conversation, save_message, get_conversation_messages

router = APIRouter(prefix="/api/chat", tags=["Chat"])

QUICK_ACTION_PROMPTS = {
    "summarize": "Summarize this text clearly into high-impact key points:\n\n",
    "grammar": "Fix the grammar, tone, and sentence flow of the following text while keeping its core message intact:\n\n",
    "eli5": "Explain the following concept like I am completely new to it, using intuitive analogies and zero jargon:\n\n",
    "email": "Draft a polished, professional email based on the following notes:\n\n",
    "debug": "Debug the following code snippet, identify why it fails, and provide the clean step-by-step fix:\n\n",
    "plan": "Plan my day with a realistic, high-priority, time-blocked schedule based on these tasks:\n\n"
}

@router.post("")
async def chat_endpoint(request: ChatRequest):
    conv_id = request.conversation_id
    if not conv_id:
        conv_id = f"conv_{uuid.uuid4().hex[:12]}"
        create_conversation(conv_id, title=request.message[:40] + ("..." if len(request.message) > 40 else ""))
    else:
        conv = get_conversation(conv_id)
        if not conv:
            create_conversation(conv_id, title=request.message[:40] + ("..." if len(request.message) > 40 else ""))

    # Save user message
    user_msg_id = f"msg_{uuid.uuid4().hex[:10]}"
    save_message(user_msg_id, conv_id, role="user", content=request.message)

    # Process response
    result = await generate_chat_response(
        query=request.message,
        conversation_id=conv_id,
        enable_search=request.enable_search
    )

    # Save assistant message
    asst_msg_id = f"msg_{uuid.uuid4().hex[:10]}"
    save_message(
        asst_msg_id,
        conv_id,
        role="assistant",
        content=result["text"],
        sources=result["sources"],
        follow_up_chips=result["follow_up_chips"]
    )

    return {
        "conversation_id": conv_id,
        "message_id": asst_msg_id,
        "content": result["text"],
        "follow_up_chips": result["follow_up_chips"],
        "sources": result["sources"],
        "error": result.get("error", False)
    }

@router.post("/stream")
async def chat_stream_endpoint(request: ChatRequest):
    conv_id = request.conversation_id
    if not conv_id:
        conv_id = f"conv_{uuid.uuid4().hex[:12]}"
        create_conversation(conv_id, title=request.message[:40] + ("..." if len(request.message) > 40 else ""))
    else:
        conv = get_conversation(conv_id)
        if not conv:
            create_conversation(conv_id, title=request.message[:40] + ("..." if len(request.message) > 40 else ""))

    # Save user message
    user_msg_id = f"msg_{uuid.uuid4().hex[:10]}"
    save_message(user_msg_id, conv_id, role="user", content=request.message)

    return StreamingResponse(
        stream_chat_response(
            query=request.message,
            conversation_id=conv_id,
            enable_search=request.enable_search
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Conversation-Id": conv_id
        }
    )

@router.post("/quick-action")
async def quick_action_endpoint(request: QuickActionRequest):
    prefix = QUICK_ACTION_PROMPTS.get(request.action.lower(), "")
    full_prompt = f"{prefix}{request.text.strip()}"
    
    conv_id = request.conversation_id or f"conv_{uuid.uuid4().hex[:12]}"
    if not get_conversation(conv_id):
        action_names = {
            "summarize": "Text Summary",
            "grammar": "Grammar Polish",
            "eli5": "Simple Explanation",
            "email": "Email Draft",
            "debug": "Code Debug",
            "plan": "Daily Schedule"
        }
        title = action_names.get(request.action.lower(), "Quick Action")
        create_conversation(conv_id, title=title)
        
    user_msg_id = f"msg_{uuid.uuid4().hex[:10]}"
    save_message(user_msg_id, conv_id, role="user", content=full_prompt)
    
    result = await generate_chat_response(query=full_prompt, conversation_id=conv_id)
    
    asst_msg_id = f"msg_{uuid.uuid4().hex[:10]}"
    save_message(
        asst_msg_id,
        conv_id,
        role="assistant",
        content=result["text"],
        sources=result["sources"],
        follow_up_chips=result["follow_up_chips"]
    )
    
    return {
        "conversation_id": conv_id,
        "message_id": asst_msg_id,
        "content": result["text"],
        "follow_up_chips": result["follow_up_chips"],
        "sources": result["sources"]
    }

@router.post("/per-reply-action")
async def per_reply_action_endpoint(request: PerReplyActionRequest):
    conv_id = request.conversation_id
    messages = get_conversation_messages(conv_id)
    if not messages:
        raise HTTPException(status_code=404, detail="Conversation not found or empty")
        
    # Find last user and assistant messages
    target_msg = None
    last_user_msg = None
    for m in reversed(messages):
        if m["id"] == request.message_id:
            target_msg = m
        if m["role"] == "user" and not last_user_msg:
            last_user_msg = m
            
    if not target_msg and messages:
        target_msg = messages[-1]
    if not last_user_msg:
        last_user_msg = {"content": "Help me with this."}
        
    action = request.action.lower()
    custom_instruction = None
    
    if action == "regenerate":
        query = last_user_msg["content"]
        custom_instruction = "Provide a fresh, alternative perspective or direct solution."
    elif action == "shorter":
        query = f"Please condense the previous answer and make it much shorter and punchier: '{target_msg['content'][:300]}'"
        custom_instruction = "Keep the reply extremely concise and direct (under 3 sentences)."
    elif action == "detailed":
        query = f"Please expand with in-depth detail, comprehensive step-by-step guidance, and real-world examples: '{target_msg['content'][:300]}'"
        custom_instruction = "Provide exhaustive technical depth and comprehensive breakdown."
    else:
        query = last_user_msg["content"]
        
    result = await generate_chat_response(
        query=query,
        conversation_id=conv_id,
        custom_instruction=custom_instruction
    )
    
    asst_msg_id = f"msg_{uuid.uuid4().hex[:10]}"
    save_message(
        asst_msg_id,
        conv_id,
        role="assistant",
        content=result["text"],
        sources=result["sources"],
        follow_up_chips=result["follow_up_chips"]
    )
    
    return {
        "conversation_id": conv_id,
        "message_id": asst_msg_id,
        "content": result["text"],
        "follow_up_chips": result["follow_up_chips"],
        "sources": result["sources"]
    }
