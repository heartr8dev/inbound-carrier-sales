"""Phase 2 placeholder. Real implementation lands in its workstream commit."""

from fastapi import APIRouter, Depends, HTTPException, status

from api.src.middleware.auth import require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/")
async def placeholder() -> None:
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not Implemented")
