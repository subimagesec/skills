# Cypher templates: AI asset exploration

These are starting points. Apply `subimage-mcp:build-cypher-query` validation and
execution rules before use. Module status qualifies coverage but does not gate
queries; existing graph data can outlive module configuration.

## Aggregate lane census

Run this first for broad questions, then fetch detail only from relevant lanes.

```cypher
MATCH (n:AIAgent) WITH count(n) AS asset_count RETURN 'code_agents' AS lane, asset_count
UNION ALL MATCH (n:AWSBedrockAgent) WITH count(n) AS asset_count RETURN 'bedrock_agents' AS lane, asset_count
UNION ALL MATCH (n:AWSBedrockKnowledgeBase) WITH count(n) AS asset_count RETURN 'bedrock_knowledge_bases' AS lane, asset_count
UNION ALL MATCH (n:AWSBedrockGuardrail) WITH count(n) AS asset_count RETURN 'bedrock_guardrails' AS lane, asset_count
UNION ALL MATCH (n:AIModel) WITH count(n) AS asset_count RETURN 'models' AS lane, asset_count
UNION ALL MATCH (n:AWSSageMakerEndpoint) WITH count(n) AS asset_count RETURN 'sagemaker_endpoints' AS lane, asset_count
UNION ALL MATCH (n:GCPVertexAIEndpoint) WITH count(n) AS asset_count RETURN 'vertex_endpoints' AS lane, asset_count
UNION ALL MATCH (n:GCPVertexAIWorkbenchInstance) WITH count(n) AS asset_count RETURN 'vertex_workbenches' AS lane, asset_count
UNION ALL MATCH (n:AIBOMSource) WITH count(n) AS asset_count RETURN 'aibom_sources' AS lane, asset_count
UNION ALL MATCH (n:OpenAIOrganization) WITH count(n) AS asset_count RETURN 'openai_organizations' AS lane, asset_count
UNION ALL MATCH (n:AnthropicOrganization) WITH count(n) AS asset_count RETURN 'anthropic_organizations' AS lane, asset_count
UNION ALL MATCH (n:ThirdPartyApp) WITH count(n) AS asset_count RETURN 'third_party_apps_to_classify' AS lane, asset_count
UNION ALL MATCH (n:AzureSubscription) WITH count(n) AS asset_count RETURN 'azure_subscriptions_coverage' AS lane, asset_count
```

The `ThirdPartyApp` and Azure rows are coverage context, not AI-asset counts.
Classify apps with the maintained rule below. Azure has no shared AI ontology
label today, so discover provider-native Azure AI labels from current schema
before adding asset counts; do not treat subscription count as AI usage.

## Code-derived AI agents and runtime

This lane finds scanner-derived agents. It does not include provider-native
agents such as `AWSBedrockAgent`.

```cypher
MATCH (agent:AIAgent)
OPTIONAL MATCH (source:AIBOMSource)-[hc:HAS_COMPONENT]->(agent)
OPTIONAL MATCH (source)-[si:SCANNED_IMAGE]->(img:Image)
OPTIONAL MATCH (source)-[sr:SCANNED_REPOSITORY]->(repo:CodeRepository)
OPTIONAL MATCH (source)-[ro:RUNS_ON]->(runtime:Container)
OPTIONAL MATCH (runtime)-[sa:SCANNED_AS]->(runtime_snapshot:FilesystemSnapshot)
OPTIONAL MATCH (repo)<-[so:SNAPSHOT_OF]-(repo_snapshot:FilesystemSnapshot)
OPTIONAL MATCH (agent)-[um:USES_MODEL]->(model:AIModel)
OPTIONAL MATCH (agent)-[ut:USES_TOOL]->(tool:AITool)
WITH coalesce(agent.logical_id, agent.id) AS logical_id,
     collect(DISTINCT agent) AS agents,
     collect(DISTINCT agent.framework) AS frameworks,
     collect(DISTINCT agent.detection_source) AS detection_sources,
     collect(DISTINCT agent.component_primary_evidence) AS evidence,
     collect(DISTINCT source.source_name) AS sources,
     collect(DISTINCT img._ont_digest) AS image_digests,
     collect(DISTINCT repo._ont_name) AS repositories,
     collect(DISTINCT runtime._ont_name) AS runtimes,
     collect(DISTINCT runtime_snapshot.id) + collect(DISTINCT repo_snapshot.id) AS filesystem_snapshots,
     collect(DISTINCT coalesce(model._ont_name, model.model_name, model.name)) AS models,
     collect(DISTINCT tool.name) AS tools
WITH logical_id, head(agents) AS agent, frameworks, detection_sources, evidence,
     sources, image_digests, repositories, runtimes, filesystem_snapshots,
     models, tools
RETURN agent.id AS id,
       logical_id,
       coalesce(agent.name, agent.model_name, agent.id) AS name,
       frameworks, detection_sources, evidence, sources, image_digests,
       repositories, runtimes, filesystem_snapshots, models, tools
ORDER BY name
LIMIT 100
```

For a broad component breakdown:

```cypher
MATCH (source:AIBOMSource)-[hc:HAS_COMPONENT]->(component:AIBOMComponent)
OPTIONAL MATCH (source)-[ro:RUNS_ON]->(runtime:Container)
RETURN component.category AS category,
       count(DISTINCT coalesce(component.logical_id, component.id)) AS component_count,
       count(DISTINCT source) AS source_count,
       count(DISTINCT runtime) AS runtime_count,
       collect(DISTINCT component.framework)[0..10] AS frameworks
ORDER BY component_count DESC
LIMIT 50
```

## Cloud-native agents

AWS Bedrock agents are currently separate from the `AIAgent` label.

```cypher
MATCH (account:AWSAccount)-[resource:RESOURCE]->(agent:AWSBedrockAgent)
OPTIONAL MATCH (agent)-[um:USES_MODEL]->(model:AIModel|AWSBedrockProvisionedModelThroughput)
OPTIONAL MATCH (agent)-[hr:HAS_ROLE]->(role:AWSRole)
OPTIONAL MATCH (agent)-[invokes:INVOKES]->(fn:AWSLambda)
OPTIONAL MATCH (agent)-[ukb:USES_KNOWLEDGE_BASE]->(kb:AWSBedrockKnowledgeBase)
OPTIONAL MATCH (guardrail:AWSBedrockGuardrail)-[applied:APPLIED_TO]->(agent)
RETURN agent.id AS id,
       agent.agent_name AS name,
       agent.agent_status AS status,
       agent.region AS region,
       account.id AS account_id,
       collect(DISTINCT coalesce(model._ont_name, model.model_name, model.id)) AS models,
       collect(DISTINCT coalesce(role.name, role.arn, role.id)) AS roles,
       collect(DISTINCT coalesce(fn.name, fn.arn, fn.id)) AS functions,
       collect(DISTINCT kb.name) AS knowledge_bases,
       collect(DISTINCT guardrail.name) AS guardrails
ORDER BY account_id, region, name
LIMIT 100
```

Discover and query additional provider-native agent labels independently. Do not
rewrite this as `MATCH (:AIAgent)` and assume it covers them.

## Cross-provider models

`AIModel` includes code-derived AIBOM models and mapped Bedrock, SageMaker, and
Vertex AI models. Separate catalog-only foundation models from assets that have
usage or deployment edges.

```cypher
MATCH (model:AIModel)
OPTIONAL MATCH (tenant:Tenant)-[resource:RESOURCE]->(model)
OPTIONAL MATCH ()-[usage:USES_MODEL|USES_EMBEDDING_MODEL|USES|INSTANCE_OF|PROVIDES_CAPACITY_FOR]->(model)
WITH model,
     collect(DISTINCT tenant.id) AS tenants,
     collect(DISTINCT usage) AS usage_edges
UNWIND CASE WHEN size(usage_edges) = 0 THEN [null] ELSE usage_edges END AS usage
UNWIND CASE WHEN usage IS NULL THEN [null] ELSE labels(startNode(usage)) END AS consumer_label
WITH model, tenants, size(usage_edges) AS usage_edge_count,
     collect(DISTINCT consumer_label) AS consumer_labels
RETURN model.id AS id,
       coalesce(model._ont_name, model.model_name, model.display_name, model.name, model.id) AS name,
       model._ont_provider AS provider,
       model._ont_type AS type,
       model._ont_status AS status,
       labels(model) AS labels,
       tenants,
       usage_edge_count,
       consumer_labels
ORDER BY usage_edge_count DESC, provider, name
LIMIT 100
```

Do not describe a foundation model with zero usage edges as deployed. It may be
only a provider catalog entry.

## GCP Vertex AI deployment path

```cypher
MATCH (project:GCPProject)-[resource:RESOURCE]->(endpoint:GCPVertexAIEndpoint)
OPTIONAL MATCH (endpoint)-[serves:SERVES]->(deployment:GCPVertexAIDeployedModel)
OPTIONAL MATCH (deployment)-[instance:INSTANCE_OF]->(model:GCPVertexAIModel)
RETURN project.id AS project_id,
       endpoint.id AS endpoint_id,
       endpoint.display_name AS endpoint_name,
       collect(DISTINCT deployment.id) AS deployment_ids,
       collect(DISTINCT coalesce(model.display_name, model._ont_name, model.id)) AS models
ORDER BY project_id, endpoint_name
LIMIT 100
```

Use schema discovery for datasets, training pipelines, feature groups, and
Workbench instances. Include Workbench in the default inventory; expand the
other labels when the question includes training data or feature stores.

```cypher
MATCH (project:GCPProject)-[resource:RESOURCE]->(workbench:GCPVertexAIWorkbenchInstance)
RETURN workbench.id AS id,
       coalesce(workbench.display_name, workbench.name, workbench.id) AS name,
       workbench.state AS state,
       workbench.service_account AS service_account,
       project.id AS project_id
ORDER BY project_id, name
LIMIT 100
```

## AWS SageMaker deployment path

```cypher
MATCH (account:AWSAccount)-[resource:RESOURCE]->(endpoint:AWSSageMakerEndpoint)
OPTIONAL MATCH (endpoint)-[uses_config:USES]->(config:AWSSageMakerEndpointConfig)
OPTIONAL MATCH (config)-[uses_model:USES]->(model:AWSSageMakerModel)
OPTIONAL MATCH (model)-[her:HAS_EXECUTION_ROLE]->(role:AWSRole)
RETURN endpoint.id AS id,
       endpoint.endpoint_name AS name,
       endpoint.endpoint_status AS status,
       endpoint.region AS region,
       account.id AS account_id,
       collect(DISTINCT model.model_name) AS models,
       collect(DISTINCT coalesce(role.name, role.arn, role.id)) AS roles
ORDER BY account_id, region, name
LIMIT 100
```

Use schema discovery for SageMaker domains, user profiles, notebook instances,
training jobs, transform jobs, model packages, storage, and execution roles when
the question extends beyond deployed inference endpoints.

## AI provider control plane

OpenAI inventory example:

```cypher
MATCH (org:OpenAIOrganization)
OPTIONAL MATCH (org)-[project_resource:RESOURCE]->(project:OpenAIProject)
OPTIONAL MATCH (project)-[service_resource:RESOURCE]->(service_account:OpenAIServiceAccount)
OPTIONAL MATCH (project)-[key_resource:RESOURCE]->(key:OpenAIApiKey)
OPTIONAL MATCH (org)-[admin_key_resource:RESOURCE]->(admin_key:OpenAIAdminApiKey)
OPTIONAL MATCH (org)-[user_resource:RESOURCE]->(user:OpenAIUser)
RETURN org.id AS organization_id,
       count(DISTINCT project) AS project_count,
       count(DISTINCT user) AS user_count,
       count(DISTINCT service_account) AS service_account_count,
       count(DISTINCT key) AS api_key_count,
       count(DISTINCT admin_key) AS admin_api_key_count,
       collect(DISTINCT project.name)[0..20] AS projects
ORDER BY organization_id
LIMIT 100
```

Use the same schema-first approach for other enabled AI provider modules. API
keys and provider accounts prove configured access, not workload execution.

Anthropic inventory example:

```cypher
MATCH (org:AnthropicOrganization)
OPTIONAL MATCH (org)-[workspace_resource:RESOURCE]->(workspace:AnthropicWorkspace)
OPTIONAL MATCH (org)-[user_resource:RESOURCE]->(user:AnthropicUser)
OPTIONAL MATCH (org)-[key_resource:RESOURCE]->(key:AnthropicApiKey)
RETURN org.id AS organization_id,
       count(DISTINCT workspace) AS workspace_count,
       count(DISTINCT user) AS user_count,
       count(DISTINCT key) AS api_key_count,
       collect(DISTINCT workspace.name)[0..20] AS workspaces
ORDER BY organization_id
LIMIT 100
```

## Employee-authorized AI apps

Reuse the maintained AI app inventory rule instead of copying its evolving name
matcher. `subimageListRules` returns its current finding count; fetch assets from
the graph only when details are needed. If it does not return
`ai_third_party_app_inventory`, report this lane as unavailable and do not infer
that there are no AI apps.

```cypher
MATCH (rule:Rule {id: 'ai_third_party_app_inventory'})-[produced:PRODUCED]->(finding:Finding:Signal)
WHERE finding.status IN ['active', 'accepted']
WITH finding
ORDER BY finding.id
LIMIT 100
OPTIONAL MATCH (finding)-[affects:AFFECTS {role: 'primary'}]->(app:ThirdPartyApp)
OPTIONAL MATCH (identity:UserAccount)-[authorized:AUTHORIZED]->(app)
RETURN app.id AS id,
       coalesce(app._ont_name, app.display_name, app.display_text, app.name, finding.display_name) AS name,
       app._ont_source AS source,
       count(DISTINCT identity) AS authorized_identity_count,
       finding.status AS finding_status,
       finding.fields_json AS fields_json
ORDER BY authorized_identity_count DESC, name
LIMIT 100
```

The rule uses allowlist and heuristic matching. Treat every result as discovered
AI-app evidence requiring confirmation, not proof of generative AI use. When
`id` is null, read `asset_node_id` from the returned `fields_json` JSON string.

## AIBOM coverage gaps

Run this before treating an empty code-derived lane as absence.

```cypher
MATCH (source:AIBOMSource)
WITH source,
     CASE
       WHEN toLower(source.source_kind) IN ['container', 'image']
            AND coalesce(source.image_matched, false) = false THEN 'unmatched_image'
       WHEN toLower(coalesce(source.source_status, 'unknown')) <> 'completed' THEN 'incomplete_source'
       WHEN source.analysis_status IS NOT NULL AND toLower(source.analysis_status) <> 'completed' THEN 'analysis_not_completed'
       ELSE NULL
     END AS gap_reason
WHERE gap_reason IS NOT NULL
RETURN source.id AS id,
       source.source_name AS source,
       source.image_uri AS image_uri,
       source.source_kind AS source_kind,
       source.total_components AS component_count,
       gap_reason
ORDER BY gap_reason, source
LIMIT 100
```

Also compare scanned sources with the runtime or repository scope the user asked
about. A clean scan of some images is not proof that every deployed image or
repository was scanned.

## AI-related findings

Call `subimageListRules`, retain rules whose tags include `ai`, and report their
`findings_count`. Fetch current finding rows only when detail is useful:

```cypher
MATCH (rule:Rule)-[produced:PRODUCED]->(finding:Finding:Signal)
WHERE rule.id IN [<AI_RULE_IDS>] AND finding.status IN ['active', 'accepted']
RETURN rule.id AS rule_id,
       finding.id AS id,
       finding.display_name AS name,
       finding.status AS status
ORDER BY rule_id, name
LIMIT 100
```

Replace `<AI_RULE_IDS>` with a quoted Cypher list built from the trusted rule ids
returned by `subimageListRules`.

Keep findings distinct from inventory: a missing finding means the rule did not
report a violation within its coverage, not that the underlying asset is absent.
