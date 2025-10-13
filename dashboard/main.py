import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from dashboard.server import app as server_app


def create_app() -> FastAPI:
    app = server_app
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app


app = create_app()
