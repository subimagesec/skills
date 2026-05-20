---
name: build-cypher-query
description: Build a verified Cypher query for the SubImage Neo4j graph by exploring the schema, reusing model queries, and validating with bounded probes. Use when the user asks a question that requires querying the graph and you need to construct (not just re-run) a Cypher statement.
---

# Build a Cypher query

Produce a correct Cypher query that answers the user's question, as fast as possible, using the minimum number of tool calls.

## PRIORITIES

1. Never guess the schema.
2. Answer correctly.
3. Be fast: parallelize tool calls and skip unnecessary discovery.
4. Keep the final query as simple as possible.
5. Run exactly one final query, or explain inline why no query can be built.

## SCHEMA RULES

- Never invent node labels, property names, or relationship types.
- Only use labels/properties/relationships that are present in the results of `subimageListModuleSchemaNodes` or `subimageGetNodesSchema`.
- If the user requests a property or entity that does not exist in the schema, stop and explain that to the user inline.
- Ontology labels (`User`, `Container`, `Image`, `ComputeInstance`, `Database`, `Group`, `Role`, ...) normalize node identity, not edges or every property. `subimageGetNodesSchema` returns one section per underlying primary label, review them all, and prefer the provider-native property over the `_ont_*` projection when both are listed (the ontology projection may be null on a tenant even when the provider-native field is populated).

## PARALLELIZE TOOL CALLS

Whenever multiple tool calls are independent, issue them **in the same turn** (parallel) instead of sequentially. Examples:

- `searchModelQueries(labels=[...])` + `subimageGetNodesSchema(node_names=[...])` together on the first turn.
- Batch every label you care about into a single `subimageGetNodesSchema` call (`node_names=["AWSAccount", "EC2Instance", "Container", ...]`). The tool resolves both primary labels and ontology aliases; you do not need a module hint.
- `subimageListModules` + `subimageListModuleSchemaNodes(module=...)` together when both are needed.
- `subimageGetLabelStats` alongside schema lookups when cardinality matters.

Do NOT serialize calls that don't depend on each other.

## WORKFLOW

Pick the fastest path that still guarantees a correct query. Do NOT run every step blindly.

### FAST PATH (preferred when applicable)

Use this when the user's question clearly maps to known node types or ontology aliases:

1. In parallel, call:
   - `searchModelQueries(labels=[...])` with the obvious labels
   - `subimageGetNodesSchema(node_names=[...])` for those same labels
2. If a model query matches, adapt it.
3. Otherwise build the query directly from the fetched schema.
4. Go to FINALIZE.

Skip `subimageListModules` / `subimageListModuleSchemaNodes` when the labels are obvious from the question. If you cannot name the labels at all, fall back to the SLOW PATH.

### SLOW PATH (fallback when ambiguous)

Use this when you are not confident about which labels/modules are involved:

1. Call `subimageListModules` and `subimageListModuleSchemaNodes` (in parallel where possible) to discover candidates.
2. Fetch schemas for the candidate labels with `subimageGetNodesSchema` (batched in one call).
3. Call `searchModelQueries` (in parallel with the schema fetch if labels are already known).
4. If the question involves fuzzy text matching, unusual property values, or uncertain relationship paths, run **one** exploratory probe with `subimageRunCypher` using `LIMIT 5` or `COUNT(*)`. Prefer `toLower(...) CONTAINS ...` for text discovery. Do not stack multiple speculative probes.
5. If a probe returns no results, try in this order, but only one alternative per round:
   a. keep the relationship type but remove direction
   b. try a bounded path `[*1..4]`
   c. try alternative validated properties or labels
6. Go to FINALIZE.

Only conclude no data exists after reasonable probing.

## PERFORMANCE RULES

- **Never scan unlabeled nodes.** `MATCH (n)` without a label touches every node in the graph and is prohibitively slow. Every node pattern must include at least one label, e.g. `MATCH (n:EC2Instance)`. If you need to search across multiple labels, use `UNION` with one labeled `MATCH` per label, or filter with `WHERE n:LabelA OR n:LabelB` on a labeled starting pattern.
- **Avoid cartesian products when possible.** Disconnected MATCH patterns without a join or shared variable create a cross-product that can be very expensive. Prefer explicit relationships or shared WHERE filters between patterns.
- **Filter early on high-cardinality labels.** LIMIT only caps the number of output rows, it does NOT reduce compute time. If a label has many nodes, add WHERE filters to narrow the scan before any traversal or aggregation.
- **Check cardinality only when it matters.** Call `subimageGetLabelStats` when you suspect a label is high-cardinality (>10 000 nodes) and your query does not already filter it early. Do not call it for every query.

## FINAL QUERY RULES

The final query must:
- use only validated labels, properties, and relationships
- every node variable must have at least one label (no bare `MATCH (n)`)
- answer the user's question directly
- include `LIMIT`
- default to `LIMIT 100` unless the user asks otherwise
- return only needed fields, not whole nodes
- always include `n.id` (or the equivalent identity property) in the RETURN clause for every matched node, so results can be cross-referenced
- use `OPTIONAL MATCH` only when missing relationships should still preserve rows
- use explicit relationship types
- never use unbounded variable-length paths
- never use anonymous relationships
- every path element must have a variable, even if unused in WHERE/RETURN (e.g. `(a)-[r1:TYPE]->(b)`, not `(a)-[:TYPE]->(b)` or `(a)-[]->(b)`)

## SIMPLIFY BEFORE RUNNING

Before executing the final query:
- remove unnecessary hops
- remove unnecessary `WITH`
- remove unnecessary `OPTIONAL MATCH`
- prefer direct properties over extra traversal
- return only the requested columns

## FINALIZE

Once you have a candidate Cypher query that satisfies the rules above, run it with `subimageRunCypher`. This is the execution path the user sees: it streams results to the UI and renders the interactive table. Do NOT spend an extra tool call on a `COUNT(*)` or other end-of-run verification query just to prove the candidate parses, syntax is validated for you.

Use `subimageRunCypher` for exploratory probes only when the schema, path, or data shape is still uncertain. Otherwise, run it once for the final answer.

Execution rules:
- Each call to `subimageRunCypher` must contain exactly one executable Cypher statement.
- If you cannot build a valid query (missing schema, ambiguous question, no matching data after probing), do not run a speculative query. Explain to the user what is missing and what they could clarify.

## CACHE SUCCESSFUL QUERIES

If you built a query from scratch (no `searchModelQueries` hit) and a probe or execution confirmed it works and returned meaningful results, call `saveModelQuery` with a clear description and the labels involved. Do not cache a query based on syntax-only acceptance. This speeds up future questions of the same shape.

## SPECIAL CASES

- For cross-provider questions, check for unified ontology/common node types before using provider-specific labels.
- For admin access questions, check both direct and indirect privilege paths, including managed policies, inline policies, wildcard `Allow` permissions, and assume-role chains.
- Use `UNION` and `RETURN DISTINCT` only when required.

## IMPROVEMENT REPORTING

You have access to `reportNeededImprovement`. Call it proactively whenever you notice something that could be better in the schema, missing properties, awkward relationships, missing node types, data sources not ingested, etc. Report it even if you managed to build the query successfully.
