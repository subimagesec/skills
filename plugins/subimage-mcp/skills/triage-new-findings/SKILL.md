---
name: triage-new-findings
description: Triage SubImage security findings against the enabled compliance frameworks, group them by theme, and recommend the next investigation steps. Use when the user asks to "triage findings", "what's new in SubImage today", "summarize my open findings", "any urgent findings", or wants a daily/weekly findings digest. Pulls framework status first, then per-framework rules and findings, and proposes the highest-priority items per framework.
---

# Triage new findings

## What this does

Walks SubImage's compliance frameworks → rules → findings hierarchy to produce a triaged digest the user can act on. Always grounds findings in the framework that flagged them so the user understands which control set is unhappy, not just "rule X has 12 findings".

## When to use

✅ User asks for a findings digest, triage, or "what's new".
✅ User wants to know which findings are most urgent or which framework is most off-track.
✅ Used as the body of a scheduled agent for a daily/weekly security brief.

❌ User asks about a specific CVE: use `subimage-mcp:investigate-cve` instead.
❌ User asks about a specific attack path: use `subimage-mcp:review-attack-path`.
❌ User wants the underlying graph (relationships, blast radius): build a Cypher query via `subimageAgentBuildQuery` then run with `subimageRunCypher`.

## Prerequisites

The user is connected to SubImage via MCP and has the `subimageReadMe` global tool guide available. This skill assumes the role-based tools (`subimageListFrameworks`, `subimageListRules`, `subimageGetRuleFindings`, optionally `subimageSendNotification` and `subimageCreateTicket`) are reachable.

## Optional inputs (ask only if relevant)

| Value | When to ask |
|---|---|
| Framework filter | If the user mentions one explicitly ("CIS AWS", "SubImage", "SOC 2"), scope to it. Otherwise pull all enabled frameworks and break down by framework. |
| Time window | If the user says "this week", "since yesterday": apply that window to `lastSeenAt` / `firstSeenAt`. Default: open and recently updated. |
| Severity threshold | If the user says "only criticals": filter `severity in [critical, high]`. Default: include everything. |
| Notification target | Only if the user explicitly asks to ship the digest somewhere (Slack channel, email, ticket). Never send unprompted. |

## Workflow

### 1. Frameworks first

Call `subimageListFrameworks`. Identify which are enabled. Note their slugs and display names. Common frameworks: `cis-aws`, `cis-gcp`, `cis-azure`, `subimage`, plus any custom ones.

If zero enabled, stop and tell the user: "No compliance frameworks are enabled. Enable one in **Settings → Frameworks**, or run `subimage-mcp:improve-cartography-coverage` to suggest which ones make sense given the connected modules."

### 2. List rules per framework

Call `subimageListRules`. Group by framework. For each framework, keep rules where `findingsCount > 0`. Sort by:

1. Severity (critical, high, medium, low)
2. Findings count (desc)
3. Most recently updated

Take the top 5 to 10 per framework. Going wider produces noise; going narrower hides cross-framework patterns.

### 3. Pull findings for the top rules

For each top rule, call `subimageGetRuleFindings(rule_id)`. Collect:

- resource type / cloud account / region distribution
- a few representative resource ids (use entity tags so the UI links to them)
- whether any are already accepted/dismissed (skip those in the digest)

If a rule has hundreds of findings, sample the most recent and mention the total count.

### 4. Group and prioritize

Look across the collected findings for cross-rule themes. Examples that often emerge:

- **Misconfiguration cluster**: one account or one team owns most of the offenders → propose ownership ping
- **Drift since last week**: rules where `findingsCount` jumped → propose investigating the change
- **Compliance regression**: a framework with a worsening pass rate vs. its history → propose which rule(s) caused it
- **Cross-framework overlap**: a rule appears in `cis-aws` and `subimage` → only count once in the prioritized list

### 5. Output

Produce a digest in this exact structure:

```
# SubImage findings triage: <date>

## Frameworks at a glance
- <framework name>: <pass-rate or finding-count summary>, <delta if known>
- ...

## Top issues per framework

### <framework 1>
1. <rule title>: <count> findings, severity <X>
   - hot resources: [[entity:<Label>:<id>|<short-name>]], [[entity:<Label>:<id>|<short-name>]] (+<rest>)
   - why it matters: <one line>
   - next step: <one line>
2. ...

### <framework 2>
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

- Listing all rules with `findingsCount > 0` regardless of severity. Turns the digest into a CSV.
- Reformatting the raw `subimageGetRuleFindings` output as a Markdown table. The system prompt in chat already forbids this for tool-derived data, and the markdown table produces a wall of text.
- Speculating about why a finding exists without a Cypher query to back it up. Stay grounded in tool output.
- Quoting the same resource multiple times in the same theme. Tag once, then count "+N more".

## References

- Tool guide (always loaded by `subimageReadMe`): see Domain 5 "Compliance & Security Findings" and Domain 6 "Ticket Management".
- Scheduled agents (where this skill is most useful as a recurring prompt): https://app.subimage.io/docs/agents/scheduled_agents
