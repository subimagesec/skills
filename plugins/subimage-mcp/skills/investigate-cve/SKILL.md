---
name: investigate-cve
description: Investigate a specific CVE in SubImage end-to-end (severity, KEV status, affected resources, fixability) and offer to pivot into attack-path exploration on the impacted assets. Use when the user mentions a CVE id ("CVE-2024-3094", "what's affected by CVE-2023-44487"), asks to "investigate this CVE", "is this CVE exploitable in our environment", "should we patch this", or hands off a vendor advisory. Always finishes by asking whether to chain into review-attack-path.
---

# Investigate a specific CVE

## What this does

Given a CVE id, pulls SubImage's full picture for it: severity, KEV status, affected packages and resources, available fixes, and a one-line recommended action. After the static summary, offers to pivot into attack-path analysis on the impacted assets so the user can answer the harder question: "is this CVE actually exploitable here?"

## When to use

✅ User pastes or names a specific CVE id and wants to understand the impact in their environment.
✅ User asks "should we patch CVE-X first" or "is CVE-X in the KEV catalog".
✅ User wants the list of containers / packages / images affected by a CVE.

❌ User wants the entire vulnerability backlog: use `subimage-mcp:triage-new-findings` (compliance) or `subimageGetVulnerabilitySummary` for raw counts.
❌ User wants to compare two CVEs: just run this skill twice and contrast the outputs.

## Prerequisites

User is connected to SubImage via MCP. This skill uses `subimageGetVulnerabilityDetails`, `subimageGetFixDetails`, and (optionally) `subimageAgentBuildQuery` + `subimageRunCypher`. The pivot at the end uses `subimageGetAttackPathsFromAsset`.

## Required inputs

| Value | If missing, ask |
|---|---|
| `<CVE_ID>` | "Which CVE id should I investigate? Format `CVE-YYYY-NNNNN`." |

## Workflow

### 1. Pull the full CVE record

```
subimageGetVulnerabilityDetails(cve_id="<CVE_ID>")
```

This returns: severity, CVSS, KEV status, description, affected packages, affected resources (containers, images, compute instances), discovered date, fix availability flags.

If the response is empty or 404, the CVE is not present in this tenant's data. Stop and tell the user: "SubImage has no record of `<CVE_ID>` in your environment. Either it does not affect any synced asset, or vulnerability scanning is not enabled for the relevant module. Run `subimage-mcp:improve-cartography-coverage` to check coverage."

### 2. If actionable, fetch fix details

For each affected package with a fix available, call:

```
subimageGetFixDetails(package="<package-name>")
```

Capture: target version, affected containers, whether the fix is a rebuild (image base change) or a package bump.

If nothing is fixable, note that explicitly in the summary; the next action shifts from "patch" to "monitor / mitigate / accept".

### 3. Optional graph follow-up

Use Cypher only when:

- The CVE record points at a resource type SubImage's structured tools do not surface in detail.
- The user explicitly asks how the CVE could propagate (e.g. "if `lodash` is here, where else is it transitively?").

```
subimageAgentBuildQuery(user_question="<rephrased intent>")
# then:
subimageRunCypher(query="<query returned above>")
```

Skip this step otherwise. The structured tools are faster and citable.

### 4. Summarize

Output in this exact structure. Keep it scannable.

```
# <CVE_ID>

**Severity**: <critical/high/...>  •  **CVSS**: <score>  •  **KEV**: <yes/no>

## What it is
<one-sentence description from the CVE record>

## Where it lands in your environment
- <count> containers across <count> images
- <count> compute instances
- packages affected: <pkg1>, <pkg2>, ...
- top exposed resources: [[entity:Container:<id>|<name>]], [[entity:Image:<id>|<name>]]

## Fixability
- **Patchable**: <count> packages have a fix → <pkg> ≥ <fixed-version>
- **Rebuild required**: <count> images need a base image bump
- **No fix yet**: <count> packages, mitigation only

## Recommended next action
<one line: patch this image first, bump this package across N services, monitor and revisit, or accept and document>
```

If KEV is `yes`, prepend a single-line callout above the title:

```
⚠️ KEV: actively exploited in the wild; prioritize over non-KEV criticals.
```

### 5. Offer the pivot to attack-path exploration

This is the most common follow-up question. Do NOT auto-pivot. End the response with:

```
Do you want me to check whether any of these resources sit on a known attack path?
I can run `subimageGetAttackPathsFromAsset` on the top exposed resources and walk through
the highest-impact ones with you (skill: `subimage-mcp:review-attack-path`).
```

If the user confirms:

- For each of the top 3 to 5 exposed resources, call `subimageGetAttackPathsFromAsset(asset_id=<id>)`.
- For any non-empty result, hand off to `subimage-mcp:review-attack-path` with the most critical path id.
- If all results are empty: "Good news: none of the affected resources are on a known attack path right now."

This converts a static CVE finding into a live exploitability question, which is the only reason most people ask about CVEs in the first place.

## Anti-patterns

- Reformatting `subimageGetVulnerabilityDetails` output as a markdown table. Forbidden by the chat system prompt for tool data.
- Asking the user to run `subimageRunCypher` themselves. Run it, summarize the result.
- Auto-pivoting to attack paths without confirmation. The user should opt in.
- Listing every affected resource. Top 5 + a count is enough.

## References

- Tool guide (always loaded by `subimageReadMe`): Domain 3 "Vulnerability Management" and Domain 4 "Attack Path Analysis".
- Companion skill for the pivot: `subimage-mcp:review-attack-path`.
