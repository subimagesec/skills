---
name: investigate-iam
description: Audit IAM privilege in SubImage end-to-end: enumerate admin-equivalent identities, map assume-role and cross-account trust chains, and resolve PermissionSet effective permissions. Use when the user asks "who has admin access", "show privilege escalation paths", "audit IAM permissions", "what can assume this role", "find cross-account trust", or scopes the question to a specific AWS account or role.
---

# Investigate IAM privilege

## What this does

Produces a structured IAM privilege report for an AWS environment by querying the SubImage graph. Collapses the typical multi-turn pattern (admin policy lookup → trust chain → SSO/PermissionSet mapping) into one investigation: who is effectively admin, how trust flows between roles and accounts, and what each Identity Center PermissionSet actually grants.

## When to use

✅ "Who has admin access in account X?" / "list privilege escalation paths".
✅ "Which roles can be assumed from another account?" (cross-account trust).
✅ "What does PermissionSet Y actually provision?"
✅ Periodic IAM hygiene review on a specific account or role.

❌ A single specific resource lookup a structured tool answers directly (e.g. one user's attached policies): query it directly.
❌ The full attack-path picture from a compromised identity: hand off to `subimage-mcp:review-attack-path`.
❌ Non-AWS identity providers as the primary subject: this skill is AWS IAM / Identity Center centric (Okta→AWS mapping is included as a join, not the focus).

## Prerequisites

- The AWS module is synced (`subimageListModules` shows `aws` enabled). IAM, STS, and Identity Center data come from it.
- This skill runs Cypher. Follow `subimage-mcp:build-cypher-query` discipline: validate labels and properties with `subimageGetNodesSchema` / `searchModelQueries` **before** trusting a template, then execute with `subimageRunCypher`. The templates in `references/cypher-templates.md` are a starting point, not a guarantee: graph labels drift.

## Optional inputs (ask only if it narrows the work)

| Value | When to use |
|---|---|
| AWS account id (12-digit) | Scope every query to one account. Apply the account-scoped variants in the templates. |
| Role name | Focus the trust-chain analysis on one role (who can assume it, what it reaches). |

If neither is given, run unscoped across all visible accounts.

## Workflow

Run the three phases. Within each, validate the template against the live schema first, then execute. The phases are independent: fire their queries together where the runner allows.

### Phase 1: Admin-equivalent identities

From `references/cypher-templates.md` § Admin-Equivalent Identities, enumerate:

1. **Direct admin users**: IAM users with `AdministratorAccess` or a wildcard `*:*` statement.
2. **Direct admin roles**: same, on roles.
3. **Indirect admin users**: users who can assume a role that is admin-equivalent.
4. **Admin via groups**: users in groups attaching an admin-equivalent policy.

Admin-equivalence = the named `AdministratorAccess` policy **OR** a statement with `*` action and `*`/null resource. Match both.

### Phase 2: Trust chains

From § Trust Chains:

1. **Cross-account trust**: roles trusting principals in a foreign account (exclude `AWSServiceRole*` and managed setup roles).
2. **Multi-hop role chaining**: assume-role paths of depth 2-4.
3. **SSO / Okta → AWS role mapping**: identity-provider users reaching AWS roles.

### Phase 3: PermissionSet effective permissions

From § PermissionSet Permissions:

1. **PermissionSet → Role → Policy**: what each Identity Center permission set provisions.
2. **Admin-equivalent PermissionSets**: permission sets granting admin access.

## Output

Produce an in-chat report (do not write to a file). Keep it scannable; tag every identity/role/account with `[[entity:<Label>:<id>|<name>]]` so the UI links it.

```
# IAM privilege audit: <all accounts | account <id> | role <name>>

## Summary
- Admin-equivalent users (direct): <n>   •   roles (direct): <n>
- Users with indirect admin (via assume-role): <n>
- Cross-account trust relationships: <n>
- PermissionSets with admin access: <n>

## 1. Admin-equivalent identities
- direct users: [[entity:AWSUser:<id>|<name>]] via <policy> (+<rest>)
- direct roles: [[entity:AWSRole:<id>|<name>]] via <policy> (+<rest>)
- indirect (assume-role): [[entity:AWSUser:<id>|<name>]] → [[entity:AWSRole:<id>|<name>]]

## 2. Trust chains
- cross-account: [[entity:AWSRole:<id>|<name>]] trusts <principal> in account <foreign-id>
- multi-hop: <srcRole> → … → <dstRole> (depth <d>)
- SSO/IdP: <identity> → [[entity:AWSRole:<id>|<entry-role>]]

## 3. PermissionSet effective permissions
- <permissionSet> (account <id>): roles <…>, policies <…>
- admin-equivalent: <permissionSet> → [[entity:AWSRole:<id>|<name>]] via <admin-policy>

## Risk summary
- **Critical**: <admin paths that bypass expected controls>
- **High**: <cross-account trust to unknown/foreign accounts>
- **Medium**: <overly broad permission sets, deep role chains>
```

If a phase returns nothing, keep its heading and write "None found" rather than dropping it.

## Anti-patterns

- Trusting a template label/relationship without schema-validating it first. The graph drifts; an unvalidated `MATCH` silently returns zero rows and you under-report admins.
- Fabricating or estimating counts. Every number traces to a query result.
- Omitting wildcard admins. `AdministratorAccess` is not the only admin path; a `*` action + `*` resource statement is equally admin.
- Reformatting raw `subimageRunCypher` output as a wall-of-text table. Summarize; tag the notable identities.
- Running unbounded queries. `LIMIT` every query (the templates default to 200).
- Asking the user to run Cypher themselves. Run it, summarize the result.

## References

- Cypher templates: [`references/cypher-templates.md`](references/cypher-templates.md) (schema-validate before trusting).
- Query discipline: `subimage-mcp:build-cypher-query`.
- Pivot for blast radius from a compromised identity: `subimage-mcp:review-attack-path`.
- Tool guide (loaded by `subimageReadMe`): Domain 4 "Attack Path Analysis" and the graph-query domain.
