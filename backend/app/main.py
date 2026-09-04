import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import router, synchronize_child_calendar
from app.api.v1.integration_router import router as integration_router
from app.core.config import get_settings
from app.integrations import deliver_outbox_once
from app.core.database import SessionLocal
from app.models.entities import CalendarSource, Child
from sqlalchemy import select, text
from app.waste_calendar import list_waste_configs, sync_waste_calendar
from app.version import VERSION

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    async def worker():
        last_waste_check = 0.0
        last_school_check = 0.0
        while True:
            try:
                await deliver_outbox_once()
            except Exception:
                import logging
                logging.getLogger("familienplan.outbox").exception("Outbox-Verarbeitung fehlgeschlagen")
            if asyncio.get_running_loop().time() - last_waste_check >= 3600:
                last_waste_check = asyncio.get_running_loop().time()
                try:
                    with SessionLocal() as db:
                        for config in list_waste_configs(db):
                            last_sync = config.get("last_sync_at")
                            due = not last_sync or datetime.fromisoformat(last_sync) < datetime.now(timezone.utc) - timedelta(hours=24)
                            if config.get("enabled") and due:
                                await sync_waste_calendar(db, config["id"])
                except Exception:
                    import logging
                    logging.getLogger("familienplan.waste").exception("Abfallkalender-Synchronisierung fehlgeschlagen")
            if asyncio.get_running_loop().time() - last_school_check >= 3600:
                last_school_check = asyncio.get_running_loop().time()
                try:
                    with SessionLocal() as db:
                        locked = bool(db.scalar(text("SELECT pg_try_advisory_lock(7346219)")))
                        if locked:
                            try:
                                children = db.scalars(select(Child).where(Child.is_active.is_(True), Child.school_calendar_url.is_not(None)))
                                for child in children:
                                    source = db.scalar(select(CalendarSource).where(CalendarSource.key == f"child-{child.id}-school"))
                                    if not source or not source.last_sync_at or source.last_sync_at < datetime.now(timezone.utc) - timedelta(hours=6):
                                        await synchronize_child_calendar(db, child)
                            finally:
                                db.execute(text("SELECT pg_advisory_unlock(7346219)"))
                except Exception:
                    import logging
                    logging.getLogger("familienplan.school").exception("Schulkalender-Synchronisierung fehlgeschlagen")
            await asyncio.sleep(15)
    task = asyncio.create_task(worker())
    yield
    task.cancel()


app = FastAPI(title="FamilienPlan API", version=VERSION, docs_url="/api/docs", redoc_url=None, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[settings.app_origin], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/api/v1")
app.include_router(integration_router, prefix="/api/v1")


@app.exception_handler(Exception)
async def unhandled_error(_: Request, exc: Exception):
    # Details belong in server logs, never in the browser response.
    import logging
    logging.getLogger("familienplan").exception("Unhandled request error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Ein interner Fehler ist aufgetreten"})


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404 and not path.startswith("api/"):
                response = await super().get_response("index.html", scope)
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                return response
            raise
        if response.status_code == 404 and not path.startswith("api/"):
            response = await super().get_response("index.html", scope)
        if path.startswith("assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.is_dir():
    @app.get("/calendar", include_in_schema=False)
    async def calendar_page():
        response = FileResponse(frontend_dist / "index.html", media_type="text/html")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    @app.get("/invite/{token}", include_in_schema=False)
    async def invitation_page(token: str):
        response = FileResponse(frontend_dist / "index.html", media_type="text/html")
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    app.mount("/", SPAStaticFiles(directory=frontend_dist, html=True), name="frontend")
