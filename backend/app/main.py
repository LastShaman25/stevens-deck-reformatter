"""Stevens Slide Studio - FastAPI entrypoint.

Run (dev):  uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api import router
from . import sessions
from . import auth
from .authoring.api import router as authoring_router
from starlette.middleware.sessions import SessionMiddleware
from contextlib import asynccontextmanager
import asyncio

@asynccontextmanager
async def lifespan(app):
    sessions.cleanup_orphans(startup=True)
    async def cleanup():
        while True:
            sessions.sweep()
            sessions.cleanup_orphans()
            await asyncio.sleep(60)
    task = asyncio.create_task(cleanup())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        for sid in list(sessions._sessions):
            sessions.delete(sid)


app = FastAPI(title="Stevens Slide Studio", version="1.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(auth.router)
app.include_router(authoring_router)
app.middleware('http')(auth.guard)
app.add_middleware(SessionMiddleware, secret_key=auth.cookie_secret(), session_cookie='stevens_oidc',
                   max_age=600, same_site='lax', https_only=auth.setting('STEVENS_PUBLIC_URL', '').startswith('https://'))

# Serve the built frontend if present (production single-process mode).
_DIST = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "frontend", "dist")
_DIST = os.path.abspath(_DIST)
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
