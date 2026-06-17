"""Validate every SKILL.md with the same loader SubImage uses at runtime.

A naive yaml.safe_load only catches syntax; the real loader also enforces the
required name/description fields and structure, i.e. the whole class of errors
that makes SubImage fail at import. Keep pydantic-ai-skills pinned in lockstep
with the version SubImage embeds (see .github/workflows/validate-skills.yml).
"""

import sys
from pathlib import Path

from pydantic_ai_skills import Skill, SkillValidationError

ROOT = Path(__file__).resolve().parent.parent

# from_file raises on the first problem; loop per-file so CI reports every
# broken SKILL.md in one run instead of one fix-push cycle at a time.
errors: list[str] = []
count = 0
for skill_md in sorted(ROOT.rglob("SKILL.md")):
    if ".claude" in skill_md.relative_to(ROOT).parts:  # nested worktrees, not real skills
        continue
    count += 1
    try:
        Skill.from_file(skill_md, validate=True)
    except SkillValidationError as e:
        errors.append(f"{skill_md.relative_to(ROOT)}: {e}")

if errors:
    print("Invalid SKILL.md files:\n" + "\n".join(f"  - {e}" for e in errors))
    sys.exit(1)
print(f"OK: {count} SKILL.md validated")
