"""Azure Functions entry point for the semiconductor job scrape."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import azure.functions as func


dependency_path = os.environ.get("AZURE_FILES_DEPENDENCY_PATH", "/mnt/dependencies")
if dependency_path not in sys.path:
    sys.path.insert(0, dependency_path)

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


@app.route(route="scrape-semiconductor", methods=["POST", "GET"])
def scrape_semiconductor(req: func.HttpRequest) -> func.HttpResponse:
    """Run the scrape and persist JSON directly to the Azure Files mount."""
    try:
        from run_semiconductor_scrape import main as run_scrape

        output_directory = Path(
            os.environ.get("JOBSPY_OUTPUT_DIRECTORY", "/mnt/jobspy-data")
        )
        paths = run_scrape(output_directory)
        return func.HttpResponse(
            json.dumps(
                {
                    "status": "completed",
                    "files": {name: str(path) for name, path in paths.items()},
                }
            ),
            mimetype="application/json",
        )
    except Exception as exc:
        return func.HttpResponse(
            json.dumps({"status": "failed", "error": str(exc)}),
            status_code=500,
            mimetype="application/json",
        )
