"""Azure Functions entry point for the semiconductor job scrape."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import quote

dependency_path = os.environ.get(
    "AZURE_FILES_DEPENDENCY_PATH",
    "/mnt/dependencies",
)
if dependency_path not in sys.path:
    sys.path.insert(0, dependency_path)

import azure.functions as func
import requests

from run_semiconductor_scrape import main as run_scrape


app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


def _graph_token() -> str:
    response = requests.post(
        f"https://login.microsoftonline.com/{os.environ['AZURE_TENANT_ID']}/oauth2/v2.0/token",
        data={
            "client_id": os.environ["AZURE_CLIENT_ID"],
            "client_secret": os.environ["AZURE_CLIENT_SECRET"],
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def _drive_path(filename: str) -> str:
    folder = os.environ.get("ONEDRIVE_FOLDER", "JobSpy")
    return "/".join(part.strip("/") for part in (folder, filename) if part)


def _graph_url(filename: str) -> str:
    user = os.environ["ONEDRIVE_USER"]
    path = quote(_drive_path(filename), safe="/")
    return (
        "https://graph.microsoft.com/v1.0/users/"
        f"{quote(user, safe='@.')}/drive/root:/{path}"
    )


def _download_previous_snapshot(directory: Path, token: str) -> None:
    filename = "semiconductor_jobs.json"
    response = requests.get(
        f"{_graph_url(filename)}:/content",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if response.status_code == 404:
        return
    response.raise_for_status()
    (directory / filename).write_bytes(response.content)


def _upload_file(path: Path, token: str) -> None:
    response = requests.put(
        f"{_graph_url(path.name)}:/content",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        data=path.read_bytes(),
        timeout=60,
    )
    response.raise_for_status()


@app.route(route="scrape-semiconductor", methods=["POST", "GET"])
def scrape_semiconductor(request: func.HttpRequest) -> func.HttpResponse:
    """Run the scrape and persist current, previous, and difference JSON."""
    try:
        token = _graph_token()
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            _download_previous_snapshot(directory, token)
            paths = run_scrape(directory)
            for path in paths.values():
                _upload_file(path, token)
        return func.HttpResponse(
            json.dumps({"status": "completed", "files": list(paths)}),
            mimetype="application/json",
        )
    except Exception as exc:
        return func.HttpResponse(
            json.dumps({"status": "failed", "error": str(exc)}),
            status_code=500,
            mimetype="application/json",
        )
