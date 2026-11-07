from fastapi import APIRouter, HTTPException
from backend.models import MemoryItem, DeleteMemoryRequest
from backend.database import get_all_memories, save_memory, delete_memory

router = APIRouter(prefix="/api/memories", tags=["Memory"])

@router.get("")
async def get_memories_endpoint():
    return get_all_memories()

@router.post("")
async def save_memory_endpoint(item: MemoryItem):
    save_memory(key=item.key, value=item.value, category=item.category)
    return {"success": True, "saved": item.key}

@router.delete("/{key}")
async def delete_memory_endpoint(key: str):
    delete_memory(key)
    return {"success": True, "deleted": key}
