from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes.dashboard_api import router as dashboard_router

app = FastAPI(title="Aegis-75 V3.0.2 Compose")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard_router)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "service": "python-api"}
