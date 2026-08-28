---
name: explore-ai-assets
description: Explore AI assets across code, container scans, cloud AI services, provider accounts, third-party apps, credentials, and findings without treating one graph label as the whole inventory. Use when the user asks "do we have any AI agents", "show our AI inventory", "where are we using AI", "find our models and AI apps", or "investigate AI assets".
---

# Explore AI assets

## What this does

Prevents a zero-result lookup on one label from becoming the false conclusion
that the tenant has no AI assets. The important schema distinction is:

- `AIAgent`, `AITool`, `AIMemory`, `AIEmbedding`, and `AIPrompt` are conditional
  labels on code-derived `AIBOMComponent` nodes.
- `AIModel` spans code-derived models plus mapped AWS Bedrock, SageMaker, and GCP
  Vertex AI model nodes.
- Cloud-native agents and surrounding services can have provider labels such as
  `AWSBedrockAgent` and are not guaranteed to carry `AIAgent`.
- AI SaaS adoption appears separately through provider tenants, API keys, users,
  service accounts, and heuristic matches on `ThirdPartyApp`.

These lanes may be disconnected. Do not infer that one is absent because
another has no rows, and do not claim a relationship that the graph does not
contain.

## When to use

✅ Inventory or investigate AI agents, models, code components, cloud AI
services, provider accounts, or employee-authorized AI apps.

✅ Answer "do we use AI?" or "what AI is deployed?" across multiple evidence
sources.

❌ A flat inventory of one already-known non-AI resource type. Use
`subimage-mcp:inventory-via-cypher`.

❌ A vulnerability, package, IAM, or exposure investigation whose starting asset
is already known. Use the matching investigation skill.

## Required inputs

Usually none. If the user names an account, provider, repository, image, agent,
or model, use it as a filter without dropping the other relevant evidence lanes.

Ask only when the requested tenant or scope is genuinely ambiguous.

## Prerequisites

- Call `subimageReadMe` once per session.
- Call `subimageListModules` before interpreting empty results. Relevant coverage
  can come from `aibom`, cloud providers, AI provider modules, and identity
  providers. Module status is coverage metadata, not a query gate: historical or
  otherwise ingested nodes may exist even when a module is absent or disabled.
- Follow `subimage-mcp:build-cypher-query` discipline. Validate labels,
  properties, relationships, and directions with `subimageGetNodesSchema` or a
  `searchModelQueries` hit before running a template.

If MCP authorization fails, stop querying that tenant, report the exact error,
and ask the user to reconnect it. Treat every dependent lane as unavailable,
not empty.

## Workflow

### 1. Establish coverage

Read module status first. Record which relevant modules are enabled, disabled,
stale, degraded, or still syncing. An unavailable lane is a coverage gap, not a
zero count, and does not justify skipping that lane's graph query.

For labels already covered by the reference templates, validate them in one
batched `subimageGetNodesSchema` call; do not enumerate each provider module
first. Use `subimageListModuleSchemaNodes` only when the question needs labels
outside those templates. Start with:

`AIBOMSource`, `AIBOMComponent`, `AIAgent`, `AIModel`, `AITool`, `AIMemory`,
`AIPrompt`, `AIEmbedding`, `AWSBedrockAgent`, `AWSBedrockKnowledgeBase`,
`AWSBedrockGuardrail`, `AWSSageMakerEndpoint`, `AWSSageMakerModel`,
`GCPVertexAIEndpoint`, `GCPVertexAIDeployedModel`,
`GCPVertexAIWorkbenchInstance`, `ThirdPartyApp`, `APIKey`, and the provider
tenant labels returned by discovery.

Do not assume this list is exhaustive. Use current module schema to discover new
provider-native AI resources, including any Azure AI labels added after this
skill was written.

### 2. Query every applicable inventory lane

Read [`references/cypher-templates.md`](references/cypher-templates.md), then run
the smallest applicable set of templates:

Start with aggregate lane counts. Fetch identifying rows only for non-empty
lanes or when the user asks for detail.

1. **Code and workload evidence**: AIBOM agents and components, their scanned
   repositories or images, and runtime containers.
2. **Cloud-managed AI**: provider-native agents and services, plus the shared
   `AIModel` view and provider deployment paths.
3. **Provider control plane**: AI provider organizations, projects, workspaces,
   users, service accounts, and API keys.
4. **Employee adoption**: AI-related `ThirdPartyApp` nodes and authorizing
   identities. Treat name matching as heuristic evidence.
5. **Security posture**: AI-tagged rules/findings, sensitive OAuth grants,
   provider-key hygiene, and AIBOM coverage gaps.

Do not stop after the first non-empty lane. Broad AI questions require all
applicable lanes because the records are not one connected ontology.

Keep the user's scope exact. "Across code and cloud providers" requires lanes
1 and 2; do not add provider-account, employee-adoption, or security-posture
queries unless the user asks for them.

### 3. Add operational context

Prefer runtime-linked images over repository-only evidence. For cloud assets,
include tenant, status, region, execution identity, deployment, and data context
only where schema-confirmed edges exist.

For an apparent code-to-cloud match, report the two records separately unless a
real relationship joins them. Matching names, model identifiers, configuration,
or credentials are correlation evidence, not proof that they are the same
deployment.

### 4. Interpret empty results safely

Never answer "no AI agents" from `MATCH (:AIAgent)` alone.

Use one of these conclusions:

- **Found**: state which lanes produced assets and distinguish deployed/runtime
  evidence from catalog, source-code, credential, or SaaS-adoption evidence.
- **Not observed in connected data**: all applicable enabled lanes were checked
  and returned no rows, but coverage is not complete.
- **No matching assets found within verified coverage**: all relevant modules
  are enabled and current, schema was verified, and every applicable lane was
  queried.

### 5. Pivot only as needed

If the user asks for risk rather than inventory, follow the strongest evidence:

- runtime or public exposure: `investigate-container` or
  `investigate-public-exposure`;
- execution roles and access chains: `investigate-iam`;
- vulnerabilities or packages: `investigate-cve` or `investigate-package`;
- graph relationships not covered by the templates: `build-cypher-query`.

## Output

Lead with the conclusion and coverage boundary. Group evidence by code/runtime,
cloud-managed AI, provider/adoption, and security posture. Put sync failures or
staleness beside the affected lane. Tag returned entities with
`[[entity:<Label>:<id>|<name>]]`; summarize interactive tables.

## Verification

- Check every relevant lane and sync state with current schema and deduplicated
  counts. Distinguish catalog, deployment, absence, and missing coverage.

## Anti-patterns

- Never treat one label as the inventory, catalog as deployment, fan-out as a
  count, correlation as an edge, or missing provider coverage as absence.

## References

- Query templates: [`references/cypher-templates.md`](references/cypher-templates.md)
- Query construction and live-schema rules: `subimage-mcp:build-cypher-query`
- Runtime context: `subimage-mcp:investigate-container`
- Identity context: `subimage-mcp:investigate-iam`
