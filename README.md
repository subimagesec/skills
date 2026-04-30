# SubImage skills

Claude Code marketplace for [SubImage](https://subimage.io), the cloud-native security platform.

Two plugins ship from this repo:

- **`subimage-setup`** : onboarding recipes for cloud and SaaS data sources (AWS, GCP, Azure, GitHub, Kubernetes outpost). Terraform / CloudFormation / Helm / aws-cli / gcloud / az / gh paths. Designed to run inside an IaC or scripts repo.
- **`subimage-mcp`** : operator workflows over the SubImage MCP server (triage findings, investigate CVEs, review attack paths, audit cartography coverage). Designed to run alongside an authenticated SubImage tenant.

The two are independent; install whichever your workflow needs.

## Install

```bash
claude plugin marketplace add subimagesec/skills
claude plugin install subimage-setup@subimage
claude plugin install subimage-mcp@subimage
```

After install, skills are namespaced under their plugin:

```text
/subimage-setup:connect-aws
/subimage-setup:connect-gcp
/subimage-setup:connect-azure
/subimage-setup:connect-kubernetes-outpost
/subimage-setup:connect-github

/subimage-mcp:triage-new-findings
/subimage-mcp:investigate-cve
/subimage-mcp:review-attack-path
/subimage-mcp:improve-cartography-coverage
```

Most are **model-invocable**: the agent picks them up automatically from the description when the user phrasing matches. You can also call any of them by name as a slash command.

## Prerequisites

`subimage-mcp` skills assume the SubImage MCP server is connected. Set that up first: https://app.subimage.io/docs/agents/connect_via_mcp

`subimage-setup` skills run anywhere a shell or IaC repo lives; no SubImage tenant connection is required to generate the IaC code (only to verify it afterwards).

## Repository layout

```text
.claude-plugin/
  marketplace.json               # marketplace catalog
plugins/
  subimage-setup/
    .claude-plugin/plugin.json   # plugin manifest
    skills/
      connect-aws/SKILL.md
      connect-gcp/SKILL.md
      connect-azure/SKILL.md
      connect-kubernetes-outpost/SKILL.md
      connect-github/SKILL.md
  subimage-mcp/
    .claude-plugin/plugin.json
    skills/
      triage-new-findings/SKILL.md
      investigate-cve/SKILL.md
      review-attack-path/SKILL.md
      improve-cartography-coverage/SKILL.md
```

## Contributing

Each `SKILL.md` follows the [Anthropic skill convention](https://agentskills.io/skill-creation/best-practices) and the [Claude Code plugin spec](https://code.claude.com/docs/en/plugins). When adding or editing a skill:

- Read the [skill creation best practices](https://agentskills.io/skill-creation/best-practices) and the companion [description optimization guide](https://agentskills.io/skill-creation/optimizing-descriptions).
- Frontmatter requires `name` (matches the directory) and `description` (when-to-trigger sentence with concrete user-typed phrasings).
- Body sections we use across all skills: **What this does**, **When to use** (✅/❌), **Required inputs** (with explicit ask-the-user phrasing), **Prerequisites**, **Gotchas** (setup skills) or **Anti-patterns** (usage skills), **Workflow**, **Output**, **Verification**, **References**.
- Never paste a literal `{{...}}` placeholder. Use `<NAMED_VAR>` and instruct the agent to ask the user for the value if it is not yet known.
- No em-dashes (`—`) in any markdown. Use `:`, `;`, `,`, or parentheses.
- Stay under the 500-line / 5,000-token soft limit per `SKILL.md`. If a skill exceeds it, split detailed reference material into a `references/` subdirectory and tell the agent when to load it.

## License

MIT. See [LICENSE](./LICENSE).

## Links

- Project home: https://subimage.io
- Public reference catalog: https://skills.subimage.io
- SubImage MCP docs: https://app.subimage.io/docs/agents/connect_via_mcp
