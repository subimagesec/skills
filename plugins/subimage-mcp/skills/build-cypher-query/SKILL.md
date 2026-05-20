---
name: build-cypher-query
description: Build and run a verified Cypher query against the SubImage Neo4j graph. Use when the user asks a question whose answer requires graph traversal (cross-resource, identity, attack-surface, ownership) and you need to construct a query, not re-run a known one. Defaults to the agent-delegated builder; falls back to authoring by hand against the public schema tools when fine control is needed.
---

# Build a Cypher query

Produce a correct Cypher query that answers the user's question, in as few tool calls as possible, using only tools the SubImage MCP server actually exposes.

## When to use

✅ The answer requires joining nodes the user can name informally (services, accounts, users, vulnerabilities, attack paths).
✅ The user pastes a question like "which EC2 instances have public IPs and an IAM role that can assume admin?" and wants the underlying data.
✅ You already tried `subimageListModules` / `subimageGetVulnerabilityDetails` etc. and the answer needs more graph context.

❌ A dedicated MCP tool answers the question directly (vulnerability lookup, framework findings, attack-path enumeration). Use the dedicated tool: it is faster, cached, and renders better in the UI.
❌ The user has a known-good Cypher query in hand. Skip the builder and run `subimageRunCypher` directly.

## Public MCP tools used

Only these are addressed by this skill; nothing else.

| Tool | Purpose |
|---|---|
| `subimageAgentBuildQuery(user_question, ...)` | Delegates schema exploration and query authoring to SubImage's internal query agent and returns a candidate Cypher statement. Default path. |
| `searchModelQueries(labels=[...])` | Looks up previously cached "model queries" for a set of labels. Cheap to call, often returns a ready-made query you can adapt. |
| `saveModelQuery(...)` | Caches a query you authored from scratch so future questions of the same shape are one tool call away. Call only after a successful execution returned meaningful rows. |
| `subimageListModules()` | Confirms which modules are synced before querying their labels. |
| `subimageListModuleSchemaNodes(module=...)` | Discovers candidate labels for a given module when you don't know them. |
| `subimageGetNodesSchema(node_names=[...])` | Returns the validated label, property, and relationship surface for a list of labels. |
| `subimageGetLabelStats(labels=[...])` | Returns cardinality per label; check when you suspect a label is high-cardinality (>10 000 nodes) and your query does not filter early. |
| `subimageRunCypher(query)` | Executes one Cypher statement. Streams to the UI as an interactive table. |

## Path A: agent-delegated (default, recommended)

Use this whenever the user gave you a natural-language question and you do not already have a candidate Cypher in hand.

1. Call `subimageAgentBuildQuery(user_question=<the user's question, restated>)`. It returns a candidate Cypher query plus the labels it explored. The builder already consults `searchModelQueries` internally, so do not pre-call it on this path.
2. Read the returned query. Check it satisfies the **Final query rules** below. If not, refine the question (more specific labels, narrower scope) and call once more.
3. Execute it via `subimageRunCypher(query=<final>)`.
4. Summarize the result rows for the user. Do not reprint the table; `subimageRunCypher` already renders it.

This is one or two tool calls plus the execution. Do not pre-load schema with `subimageGetNodesSchema` before this path: the builder already does that internally.

## Path B: author by hand (fallback)

Use only when:

- you already know the exact labels involved and the agent builder is overkill,
- or you need a specific query shape the builder keeps refusing (custom `UNION`, exotic aggregation, etc.),
- or `subimageAgentBuildQuery` returned a query that does not match the question after one refinement.

In parallel on the first turn, when the labels are obvious:

- `searchModelQueries(labels=[...])` with those labels — if a cached query matches, adapt it instead of authoring from scratch.
- `subimageGetNodesSchema(node_names=["LabelA", "LabelB", ...])` — batch every label you care about into one call. The tool resolves both primary labels and ontology aliases.
- `subimageGetLabelStats(labels=[...])` — only if you suspect any of those labels is high-cardinality and your draft does not filter on it early.

If labels are not obvious, first call `subimageListModules()` then `subimageListModuleSchemaNodes(module=<m>)` to find candidates, then fetch their schemas as above (and re-run `searchModelQueries` with the resolved labels).

If text matching is uncertain, run **one** exploratory probe with `subimageRunCypher` using `LIMIT 5` or `COUNT(*)`. Prefer `toLower(...) CONTAINS ...` for text discovery. Do not stack multiple speculative probes; refine the labels instead.

When the query is ready, run it with `subimageRunCypher`. If you authored it from scratch (no `searchModelQueries` hit) and execution returned meaningful rows, call `saveModelQuery` with a clear description and the labels involved so future questions of the same shape can skip the authoring step. Do not cache a query that only passed syntax: cache after the result is confirmed useful.

## Schema rules

- Never invent node labels, property names, or relationship types. Use only what `subimageListModuleSchemaNodes` or `subimageGetNodesSchema` returned.
- Ontology labels (`User`, `Container`, `Image`, `ComputeInstance`, `Database`, `Group`, `Role`, ...) normalize identity, not edges or every property. `subimageGetNodesSchema` returns one section per underlying primary label; review them all, and prefer the provider-native property over the `_ont_*` projection when both are listed (the ontology projection may be null on a tenant even when the provider-native field is populated).
- If the user requests a property or entity that does not exist in the schema, stop and tell them inline. Do not guess.

## Final query rules

The query passed to `subimageRunCypher` must:

- use only validated labels, properties, and relationships,
- give every node variable at least one label (no bare `MATCH (n)`); unlabeled scans touch the entire graph and time out,
- give every relationship pattern a variable and an explicit type (e.g. `(a)-[r1:RELATES_TO]->(b)`; never `(a)-[:RELATES_TO]->(b)` or `(a)-[]->(b)`),
- include `LIMIT`, default `LIMIT 100` unless the user asks otherwise,
- return only the needed fields, not whole nodes,
- always include `n.id` (or the equivalent identity property) in the `RETURN` clause for every matched node so results can be cross-referenced,
- use `OPTIONAL MATCH` only when missing relationships should still preserve rows,
- never use unbounded variable-length paths.

Performance:

- Filter early on high-cardinality labels. `LIMIT` only caps output rows; it does not reduce compute time. Add `WHERE` filters to narrow the scan before any traversal or aggregation.
- Avoid disconnected `MATCH` patterns without a shared variable; they create a cartesian product.

Simplify before running:

- remove unnecessary hops, `WITH`, `OPTIONAL MATCH`,
- prefer direct properties over extra traversal,
- return only the columns the user asked for.

## Execution rules

- Each `subimageRunCypher` call must contain exactly one executable Cypher statement.
- Do not run a redundant `COUNT(*)` after the final query "to verify it parses". `subimageRunCypher` validates syntax on the way in.
- If you cannot build a valid query (missing schema, ambiguous question, no matching data after one probe), do not run a speculative query. Explain to the user what is missing and what they could clarify.

## Anti-patterns

- Reframing the user's question and immediately running `subimageRunCypher` with a query authored from memory. Use Path A or Path B first to ground every label.
- Pre-calling `searchModelQueries` before `subimageAgentBuildQuery` on Path A: the builder already consults the cache internally; you waste a turn.
- Calling `saveModelQuery` on a query that only passed syntax. Cache only after a real execution returned useful rows.
- Reformatting `subimageRunCypher` results as a markdown table. The tool streams an interactive table; summarize, do not duplicate.
- Looping speculative probes ("try this, no, try that"). One probe with `LIMIT 5` or `COUNT(*)`, then commit.
- Pre-loading the full schema "just in case" before Path A. The agent builder does that internally; you waste a turn and tokens.
- Calling `subimageGetLabelStats` for every query. Only check when a label is plausibly large and your query does not already filter it.

## Special cases

- Cross-provider questions: check for unified ontology / common node types before using provider-specific labels.
- Admin access questions: check both direct and indirect privilege paths, including managed policies, inline policies, wildcard `Allow` permissions, and assume-role chains.
- Use `UNION` and `RETURN DISTINCT` only when required.

## References

- Canonical doc: https://app.subimage.io/docs/agents/connect_via_mcp
- The MCP tool selection guide is auto-loaded by the first call to `subimageReadMe`; rely on it for tool-to-domain mapping.
