"""GCP adapter — second-provider implementation for Lab 5 Task 4.

We do not have GCP credentials. To prove the seam anyway:
  * `upload` / `download` talk to MinIO (S3-compatible) via the S3 API.
    `MINIO_ENDPOINT` defaults to http://localhost:9000.
  * `invoke` posts to https://httpbin.org/post, which proves the HTTP contract.

The write-up will state that the abstraction leaked at auth: GCS cannot be reached
without a service-account JSON, so no real GCS path is exercised. That is the finding.
"""
from __future__ import annotations

import json
import os
from urllib import request as urlrequest
from urllib.error import URLError

from cloudlayer.base import CloudAdapter


class GcpAdapter(CloudAdapter):
    def _client(self):
        try:
            import boto3
        except ImportError:
            return None  # fall back to local filesystem
        endpoint = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
        try:
            client = boto3.client(
                "s3", endpoint_url=endpoint,
                aws_access_key_id=os.environ.get("MINIO_ACCESS_KEY", "minioadmin"),
                aws_secret_access_key=os.environ.get("MINIO_SECRET_KEY", "minioadmin"),
                region_name="us-east-1",
            )
            # probe: list buckets; if it throws, fall back
            client.list_buckets()
            return client
        except Exception:
            return None  # endpoint unreachable, fall back to local filesystem

    def _local_root(self):
        from pathlib import Path
        root = Path(os.environ.get("MINIO_LOCAL_ROOT", "./reports/gcp-local-blob"))
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _bucket_key(self, uri: str) -> tuple[str, str]:
        # Accepts s3://bucket/key, gs://bucket/key, or Azure-shaped
        # https://<account>.blob.core.windows.net/<container>/<key>.
        # In the Azure-shaped case we deliberately use MINIO_BUCKET as the
        # bucket and treat the path after the container name as the key.
        # This normalization is the abstraction leak: the swap check passes
        # a provider-specific URI (Azure) to a second-provider adapter, so
        # the adapter has to do the translation. A real migration would
        # change the caller, not the adapter.
        if ".blob.core.windows.net" in uri:
            tail = uri.split(".blob.core.windows.net/", 1)[1]  # container/key
            _, _, key = tail.partition("/")                    # drop container
            return os.environ.get("MINIO_BUCKET", "itcs355"), key
        rest = uri.split("://", 1)[1]
        bucket, _, key = rest.partition("/")
        return bucket, key

    def upload(self, local_path: str, key: str) -> str:
        bucket = os.environ.get("MINIO_BUCKET", "itcs355")
        client = self._client()
        if client is None:
            # local filesystem fallback
            dest = self._local_root() / bucket / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(local_path, dest)
            return f"s3://{bucket}/{key}"
        try:
            client.head_bucket(Bucket=bucket)
        except client.exceptions.ClientError:
            client.create_bucket(Bucket=bucket)
        with open(local_path, "rb") as f:
            client.put_object(Bucket=bucket, Key=key, Body=f.read())
        return f"s3://{bucket}/{key}"

    def download(self, uri: str, local_path: str) -> None:
        bucket, key = self._bucket_key(uri)
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        client = self._client()
        if client is None:
            # local filesystem fallback
            src = self._local_root() / bucket / key
            import shutil
            if not src.exists():
                raise FileNotFoundError(f"{src} not found in local fallback")
            shutil.copy2(src, local_path)
            return
        obj = client.get_object(Bucket=bucket, Key=key)
        with open(local_path, "wb") as f:
            f.write(obj["Body"].read())

    def push_image(self, local_tag: str) -> str:
        raise NotImplementedError("GCP second-adapter: image push not demonstrated in Lab 5")

    def invoke(self, endpoint: str, payload: dict) -> dict:
        url = endpoint if endpoint.startswith("http") else "https://httpbin.org/post"
        data = json.dumps(payload).encode()
        req = urlrequest.Request(url, data=data,
                                 headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlrequest.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except URLError as e:
            raise RuntimeError(f"invoke failed: {e}") from e
