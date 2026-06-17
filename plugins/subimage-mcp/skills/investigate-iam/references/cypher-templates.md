# Cypher templates: IAM privilege audit

Starting-point queries for `investigate-iam`. They assume the AWS IAM / STS / Identity Center labels that SubImage's graph (Cartography-derived) commonly uses. **Schema-validate before trusting**: run `subimageGetNodesSchema(node_names=["AWSUser","AWSRole","AWSPolicy","AWSPolicyStatement","AWSGroup","AWSPermissionSet","AWSPrincipal","AWSAccount","OktaUser","OktaGroup"])` (and `searchModelQueries` for these labels) and adjust label/relationship/property names to whatever the live schema reports. Every query is `LIMIT`-bounded; keep it that way.

Admin-equivalence throughout = the named `AdministratorAccess` policy **OR** a statement whose action includes `*` and whose resource is `*` or null.

## Admin-Equivalent Identities

### Direct admin users

```cypher
MATCH (u:AWSUser)-[:POLICY]->(p:AWSPolicy)
WHERE p.name = 'AdministratorAccess'
   OR EXISTS {
        MATCH (p)-[:STATEMENT]->(s:AWSPolicyStatement)
        WHERE '*' IN s.action AND (s.resource IS NULL OR '*' IN s.resource)
      }
RETURN DISTINCT u.name AS user, u.arn AS userArn, p.name AS policyName
ORDER BY user
LIMIT 200
```

### Direct admin roles

```cypher
MATCH (r:AWSRole)-[:POLICY]->(p:AWSPolicy)
WHERE p.name = 'AdministratorAccess'
   OR EXISTS {
        MATCH (p)-[:STATEMENT]->(s:AWSPolicyStatement)
        WHERE '*' IN s.action AND (s.resource IS NULL OR '*' IN s.resource)
      }
RETURN DISTINCT r.name AS role, r.arn AS roleArn, p.name AS policyName
ORDER BY role
LIMIT 200
```

### Indirect admin users (via assume-role)

```cypher
MATCH (u:AWSUser)-[:STS_ASSUMEROLE_ALLOW]->(r:AWSRole)-[:POLICY]->(p:AWSPolicy)
WHERE p.name = 'AdministratorAccess'
   OR EXISTS {
        MATCH (p)-[:STATEMENT]->(s:AWSPolicyStatement)
        WHERE '*' IN s.action AND (s.resource IS NULL OR '*' IN s.resource)
      }
RETURN DISTINCT u.name AS user, u.arn AS userArn,
       r.name AS viaRole, r.arn AS roleArn, p.name AS policyName
ORDER BY user
LIMIT 200
```

### Admin via groups

```cypher
MATCH (u:AWSUser)-[:MEMBER_AWS_GROUP]->(g:AWSGroup)-[:POLICY]->(p:AWSPolicy)
WHERE p.name = 'AdministratorAccess'
   OR EXISTS {
        MATCH (p)-[:STATEMENT]->(s:AWSPolicyStatement)
        WHERE '*' IN s.action AND (s.resource IS NULL OR '*' IN s.resource)
      }
RETURN DISTINCT u.name AS user, u.arn AS userArn,
       g.name AS groupName, p.name AS policyName
ORDER BY user
LIMIT 200
```

## Trust Chains

### Cross-account trust

```cypher
MATCH (a:AWSAccount)-[:RESOURCE]->(r:AWSRole)-[:TRUSTS_AWS_PRINCIPAL]->(p:AWSPrincipal)<-[:RESOURCE]-(a2:AWSAccount)
WHERE a.id <> a2.id
  AND NOT r.name CONTAINS 'AWSServiceRole'
  AND NOT r.name CONTAINS 'QuickSetup'
RETURN r.name AS role, r.arn AS roleArn,
       p.arn AS trustedPrincipal,
       a2.name AS foreignAccount, a2.id AS foreignAccountId
ORDER BY role
LIMIT 200
```

### Multi-hop role chains (depth 2-4)

```cypher
MATCH path = (srcRole:AWSRole)-[:STS_ASSUMEROLE_ALLOW*2..4]->(dstRole:AWSRole)
RETURN srcRole.name AS sourceRole, srcRole.arn AS sourceRoleArn,
       [n IN nodes(path)[1..] | n.arn] AS chain,
       length(path) AS depth
ORDER BY depth DESC, sourceRole
LIMIT 200
```

### SSO / Okta user → AWS role mapping

```cypher
MATCH (user:OktaUser)-[:MEMBER_OF_OKTA_GROUP]->(group:OktaGroup)-[:ALLOWED_BY]->(role:AWSRole)<-[:RESOURCE]-(acc:AWSAccount)
RETURN user.email AS identity, 'Okta' AS provider,
       role.arn AS entryRole, acc.name AS account,
       collect(DISTINCT group.name) AS viaGroups
ORDER BY identity
LIMIT 200
```

### AWS Identity Center (SSO) PermissionSet → role mapping

```cypher
MATCH (ps:AWSPermissionSet)-[:ASSIGNED_TO_ROLE]->(role:AWSRole)<-[:RESOURCE]-(acc:AWSAccount)
RETURN ps.name AS permissionSet,
       role.arn AS entryRole,
       acc.name AS account, acc.id AS accountId
ORDER BY permissionSet, account
LIMIT 200
```

## PermissionSet Permissions

### PermissionSet → Role → Policy (full breakdown)

```cypher
MATCH (ps:AWSPermissionSet)-[:ASSIGNED_TO_ROLE]->(role:AWSRole)<-[:RESOURCE]-(acc:AWSAccount)
OPTIONAL MATCH (role)-[:POLICY]->(pol:AWSPolicy)-[:STATEMENT]->(stmt:AWSPolicyStatement)
RETURN ps.name AS permissionSet, ps.id AS permissionSetId,
       acc.name AS account, acc.id AS accountId,
       collect(DISTINCT role.arn) AS provisionedRoles,
       collect(DISTINCT pol.name) AS attachedPolicies,
       collect(DISTINCT {action: stmt.action, resource: stmt.resource, effect: stmt.effect}) AS statements
ORDER BY permissionSet, account
LIMIT 200
```

### Admin-equivalent PermissionSets

```cypher
MATCH (ps:AWSPermissionSet)-[:ASSIGNED_TO_ROLE]->(role:AWSRole)-[:POLICY]->(p:AWSPolicy)
WHERE p.name = 'AdministratorAccess'
   OR EXISTS {
        MATCH (p)-[:STATEMENT]->(s:AWSPolicyStatement)
        WHERE '*' IN s.action AND (s.resource IS NULL OR '*' IN s.resource)
      }
MATCH (role)<-[:RESOURCE]-(acc:AWSAccount)
RETURN DISTINCT ps.name AS permissionSet, ps.id AS permissionSetId,
       acc.name AS account, acc.id AS accountId,
       role.arn AS roleArn, p.name AS adminPolicy
ORDER BY permissionSet, account
LIMIT 200
```

## Account-Scoped Variants

When the user provides a 12-digit account id, scope each query to it.

For queries that already match an `AWSAccount` node, filter on **that query's** account alias. Use the alias the target query actually binds (the cross-account-trust query binds `a` and `a2`; the PermissionSet queries bind `acc`) and combine with any existing `WHERE` using `AND`:

```cypher
WHERE acc.id = '<account-id>'
```

For queries without an explicit account node, lead with:

```cypher
MATCH (acc:AWSAccount {id: '<account-id>'})-[:RESOURCE]->(targetNode)
```

and continue the pattern from `targetNode`.
