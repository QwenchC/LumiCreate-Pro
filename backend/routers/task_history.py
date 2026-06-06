"""Task history endpoints (E2)."""
from typing import Optional

from fastapi import APIRouter

from services import task_history as th

router = APIRouter()


@router.get("")
async def list_records(limit: int = 100, project_id: Optional[str] = None, type: Optional[str] = None):
    return {"records": th.list_records(limit=limit, project_id=project_id, type_=type)}


@router.get("/stats")
async def stats():
    return th.stats()


@router.delete("", status_code=204)
async def clear_all():
    th.clear()
