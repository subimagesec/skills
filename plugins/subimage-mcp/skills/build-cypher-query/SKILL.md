---
name: build-cypher-query
description: Build and run a Cypher query against the SubImage Neo4j graph only when the user request requires graph traversal, relationships, identity/access, reachability, ownership, blast radius, root cause, or absence validation, and no dedicated MCP tool can answer directly.
---

# Build a Cypher query

Produce a correct Cypher query that answers the user's question, in as few tool calls as possible, using only tools the SubImage MCP server actually exposes.

## Hard entry gate

- Before any schema discovery, model-query lookup, or Cypher execution, check whether a dedicated SubImage MCP tool can answer the user's exact question. If yes, do not use this skill.
- If there is already a non-empty result from Issues, Vulnerabilities, Inventory, Compliance, or Attack Paths that directly answers the question: stop and answer from that result. Do not use this skill to validate, enrich, double-check, or improve confidence.
- "More graph detail might exist", "validate with Cypher", and "dedicated tool result was non-empty" are not sufficient reasons. This skill is blocked unless the user explicitly asks for graph relationships, root cause, blast radius, reachability, ownership, permissions, or absence validation.

## When to use

✅ The answer requires graph traversal, joins, relationships, identity/access, reachability, blast radius, ownership, root cause, transitive reasoning, or absence validation.
✅ A graph-shaped question like "which EC2 instances have public IPs and an IAM role that can assume admin?"
✅ A dedicated MCP tool returned **empty** results and absence must be validated.
✅ A dedicated MCP tool returned non-empty results but is missing required fields for the user's exact question.
✅ The answer requires joining graph entities across domains and no dedicated MCP tool can answer directly.

❌ A dedicated MCP tool answers the question directly.
❌ Remediation, prioritization, action items, vulnerability lookup, package fixability, framework findings, inventory listing, or attack-path enumeration where the matching dedicated tool returned non-empty results.
❌ Only trying to validate, enrich, or double-check a sufficient dedicated-tool result.
❌ The user has a known-good Cypher query in hand. Skip this skill and run `subimageRunCypher` directly.

## Public MCP tools used

Only these are addressed by this skill; nothing else.

| Tool | Purpose |
|---|---|
| `searchModelQueries(labels=[...])` | Looks up previously cached "model queries" for a set of labels. Cheap, often returns a ready-made query you can adapt. |
| `saveModelQuery(...)` | Caches a query you authored from scratch so future questions of the same shape are one tool call away. Call only after a successful execution returned meaningful rows. |
| `subimageListModules()` | Confirms which modules are synced before querying their labels. |
| `subimageListModuleSchemaNodes(module=...)` | Discovers candidate labels for a given module when you don't know them. |
| `subimageGetNodesSchema(node_names=[...])` | Returns the validated label, property, and relationship surface for a list of labels. |
| `subimageGetLabelStats(labels=[...])` | Returns cardinality per label; check when you suspect a label is high-cardinality (>10 000 nodes) and your query does not filter early. |
| `subimageRunCypher(query)` | Executes one Cypher statement. Streams to the UI as an interactive table. |

## Workflow

The workflow has four sequential steps. Step 1 has two variants depending on whether the user's question already names the labels; steps 2, 3, and 4 are the same in both cases.

### Step 1 — Resolve labels

**Fast path (labels obvious from the question):** when the user's wording maps directly to labels (`EC2`, `IAMRole`, `User`, `Container`, `Vulnerability`, ...), skip discovery and go straight to step 2.

**Slow path (labels ambiguous):** when the user's wording does not map cleanly to labels (e.g. "find anything exposed to the public"):

1. `subimageListModules()` to confirm which modules are synced.
2. `subimageListModuleSchemaNodes(module=<m>)` on the modules that could host the answer, to enumerate candidate labels.

Once you have a label shortlist, continue to step 2.

### Step 2 — Look up examples and schema in parallel

With the labels in hand, fire these calls on a single turn:

- `searchModelQueries(labels=[...])` — looks up cached example queries for these labels. If a hit matches the question's shape, adapt it instead of authoring from scratch. (This is **not** label discovery — it requires the labels as input.)
- `subimageGetNodesSchema(node_names=["LabelA", "LabelB", ...])` — batches every label into one call. Returns the validated properties and relationships, including authoritative relationship examples and direction. Resolves both primary labels and ontology aliases.
- `subimageGetLabelStats(labels=[...])` — only if you suspect a label is high-cardinality and your draft will not filter on it early.

Then either adapt the cached query or author one from the schema. Before writing Cypher, extract the exact relationship pattern from the schema examples for every hop. Apply the **Final query rules** below.

### Step 3 — Optional probe (at most one)

If after step 2 you are still uncertain about a property's actual values, the path's shape, relationship direction, or whether matching rows exist, run **one** probe with `subimageRunCypher` using `LIMIT 5` or `COUNT(*)`. Prefer `toLower(...) CONTAINS ...` for text discovery.

For relationship-direction uncertainty, keep the probe bounded and typed. Use the same validated labels and relationship type in an undirected diagnostic pattern, return `labels(startNode(r))`, `type(r)`, `labels(endNode(r))`, and key IDs, then correct the final query to the directed schema shape. Do not leave the final query undirected unless direction is genuinely irrelevant and the query deduplicates rows.

Do not stack speculative probes; refine labels or filters instead.

Skip this step entirely if step 2 left no ambiguity.

### Step 4 — Execute and cache

Do not run the final query if a dedicated non-Cypher tool has already returned a sufficient non-empty answer during this turn.

1. Run the final query with `subimageRunCypher(query=<final>)`. It streams to the UI as an interactive table; summarize the rows for the user, do not reprint the table.
2. If you authored the query from scratch (no `searchModelQueries` hit) and execution returned meaningful rows, call `saveModelQuery` with a clear description and the labels involved so future questions of the same shape can skip the authoring step. Do not cache a query that only passed syntax: cache after the result is confirmed useful.

## Schema rules

- Never invent node labels, property names, or relationship types. Use only what `subimageListModuleSchemaNodes` or `subimageGetNodesSchema` returned.
- Relationship direction is schema. Use the directed relationship examples from `subimageGetNodesSchema`; do not infer direction from relationship names, user wording, or prose like "to Label" in a relationship list.
- Ontology labels (`User`, `Container`, `Image`, `ComputeInstance`, `Database`, `Group`, `Role`, ...) normalize identity, not edges or every property. `subimageGetNodesSchema` returns one section per underlying primary label; review them all, and prefer the provider-native property over the `_ont_*` projection when both are listed (the ontology projection may be null on a tenant even when the provider-native field is populated).
- If the user requests a property or entity that does not exist in the schema, stop and tell them inline. Do not guess.

## Final query rules

The query passed to `subimageRunCypher` must:

- be read-only. Only MATCH, OPTIONAL MATCH, WHERE, WITH, UNWIND, RETURN, ORDER BY, LIMIT, and read-only procedures (e.g. `apoc.meta.*`) are allowed. Never CREATE, MERGE, DELETE, SET, REMOVE, DROP, or any writing/virtual APOC procedure (`apoc.create.*`, including `apoc.create.vNode` / `apoc.create.vRelationship`): the graph role rejects them and the query will fail.
- use only validated labels, properties, and relationships,
- give every node variable at least one label (no bare `MATCH (n)`); unlabeled scans touch the entire graph and time out,
- give every relationship pattern a variable and an explicit type (e.g. `(a)-[r1:RELATES_TO]->(b)`; never `(a)-[:RELATES_TO]->(b)` or `(a)-[]->(b)`),
- use the schema-declared direction for every relationship. If a cached model query or draft uses the opposite arrow, correct it before execution and note the correction in prose if useful.
- include `LIMIT`, default `LIMIT 100` unless the user asks otherwise,
- use `OPTIONAL MATCH` only when missing relationships should still preserve rows,
- never use unbounded variable-length paths.

Performance:

- Filter early on high-cardinality labels. `LIMIT` only caps output rows; it does not reduce compute time. Add `WHERE` filters to narrow the scan before any traversal or aggregation.
- Avoid disconnected `MATCH` patterns without a shared variable; they create a cartesian product.

Simplify before running:

- remove unnecessary hops, `WITH`, `OPTIONAL MATCH`,
- prefer direct properties over extra traversal,

## Execution rules

- Each `subimageRunCypher` call must contain exactly one executable Cypher statement.
- Never include `//` comments in the query string passed to `subimageRunCypher`. Keep any explanatory notes in your prose, not in the query.
- Do not run a redundant `COUNT(*)` after the final query "to verify it parses". `subimageRunCypher` validates syntax on the way in.
- If you cannot build a valid query (missing schema, ambiguous question, no matching data after one probe), do not run a speculative query. Explain to the user what is missing and what they could clarify.

## Anti-patterns

- Reframing the user's question and immediately running `subimageRunCypher` with a query authored from memory. Always ground labels via `subimageGetNodesSchema` (or a `searchModelQueries` hit) first.
- Reversing a relationship because the type name or relationship-list prose reads naturally in the other direction. Schema examples are authoritative for direction.
- Using undirected relationships as the final answer to avoid choosing direction. Undirected matches traverse both ways, can double-count rows, and can hide modeling mistakes.
- Calling `saveModelQuery` on a query that only passed syntax. Cache only after a real execution returned useful rows.
- Reformatting `subimageRunCypher` results as a markdown table. The tool streams an interactive table; summarize, do not duplicate.
- Looping speculative probes ("try this, no, try that"). One probe with `LIMIT 5` or `COUNT(*)`, then commit.
- Pre-loading the full schema "just in case" via `subimageListModuleSchemaNodes` on every module. Only enumerate modules when the labels are genuinely unknown.
- Calling `subimageGetLabelStats` for every query. Only check when a label is plausibly large and your query does not already filter it.
- Building virtual nodes or relationships (`apoc.create.vNode` / `apoc.create.vRelationship`) to "visualize" a derived relationship.

## Special cases

- Cross-provider questions: check for unified ontology / common node types before using provider-specific labels.
- Admin access questions: check both direct and indirect privilege paths, including managed policies, inline policies, wildcard `Allow` permissions, and assume-role chains.
- Use `UNION` and `RETURN DISTINCT` only when required.

## References

- Canonical doc: https://app.subimage.io/docs/agents/connect_via_mcp
- The MCP tool selection guide is auto-loaded by the first call to `subimageReadMe`; rely on it for tool-to-domain mapping.
