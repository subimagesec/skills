---
name: create-custom-rule
description: Design, validate, and save a tenant-local SubImage custom Cypher rule, or fix and update an existing one, with `subimageCreateCustomRule` and `subimageUpdateCustomRule`. Use when the user asks to "create a rule", "write a Cypher rule for X", "add a custom finding", "edit my custom rule", "fix my failing rule", "track this as a rule", or wants an investigation's result watched from now on.
---

# Create or update a SubImage custom rule

Turn what the user wants to act on into a rule whose findings land where that action happens. The skill ends when the rule is saved, or the user declines it, and the user knows what the next findings build will produce.

## What this does

A custom rule is a detection the tenant writes in Cypher. After every findings build, each row its queries return becomes a finding on the Rules page. Findings then go through the same acceptance, history, notifications, and issue triage as a built-in rule's.

A rule is not a form to fill in. Every field is a lever on how rows turn into findings, and the right setting follows from what someone will do with a finding once it exists. Read **Design the rule** and **How rows become findings** before drafting. Most bad rules come from skipping them.

Uses `subimageListRules`, `subimageRunCypher`, `subimageCreateCustomRule`, `subimageUpdateCustomRule`, and the sibling skill [`build-cypher-query`](../build-cypher-query/SKILL.md) for schema discovery.

## When to use

✅ The user wants to track a condition over time that no built-in or existing custom rule covers.
✅ An investigation turned up a problem that can come back, and the user accepted an offer to keep watching for it.
✅ The user wants to change a custom rule, or `subimageListRules(exec_status="ERROR")` shows one failing.
✅ The user says "create a rule", "write a Cypher rule for X", "flag every X that Y", or "fix my rule".

❌ A one-off question about the graph. Use `build-cypher-query` and `subimageRunCypher`; a rule is for something to track.
❌ Changing a built-in rule. Built-in rules cannot be updated. Write a custom rule, or disable the built-in from its rule page.
❌ Deleting a custom rule. There is no MCP tool for it; the user deletes it from the rule's page.

## Required inputs

Only the intent: what the user will do with a finding. Ask about it only when the request could serve more than one action (see **Start from the action**). Derive the id, name, description, tags, and module yourself and propose them. In chat, the approval card shows them before anything is written.

## Design the rule

### Start from the action

The intent is the whole design. What someone will do with a finding decides what the finding is anchored on and how it splits. Two rules over the same graph show it:

- **"Containers with critical CVEs."** The finding is about the container. It makes questions about that container easy to answer: is it high risk, is its access to other resources too broad, which paths lead from it. Anchor on the container. Its CVEs are evidence in columns outside the identity, so any number of them is one finding, and that finding becomes one issue about the container.
- **"Critical CVEs on a container."** The finding is about each CVE where it appears. It makes it easy to split the work into a ticket per CVE and to track whether each one is fixed. The CVE goes in the identity, so each CVE is its own finding and its own issue, and each closes when that CVE is fixed.

Both read the same nodes and can match the same rows. They differ only in intent, and the intent determines the anchor, the identity, and the issues that come downstream. Name the action before choosing a single field.

### Anchor on what the action is about

The affected asset is the node a person opens from the finding, the node issue triage scopes and assigns, and the starting point for any investigation of reach. Pick the node the intended action works on, not merely the first node the query matches.

### Identity is the grain the action needs, written down

`identity_fields` are the columns that make a row the same finding as last build. Include the columns that are part of the problem, and the stable properties that identify the underlying object without changing because the problem is present.

- **Too broad:** a column that churns with the object, such as a count, a timestamp, or the list of current causes, closes and reopens the finding every build. One issue becomes thousands of findings, and acceptance is lost each time.
- **Too narrow:** distinct problems merge into one finding, and the rule loses the granularity it was meant to track.

When a node's `id` is in the identity, its other properties add nothing: the id already pins the node.

### Several facts answer one question

A rule has one or more facts, each with its own query. Write several only when one question needs different queries to cover differently shaped graphs, such as one per provider. A different question is a different rule.

## How rows become findings

This is what a findings build does with each fact. Every field choice above lands somewhere in it.

1. **The query is wrapped.** It runs as the body of `CALL { ... }`, so a trailing `;` is dropped and `LIMIT` applies inside, before anything else. The build then looks up the node with label `asset_label` whose `id` equals the `asset_id_field` column.
2. **One bad row fails the whole rule.** The build stops rather than skipping the row, because a skipped row would read as a fixed finding. The rule goes to `ERROR` and keeps its existing findings. A row fails when:
   - no `asset_label` node has that id, including a null id from an `OPTIONAL MATCH`;
   - two rows share the identity but differ in another column;
   - a value does not fit its column.
   
   Rows that are identical in every column collapse into one finding.
3. **Every column becomes text.** Each `RETURN` alias is a finding field. Booleans become `true`/`false`, times become ISO text, maps become JSON, numbers become text, and lists are joined with `", "` in the order the query returned them. Nulls and empty strings are dropped. A rule's columns are the union of all its facts' aliases, so a column one fact lacks is blank on that fact's findings.
4. **Identity is a hash.** A finding's id hashes the rule id, the fact id, and the identity column values. Changing any of them makes a different finding: a new rule or fact id, a different set of identity columns, or a changed value in one of them. With `identity_fields` omitted, the identity is every returned column, so adding or removing a column replaces every finding.
5. **Each build is matched against the last.** A new id opens a finding. A missing id closes it into history. A matching id keeps its first-seen date and its acceptance, and records an update when a non-identity column or the affected asset changed.
6. **The affected asset** is `asset_label` plus `asset_id_field`: a label the query binds and a column returned as exactly `<var>.id` off that variable. `u.id AS id` works; `u.arn AS id` does not. Leave it out of the identity to let a finding survive its resource being rebuilt.
7. **The display field** is the column a finding is shown as. Omitted or empty, it is the asset id.

## Query craft

- Treat `LIMIT` as a safety cap well above the real count. Past it, the build keeps an arbitrary subset of rows, and findings rotate from one build to the next.
- Sort anything collected into a column, for example `apoc.coll.sort(collect(DISTINCT v.id))`. An unsorted list can come back in a different order and record an update on every build.
- Filter out null ids when the asset comes from an `OPTIONAL MATCH`: `WHERE x.id IS NOT NULL`.
- Use `DISTINCT`, or aggregate with `collect()`, when several graph paths reach the same answer.
- Filter early on labels and properties, and bound variable-length paths. Otherwise the rule fails on time or memory.
- Prefer ontology labels (`Device`, `UserAccount`, `ComputeInstance`, `Container`) for cross-provider questions, with `module: "Cross-Cloud"`. Use provider labels when the question is about one provider.
- `module` labels the fact and does not gate it: the rule runs whether or not that module is synced. It must be one of `AIBOM`, `Airbyte`, `Anthropic`, `AWS`, `Azure`, `BigFix`, `Cloudflare`, `CrowdStrike`, `Databricks`, `DigitalOcean`, `Duo`, `microsoft`, `GCP`, `GitHub`, `GitLab`, `googleworkspace`, `Jamf`, `JumpCloud`, `Kandji`, `Keycloak`, `Kubernetes`, `LastPass`, `OCI`, `Okta`, `OpenAI`, `PagerDuty`, `Railway`, `Scaleway`, `Supabase`, `Semgrep`, `SentinelOne`, `snipeit`, `SpaceLift`, `TailScale`, `Trivy`, `SubImage`, `Zoom`, `Cross-Cloud`. The casing is exact.
- `source` and `extra` are reserved and cannot be aliases.

## What findings feed

- Issue triage groups a rule's findings into issues. It reads the rule's name and description, every finding field, and the columns `account_id`, `project_id`, `provider`, and `resource_type` when present. Write the name and description for that reader as much as for people, and return those columns when the graph has them.
- Custom rules do not feed attack paths or compliance frameworks.
- The `custom` tag is reserved and stripped on save. Leave it out.

## Workflow

Run the steps in order. Every check happens before the save, inside this turn: a findings build runs long after the turn ends, and nothing brings you back to it.

### Starting from an investigation

When the rule comes out of an investigation, most of the design is already in the conversation. The user's concern is the intent, and the queries you ran are the first draft. Reshape them rather than starting over: an investigation query often returns counts, a top-N, or one row per path. A rule needs one row per finding at the grain the action needs, anchored on a node, under a generous `LIMIT`. Then continue from Step 1 with that action.

### Step 1: State the design

Before drafting, tell the user the action, then the anchor and grain it implies. For example: "to examine high-risk containers: one finding per container, anchored on the container" or "to ticket each CVE: one finding per CVE on each container". When the request could serve either action, ask which action they want. Do not ask which fields to fill in; they follow from the answer.

### Step 2: Check the id, or read the rule

- **Create:** call `subimageListRules` and pick a kebab-case id that is unused across built-in and custom rules. Mirror the naming and tags of nearby rules.
- **Update or fix:** call `subimageListRules(view="custom_definitions")` for the current definition. For a failing rule, `subimageListRules(exec_status="ERROR")` gives its `error_code`, `error`, and `error_hint`; start from those and the table in **Refusals**.

### Step 3: Draft and probe with `subimageRunCypher`

Use [`build-cypher-query`](../build-cypher-query/SKILL.md) to discover labels and properties. Then run probes against the live graph. `subimageRunCypher` returns at most 100 rows, but its `total_count` counts every matching row and ignores `LIMIT`.

- **Rows look right:** run the draft and read the rows.
- **Count fits the cap:** if `total_count` is at or above your `LIMIT`, raise it.
- **Grain holds:** compare rows with distinct identities. Wrap the draft without its `LIMIT`, for example `CALL { <draft> } RETURN count(*) AS rows, count(DISTINCT [<identity columns>]) AS findings`. A difference means two rows share an identity, which fails the rule unless they are identical.
- **Anchor resolves:** every row has a non-null asset id.
- **Zero rows:** run the query with its `WHERE` condition removed or inverted. If that returns the assets you expect, 0 is the correct answer for a condition that currently holds, as with "a bucket that must stay private". Say so rather than loosening the rule.

### Step 4: Assemble the body

Rule: `id`, `name`, `description`, `tags`, `references` (each `{title, url}`), `allow_community_contribution` (default `false`; set `true` only on an explicit opt-in), `facts`.

Fact: `id`, `name`, `description`, `module`, `cypher_query`, `cypher_visual_query`, `asset_label`, `asset_id_field`, optional `identity_fields`, optional `display_field`.

- `cypher_query` aliases every returned column with `AS`, has a `LIMIT`, and is read-only. `CREATE`, `MERGE`, `DELETE`, `SET`, `REMOVE`, and `LOAD CSV` are rejected.
- `cypher_visual_query` is the same query with its last `RETURN` replaced by `RETURN *`, keeping the `LIMIT`. It draws the graph view and does not decide which rows become findings.
- `identity_fields` and `display_field` name returned columns.
- Do not send `output_fields`, `maturity`, or `cypher_count_query`.

**Update:** send the whole rule back. `id` cannot change. Keep every fact `id` as it is, because a new fact id replaces that fact's findings. An omitted optional field resets to its default: `tags`, `references`, `identity_fields`, and `display_field` included.

Before an update changes a fact's identity, or the columns of a fact with no `identity_fields`, tell the user that fact's findings will close and reopen, and that acceptance and issue triage do not carry over. Changing other columns or the display field updates findings in place.

### Step 5: Save

Call `subimageCreateCustomRule` or `subimageUpdateCustomRule` with `{"rule": <body>}`. The tool runs the draft the way the findings build will, against the graph as it is now, and refuses it when a query would fail. On a refusal, fix the body per **Refusals** and call again.

In SubImage chat, a draft that passes waits on an approval card. Tell the user it is ready for their approval, and stop. Other MCP clients write immediately.

### Step 6: Hand off

Report the rule id, what one finding means in a sentence ("one finding per container with a critical CVE"), the row count from Step 3, and that findings appear on the next findings build. Point to the rule's page in SubImage for the user to check later.

After fixing a failing rule, the successful save is the evidence: it ran the same detection the build runs. The rule shows `ERROR` until the next build, so say that rather than checking it again.

## Refusals

A refused save returns `MCPErrorResponse`:

- `custom_rule_test_failed`: the message reads `fact '<id>': <code> (<error>). <hint>` for each failing fact.
- `custom_rule_conflict`: the id is taken by a built-in or custom rule. Pick another.
- `custom_rule_not_found`: the update names an id that is not a custom rule.
- `cypher_validation_unavailable`: the check could not run. Retry shortly.

Codes inside `custom_rule_test_failed`:

| Code | Fix |
|---|---|
| `invalid_fact` | A save-time check failed: a missing `AS` alias or `LIMIT`, a write clause, an anchor that is not `<var>.id` off a node bound to `asset_label`, or identity or display fields that are not returned columns. The error names which. |
| `cypher_error` | Neo4j rejected the query. Run it with `subimageRunCypher` to see the full error. |
| `affected_asset_not_found` | A row's asset id matches no `asset_label` node. Return `<var>.id` off the labeled variable and filter out nulls. |
| `duplicate_signal_id` | Two rows share an identity but differ elsewhere. Add the differing column to `identity_fields`, or collapse the rows with `DISTINCT` or `collect()`. Decide by the grain from Step 1. |
| `invalid_rule_output` | A column first saved as a number or boolean received another type. Return that type, or return the value under a new alias, which is stored as text. |
| `memory_limit_exceeded` | Filter before aggregating and bound variable-length paths. |
| `query_timeout` | Only the interactive time limit was hit. It does not block the save, since the build has no limit, but narrow the query if you can. |

Any other code is on SubImage's side. Tell the user to contact support.

## Example

"Any S3 bucket that becomes anonymously accessible should be a finding." The action is to fix or accept each bucket, so the finding is about the bucket, one per bucket. Its region can change without making it a different problem.

```json
{
  "rule": {
    "id": "s3-bucket-anonymous-access",
    "name": "S3 buckets with anonymous access",
    "description": "S3 buckets that anonymous principals can read or act on. Each finding is one bucket; fix the bucket policy or ACL, or accept the finding if the bucket is public on purpose.",
    "tags": ["aws", "data-exposure"],
    "references": [],
    "allow_community_contribution": false,
    "facts": [
      {
        "id": "s3-bucket-anonymous-access-0",
        "name": "S3 buckets with anonymous access",
        "description": "Buckets flagged as anonymously accessible or with anonymous actions allowed.",
        "module": "AWS",
        "cypher_query": "MATCH (b:AWSS3Bucket) WHERE b.anonymous_access = true OR (b.anonymous_actions IS NOT NULL AND size(b.anonymous_actions) > 0) RETURN b.id AS id, b.name AS name, b.region AS region LIMIT 1000",
        "cypher_visual_query": "MATCH (b:AWSS3Bucket) WHERE b.anonymous_access = true OR (b.anonymous_actions IS NOT NULL AND size(b.anonymous_actions) > 0) RETURN * LIMIT 1000",
        "asset_label": "AWSS3Bucket",
        "asset_id_field": "id",
        "identity_fields": ["id"],
        "display_field": "name"
      }
    ]
  }
}
```

## Output

A saved custom rule, or a draft waiting on the user's approval in chat, plus the hand-off from Step 6.

## Verification

Verification happens before the save: the probes in Step 3, then a save that passes the tool's own run. Do not promise to check findings later.

If, in a later turn, the user asks how an already-built rule is doing:

```cypher
MATCH (:Rule {id: '<RULE_ID>'})-[:PRODUCED]->(f:Finding:Signal)-[:AFFECTS {role: 'primary'}]->(a)
WHERE f.status = 'active'
RETURN f.display_name AS finding, labels(a) AS asset_labels, a.id AS asset_id
LIMIT 100
```

## Anti-patterns

- Choosing fields before naming the action. The anchor and the identity follow from it.
- Putting a count, a timestamp, or a list of current causes in the identity. Findings churn and acceptance is lost.
- Leaving `identity_fields` unset on a query whose columns may grow. Every new column replaces every finding.
- A `LIMIT` near the real count, or a query whose count is at its `LIMIT`. Findings rotate.
- An asset id that is not `<var>.id` off a node bound to `asset_label`, or one that can be null.
- Loosening a correct query because it returns 0 rows today.
- Renaming a fact id, or dropping optional fields, on an update.
- Saying you will wait for the build or check the findings later. The turn ends first.
- Retrying a refused body unchanged.

## References

- Custom rules in SubImage: https://app.subimage.io/docs/custom_rules
- SubImage MCP setup: https://app.subimage.io/docs/agents/connect_via_mcp
- Schema discovery and Cypher authoring: [`build-cypher-query`](../build-cypher-query/SKILL.md)
