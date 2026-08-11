---
name: signals-via-cypher
description: Answer questions about findings, compliance posture, vulnerabilities, CVEs, packages, and attack paths by querying the Signal nodes that hold them in Neo4j. Use when the user asks what is failing a rule, how a framework scores, which CVEs or packages are present, what is exploitable or KEV-listed, or how an attacker could reach an asset.
---

# Security Signals via Cypher

## What this does

SubImage derives its security observations from the graph and stores the active
ones back in it as `Signal` nodes. A finding, a vulnerability, and an attack path
are all `:Signal` with one domain label, so "which buckets fail the public-access
rule", "which CVEs are KEV-listed", and "how does an attacker reach the admin
role" are each one Cypher query on a shape this skill gives you.

## Hard entry gate

Load this skill for the current state of findings, compliance rule results,
vulnerabilities, CVEs, packages, or attack paths.

Do NOT load it for:

- **history**: "when did this change", "how many last month", "is our score
  improving". The graph holds only currently active Signals. Use
  `subimageGetRuleHistory` and `subimageGetFrameworkHistory`.
- **what is configured**: which rules or frameworks exist, are enabled, or are
  tenant-authored. Those join operator state Cypher cannot read. Use
  `subimageListRules`, `subimageListCustomRules`, `subimageListFrameworks`.
- **remediation work**: issues and action items (`subimageListIssues`,
  `subimageGetIssue`, `subimageListVulnerabilityActionItems`).
- **flat resource inventory** of one resource type: use `inventory-via-cypher`.
- **what-if scenario modeling**: `subimageGetScenarioCapabilities`, then
  `subimageCreateAttackPathScenario`.

**The shapes below are authoritative.** Do not call `subimageListModules`,
`subimageListModuleSchemaNodes`, `subimageGetNodesSchema`, or
`subimageSearchModelQueries` before querying them; go straight to
`subimageRunCypher`.

## Required inputs

- **the domain**: finding/compliance, vulnerability/package, or attack path.
- **any filter value** the question implies: a rule id, a framework slug, a CVE
  id, a package name, an asset name. Ask only when the question names a filter
  without a value.

Resolve a rule id or framework slug with `subimageListRules` /
`subimageListFrameworks` first when the user named one in prose; those catalogs
are the authority on what exists.

## Prerequisites

`subimageRunCypher` (read-only). Nothing else.

## The Signal contract

Every Signal carries the shared `Signal` label plus one domain label, and these
shared properties:

| Property | Meaning |
|---|---|
| `id` | deterministic signal id |
| `signal_type` | `finding`, `vulnerability`, or `attack-path` |
| `status` | `active` or `accepted`; accepted means a human accepted the risk |
| `first_seen` | start of the current active occurrence |
| `sources` | list of Cartography module names of the participating resources |

**Always filter `status`.** `status = 'active'` is what "open" means;
`status IN ['active','accepted']` is the full current set. An accepted Signal is
still in the graph and silently inflates a count that meant "open".

Only active Signals exist. There is no inactive Signal to find, so absence in
the graph proves current absence, not that something never happened.

## Findings and compliance

```text
(:Rule)-[:PRODUCED]->(:Finding:Signal)-[:AFFECTS {role}]->(resource)
(:Rule)-[:MAPS_TO]->(:Framework)
```

| Node | Fields |
|---|---|
| `:Finding:Signal` | `display_name`, `status`, `first_seen`, `sources`, `fact_id`, `fields_json`, `extra_json` |
| `:Rule` | `id`, `name`, `state`, `tags`, `custom`, `catalog_visible`, `total_assets`, `passing_assets`, `failing_assets` |
| `:Framework` | `id` (e.g. `cis:aws`, `soc2:tsc`, `iso:27001`), `state` |

`Rule.failing_assets` / `passing_assets` / `total_assets` are the compliance
counters the sync already computed. Use them for "how are we doing on X" instead
of counting Findings, which counts observations rather than assets.

`fields_json` and `extra_json` are canonical JSON strings, not maps: return them
whole and read them yourself rather than trying to index into them in Cypher.

Findings for one rule:

```cypher
MATCH (r:Rule {id: 'object_storage_public'})-[:PRODUCED]->(f:Finding:Signal)-[:AFFECTS]->(n)
WHERE f.status = 'active'
RETURN f.id AS id, f.display_name AS asset_name, n.id AS asset_id, labels(n) AS asset_labels
ORDER BY asset_name
LIMIT 100
```

Everything failing on one asset:

```cypher
MATCH (r:Rule)-[:PRODUCED]->(f:Finding:Signal)-[:AFFECTS]->(n {id: 'i-eval-public'})
WHERE f.status = 'active'
RETURN r.id AS rule, r.name AS rule_name, f.id AS finding_id
ORDER BY rule
LIMIT 100
```

Posture for one framework:

```cypher
MATCH (r:Rule)-[:MAPS_TO]->(:Framework {id: 'cis:aws'})
RETURN r.id AS rule, r.name AS name, r.failing_assets AS failing, r.total_assets AS total
ORDER BY failing DESC, rule
LIMIT 100
```

Noisiest rules:

```cypher
MATCH (r:Rule)-[:PRODUCED]->(f:Finding:Signal)
WHERE f.status = 'active'
RETURN r.id AS rule, r.name AS name, count(f) AS findings
ORDER BY findings DESC, rule
LIMIT 20
```

## Vulnerabilities, CVEs and packages

```text
(:VulnerabilitySignal:Signal)-[:INSTANCE_OF]->(:CVEMetadata)
(:VulnerabilitySignal:Signal)-[:AFFECTS]->(:Image)<-[:RESOLVED_IMAGE]-(:Container|:Function)
(:CVEMetadata)-[:ENRICHES]->(:TrivyImageFinding:CVE)-[:AFFECTS]->(:PackageVersion)
(:PackageVersion)-[:DEPLOYED]->(:Image)
```

A Signal is one `(cve_id, service_image)` pair, **not** one CVE: the same CVE on
two services is two Signals. Count `DISTINCT v.cve_id` when the user asks "how
many CVEs" and count Signals when they ask "how many vulnerabilities".

| Node | Fields |
|---|---|
| `:VulnerabilitySignal:Signal` | `cve_id`, `service_image`, `status`, `first_seen`, `sources`, `public_exploit`, `exploit_maturity` |
| `:CVEMetadata` | `id` (the CVE id), `title`, `description`, `base_severity`, `base_score`, `vector_string`, `cvss_version`, `published_date`, `is_kev`, `cisa_exploit_add`, `epss_score`, `epss_percentile` |
| `:PackageVersion` | `name`, `version`, `fixed_version` |

Severity lives on `CVEMetadata`, not on the Signal, and `base_severity` can be
null. Derive it the way the product does:

```cypher
MATCH (v:VulnerabilitySignal:Signal)-[:INSTANCE_OF]->(m:CVEMetadata)
WHERE v.status = 'active'
RETURN v.cve_id AS cve, v.service_image AS service_image,
       CASE
         WHEN m.base_severity IS NOT NULL THEN toUpper(m.base_severity)
         WHEN m.base_score >= 9 THEN 'CRITICAL'
         WHEN m.base_score >= 7 THEN 'HIGH'
         WHEN m.base_score >= 4 THEN 'MEDIUM'
         WHEN m.base_score > 0 THEN 'LOW'
         ELSE 'UNKNOWN'
       END AS severity,
       m.base_score AS cvss_score
ORDER BY cvss_score DESC
LIMIT 100
```

Exploited means KEV **or** a known public exploit:

```cypher
MATCH (v:VulnerabilitySignal:Signal)-[:INSTANCE_OF]->(m:CVEMetadata)
WHERE v.status = 'active'
  AND (coalesce(m.is_kev, false) OR coalesce(v.public_exploit, false))
RETURN DISTINCT v.cve_id AS cve, m.base_score AS cvss_score,
       coalesce(m.is_kev, false) AS kev, m.cisa_exploit_add AS kev_date
ORDER BY cvss_score DESC
LIMIT 100
```

Where a CVE actually runs:

```cypher
MATCH (v:VulnerabilitySignal:Signal {cve_id: 'CVE-2026-11111'})-[:AFFECTS]->(i:Image)
      <-[:RESOLVED_IMAGE]-(rt)
WHERE v.status = 'active'
  AND (rt:Container OR rt:Function)
  AND (NOT rt:Container OR rt._ont_state = 'running')
RETURN DISTINCT rt.id AS runtime_id, coalesce(rt._ont_name, rt.name) AS name,
       labels(rt) AS labels, i.id AS image
LIMIT 100
```

Fixability, per package:

```cypher
MATCH (v:VulnerabilitySignal:Signal)-[:INSTANCE_OF]->(m:CVEMetadata)
      -[:ENRICHES]->(:TrivyImageFinding:CVE)-[:AFFECTS]->(p:PackageVersion)
WHERE v.status = 'active'
RETURN DISTINCT v.cve_id AS cve, p.name AS package, p.version AS installed,
       p.fixed_version AS fixed_in
ORDER BY package
LIMIT 100
```

A null `fixed_version` means no fix is published; say so rather than omitting the
row.

## Attack paths

```text
(:AttackPath:Signal)-[:HAS_STEP {position}]->(:AttackPathStep)
(:AttackPath:Signal)-[:FOR_RULE]->(:Rule)
(:AttackPathStep)-[:FROM]->(resource)
(:AttackPathStep)-[:TO]->(resource)
(:AttackPathStep)-[:GRANTS]->(:AttackerCapacity)
```

| Node | Fields |
|---|---|
| `:AttackPath:Signal` | `title`, `status`, `criticality_score`, `impact_score`, `likelihood_score`, `difficulty_score`, `context_type` (`default`, `rule`, `scenario`), `context_id` |
| `:AttackPathStep` | `position` (zero-based), `transition_id`, `capability`, `description`, `templated_description` |

`context_type = 'default'` is the environment-wide set; a `rule` or `scenario`
path exists only inside that context. Filter to `'default'` unless the user asked
about a rule context or a saved scenario, or the same path appears several times.

Listing:

```cypher
MATCH (a:AttackPath:Signal)
WHERE a.status = 'active' AND a.context_type = 'default'
RETURN a.id AS id, a.title AS title, a.criticality_score AS criticality,
       a.impact_score AS impact, a.likelihood_score AS likelihood
ORDER BY criticality DESC
LIMIT 20
```

Steps of one path, in order:

```cypher
MATCH (a:AttackPath:Signal {id: '<path id>'})-[h:HAS_STEP]->(s:AttackPathStep)
OPTIONAL MATCH (s)-[:FROM]->(src)
OPTIONAL MATCH (s)-[:TO]->(dst)
RETURN h.position AS position, s.transition_id AS transition, s.capability AS capability,
       s.description AS description,
       collect(DISTINCT src.id) AS from_ids, collect(DISTINCT dst.id) AS to_ids
ORDER BY position
```

Paths touching one asset (either end of any step):

```cypher
MATCH (a:AttackPath:Signal)-[:HAS_STEP]->(s:AttackPathStep)-[:FROM|TO]->(n {id: 'i-eval-public'})
WHERE a.status = 'active' AND a.context_type = 'default'
RETURN DISTINCT a.id AS id, a.title AS title, a.criticality_score AS criticality
ORDER BY criticality DESC
LIMIT 20
```

Prefer `s.description`, which is the rendered step text.
`templated_description` still holds `{{...}}` placeholders and is not for display.

## Rules

- One self-contained read-only statement per `subimageRunCypher` call. No `//`
  comments, no parameters, no semicolon.
- Always filter `status`.
- Always `LIMIT` a listing whose size grows with the environment (100 unless
  asked for more). A result bounded by construction, such as the ordered steps
  of one attack path, takes no `LIMIT`: capping it would truncate the chain
  mid-way and the partial answer would read as the whole one.
- Return the Signal's `id` on every query that returns one row per Signal, so
  the answer can be tagged and drilled into. An aggregate returns the grouping
  key and the count instead.
- `subimageRunCypher` takes no query parameters, so any value from the user is
  inlined as a literal. Escape backslashes and single quotes before inlining.
- A CVE id is uppercase in the graph; use `toUpper()` on a user-supplied one
  rather than matching it verbatim.
- Do not join a Signal to a resource through anything but `AFFECTS`, `FROM`,
  `TO`, or `PRODUCED`. There is no `tenant_id` property on a Signal; scope by
  traversing from the affected resource to its `:Tenant`.

## Anti-patterns

- Counting Findings when the user asked how many assets fail: one asset can carry
  several Findings from one rule. Read `Rule.failing_assets`.
- Counting Vulnerability Signals when the user asked how many CVEs: the Signal is
  per `(cve, service_image)`.
- Answering "has this ever been an issue" from the graph. Only active Signals
  exist there; that question belongs to the history tools.
- Reporting a severity read straight off `m.base_severity` without the score
  fallback: it is null for some CVEs and the answer silently drops them.
- Re-running the query with a different limit to "check" a result that already
  answered the question.

## Output

Answer in prose or a short list, not a dump of raw rows. Lead with the count and
the worst offenders, name them, and tag entities so they are clickable. When the
result hit the `LIMIT`, say so and give the total from one follow-up `count()`
query rather than implying the page is the whole set.

## Verification

- The query filtered `status`.
- One `subimageRunCypher` call answered it; two means the first was wrong or a
  count follow-up was genuinely needed.
- A severity, KEV, or fixability claim came from `CVEMetadata` or
  `PackageVersion`, not from the Signal alone.

## References

- `subimage-mcp:build-cypher-query` for relational questions that leave the
  Signal layer: ownership, reachability between arbitrary resource types.
- `subimage-mcp:inventory-via-cypher` for flat listings of one resource type.
- `subimage-mcp:investigate-cve`, `investigate-container`,
  `investigate-public-exposure`, `review-attack-path` for the per-domain
  investigation flows that start from one entity.
