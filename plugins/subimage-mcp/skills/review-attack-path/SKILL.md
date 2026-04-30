---
name: review-attack-path
description: Walk a SubImage attack path step by step, identify the most sensitive impacted assets, propose the fastest remediation, hunt for credible n+1 extensions the engine has not yet modeled, and optionally simulate what-if scenarios. Use when the user asks to "review this attack path", "explain this attack path", "what would happen if X is compromised", "what attack paths involve <asset>", "find lateral movement opportunities from <asset>", "assess the blast radius of <asset>", or pivots from `subimage-mcp:investigate-cve`. Three entry modes: by path id, by asset id, or n+1 extension hunt.
---

# Review an attack path

## What this does

Three modes against the SubImage attack-path engine and the underlying Neo4j graph:

1. **Walk a known path** in plain English, surface the most sensitive terminal asset, and propose the fastest fix.
2. **Pivot from an asset** to find which paths it sits on and review the worst.
3. **Hunt for n+1 extensions**: probe the graph past a path's terminal node to find credible next steps the engine has not yet modeled, and report them via `reportNeededImprovement`.

Optional what-if simulation overlays any of the above.

## When to use

✅ User has an attack path id from the SubImage UI or a list response.
✅ User has an asset and wants to know if it is on any path.
✅ User wants to extend an existing path: "find lateral movement from here", "assess blast radius of <asset>", "what could come next".
✅ User wants a what-if: "if attacker compromises X, what happens?".
✅ User just finished `subimage-mcp:investigate-cve` and confirmed the pivot.

❌ User wants the full path catalog: just call `subimageListAttackPaths` and summarize without going step by step.
❌ User wants the static rule set behind the engine: that is `subimage-mcp:triage-new-findings` for findings, or the doc.

## Prerequisites

Connected via MCP. Uses `subimageListAttackPaths`, `subimageGetAttackPathDetails`, `subimageGetAttackPathsFromAsset`, `subimageGetScenarioCapabilities`, `subimageCreateAttackPathScenario`, `subimageRunCypher` (with `subimageAgentBuildQuery` to draft queries), `subimageListModuleSchemaNodes`, `subimageGetNodesSchema`, and `reportNeededImprovement`. Ticket and notification follow-ups use `subimageListLinearTeams`, `subimageCreateTicket`, `subimageSendNotification`.

## Required inputs

Pick one entry mode and collect the matching values. **If anything is missing, ask the user explicitly.**

| Entry mode | Required value | If missing, ask |
|---|---|---|
| Walk a known path | `<ATTACK_PATH_ID>` | "What is the attack path id? You can find it in the URL when viewing a path in SubImage, or call `subimageListAttackPaths` and pick one." |
| Pivot from an asset | `<ASSET_ID>` (resource ARN or fully-qualified id) | "What is the asset id? Resource ARN for AWS, fully-qualified id for GCP/Azure, or the SubImage detail-page URL works." |
| n+1 extension hunt | a starting `<ATTACK_PATH_ID>` *or* an `<ASSET_ID>` already known to be a terminal node of interest | "Where should I start the n+1 hunt: from a specific path's terminal node, or from an asset I should treat as compromised?" |

For a what-if scenario, also collect:

| Value | If missing, ask |
|---|---|
| `<NODE_LABEL>` | "Which node label is the starting point? (e.g. `EC2Instance`, `S3Bucket`, `User`)." |
| Capabilities to grant | "Which attacker capabilities should I simulate? Run `subimageGetScenarioCapabilities` first to see what is valid for this node label." |

## Posture (read this before calling any tool)

The graph is the source of truth. Be conservative.

1. Distinguish three confidence tiers in every output. Tag each statement implicitly via the section it sits in:
   - **Confirmed**: directly returned by the attack-path engine or by a Cypher query that hit specific labeled rows.
   - **Inferred**: combining two confirmed facts via a documented schema relationship, with a Cypher probe that backs the join.
   - **Hypothetical**: result of a what-if scenario, or a graph-shape observation without a concrete row backing it. Always say so.
2. Never invent labels, relationships, transitions, or security semantics. If the schema does not show a relationship, the path does not exist.
3. Adjacency in the graph does not imply exploitability. A relationship between two nodes is necessary but not sufficient.
4. Prefer missing a weak idea over reporting a bad one. Bad transition reports are worse than silence.
5. If evidence is weak or ambiguous, say so explicitly. Do not paper over uncertainty.

## Workflow

### Mode A: walk a known attack path

1. Call `subimageGetAttackPathDetails(attack_path_id="<ATTACK_PATH_ID>")`.
2. Decompose the path into four parts:
   - **Initial compromise**: the entry node and what gets the attacker in.
   - **Key pivots**: the 1 to 3 transitions that materially change the attacker's position (privilege gain, network reach, data access).
   - **Terminal node**: the last node in the chain.
   - **Terminal impact**: what the attacker now owns or can do.
3. Translate each transition into a plain-language sentence ("from `X` the attacker pivots to `Y` because `<reason from the transition>`"). Do not relist the JSON.
4. Rank impact: production / customer data / privileged identity > internal / dev > sandbox.

### Mode B: pivot from an asset

1. Call `subimageGetAttackPathsFromAsset(asset_id="<ASSET_ID>")`. SubImage returns paths sorted by criticality.
2. If empty: "No known attack path involves `<ASSET_ID>` right now. The asset may still be at risk via paths the engine has not modeled. Want me to run the n+1 extension hunt (Mode C) starting from this asset?"
3. If non-empty: pick the top 1 to 3, run Mode A on each.

### Mode C: hunt for n+1 extensions

This is what the analyst mode adds: inspect the terminal node of a path and probe the graph to determine whether a credible next step exists that the engine does not yet model.

1. Pick the terminal node of the path you are extending (or use `<ASSET_ID>` directly if the user named it).
2. Inspect what the schema says lives next to that node:
   ```
   subimageListModuleSchemaNodes(module="<module-of-the-node>")
   subimageGetNodesSchema(node_labels=["<TerminalLabel>"])
   ```
   Note the relationship types and target labels.
3. For each plausible relationship, run a small Cypher probe to confirm that real rows exist (see Cypher rules below). Examples of credible n+1 categories:
   - **Lateral movement**: from a compromised compute instance, reachable peers via security groups / VPC peering / shared service accounts.
   - **Privilege escalation**: from a non-admin identity, edges to roles or policies that effectively grant admin (`iam:PassRole`, `AssumeRole`, group memberships, custom roles with star permissions).
   - **Data exfiltration**: from any compromised compute, reachable storage with sensitive data labels or public read.
   - **Cross-account / cross-tenant**: trust relationships, cross-account role assumes, federated identity bridges.
4. Apply the **5-test checklist** below before reporting anything.
5. Report each credible extension via `reportNeededImprovement` (format below). Increment a counter; mention it in the final output.

### Mode D: what-if scenario (overlay)

Only when the user asks ("what if X is compromised", "simulate granting Y").

1. `subimageGetScenarioCapabilities(node_label="<NODE_LABEL>")` to discover valid capabilities.
2. Tell the user which capabilities are available and ask which to grant.
3. `subimageCreateAttackPathScenario(..., preview_only=true)`. **Always pass `preview_only=true`**: the user can inspect the result without it being persisted as a real path.
4. Walk the resulting path(s) using Mode A.

## Cypher rules for graph probes

When running Cypher in Mode C (and any time you escalate to `subimageRunCypher`):

- Always cap exploratory queries: `LIMIT 5`. Wider scans burn tokens and add no signal.
- Start broad, then refine. First query confirms the shape exists; second query gets the specific rows.
- For text matching, prefer `toLower(prop) CONTAINS "term"` over regex.
- Never use unbounded variable-length paths (`-[*]->`). Bound them: `-[*1..3]->` at most.
- Verify labels and relationships exist on real rows before reasoning about them. If `MATCH (a:Foo)-[:BAR]->(b)` returns 0 rows, the relationship is conceptual; do not present it as exploitable.
- If `subimageRunCypher` returns 0 rows, that is itself a confirmed fact: the relationship is not present in this tenant.

If you are unsure of the schema, draft the query via `subimageAgentBuildQuery(user_question=...)` and execute it with `subimageRunCypher`. Do not write Cypher from intuition.

## When to report a missing transition

Report via `reportNeededImprovement` only when **all five** are true:

1. The source and target labels are supported by real rows in this tenant's graph (not just the schema).
2. The relationship between them exists in the graph (a Cypher probe found at least one row).
3. The attacker's current position plausibly allows the step (capability, network reach, identity).
4. The step provides meaningful new impact, privilege, or reach (not just "another node of the same kind").
5. The step is not obviously already modeled by an existing transition (check by walking a few existing paths between similar node types).

If any one fails, do not report. State internally why and move on.

### `reportNeededImprovement` format

Fill the fields exactly:

- **context**: `Attack path analysis: <user request, one sentence>`
- **problem**: `Potential missing transition: <SourceLabel> can reach <TargetLabel> via <relationship>, enabling <impact>. Transition type: <lateral-movement | privilege-escalation | data-exfiltration | cross-account>. Evidence: <N> matches. Cypher pattern: <one-line MATCH>.`
- **workaround**: `partial`
- **workaround_detail**: `The current path stops at <terminal node>, but graph evidence suggests the attacker may continue to <target> via <mechanism>.`
- **suggested_improvement**: `Add a transition from <SourceLabel> to <TargetLabel> under conditions: <list of validated conditions>.`

## Output

For each path reviewed (Modes A and B):

```
# Attack path: <short title>

**Criticality**: <score / category>  ;  **Steps**: <N>

## In plain English
The attacker starts at [[entity:<Label>:<id>|<short>]] (<one-line context>).
1. <transition 1 in plain language>
2. <transition 2 in plain language>
3. ...
N. The chain ends at [[entity:<Label>:<id>|<short>]] which gives them <impact>.

## What this means
- **Initial compromise**: <one line>
- **Key pivot(s)**: <one line, naming the transitions that mattered>
- **Terminal impact**: <one line, naming what the attacker now controls>
- **Most sensitive impacted asset**: [[entity:<Label>:<id>|<short>]] (<why it matters>)
- **Why this path is exploitable today**: <rooted in the actual transitions, no speculation>

## Fastest remediation
<one or two concrete actions in priority order. Name the policy, the SG rule, the secret, the role.>

## What to do next
- Mitigate: <action>; owner: <team or `unknown`>
- Re-run after the change: SubImage refreshes paths on the next sync.
```

After Mode C, append:

```
## n+1 extension hunt
- probes run: <count>
- credible extensions found: <count>
- transitions reported via `reportNeededImprovement`: <count>
- summary of each reported extension (one line each)
```

If Mode C found nothing credible, say so plainly: "No credible n+1 extension supported by graph evidence. The terminal node `<id>` does not currently sit next to anything that survives the 5-test checklist."

Always tag entities with `[[entity:<Label>:<node.id>|<display>]]` so the chat UI links them.

## Optional follow-ups

If the user wants a ticket created:

1. `subimageListLinearTeams()` to get team ids.
2. `subimageCreateTicket(team_id=..., title="Mitigate: <path title>", description="<the narrative + remediation>")`.

Confirm the team before creating. Same rule for `subimageSendNotification`: confirm the channel.

## Anti-patterns

- Returning the raw transitions list as a markdown table. Forbidden by the chat system prompt for tool data, and useless when the goal is to make the path readable.
- Hand-waving on remediation ("review IAM policies"). Name the policy, the rule, the resource.
- Speculating about transitions the engine did not produce ("the attacker could also..."). If the user asks, run Mode C with Cypher probes; never claim an extension without evidence.
- Reporting a transition idea after one weak probe. Run the 5-test checklist; if any fails, do not report.
- Walking 5+ paths in one response. The user only acts on the top 1 or 2; deeper than that becomes wallpaper.
- Forgetting `preview_only=true` on what-if scenarios. The unflagged form persists the scenario; that is rarely what the user wants on first look.
- Treating schema relationships as confirmed exploitability. Probe first, then report.

## References

- Tool guide (always loaded by `subimageReadMe`): Domain 4 "Attack Path Analysis", Domain 1 "Knowledge Graph Exploration" for Cypher.
- Companion skill for vulnerability triage that often pivots here: `subimage-mcp:investigate-cve`.
- Architecture: https://app.subimage.io/docs/architecture/attack_path
