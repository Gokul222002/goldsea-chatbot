from fastapi import APIRouter, Depends
from backend.models import SearchRequest
from backend.search_tool import perform_web_search
from backend.database import User
from backend.dependencies import get_current_user

router = APIRouter(prefix="/api/search", tags=["Search"])

@router.post("")
async def search_endpoint(
    request: SearchRequest,
    current_user: User = Depends(get_current_user)
):
    context, sources = await perform_web_search(request.query, max_results=request.max_results)
    return {
        "query": request.query,
        "sources": sources,
        "context": context
    }
