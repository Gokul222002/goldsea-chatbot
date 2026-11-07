from fastapi import APIRouter
from backend.models import SearchRequest
from backend.search_tool import perform_web_search

router = APIRouter(prefix="/api/search", tags=["Search"])

@router.post("")
async def search_endpoint(request: SearchRequest):
    context, sources = await perform_web_search(request.query, max_results=request.max_results)
    return {
        "query": request.query,
        "sources": sources,
        "context": context
    }
