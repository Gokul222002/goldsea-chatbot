from pydantic import BaseModel, Field, EmailStr
from typing import List, Dict, Any, Optional

# ------------------------------------------------------------------------------
# Authentication & Account Request Models
# ------------------------------------------------------------------------------

class SignUpRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

class VerifyEmailRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    code: str = Field(..., min_length=6, max_length=6)

class ResendCodeRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    purpose: str = Field(default="verification")  # 'verification' or 'password_reset'

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)

class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)

class ResetPasswordRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

class UpdateProfileRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)

class DeleteAccountRequest(BaseModel):
    password: str = Field(..., min_length=1)

# ------------------------------------------------------------------------------
# Chat & Conversation Request Models
# ------------------------------------------------------------------------------

class SourceItem(BaseModel):
    title: str
    url: str
    snippet: Optional[str] = ""

class AttachmentItem(BaseModel):
    name: str
    type: str = "document"  # "image" or "document"
    mime_type: Optional[str] = "text/plain"
    size: Optional[int] = 0
    data: Optional[str] = None  # base64 string for images
    preview: Optional[str] = None  # data URL or thumbnail
    extracted_text: Optional[str] = None
    page_images: Optional[List[Dict[str, Any]]] = None

class ChatRequest(BaseModel):
    message: str = Field(default="", min_length=0)
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
