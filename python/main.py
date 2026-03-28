import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from routes.dashboard_api import router as dashboard_router
from services.api_errors import error_response
from services.pair_registry_updater import pair_registry_updater

BASE_DIR = Path(__file__).resolve().parent
TZ_TAIPEI = timezone(timedelta(hours=8))
APP_STARTED_AT = datetime.now(TZ_TAIPEI).isoformat()

app = FastAPI(title="Aegis-75 V3.0.2 Dashboard Enabled")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard_router)

app.mount(
    "/dashboard",
    StaticFiles(directory=BASE_DIR / "static" / "dashboard", html=True),
    name="dashboard",
)


@app.on_event("startup")
async def startup_pair_registry_updater() -> None:
    app.state.pair_registry_stop_event = asyncio.Event()
    await asyncio.to_thread(pair_registry_updater.sync_once)
    app.state.pair_registry_task = asyncio.create_task(
        pair_registry_updater.run_periodic_sync(app.state.pair_registry_stop_event)
    )


@app.on_event("shutdown")
async def shutdown_pair_registry_updater() -> None:
    stop_event = getattr(app.state, "pair_registry_stop_event", None)
    task = getattr(app.state, "pair_registry_task", None)
    if stop_event is not None:
        stop_event.set()
    if task is not None:
        await task

@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "service": "python-api", "startedAt": APP_STARTED_AT}


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(_, exc: RequestValidationError) -> JSONResponse:
    return error_response(
        400,
        "validation_error",
        "Request validation failed",
        exc.errors(),
    )
