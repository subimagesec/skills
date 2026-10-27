# Agent guide

Guide for agents editing this repo. Publication checkpoints (frontmatter, the section list, dashes, the line limit, version bumps) live in [Contributing](README.md#contributing) and in `.agents/skills/preflight-new-skill`.

## Writing a good skill

- A skill teaches an agent how to do a job. Keep what changes the work the agent does. Leave out mechanics it cannot act on, and checks it cannot immediately run inside the turn.

- Describe internal mechanics that an agent might need to understand to effectively use the tools to accomplish the relevant goals, but be smart about what you include so that you are not indiscriminately paraphrasing internal logic. The failure mode is a skill that starts narrating the pipeline for its own sake: for example, how an id is hashed, how a query is wrapped before it runs, how each value is converted and stored, how one run is matched against the last. None of that changes what the agent writes or which tool it calls, so it does not belong. A mechanism earns its place only when, without it, the agent would make a worse choice.

- Do not copy a list out of the Cartography schema into a skill, unless the skill is extremely specific to a narrow schema. Avoid listing node labels, modules, relationship types, properties. This is because that list becomes stale the moment Cartography adds or renames something. The schema is discovered at runtime. Tell the agent how to look the value up, or which label to prefer, and leave the inventory out of the skill.
