---
name: connect-gcp
description: Connect a Google Cloud organization to SubImage by creating a service account with org-level IAM read roles and registering its key. Use when the user asks to "connect GCP to SubImage", "set up GCP scanning", "create the SubImage GCP service account", "wire GCP into SubImage", or works in a Terraform repo and wants SubImage to inventory their GCP projects, folders, and IAM. Covers Terraform and gcloud paths.
---

# Connect GCP to SubImage

## What this does

Creates a service account `subimage-org-inventory` in a host project, grants it the IAM roles SubImage needs at the organization level, generates a JSON key, and registers it in the SubImage GCP module. Walks two paths: Terraform and `gcloud`.

## When to use

✅ User wants to onboard a Google Cloud organization, or a single project, into SubImage.
✅ User asks for the GCP service account, IAM bindings, or Terraform for SubImage scanning.
✅ User is in their IaC repo and wants the GCP setup committed as code.

❌ User is already on Workload Identity Federation and wants to remove the long-lived key: that path is not yet self-serve, contact SubImage.
❌ User wants to scan GKE pods at the Kubernetes layer: this skill stops at the GCP IAM layer; combine with `subimage-setup:connect-kubernetes-outpost` if the cluster API is private.

## Required inputs

Before running anything, collect these. **If any are missing, ask the user explicitly** rather than guessing.

| Value | Where to find it | If missing, ask |
|---|---|---|
| `<ORG_ID>` | Numeric organization ID. `gcloud organizations list` returns it. | "What is your GCP organization ID? Run `gcloud organizations list` to find it." |
| `<HOST_PROJECT>` | Project that will own the service account and absorb API billing. Pick an existing infra/security project or create one. | "Which GCP project should host the SubImage service account and absorb the API billing? Pick an existing infra/security project, or tell me to use a new one." |
| Coverage scope | Org root, a folder, or a single project. | "Should SubImage cover the entire organization, a specific folder, or one project?" |
| Optional roles | Whether to include `cloudasset.viewer`, `bigquery.dataViewer`, `cloudsql.viewer`, `notebooks.viewer`, `run.viewer`, `artifactregistry.reader`. | "Do you want any of these optional read roles on top of the required set: Cloud Asset Inventory, BigQuery, Cloud SQL, Notebooks, Cloud Run, Artifact Registry? Default: just the three required roles." |
| Path choice | Terraform or `gcloud`. | "Which path: Terraform (recommended for IaC repos) or `gcloud` (one-off setup)?" |

## Permissions baseline

Required at the organization level (or at the chosen scope):

| Role | Purpose |
|---|---|
| `roles/iam.securityReviewer` | Read IAM policies and relationships |
| `roles/resourcemanager.organizationViewer` | Discover the org, projects, and folders |
| `roles/resourcemanager.folderViewer` | Enumerate folder hierarchy |

Optional, enable based on what you want covered:

| Role | Adds |
|---|---|
| `roles/cloudasset.viewer` | Effective IAM policy bindings, IAM fallback when project IAM API is disabled |
| `roles/run.viewer` | Cloud Run services, jobs, executions |
| `roles/notebooks.viewer` | Vertex AI Workbench (Notebooks) |
| `roles/cloudsql.viewer` | Cloud SQL instances, databases, users |
| `roles/bigquery.dataViewer` | BigQuery datasets and tables |
| `roles/bigquery.connectionUser` | BigQuery connection resources |
| `roles/artifactregistry.reader` | Pull container images for vuln/SBOM scanning |

## Gotchas

Read these before generating any commands; they correct the most common wrong assumptions.

- **Sync calls bill against the host project, not the projects being scanned.** Pick a host project whose billing you control and accept that all SubImage discovery API calls land there. This is also why API enablement happens on the host, not on every scanned project.
- **A missing optional API does not break the sync.** SubImage logs a warning and skips that collector; the rest continues. Do not chase every "API disabled" warning unless the user actually wants that collector.
- **Selective sync has hidden dependencies.** `policy_bindings` depends on `iam`. `permission_relationships` depends on both `iam` and `policy_bindings`. `bigquery_connection` depends on `bigquery`. Removing a dependency without removing its dependents produces silently empty results.
- **`gcp_enable_cai_iam_fallback` is narrower than it looks.** Disabling it only turns off the IAM-via-CAI fallback. CAI-backed `policy_bindings` still run if `policy_bindings` is in `gcp_requested_syncs`. To fully avoid CAI, deselect `policy_bindings` too.
- **GKE coverage stops at the resource layer.** `container.googleapis.com` gives SubImage clusters and node pools. In-cluster scanning (pods, RBAC, configmaps) requires a public cluster API or the `connect-kubernetes-outpost` skill on top.
- **Long-lived JSON keys are a credential.** Store in AWS Secrets Manager and feed SubImage the ARN. Rotate or migrate to Workload Identity Federation when SubImage offers it for this tenant.
- **Do not pass the placeholder strings.** Substitute `<ORG_ID>`, `<HOST_PROJECT>`, etc. before running. `gcloud organizations add-iam-policy-binding "<ORG_ID>" ...` will fail with a confusing "invalid argument" error if the literal angle-bracket form leaks through.

## Path A: Terraform

```hcl
# subimage_gcp.tf
variable "subimage_org_id"      { type = string }
variable "subimage_host_project" { type = string }

# Optional list of extra roles to add on top of the required set.
variable "subimage_optional_roles" {
  type    = list(string)
  default = []
  # Example: ["roles/cloudasset.viewer", "roles/artifactregistry.reader"]
}

resource "google_service_account" "subimage" {
  project      = var.subimage_host_project
  account_id   = "subimage-org-inventory"
  display_name = "SubImage org inventory"
}

locals {
  required_roles = [
    "roles/iam.securityReviewer",
    "roles/resourcemanager.organizationViewer",
    "roles/resourcemanager.folderViewer",
  ]
  all_roles = concat(local.required_roles, var.subimage_optional_roles)
}

resource "google_organization_iam_member" "subimage" {
  for_each = toset(local.all_roles)
  org_id   = var.subimage_org_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.subimage.email}"
}

# APIs the host project needs enabled. Add more from the gcloud list below as needed.
resource "google_project_service" "core" {
  for_each = toset([
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "iam.googleapis.com",
  ])
  project            = var.subimage_host_project
  service            = each.key
  disable_on_destroy = false
}

# Long-lived key. Avoid in production if possible: prefer Workload Identity
# Federation (contact SubImage) and remove this resource once configured.
resource "google_service_account_key" "subimage" {
  service_account_id = google_service_account.subimage.name
}

output "subimage_sa_email" {
  value = google_service_account.subimage.email
}

# Sensitive. Either store it in your secret manager and feed SubImage the ARN,
# or paste the decoded value directly into the SubImage UI.
output "subimage_sa_key_b64" {
  value     = google_service_account_key.subimage.private_key
  sensitive = true
}
```

To get the JSON key:

```bash
terraform output -raw subimage_sa_key_b64 | base64 --decode > subimage-sa.json
```

For folder scope instead of org root, swap `google_organization_iam_member` for `google_folder_iam_member` and pass `folder` instead of `org_id`. For a single project, use `google_project_iam_member`.

## Path B: gcloud

```bash
ORG_ID=<ORG_ID>
HOST_PROJECT=<HOST_PROJECT>

# 1. Create the service account in the host project.
gcloud iam service-accounts create subimage-org-inventory \
  --project="$HOST_PROJECT" \
  --display-name="SubImage org inventory"

SA_EMAIL="subimage-org-inventory@${HOST_PROJECT}.iam.gserviceaccount.com"

# 2. Grant the required roles at the organization root.
for ROLE in \
    roles/iam.securityReviewer \
    roles/resourcemanager.organizationViewer \
    roles/resourcemanager.folderViewer; do
  gcloud organizations add-iam-policy-binding "$ORG_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$ROLE"
done

# 3. Optional: add any extra roles from the table above. Example:
gcloud organizations add-iam-policy-binding "$ORG_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/cloudasset.viewer"

# 4. Generate a JSON key (treat as a credential).
gcloud iam service-accounts keys create subimage-sa.json \
  --iam-account="$SA_EMAIL"
```

For folder scope: replace `gcloud organizations add-iam-policy-binding "$ORG_ID"` with `gcloud resource-manager folders add-iam-policy-binding "<FOLDER_ID>"`. For a single project: `gcloud projects add-iam-policy-binding "$PROJECT_ID"`.

## Enable APIs on the host project

Sync calls are billed against the host project. Enable at minimum the core three:

```bash
gcloud services enable \
  cloudresourcemanager.googleapis.com \
  serviceusage.googleapis.com \
  iam.googleapis.com \
  --project="$HOST_PROJECT"
```

For broader coverage, also enable: `compute`, `storage`, `container`, `dns`, `cloudkms`, `bigtableadmin`, `sqladmin`, `cloudasset`, `cloudfunctions`, `run`, `secretmanager`, `artifactregistry`, `aiplatform`, `notebooks`, `bigquery`, `bigqueryconnection`. SubImage logs a warning and skips collectors whose APIs are disabled, so missing APIs do not break the sync.

## Register the module in SubImage

1. SubImage → **Modules → Add → gcp**.
2. Paste the JSON key content into `gcp_service_account_key`, or store it in AWS Secrets Manager and paste the ARN instead.
3. Optional: `gcp_requested_syncs` for selective sync (e.g. `compute,storage,iam`). Leave empty to sync everything.
4. Optional: `gcp_enable_cai_iam_fallback` (default on) lets SubImage backfill IAM data via Cloud Asset Inventory when a project's IAM API is disabled.
5. Save and **Run Sync**.

## Verification

```bash
# Quick sanity check the SA can reach the org IAM API.
gcloud auth activate-service-account --key-file=subimage-sa.json
gcloud organizations get-iam-policy <ORG_ID> --format=json | head
```

Then in any MCP-connected AI client:

```
subimageListModules()
```

Look for `gcp` with `status: synced`.

## Troubleshooting

- **`PERMISSION_DENIED` on `cloudresourcemanager.organizations.get`**: missing `roles/resourcemanager.organizationViewer` on the org. Re-run the role binding.
- **Sync logs say "API disabled"**: the corresponding API is not enabled on the host project. Either enable it or live with the missing collector.
- **Selective sync surprise**: `policy_bindings` depends on `iam`; `permission_relationships` depends on both `iam` and `policy_bindings`; `bigquery_connection` depends on `bigquery`.

## References

- Canonical doc: https://app.subimage.io/docs/modules/gcp
- Workload Identity Federation: contact SubImage to migrate off long-lived keys.
