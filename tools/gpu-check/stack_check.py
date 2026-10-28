"""A GPU container reaches another container by its service name.

compose.yaml mounts this folder into the container at /app/src, so edits here need no rebuild.
Run from Ubuntu:  docker compose run --rm app
"""

import json
import urllib.request

import torch

QDRANT = "http://qdrant:6333"  # the service name from compose.yaml; Compose's DNS resolves it


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(QDRANT + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


def collections() -> list[str]:
    return [c["name"] for c in call("GET", "/collections")["result"]["collections"]]


def main() -> None:
    gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none"
    print(f"GPU: {gpu}")
    print(f"collections at start: {collections()}")
    if "demo" not in collections():
        call("PUT", "/collections/demo", {"vectors": {"size": 4, "distance": "Cosine"}})
        print("created collection 'demo'")
    print(f"collections now: {collections()}")


if __name__ == "__main__":
    main()
