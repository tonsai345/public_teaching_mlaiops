"""Lab 5 — compile pipeline/pipeline.yaml into your provider's pipeline service.

This module is Layer 3, so provider SDKs are allowed here and nowhere else. The DAG stays
in YAML; only the translation lives here. That separation is what you argue for or against
in Lab 5 Task 4.

Implement ONE compile function, for your provider.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

SPEC = Path(__file__).resolve().parents[1] / "pipeline" / "pipeline.yaml"


def load_spec(path: Path = SPEC) -> dict[str, Any]:
    """Read the neutral DAG and expand ${VAR} references from the environment."""
    raw = path.read_text()
    for key, value in os.environ.items():
        raw = raw.replace(f"${{{key}}}", value)
    return yaml.safe_load(raw)


def compile_aws(spec: dict[str, Any]):
    """SageMaker Pipelines.

    Each step becomes a ProcessingStep or TrainingStep; `condition` becomes a
    ConditionStep. Note that SageMaker's condition steps branch rather than abort, so
    `on_failure: abort` needs a FailStep on the else branch — an asymmetry worth
    mentioning in your Lab 5 write-up.
    """
    raise NotImplementedError("TODO Lab 5: build a sagemaker.workflow.pipeline.Pipeline")


def compile_azure(spec: dict[str, Any]):
    """Azure ML Pipelines."""
    from azure.ai.ml import Input, Output, command
    from azure.ai.ml.constants import AssetTypes
    from azure.ai.ml.dsl import pipeline
    from azure.ai.ml.entities import Environment

    repo_root = str(Path(__file__).resolve().parents[1])
    cfg_env = {
        "BLOB_URI": os.environ.get("BLOB_URI", ""),
        "AZURE_STORAGE_CONNECTION_STRING": os.environ.get("AZURE_STORAGE_CONNECTION_STRING", ""),
        "MODEL_REGISTRY_NAME": os.environ.get("MODEL_REGISTRY_NAME", "itcs355"),
        "MLFLOW_TRACKING_URI": os.environ.get("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db"),
    }
    compute_default = os.environ.get("TRAIN_INSTANCE", "cpu-cluster")
    by_name = {s["name"]: s for s in spec["steps"]}

    def make_env(image: str) -> Environment:
        return Environment(image=image, name="itcs355-lab5-env")

    @pipeline(name=spec["name"], description="ITCS355 Lab 5 training pipeline")
    def dag():
        s = by_name["ingest"]
        ingest_job = command(
            code=repo_root,
            command="python scripts/make_dataset.py --out ${{outputs.raw_data}}/sensors.csv",
            environment=make_env(s["image"]), compute=compute_default,
            environment_variables=cfg_env,
            outputs={"raw_data": Output(type=AssetTypes.URI_FOLDER, mode="rw_mount")},
        )

        s = by_name["validate"]
        validate_job = command(
            code=repo_root,
            command="pytest -q tests/test_data.py",
            environment=make_env(s["image"]), compute=compute_default,
            environment_variables={**cfg_env, "DATA_PATH": "${{inputs.raw_data}}/sensors.csv"},
            inputs={"raw_data": Input(type=AssetTypes.URI_FOLDER, mode="ro_mount")},
            on_error="fail",
        )
        validate_job.inputs.raw_data = ingest_job.outputs.raw_data

        s = by_name["train"]
        train_job = command(
            code=repo_root,
            command="python -m src.train --data-path ${{inputs.raw_data}}/sensors.csv "
                    "--metrics-out ${{outputs.metrics}}/metrics.json --model-out ${{outputs.model}}",
            environment=make_env(s["image"]), compute=compute_default,
            environment_variables=cfg_env,
            inputs={"raw_data": Input(type=AssetTypes.URI_FOLDER, mode="ro_mount")},
            outputs={
                "model": Output(type=AssetTypes.URI_FOLDER, mode="rw_mount"),
                "metrics": Output(type=AssetTypes.URI_FOLDER, mode="rw_mount"),
            },
        )
        train_job.inputs.raw_data = ingest_job.outputs.raw_data

        s = by_name["evaluate"]
        evaluate_job = command(
            code=repo_root,
            command="python scripts/evaluation_gate.py "
                    "--metrics ${{inputs.metrics}}/metrics.json "
                    "--decision-out ${{outputs.gate_decision}}/gate_decision.json",
            environment=make_env(s["image"]), compute=compute_default,
            environment_variables=cfg_env,
            inputs={"metrics": Input(type=AssetTypes.URI_FOLDER, mode="ro_mount")},
            outputs={"gate_decision": Output(type=AssetTypes.URI_FOLDER, mode="rw_mount")},
        )
        evaluate_job.inputs.metrics = train_job.outputs.metrics

        s = by_name["register"]
        register_job = command(
            code=repo_root,
            command="python scripts/register.py "
                    "--model-dir ${{inputs.model}} "
                    "--metrics ${{inputs.metrics}}/metrics.json",
            environment=make_env(s["image"]), compute=compute_default,
            environment_variables=cfg_env,
            inputs={
                "model": Input(type=AssetTypes.URI_FOLDER, mode="ro_mount"),
                "metrics": Input(type=AssetTypes.URI_FOLDER, mode="ro_mount"),
            },
        )
        register_job.inputs.model = train_job.outputs.model
        register_job.inputs.metrics = train_job.outputs.metrics

        s = by_name["deploy_staging"]
        deploy_job = command(
            code=repo_root,
            command="python scripts/deploy.py --model ${MODEL_REGISTRY_NAME}:latest --endpoint itcs355-serve",
            environment=make_env(s["image"]), compute=compute_default,
            environment_variables=cfg_env,
        )

        # Return only the FINAL job in the chain. Azure ML requires every job
        # to be reachable from a returned output. Since deploy_job depends on
        # register_job -> evaluate_job -> train_job -> validate_job -> ingest_job,
        # returning deploy_job's output proves the whole chain is connected.
        return {
            "final_output": deploy_job.outputs,
        }

    return dag()


def submit_azure(ml_client=None):
    """Compile and submit. Called by `make pipeline`."""
    spec = load_spec()
    job = compile_azure(spec)
    if ml_client is None:
        from src import config as _cfg
        _cfg.load(strict=False)
        from azure.ai.ml import MLClient
        from azure.identity import DefaultAzureCredential
        ml_client = MLClient(
            DefaultAzureCredential(),
            os.environ["AZURE_SUBSCRIPTION_ID"],
            os.environ.get("AZURE_RESOURCE_GROUP", "itcs355-6688063-rg"),
            os.environ.get("AZURE_WORKSPACE", "itcs355-workspace"),
        )
    submitted = ml_client.jobs.create_or_update(job)
    print(f"submitted: {submitted.name}")
    print(f"studio:    {submitted.studio_url}")
    return submitted


def compile_gcp(spec: dict[str, Any]):
    """Vertex AI Pipelines.

    Kubeflow Pipelines underneath: steps become container components, conditions become
    dsl.If blocks. The compiled artifact is a JSON file you submit, so your build step
    produces a file rather than an object — different from the other two.
    """
    raise NotImplementedError("TODO Lab 5: compile a KFP pipeline and submit to Vertex")


COMPILERS = {"aws": compile_aws, "azure": compile_azure, "gcp": compile_gcp}


def compile_for(provider: str, spec: dict[str, Any] | None = None):
    spec = spec or load_spec()
    try:
        return COMPILERS[provider.lower()](spec)
    except KeyError:
        raise ValueError(f"No pipeline compiler for {provider!r}") from None
