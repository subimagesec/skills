# subimage-mcp

Operator workflows over the [SubImage](https://subimage.io) MCP server. Each skill orchestrates a multi-tool flow against a connected SubImage tenant : findings triage, CVE deep dive, attack-path review, coverage audit.

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
| [`subimage-mcp:improve-cartography-coverage`](./skills/improve-cartography-coverage/SKILL.md) | Scan the current repo for providers, cross-reference with `subimageListModules`, check the SubImage compliance framework, surface top actionable findings. |

## Prerequisites

These skills assume the SubImage MCP server is connected to your client. If it is not, set it up first :

- Connect via MCP : https://app.subimage.io/docs/agents/connect_via_mcp
- Or follow the SubImage docs for OAuth / M2M authentication.

The `subimageReadMe` MCP tool injects the global tool-selection guide into the conversation on first call; these skills layer recipe-style multi-tool flows on top of it.

## Conventions

Every skill follows the same shape:

1. **Required inputs** : the agent asks the user for the CVE id, asset id, framework slug, etc. It never invents values.
2. **Anti-patterns** : behaviors the agent will gravitate toward but should not (markdown tables on tool data, auto-pivoting without consent, walking 5+ paths in one response).
3. **Output template** : a markdown skeleton so multiple invocations produce comparable artifacts.
4. **Hand-off hooks** : skills explicitly chain into siblings (CVE -> attack path, coverage -> setup) and tell the user when to switch.
