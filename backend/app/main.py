import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import router
from app.api.v1.integration_router import router as integration_router
from app.core.config import get_settings
from app.integrations import deliver_outbox_once
from app.version import VERSION

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    async def worker():
        while True:
            try:
                await deliver_outbox_once()
            except Exception:
                import logging
                logging.getLogger("familienplan.outbox").exception("Outbox-Verarbeitung fehlgeschlagen")
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
    app.mount("/", SPAStaticFiles(directory=frontend_dist, html=True), name="frontend")
