---
name: identify-iac-repositories
description: Identify and rank CodeRepository nodes that manage Infrastructure as Code (Terraform, OpenTofu, Pulumi, CloudFormation, CDK, Bicep, Helm, Kustomize, GitOps) in the SubImage graph. Use when the user asks to "find our IaC repos", "which repositories manage infrastructure", "where is our Terraform", "rank infrastructure repositories", or wants an IaC repository inventory built from graph evidence.
---

# Identify IaC repositories

## What this does

Returns a concise, ranked list of `CodeRepository` candidates that likely manage
infrastructure, grouped by confidence, with one short line of evidence each. It
reads only what is already in the SubImage graph: it does not open files, and it
uses `subimageListModules` to decide which searches are even worth running.

Internal categories (keep them separate; never conflate one for another):

1. `cloud_infrastructure`: Terraform, OpenTofu, Pulumi, CloudFormation, CDK, or Bicep.
2. `kubernetes_configuration`: Helm, Kustomize, Kubernetes manifests, or GitOps.
3. `deployment_automation`: cloud authentication and application deployment.
4. `artifact_build`: application images, packages, and other artifacts.

Never describe a deployment or build repository as IaC without additional evidence.

## When to use

✅ The user wants an inventory of which existing repositories manage infrastructure.
✅ The user wants those repositories ranked by how confident the evidence is.
✅ The user asks where their Terraform / Helm / Pulumi / CloudFormation lives.

❌ The user wants to know which providers to *connect* to SubImage, or what is
   missing from their setup. That is `subimage-mcp:improve-subimage-coverage`; this
   skill inventories repos that are already ingested, it does not audit coverage.
❌ The user wants a full audit or a coverage/compliance report. This returns a
   candidate list, not an audit.

## Prerequisites

- Runs against the SubImage MCP server. Call `subimageReadMe` once per session
  before any other SubImage tool.
- Tools used: `subimageReadMe`, `subimageListModules`, `subimageRunCypher`, and
  (for label/relationship validation) `subimageListModuleSchemaNodes` /
  `subimageGetNodesSchema`.

## Rules

- Execute read-only Cypher only.
- Return a candidate list, not an audit or coverage report.
- Give one short evidence summary per candidate.
- Use the score internally. Do not show numeric scores unless the user asks.
- Except for direct Spacelift attribution, require at least two independent signal
  families before returning `probable`.
- Do not add points repeatedly for duplicate workflows or actions.
- Distinguish absence of evidence from evidence of absence.
- Never display secret or variable values; use names only.
- GitHub and GitLab manifest nodes represent dependency manifests. They are not
  inventories of IaC files.
- GitHub secret values and GitLab variable values are not ingested.
- The graph does not generically model Terraform, OpenTofu, or Pulumi files, plans,
  states, modules, or resources.

## Workflow

### Step 1: List enabled modules first

Call `subimageListModules()` before running any search. Build a set
`enabled_modules` from the rows where the module is actually enabled (configured and
connected, not merely listed). The values are SubImage module slugs (`aws`, `gcp`,
`github`, `gitlab`, `kubernetes`, `spacelift`, `circleci`, `semgrep`, ...).

This is the canonical source for what is queryable. Do not try to reconstruct
coverage with Cypher (`MATCH (n) WHERE n._module_name IS NOT NULL`,
`ModuleSyncMetadata`, `SubImageModule`); those are not the source of truth and an
unlabeled scan will time out.

### Step 2: Choose which searches to run

Run only the searches whose backing module is in `enabled_modules`. If a module is
disabled or absent, **skip its search silently** (no candidates and no caveat from
that source). Gating map:

| Search | Required module(s) |
|---|---|
| Spacelift attribution | `spacelift` (assumed-role resolution also needs `aws`) |
| GitHub (languages, workflows, OIDC role use, vars/secrets/envs) | `github` |
| GitLab CI (config, includes, variables, environments) | `gitlab` |
| CircleCI | `circleci` |
| AWS CodeBuild | `aws` |
| Semgrep opportunistic file evidence | `semgrep` |
| Image counterevidence (`Image`-[:PACKAGED_FROM]->repo) | the container/image module |

Confirm the exact slug against the live `subimageListModules` output; if a search's
module slug is not present, skip that search.

### Step 3: Labels and relationships

Every label, relationship, and direction used below was checked against the SubImage
Cartography schema. `CodeRepository` is a semantic ontology label carried by both
`GitHubRepository` and `GitLabProject`, so matching `(:CodeRepository)` spans both
providers. The schema-confirmed directed patterns are:

- `(:GitHubRepository)-[:LANGUAGE]->(:ProgrammingLanguage)`
- `(:GitHubRepository)-[:HAS_WORKFLOW]->(:GitHubWorkflow)`
- `(:GitHubWorkflow)-[:USES_ACTION]->(:GitHubAction)`
- `(:GitHubWorkflow)-[:REFERENCES_SECRET]->(:GitHubActionsSecret)`
- `(:GitHubRepository)-[:HAS_VARIABLE]->(:GitHubActionsVariable)`
- `(:GitHubRepository)-[:HAS_SECRET]->(:GitHubActionsSecret)`
- `(:GitHubRepository)-[:HAS_ENVIRONMENT]->(:GitHubEnvironment)` and
  `(:GitLabProject)-[:HAS_ENVIRONMENT]->(:GitLabEnvironment)`
- `(:GitHubRepository)-[:ASSUMED_ROLE_WITH_WEB_IDENTITY]->(:AWSRole)`
- `(:SpaceliftStack)-[:GENERATED]->(:SpaceliftRun)`,
  `(:SpaceliftRun)-[:AFFECTED]->(...)`, `(:SpaceliftStack)-[:ASSUMES]->(:AWSRole)`
- `(:GitLabProject)-[:RESOURCE]->(:GitLabCIConfig)`,
  `(:GitLabCIConfig)-[:USES_INCLUDE]->(:GitLabCIInclude)`,
  `(:GitLabCIConfig)-[:REFERENCES_VARIABLE]->(:GitLabCIVariable)`
- `(:CircleCIProject)-[:BUILDS]->(:CodeRepository)`,
  `(:CircleCIProject)-[:RESOURCE]->(:CircleCIPipeline)`
- `(:SemgrepSASTFinding|:SemgrepSecretsFinding)-[:FOUND_IN]->(:CodeRepository)`
- `(:Image)-[:PACKAGED_FROM]->(:CodeRepository)`

Schema still varies by tenant and module version, so if a query errors or returns
nothing on a given tenant, confirm the labels with
`subimageGetNodesSchema(node_names=[...])` (and `searchModelQueries` for a cached
query of the same shape) and adjust to what the live schema reports. Do not invent a
label, relationship, direction, or property that the schema does not list.

See `subimage-mcp:build-cypher-query` for the full query rules; every query in this
skill follows them:

- every node variable carries a label (no bare `MATCH (n)`);
- every relationship has a variable and an explicit type
  (`(r)-[hw:HAS_WORKFLOW]->(w)`, never `-[:HAS_WORKFLOW]->` or `-[]->`);
- use the schema-declared direction;
- include `LIMIT` (default 100), return only needed fields, always return the node
  `id`;
- use `OPTIONAL MATCH` only where a missing relationship should still keep the row;
- one statement per `subimageRunCypher`, and no `//` comments in the query string.

### Step 4: Inventory repositories

```cypher
MATCH (r:CodeRepository)
RETURN
  labels(r) AS labels,
  r.id AS id,
  coalesce(r._ont_fullname, r.fullname, r.path_with_namespace, r.name) AS repository,
  coalesce(r._ont_url, r.url, r.web_url) AS url,
  coalesce(r._ont_archived, r.archived, false) AS archived,
  r._module_name AS source_module,
  r.lastupdated AS lastupdated
ORDER BY repository
LIMIT 100
```

Normally exclude archived or disabled repositories. Report one only when an active
resource is still attributed to it.

### Step 5: Spacelift attribution (module `spacelift`)

Spacelift provides the strongest signal in the current data model.

```cypher
MATCH (s:SpaceliftStack)
OPTIONAL MATCH (s)-[gen:GENERATED]->(run:SpaceliftRun)
OPTIONAL MATCH (run)-[aff:AFFECTED]->(resource)
OPTIONAL MATCH (s)-[asr:ASSUMES]->(role:AWSRole)
RETURN
  s.id AS stack_id,
  s.name AS stack_name,
  s.repository AS repository,
  s.branch AS branch,
  s.project_root AS project_root,
  s._ont_type AS pipeline_type,
  collect(DISTINCT {labels: labels(resource), id: resource.id, arn: resource.arn}) AS affected_resources,
  collect(DISTINCT role.arn) AS assumed_roles,
  count(DISTINCT run) AS observed_runs
ORDER BY stack_name
LIMIT 100
```

`SpaceliftStack.repository` is a string property, not an edge to `CodeRepository`.
Resolve it to a repository by normalizing HTTPS/SSH URLs, the `.git` suffix, casing,
`owner/repository` names, and GitHub/GitLab hostnames. Do not invent a relationship.
A stack that matches a repository, strengthened by an `AFFECTED` run, gives very high
confidence for the affected resources.

### Step 6: GitHub (module `github`)

**Languages.** `primarylanguage = "HCL"` is strong evidence; HCL present is useful.
This model does not retain language percentages.

```cypher
MATCH (r:GitHubRepository)
OPTIONAL MATCH (r)-[lang:LANGUAGE]->(language:ProgrammingLanguage)
RETURN
  r.fullname AS repository,
  r.primarylanguage AS primary_language,
  collect(DISTINCT language.name) AS languages
ORDER BY repository
LIMIT 100
```

**Workflows, actions, and permissions.**

```cypher
MATCH (r:GitHubRepository)-[hw:HAS_WORKFLOW]->(w:GitHubWorkflow)
OPTIONAL MATCH (w)-[ua:USES_ACTION]->(a:GitHubAction)
OPTIONAL MATCH (w)-[rs:REFERENCES_SECRET]->(secret:GitHubActionsSecret)
RETURN
  r.fullname AS repository,
  collect(DISTINCT {
    name: w.name, path: w.path, state: w.state,
    triggers: w.trigger_events,
    id_token: w.permissions_id_token,
    deployments: w.permissions_deployments
  }) AS workflows,
  collect(DISTINCT a.full_name) AS actions,
  collect(DISTINCT secret.name) AS referenced_secret_names
ORDER BY repository
LIMIT 100
```

Strong `cloud_infrastructure` actions: `hashicorp/setup-terraform`, OpenTofu or
Terragrunt actions, `pulumi/actions`, CloudFormation actions, ARM or Bicep actions.
Strong `kubernetes_configuration` actions: Helm and chart-releaser actions,
Kustomize, kubectl, Argo CD or Flux. Deployment-only signals (not IaC on their own):
`aws-actions/configure-aws-credentials`, `aws-actions/amazon-ecr-login`, Azure or GCP
login, Docker build and push, `permissions_id_token = "write"`.

**Observed AWS role use.**

```cypher
MATCH (r:GitHubRepository)
OPTIONAL MATCH (r)-[oidc:ASSUMED_ROLE_WITH_WEB_IDENTITY]->(role:AWSRole)
RETURN
  r.fullname AS repository,
  collect(DISTINCT {
    role_arn: role.arn,
    last_used: oidc.last_used,
    times_used: oidc.times_used,
    first_seen: oidc.first_seen_in_time_window
  }) AS observed_oidc_roles
ORDER BY repository
LIMIT 100
```

This proves observed OIDC use (stronger than `id-token: write`), but it does not
prove the repository contains IaC.

**Variables, secrets, and environments.**

```cypher
MATCH (r:GitHubRepository)
OPTIONAL MATCH (r)-[hv:HAS_VARIABLE]->(variable:GitHubActionsVariable)
OPTIONAL MATCH (r)-[hs:HAS_SECRET]->(secret:GitHubActionsSecret)
OPTIONAL MATCH (r)-[he:HAS_ENVIRONMENT]->(environment:GitHubEnvironment)
RETURN
  r.fullname AS repository,
  collect(DISTINCT variable.name) AS variable_names,
  collect(DISTINCT secret.name) AS secret_names,
  collect(DISTINCT environment.name) AS environments
ORDER BY repository
LIMIT 100
```

Names such as `TF_*`, `TERRAFORM_*`, `AWS_*`, `ARM_*`, `AZURE_*`, `GOOGLE_*`,
`KUBECONFIG`, and `HELM_*` are supporting signals only. Never display their values.

### Step 7: GitLab (module `gitlab`)

```cypher
MATCH (project:GitLabProject)
OPTIONAL MATCH (project)-[res:RESOURCE]->(config:GitLabCIConfig)
OPTIONAL MATCH (config)-[inc:USES_INCLUDE]->(include:GitLabCIInclude)
OPTIONAL MATCH (config)-[rv:REFERENCES_VARIABLE]->(variable:GitLabCIVariable)
OPTIONAL MATCH (project)-[he:HAS_ENVIRONMENT]->(environment:GitLabEnvironment)
RETURN
  project.path_with_namespace AS repository,
  project.languages AS languages,
  collect(DISTINCT {
    file: config.file_path, stages: config.stages,
    default_image: config.default_image, trigger_rules: config.trigger_rules
  }) AS ci_configs,
  collect(DISTINCT include.location) AS includes,
  collect(DISTINCT variable.key) AS referenced_variable_names,
  collect(DISTINCT environment.name) AS environments
ORDER BY repository
LIMIT 100
```

Look for Terraform, OpenTofu, Pulumi, Helm, Kustomize, Argo CD, or Flux in
`languages`, `default_image`, `stages`, included locations, and variable names. A
`GitLabCIConfig` proves only that CI exists.

### Step 8: Other CI sources

**CircleCI** (module `circleci`). Connects CI to repositories, but pipeline runs and
job commands are not ingested.

```cypher
MATCH (project:CircleCIProject)
OPTIONAL MATCH (project)-[b:BUILDS]->(repo:CodeRepository)
OPTIONAL MATCH (project)-[res:RESOURCE]->(pipeline:CircleCIPipeline)
RETURN
  project.name AS project,
  project.vcs_url AS vcs_url,
  coalesce(repo._ont_fullname, repo.fullname, repo.path_with_namespace) AS repository,
  collect(DISTINCT {
    config_repo: pipeline.config_source_repo_full_name,
    config_path: pipeline.config_source_file_path,
    checkout_repo: pipeline.checkout_source_repo_full_name
  }) AS pipelines
LIMIT 100
```

**AWS CodeBuild** (module `aws`). No direct relationship to `CodeRepository`;
normalize `source_location` against known repositories.

```cypher
MATCH (project:AWSCodeBuildProject)
RETURN
  project.name AS project,
  project.source_type AS source_type,
  project.source_location AS source_location,
  project.environment_variables AS environment_variables,
  project.region AS region
LIMIT 100
```

### Step 9: Semgrep opportunistic evidence (module `semgrep`)

A finding can reveal an IaC path; the absence of a finding does not mean the file is
absent. `SemgrepSASTFinding` and `SemgrepSecretsFinding` both carry the ontology label
`SecurityIssue`, so seed the scan on that label (a label scan, never a bare
`MATCH (finding)`) and narrow to the two Semgrep types in the `WHERE`.

```cypher
MATCH (finding:SecurityIssue)-[fi:FOUND_IN]->(repo:CodeRepository)
WHERE (finding:SemgrepSASTFinding OR finding:SemgrepSecretsFinding)
WITH repo,
  coalesce(finding.file_path, finding.finding_path) AS path,
  finding.rule_id AS rule_id,
  finding.type AS finding_type
WHERE toLower(path) ENDS WITH ".tf"
  OR toLower(path) CONTAINS "terragrunt"
  OR toLower(path) ENDS WITH "chart.yaml"
  OR toLower(path) ENDS WITH "values.yaml"
  OR toLower(path) ENDS WITH "kustomization.yaml"
  OR toLower(path) CONTAINS "pulumi"
RETURN
  coalesce(repo._ont_fullname, repo.fullname, repo.path_with_namespace) AS repository,
  collect(DISTINCT {path: path, rule: rule_id, type: finding_type}) AS evidence
ORDER BY repository
LIMIT 100
```

### Step 10: Counterevidence (image/container module)

The ontology edge is `(:Image)-[:PACKAGED_FROM]->(:CodeRepository)` (provider-native
variants such as `(:AWSECRRepositoryImage)-[:PACKAGED_FROM]->(:GitHubRepository)` also
exist; matching on the `Image` / `CodeRepository` ontology labels covers them).

```cypher
MATCH (image:Image)-[pf:PACKAGED_FROM]->(repo:CodeRepository)
RETURN
  coalesce(repo._ont_fullname, repo.fullname, repo.path_with_namespace) AS repository,
  repo.id AS id,
  count(DISTINCT image) AS produced_images,
  collect(DISTINCT pf.match_method) AS match_methods
ORDER BY produced_images DESC
LIMIT 100
```

Producing images usually indicates `artifact_build` or an application repo. It is not
definitive: a monorepo can also contain IaC. Do not treat these as direct evidence:
workflow count; environments alone; branches or commit activity; secrets or variables
alone; GitHub Pages; Docker build and push; `AWSCloudFormationStack` without source
attribution; Kubernetes runtime state without repository provenance.

### Step 11: Score, rank, and present

Apply the scoring below, group by confidence, and render the response format. Present
the list, then ask the user to confirm it is correct.

### Step 12: Persist on confirmation

Only after the user explicitly confirms, persist the confirmed IaC-repository list to
whatever durable memory the current harness provides, so future sessions can reuse it
without re-deriving. Do not prescribe a specific tool; use the memory mechanism
available in this environment. If none is available, say so rather than silently
dropping the step. Do not save anything before the user confirms, and do not save on
a "no".

## Scoring

Use the score as an explanation aid, not a statistical truth:

| Family | Signal | Points |
|---|---|---:|
| Attribution | `SpaceliftStack.repository` resolves to the repository | +100 |
| Observed effect | Spacelift run `AFFECTED` a resource | +50 |
| Observed file | Semgrep finding in `.tf`, Terragrunt, or Pulumi path | +25 |
| Language | HCL is primary | +35 |
| Language | HCL is present but not primary | +20 |
| CI | Terraform, OpenTofu, Pulumi, or CloudFormation action | +30 |
| Kubernetes | Helm, Kustomize, or GitOps action/configuration | +25 for `kubernetes_configuration` |
| CI | Explicitly IaC-oriented include or CI image | +20 |
| Cloud | OIDC role use was actually observed | +15 |
| Cloud | OIDC permission or credentials action only | +5 |
| Metadata | Name, description, or path explicitly indicates infrastructure | +5 |
| Secrets | Cloud or IaC variable/secret names | +3, capped at +10 |
| Counterevidence | Primarily produces application images | -10 |

Count each correlated family once. Several workflows with `id-token: write` still
contribute only +5 total.

Thresholds:

- `>= 50` with at least two independent signal families, or direct Spacelift
  attribution: high confidence.
- `25-49` with at least two signal families: medium confidence.
- `10-24`, or a single meaningful signal family: low confidence.
- `< 10`: omit from the candidate list.

Except for Spacelift, never assign high or medium confidence from only one family.

## Response format

```markdown
## High confidence
- `owner/repository`: Terraform cloud infrastructure. HCL plus
  `hashicorp/setup-terraform` and observed AWS OIDC role use.

## Medium confidence
- `owner/repository`: Kubernetes configuration. Helm chart language and Helm
  release workflows.

## Low confidence
- `owner/repository`: Possible deployment automation. AWS credentials action and
  `id-token: write`, but no direct IaC signal.
```

Omit empty confidence sections. If no candidate reaches low confidence, return:

```text
No IaC repository candidates were found in the available graph data.
```

Never claim to have seen file contents when the evidence came only from a language,
action, finding, or variable name.

## Anti-patterns

- Running searches for modules that are not enabled. Gate on `subimageListModules`
  and skip disabled sources silently.
- Reconstructing module coverage with Cypher instead of `subimageListModules`.
- Treating `SpaceliftStack.repository` as a relationship to `CodeRepository`. It is a
  string; normalize and resolve it.
- Calling a deployment or build repository "IaC" on a single credentials/OIDC signal.
- Displaying secret or variable values. Names only.
- Saving to memory before the user confirms, or prescribing a specific save tool.
- Reformatting `subimageRunCypher` results as a markdown table. Summarize the rows.

## References

- Query authoring rules: `subimage-mcp:build-cypher-query`.
- Coverage / "what should I connect" audit: `subimage-mcp:improve-subimage-coverage`.
- Tool guide auto-loaded by `subimageReadMe` on first call.
