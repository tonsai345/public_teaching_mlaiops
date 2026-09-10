"""Azure adapter. Implement upload/download/push_image for Lab 1.

SDK:  pip install azure-storage-blob azure-identity azure-containerregistry
Docs: BlobServiceClient for storage; ACR push goes through `docker push` after
      `az acr login --name <registry>`.

Hints for Lab 1:
  * BLOB_URI is either abfss://container@account.dfs.core.windows.net/prefix or
    https://account.blob.core.windows.net/container/prefix. Pick one form and parse
    it here, never in src/.
  * Use DefaultAzureCredential rather than a connection string. It picks up your CLI
    login locally and your managed identity in CI, which is what Lab 4 needs.
  * push_image must return the digest reference: registry.azurecr.io/repo@sha256:...
  * Azure tags live on the resource, not the blob. Tag the storage account, the
    registry, and later the workspace with cfg.tags(1).
"""
from __future__ import annotations

import os
import re
import subprocess
from typing import Any

from cloudlayer.base import CloudAdapter


class AzureAdapter(CloudAdapter):
    def upload(self, local_path: str, key: str) -> str:
        """Upload a file to Azure Blob Storage.
        
        Args:
            local_path: Path to the local file to upload
            key: The blob key (path) within the container
            
        Returns:
            The full URI of the uploaded blob
        """
        from azure.storage.blob import BlobServiceClient

        cfg = self.cfg
        blob_uri = cfg.blob_uri
        conn_str = cfg.azure_storage_connection_string

        if not blob_uri:
            raise ValueError("BLOB_URI not configured in cloud.env")
        if not conn_str:
            raise ValueError("AZURE_STORAGE_CONNECTION_STRING not configured in cloud.env")

        # Parse BLOB_URI: https://account.blob.core.windows.net/container
        rest = blob_uri.replace("https://", "")
        parts = rest.split("/")

        if len(parts) < 2:
            raise ValueError(f"Invalid BLOB_URI: {blob_uri}")

        container_name = parts[1]

        # Use connection string
        client = BlobServiceClient.from_connection_string(conn_str)
        container_client = client.get_container_client(container_name)

        # Upload the file
        with open(local_path, "rb") as f:
            container_client.upload_blob(key, f, overwrite=True)

        return f"{blob_uri}/{key}"

    def download(self, uri: str, local_path: str) -> None:
        """Download a file from Azure Blob Storage.
        
        Args:
            uri: The full URI of the blob to download
            local_path: Path where the file should be saved
        """
        from azure.storage.blob import BlobServiceClient
        import os

        cfg = self.cfg
        conn_str = cfg.azure_storage_connection_string

        if not conn_str:
            raise ValueError("AZURE_STORAGE_CONNECTION_STRING not configured in cloud.env")

        # Parse URI: https://account.blob.core.windows.net/container/key
        rest = uri.replace("https://", "")
        parts = rest.split("/")

        if len(parts) < 3:
            raise ValueError(f"Invalid URI: {uri}")

        container_name = parts[1]
        blob_name = "/".join(parts[2:])

        # Use connection string
        client = BlobServiceClient.from_connection_string(conn_str)
        container_client = client.get_container_client(container_name)

        # Create parent directories only if there is a directory path
        parent_dir = os.path.dirname(local_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        # Download the blob
        with open(local_path, "wb") as f:
            data = container_client.download_blob(blob_name).readall()
            f.write(data)

    def push_image(self, image_name: str) -> str:
        """Push a Docker image to Azure Container Registry.
        
        Args:
            image_name: Name of the image to push (e.g., "itcs355-lab1:2018ce9")
        
        Returns:
            str: The digest reference (e.g., "registry.azurecr.io/repo@sha256:...")
        """
        # Get config from self.cfg (defined in CloudAdapter)
        cfg = self.cfg

        # Get registry from config using dot notation
        registry = cfg.container_registry.split("/")[0]
        if not registry:
            raise ValueError("CONTAINER_REGISTRY not configured in cloud.env")

        # Extract repository name from container_registry
        repository = cfg.container_registry.split("/")[-1]
        if not repository:
            repository = "itcs355-lab1"

        # Full image tag
        full_tag = f"{registry}/{repository}:latest"

        try:
            # 1. Login to ACR
            subprocess.run(
                ["az", "acr", "login", "--name", registry.split(".")[0]],
                check=True,
                capture_output=True
            )

            # 2. Tag the local image
            subprocess.run(
                ["docker", "tag", image_name, full_tag],
                check=True,
                capture_output=True
            )

            # 3. Push the image
            result = subprocess.run(
                ["docker", "push", full_tag],
                check=True,
                capture_output=True,
                text=True
            )

            # 4. Get the digest from the push output
            digest_match = re.search(r'digest:\s*(sha256:[a-f0-9]+)', result.stdout)
            if not digest_match:
                # Alternative: get from docker inspect
                inspect_result = subprocess.run(
                    ["docker", "inspect", full_tag, "--format", "{{.RepoDigests}}"],
                    check=True,
                    capture_output=True,
                    text=True
                )
                digest_match = re.search(r'\["(.*?)@(sha256:[a-f0-9]+)"\]', inspect_result.stdout)
                if digest_match:
                    registry_name = digest_match.group(1)
                    digest = digest_match.group(2)
                    return f"{registry_name}@{digest}"
                else:
                    raise ValueError("Could not find digest for pushed image")

            # Return the digest reference
            return f"{full_tag}@{digest_match.group(1)}"

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            raise RuntimeError(f"Failed to push image: {error_msg}") from e

    # submit_training / register_model  -> Lab 2 (Azure ML command job + model registry)
    # deploy / invoke                   -> Lab 3 (managed online endpoint + deployment)
    # emit_metric                       -> Lab 4 (Azure Monitor custom metric)
    # generate                          -> Lab 5 (managed LLM endpoint; read the usage block for to>
    # teardown                          -> Lab 5 (resource graph query by tag)
