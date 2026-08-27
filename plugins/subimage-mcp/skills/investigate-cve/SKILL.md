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

❌ User wants the entire vulnerability backlog: use `subimage-mcp:triage-new-findings` (compliance), or count `(:VulnerabilitySignal:Signal)` by severity for raw numbers.
❌ User wants to compare two CVEs: just run this skill twice and contrast the outputs.

## Prerequisites

This skill reads the vulnerability graph through `subimageRunCypher`. The optional internet-enrichment step uses `WebSearch` (and `WebFetch` for a specific advisory URL). The pivot at the end reads attack paths from the same graph.

## Required inputs

| Value | If missing, ask |
|---|---|
| `<CVE_ID>` | "Which CVE id should I investigate? Format `CVE-YYYY-NNNNN`." |

## Workflow

### 1. Pull the full CVE record

A CVE is present as one `:VulnerabilitySignal:Signal` per affected service
image, all pointing at the same `:CVEMetadata`:

```cypher
MATCH (v:VulnerabilitySignal:Signal)-[:INSTANCE_OF]->(m:CVEMetadata)
WHERE v.cve_id = toUpper('<CVE_ID>') AND v.status IN ['active', 'accepted']
OPTIONAL MATCH (m)-[:ENRICHES]->(f:TrivyImageFinding:CVE)-[:AFFECTS]->(p:PackageVersion)
WHERE EXISTS { (v)-[:AFFECTS]->(:Image)<-[:DEPLOYED]-(p) }
OPTIONAL MATCH (p)-[:SHOULD_UPDATE_TO]->(fix:TrivyFix)-[:APPLIES_TO]->(f)
RETURN DISTINCT m.id AS cve, m.title AS title, m.description AS description,
       CASE
         WHEN m.base_severity IS NOT NULL THEN toUpper(m.base_severity)
         WHEN m.base_score >= 9 THEN 'CRITICAL'
         WHEN m.base_score >= 7 THEN 'HIGH'
         WHEN m.base_score >= 4 THEN 'MEDIUM'
         WHEN m.base_score > 0 THEN 'LOW'
         ELSE 'UNKNOWN'
       END AS severity,
       m.base_score AS cvss_score, m.published_date AS published_date,
       coalesce(m.is_kev, false) AS cisa_known_exploit, m.cisa_exploit_add AS kev_date,
       m.epss_score AS epss_score, m.epss_percentile AS epss_percentile,
       v.service_image AS service_image, v.status AS status,
       p.name AS package, p.version AS installed, fix.version AS fixed_in
ORDER BY service_image, package
LIMIT 100
```

Four things this query encodes that a shorter one gets wrong:

- The severity `CASE` is the fallback the product applies. `base_severity` is
  null on some CVEs, and reading it raw silently drops them.
- The `EXISTS` clause pins each package to an image the Signal actually affects.
  `ENRICHES` alone reaches every occurrence of that CVE across the fleet.
- The fix version is `TrivyFix.version`, reached through the package. There is no
  `fixed_version` property on `PackageVersion`; reading one returns null on every
  row, which reads as "nothing is fixable" instead of as an error. The
  `APPLIES_TO` hop back onto `f` is what scopes the fix to *this* CVE: a package
  carries one `SHOULD_UPDATE_TO` edge per fix across all of its CVEs.
- `status IN ['active','accepted']` is the current set the product reads. An
  accepted CVE is one a human signed off on, not an absent one.

`toUpper()` matters because CVE ids are uppercase in the graph and users type
them either way.

If the query returns no rows, the CVE is not present in this tenant's data. Stop and tell the user: "SubImage has no record of `<CVE_ID>` in your environment. Either it does not affect any synced asset, or vulnerability scanning is not enabled for the relevant module. Run `subimage-mcp:improve-subimage-coverage` to check coverage."

If every row comes back `status = 'accepted'`, the CVE **is** present and someone
accepted the risk. Do not use the "no record" wording. Lead with that instead:
the CVE is known, the risk was accepted, and here is where it still sits. Offer
to pull the acceptance rationale as a follow-up. When rows are mixed, report the
active ones as the open work and mention the accepted ones separately rather than
folding them into one count.

Then find where it actually runs. The Signal affects an image; the workloads
running that image are one hop further:

```cypher
MATCH (v:VulnerabilitySignal:Signal)-[:AFFECTS]->(i:Image)<-[:RESOLVED_IMAGE]-(rt)
WHERE v.cve_id = toUpper('<CVE_ID>') AND v.status IN ['active', 'accepted']
  AND (rt:Container OR rt:Function)
  AND (NOT rt:Container OR rt._ont_state = 'running')
RETURN DISTINCT rt.id AS runtime_id, coalesce(rt._ont_name, rt.name) AS runtime_name,
       labels(rt) AS labels, i.id AS image
ORDER BY runtime_id
LIMIT 100
```

A vulnerable image nobody runs is a different conversation from a vulnerable
image on a production container, so keep the two counts distinct in the summary.
`subimageRunCypher` takes no query parameters, so every value above is inlined
as a literal: escape backslashes and single quotes before substituting. ARNs
and fully-qualified GCP/Azure ids can carry either.


### 2. Read fixability from the record

Fix data is already in step 1: each row carries `installed` and `fixed_in`, the
latter from `TrivyFix.version`. A null `fixed_in` means no fix is published; say
so rather than dropping the row. Derive, per package: target fix version, the
affected workloads from the runtime query above, and whether the fix is a package
bump or an image rebuild.

Query further **only** when you need per-package detail step 1 does not carry,
such as every other CVE on the same package:

```cypher
MATCH (p:PackageVersion {name: '<package-name>'})-[:DEPLOYED]->(i:Image)
MATCH (v:VulnerabilitySignal:Signal)-[:AFFECTS]->(i)
MATCH (v)-[:INSTANCE_OF]->(m:CVEMetadata)
      -[:ENRICHES]->(f:TrivyImageFinding:CVE)-[:AFFECTS]->(p)
WHERE v.status IN ['active', 'accepted']
OPTIONAL MATCH (p)-[:SHOULD_UPDATE_TO]->(fix:TrivyFix)-[:APPLIES_TO]->(f)
RETURN DISTINCT m.id AS cve, m.base_severity AS severity, m.base_score AS cvss_score,
       p.version AS installed, fix.version AS fixed_in, v.status AS status
ORDER BY cvss_score DESC
LIMIT 100
```

The third `MATCH` is what makes this "CVEs in this package". Without the
`ENRICHES`/`AFFECTS` join back onto `p`, the query returns every CVE on every
image that happens to also carry the package, which on a busy image is thousands
of unrelated rows.

If nothing is fixable, note that explicitly in the summary; the next action shifts from "patch" to "monitor / mitigate / accept".

### 3. Optional internet enrichment (agent judgment)

SubImage tells you where the CVE lands; the public record tells you how dangerous it is in the wild. Reach for `WebSearch` **only when it would change the recommendation**, not for every CVE. Good triggers:

- The CVE is KEV or critical, and the user is deciding patch priority.
- No fix is available (need mitigations / workarounds from the advisory).
- The CVE is very recent (exploit/PoC landscape still moving).
- The user explicitly asks about real-world exploitability, PoCs, or active exploitation.

When triggered, run at most ~1-3 focused searches (e.g. the NVD/vendor advisory, public PoC / exploit availability, active-exploitation reports). Use `WebFetch` to read a specific advisory URL the search surfaces. Fold the result into the summary as a short **External context** subsection (exploit maturity, notable advisories, mitigations) with source links.

When not triggered, skip it and instead offer it as a one-line follow-up ("Want me to check public exploit / PoC availability for this CVE?"). Never let web text override SubImage's environment-specific data: the graph is authoritative for *what you run*; the web is context for *how bad it is*.

### 4. Optional graph follow-up

Use Cypher only when:

- Steps 1 and 2 point at a resource type whose surroundings you still need to map.
- The user explicitly asks how the CVE could propagate (e.g. "if `lodash` is here, where else is it transitively?").

```
subimageAgentBuildQuery(user_question="<rephrased intent>")
# then:
subimageRunCypher(query="<query returned above>")
```

Skip this step otherwise. Steps 1 and 2 already answer the common questions.

### 5. Summarize

Output in this exact structure. Keep it scannable.

```
# <CVE_ID>

**Severity**: <critical/high/...>  •  **CVSS**: <score>  •  **KEV**: <yes/no>  •  **EPSS**: <score> (<percentile> pct)  •  **Published**: <date>

## What it is
<one-sentence description from the CVE record>

## Where it lands in your environment
- <count> containers (ECS/Kubernetes) across <count> images
- packages affected: <pkg1>, <pkg2>, ...
- top exposed resources: [[entity:Container:<id>|<name>]], [[entity:Image:<id>|<name>]]

## Fixability
- **Patchable**: <count> packages have a fix → <pkg> ≥ <fixed-version>
- **Rebuild required**: <count> images need a base image bump
- **No fix yet**: <count> packages, mitigation only

## External context (only if step 3 ran)
- exploit maturity: <PoC / weaponized / none known> (<source link>)
- mitigations / workarounds: <one line> (<source link>)

## Recommended next action
<one line: patch this image first, bump this package across N services, monitor and revisit, or accept and document>
```

Omit `EPSS` from the header line if the record has no EPSS data (`epss_score` is null). Omit the **External context** section entirely when step 3 did not run.

If KEV is `yes`, prepend a single-line callout above the title:

```
⚠️ KEV: actively exploited in the wild; prioritize over non-KEV criticals.
```

### 6. Offer the pivot to attack-path exploration

This is the most common follow-up question. Do NOT auto-pivot. End the response with:

```
Do you want me to check whether any of these resources sit on a known attack path?
I can check the top exposed resources against the attack-path graph and walk through
the highest-impact ones with you (skill: `subimage-mcp:review-attack-path`).
```

If the user confirms:

- For each of the top 3 to 5 exposed resources, look for paths touching it. A
  resource participates through an `AttackerCapacity`, not through the step's
  `FROM`/`TO` endpoints:
  ```cypher
  MATCH (n {id: '<resource-id>'})-[:REASON|ON]-(c:AttackerCapacity)
        <-[:GRANTS]-(:AttackPathStep)<-[:HAS_STEP]-(a:AttackPath:Signal)
  WHERE coalesce(a.status, 'active') IN ['active', 'accepted']
  RETURN DISTINCT a.id AS id, a.title AS title, a.criticality_score AS criticality,
         a.context_type AS context
  ORDER BY criticality DESC, id
  LIMIT 20
  ```
- For any non-empty result, hand off to `subimage-mcp:review-attack-path` with the most critical path id.
- If all results are empty: "Good news: none of the affected resources are on a known attack path right now." This claim is only safe with the capacity join above; the `FROM|TO` form misses assets that participate as a capacity reason and would make the reassurance false.

This converts a static CVE finding into a live exploitability question, which is the only reason most people ask about CVEs in the first place.

## Anti-patterns

- Reformatting the CVE query output as a markdown table. Forbidden by the chat system prompt for tool data.
- Asking the user to run `subimageRunCypher` themselves. Run it, summarize the result.
- Auto-pivoting to attack paths without confirmation. The user should opt in.
- Listing every affected resource. Top 5 + a count is enough.
- Web-searching every CVE reflexively. The internet step is for KEV/critical/no-fix/exploitability questions; otherwise offer it, don't run it.
- Letting public web text override SubImage data about what you actually run. The graph is authoritative for your environment.

## References

- Tool guide (always loaded by `subimageReadMe`): Domain 3 "Vulnerability Management" and Domain 4 "Attack Path Analysis".
- Companion skill for the pivot: `subimage-mcp:review-attack-path`.
- Internet enrichment: `WebSearch` / `WebFetch` (NVD, vendor advisories, public PoC trackers). Use sparingly per the step-3 triggers.
