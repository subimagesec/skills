# subimage-mcp

Operator workflows over the [SubImage](https://subimage.io) MCP server. Each skill orchestrates a multi-tool flow : findings triage, CVE deep dive, attack-path review, coverage audit, Cypher query authoring, custom rule authoring.

## Install

```bash
claude plugin marketplace add subimagesec/skills
claude plugin install subimage-mcp@subimage
```

## Skills

| Skill | What it does |
|---|---|
| [`subimage-mcp:triage-new-findings`](./skills/triage-new-findings/SKILL.md) | Frameworks-first findings digest with grouped themes and recommended next steps. |
| [`subimage-mcp:investigate-cve`](./skills/investigate-cve/SKILL.md) | Full impact and fixability for a specific CVE, with an opt-in pivot to attack-path exploration. |
| [`subimage-mcp:review-attack-path`](./skills/review-attack-path/SKILL.md) | Walk an attack path step by step, identify the most sensitive impacted assets, hunt for n+1 extensions, propose the fastest fix. |
| [`subimage-mcp:improve-subimage-coverage`](./skills/improve-subimage-coverage/SKILL.md) | Scan the current repo for providers, cross-reference with `subimageListModules`, check the SubImage compliance framework, surface top actionable findings. |
| [`subimage-mcp:build-cypher-query`](./skills/build-cypher-query/SKILL.md) | Construct a verified Cypher query against the SubImage Neo4j graph by exploring the schema, reusing model queries, and validating with bounded probes. |
| [`subimage-mcp:create-custom-rule`](./skills/create-custom-rule/SKILL.md) | Draft, validate against the live tenant graph, and persist a tenant-local custom Cypher rule via `subimageCreateCustomRule`. |

The `subimageReadMe` MCP tool injects the global tool-selection guide into the conversation on first call; these skills layer recipe-style multi-tool flows on top of it. See [MCP setup](https://app.subimage.io/docs/agents/connect_via_mcp) to wire the server into your client.

## Conventions

Every skill follows the same shape:

1. **Required inputs** : the agent asks the user for the CVE id, asset id, framework slug, etc. It never invents values.
2. **Anti-patterns** : behaviors the agent will gravitate toward but should not (markdown tables on tool data, auto-pivoting without consent, walking 5+ paths in one response).
3. **Output template** : a markdown skeleton so multiple invocations produce comparable artifacts.
4. **Hand-off hooks** : skills explicitly chain into siblings (CVE -> attack path, coverage -> setup) and tell the user when to switch.
