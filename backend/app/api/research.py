"""Research source search endpoint."""

from fastapi import APIRouter

from app.schemas.source_result import SourceSearchRequest, SourceSearchResponse
from app.services.research_source import ResearchSourceService

router = APIRouter(prefix="/research", tags=["research"])


@router.post("/search", response_model=SourceSearchResponse)
async def search_sources(request: SourceSearchRequest) -> SourceSearchResponse:
    """Search arXiv and GitHub, returning normalized, deduplicated results.

    A single unavailable source is reported in `errors` rather than failing
    the whole request, as long as the other source can still respond.
    """

    service = ResearchSourceService()
    return await service.search(
        request.query,
        sources=request.sources,
        max_results_per_source=request.max_results_per_source,
        published_after=request.published_after,
    )
