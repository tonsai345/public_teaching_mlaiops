"""Lab 3 — inference service.

Provider-neutral by construction: the model arrives through the adapter, and the same
container image deploys to SageMaker, Azure ML, or Vertex AI. Route paths differ per
platform; that difference belongs in cloudlayer/, never here.

Run locally:  uvicorn service.app:app --port 8080
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from service.schemas import BatchRequest, BatchResponse, PredictRequest, PredictResponse

logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":%(message)s}',
)
log = logging.getLogger("service")

STATE: dict[str, Any] = {"model": None, "version": os.environ.get("MODEL_VERSION", "unknown")}


def _load_model_from_blob():
    """Download the model artifact from Blob Storage and load it with joblib.

    This path avoids needing Azure ML registry auth from inside the container
    (which requires either a managed identity or a service principal — neither
    is available on the express Container Apps tier).
    """
    import os
    from pathlib import Path
    from urllib.parse import urlparse

    import joblib
    from azure.storage.blob import BlobServiceClient

    blob_path = os.environ["MODEL_BLOB_PATH"]  # full https://... URL
    conn_str = os.environ["AZURE_STORAGE_CONNECTION_STRING"]

    parsed = urlparse(blob_path)
    path_parts = parsed.path.lstrip("/").split("/", 1)
    container_name = path_parts[0]
    blob_name = path_parts[1] if len(path_parts) > 1 else path_parts[0]

    local_path = Path("/tmp/model.joblib")
    local_path.parent.mkdir(parents=True, exist_ok=True)

    client = BlobServiceClient.from_connection_string(conn_str)
    container_client = client.get_container_client(container_name)
    log.info('"downloading model from %s"', blob_path)
    with open(local_path, "wb") as f:
        data = container_client.download_blob(blob_name).readall()
        f.write(data)
    log.info('"downloaded %d bytes"', len(data))

    return joblib.load(local_path)


def _load_model_from_registry():
    """Legacy path: load from Azure ML registry by name:version.

    Only usable when the container has Azure credentials (managed identity
    or service principal env vars). Kept for parity with the Lab 2 model
    registry if those are ever wired up.
    """
    name = os.environ.get("MODEL_REGISTRY_NAME")
    version = os.environ.get("MODEL_VERSION")
    if not (name and version):
        return None
    import mlflow.sklearn
    mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
    return mlflow.sklearn.load_model(f"models:/{name}/{version}")


def _load_model():
    """Load once, at startup. Never per request.

    Prefers the Blob artifact path (no directory permission needed). Falls
    back to the Azure ML registry if that env is configured and Blob is not.
    """
    if os.environ.get("MODEL_BLOB_PATH"):
        return _load_model_from_blob()
    if os.environ.get("MODEL_REGISTRY_NAME") and os.environ.get("MODEL_VERSION"):
        return _load_model_from_registry()

    # Local dev / tests only.
    from pathlib import Path
    import joblib
    path = Path(os.environ.get("MODEL_PATH", "reports/model.joblib"))
    if not path.exists():
        raise RuntimeError(
            "No model available. Set MODEL_BLOB_PATH, MODEL_REGISTRY_NAME+MODEL_VERSION, "
            "or MODEL_PATH."
        )
    return joblib.load(path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        STATE["model"] = _load_model()
        log.info('"model loaded, version=%s"', STATE["version"])
    except Exception as exc:
        STATE["model"] = None
        log.error('"model load failed: %s"', exc)
    yield
    STATE["model"] = None


app = FastAPI(title="ITCS355 inference", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    started = time.perf_counter()
    response = await call_next(request)
    latency_ms = (time.perf_counter() - started) * 1000
    response.headers["x-request-id"] = request_id
    response.headers["x-model-version"] = str(STATE["version"])
    log.info(
        '{"request_id":"%s","path":"%s","status":%d,"latency_ms":%.2f,"model_version":"%s"}',
        request_id, request.url.path, response.status_code, latency_ms, STATE["version"],
    )
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/ready")
def ready():
    if STATE["model"] is None:
        return JSONResponse(status_code=503, content={"status": "not_ready", "reason": "model not loaded"})
    return {"status": "ready", "model_version": STATE["version"]}


def _score(rows: list[dict]) -> list[float]:
    if STATE["model"] is None:
        raise HTTPException(status_code=503, detail="model not loaded")
    import pandas as pd

    from src.data import FEATURES

    frame = pd.DataFrame(rows)[FEATURES]
    return [float(p) for p in STATE["model"].predict_proba(frame)[:, 1]]


@app.post("/predict", response_model=PredictResponse)
def predict(payload: PredictRequest) -> PredictResponse:
    score = _score([payload.model_dump()])[0]
    return PredictResponse(probability=score, model_version=str(STATE["version"]))


@app.post("/predict/batch", response_model=BatchResponse)
def predict_batch(payload: BatchRequest) -> BatchResponse:
    scores = _score([row.model_dump() for row in payload.rows])
    return BatchResponse(probabilities=scores, model_version=str(STATE["version"]))
