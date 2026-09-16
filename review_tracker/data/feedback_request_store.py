"""Storage for bug/feature requests submitted from the app, on a network share."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

REQUEST_STORAGE_PATH = Path(r"\\vi.vector.int\user\Tmp\tfarahani")
REQUEST_FILE_NAME = "bug_feature_requests.json"


def save_request(request_type: str, description: str, username: str) -> dict[str, Any]:
    """Append a bug/feature request to the shared request file and return it."""
    REQUEST_STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    request_file = REQUEST_STORAGE_PATH / REQUEST_FILE_NAME

    request_obj = {
        "id": datetime.now().isoformat(),
        "type": request_type,
        "description": description,
        "username": username,
        "status": "open",
        "created_at": datetime.now().isoformat(),
    }

    requests: list[Any] = []
    if request_file.exists():
        try:
            with open(request_file, "r", encoding="utf-8") as f:
                existing = json.load(f)
                if isinstance(existing, list):
                    requests = existing
                elif isinstance(existing, dict):
                    requests = [existing]
        except (json.JSONDecodeError, IOError):
            requests = []

    requests.append(request_obj)

    with open(request_file, "w", encoding="utf-8") as f:
        json.dump(requests, f, indent=2, ensure_ascii=False)

    return request_obj
