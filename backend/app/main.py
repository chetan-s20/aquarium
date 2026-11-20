from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import alerts, auth, export, fish, health, imports, readings, simulator, tanks
from app.config import settings

app = FastAPI(title=settings.app_name, version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

for module in (health, tanks, readings, alerts, auth, fish, export, simulator, imports):
    app.include_router(module.router)


@app.get("/")
def root():
    return {"name": settings.app_name, "docs": "/docs", "health": "/health"}
