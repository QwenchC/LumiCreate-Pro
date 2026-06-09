from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import settings, projects, text_engine, image_engine, audio_engine, video_engine, subtitle_engine, orchestrator, templates, logs, tasks, elements, project_elements, music, sfx_engine, prompts_engine


def create_app() -> FastAPI:
    app = FastAPI(
        title="LumiCreate-Pro API",
        version="1.4.5",
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
    app.include_router(tasks.router,            prefix="/api/tasks",            tags=["tasks"])
    app.include_router(elements.router,         prefix="/api/elements",         tags=["elements"])
    app.include_router(project_elements.router, prefix="/api/projects/{project_id}/elements", tags=["project-elements"])
    app.include_router(music.router,            prefix="/api/music",            tags=["music"])
    app.include_router(sfx_engine.router,        prefix="/api/sfx",              tags=["sfx"])
    app.include_router(prompts_engine.router,    prefix="/api/prompts",          tags=["prompts"])
    from routers import task_history as th_router
    app.include_router(th_router.router,        prefix="/api/task-history",     tags=["task-history"])

    # E1: install log bus tee + record event loop on startup
    @app.on_event("startup")
    async def _install_log_bus():
        import asyncio as _aio
        from services.log_bus import install_tee, set_main_loop
        install_tee()
        set_main_loop(_aio.get_running_loop())

    # B2: 进程退出时关掉共享线程池（避免 Windows 端口不释放等问题）
    @app.on_event("shutdown")
    async def _shutdown_exec_pool():
        try:
            from services.exec_pool import shutdown
            shutdown(wait=False)
        except Exception:
            pass

    # B1: 启动时清理上次进程崩溃留下的"假死"任务
    @app.on_event("startup")
    async def _cleanup_interrupted_tasks():
        try:
            from services.task_runner import cleanup_interrupted_tasks
            n = cleanup_interrupted_tasks()
            if n:
                print(f"[startup] marked {n} stale running/pending task(s) as interrupted",
                      flush=True)
        except Exception as e:
            print(f"[startup] cleanup_interrupted_tasks failed: {e}", flush=True)

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "version": "1.4.5"}

    return app
