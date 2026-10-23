"""FutureReady AI web application. Run with uvicorn src.main:app."""

from contextlib import asynccontextmanager
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api.routes import router
from src.api.sessions import SessionStore
from src.backend import CareerBackend
from src.reskilling.course_catalog import CourseCatalogStore

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT.parent / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app):
    app.state.backend = CareerBackend(course_store=CourseCatalogStore(
        ROOT.parent / "data/processed/onet/31.0/courses.json"))
    app.state.sessions = SessionStore()
    yield
    app.state.sessions.clear()


app = FastAPI(title="FutureReady AI", version="0.2.0", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=FRONTEND / "assets", check_dir=False), name="assets")
app.mount("/fonts", StaticFiles(directory=ROOT.parent / "frontend" / "public" / "fonts"), name="fonts")
app.include_router(router, prefix="/api/v2")


@app.exception_handler(RequestValidationError)
async def invalid_request(request, error):
    return JSONResponse(status_code=422, content={
        "detail": "Some fields are invalid. Check your selections and try again.",
        "fields": [".".join(map(str, item["loc"])) for item in error.errors()],
    })


@app.middleware("http")
async def private_responses(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index(request: Request):
    if not (FRONTEND / "index.html").is_file():
        return HTMLResponse(
            "<h1>Frontend build needed</h1><p>Run npm ci and npm run build in the frontend folder, "
            "or use npm run dev there for the Vite preview on port 5173.</p>", status_code=503)
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/health")
def health():
    return {"status": "ok"}


def run():
    """Start the web app locally or on Replit, keeping demo sessions in one worker."""
    import uvicorn

    try:
        port = int(os.environ.get("PORT", "8000"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise SystemExit("PORT must be an integer between 1 and 65535.") from None
    uvicorn.run("src.main:app", host="0.0.0.0", port=port, workers=1,
                access_log=False)


if __name__ == "__main__":
    run()
