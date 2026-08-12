---
name: triage-new-findings
description: Triage SubImage security findings by listing the rules that have findings, grouping them by tag/theme, and recommending the next investigation steps. Use when the user asks to "triage findings", "what's new in SubImage today", "summarize my open findings", "any urgent findings", or wants a daily/weekly findings digest. Lists rules directly, groups by tag, and proposes the highest-priority items per theme (surfacing compliance frameworks as context).
---

# Triage new findings

## What this does

Lists SubImage's security rules, groups the ones with findings by tag (theme/category), and produces a triaged digest the user can act on. Surfaces the compliance frameworks a rule belongs to as context where useful, so the user understands which control set is unhappy, not just "rule X has 12 findings".

## When to use

✅ User asks for a findings digest, triage, or "what's new".
✅ User wants to know which findings are most urgent or which framework is most off-track.
✅ Used as a recurring prompt for a daily/weekly security brief.

❌ User asks about a specific CVE: use `subimage-mcp:investigate-cve` instead.
❌ User asks about a specific attack path: use `subimage-mcp:review-attack-path`.
❌ User wants the underlying graph (relationships, blast radius): build a Cypher query via `subimageAgentBuildQuery` then run with `subimageRunCypher`.

## Prerequisites

The `subimageReadMe` global tool guide is available. This skill assumes the role-based tools (`subimageListRules`, `subimageRunCypher`, optionally `subimageSendNotification` and `subimageCreateTicket`) are reachable.

## Optional inputs (ask only if relevant)

| Value | When to ask |
|---|---|
| Tag / theme filter | If the user mentions one explicitly ("IAM", "exposure", "encryption"), scope to rules carrying that tag. If they name a framework ("CIS AWS", "SubImage", "SOC 2"), keep only rules mapped to it via `(:Rule)-[:MAPS_TO]->(:Framework)`. Otherwise break down by tag across all rules. |
| Time window | If the user says "this week", "since yesterday": apply that window to `lastSeenAt` / `firstSeenAt`. Default: open and recently updated. |
| Severity threshold | If the user says "only criticals": filter `severity in [critical, high]`. Default: include everything. |
| Notification target | Only if the user explicitly asks to ship the digest somewhere (Slack channel, email, ticket). Never send unprompted. |

## Workflow

### 1. List the rules directly

Call `subimageListRules()`. It returns every rule with `id`, `name`, `description`, `tags`, `findings_count`, `has_findings`, and `disabled`. There is **no** `framework` parameter; do not pass one. Keep rows where `has_findings` is true and `disabled` is false.

If none have findings, stop and tell the user: "No rules are producing findings right now. Modules may still be syncing, or no rules are enabled. Run `subimage-mcp:improve-subimage-coverage` to check coverage."

### 2. Group by tag

Group the kept rules by `tags` (a rule with multiple tags appears in each of its tag groups). Within each group sort by:

1. Severity (critical, high, medium, low)
2. Findings count (desc)
3. Most recently updated

Take the top 5 per tag group. Going wider produces noise, and step 3 can only pull findings for 5 rules per call anyway.

### 3. Pull findings for the top rules

Findings are `:Signal` nodes in the graph, one per affected asset. Pull the top
rules in one query rather than one call per rule.

**Budget the row count first.** `subimageRunCypher` returns at most 100 rows
whatever `LIMIT` you write, so `rules x per-rule limit` must stay under 100.
Take **at most 5 rules at 20 findings each**. Ask for 8 rules at 25 and you get
200 rows requested, 100 returned, and the tail rules come back empty while the
digest reads as if they had no findings.

```cypher
MATCH (r:Rule)
WHERE r.id IN ['<rule-id-1>', '<rule-id-2>']
CALL (r) {
  MATCH (r)-[:PRODUCED]->(f:Finding:Signal)-[:AFFECTS {role: 'primary'}]->(n)
  WHERE f.status = 'active'
  RETURN f, n
  ORDER BY f.first_seen DESC
  LIMIT 20
}
RETURN r.id AS rule, f.id AS finding_id, f.display_name AS asset_name,
       n.id AS asset_id, labels(n) AS asset_labels, f.first_seen AS first_seen
ORDER BY rule, first_seen DESC
```

The per-rule subquery is what makes "top 20 most recent **per rule**" hold. A
single global `LIMIT` ordered by name would spend the whole budget on whichever
rule sorts first and return nothing for the rest.

`first_seen` is a graph temporal, so `ORDER BY` on it is chronological rather
than lexicographic. `role: 'primary'` is the only role written on a finding's
`AFFECTS`, so naming it changes no results; it just states which edge is meant.

If more than 5 rules deserve a look, run the query again with the next batch
rather than widening one call.

Collect:

- resource type / cloud account / region distribution, from `asset_labels` and by traversing from the asset to its `:Tenant`
- a few representative resource ids (use entity tags so the UI links to them)
- the frameworks the rule belongs to, via `(r)-[:MAPS_TO]->(:Framework)`, whose id is `{short_name}:{scope}` such as `cis:aws` or `soc2:tsc` (optional context for the digest)
- the query filters `f.status = 'active'`, which drops findings whose risk a human accepted. That is a deliberate narrowing for a "what is open" digest, and it is narrower than the product's own finding reads, which return active and accepted and label the accepted ones. Widen to `IN ['active','accepted']` if the user asks what the rule currently matches rather than what is on their plate.

If a rule has hundreds of findings, sample the most recent and mention the total from that rule's `findings_count` in step 1's `subimageListRules()`. Do not use the query's own row count: the per-rule `LIMIT 20` caps it, so it reports the sample size, not the total.

### 4. Group and prioritize

Look across the collected findings for cross-rule themes. Examples that often emerge:

- **Misconfiguration cluster**: one account or one team owns most of the offenders → propose ownership ping
- **Drift since last week**: rules where `findings_count` jumped → propose investigating the change
- **Tag concentration**: one tag group (e.g. `iam`, `exposure`) holds most of the high-severity findings → propose tackling that theme first
- **Cross-framework overlap**: a rule's `frameworks` include both `cis-aws` and `subimage` → only count it once in the prioritized list

### 5. Output

Produce a digest in this exact structure:

```
# SubImage findings triage: <date>

## At a glance
- <tag group>: <rule count> rules, <finding count> findings, <delta if known>
- ...

## Top issues by tag

### <tag group 1, e.g. "iam">
1. <rule title>: <count> findings, severity <X>
   - hot resources: [[entity:<Label>:<id>|<short-name>]], [[entity:<Label>:<id>|<short-name>]] (+<rest>)
   - frameworks: <e.g. cis-aws, subimage> (if useful)
   - why it matters: <one line>
   - next step: <one line>
2. ...

### <tag group 2>
...

## Cross-cutting themes
- <theme>: <evidence>

## Recommended actions
- <action 1, owner-pingable>
- <action 2, ticket-worthy>
```

Keep each rule entry to 3-4 lines. The user is scanning, not reading.

### 6. Optional: ship it

If (and only if) the user asked to send the digest:

- Slack/email: call `subimageSendNotification(channel=..., body=...)`. Confirm the channel before sending.
- Ticket: call `subimageCreateTicket(team_id=..., title=..., description=...)`. Use `subimageListLinearTeams` first to resolve `team_id` if not known.

Never auto-send without explicit confirmation. The digest is most useful as a chat answer first.

## Anti-patterns

- Listing all rules with `findings_count > 0` regardless of severity. Turns the digest into a CSV.
- Passing a `framework=` argument to `subimageListRules`. The tool does not accept one; list rules directly and group by `tags`.
- Reformatting the raw finding rows as a Markdown table. The system prompt in chat already forbids this for tool-derived data, and the markdown table produces a wall of text.
- Speculating about why a finding exists without a Cypher query to back it up. Stay grounded in tool output.
- Quoting the same resource multiple times in the same theme. Tag once, then count "+N more".

## References

- Tool guide (always loaded by `subimageReadMe`): see Domain 5 "Compliance & Security Findings" and Domain 6 "Ticket Management". Note `subimageListRules` returns per-rule `tags` and takes no `framework` argument.
