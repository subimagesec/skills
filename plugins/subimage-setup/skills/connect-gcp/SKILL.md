---
name: connect-gcp
description: Connect a Google Cloud organization to SubImage with Workload Identity Federation or, only when WIF is not possible, a service account JSON key. Use when the user asks to "connect GCP to SubImage", "set up GCP scanning", "wire GCP into SubImage", or works in a Terraform repo and wants SubImage to inventory GCP projects, folders, IAM, and Artifact Registry images. Covers Terraform and gcloud paths.
---

# Connect GCP to SubImage

## What this does

Creates a Google Workload Identity Pool and AWS provider that trust the SubImage tenant AWS role, grants Google Cloud IAM roles directly to that WIF principal, and gives the user the three values to enter in the SubImage GCP module. Service account JSON keys are covered only as a fallback for environments that cannot use WIF.

## When to use

✅ User wants to onboard a Google Cloud organization, folder, or project into SubImage.
✅ User asks for GCP WIF setup, IAM bindings, Terraform, or `gcloud` commands for SubImage scanning.
✅ User is in their IaC repo and wants to commit the GCP setup as code.

❌ User wants to scan GKE pods at the Kubernetes layer: this skill stops at the GCP resource/IAM layer; combine with `subimage-setup:connect-kubernetes-outpost` if the cluster API is private.
❌ User only wants service account key setup and already knows WIF is impossible: skip to [Fallback: service account key](#fallback-service-account-key).

## Required inputs

Before generating commands or HCL, collect these values. **If any are missing, ask the user explicitly.** Do not invent values or paste literal placeholders into customer commands.

| Value | Where to find it | If missing, ask |
|---|---|---|
| `<ORG_ID>` | Numeric organization ID. `gcloud organizations list` returns it. | "What is your GCP organization ID? Run `gcloud organizations list` to find it." |
| `<HOST_PROJECT>` | Project that will own the Workload Identity Pool, or the service account on the JSON-key path. Discovery and Cloud Asset calls use it as their quota project. Pick an existing infra/security project or create one. | "Which GCP project should own the SubImage Workload Identity Pool? Discovery and Cloud Asset API calls are charged to it." |
| `<TENANT_ACCOUNT_ID>` | SubImage tenant AWS account ID. SubImage auto-fills this in **Settings -> Modules -> GCP** and in the GCP setup docs. It is also visible in the AWS module principal ARN. | "What is your SubImage tenant AWS account ID? It should be a 12-digit AWS account ID from the GCP setup docs or the AWS principal ARN." |
| `<TENANT_ID>` | SubImage tenant slug. Same setup docs table; also appears in `<TENANT_ID>-subimage-readonly`. | "What is your SubImage tenant ID? It is the slug used in `<TENANT_ID>-subimage-readonly`." |
| Coverage scope | Org root, a folder, or a single project. | "Should SubImage cover the entire organization, a specific folder, or one project?" |
| GAR scanning | Whether SubImage should scan images in Google Artifact Registry. | "Should SubImage scan container images stored in Google Artifact Registry? If yes, which projects or repositories contain them?" |
| Optional roles | Whether to include `bigquery.dataViewer`, `bigquery.connectionUser`, `cloudsql.viewer`, `notebooks.viewer`, or the list-only API key custom role. | "Do you want optional coverage for BigQuery, Cloud SQL, Notebooks, or API keys? Default: only the six required roles." |
| Path choice | Terraform or `gcloud`. | "Which path: Terraform (recommended for IaC repos) or `gcloud` (one-off setup)?" |

Suggested IDs:

```text
Workload Identity Pool ID: subimage-wip
AWS provider ID: subimage-aws-provider
SubImage AWS role name: <TENANT_ID>-subimage-readonly
```

## Permissions baseline

Grant these roles to the WIF principal at the organization level, folder level, or project level depending on the requested scope:

| Role | Purpose |
|---|---|
| `roles/iam.securityReviewer` | Read IAM policies, relationships, and Workload Identity Federation pools/providers. If the user substitutes a custom role, it must include `iam.workloadIdentityPools.list` and `iam.workloadIdentityPoolProviders.list`, or they must also grant `roles/iam.workloadIdentityPoolViewer`. |
| `roles/compute.viewer` | Compute Engine inventory, including instances, networking, SSL policies, and target proxies. |
| `roles/resourcemanager.organizationViewer` | Discover the organization, projects, and folders. |
| `roles/resourcemanager.folderViewer` | Enumerate folder hierarchy. |
| `roles/cloudasset.viewer` | Effective IAM policy bindings and IAM fallback when a target project's IAM API is disabled. Attack paths and IAM permission analysis depend on it. |
| `roles/run.viewer` | Cloud Run services, jobs, executions, and revisions. Revisions hold the image digest behind a service deployed by tag, which SubImage needs to link the service to its image for scanning and vulnerability action items. |

Optional roles:

| Role | Adds |
|---|---|
| `roles/notebooks.viewer` | Vertex AI Workbench resources. |
| Custom role with `apikeys.keys.list` | GCP API key inventory. Do not use `roles/serviceusage.apiKeysViewer`: it also grants `apikeys.keys.getKeyString`, which reads every key's secret value, and SubImage only lists keys. See [API key inventory](#api-key-inventory). |
| `roles/cloudsql.viewer` | Cloud SQL instances, databases, and users. |
| `roles/bigquery.dataViewer` | BigQuery datasets and tables. |
| `roles/bigquery.connectionUser` | BigQuery connection resources. |
| `roles/artifactregistry.reader` | Pull Artifact Registry images for vulnerability and SBOM scanning. Prefer repository or project scope for this role when practical. |

## Gotchas

Read these before generating commands; they correct the most common wrong assumptions.

- **SubImage uses direct WIF credentials.** It stores `gcp_wif_project_number`, `gcp_wif_pool_id`, and `gcp_wif_provider_id`, then creates AWS external-account credentials directly. It does not impersonate a Google service account for WIF. Do not bind scanner roles to a service account unless using the service-account-key fallback.
- **Bind roles to the WIF principal itself.** The principal must be `principalSet://iam.googleapis.com/projects/<HOST_PROJECT_NUMBER>/locations/global/workloadIdentityPools/<POOL_ID>/attribute.aws_role/arn:aws:sts::<TENANT_ACCOUNT_ID>:assumed-role/<TENANT_ID>-subimage-readonly`.
- **Token exchange success is not enough.** STS can issue a Google token while GCP APIs still return `PERMISSION_DENIED` if the IAM roles were granted to a service account, the wrong pool, the wrong host project number, or the wrong principal attribute.
- **AWS role ARN vs assumed-role ARN differ.** The AWS IAM role is `arn:aws:iam::<TENANT_ACCOUNT_ID>:role/<TENANT_ID>-subimage-readonly`. The WIF principal uses the STS assumed-role form: `arn:aws:sts::<TENANT_ACCOUNT_ID>:assumed-role/<TENANT_ID>-subimage-readonly`.
- **Policy bindings need the API and the role.** `roles/cloudasset.viewer` does nothing unless `cloudasset.googleapis.com` is enabled on the host project. Without both, the GCP sync finishes as Degraded and GCP attack paths never appear.
- **Cloud Run needs `run.revisions.get`.** Listing services works with narrower roles, but a service deployed by tag only exposes its image digest on the revision. Without `roles/run.viewer`, the sync logs `Permission 'run.revisions.get' denied` warnings and those services are never scanned.
- **GAR image scanning needs Artifact Registry access.** If the user wants vulnerability/SBOM scanning for GAR images, grant `roles/artifactregistry.reader` on the relevant repositories or projects. Organization scope is easiest but broader than necessary.
- **Host project APIs and resource APIs are enabled in different places.** An API must be enabled in the project Google charges the call to (the quota project). SubImage sets no explicit quota project, so discovery, STS, and Cloud Asset Inventory calls use the host project that owns the pool/provider; enable `cloudresourcemanager`, `serviceusage`, `iam`, `sts`, and `cloudasset` there. Every other collector (Compute, Cloud Run, GKE, API keys, and so on) runs only in scanned projects where that resource's API is enabled *in that project*. Enabling a resource API on the host project covers only the host project's own resources. Projects that run a service already have its API enabled, so do not tell the user to enable resource APIs on the host project to get org-wide coverage. A disabled resource API does not break the sync; SubImage skips that resource type for that project.
- **Selective sync has hidden dependencies.** `policy_bindings` depends on `iam`. `permission_relationships` depends on both `iam` and `policy_bindings`. `bigquery_connection` depends on `bigquery`.
- **Do not pass placeholder strings.** Substitute `<ORG_ID>`, `<HOST_PROJECT>`, `<TENANT_ACCOUNT_ID>`, and `<TENANT_ID>` before running any command.
- **A Secrets Manager ARN needs the separate Secrets account setup.** `SubImageScanRole` does not grant secret access. Before using an ARN for the service-account-key fallback, configure the account and `SubImageSecretsRole` as described below.

## Path A: Terraform

Use this when the customer's GCP IAM is owned by IaC.

```hcl
# subimage_gcp_wif.tf
variable "subimage_org_id" { type = string }
variable "subimage_host_project" { type = string }
variable "subimage_tenant_account_id" { type = string }
variable "subimage_tenant_id" { type = string }

variable "subimage_optional_roles" {
  type    = list(string)
  default = []
  # Example: ["roles/cloudsql.viewer", "roles/bigquery.dataViewer"]
}

data "google_project" "host" {
  project_id = var.subimage_host_project
}

locals {
  pool_id                    = "subimage-wip"
  provider_id                = "subimage-aws-provider"
  subimage_aws_role_name     = "${var.subimage_tenant_id}-subimage-readonly"
  subimage_assumed_role_arn  = "arn:aws:sts::${var.subimage_tenant_account_id}:assumed-role/${local.subimage_aws_role_name}"
  subimage_wif_member        = "principalSet://iam.googleapis.com/projects/${data.google_project.host.number}/locations/global/workloadIdentityPools/${google_iam_workload_identity_pool.subimage.workload_identity_pool_id}/attribute.aws_role/${local.subimage_assumed_role_arn}"
}

resource "google_iam_workload_identity_pool" "subimage" {
  project                   = var.subimage_host_project
  workload_identity_pool_id = local.pool_id
  display_name              = "SubImage AWS"
}

resource "google_iam_workload_identity_pool_provider" "subimage_aws" {
  project                            = var.subimage_host_project
  workload_identity_pool_id          = google_iam_workload_identity_pool.subimage.workload_identity_pool_id
  workload_identity_pool_provider_id = local.provider_id
  display_name                       = "SubImage AWS"

  aws {
    account_id = var.subimage_tenant_account_id
  }

  attribute_mapping = {
    "google.subject"     = "assertion.arn"
    "attribute.account"  = "assertion.account"
    "attribute.aws_role" = "assertion.arn.contains('assumed-role') ? assertion.arn.extract('{account_arn}assumed-role/') + 'assumed-role/' + assertion.arn.extract('assumed-role/{role_name}/') : assertion.arn"
  }

  attribute_condition = "assertion.arn.startsWith('${local.subimage_assumed_role_arn}/')"
}

locals {
  required_roles = [
    "roles/iam.securityReviewer",
    "roles/compute.viewer",
    "roles/resourcemanager.organizationViewer",
    "roles/resourcemanager.folderViewer",
    "roles/cloudasset.viewer",
    "roles/run.viewer",
  ]
  all_roles = concat(local.required_roles, var.subimage_optional_roles)
}

resource "google_organization_iam_member" "subimage" {
  for_each = toset(local.all_roles)
  org_id   = var.subimage_org_id
  role     = each.key
  member   = local.subimage_wif_member
}

resource "google_project_service" "core" {
  for_each = toset([
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "iam.googleapis.com",
    "sts.googleapis.com",
    "cloudasset.googleapis.com",
  ])
  project            = var.subimage_host_project
  service            = each.key
  disable_on_destroy = false
}

output "subimage_gcp_wif_project_number" {
  value = data.google_project.host.number
}

output "subimage_gcp_wif_pool_id" {
  value = google_iam_workload_identity_pool.subimage.workload_identity_pool_id
}

output "subimage_gcp_wif_provider_id" {
  value = google_iam_workload_identity_pool_provider.subimage_aws.workload_identity_pool_provider_id
}
```

For folder scope instead of org root, replace `google_organization_iam_member` with `google_folder_iam_member` and pass the folder ID. For single-project scope, use `google_project_iam_member`.

If the user wants GAR scanning, add repository- or project-scoped Artifact Registry bindings. Repository scope example:

```hcl
resource "google_artifact_registry_repository_iam_member" "subimage_reader" {
  project    = "<GAR_PROJECT>"
  location   = "<LOCATION>"
  repository = "<REPOSITORY>"
  role       = "roles/artifactregistry.reader"
  member     = local.subimage_wif_member
}
```

## Path B: gcloud

Use this for one-off setup or when the user does not want to commit Terraform.

```bash
ORG_ID=<ORG_ID>
HOST_PROJECT=<HOST_PROJECT>
TENANT_ACCOUNT_ID=<TENANT_ACCOUNT_ID>
TENANT_ID=<TENANT_ID>
POOL_ID=subimage-wip
PROVIDER_ID=subimage-aws-provider

SUBIMAGE_AWS_ROLE_NAME="${TENANT_ID}-subimage-readonly"
SUBIMAGE_ASSUMED_ROLE_ARN="arn:aws:sts::${TENANT_ACCOUNT_ID}:assumed-role/${SUBIMAGE_AWS_ROLE_NAME}"
HOST_PROJECT_NUMBER="$(gcloud projects describe "$HOST_PROJECT" --format='value(projectNumber)')"
SUBIMAGE_WIF_MEMBER="principalSet://iam.googleapis.com/projects/${HOST_PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL_ID}/attribute.aws_role/${SUBIMAGE_ASSUMED_ROLE_ARN}"

gcloud services enable \
  cloudresourcemanager.googleapis.com \
  serviceusage.googleapis.com \
  iam.googleapis.com \
  sts.googleapis.com \
  cloudasset.googleapis.com \
  --project="$HOST_PROJECT"

gcloud iam workload-identity-pools create "$POOL_ID" \
  --project="$HOST_PROJECT" \
  --location=global \
  --display-name="SubImage AWS"

gcloud iam workload-identity-pools providers create-aws "$PROVIDER_ID" \
  --project="$HOST_PROJECT" \
  --location=global \
  --workload-identity-pool="$POOL_ID" \
  --account-id="$TENANT_ACCOUNT_ID" \
  --attribute-mapping="google.subject=assertion.arn,attribute.account=assertion.account,attribute.aws_role=assertion.arn.contains('assumed-role') ? assertion.arn.extract('{account_arn}assumed-role/') + 'assumed-role/' + assertion.arn.extract('assumed-role/{role_name}/') : assertion.arn" \
  --attribute-condition="assertion.arn.startsWith('${SUBIMAGE_ASSUMED_ROLE_ARN}/')"

for ROLE in \
    roles/iam.securityReviewer \
    roles/compute.viewer \
    roles/resourcemanager.organizationViewer \
    roles/resourcemanager.folderViewer \
    roles/cloudasset.viewer \
    roles/run.viewer; do
  gcloud organizations add-iam-policy-binding "$ORG_ID" \
    --member="$SUBIMAGE_WIF_MEMBER" \
    --role="$ROLE"
done
```

For folder scope, replace `gcloud organizations add-iam-policy-binding "$ORG_ID"` with `gcloud resource-manager folders add-iam-policy-binding "<FOLDER_ID>"`. For single-project scope, use `gcloud projects add-iam-policy-binding "$PROJECT_ID"`.

If the user wants GAR scanning, prefer repository or project scope:

```bash
gcloud artifacts repositories add-iam-policy-binding "<REPOSITORY>" \
  --project="<GAR_PROJECT>" \
  --location="<LOCATION>" \
  --member="$SUBIMAGE_WIF_MEMBER" \
  --role="roles/artifactregistry.reader"
```

If repository-level bindings are impractical, use project scope:

```bash
gcloud projects add-iam-policy-binding "<GAR_PROJECT>" \
  --member="$SUBIMAGE_WIF_MEMBER" \
  --role="roles/artifactregistry.reader"
```

## API key inventory

Only if the user wants GCP API keys in the graph. Create a list-only custom role and bind it at the same scope as the required roles. Creating an organization custom role needs `roles/iam.organizationRoleAdmin`.

Terraform:

```hcl
resource "google_organization_iam_custom_role" "subimage_apikeys_list" {
  org_id      = var.subimage_org_id
  role_id     = "subimageApiKeysList"
  title       = "SubImage API key inventory"
  permissions = ["apikeys.keys.list"]
}

resource "google_organization_iam_member" "subimage_apikeys_list" {
  org_id = var.subimage_org_id
  role   = google_organization_iam_custom_role.subimage_apikeys_list.name
  member = local.subimage_wif_member
}
```

gcloud:

```bash
gcloud iam roles create subimageApiKeysList \
  --organization="$ORG_ID" \
  --title="SubImage API key inventory" \
  --permissions=apikeys.keys.list

gcloud organizations add-iam-policy-binding "$ORG_ID" \
  --member="$SUBIMAGE_WIF_MEMBER" \
  --role="organizations/${ORG_ID}/roles/subimageApiKeysList"
```

## Register the module in SubImage

1. SubImage -> **Modules -> Add -> gcp**.
2. Enter the WIF values:
   - `gcp_wif_project_number`: host project number (`$HOST_PROJECT_NUMBER` or Terraform output `subimage_gcp_wif_project_number`)
   - `gcp_wif_pool_id`: `subimage-wip` unless changed
   - `gcp_wif_provider_id`: `subimage-aws-provider` unless changed
3. Leave `gcp_service_account_key` empty when using WIF.
4. Optional: set `gcp_requested_syncs` for selective sync, such as `compute,storage,iam`. Leave empty to sync everything.
5. Optional: keep `gcp_enable_cai_iam_fallback` enabled if the user wants Cloud Asset Inventory fallback for IAM data.
6. Save and run a GCP sync.

## Fallback: service account key

Use this only when WIF is not possible. This path is separate from WIF:

1. Create a service account in the host project.
2. Grant the same required and optional roles to `serviceAccount:<SA_EMAIL>` at the chosen scope.
3. Generate a JSON key and treat it as a credential.
4. Register only `gcp_service_account_key` in SubImage. Do not also enter WIF fields.

Minimal `gcloud` fallback:

```bash
ORG_ID=<ORG_ID>
HOST_PROJECT=<HOST_PROJECT>

gcloud iam service-accounts create subimage-org-inventory \
  --project="$HOST_PROJECT" \
  --display-name="SubImage org inventory"

SA_EMAIL="subimage-org-inventory@${HOST_PROJECT}.iam.gserviceaccount.com"

for ROLE in \
    roles/iam.securityReviewer \
    roles/compute.viewer \
    roles/resourcemanager.organizationViewer \
    roles/resourcemanager.folderViewer \
    roles/cloudasset.viewer \
    roles/run.viewer; do
  gcloud organizations add-iam-policy-binding "$ORG_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$ROLE"
done

gcloud iam service-accounts keys create subimage-sa.json \
  --iam-account="$SA_EMAIL"
```

Store the key in AWS Secrets Manager and paste the ARN into `gcp_service_account_key`, or paste the JSON into SubImage's managed secret field.

If using AWS Secrets Manager:

1. Open SubImage → **Settings → Configuration** and save the AWS account ID that owns the secret.
2. Copy the SubImage-generated External ID.
3. Deploy `SubImageSecretsRole` in that account with a trust-policy `sts:ExternalId` condition matching the copied value.
4. Paste the secret ARN into `gcp_service_account_key`.

SubImage supports one Secrets account per tenant. The managed secret field does not require this AWS setup.

## Verification

There is no customer-side `gcloud --impersonate-service-account` check for the direct-WIF path because SubImage does not impersonate a Google service account. Verify the setup by checking the IAM binding target and then running the SubImage sync.

Useful pre-sync checks:

```bash
gcloud iam workload-identity-pools providers describe "$PROVIDER_ID" \
  --project="$HOST_PROJECT" \
  --location=global \
  --workload-identity-pool="$POOL_ID"

gcloud organizations get-iam-policy "$ORG_ID" \
  --flatten="bindings[].members" \
  --filter="bindings.members:$SUBIMAGE_WIF_MEMBER" \
  --format="table(bindings.role, bindings.members)"
```

Then in any MCP-connected AI client:

```text
subimageListModules()
```

Look for `gcp` with `status: synced`. If the sync fails with GCP API `PERMISSION_DENIED`, re-check that the role bindings target `$SUBIMAGE_WIF_MEMBER`, not a Google service account.

## Troubleshooting

- **STS token exchange succeeds but GCP APIs return `PERMISSION_DENIED`**: roles were likely bound to the wrong principal. Bind the required roles to the `principalSet://.../attribute.aws_role/arn:aws:sts::<TENANT_ACCOUNT_ID>:assumed-role/<TENANT_ID>-subimage-readonly` member.
- **`PERMISSION_DENIED` on `cloudresourcemanager.organizations.get`**: missing `roles/resourcemanager.organizationViewer` at the chosen scope.
- **WIF provider rejects the AWS identity**: check `aws.account_id`, `attribute_condition`, `<TENANT_ACCOUNT_ID>`, `<TENANT_ID>`, and that `sts.googleapis.com` is enabled on the host project.
- **GCP sync finishes as Degraded for policy bindings**: enable `cloudasset.googleapis.com` on the host project and grant `roles/cloudasset.viewer` at the organization level.
- **`Permission 'run.revisions.get' denied` in sync logs**: grant `roles/run.viewer`; Cloud Run services deployed by tag cannot be linked to their images without it.
- **GAR image scanning fails**: grant `roles/artifactregistry.reader` on the specific repositories or projects that contain images.
- **A resource type is missing for one project**: SubImage syncs a resource type only where its API is enabled in that project. Ask the user which project, check with `gcloud services list --enabled --project` on it, and enable the API there if they want it covered. Enabling it on the host project does not help other projects.
- **Selective sync surprise**: `policy_bindings` depends on `iam`; `permission_relationships` depends on both `iam` and `policy_bindings`; `bigquery_connection` depends on `bigquery`.

## References

- Canonical doc: https://app.subimage.io/docs/modules/gcp
- Secrets account setup: https://app.subimage.io/docs/secrets
- Workload Identity Federation with AWS: https://cloud.google.com/iam/docs/workload-identity-federation-with-other-clouds
