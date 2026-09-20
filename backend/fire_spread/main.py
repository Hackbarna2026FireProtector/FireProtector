"""FastAPI entrypoint for the fire-spread service."""

from fastapi import FastAPI

from fire_spread.router import router

app = FastAPI(title="Fire Spread API", version="2.0.0")
app.include_router(router, prefix="/fire")
