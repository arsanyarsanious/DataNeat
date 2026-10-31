"""Serve the exported frontend on the API origin, without an extra Node server."""
import os
from starlette.staticfiles import StaticFiles
from starlette.exceptions import HTTPException


class ExportedSite(StaticFiles):
    async def get_response(self, path, scope):
        # Never turn missing API endpoints into a successful HTML page.
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404)
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or path.rsplit("/", 1)[-1].find(".") >= 0:
                raise
            return await super().get_response(path.rstrip("/") + ".html", scope)


def install_static_site(app):
    directory = os.getenv("STATIC_DIR")
    if directory:
        app.mount("/", ExportedSite(directory=directory, html=True), name="frontend")
