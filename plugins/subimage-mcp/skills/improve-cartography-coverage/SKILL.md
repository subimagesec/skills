---
name: improve-cartography-coverage
description: Audit the current repo for cloud / SaaS providers that are NOT yet wired into SubImage, then check whether the SubImage compliance framework is enabled and surface its top actionable findings. Use when the user asks to "improve SubImage coverage", "what should I connect to SubImage", "audit cartography coverage", "what's missing in my SubImage setup", or runs this on a recurring schedule against their IaC repo. Closes the loop between "I have IaC defining X" and "SubImage tells me what's wrong with X".
---

# Improve cartography coverage

## What this does

Three passes:

1. **Detect** which providers the user's current repo and local environment touch (Terraform providers, CLI configs, git remotes).
2. **Cross-reference** with `subimageListModules` to compute coverage gaps and link them to the right setup skill.
3. **Inspect** the SubImage compliance framework state: if enabled, surface its top actionable findings, prioritizing those whose resources come from a recently-detected or newly-enabled provider.

This is the bridge between IaC reality and SubImage observability. Most other skills assume the wiring is already done; this one finds the wiring that is missing and the findings that prove it would have been worth doing.

## When to use

✅ User opens this skill in their IaC or scripts repo and wants a coverage audit.
✅ User just enabled a new module and wants to know which findings now light up.
✅ User wants this on a recurring cadence (weekly scheduled agent on the IaC repo).
✅ Onboarding of a new tenant: catches what was forgotten.

❌ User wants to actually connect a specific module: this skill diagnoses; the `subimage-setup:connect-<module>` skills do the work. This skill should hand off.

## Prerequisites

- The skill runs against the **current working directory**. Run it from the root of the IaC or scripts repo to maximize signal.
- Connected to SubImage via MCP (uses `subimageListModules`, `subimageListFrameworks`, `subimageListRules`, `subimageGetRuleFindings`).

## Workflow

### 1. Detect providers from the local repo

Build a set `detected_providers` from these signals. They are read-only; nothing here mutates the repo.

**Terraform providers** (strongest signal):

```bash
grep -rEho 'provider[[:space:]]+"(aws|google|azurerm|github|kubernetes|okta|cloudflare|tailscale|datadog|gitlab|slack|pagerduty|sentry|cloudflare|snowflake|vercel|sentinelone|crowdstrike)"' \
  --include='*.tf' . 2>/dev/null \
  | sort -u
```

Terraform provider name → SubImage module slug:

| Provider | Module slug |
|---|---|
| `aws` | `aws` |
| `google` | `gcp` |
| `azurerm` | `azure` |
| `github` | `github` |
| `gitlab` | `gitlab` |
| `kubernetes` (private endpoint) | implies `eks` + `connect-kubernetes-outpost` |
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

Build set `enabled_modules` from rows where the module is enabled (configured and connected, not just listed).

### 3. Compute coverage gaps

`coverage_gaps = detected_providers \ enabled_modules`

For each gap, classify:

- **Tier 1 (skill exists)**: `aws`, `gcp`, `azure`, `github`, `kubernetes`/EKS-private (outpost). Link directly to the matching `subimage-setup:connect-<module>` skill (loaded by the SubImage marketplace plugin).
- **Tier 2 (no skill yet)**: any other module SubImage supports. Link to `https://app.subimage.io/docs/modules/<module>`.
- **No SubImage module**: e.g. `datadog`. Note it without a link.

Also note the inverse: modules enabled in SubImage that you do NOT see in the repo. Usually fine (they may be wired elsewhere), but worth flagging if it is something the user clearly does not own anymore.

### 4. Check the SubImage compliance framework

```
subimageListFrameworks()
```

Find the entry whose slug or display name is `subimage` (or "SubImage"). Three cases:

- **Not present**: the framework is not available for this tenant version. Skip step 5.
- **Disabled**: tell the user "The SubImage framework exists but is not enabled. Enable it at **Settings → Frameworks → SubImage** to get the curated rule set on top of CIS." Skip step 5.
- **Enabled**: continue to step 5.

### 5. Surface top actionable findings (only if framework enabled)

```
subimageListRules(framework="<subimage-framework-slug>")
```

Filter to rules with `findingsCount > 0`. Take the top 5 by:

1. Severity (critical → high → medium → low)
2. Recently-touched providers (rules whose resource type maps to a provider in `detected_providers` OR a provider just promoted out of the gap list)
3. Findings count (desc)

For each top rule:

```
subimageGetRuleFindings(rule_id="<rule-id>")
```

Capture: a few representative resources (with entity tags), severity, account or project distribution.

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

## SubImage framework status
- Status: <enabled / disabled / not available>
- <one-line action if disabled or missing>

## Top actionable findings (SubImage framework, if enabled)
1. <rule title>: <count> findings, severity <X>
   - hot resources: [[entity:<Label>:<id>|<short>]] (+<rest>)
   - tied to: <provider> *(newly detected: yes/no)*
   - next step: <one line>
2. ...

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

## References

- Tool guide (always loaded by `subimageReadMe`): Domain 5 "Compliance & Security Findings", Domain 7 "Cloud CLI Command Generation" (for verification).
- Setup skills: `subimage-setup:connect-aws`, `subimage-setup:connect-gcp`, `subimage-setup:connect-azure`, `subimage-setup:connect-github`, `subimage-setup:connect-kubernetes-outpost`.
- Findings triage follow-up: `subimage-mcp:triage-new-findings`.
