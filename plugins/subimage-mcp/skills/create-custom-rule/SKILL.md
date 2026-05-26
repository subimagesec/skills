---
name: create-custom-rule
description: Draft, validate, and persist a tenant-local SubImage custom Cypher rule via the `subimageCreateCustomRule` MCP tool. Use when the user asks to "create a rule", "add a custom finding", "write a Cypher rule for X", or wants to detect a misconfiguration not covered by the built-in rules.
---

# Create a SubImage custom rule

Help an operator author and persist a new SubImage custom security rule end-to-end from chat. The skill ends when the rule is saved and the user knows when to expect findings.

The deliverable is one successful `subimageCreateCustomRule` call. Findings are produced on the next scheduled findings build, not inline.

## What this does

A SubImage custom rule is a tenant-local Cartography rule. It contains:

- one or more **Facts**, each with a Cypher detection query (`cypher_query`) plus a graph-visualization query (`cypher_visual_query`),
- an `output_fields` list describing every column the detection query returns,
- optional `references` (CIS controls, vendor advisories, etc.),
- tags for categorization.

## When to use

✅ The user wants to detect a misconfiguration not already covered by SubImage's built-in rules.
✅ The user says "create a rule", "add a custom finding", or "write a Cypher rule for X".
✅ The detection logic can be expressed as a read-only Cypher query over the tenant graph.

❌ The user wants to edit or delete an existing custom rule. Use the REST API (`PUT` / `DELETE /findings/custom-rule/{id}`); no MCP equivalent today.
❌ The user wants a one-off finding without a backing rule. Findings always come from a rule.
❌ The user wants to author an upstream Cartography rule shipped to every tenant. That is a different workflow outside this skill.

## Required inputs

Ask the user inline for anything missing before drafting Cypher:

- **Rule intent in plain English**: what does a finding mean? e.g. "RDS instances without storage encryption".
- **Target Cartography module(s)**: which provider does this query? (`AWS`, `GCP`, `Azure`, `GitHub`, `Okta`, `Kubernetes`, etc.). If the detection spans providers, split into one Fact per provider; one rule may contain several Facts.
- **Candidate rule id**: kebab-case, tenant-unique. Mirror the naming of existing rules.
- **Tags**: short, lowercased, e.g. `aws`, `data-protection`. The `custom` tag is reserved; if the user requests it, drop it silently.

## Non-negotiables for Cypher

Two rules cannot be broken. The server rejects rule submissions that violate them.

1. **Every `RETURN` expression in `cypher_query` must alias to a name listed in `output_fields`, using explicit `AS`.** Example: `RETURN db.id AS id, db.name AS name, db.region AS region`. `RETURN *` and unaliased returns are rejected. `output_fields` must include one entry per alias, with `type` in `{"string", "number", "boolean"}`.
2. **`cypher_visual_query` returns whole nodes and relationships, not scalar properties.** Example: `MATCH (db:RDSInstance) WHERE db.publicly_accessible = true RETURN db LIMIT 100`. This query powers graph visualization in the UI.

Both queries must contain a `LIMIT` clause and use `MATCH` / `RETURN` only. Write operations (`CREATE`, `MERGE`, `DELETE`, `SET`, `REMOVE`) are rejected.

## Workflow

Run the steps in order. Do not skip step 1.

### Step 1: Confirm intent and check for collisions

Call `subimageListRules` to:

- mirror naming and tag conventions used by existing rules,
- confirm the candidate id is not already taken. A collision returns `error="conflict"` at submit time.

If the detection is unclear, ask the user one focused clarifying question before drafting Cypher. A bad detection wastes a full findings-build cycle.

### Step 2: Pick the Cartography module

Pick the module(s) the rule queries: `AWS`, `GCP`, `Azure`, `GitHub`, `Okta`, `Kubernetes`, etc. The module drives which data the rule depends on at build time. For cross-provider detections, split into one Fact per provider.

### Step 3: Draft the queries

For each Fact, draft `cypher_query` and `cypher_visual_query` against the live tenant schema. If you need help discovering labels and properties, use the sibling skill [`build-cypher-query`](../build-cypher-query/SKILL.md) (it covers `subimageListModuleSchemaNodes`, `subimageGetNodesSchema`, and the agent-delegated builder).

Constraints for `cypher_query`:

- `RETURN` aliases match `output_fields` names exactly (see non-negotiable #1).
- Include `LIMIT`, default `LIMIT 10000` to allow normal tenants while preventing pathological queries.
- Prefer ontology labels (`User`, `Device`, `Identity`, `ComputeInstance`, ...) when the detection is cross-provider; provider-native labels otherwise.

Constraints for `cypher_visual_query`:

- Return whole nodes and relationships, not scalars (see non-negotiable #2).
- `LIMIT 100` is the typical ceiling for the UI graph view.
- Include enough graph context for an analyst to understand the finding.

### Step 4: Verify against the live tenant graph

Run both `cypher_query` and `cypher_visual_query` via `subimageRunCypher` before submitting. Confirm:

- the result count is plausible (not 0, not millions),
- the returned rows make sense for the intended detection,
- ontology and property assumptions hold for this tenant.

If `cypher_query` returns 0 rows when the user expects findings, the rule will silently produce no findings after build. Iterate before submitting.

### Step 5: Submit

Call `subimageCreateCustomRule` exactly once with a `CustomRuleRequest` payload. Example:

```json
{
  "id": "tenant-rds-without-encryption",
  "name": "RDS instances without storage encryption",
  "description": "Flags RDS instances missing storage encryption.",
  "tags": ["aws", "data-protection"],
  "facts": [
    {
      "id": "aws-rds-no-encryption",
      "name": "AWS RDS without encryption",
      "description": "RDS instances where storage_encrypted is false.",
      "module": "AWS",
      "cypher_query": "MATCH (db:RDSInstance) WHERE db.storage_encrypted = false RETURN db.id AS id, db.db_instance_identifier AS name, db.region AS region LIMIT 10000",
      "cypher_visual_query": "MATCH (db:RDSInstance) WHERE db.storage_encrypted = false RETURN db LIMIT 100"
    }
  ],
  "output_fields": [
    {"name": "id", "type": "string"},
    {"name": "name", "type": "string"},
    {"name": "region", "type": "string"}
  ],
  "references": [],
  "allow_community_contribution": false
}
```

Errors returned as `MCPErrorResponse`:

- `error="conflict"`: the id collides with a built-in rule or another custom rule. Pick a new id and retry.
- `error="validation_error"`: Cypher rejected. Read `message`: it describes the issue (forbidden write op, missing `LIMIT` or `RETURN`, missing `AS` alias, live-graph syntax error). Fix and retry.

### Step 6: Report back to the user

Tell the user:

- the new rule id,
- that findings appear after the next scheduled findings build, not immediately,
- after the next build, they can call `subimageGetRuleFindings(rule_id=<new-id>)` or open the rule in the SubImage UI.

## Output

A persisted custom rule in the tenant, plus a primed Cartography rule in the findings cache. Both are produced by the single `subimageCreateCustomRule` call.

## Verification

After the next scheduled findings build completes, call `subimageGetRuleFindings(rule_id=<new-id>)`. Expect a row count consistent with what `subimageRunCypher` returned during Step 4. If the build has not run yet, the call returns an empty result; this is not a failure.

## Anti-patterns

- `RETURN *` or unaliased `RETURN` expressions in `cypher_query`. The server rejects the rule.
- `cypher_visual_query` returning scalar properties instead of whole nodes. The UI graph view will be empty.
- Using the reserved `custom` tag. Drop it silently if the user asks for it.
- Trying to set rule maturity. It is fixed at `EXPERIMENTAL` server-side.
- Drafting a `cypher_count_query` on a Fact. Not supported for custom rules.
- Skipping Step 4 (live-graph validation) and submitting a rule that produces 0 findings.
- Setting `allow_community_contribution: true` without an explicit opt-in from the user. Default to `false`.
- Calling `subimageCreateCustomRule` more than once with the same id after a `validation_error`. Fix the payload first, then retry.

## References

- SubImage MCP setup: https://app.subimage.io/docs/agents/connect_via_mcp
- Sibling skill for Cypher discovery and authoring: [`build-cypher-query`](../build-cypher-query/SKILL.md)
