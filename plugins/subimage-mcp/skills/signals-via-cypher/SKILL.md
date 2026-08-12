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

**Always filter `status`, and default to `status IN ['active','accepted']`.** That
is the full current set, and it is what the product's own reads use. `active`
alone is the narrower "open work" set: correct for a remediation digest, wrong
for "does this exist", because an accepted Signal is a risk a human looked at and
signed off on, not an absent one. When you include both, return `status` so an
accepted row can be labeled instead of passing as open.

Attack path Signals can carry no `status` property at all, which counts as
active. Filter them with `coalesce(a.status, 'active') IN ['active','accepted']`.

Only current Signals exist, whether active or accepted. There is no inactive
Signal to find, so absence in the graph proves current absence, not that
something never happened.

## Findings and compliance

```text
(:Rule)-[:PRODUCED]->(:Finding:Signal)
(:Finding:Signal)-[:AFFECTS {role: 'primary'}]->(resource)   // may be absent
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

**`AFFECTS` is not guaranteed to exist, so never match it with a plain `MATCH`.**
`'primary'` is the only `role` ever written, but the edge is only merged on a
create or an update: an unchanged Finding never re-merges it, and "unchanged" is
judged by a fingerprint stored on the Finding that does not observe the edge. So
when a resource node is deleted and later re-created under the same id, the
`AFFECTS` edge is gone for good while the Finding stays active. A large standing
fraction of active Findings has no edge at all, and a mandatory match drops every
one of them without a trace.

Three consequences to build queries around:

- **`OPTIONAL MATCH` the asset, always.** Select and `LIMIT` the Findings first,
  then attach the asset. Putting the asset in the driving `MATCH` also makes the
  `LIMIT` count joined rows instead of Findings.
- **`fields_json` is the fallback identity.** The rule spec requires an
  asset-id field, so the affected asset's id is always in there even when the
  edge is not. Return `fields_json` (and `extra_json`) alongside `n.id` so an
  edgeless row is still actionable. The key name is not standardized, so read it
  yourself rather than trying to index into the JSON in Cypher.
- **`display_name` is always populated**, so an edgeless Finding still names its
  asset in prose even when `n` is null.

None of the product's own finding reads traverse `AFFECTS`; they return Finding
properties only. Requiring the edge is stricter than the product, not equivalent
to it.

The finding examples below filter `active` alone, which is a deliberate
narrowing: they answer "what is open". Note that this is narrower than the
product, whose finding reads return `['active','accepted']` and flag the accepted
ones. Widen when the question is "does this asset fail rule X" rather than "what
is on my plate".

Findings for one rule:

```cypher
MATCH (r:Rule {id: 'object_storage_public'})-[:PRODUCED]->(f:Finding:Signal)
WHERE f.status = 'active'
WITH f
ORDER BY f.display_name
LIMIT 100
OPTIONAL MATCH (f)-[:AFFECTS {role: 'primary'}]->(n)
RETURN f.id AS id, f.display_name AS asset_name, n.id AS asset_id,
       labels(n) AS asset_labels, f.fields_json AS fields_json
ORDER BY asset_name
```

The `LIMIT` sits on the Findings, before the asset is attached, so it caps
Findings rather than joined rows. A null `asset_id` is an edgeless Finding, not an
absent one: fall back to `fields_json` for its asset id.

Everything failing on one asset:

```cypher
MATCH (r:Rule)-[:PRODUCED]->(f:Finding:Signal)
WHERE f.status = 'active'
  AND (EXISTS { (f)-[:AFFECTS {role: 'primary'}]->({id: 'i-eval-public'}) }
       OR f.fields_json CONTAINS '"i-eval-public"')
RETURN r.id AS rule, r.name AS rule_name, f.id AS finding_id,
       f.display_name AS asset_name
ORDER BY rule
LIMIT 100
```

Here the asset is the filter, not a returned column, so it cannot be optional.
The `fields_json` arm is what keeps edgeless Findings for this asset in the
result; without it the query answers "what fails on this asset **and still has
its edge**", which reads as a clean asset when it is not. Quote the id inside the
`CONTAINS` so a short id does not match a longer one by prefix.

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
(:PackageVersion)-[:SHOULD_UPDATE_TO]->(:TrivyFix)-[:APPLIES_TO]->(:TrivyImageFinding)
```

A Signal is one `(cve_id, service_image)` pair, **not** one CVE: the same CVE on
two services is two Signals. Count `DISTINCT v.cve_id` when the user asks "how
many CVEs" and count Signals when they ask "how many vulnerabilities".

| Node | Fields |
|---|---|
| `:VulnerabilitySignal:Signal` | `cve_id`, `service_image`, `status`, `first_seen`, `sources`, `public_exploit`, `exploit_maturity` |
| `:CVEMetadata` | `id` (the CVE id), `title`, `description`, `base_severity`, `base_score`, `vector_string`, `cvss_version`, `published_date`, `is_kev`, `cisa_exploit_add`, `epss_score`, `epss_percentile` |
| `:PackageVersion` | `name`, `version`, `type`, `purl` |
| `:TrivyFix` | `id`, `version` (the fixed version string) |

There is **no** `fixed_version` on `PackageVersion`. Reading one returns null on
every row, which reads as "nothing is fixable" rather than as an error. The fix
version lives on `TrivyFix.version`.

Severity lives on `CVEMetadata`, not on the Signal, and `base_severity` can be
null. Derive it the way the product does:

```cypher
MATCH (v:VulnerabilitySignal:Signal)-[:INSTANCE_OF]->(m:CVEMetadata)
WHERE v.status IN ['active', 'accepted']
RETURN v.cve_id AS cve, v.service_image AS service_image, v.status AS status,
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
WHERE v.status IN ['active', 'accepted']
  AND (coalesce(m.is_kev, false) OR coalesce(v.public_exploit, false))
RETURN DISTINCT v.cve_id AS cve, m.base_score AS cvss_score, v.status AS status,
       coalesce(m.is_kev, false) AS kev, m.cisa_exploit_add AS kev_date
ORDER BY cvss_score DESC
LIMIT 100
```

Where a CVE actually runs:

```cypher
MATCH (v:VulnerabilitySignal:Signal)-[:AFFECTS]->(i:Image)<-[:RESOLVED_IMAGE]-(rt)
WHERE v.cve_id = toUpper('cve-2026-11111')
  AND v.status IN ['active', 'accepted']
  AND (rt:Container OR rt:Function)
  AND (NOT rt:Container OR rt._ont_state = 'running')
RETURN DISTINCT rt.id AS runtime_id, coalesce(rt._ont_name, rt.name) AS name,
       labels(rt) AS labels, i.id AS image, v.status AS status
LIMIT 100
```

Fixability, per package:

```cypher
MATCH (v:VulnerabilitySignal:Signal)-[:INSTANCE_OF]->(m:CVEMetadata)
      -[:ENRICHES]->(f:TrivyImageFinding:CVE)-[:AFFECTS]->(p:PackageVersion)
WHERE v.status IN ['active', 'accepted']
  AND EXISTS { (v)-[:AFFECTS]->(:Image)<-[:DEPLOYED]-(p) }
OPTIONAL MATCH (p)-[:SHOULD_UPDATE_TO]->(fix:TrivyFix)-[:APPLIES_TO]->(f)
RETURN DISTINCT v.cve_id AS cve, v.status AS status, p.name AS package,
       p.version AS installed, fix.version AS fixed_in
ORDER BY package
LIMIT 100
```

Two joins here are load-bearing, not refinements.

The `EXISTS` clause: `ENRICHES` reaches every package occurrence of that CVE
anywhere in the fleet, so without it each Signal is reported against packages
from images it does not affect. Pin the package to an image the Signal actually
affects, through `DEPLOYED`.

The `APPLIES_TO` hop back onto `f`: a `PackageVersion` carries one
`SHOULD_UPDATE_TO` edge per fix across **all** of its CVEs. Walk to `TrivyFix`
without closing the triangle back onto this CVE's finding and you report some
other CVE's fix version as this one's. Note the direction: `APPLIES_TO` points at
the finding, not at the package.

A null `fixed_in` means no fix is published; say so rather than omitting the row.

## Attack paths

```text
(:AttackPath:Signal)-[:HAS_STEP {position}]->(:AttackPathStep)
(:AttackPath:Signal)-[:FOR_RULE]->(:Rule)
(:AttackPathStep)-[:FROM]->(resource)
(:AttackPathStep)-[:TO]->(resource)
(:AttackPathStep)-[:GRANTS]->(:AttackerCapacity)
(:AttackerCapacity)-[:ON]->(resource)
(:AttackerCapacity)-[:REASON]->(resource)
```

| Node | Fields |
|---|---|
| `:AttackPath:Signal` | `title`, `status`, `criticality_score`, `impact_score`, `likelihood_score`, `difficulty_score`, `context_type` (`default`, `rule`, `scenario`, `preview`), `context_id` |
| `:AttackPathStep` | `position` (zero-based), `transition_id`, `capability`, `description`, `templated_description` |
| `:AttackerCapacity` | `id`, `type`, `transition_id`, `context` |

**A resource participates in a path through an `AttackerCapacity`, not through
`FROM`/`TO`.** `FROM` and `TO` are derived edges carrying the endpoints a step
*displays*: `TO` is built from the step's own capacity, `FROM` from the previous
step's. A resource can be the `REASON` a capacity holds without ever being an
endpoint. So the two joins are not interchangeable:

- **rendering** a path you already have: `FROM`/`TO`, which is what the step shows;
- **discovering** which paths touch an asset: `REASON|ON` to the capacity, then
  `GRANTS` back to the step. This is what the product runs.

`context_type = 'default'` is the environment-wide set; `rule`, `scenario`, and
`preview` paths exist only inside their context. Return `context_type` as a
column rather than filtering it by default: the product's asset lookup applies no
such filter, and filtering silently hides rule-context paths. Narrow to
`'default'` when the user asked for the environment-wide picture, or when the
same path is coming back once per context.

Listing:

```cypher
MATCH (a:AttackPath:Signal)
WHERE coalesce(a.status, 'active') IN ['active', 'accepted']
  AND a.context_type = 'default'
RETURN a.id AS id, a.title AS title, a.criticality_score AS criticality,
       a.impact_score AS impact, a.likelihood_score AS likelihood,
       coalesce(a.status, 'active') AS status
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

Paths touching one asset:

```cypher
MATCH (n {id: 'i-eval-public'})-[:REASON|ON]-(c:AttackerCapacity)
      <-[:GRANTS]-(:AttackPathStep)<-[:HAS_STEP]-(a:AttackPath:Signal)
WHERE coalesce(a.status, 'active') IN ['active', 'accepted']
RETURN DISTINCT a.id AS id, a.title AS title, a.criticality_score AS criticality,
       a.context_type AS context, coalesce(a.status, 'active') AS status
ORDER BY criticality DESC, id
LIMIT 20
```

The `REASON|ON` hop is deliberately undirected, matching the product. Writes only
ever go `(capacity)-[:ON|REASON]->(resource)`, so direction changes no results; it
just keeps the pattern robust. Do not rewrite this as `FROM|TO` on the step: that
form reports "no path" for any asset that participates only as a capacity reason.

Prefer `s.description`, which is the rendered step text.
`templated_description` still holds unrendered double-brace placeholders and is
not for display.

## Rules

- One self-contained read-only statement per `subimageRunCypher` call. No `//`
  comments, no parameters, no semicolon.
- Always filter `status`, defaulting to `['active','accepted']`.
- **`subimageRunCypher` returns at most 100 rows, whatever `LIMIT` you write.**
  The server takes `min(its cap, your limit)`, so you can lower the ceiling but
  never raise it. It also returns `total_count`, the true size. Size any query
  whose shape can exceed 100 rows to fit under it, and when the page is partial,
  say so and quote `total_count` rather than implying the page is the whole set.
- A query that fans out over N groups and wants k rows each must keep N times k
  under 100, and must take its per-group slice in a `CALL (x) { ... LIMIT k }`
  subquery. A single global `LIMIT` spends the whole budget on whichever group
  sorts first and returns nothing for the rest.
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
  `TO`, `PRODUCED`, or the `GRANTS`/`REASON`/`ON` chain for attack paths. There
  is no `tenant_id` property on a Signal; scope by traversing from the affected
  resource to its `:Tenant`.

## Anti-patterns

- Counting Findings when the user asked how many assets fail: one asset can carry
  several Findings from one rule. Read `Rule.failing_assets`.
- Counting Vulnerability Signals when the user asked how many CVEs: the Signal is
  per `(cve, service_image)`.
- Answering "has this ever been an issue" from the graph. Only active Signals
  exist there; that question belongs to the history tools.
- Reporting a severity read straight off `m.base_severity` without the score
  fallback: it is null for some CVEs and the answer silently drops them.
- Matching a Finding's `AFFECTS` with a plain `MATCH`. The edge is frequently
  missing on active Findings, so this drops them with no sign in the result. Use
  `OPTIONAL MATCH` and fall back to `fields_json`.
- Putting the asset in the driving `MATCH` of a limited findings query. The
  `LIMIT` then counts joined rows, not Findings.
- Reading a fix version off `PackageVersion`. The property does not exist, so
  every row comes back null and the answer becomes "nothing is fixable".
- Associating a package with a CVE because both sit on the same image. The join
  runs through `TrivyImageFinding`; co-location alone pairs every package on an
  image with every CVE on it.
- Finding the paths that touch an asset by matching the step's `FROM`/`TO`
  endpoints. Go through the `AttackerCapacity`.
- Re-running the query with a different limit to "check" a result that already
  answered the question.

## Output

Answer in prose or a short list, not a dump of raw rows. Lead with the count and
the worst offenders, name them, and tag entities so they are clickable. When the
result hit the `LIMIT`, say so and give the total from one follow-up `count()`
query rather than implying the page is the whole set.

## Verification

- The query filtered `status`, and narrowed to `active` alone only on purpose.
- The query cannot produce more than 100 rows, or the answer quotes
  `total_count` instead of presenting the page as the whole set.
- Any Finding-to-asset traversal is an `OPTIONAL MATCH` applied after the
  Findings were selected and limited, and the answer treats a null asset as an
  edgeless Finding rather than dropping the row.
- One `subimageRunCypher` call answered it; two means the first was wrong or a
  count follow-up was genuinely needed.
- A severity or KEV claim came from `CVEMetadata`, and a fix version from
  `TrivyFix` reached through this CVE's own finding, not from the Signal alone.

## References

- `subimage-mcp:build-cypher-query` for relational questions that leave the
  Signal layer: ownership, reachability between arbitrary resource types.
- `subimage-mcp:inventory-via-cypher` for flat listings of one resource type.
- `subimage-mcp:investigate-cve`, `investigate-container`,
  `investigate-public-exposure`, `review-attack-path` for the per-domain
  investigation flows that start from one entity.
