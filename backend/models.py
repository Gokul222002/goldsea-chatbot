from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class SourceItem(BaseModel):
    title: str
    url: str
    snippet: Optional[str] = ""

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None
    tone: Optional[str] = None
    enable_search: bool = True
    attachments: Optional[List[Dict[str, Any]]] = None

class QuickActionRequest(BaseModel):
    action: str
    text: str
    conversation_id: Optional[str] = None

class PerReplyActionRequest(BaseModel):
    action: str  # "regenerate", "shorter", "detailed"
    message_id: str
    conversation_id: str

class MemoryItem(BaseModel):
    key: str
    value: str
    category: str = "preference"

class DeleteMemoryRequest(BaseModel):
    key: str

class CreateConversationRequest(BaseModel):
    title: Optional[str] = "New Conversation"

class UpdateConversationRequest(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None

class SearchRequest(BaseModel):
    query: str
    max_results: int = 5
