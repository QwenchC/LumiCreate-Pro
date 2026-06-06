from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import settings, projects, text_engine, image_engine, audio_engine, video_engine, subtitle_engine, orchestrator, templates, logs


def create_app() -> FastAPI:
    app = FastAPI(
        title="LumiCreate-Pro API",
        version="0.1.0",
        docs_url="/docs",
    )

    # Allow Electron renderer (localhost:5173 in dev, file:// in prod)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(settings.router,      prefix="/api/settings",      tags=["settings"])
    app.include_router(projects.router,       prefix="/api/projects",       tags=["projects"])
    app.include_router(text_engine.router,    prefix="/api/text-engine",    tags=["text-engine"])
    app.include_router(image_engine.router,   prefix="/api/image-engine",   tags=["image-engine"])
    app.include_router(audio_engine.router,   prefix="/api/audio-engine",   tags=["audio-engine"])
    app.include_router(video_engine.router,     prefix="/api/video-engine",     tags=["video-engine"])
    app.include_router(subtitle_engine.router,  prefix="/api/subtitle-engine",  tags=["subtitle-engine"])
    app.include_router(orchestrator.router,     prefix="/api/orchestrator",     tags=["orchestrator"])
    app.include_router(templates.router,        prefix="/api/templates",        tags=["templates"])
    app.include_router(logs.router,             prefix="/api/logs",             tags=["logs"])
    from routers import task_history as th_router
    app.include_router(th_router.router,        prefix="/api/task-history",     tags=["task-history"])

    # E1: install log bus tee + record event loop on startup
    @app.on_event("startup")
    async def _install_log_bus():
        import asyncio as _aio
        from services.log_bus import install_tee, set_main_loop
        install_tee()
        set_main_loop(_aio.get_running_loop())

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    return app
