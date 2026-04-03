"""
PromptCI FastAPI application entry point.
Initialises the database and output directory on startup.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router
from database.db import init_db
from config.settings import OUTPUTS_DIR, COMPOSIO_CACHE_DIR

app = FastAPI(title="PromptCI API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # VS Code extension needs this
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

@app.on_event("startup")
async def startup():
    init_db()
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    os.makedirs(COMPOSIO_CACHE_DIR, exist_ok=True)
