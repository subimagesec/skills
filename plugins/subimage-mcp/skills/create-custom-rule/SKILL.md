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

❌ The user wants to fix or change an existing custom rule. Use the sibling skill [`fix-custom-rule`](../fix-custom-rule/SKILL.md), which edits it with `subimageUpdateCustomRule`.
❌ The user wants to delete a custom rule. Use the REST API (`DELETE /findings/custom-rule/{id}`); there is no MCP tool for it.
❌ The user wants a one-off finding without a backing rule. Findings always come from a rule.
❌ The user wants to author an upstream Cartography rule shipped to every tenant. That is a different workflow outside this skill.

## Required inputs

Ask the user inline for anything missing before drafting Cypher:

- **Rule intent in plain English**: what does a finding mean? e.g. "RDS instances without storage encryption".
- **Target Cartography module(s)**: which provider does this query? (`AWS`, `GCP`, `Azure`, `GitHub`, `Okta`, `Kubernetes`, etc.). If the detection spans providers, split into one Fact per provider; one rule may contain several Facts.
- **Candidate rule id**: kebab-case, tenant-unique. Mirror the naming of existing rules.
- **Tags**: short, lowercased, e.g. `aws`, `data-protection`. The `custom` tag is reserved; if the user requests it, drop it silently.

## Non-negotiables for Cypher

These rules cannot be broken. The server rejects a rule that violates the first two. A rule that violates the last two fails every findings build, and saving it is refused wherever the test run is enabled.

1. **Every `RETURN` expression in `cypher_query` must alias to a name listed in `output_fields`, using explicit `AS`.** Example: `RETURN db.id AS id, db.name AS name, db.region AS region`. `RETURN *` and unaliased returns are rejected. `output_fields` must include one entry per alias, with `type` in `{"string", "number", "boolean"}`.
2. **`cypher_visual_query` returns whole nodes and relationships, not scalar properties.** Example: `MATCH (db:AWSRDSInstance) WHERE db.publicly_accessible = true RETURN db LIMIT 100`. This query powers graph visualization in the UI.
3. **Each output field's `type` matches what the query actually returns.** A property that holds `true` / `false` is `boolean`, even when it reads like a label. Declaring it `string` makes every run fail with `invalid_rule_output`. Either declare the real type or convert in Cypher (`toString(b.public)`). A list from `collect()` is stored as text, so it belongs in a `string` field.
4. **One row per finding.** Every output field is part of a finding's identity. Rows that are identical in every column are merged, so a query that reaches the same answer twice (for example through two relationship types) is fine. Rows with the same output values but a different asset or extra column fail the rule with `duplicate_signal_id`: add the column that tells them apart as an output field, or combine the rows with `DISTINCT`.

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

- `RETURN` aliases match `output_fields` names exactly, and each field's `type` matches the returned value (see non-negotiables #1 and #3).
- Include `LIMIT`, default `LIMIT 10000` to allow normal tenants while preventing pathological queries.
- Prefer ontology labels (`User`, `Device`, `Identity`, `ComputeInstance`, ...) when the detection is cross-provider; provider-native labels otherwise.

Constraints for `cypher_visual_query`:

- Return whole nodes and relationships, not scalars (see non-negotiable #2).
- `LIMIT 100` is the typical ceiling for the UI graph view.
- Include enough graph context for an analyst to understand the finding.

### Step 4: Verify against the live tenant graph

If `subimageTestCustomRule` is available, call it with the full draft rule (the same payload you will submit). It runs every Fact through the same detection the findings build uses, read-only, and returns per Fact: `findings_count`, a `sample` of findings, `duration_ms`, and on failure `error_code`, `error` and `error_hint`. Fix the draft and test again until `ok` is true. A Fact that only hit the interactive time limit (`query_timeout`) still saves (`can_save` is true), because the findings build has no time limit.

Whether or not that tool is available, also run `cypher_visual_query` via `subimageRunCypher`, and run `cypher_query` too when the test tool is not available. Confirm:

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
      "cypher_query": "MATCH (db:AWSRDSInstance) WHERE db.storage_encrypted = false RETURN db.id AS id, db.db_instance_identifier AS name, db.region AS region LIMIT 10000",
      "cypher_visual_query": "MATCH (db:AWSRDSInstance) WHERE db.storage_encrypted = false RETURN db LIMIT 100"
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
- `error="custom_rule_test_failed"`: the rule was test-run and would fail in the findings build, so it was not saved. `message` names each failing Fact with its `error_code` and a fix hint. Fix the draft (re-test with `subimageTestCustomRule` if available) and retry.

### Step 6: Report back to the user

Tell the user:

- the new rule id,
- that findings appear after the next scheduled findings build, not immediately,
- after the next build, they can read the rule's findings with the Cypher in Verification below, or open the rule in the SubImage UI.

## Output

A persisted custom rule registered with the tenant, produced by the single `subimageCreateCustomRule` call. The rule definition is stored immediately; findings against it are computed on the next scheduled findings build (see Workflow step 6 and Verification).

## Verification

After the next scheduled findings build completes, count the Findings the rule produced:

```cypher
MATCH (:Rule {id: '<new-id>'})-[:PRODUCED]->(f:Finding:Signal)
WHERE f.status = 'active'
RETURN count(f) AS findings
```

Expect a count consistent with what `subimageRunCypher` returned during Step 4. If the build has not run yet, the count is zero; this is not a failure.

## Anti-patterns

- `RETURN *` or unaliased `RETURN` expressions in `cypher_query`. The server rejects the rule.
- `cypher_visual_query` returning scalar properties instead of whole nodes. The UI graph view will be empty.
- Using the reserved `custom` tag. Drop it silently if the user asks for it.
- Trying to set rule maturity. It is fixed at `EXPERIMENTAL` server-side.
- Drafting a `cypher_count_query` on a Fact. Not supported for custom rules.
- Skipping Step 4 (live-graph validation) and submitting a rule that produces 0 findings.
- Declaring an output field `string` for a property that returns `true` / `false`. Use `boolean`, or `toString()` it in the query.
- Returning rows that share every output value but point at different assets. Add the distinguishing column as an output field.
- Setting `allow_community_contribution: true` without an explicit opt-in from the user. Default to `false`.
- Calling `subimageCreateCustomRule` more than once with the same id after a `validation_error`. Fix the payload first, then retry.

## References

- SubImage MCP setup: https://app.subimage.io/docs/agents/connect_via_mcp
- Sibling skill for Cypher discovery and authoring: [`build-cypher-query`](../build-cypher-query/SKILL.md)
- Sibling skill for repairing a rule that fails in the findings build: [`fix-custom-rule`](../fix-custom-rule/SKILL.md)
