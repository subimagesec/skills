---
name: connect-declarative-schema
description: Bring custom context (service catalogs, owner/team mappings, business criticality, CMDB) into the SubImage graph via the Declarative Schema module. Use when the user asks to "add a service catalog to SubImage", "import a CMDB", "wire team ownership into SubImage", "set up declarative schema", or has a list of services/apps/owners they want joined against existing AWS/GCP/Azure/Identity nodes. Walks data formatting (JSONL), YAML schema authoring, and the S3 or GCS plumbing.
---

# Connect a Declarative Schema source to SubImage

## What this does

Loads custom nodes and relationships into SubImage's Neo4j graph from JSONL files on S3 or GCS, described by a YAML schema. SubImage automatically wires every loaded node under a per-schema `DeclarativeSchemaRoot` via `RESOURCE` edges so cleanup and re-syncs are safe. This skill covers three steps:

1. Shape the source data as JSONL (one record per line, `id` required).
2. Author the YAML schema (node labels, properties, relationships).
3. Set up the plumbing (S3 cross-account role **or** GCS bucket access via the existing GCP module) and register the schema entry in the SubImage UI.

## When to use

✅ User has a service/app catalog, owner mapping, or CMDB they want joined against existing SubImage nodes (`AWSAccount`, `AWSUser`, `EC2Instance`, etc.).
✅ User wants to attach business criticality or team metadata to existing cloud resources.
✅ User already runs the GCP module and wants to drop data on GCS, or owns an AWS account they can deploy IAM in.

❌ User wants arbitrary ETL or transforms during ingestion: Declarative Schema is declarative only. Pre-shape the JSONL before upload.
❌ User wants to *modify* properties on nodes ingested by another module (e.g. write to an `EC2Instance` node directly): use relationships instead, do not redeclare existing labels.
❌ User wants real-time push of records: this is sync-based, not event-driven.

## Required inputs

Before generating any files, collect these. **If any are missing, ask the user explicitly.**

| Value | Where to find it | If missing, ask |
|---|---|---|
| Storage provider | S3 or GCS. | "Will the schema and data files live on S3 or GCS? GCS reuses your existing SubImage GCP module credentials, no extra IAM. S3 needs a cross-account IAM role deployed in the bucket-owning account." |
| `<BUCKET_NAME>` | Bucket that holds `schema.yaml` and the JSONL data. | "Which bucket should hold the schema and data files?" |
| `<SCHEMA_ID>` | Unique id for this schema entry in the module config. Lowercase letters, numbers, hyphens, underscores. | "Pick a short identifier for this schema entry (e.g. `service_catalog`, `team_ownership`). Lowercase, hyphens or underscores only. Must be unique across schema entries in this module." |
| `<TENANT_ACCOUNT_ID>` (S3 only) | SubImage tenant AWS account ID. **Settings → Modules → AWS** in the SubImage UI. | "What is your SubImage tenant AWS account ID? Same value as for the AWS module setup, in the principal ARN at Settings → Modules → AWS. Format: 12 digits." |
| `<TENANT_ID>` (S3 only) | SubImage tenant slug (e.g. `acme`). | "What is your SubImage tenant ID (the slug, e.g. `acme`)?" |
| `<BUCKET_ACCOUNT_ID>` (S3 only) | 12-digit AWS account ID that owns the bucket; where `SubImageDeclarativeSchemaRole` will be deployed. | "Which AWS account owns the bucket? `SubImageDeclarativeSchemaRole` will be deployed there." |
| Node types | What real-world things become graph nodes (services, teams, apps, owners, ...). | "Which entities do you want as nodes? List each one with the fields you have on it." |
| Joins | Which existing SubImage labels these nodes should connect to and via which property. | "Which existing SubImage labels should each new node type connect to (e.g. `AWSAccount.id`, `AWSUser.email`), and via which field on your records?" |

GCS path has no AWS inputs, it inherits the GCP module's service account credentials.

## Gotchas

Read these before generating any files; they correct the most common wrong assumptions.

- **`id` is mandatory on every node type.** It must appear in `node_properties` and be present (non-null, unique within that node_label) on every JSONL record. Without `id`, validation fails and nothing loads.
- **`data_path` and `schema_path` must share the same provider in one YAML file.** You can mix S3 and GCS across *different* schema entries in the same module config, but inside one YAML file every `data_path` must be on the same bucket protocol as the `schema_path`.
- **Join fields don't need to be in `node_properties`.** A field used only to match a relationship target (e.g. `aws_account_id`) is fine in the JSONL without being declared as a stored property, unless you also want it on the node.
- **`direction_inward` is mandatory and the semantics are easy to flip.** `direction_inward: false` means *this node points OUT to the target* (`(this)-[:REL]->(target)`); `true` means *the target points IN to this node* (`(this)<-[:REL]-(target)`). Pick from the existing label's perspective when modelling: a `Service` "runs in" an `AWSAccount` => `direction_inward: false` on `Service`.
- **`SubImageDeclarativeSchemaRole` is a separate role from `SubImageScanRole`.** Different name, different external ID (`subimage-declarative-schema`), different policy. Do not graft the policy onto the AWS scan role: SubImage assumes a specific ARN derived from `aws_account_id` you put in the schema entry.
- **External ID is fixed.** `subimage-declarative-schema` is hardcoded; do not customise it. The trust policy must require it via `sts:ExternalId`.
- **GCS path reuses the GCP module SA without rebinding.** If the GCP module is not yet connected, set that up first via `subimage-setup:connect-gcp`, then grant `roles/storage.objectViewer` to that SA on the bucket.
- **Empty strings != null for optional relationship fields.** Use `null` (or omit the key) in JSONL records when a relationship target is unknown. An empty string creates a relationship to a node whose join field is `""`.
- **Schema files are capped at 10 MB, data files at 30 GB.** Larger CMDB exports must be split across multiple JSONL files (one per node type already enforces some split).
- **Do not redeclare an existing SubImage label.** Defining `node_label: AWSAccount` will not enrich AWS-module nodes; it creates a parallel `AWSAccount` namespace tied to the `DeclarativeSchemaRoot` and confuses downstream queries. Use a new label and connect it with a relationship instead.
- **Do not pass the placeholder strings.** `<TENANT_ACCOUNT_ID>`, `<TENANT_ID>`, `<BUCKET_NAME>` must be substituted in CloudFormation/Terraform/CLI before applying. AWS will accept the literal angle-bracket form and the sync silently fails.

## Step 1: Shape the data (JSONL)

One JSONL file per `node_label`. One JSON object per line, no array wrapper, no commas between lines.

Required:

- `id`: unique within the node_label, string.

Recommended:

- Every property listed in the YAML's `node_properties` should be present on every record (use `null` for missing values).
- Every field used as a relationship `source field` should be on every record that participates in that relationship.

Example, `services.jsonl`:

```jsonl
{"id":"svc-001","name":"checkout-api","criticality":"high","aws_account_id":"123456789012","owner_email":"alice@acme.example"}
{"id":"svc-002","name":"billing-worker","criticality":"medium","aws_account_id":"123456789012","owner_email":"bob@acme.example"}
{"id":"svc-003","name":"reports","criticality":"low","aws_account_id":"987654321098","owner_email":null}
```

Notes:

- `aws_account_id` and `owner_email` are join fields; they don't have to appear in `node_properties` unless the user also wants them stored on the node.
- `null` is the right value for "unknown owner", not `""`.

## Step 2: Author the YAML schema

One YAML file per logical schema entry; a list of node definitions inside.

Top-level structure of each node definition:

| Field | Required | Notes |
|---|---|---|
| `node_label` | yes | Neo4j label for the node. Use a new label, do not reuse one created by another module. |
| `node_properties` | yes | List of fields persisted on the node. **Must include `id`.** |
| `schema_version` | yes | Integer, bump when you change the shape. |
| `data_path` | yes | `s3://...` or `gs://...` URI of the JSONL for this node type. Must use the same protocol as `schema_path`. |
| `relationships` | optional | List of edge definitions, see below. |
| `extra_node_labels` | optional | Additional labels to set on the node (e.g. `["BusinessAsset"]`). |

Each relationship entry:

| Field | Required | Notes |
|---|---|---|
| `rel_label` | yes | Edge type (uppercase Neo4j convention: `OWNED_BY`, `RUNS_IN_ACCOUNT`). |
| `target_node_label` | yes | Existing or other-schema-defined label. |
| `field` | yes | Field on **this** node's record used as the source of the match. |
| `target_field` | yes | Field on the target node used as the match key (usually `id`). |
| `direction_inward` | yes | `false` => `(this)-[:REL]->(target)`. `true` => `(this)<-[:REL]-(target)`. |

Example, `schema.yaml` joining a service catalog to existing AWS accounts and users:

```yaml
- node_label: Service
  schema_version: 1
  node_properties:
    - id
    - name
    - criticality
  relationships:
    - rel_label: RUNS_IN_ACCOUNT
      target_node_label: AWSAccount
      field: aws_account_id
      target_field: id
      direction_inward: false
    - rel_label: OWNED_BY
      target_node_label: AWSUser
      field: owner_email
      target_field: email
      direction_inward: false
  data_path: s3://acme-subimage/data/services.jsonl
```

Reuse the same shape for additional node types (teams, applications, ...). All node types defined in this file must share the same protocol on their `data_path`.

For mixed-provider tenants, split into multiple YAML files (one per provider) and add one schema entry per YAML in the Declarative Schema module config.

## Step 3a: Plumbing for S3

SubImage derives the role ARN from `aws_account_id` you set in the module config:

```
arn:aws:iam::<BUCKET_ACCOUNT_ID>:role/SubImageDeclarativeSchemaRole
```

with the fixed external ID `subimage-declarative-schema`. Pick one of CloudFormation, Terraform, or CLI. Substitute placeholders before applying.

### Option A: CloudFormation

```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: IAM Role for SubImage Declarative Schema bucket access.

Resources:
  SubImageDeclarativeSchemaRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: SubImageDeclarativeSchemaRole
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              AWS:
                - 'arn:aws:iam::<TENANT_ACCOUNT_ID>:role/<TENANT_ID>-subimage-readonly'
            Action: sts:AssumeRole
            Condition:
              StringEquals:
                sts:ExternalId: subimage-declarative-schema

  AllowSubImageDeclarativeSchemaAccess:
    Type: AWS::IAM::Policy
    Properties:
      PolicyName: AllowSubImageDeclarativeSchemaAccess
      Roles:
        - !Ref SubImageDeclarativeSchemaRole
      PolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Sid: ReadDeclarativeSchemaObjects
            Effect: Allow
            Action:
              - s3:GetObject
            Resource:
              - 'arn:aws:s3:::<BUCKET_NAME>/schema.yaml'
              - 'arn:aws:s3:::<BUCKET_NAME>/data/*'

Outputs:
  SubImageDeclarativeSchemaRoleArn:
    Value: !GetAtt SubImageDeclarativeSchemaRole.Arn
```

### Option B: Terraform

```hcl
resource "aws_iam_role" "subimage_declarative_schema" {
  name = "SubImageDeclarativeSchemaRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        AWS = [
          "arn:aws:iam::<TENANT_ACCOUNT_ID>:role/<TENANT_ID>-subimage-readonly",
        ]
      }
      Action = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "sts:ExternalId" = "subimage-declarative-schema"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "subimage_declarative_schema" {
  name = "AllowSubImageDeclarativeSchemaAccess"
  role = aws_iam_role.subimage_declarative_schema.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "ReadDeclarativeSchemaObjects"
      Effect = "Allow"
      Action = ["s3:GetObject"]
      Resource = [
        "arn:aws:s3:::<BUCKET_NAME>/schema.yaml",
        "arn:aws:s3:::<BUCKET_NAME>/data/*",
      ]
    }]
  })
}

output "subimage_declarative_schema_role_arn" {
  value = aws_iam_role.subimage_declarative_schema.arn
}
```

### Option C: aws-cli

Save the trust policy as `trust-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "AWS": "arn:aws:iam::<TENANT_ACCOUNT_ID>:role/<TENANT_ID>-subimage-readonly" },
    "Action": "sts:AssumeRole",
    "Condition": {
      "StringEquals": { "sts:ExternalId": "subimage-declarative-schema" }
    }
  }]
}
```

Save the inline policy as `role-policy.json`:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "ReadDeclarativeSchemaObjects",
    "Effect": "Allow",
    "Action": ["s3:GetObject"],
    "Resource": [
      "arn:aws:s3:::<BUCKET_NAME>/schema.yaml",
      "arn:aws:s3:::<BUCKET_NAME>/data/*"
    ]
  }]
}
```

Then:

```bash
aws iam create-role \
  --role-name SubImageDeclarativeSchemaRole \
  --assume-role-policy-document file://trust-policy.json

aws iam put-role-policy \
  --role-name SubImageDeclarativeSchemaRole \
  --policy-name AllowSubImageDeclarativeSchemaAccess \
  --policy-document file://role-policy.json
```

### Upload schema and data

```bash
aws s3 cp schema.yaml s3://<BUCKET_NAME>/schema.yaml
aws s3 cp services.jsonl s3://<BUCKET_NAME>/data/services.jsonl
# repeat for each JSONL referenced by data_path
```

## Step 3b: Plumbing for GCS

GCS path has no IAM role to deploy. It reuses the existing GCP module service account.

Prerequisites:

1. The SubImage GCP module is already connected (see `subimage-setup:connect-gcp`). If not, do that first.
2. The GCP host project's SA email is `subimage-org-inventory@<HOST_PROJECT>.iam.gserviceaccount.com` (or whatever the user picked during GCP setup).

Grant the SA read access on the bucket or the relevant prefix:

```bash
gcloud storage buckets add-iam-policy-binding gs://<BUCKET_NAME> \
  --member="serviceAccount:subimage-org-inventory@<HOST_PROJECT>.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
```

Upload the files:

```bash
gcloud storage cp schema.yaml gs://<BUCKET_NAME>/schema.yaml
gcloud storage cp services.jsonl gs://<BUCKET_NAME>/data/services.jsonl
```

## Step 4: Register the schema entry in SubImage

1. SubImage → **Modules → Add → declarative_schema** (or edit if already present).
2. Add a schema entry:
   - `schema_path`: `s3://<BUCKET_NAME>/schema.yaml` or `gs://<BUCKET_NAME>/schema.yaml`.
   - `schema_id`: e.g. `service_catalog`. Must be unique within this module config.
   - `aws_account_id`: 12-digit `<BUCKET_ACCOUNT_ID>` for S3 entries. **Leave blank for GCS entries.**
3. Repeat for every schema entry; you can mix S3 and GCS entries in one module.
4. Save and hit **Run Sync**.

## Verification

After a successful sync, validate via Cypher (adapt to your labels):

```cypher
// Confirm the schema root and its nodes
MATCH (root:DeclarativeSchemaRoot {id: '<SCHEMA_ID>'})-[:RESOURCE]->(n)
RETURN labels(n)[0] AS label, count(n) AS count
ORDER BY label;
```

```cypher
// Verify the custom join against existing AWS data
MATCH (s:Service)-[:RUNS_IN_ACCOUNT]->(a:AWSAccount)
RETURN s.id, s.name, s.criticality, a.id
LIMIT 25;
```

```cypher
// All declarative schema roots, last refresh time
MATCH (root:DeclarativeSchemaRoot)
RETURN root.id AS schema_id, root.lastupdated AS lastupdated
ORDER BY schema_id;
```

From any MCP-connected AI client:

```
subimageListModules()
```

Look for `declarative_schema` with `status: synced` and a recent `lastSyncEndedAt`.

## Troubleshooting

- **Sync fails with "validation error: missing `id`"**: a JSONL record has no `id` field, or `id` is not in `node_properties`. Fix the data or the schema.
- **`AccessDenied` calling `sts:AssumeRole` (S3)**: the trust policy is missing the SubImage principal ARN, or `sts:ExternalId` is wrong. Re-deploy with the correct values.
- **`AccessDenied` reading `schema.yaml` or `data/*.jsonl` (S3)**: the role policy resource list does not cover the object key you uploaded to. Either move the files to match, or widen the policy.
- **GCS reads fail with `403`**: the GCP module SA does not have `roles/storage.objectViewer` on the bucket. Grant it.
- **Relationship missing despite sync success**: the join field value in your JSONL does not match any target node's property. Confirm both sides exist with matching strings (case-sensitive).
- **Provider mismatch error**: a `data_path` inside the schema file uses a different protocol than `schema_path`. Split into two schema entries (one per provider).

## References

- Canonical doc: https://app.subimage.io/docs/modules/declarative_schema
- AWS connection (for the `<TENANT_ACCOUNT_ID>` / `<TENANT_ID>` values): `subimage-setup:connect-aws`
- GCP connection (prerequisite for GCS path): `subimage-setup:connect-gcp`
