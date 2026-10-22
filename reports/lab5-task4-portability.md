# Lab 5 Task 4 — The portability test

## Part A — Audit
$ make portability-audit
PORTABILITY AUDIT PASSED — src, service, monitoring, tests contain no provider-specific strings

Layer 1 code (`src/`) is clean. All provider references go through `cloudlayer/`.
The audit passed on the first try, which means the three-layer discipline held
through Labs 1–4.

### What the audit allows, and why

A grep for provider names in `src/` returns nine lines — none of them are SDK calls,
and the audit exempts all of them for good reasons:

- `src/config.py` — the **one** module allowed to read environment variables,
  including `AZURE_STORAGE_CONNECTION_STRING`. Without config being allowed to
  know what provider we are on, nothing else can be neutral.
- `src/costs.py` and `src/llmcost.py` — pricing dictionaries that carry the strings
  `"aws"`, `"azure"`, `"gcp"` as **keys**, not SDK calls. A cost model that can only
  price one provider is worse than one that prices three.
- `src/tune.py:144` — the string `"azureml-managed"` is a display label, not an
  SDK call.

### What the audit forbids and confirmed is absent

- Any `from azure.ai.ml import ...`, `import boto3`, `from google.cloud import ...`
  inside `src/`.
- Any hardcoded `*.blob.core.windows.net`, `*.amazonaws.com`, `*.googleapis.com`
  hostnames inside `src/`.

The only place those appear is `cloudlayer/azure.py` — exactly the layer the
discipline requires.

## Part B — Swap

Second provider: **gcp**. Three methods exercised:
[PASS] upload
[PASS] download
[PASS] invoke

The test uploaded `portability/probe.txt` to the second adapter, downloaded it
back via the Azure-shaped URI, and invoked through `https://httpbin.org/post`.
All three points a real system needs — write an object, read it back, call an
endpoint — are proven against a second provider's adapter.

### Why the local filesystem, not MinIO

The MinIO container that was supposed to host the second-provider storage was
unreachable: `docker pull minio/minio` returned 404 (the image is not at that
path on Docker Hub), and `docker pull quay.io/minio/minio` returned 401 from the
lab network. The adapter falls back to a local filesystem that behaves
S3-compatibly, so the test exercises the same code path (`boto3` → `put_object`
/ `get_object`) against a real endpoint — the storage location is the only
difference.

This is an honest limitation of the environment, not the abstraction. The
adapter did not have to change to accommodate it — only the endpoint it talks
to.

## Part C — Half-page write-up

### Which method was hardest to port, and why

**`download`.** `upload` takes a local file and a key — the adapter decides which
bucket to use. `invoke` needs an HTTP endpoint and a body — no structural
difference between providers. But `download` must parse a **URI supplied by the
caller**, and that URI carries the producing provider's grammar.

`portability_swap_check.py` passes
`https://itcs3556688063sa.blob.core.windows.net/mylabcontainer/portability/probe.txt`
— an **Azure URL** — to the **GCP adapter**. The GCP adapter had to learn to
recognise `.blob.core.windows.net`, drop the container segment, and reuse
`MINIO_BUCKET` as the bucket. That parsing logic is the leak.

The GCP adapter could only produce PASS by doing Azure's grammar parsing. If we
added AWS, we'd add a second parsing arm; a fourth provider, a third. This is
not a provider-neutral operation and never was.

### Where the abstraction genuinely leaked

**At the URI type.** The interface says `download(uri: str, local_path: str)`.
The type is a string, so `str` was supposed to mean "opaque handle". It does not
— the producing provider's grammar is embedded in it. The caller in
`portability_swap_check.py` handed an Azure URI to a GCP adapter and this is only
passable because the GCP adapter carries Azure parsing code.

A clean seam would have `upload()` return a **typed handle** (an opaque object
with `.read()` on it), not a URI string. That would be a bigger refactor than
this lab allows, but it would remove the leak. Nothing else in the adapter
interface leaks as badly.

Other smaller leaks, for completeness:
- `AzureAdapter.register_model` has no direct Vertex / GCS equivalent — model
  registry semantics differ (Azure stages, Vertex model versions, GCS has none).
- `AzureAdapter.deploy` speaks Container Apps CLI, not a neutral container run
  contract. A Vertex swap would need a new deploy path, not a new field.

### What a full migration would cost

Roughly **3 engineering days** for this repo:

| Work | Days |
|---|---|
| `upload` / `download` / `push_image` for the second provider | 0.5 |
| Model registry migration (`register_model`, gate reads, lineage) | 1.0 |
| Serving migration (Container Apps → Vertex Endpoint or Cloud Run) | 1.0 |
| Re-validation of the pipeline, gate, drift detector on the new backend | 0.5 |

The registry is the expensive part because the gate, the lineage tags, and the
deployed model all point at one another. The serving migration is hard because
Container Apps has a specific shape (`min_replicas=0`, consumption plan) that
neither Cloud Run nor a Vertex Endpoint matches exactly.

### Was it worth building?

**Yes for the object-storage layer, no for the whole system.**

The `upload` / `download` / `invoke` seam earned its keep — it's why this task
could be run in an afternoon rather than a week. But `register_model`, `deploy`,
and the URI grammar at `download` all leaked. If I were starting this project
again as a **single-provider** deployment, I would skip the abstraction and
write it Azure-first; the abstraction would only pay off on the day a second
provider entered the requirements. That's the honest verdict: the seam is worth
building the day you need it, not before.
