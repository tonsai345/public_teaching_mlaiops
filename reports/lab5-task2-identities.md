# Lab 5 Task 2 — Least privilege identities

Subscription: ce0c4612-4e67-4c7b-b2e6-0a2198ad93b3
Resource group: itcs355-6688063-rg
Workspace: itcs355-workspace
Storage account: itcs3556688063sa
Container registry: itcs3556688063acr

## Identities and roles

| Identity | Principal ID | Roles | Why each is needed |
|---|---|---|---|
| itcs355-train-mi | 76f36c9d-1504-4f5b-aa06-e010daec6a33 | Storage Blob Data Reader (storage account) · AzureML Data Scientist (workspace) | Read training data from blob; write job outputs, metrics, model artifacts into the workspace |
| itcs355-serve-mi | ba960dd4-6a11-4124-baca-810556d438fa | AcrPull (ACR) | Pull the serving image at Container Apps startup only |
| itcs355-ci-mi    | 0fc70af9-14b0-4800-a967-47ba934697a9 | AcrPush (ACR) · AzureML Data Scientist (workspace) | Push images to ACR; submit pipeline jobs; register models |

## Separation of duties

- itcs355-train-mi: **no** ACR access, **no** deploy capability, **no** role-assignment capability
- itcs355-serve-mi: **no** storage data-plane access, **no** push, **no** job submission
- itcs355-ci-mi:    **no** direct storage access, **no** ability to pull running endpoint images

The split is intentional. A serving identity scoped to AcrPull only cannot exfiltrate
training data even if the container is compromised; a training identity scoped to
Storage Blob Data Reader cannot push a malicious image.

## Test: remove one permission and observe the break

See `reports/lab5-task2-break-evidence.txt`.

In one line: removing Storage Blob Data Contributor from the signed-in user caused
blob uploads to fail with `HttpResponseError: This request is not authorized to
perform this operation using this permission. ErrorCode: AuthorizationPermissionMismatch`.
The permission is load-bearing and the pipeline would fail at ingest without it.
