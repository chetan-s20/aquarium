from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.imports import router as imports_router
from app.api.tanks import router as tanks_router
from app.api.readings import router as readings_router
from app.api.alerts import router as alerts_router
from app.api.simulator import router as simulator_router
from app.config import settings

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(tanks_router)
app.include_router(readings_router)
app.include_router(simulator_router)
app.include_router(alerts_router)
app.include_router(imports_router)


@app.get("/")
def root():
    return {"name": settings.app_name, "docs": "/docs", "health": "/health"}
