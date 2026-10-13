---
name: fix-custom-rule
description: Find SubImage custom rules that fail in the findings build, explain why, and repair them via MCP. Lists failing rules with subimageListRules(exec_status="ERROR"), reads the error code and fix hint, pulls the rule's definition, tests a corrected draft with subimageTestCustomRule, and saves it with subimageUpdateCustomRule. Use when the user asks "why is this rule failing", "fix my custom rule", "which rules are broken", or when a rule shows an error status.
---

# Fix a failing SubImage custom rule

When a rule hits one bad row during the findings build, the whole rule stops for that run: its findings are not refreshed and the build reports it as failed. This skill finds those rules, explains each failure in plain terms, and repairs the custom ones without leaving the chat. It ends when the corrected rule is saved and the user knows when it will run again.

## When to use

✅ The user asks why a rule is failing, which rules are broken, or to fix a custom rule.
✅ A rule shows an `error` status in the UI, or a findings sync was reported as degraded.

❌ The failing rule is built in (not `custom_rule`). Its definition can't be edited. Report the reason and hint; most built-in failures come from stale graph data and clear after the next sync, otherwise contact SubImage support.
❌ The user wants a new rule. Use [`create-custom-rule`](../create-custom-rule/SKILL.md).

## Workflow

### Step 1: Find failing rules

Call `subimageListRules(exec_status="ERROR")`. Each item carries:

- `error_code`: why the last run failed (table below),
- `error`: one sentence naming what went wrong and where, for example "Column 'public_read' returned a boolean, but its output field is declared as string. Seen on S3Bucket 'example-bucket', fact 'example-rule-0' of rule 'example-rule'.",
- `error_hint`: how to fix it,
- `last_ok_at`: the last run that completed. Findings are not fully refreshed since then,
- `custom_rule`: whether the tenant can edit it.

If the user named a rule, find it in the list. If `exec_status` is not accepted, the deployment predates rule health: call `subimageListRules()` and open the rule in the UI instead.

### Step 2: Explain the failure

Tell the user, per failing rule: the `error` sentence, the `error_hint`, and how long findings have been stale (`last_ok_at`). For built-in rules, stop here.

| `error_code` | Meaning | Usual fix |
|---|---|---|
| `invalid_rule_output` | A returned value doesn't match its output field's declared type | Change the field's `type` (a true/false property is `boolean`), or convert in Cypher with `toString()` |
| `duplicate_signal_id` | Two rows share every output value but differ in asset or extra columns | Add the distinguishing column as an output field, or combine rows with `DISTINCT` |
| `affected_asset_not_found` | The asset id field doesn't match a node with the Fact's asset label | Return the node's `id` property in the asset id field, and check the asset label |
| `affected_asset_source_missing` | The matched node wasn't written by a sync module | Stale graph data; not fixable in the rule. Contact SubImage support |
| `display_name_unresolvable` | A matched asset has no name or id | Return a non-empty id in the asset id field |
| `invalid_fact` | The Fact is missing its asset label, asset id field or output fields | Fill them in |
| `cypher_error` | Neo4j rejected the query | Run it with `subimageRunCypher` to see the full error, then fix it |
| `query_timeout`, `memory_limit_exceeded` | The query is too heavy | Filter early on labels, filter before aggregating, bound variable-length paths |
| `internal_error` and other processing codes | SubImage couldn't process the results | Not a rule problem. Contact SubImage support |

### Step 3: Pull the definition

Call `subimageListRules(view="custom_definitions")` and take the failing rule's full definition: facts (`cypher_query`, `cypher_visual_query`, `asset_label`, `asset_id_field`, `module`), `output_fields`, tags and references.

To confirm the cause before editing, reproduce it with `subimageRunCypher`. For a type mismatch, check the returned types:

```cypher
MATCH (b:S3Bucket) WHERE b.anonymous_access = true
WITH b.anonymous_access AS public_read
RETURN valueType(public_read) AS type, count(*) AS rows
```

For duplicates, group by every output field and look for counts above one.

### Step 4: Draft and test the fix

Apply the smallest change that fixes the code: a field type, a `DISTINCT`, an extra output field, a narrower match. Keep the rule `id` and the fact ids unchanged.

If `subimageTestCustomRule` is available, call it with the full corrected rule. It runs the draft through the same detection as the findings build, read-only, and returns per fact `ok`, `findings_count`, a `sample`, `duration_ms`, and on failure `error_code`, `error` and `error_hint`. Repeat until `ok` is true (a fact that only hit `query_timeout` may still be saved; `can_save` says so). If the tool is not available, rerun the Step 3 checks with `subimageRunCypher` against the corrected query.

Changing an output field's type or value shape changes the finding identity: the rule's existing findings close and new ones open on the next run. Tell the user before saving.

### Step 5: Save

Call `subimageUpdateCustomRule` once with the full corrected rule (omitted optional fields reset to their defaults, so send everything from Step 3). In chat clients this asks the user to approve the change. Where the test run is enabled, the save runs it again and returns `error="custom_rule_test_failed"` if the rule would still fail: read `message`, fix the draft and retry.

### Step 6: Report back

Tell the user what changed and why, that the rule runs again on the next scheduled findings build, and how to confirm: `subimageListRules(exec_status="ERROR")` no longer lists it after that build.

## Anti-patterns

- Editing a built-in rule's behavior by creating a near-copy custom rule without telling the user.
- Saving without testing the corrected draft.
- Sending a partial rule to `subimageUpdateCustomRule`; omitted fields reset.
- Changing the rule `id` or fact ids to "start fresh". It orphans the rule's history.
- Treating `affected_asset_source_missing` or processing errors as rule bugs.

## References

- SubImage MCP setup: https://app.subimage.io/docs/agents/connect_via_mcp
- Authoring new rules: [`create-custom-rule`](../create-custom-rule/SKILL.md)
- Cypher discovery: [`build-cypher-query`](../build-cypher-query/SKILL.md)
