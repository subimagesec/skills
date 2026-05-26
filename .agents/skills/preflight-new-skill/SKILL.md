---
name: preflight-new-skill
description: Pre-flight audit of a newly added skill in this repo before opening a PR. Use when the user says "I added a new skill", "check this skill before PR", "review my new skill", "is my skill ready to ship", or has just created a `plugins/<plugin>/skills/<name>/SKILL.md` and wants every publication checkpoint validated (no leaks, no dashes, no placeholders, frontmatter sane, discoverability updated, MCP tool names cross-referenced).
---

# Pre-flight a new skill before PR

Audit a freshly added or modified skill in this marketplace repo. The skill ends when every checkpoint passes or every failure is listed with the exact file and line to fix.

Operate on the current git branch. The target is whichever skill is new or modified versus `main`.

## When to use

✅ The user just added a skill under `plugins/<plugin>/skills/<name>/SKILL.md` and asks for a review before PR.
✅ The user pings "check my skill" / "is this ready to ship" / "did I forget anything".
✅ A skill was edited (description tweak, body refactor) and needs the same gate before merging.

❌ The user is still drafting and explicitly asks for content help. Use `skill-creator` instead; this skill audits, it does not author.
❌ A change that does not touch any `SKILL.md`. Run normal review.

## Required inputs

Usually none: derive the target from git.

Ask only if ambiguous:

- "Which skill should I audit?" when more than one new `SKILL.md` exists on the branch and the user did not name one.

## Workflow

Run the steps in order. Report failures inline as you find them; do not batch silently to the end.

### Step 1: Locate the target skill(s)

```bash
git diff --name-only main...HEAD | grep -E 'plugins/.+/skills/.+/SKILL\.md$'
```

If multiple match, ask the user which one to audit (or audit them in turn). If none match, tell the user there is no new skill on this branch and stop.

For each target, capture:

- `PLUGIN` = the plugin directory (e.g. `subimage-mcp`)
- `NAME` = the skill directory name (e.g. `create-custom-rule`)
- `SKILL_PATH` = `plugins/<PLUGIN>/skills/<NAME>/SKILL.md`

### Step 2: Frontmatter and shape

Open `SKILL_PATH` and confirm:

- `name:` exactly matches the directory name (`<NAME>`).
- `description:` is one sentence, ends with concrete user-typed phrasings (at least three, e.g. "create a rule", "add a custom finding", "write a Cypher rule for X").
- No `{{...}}` placeholders anywhere in the file:
  ```bash
  grep -n '{{' "$SKILL_PATH" || echo "OK"
  ```
- Body uses the standard sections in this repo: **What this does**, **When to use** (with ✅/❌ bullets), **Required inputs**, **Workflow**, **Output**, **Verification**, **Anti-patterns**, **References**. Setup-style skills may have **Gotchas** instead of Anti-patterns.

### Step 3: Style rules

- No em-dashes or en-dashes (the global preference, also stated in the repo README):
  ```bash
  grep -n '—\|–' "$SKILL_PATH" || echo "OK: no em/en-dashes"
  ```
- US English, even if the user wrote the request in another language.
- Under the 500-line soft limit:
  ```bash
  wc -l "$SKILL_PATH"
  ```
  If over 500 lines, suggest splitting detailed content into a sibling `references/` directory and loading it on demand from the SKILL body.

### Step 4: Leak / public-readiness scan

This repo is public. The SKILL.md must not reference paths, services, or internals that only exist in private codebases the operator works in.

Source the leak patterns from the local audit file (not committed, lives outside this repo):

```bash
PATTERNS="${PREFLIGHT_LEAK_PATTERNS:-$HOME/.config/preflight-new-skill/leak-patterns.txt}"
if [ -f "$PATTERNS" ]; then
  grep -nEf "$PATTERNS" "$SKILL_PATH" || echo "OK: no pattern hits"
else
  echo "NOTE: leak-pattern file missing at $PATTERNS; falling back to generic heuristics"
fi
```

If `$PATTERNS` is absent, fall back to generic heuristics that flag candidates without naming any private repo:

- file-path-looking strings inside prose (anything with `/` and a language extension like `.py`, `.go`, `.ts`, `.rs`):
  ```bash
  grep -nE '[A-Za-z0-9_-]+/[A-Za-z0-9_/-]+\.(py|go|ts|tsx|rs|java|rb|kt)' "$SKILL_PATH" || echo "OK"
  ```
- references to internal-sounding hostnames or buckets:
  ```bash
  grep -niE '\.internal\b|internal\.[a-z]+\.[a-z]+|(^|\s)s3://|(^|\s)gs://|(^|\s)arn:aws:' "$SKILL_PATH" || echo "OK"
  ```
- tokens, credentials, emails of real people (only `support@subimage.io` and `noreply@anthropic.com` are acceptable in this repo):
  ```bash
  grep -noE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' "$SKILL_PATH" \
    | grep -vE '@(subimage\.io|anthropic\.com|example\.(com|org|net))$' \
    || echo "OK"
  grep -nE 'sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-' "$SKILL_PATH" || echo "OK"
  ```

For every hit, decide whether the reference is public-surface (documented API, public REST endpoint, open-source dependency) or internal. Flag internal ones to the user with the line number and propose a generic phrasing. Do not enumerate private path names inline in this skill: the operator running the audit already knows them, and this SKILL.md lives in a public repo.

### Step 5: Redundant or obvious prerequisites

This repo dropped per-skill "Requires a connected SubImage tenant" / "Connected to SubImage via MCP" phrasings because they are obvious for every `subimage-mcp` skill. Re-check that the new skill did not reintroduce them:

```bash
grep -niE 'connected (sub[iI]mage tenant|via mcp|to sub[iI]mage)|requires a connected' "$SKILL_PATH" || echo "OK"
```

If found, propose dropping the sentence or merging it into the tool list (e.g. "Uses `subimageX`, `subimageY`.").

### Step 6: MCP tool names cross-check (subimage-mcp only)

For skills under `plugins/subimage-mcp/skills/`, every MCP tool referenced should already appear in a sibling skill, in this repo's public docs (`https://app.subimage.io/docs/agents/connect_via_mcp`), or be plausibly the new tool the skill is built around.

Extract tool names from the file and cross-check against sibling skills:

```bash
grep -oE 'subimage[A-Z][A-Za-z]+|searchModelQueries|saveModelQuery|reportNeededImprovement' "$SKILL_PATH" \
  | sort -u \
  | while read -r tool; do
      hits=$(grep -rl "$tool" plugins/subimage-mcp/skills/ | grep -v "$SKILL_PATH" | wc -l | tr -d ' ')
      echo "$tool : $hits other skill(s)"
    done
```

Tools with `0 other skills` are either brand-new (acceptable if that is the rule's point) or a typo (more common). Ask the user to confirm each `0`-hit name is intentional, or pull the canonical name from the live MCP tool list.

### Step 7: Discoverability surfaces updated

When a skill is added (not just edited), four surfaces must list it. Confirm each:

1. **Root README** (`README.md`): the `/<plugin>:<name>` slash command appears in the listing, and `<name>/SKILL.md` appears under "Repository layout":
   ```bash
   grep -n "/$PLUGIN:$NAME" README.md
   grep -n "$NAME/SKILL.md" README.md
   ```
2. **Plugin README** (`plugins/<PLUGIN>/README.md`): a row in the Skills table with a link to the new SKILL.md:
   ```bash
   grep -n "$NAME" "plugins/$PLUGIN/README.md"
   ```
3. **Plugin manifest** (`plugins/<PLUGIN>/.claude-plugin/plugin.json`): the `description` field should hint at the new capability if it adds a new category (skip if the skill is a variant of an existing one).
4. **Marketplace catalog** (`.claude-plugin/marketplace.json`): same description sync as the plugin manifest.
5. **Public catalog page** (`index.html`): an `<li>` entry under the matching plugin block linking to the new SKILL.md.

Report which of the five are missing with the exact insertion point.

### Step 7b: Skip discoverability for edits

If `git diff --name-status main...HEAD` shows the SKILL.md as `M` (modified) rather than `A` (added), skip step 7 and only validate that any existing pointer still resolves.

### Step 8: Final summary

Emit a short report:

```
SKILL: plugins/<plugin>/skills/<name>/SKILL.md

Frontmatter        : OK | FAIL <reason>
Style              : OK | FAIL <reason>
Leak scan          : OK | FAIL <lines>
Redundant prereqs  : OK | FAIL <line>
MCP tool names     : OK | FAIL <names>
Discoverability    : OK | FAIL <missing surfaces>

Action items:
- <one bullet per fix, with file:line>
```

If every check is OK, end with: "Ready for PR. Run `git push -u origin <branch>` then ask the user for explicit authorization before `gh pr create` (per the global rule)."

## Output

The summary block above, plus inline fixes the user can apply. Do not open a PR from this skill: PR creation requires per-PR user authorization.

## Verification

Run the audit on a known-good recent skill (e.g. `plugins/subimage-mcp/skills/create-custom-rule/SKILL.md`) and confirm every checkpoint returns OK. Then mutate one rule (introduce an em-dash, drop a discoverability surface) and confirm the audit catches it.

## Anti-patterns

- Auto-fixing the SKILL.md without the user's go-ahead. This skill reports; the user (or a follow-up edit turn) fixes.
- Running `gh pr create` at the end. PR creation is gated by explicit per-PR authorization.
- Skipping step 5 because the skill "looks fine". The "requires a connected tenant" phrasing has been re-introduced multiple times; the grep is cheap.
- Treating a 0-hit MCP tool name as automatically wrong. New skills do introduce new tools (e.g. `subimageCreateCustomRule`). Confirm intent rather than rejecting.
- Reformatting the audit summary as prose. The block layout is the contract; agents parse it on follow-up turns.

## References

- Repo contribution rules: [README.md](../../../README.md) section "Contributing"
- Anthropic skill convention: https://agentskills.io/skill-creation/best-practices
- Description optimization: https://agentskills.io/skill-creation/optimizing-descriptions
- Claude Code plugin spec: https://code.claude.com/docs/en/plugins
