---
name: improve-subimage-coverage
description: Audit the current repo for cloud / SaaS providers that are NOT yet wired into SubImage, then list the security rules with findings and surface the top actionable ones grouped by tag. Use when the user asks to "improve SubImage coverage", "what should I connect to SubImage", "audit SubImage coverage", "what's missing in my SubImage setup", or runs this on a recurring schedule against their IaC repo. Closes the loop between "I have IaC defining X" and "SubImage tells me what's wrong with X".
---

# Improve SubImage coverage

## What this does

Three passes:

1. **Detect** which providers the user's current repo and local environment touch (Terraform providers, CLI configs, git remotes).
2. **Cross-reference** with `subimageListModules` to compute coverage gaps and link them to the right setup skill.
3. **Inspect** the security rules that have findings: list them directly, group by tag, and surface the top actionable ones, prioritizing tags whose resources come from a recently-detected or newly-enabled provider.

This is the bridge between IaC reality and SubImage observability. Most other skills assume the wiring is already done; this one finds the wiring that is missing and the findings that prove it would have been worth doing.

## When to use

✅ User opens this skill in their IaC or scripts repo and wants a coverage audit.
✅ User just enabled a new module and wants to know which findings now light up.
✅ User wants this on a recurring cadence (weekly recurring prompt on the IaC repo).
✅ Onboarding of a new tenant: catches what was forgotten.

❌ User wants to actually connect a specific module: this skill diagnoses; the `subimage-setup:connect-<module>` skills do the work. This skill should hand off.

## Prerequisites

- The skill runs against the **current working directory**. Run it from the root of the IaC or scripts repo to maximize signal.
- Uses `subimageListModules`, `subimageListRules`, `subimageRunCypher`.

## Workflow

### 1. Detect providers from the local repo

Build a set `detected_providers` of raw Terraform provider names from these signals. They are read-only; nothing here mutates the repo. The next step normalizes this set to SubImage module slugs (`detected_modules`).

**Terraform providers** (strongest signal):

```bash
grep -rEho 'provider[[:space:]]+"(aws|google|azurerm|github|kubernetes|okta|cloudflare|tailscale|datadog|gitlab|slack|pagerduty|sentry|cloudflare|snowflake|vercel|sentinelone|crowdstrike)"' \
  --include='*.tf' . 2>/dev/null \
  | sort -u
```

Normalize each Terraform provider name to the matching SubImage module slug **before any diff**; the raw provider names and the module slugs are not the same vocabulary (`google` ≠ `gcp`, `azurerm` ≠ `azure`). Apply this map:

| Terraform provider | SubImage module slug |
|---|---|
| `aws` | `aws` |
| `google` | `gcp` |
| `azurerm` | `azure` |
| `github` | `github` |
| `gitlab` | `gitlab` |
| `kubernetes` | `kubernetes` (plus `connect-kubernetes-outpost` if the cluster API is private) |
| `okta` | `okta` |
| `cloudflare` | `cloudflare` |
| `tailscale` | `tailscale` |
| `datadog` | none yet (note as "no SubImage module") |
| `slack` | `slack` |
| `pagerduty` | `pagerduty` |
| `sentry` | `sentry` |
| `vercel` | `vercel` |
| `sentinelone` | `sentinelone` |
| `crowdstrike` | `crowdstrike` |

After mapping, `detected_modules` is the **set of SubImage module slugs** the repo touches. Drop entries whose mapped slug is `none`: they cannot be a coverage gap by definition.

**CLI / environment signals** (weaker, but useful when no IaC):

```bash
ls ~/.aws/config 2>/dev/null && echo "aws cli configured"
ls ~/.config/gcloud/configurations/ 2>/dev/null | head && echo "gcloud configured"
kubectl config get-contexts 2>/dev/null | tail -n +2 | awk '{print $2}' | sort -u
gh auth status 2>/dev/null | grep -E 'Logged in to' || true
git remote -v 2>/dev/null | awk '{print $2}' | sort -u  # github.com / gitlab.com / bitbucket.org / ghe host
```

**Manifest signals** (optional, only if there are package manifests in the repo):

- `package.json` deps containing `@slack/web-api`, `octokit`, `@datadog/...` → reinforces those providers.
- `requirements.txt` / `pyproject.toml` containing `boto3`, `google-cloud-*`, `azure-mgmt-*` → reinforces cloud providers.

Treat manifest hits as additive but lower-confidence than Terraform providers.

### 2. List enabled SubImage modules

```
subimageListModules()
```

Build set `enabled_modules` from rows where the module is enabled (configured and connected, not just listed). The values here are SubImage module slugs (`aws`, `gcp`, `azure`, `kubernetes`, ...), which is why step 1 must normalize the Terraform provider names before this step runs.

### 3. Compute coverage gaps

`coverage_gaps = detected_modules \ enabled_modules`

Both sides are SubImage module slugs after step 1's normalization. If you skipped the mapping, you will report false gaps (e.g. report `google` as missing while the `gcp` module is enabled).

For each gap, classify:

- **Tier 1 (skill exists)**: `aws`, `gcp`, `azure`, `github`, `kubernetes` (use `connect-kubernetes-outpost` when the cluster API is private), `declarative_schema`. Link directly to the matching `subimage-setup:connect-<module>` skill (loaded by the SubImage marketplace plugin).
- **Tier 2 (no skill yet)**: any other module SubImage supports. Link to `https://app.subimage.io/docs/modules/<module>`.
- **No SubImage module**: e.g. `datadog`. Note it without a link.

Also note the inverse: modules enabled in SubImage that you do NOT see in the repo. Usually fine (they may be wired elsewhere), but worth flagging if it is something the user clearly does not own anymore.

### 4. List the rules directly

```
subimageListRules()
```

This returns every rule with `id`, `name`, `description`, `tags`, `findings_count`, `has_findings`, and `disabled`. There is **no** `framework` parameter; do not pass one. Findings live on rules, and each rule carries its own `tags` (theme/category) and, through `(:Rule)-[:MAPS_TO]->(:Framework)` in the graph, its compliance frameworks. Tags are the grouping axis here, not frameworks.

Keep only rows where `has_findings` is true (`findings_count > 0`) and `disabled` is false. If that set is empty, the rule set is not producing findings yet (modules may still be syncing, or no rules are enabled): say so and skip step 5.

### 5. Group by tag and surface the top findings

Group the kept rules by `tags` (a rule with multiple tags appears in each of its tag groups). `subimageListRules()` does not return severity, so do the initial ranking on the fields it does return:

1. Whether the tag group ties to a slug in `detected_modules` OR a module just promoted out of the gap list (relevance to this repo wins).
2. Findings count (desc).

Take a candidate top ~8 rules, then pull their findings in one query. Findings
are `:Signal` nodes in the graph, one per affected asset. Slice per rule, not
globally:

```cypher
MATCH (r:Rule)
WHERE r.id IN ['<rule-id-1>', '<rule-id-2>']
CALL (r) {
  MATCH (r)-[:PRODUCED]->(f:Finding:Signal)-[:AFFECTS {role: 'primary'}]->(n)
  WHERE f.status = 'active'
  RETURN f, n
  ORDER BY f.first_seen DESC
  LIMIT 12
}
RETURN r.id AS rule, f.display_name AS asset_name, n.id AS asset_id,
       labels(n) AS asset_labels, f.first_seen AS first_seen
ORDER BY rule, asset_name
```

`subimageRunCypher` returns at most 100 rows whatever `LIMIT` you write, so
`rules x per-rule limit` has to stay under it: 8 rules at 12 is 96. A single
global `LIMIT 100` ordered by rule name would let one noisy rule consume the
entire budget, leaving every other rule looking clean when it is not. Keep the
`CALL (r) { ... }` subquery; that is what makes the slice per rule.

Capture: a few representative resources (with entity tags), account or project distribution, and (optional context) the frameworks the rule belongs to, via `(r)-[:MAPS_TO]->(:Framework)`, whose id is `{short_name}:{scope}` such as `cis:aws` or `soc2:tsc`. Findings carry no severity field, so keep the ranking above (repo relevance, then findings count) and take the top 5.

### 6. Output

Use this exact structure:

```
# SubImage coverage audit: <repo path or org name>

## Coverage gaps (detected here, not enabled in SubImage)
- **<provider>** → <Tier 1 link to setup skill> *(recommended next step)*
- **<provider>** → <Tier 2 link to docs>
- **<provider>** → no SubImage module yet, skip

If empty: "No coverage gaps detected. Every provider this repo touches is enabled in SubImage."

## Enabled but not detected here
- <module>: enabled in SubImage but not visible in this repo. (Usually fine; just confirm ownership.)

If empty: omit this section.

## Top actionable findings (by tag)
### <tag group, e.g. "iam" / "exposure" / "encryption">
1. <rule title>: <count> findings
   - hot resources: [[entity:<Label>:<id>|<short>]] (+<rest>)
   - tied to: <provider> *(newly detected: yes/no)*
   - next step: <one line>
2. ...

If no rules have findings: "No rules are producing findings yet. Modules may still be syncing, or no rules are enabled."

## Recommended actions (ranked)
1. <action with the highest expected leverage, usually closing the most impactful gap>
2. ...
```

### 7. Hand off

If the top recommended action is "connect provider X" and a Tier 1 setup skill exists, offer to load it:

> Want me to walk through `subimage-setup:connect-<module>` now? It will ask for the values it needs (tenant id, account ids, etc.) and produce the Terraform / CloudFormation / CLI snippets.

Do not auto-load. The user opts in.

## Anti-patterns

- Treating manifest hits as authoritative. `boto3` in a requirements file does not mean AWS is in production; Terraform `provider "aws"` does.
- Recommending modules SubImage does not support. Only Tier 1 / Tier 2 modules. Note unsupported providers without linking.
- Generating a wall of findings. Top 5 is the budget; deeper goes into `subimage-mcp:triage-new-findings`.
- Pivoting into actually configuring a module from this skill. Hand off.
- Using Cypher to invent coverage data. Use `subimageListModules` directly; it is the canonical source.
- Passing a `framework=` argument to `subimageListRules`. The tool does not accept one; list rules directly and group by `tags`.

## References

- Tool guide (always loaded by `subimageReadMe`): Domain 5 "Compliance & Security Findings", Domain 7 "Cloud CLI Command Generation" (for verification). Note `subimageListRules` returns per-rule `tags` and takes no `framework` argument.
- Setup skills: `subimage-setup:connect-aws`, `subimage-setup:connect-gcp`, `subimage-setup:connect-azure`, `subimage-setup:connect-github`, `subimage-setup:connect-kubernetes-outpost`.
- Findings triage follow-up: `subimage-mcp:triage-new-findings`.
