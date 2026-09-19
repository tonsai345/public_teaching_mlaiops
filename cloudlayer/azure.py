"""Azure adapter. Lab 1 (upload/download/push_image) + Lab 2 (jobs + registry).

SDK:  pip install azure-storage-blob azure-identity azure-ai-ml
Docs: BlobServiceClient for storage; ACR push goes through `docker push`
      after `az acr login`; Lab 2 jobs go through azure-ai-ml.
"""
from __future__ import annotations

import os
import re
import subprocess
from typing import Any

from cloudlayer.base import CloudAdapter


# --- Azure ML constants for Lab 2 ---------------------------------------------
AZURE_SUBSCRIPTION_ID = "ce0c4612-4e67-4c7b-b2e6-0a2198ad93b3"
AZURE_RESOURCE_GROUP = "itcs355-6688063-rg"
AZURE_WORKSPACE = "itcs355-workspace"
AZURE_COMPUTE = "cpu-cluster"
AZURE_EXPERIMENT = "itcs355-lab2"


class AzureAdapter(CloudAdapter):

    # --- Lab 1 ---------------------------------------------------------------
    def upload(self, local_path: str, key: str) -> str:
        """Upload a file to Azure Blob Storage."""
        from azure.storage.blob import BlobServiceClient

        cfg = self.cfg
        blob_uri = cfg.blob_uri
        conn_str = cfg.azure_storage_connection_string

        if not blob_uri:
            raise ValueError("BLOB_URI not configured in cloud.env")
        if not conn_str:
            raise ValueError("AZURE_STORAGE_CONNECTION_STRING not configured in cloud.env")

        rest = blob_uri.replace("https://", "")
        parts = rest.split("/")
        if len(parts) < 2:
            raise ValueError(f"Invalid BLOB_URI: {blob_uri}")
        container_name = parts[1]

        client = BlobServiceClient.from_connection_string(conn_str)
        container_client = client.get_container_client(container_name)

        with open(local_path, "rb") as f:
            container_client.upload_blob(key, f, overwrite=True)

        return f"{blob_uri}/{key}"

    def download(self, uri: str, local_path: str) -> None:
        """Download a file from Azure Blob Storage."""
        from azure.storage.blob import BlobServiceClient

        cfg = self.cfg
        conn_str = cfg.azure_storage_connection_string

        if not conn_str:
            raise ValueError("AZURE_STORAGE_CONNECTION_STRING not configured in cloud.env")

        rest = uri.replace("https://", "")
        parts = rest.split("/")
        if len(parts) < 3:
            raise ValueError(f"Invalid URI: {uri}")
        container_name = parts[1]
        blob_name = "/".join(parts[2:])

        client = BlobServiceClient.from_connection_string(conn_str)
        container_client = client.get_container_client(container_name)

        parent_dir = os.path.dirname(local_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        with open(local_path, "wb") as f:
            data = container_client.download_blob(blob_name).readall()
            f.write(data)

    def push_image(self, image_name: str) -> str:
        """Push a Docker image to ACR, return the digest reference."""
        cfg = self.cfg

        registry = cfg.container_registry.split("/")[0]
        if not registry:
            raise ValueError("CONTAINER_REGISTRY not configured in cloud.env")

        repository = cfg.container_registry.split("/")[-1] or "itcs355-lab1"
        full_tag = f"{registry}/{repository}:latest"

        try:
            subprocess.run(
                ["az", "acr", "login", "--name", registry.split(".")[0]],
                check=True, capture_output=True,
            )
            subprocess.run(
                ["docker", "tag", image_name, full_tag],
                check=True, capture_output=True,
            )
            result = subprocess.run(
                ["docker", "push", full_tag],
                check=True, capture_output=True, text=True,
            )

            digest_match = re.search(r'digest:\s*(sha256:[a-f0-9]+)', result.stdout)
            if not digest_match:
                inspect_result = subprocess.run(
                    ["docker", "inspect", full_tag, "--format", "{{.RepoDigests}}"],
                    check=True, capture_output=True, text=True,
                )
                digest_match = re.search(
                    r'\["(.*?)@(sha256:[a-f0-9]+)"\]', inspect_result.stdout
                )
                if digest_match:
                    return f"{digest_match.group(1)}@{digest_match.group(2)}"
                raise ValueError("Could not find digest for pushed image")

            return f"{full_tag}@{digest_match.group(1)}"

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            raise RuntimeError(f"Failed to push image: {error_msg}") from e

    # --- Lab 2 ---------------------------------------------------------------
    def _ml_client(self):
        """Build an MLClient using the current Azure CLI login."""
        from azure.ai.ml import MLClient
        from azure.identity import DefaultAzureCredential

        return MLClient(
            DefaultAzureCredential(),
            AZURE_SUBSCRIPTION_ID,
            AZURE_RESOURCE_GROUP,
            AZURE_WORKSPACE,
        )

    def submit_training(self, image_uri: str, args: dict[str, Any],
                        instance: str | None = None, spot: bool = False) -> str:
        """Submit a training job to Azure ML as a command job.

        Runs on cpu-cluster (on-demand). Spot and serverless are blocked
        by quota on this Azure for Students subscription; the cost model
        in src/costs.py applies the spot factor to reflect production pricing.
        """
        from azure.ai.ml import command
        from azure.ai.ml.entities import Environment, UserIdentityConfiguration

        ml_client = self._ml_client()
        cfg = self.cfg

        cmd_parts = ["python /app/scripts/remote_entrypoint.py"]
        for key, value in args.items():
            cmd_parts.append(f"--{key.replace('_', '-')} {value}")
        command_str = " ".join(cmd_parts)

        env_vars = {
            "BLOB_URI": cfg.blob_uri,
            "AZURE_STORAGE_CONNECTION_STRING": cfg.azure_storage_connection_string,
            "MLFLOW_TRACKING_URI": "sqlite:////tmp/mlflow.db",
        }

        result = subprocess.run(
            ["az", "acr", "repository", "show-manifests",
             "--name", "itcs3556688063acr",
             "--repository", "itcs355",
             "--orderby", "time_desc",
             "--query", "[0].digest",
             "-o", "tsv"],
            check=True, capture_output=True, text=True,
        )
        image_digest = result.stdout.strip().replace("sha256:", "")[:12]

        custom_env = Environment(
            image=image_uri,
            name="itcs355-lab2-env",
            version=image_digest,
            description="Lab 2 training environment",
        )

        job = command(
            code=None,
            command=command_str,
            environment=custom_env,
            compute=AZURE_COMPUTE,
            display_name="lab2-train-remote",
            experiment_name=AZURE_EXPERIMENT,
            environment_variables=env_vars,
            identity=UserIdentityConfiguration(),
        )

        returned_job = ml_client.jobs.create_or_update(job)
        return returned_job.name

    def wait_training(self, job_id: str) -> dict[str, Any]:
        """Poll until the job completes, then return its status."""
        import time
        ml_client = self._ml_client()

        while True:
            job = ml_client.jobs.get(job_id)
            if job.status in ("Completed", "Failed", "Canceled"):
                break
            time.sleep(10)

        return {
            "job_id": job_id,
            "status": job.status,
            "display_name": job.display_name,
            "studio_url": job.studio_url,
        }

    def register_model(self, model_uri: str, name: str,
                       lineage: dict[str, str] | None = None,
                       stage: str = "Staging") -> str:
        """Register a model in Azure ML with full lineage.

        Returns the version string (e.g. "1").
        """
        from azure.ai.ml.entities import Model
        from azure.ai.ml.constants import AssetTypes

        ml_client = self._ml_client()

        tags = dict(lineage or {})
        tags["stage"] = stage

        model = Model(
            path=model_uri,
            name=name,
            description="ITCS355 Lab 2 registered model",
            type=AssetTypes.CUSTOM_MODEL,
            tags=tags,
        )

        registered = ml_client.models.create_or_update(model)
        return str(registered.version)

    # deploy / invoke  -> Lab 3 (managed online endpoint + deployment)
    # emit_metric      -> Lab 4 (Azure Monitor custom metric)
    # generate         -> Lab 5 (managed LLM endpoint)
    # teardown         -> Lab 5 (resource graph query by tag)
