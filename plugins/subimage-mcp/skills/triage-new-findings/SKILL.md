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
✅ Used as the body of a scheduled agent for a daily/weekly security brief.

❌ User asks about a specific CVE: use `subimage-mcp:investigate-cve` instead.
❌ User asks about a specific attack path: use `subimage-mcp:review-attack-path`.
❌ User wants the underlying graph (relationships, blast radius): build a Cypher query via `subimageAgentBuildQuery` then run with `subimageRunCypher`.

## Prerequisites

The `subimageReadMe` global tool guide is available. This skill assumes the role-based tools (`subimageListRules`, `subimageGetRuleFindings`, optionally `subimageSendNotification` and `subimageCreateTicket`) are reachable.

## Optional inputs (ask only if relevant)

| Value | When to ask |
|---|---|
| Tag / theme filter | If the user mentions one explicitly ("IAM", "exposure", "encryption"), scope to rules carrying that tag. If they name a framework ("CIS AWS", "SubImage", "SOC 2"), keep only rules whose `frameworks` (from `subimageGetRuleFindings`) include it. Otherwise break down by tag across all rules. |
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

Take the top 5 to 10 per tag group. Going wider produces noise; going narrower hides cross-cutting patterns.

### 3. Pull findings for the top rules

For each top rule, call `subimageGetRuleFindings(rule_id)`. Collect:

- resource type / cloud account / region distribution
- a few representative resource ids (use entity tags so the UI links to them)
- the `frameworks` the rule belongs to (optional context for the digest)
- whether any are already accepted/dismissed (skip those in the digest)

If a rule has hundreds of findings, sample the most recent and mention the total count.

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
- Reformatting the raw `subimageGetRuleFindings` output as a Markdown table. The system prompt in chat already forbids this for tool-derived data, and the markdown table produces a wall of text.
- Speculating about why a finding exists without a Cypher query to back it up. Stay grounded in tool output.
- Quoting the same resource multiple times in the same theme. Tag once, then count "+N more".

## References

- Tool guide (always loaded by `subimageReadMe`): see Domain 5 "Compliance & Security Findings" and Domain 6 "Ticket Management". Note `subimageListRules` returns per-rule `tags` and takes no `framework` argument.
- Scheduled agents (where this skill is most useful as a recurring prompt): https://app.subimage.io/docs/agents/scheduled_agents
