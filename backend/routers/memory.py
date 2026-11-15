from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, status, Request
from backend.models import MemoryItem, DeleteMemoryRequest
from backend.database import User, get_all_memories, save_memory, delete_memory, clear_all_memories
from backend.dependencies import get_current_user
from backend.security import contains_sensitive_data, verify_csrf

router = APIRouter(prefix="/api/memories", tags=["Memory"])

@router.get("")
async def get_memories_endpoint(current_user: User = Depends(get_current_user)):
    """Returns all long-term memories belonging to the authenticated user."""
    return get_all_memories(user_id=current_user.id)

@router.post("")
async def save_memory_endpoint(
    item: MemoryItem,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Saves or updates a memory key-value pair for the authenticated user, blocking sensitive credentials."""
    verify_csrf(request)
    if contains_sensitive_data(item.value) or contains_sensitive_data(item.key):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sensitive data (passwords, payment cards, national IDs) cannot be stored in persistent memory."
        )

    res = save_memory(
        user_id=current_user.id,
        key=item.key,
        value=item.value,
        category=item.category or "preference"
    )
    return {"success": True, "memory": res}

@router.delete("/{key_or_id}")
async def delete_memory_endpoint(
    key_or_id: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Deletes an individual memory entry for the authenticated user."""
    verify_csrf(request)
    success = delete_memory(user_id=current_user.id, key_or_id=key_or_id)
    if not success:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"success": True, "deleted": key_or_id}

@router.delete("")
async def clear_all_memories_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Deletes all long-term memories for the authenticated user."""
    verify_csrf(request)
    count = clear_all_memories(user_id=current_user.id)
    return {"success": True, "cleared_count": count}
