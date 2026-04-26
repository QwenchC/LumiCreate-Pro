from fastapi import APIRouter
from config import AppSettings, load_settings, save_settings

router = APIRouter()


@router.get("", response_model=AppSettings)
async def get_settings():
    return load_settings()


@router.post("", response_model=AppSettings)
async def update_settings(new_settings: AppSettings):
    save_settings(new_settings)
    return new_settings
