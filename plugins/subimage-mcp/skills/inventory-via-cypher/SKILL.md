---
name: inventory-via-cypher
description: Answer flat resource-inventory questions - list, count, filter, sort, or paginate ONE resource type - by mapping the requested type to its Neo4j ontology label and running a single Cypher query. Use when the user asks "list", "how many", "show me all", or "which of our <resource type>", across any cloud, SaaS, or VCS provider.
---

# Inventory via Cypher

## What this does

Answers a flat resource-inventory question with one Cypher query. SubImage
normalizes every provider's resources onto a small set of ontology labels, so
"list our databases" is one `MATCH` on `:Database`, whatever mix of RDS, Cloud
SQL and Azure SQL sits underneath. Reading the label directly reaches every
resource type in the graph, which is why there is no dedicated inventory tool.

## Hard entry gate

Load this skill only for a flat question about ONE resource type: a listing, a
count, a filter, a sort, a page, or a breakdown by one attribute.

**One ontology label is one resource type, however many provider words the
question uses.** "Network access controls and firewalls", "buckets and blob
storage", "VMs, instances, and droplets" each name a single label below, not
several types. Answer them with one query on that label. Enumerating the
provider-native labels behind it (`AWSEC2SecurityGroup`, `GCPFirewall`,
`AzureFirewall`, ...) is the failure this skill exists to prevent: it is slower,
it silently misses providers you did not think of, and the ontology label already
spans all of them.

Do NOT load it for:

- relationships, reachability, access, blast radius, root cause, privilege
  chains, or anything spanning two resource types (use `build-cypher-query`);
- CVEs, packages, fixability, findings, or attack paths: those are `:Signal`
  nodes with their own shapes (use `signals-via-cypher`);
- issues and action items (`subimageListIssues`);
- which compliance rules and frameworks exist or are enabled
  (`subimageListRules`, `subimageListFrameworks`).

**The mapping table below is authoritative.** For any type it covers, do not
call `subimageListModules`, `subimageListModuleSchemaNodes`,
`subimageGetNodesSchema`, or `subimageSearchModelQueries` first: go straight to
`subimageRunCypher`. Only reach for schema exploration when the requested type is
genuinely absent from the table.

## Required inputs

- **the resource type**, in the user's own words. Map it to a label yourself via
  the table below; never ask the user for a Neo4j label.
- **any filter value** the question implies (a name, a region, a state, a
  provider). Ask only when the question names a filter without a value ("the
  container named..." with no name).

Never invent a filter value or narrow to one provider the user did not name.

## Prerequisites

`subimageRunCypher` (read-only). Nothing else for any type in the table.

## Mapping table

Every row is one ontology label. `provider` is `_ont_source` on every label that
has it. `id` is always the node's `id`.

| Resource type | Label | Fields (property) |
|---|---|---|
| compute instances | `:ComputeInstance` | name, region, state, type, created_at, public_ip_address, private_ip_address (all `_ont_*`) |
| containers | `:Container` | name, image, image_digest, state, cpu, memory, region, namespace, health_status (all `_ont_*`) |
| compute clusters | `:ComputeCluster` | name, endpoint, region, status, version (all `_ont_*`) |
| container registries | `:ContainerRegistry` | name, created_at, location, size_bytes, uri (all `_ont_*`) |
| databases | `:Database` | name, type, version, port, encrypted, location (all `_ont_*`) |
| object storage | `:ObjectStorage` | name, location, encrypted, versioning, public (all `_ont_*`) |
| functions | `:Function` | name, runtime, memory, timeout, deployment_type (all `_ont_*`) |
| load balancers | `:LoadBalancer` | name, lb_type, scheme, dns_name, region (all `_ont_*`) |
| public IPs | `:PublicIP` | `ip_address` (native, no prefix) |
| DNS zones | `:DNSZone` | name, public (all `_ont_*`) |
| network access controls, firewalls, security groups, NSGs, NACLs, WAF rules | `:NetworkAccessControl` | name, direction (all `_ont_*`) |
| certificates | `:Certificate` | domain, expiry (all `_ont_*`) |
| secrets | `:Secret` | name, created_at, updated_at, rotation_enabled (all `_ont_*`) |
| API keys | `:APIKey` | name, created_at, updated_at, expires_at, last_used_at (all `_ont_*`); `repository_selection`, `permissions` native |
| permission roles | `:PermissionRole` | name, type, scope (all `_ont_*`) |
| service accounts | `:ServiceAccount` | name, email, active (all `_ont_*`) |
| user groups | `:UserGroup` | name, description, email (all `_ont_*`) |
| user accounts | `:UserAccount` | email, has_mfa, active, lastactivity (all `_ont_*`) |
| users (identities) | `:User` | `fullname`, `email`, `active` (native, no prefix) |
| devices | `:Device` | `hostname`, `manufacturer`, `model`, `os`, `os_version`, `platform`, `serial_number` (all native) |
| third-party / SaaS apps | `:ThirdPartyApp` | name, client_id, enabled, native_app, protocol (all `_ont_*`) |
| code repositories | `:CodeRepository` | name, fullname, url, public, archived, default_branch (all `_ont_*`) |
| accounts, subscriptions, projects, orgs (tenants) | `:Tenant` | status, domain (all `_ont_*`) |

Traps worth naming:

- user groups are `:UserGroup`, **not** `:Group`.
- `:User` is the deduplicated identity across providers; `:UserAccount` is the
  per-provider account. "How many users" means `:User`; "how many Okta
  accounts" means `:UserAccount` filtered on `_ont_source`.
- never narrow an ontology label to the provider labels underneath it.
  `MATCH (n:Tenant) WHERE n:AWSAccount OR n:AzureSubscription` silently drops
  every provider you did not list, and SaaS tenants (Okta, GitHub, OpenAI, ...)
  are `:Tenant` too. Filter on `_ont_source` when the user asks for one provider.
- `:ComputeCluster` double-counts EKS unless you exclude the Kubernetes twin:
  `WHERE NOT (n:KubernetesCluster AND EXISTS { (:AWSEKSCluster)-[:MAPS_TO]->(n) })`.
  `:AWSEKSCluster` is the current primary label; the `:EKSCluster` alias other
  skills still use is deprecated upstream and goes away in Cartography v1.0.0.
- a `:UserAccount` is inactive when `_ont_active` is false, but some providers
  write only `_ont_inactive`. Resolve activity as
  `coalesce(n._ont_active, NOT n._ont_inactive)`.

## Patterns

Listing:

```cypher
MATCH (n:ComputeInstance)
RETURN n.id AS id, n._ont_name AS name, n._ont_region AS region, n._ont_state AS state
ORDER BY name
LIMIT 100
```

Count:

```cypher
MATCH (n:Container) RETURN count(n) AS count
```

Filter, exact and substring:

```cypher
MATCH (n:Container)
WHERE n._ont_state = 'running' AND toLower(n._ont_name) CONTAINS toLower('payments')
RETURN n.id AS id, n._ont_name AS name, n._ont_image AS image
LIMIT 100
```

Sort and paginate:

```cypher
MATCH (n:UserAccount)
RETURN n.id AS id, n._ont_email AS email, n._ont_has_mfa AS has_mfa
ORDER BY email ASC
SKIP 0 LIMIT 25
```

Breakdown by one attribute:

```cypher
MATCH (n:Container)
RETURN n._ont_source AS provider, count(n) AS count
ORDER BY count DESC
```

## Rules

- One self-contained read-only statement per `subimageRunCypher` call. No `//`
  comments, no parameters, no semicolon.
- Always match a label. A bare `MATCH (n)` scans the whole graph.
- Always `LIMIT` a listing; 100 unless the user asked for more.
- Return `n.id` on every query that returns one row per node, so the answer can
  be tagged and drilled into. An aggregate (a count, a group-by) returns the
  grouping key and the count instead; there is no single node to identify.
- `subimageRunCypher` takes no query parameters, so any value from the user is
  inlined as a literal. Escape backslashes and single quotes in it before
  inlining (`O'Brien` becomes `'O\'Brien'`), or the statement breaks on the
  apostrophe.
- Prefer the `_ont_*` property. When it comes back null across the board, fall
  back to the provider-native one of the same name via
  `coalesce(n._ont_name, n.name)`: ontology mapping coverage varies by provider.
- Scope to one account, subscription, or project with the `:Tenant` edge:
  `MATCH (t:Tenant {_ont_name: 'prod'})-[:RESOURCE]->(n:ComputeInstance)`.

## Anti-patterns

- Provider console deep links are computed outside the graph; a Cypher answer
  cannot produce them. Say so rather than constructing a plausible URL.
- If the requested resource type has no row above and schema exploration finds
  no matching label, say the type is not modeled. Never answer with a
  neighboring type.
- A count and a listing are two queries. Do not re-run `count(*)` after a
  listing that already returned every row under the limit.
- A question naming several provider technologies is still one query on one
  label. Reaching for schema discovery to enumerate provider-native labels turns
  a two-call answer into a ten-call one and still misses providers.

## Output

Answer in prose or a short list, not a dump of the raw rows. State the count,
name the notable members, and tag entities so they are clickable. When the
result hit the `LIMIT`, say so and give the total from a second `count(n)` query
rather than implying the page is the whole set.

## Verification

- The query names a label from the table, not a provider-native label.
- One `subimageRunCypher` call answered it. More than two means the entry gate
  was wrong and this was a `build-cypher-query` question.
- The row count is consistent with what you reported.

## References

- `subimage-mcp:build-cypher-query` for anything relational: joins, reachability,
  ownership, blast radius, absence validation.
- `subimage-mcp:investigate-ip`, `investigate-container`, `investigate-iam` for
  the per-domain investigation flows that start from one resource.
