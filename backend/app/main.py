import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import alerts, auth, disease, export, fish, health, imports, readings, simulator, tanks
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

for module in (health, tanks, readings, alerts, auth, fish, export, simulator, imports, disease):
    app.include_router(module.router)

# Serve the built frontend (single-container deploy) when it is present.
_static = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(_static):
    app.mount("/", StaticFiles(directory=_static, html=True), name="frontend")


@app.get("/")
def root():
    return {"name": settings.app_name, "docs": "/docs", "health": "/health"}
