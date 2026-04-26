from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import settings, projects, text_engine, image_engine, audio_engine, video_engine


def create_app() -> FastAPI:
    app = FastAPI(
        title="LumiCreate-Local API",
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
    app.include_router(video_engine.router,   prefix="/api/video-engine",   tags=["video-engine"])

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    return app
