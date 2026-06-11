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
| `<HOST_PROJECT>` | Project that will own the Workload Identity Pool and absorb API billing. Pick an existing infra/security project or create one. | "Which GCP project should host the SubImage Workload Identity Pool and absorb API billing?" |
| `<TENANT_ACCOUNT_ID>` | SubImage tenant AWS account ID. SubImage auto-fills this in **Settings -> Modules -> GCP** and in the GCP setup docs. It is also visible in the AWS module principal ARN. | "What is your SubImage tenant AWS account ID? It should be a 12-digit AWS account ID from the GCP setup docs or the AWS principal ARN." |
| `<TENANT_ID>` | SubImage tenant slug. Same setup docs table; also appears in `<TENANT_ID>-subimage-readonly`. | "What is your SubImage tenant ID? It is the slug used in `<TENANT_ID>-subimage-readonly`." |
| Coverage scope | Org root, a folder, or a single project. | "Should SubImage cover the entire organization, a specific folder, or one project?" |
| GAR scanning | Whether SubImage should scan images in Google Artifact Registry. | "Should SubImage scan container images stored in Google Artifact Registry? If yes, which projects or repositories contain them?" |
| Optional roles | Whether to include `cloudasset.viewer`, `bigquery.dataViewer`, `bigquery.connectionUser`, `cloudsql.viewer`, `notebooks.viewer`, or `run.viewer`. | "Do you want optional coverage for Cloud Asset Inventory policy bindings, BigQuery, Cloud SQL, Notebooks, or Cloud Run? Default: only the three required roles." |
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
| `roles/resourcemanager.organizationViewer` | Discover the organization, projects, and folders. |
| `roles/resourcemanager.folderViewer` | Enumerate folder hierarchy. |

Optional roles:

| Role | Adds |
|---|---|
| `roles/cloudasset.viewer` | Effective IAM policy bindings and IAM fallback when a target project's IAM API is disabled. |
| `roles/run.viewer` | Cloud Run services, jobs, and executions. |
| `roles/notebooks.viewer` | Vertex AI Workbench resources. |
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
- **GAR image scanning needs Artifact Registry access.** If the user wants vulnerability/SBOM scanning for GAR images, grant `roles/artifactregistry.reader` on the relevant repositories or projects. Organization scope is easiest but broader than necessary.
- **Sync calls bill against the host project.** Enable APIs on the host project that owns the pool/provider. Optional API gaps do not break the whole sync; SubImage logs warnings and skips those collectors.
- **Selective sync has hidden dependencies.** `policy_bindings` depends on `iam`. `permission_relationships` depends on both `iam` and `policy_bindings`. `bigquery_connection` depends on `bigquery`.
- **Do not pass placeholder strings.** Substitute `<ORG_ID>`, `<HOST_PROJECT>`, `<TENANT_ACCOUNT_ID>`, and `<TENANT_ID>` before running any command.

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
  # Example: ["roles/cloudasset.viewer", "roles/run.viewer"]
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
    "roles/resourcemanager.organizationViewer",
    "roles/resourcemanager.folderViewer",
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
    roles/resourcemanager.organizationViewer \
    roles/resourcemanager.folderViewer; do
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

## Enable optional APIs on the host project

Enable optional APIs based on what the user wants synced:

```bash
gcloud services enable compute.googleapis.com --project="$HOST_PROJECT"
gcloud services enable storage.googleapis.com --project="$HOST_PROJECT"
gcloud services enable container.googleapis.com --project="$HOST_PROJECT"
gcloud services enable dns.googleapis.com --project="$HOST_PROJECT"
gcloud services enable cloudkms.googleapis.com --project="$HOST_PROJECT"
gcloud services enable bigtableadmin.googleapis.com --project="$HOST_PROJECT"
gcloud services enable sqladmin.googleapis.com --project="$HOST_PROJECT"
gcloud services enable cloudasset.googleapis.com --project="$HOST_PROJECT"
gcloud services enable cloudfunctions.googleapis.com --project="$HOST_PROJECT"
gcloud services enable run.googleapis.com --project="$HOST_PROJECT"
gcloud services enable secretmanager.googleapis.com --project="$HOST_PROJECT"
gcloud services enable artifactregistry.googleapis.com --project="$HOST_PROJECT"
gcloud services enable aiplatform.googleapis.com --project="$HOST_PROJECT"
gcloud services enable notebooks.googleapis.com --project="$HOST_PROJECT"
gcloud services enable bigquery.googleapis.com --project="$HOST_PROJECT"
gcloud services enable bigqueryconnection.googleapis.com --project="$HOST_PROJECT"
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
    roles/resourcemanager.organizationViewer \
    roles/resourcemanager.folderViewer; do
  gcloud organizations add-iam-policy-binding "$ORG_ID" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$ROLE"
done

gcloud iam service-accounts keys create subimage-sa.json \
  --iam-account="$SA_EMAIL"
```

Store the key in AWS Secrets Manager and paste the ARN into `gcp_service_account_key`, or paste the JSON into SubImage's managed secret field.

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
- **GAR image scanning fails**: grant `roles/artifactregistry.reader` on the specific repositories or projects that contain images.
- **Sync logs say "API disabled"**: enable the corresponding API on the host project, or leave it disabled if the user does not need that collector.
- **Selective sync surprise**: `policy_bindings` depends on `iam`; `permission_relationships` depends on both `iam` and `policy_bindings`; `bigquery_connection` depends on `bigquery`.

## References

- Canonical doc: https://app.subimage.io/docs/modules/gcp
- Workload Identity Federation with AWS: https://cloud.google.com/iam/docs/workload-identity-federation-with-other-clouds
