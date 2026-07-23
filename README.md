# SubImage skills

Agent skills marketplace for [SubImage](https://subimage.io), the cloud-native security platform. The same `SKILL.md` files work in Claude Code, Codex, Cursor, and other clients that support Agent Skills.

Two plugins ship from this repo:

- **`subimage-setup`**: onboarding recipes for cloud and SaaS data sources (AWS, GCP, Azure, GitHub, Kubernetes outpost). Terraform / CloudFormation / Helm / aws-cli / gcloud / az / gh paths. Designed to run inside an IaC or scripts repo.
- **`subimage-mcp`**: operator workflows over the SubImage MCP server (triage findings, investigate CVEs, trace package origin, review attack paths, audit SubImage coverage, build Cypher queries against the graph). Designed to run alongside an authenticated SubImage tenant.

The two are independent; install whichever your workflow needs.

## Install

### Claude Code

```bash
claude plugin marketplace add subimagesec/skills
claude plugin install subimage-setup@subimage
claude plugin install subimage-mcp@subimage
```

### Codex

```bash
codex plugin marketplace add subimagesec/skills
codex
```

Then run `/plugins`, select **SubImage Skills**, and install `subimage-setup` and/or `subimage-mcp`.

### Cursor

Open **Preferences** -> **Cursor Settings** -> **Rules, Skills, Subagents**, then choose **New** -> **Import from GitHub/GitLab** and enter:

```text
https://github.com/subimagesec/skills
```

Cursor imports the repo's Agent Skills and lists them under **Agent Decides**.

No `.mdc` file is required. Cursor Agent Skills use `SKILL.md`; `.mdc` files are for Cursor rules.

### Other Agent Skills clients

```bash
npx skills add subimagesec/skills
```

After install, skills are namespaced under their plugin:

```text
/subimage-setup:connect-aws
/subimage-setup:connect-gcp
/subimage-setup:connect-azure
/subimage-setup:connect-kubernetes-outpost
/subimage-setup:connect-github
/subimage-setup:connect-declarative-schema

/subimage-mcp:triage-new-findings
/subimage-mcp:investigate-cve
/subimage-mcp:investigate-package
/subimage-mcp:investigate-iam
/subimage-mcp:investigate-container
/subimage-mcp:investigate-ip
/subimage-mcp:investigate-public-exposure
/subimage-mcp:review-attack-path
/subimage-mcp:improve-subimage-coverage
/subimage-mcp:build-cypher-query
/subimage-mcp:create-custom-rule
```

Most are **model-invocable**: the agent picks them up automatically from the description when the user phrasing matches. You can also call any of them by name as a slash command.

## Prerequisites

`subimage-mcp` skills run against the SubImage MCP server: https://app.subimage.io/docs/agents/connect_via_mcp

`subimage-setup` skills run anywhere a shell or IaC repo lives; no tenant connection is required to generate the IaC code (only to verify it afterwards).

## Repository layout

```text
.agents/
  plugins/
    marketplace.json              # Codex marketplace catalog
.claude-plugin/
  marketplace.json               # marketplace catalog
plugins/
  subimage-setup/
    .codex-plugin/plugin.json    # Codex plugin manifest
    .claude-plugin/plugin.json   # plugin manifest
    skills/
      connect-aws/SKILL.md
      connect-gcp/SKILL.md
      connect-azure/SKILL.md
      connect-kubernetes-outpost/SKILL.md
      connect-github/SKILL.md
      connect-declarative-schema/SKILL.md
  subimage-mcp/
    .codex-plugin/plugin.json
    .claude-plugin/plugin.json
    skills/
      triage-new-findings/SKILL.md
      investigate-cve/SKILL.md
      investigate-package/SKILL.md
      investigate-iam/SKILL.md
      investigate-container/SKILL.md
      investigate-ip/SKILL.md
      investigate-public-exposure/SKILL.md
      review-attack-path/SKILL.md
      improve-subimage-coverage/SKILL.md
      build-cypher-query/SKILL.md
      create-custom-rule/SKILL.md
```

## Contributing

Each `SKILL.md` follows the [Agent Skills standard](https://agentskills.io), with Claude Code and Codex plugin manifests layered on top for native installs. When adding or editing a skill:

- Read the [skill creation best practices](https://agentskills.io/skill-creation/best-practices), the companion [description optimization guide](https://agentskills.io/skill-creation/optimizing-descriptions), the [Codex skills docs](https://developers.openai.com/codex/skills), and the [Cursor Agent Skills docs](https://cursor.com/docs/skills).
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
- Codex plugin docs: https://developers.openai.com/codex/plugins/build
- Cursor Agent Skills docs: https://cursor.com/docs/skills
