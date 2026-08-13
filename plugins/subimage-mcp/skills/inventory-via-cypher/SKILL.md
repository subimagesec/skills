---
name: inventory-via-cypher
description: Answer flat resource-inventory questions - list, count, filter, sort, or paginate ONE resource type - by mapping the requested type to its Neo4j ontology label, or to the provider-native label when the user names a specific product, then running a single Cypher query. Use when the user asks "list", "how many", "show me all", "which of our <resource type>", or names a product such as "our RDS instances", "our EKS clusters", or "our GitHub repositories", across any cloud, SaaS, or VCS provider.
---

# Inventory via Cypher

## What this does

Answers a flat resource-inventory question with one Cypher query. SubImage
normalizes every provider's resources onto a small set of ontology labels, so
"list our databases" is one `MATCH` on `:Database`, whatever mix of RDS, Cloud
SQL and Azure SQL sits underneath. When the user names one product rather than a
category, the same single query runs on that product's provider-native label:
"list our RDS instances" is one `MATCH` on `:AWSRDSInstance`. Either way a single
label reaches the resources directly, which is why there is no dedicated
inventory tool.

## Hard entry gate

Load this skill only for a flat question about ONE resource type: a listing, a
count, a filter, a sort, a page, or a breakdown by one attribute.

**One resource type is one label, and one label is one query.** Which label
depends on a single question: did the user name a category or a product?

- **A category, named generically**, takes the ontology label from the mapping
  table. "Network access controls and firewalls", "buckets and blob storage",
  "VMs, instances, and droplets" each name one ontology label, not several types,
  however many provider words the question uses. Enumerating the provider-native
  labels behind one of them (`AWSEC2SecurityGroup`, `GCPFirewall`,
  `AzureFirewall`, ...) is the failure this skill exists to prevent: it is
  slower, it silently misses providers you did not think of, and the ontology
  label already spans all of them.
- **A product, named explicitly**, takes that product's native label from the
  named-products table. "Our RDS instances", "our EKS clusters", "our GitHub
  repositories" each name one product, and its native label is the only label
  that means exactly that product. Take one native label, never a union.

A provider word is not a product name. "Our AWS databases" is a category scoped
to a provider, so it stays on the ontology label with an `_ont_source` filter,
not on a list of every AWS database label.

Do NOT load it for:

- relationships, reachability, access, blast radius, root cause, privilege
  chains, or anything spanning two resource types (use `build-cypher-query`);
- CVEs, packages, fixability, findings, or attack paths: those are `:Signal`
  nodes with their own shapes (use `signals-via-cypher`);
- issues and action items (`subimageListIssues`);
- which compliance rules and frameworks exist or are enabled
  (`subimageListRules`, `subimageListFrameworks`).

**Both tables below are authoritative.** For any type or product they cover, do
not call `subimageListModules`, `subimageListModuleSchemaNodes`,
`subimageGetNodesSchema`, or `subimageSearchModelQueries` first: go straight to
`subimageRunCypher`. Only reach for schema exploration when the requested type or
product is genuinely absent from both.

## Required inputs

- **the resource type or product**, in the user's own words. Map it to a label
  yourself via the tables below; never ask the user for a Neo4j label.
- **any filter value** the question implies (a name, a region, a state, a
  provider). Ask only when the question names a filter without a value ("the
  container named..." with no name).

Never invent a filter value or narrow to one provider the user did not name.

## Prerequisites

`subimageRunCypher` (read-only). Nothing else for any type in the table.

## Mapping table

The table for a category the user named generically. Every row is one ontology
label. `provider` is `_ont_source` on every label that has it. `id` is always the
node's `id`.

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
- never satisfy a generic category by OR-ing the native labels underneath it.
  `MATCH (n:Tenant) WHERE n:AWSAccount OR n:AzureSubscription` silently drops
  every provider you did not list, and SaaS tenants (Okta, GitHub, OpenAI, ...)
  are `:Tenant` too. Filter on `_ont_source` when the user asks for one provider.
  A native label answers a product the user named, one label, never a union.
- `:ComputeCluster` double-counts EKS unless you exclude the Kubernetes twin:
  `WHERE NOT (n:KubernetesCluster AND EXISTS { (:AWSEKSCluster)-[:MAPS_TO]->(n) })`.
  `:AWSEKSCluster` is the current primary label; the unprefixed `:EKSCluster`
  alias is deprecated upstream and goes away in Cartography v1.0.0.
- a `:UserAccount` is inactive when `_ont_active` is false, but some providers
  write only `_ont_inactive`. Resolve activity as
  `coalesce(n._ont_active, NOT n._ont_inactive)`.

## Named products

Reach for this table only when the user named the product. Almost every row
narrows a row above: the ontology label rides on the same node as an extra label,
so a native query still returns `id` and every populated `_ont_*` property. Going
native loses nothing, it only narrows.

AWS product labels are `AWS`-prefixed: `:AWSRDSInstance`, not `:RDSInstance`. The
unprefixed spellings are compatibility aliases that Cartography removes in
v1.0.0, so write the prefixed form even though both still resolve today. No other
provider was renamed, which is why `:GKECluster` carries no `GCP` prefix.

| The user names | Native label | Same node also carries |
|---|---|---|
| RDS instances | `:AWSRDSInstance` | `:Database` |
| Aurora or RDS clusters | `:AWSRDSCluster` | nothing |
| DynamoDB tables | `:AWSDynamoDBTable` | `:Database` |
| EKS clusters | `:AWSEKSCluster` | `:ComputeCluster` |
| ECS clusters | `:AWSECSCluster` | `:ComputeCluster` |
| EC2 instances | `:AWSEC2Instance` | `:ComputeInstance` |
| S3 buckets | `:AWSS3Bucket` | `:ObjectStorage` |
| Lambda functions | `:AWSLambda` | `:Function` |
| ECR repositories | `:AWSECRRepository` | `:ContainerRegistry` |
| GitHub repositories | `:GitHubRepository` | `:CodeRepository` |
| GitLab projects | `:GitLabProject` | `:CodeRepository` |
| GKE clusters | `:GKECluster` | `:ComputeCluster` |
| GCE instances | `:GCPInstance` | `:ComputeInstance` |
| Cloud SQL instances | `:GCPCloudSQLInstance` | `:Database` |
| GCS buckets | `:GCPBucket` | `:ObjectStorage` |
| AKS clusters | `:AzureKubernetesCluster` | `:ComputeCluster` |
| Azure VMs | `:AzureVirtualMachine` | `:ComputeInstance` |
| Azure SQL databases | `:AzureSQLDatabase` | `:Database` |
| Okta users | `:OktaUser` | `:UserAccount` |

Native properties worth filtering on, none of which the ontology projects for
every provider:

- `:AWSRDSInstance`: `db_instance_identifier`, `engine`, `engine_version`,
  `storage_encrypted`, `publicly_accessible`, `multi_az`, `deletion_protection`.
- `:AWSEKSCluster`: `version` (the Kubernetes version), `platform_version`,
  `status`, `endpoint_public_access`, `authentication_mode`.
- `:GitHubRepository`: `fullname`, `primarylanguage`, `private`, `archived`,
  `defaultbranch`.

Native-label traps:

- it is `:AWSLambda`, not `AWSLambdaFunction`.
- `:AWSRDSCluster` carries no ontology label at all, so Aurora clusters are
  unreachable through `:Database`. The native label is the only way to list them.
- `:GitHubRepository` has no `visibility`; use the boolean `private`. Its
  property names are lowercase-concatenated, not snake_case: `fullname`,
  `defaultbranch`, `primarylanguage`.
- Azure object storage is `:AzureStorageBlobContainer`. `:AzureStorageAccount` is
  the parent account and carries no ontology label.

When the named product has no row here, resolve its label with ONE
`subimageGetNodesSchema` or `subimageListModuleSchemaNodes` call, then query. One
discovery call, never a discovery phase.

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

Category beside named product. "List our databases" stays on the ontology label:

```cypher
MATCH (n:Database)
RETURN n.id AS id, n._ont_name AS name, n._ont_type AS engine, n._ont_source AS provider
ORDER BY name
LIMIT 100
```

"List our unencrypted RDS instances" goes native:

```cypher
MATCH (n:AWSRDSInstance)
WHERE n.storage_encrypted = false
RETURN n.id AS id, n.db_instance_identifier AS name, n.engine AS engine, n.region AS region
ORDER BY name
LIMIT 100
```

`storage_encrypted` is the load-bearing clause and it exists only on the native
node. `:Database` cannot express this filter, and `_ont_source = 'aws'` would
return DynamoDB and OpenSearch alongside RDS.

"Which EKS clusters are on version 1.31?":

```cypher
MATCH (n:AWSEKSCluster)
WHERE n.version = '1.31'
RETURN n.id AS id, n.name AS name, n.region AS region, n.version AS version
ORDER BY name
LIMIT 100
```

Going native also drops the `:ComputeCluster` dedup clause: `:AWSEKSCluster`
matches each EKS cluster once, with no Kubernetes twin to exclude.

"List our code repositories" stays on the ontology label; "list our GitHub
repositories" goes native and can then read GitHub-only fields:

```cypher
MATCH (n:CodeRepository)
RETURN n.id AS id, n._ont_fullname AS name, n._ont_public AS public
ORDER BY name
LIMIT 100
```

```cypher
MATCH (n:GitHubRepository)
WHERE n.archived = false
RETURN n.id AS id, n.fullname AS name, n.primarylanguage AS language, n.private AS private
ORDER BY name
LIMIT 100
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
- On an ontology label, prefer the `_ont_*` property. When it comes back null
  across the board, fall back to the provider-native one of the same name via
  `coalesce(n._ont_name, n.name)`: ontology mapping coverage varies by provider.
- On a native label, read the native property directly for anything
  product-specific. That is the reason to be there. `n.id` still comes back, and
  the `_ont_*` properties are still on the node for whatever the ontology covers.
- Scope to one account, subscription, or project with the `:Tenant` edge:
  `MATCH (t:Tenant {_ont_name: 'prod'})-[:RESOURCE]->(n:ComputeInstance)`.

## Anti-patterns

- Provider console deep links are computed outside the graph; a Cypher answer
  cannot produce them. Say so rather than constructing a plausible URL.
- If the requested resource type or product has no row above and schema
  exploration finds no matching label, say it is not modeled. Never answer with a
  neighboring type or a sibling product.
- A count and a listing are two queries. Do not re-run `count(*)` after a
  listing that already returned every row under the limit.
- A question naming several provider technologies is still one query on one
  label. Reaching for schema discovery to enumerate provider-native labels turns
  a two-call answer into a ten-call one and still misses providers.
- Answering a named product through its ontology label and then trying to
  recover the product from `_ont_type`. `:Database` spans RDS, OpenSearch,
  DynamoDB, Azure SQL, Cloud SQL and a dozen more; `_ont_type` holds an engine
  name, not a product, so no filter over it isolates RDS. Use the native label.

## Output

Answer in prose or a short list, not a dump of the raw rows. State the count,
name the notable members, and tag entities so they are clickable. When the
result hit the `LIMIT`, say so and give the total from a second `count(n)` query
rather than implying the page is the whole set.

## Verification

- The query names exactly one label: the ontology label when the user named a
  category, that product's native label only when the user named the product.
  Never a union of labels, and never a native label for a generic request.
- Any AWS native label in the query is `AWS`-prefixed.
- One `subimageRunCypher` call answered it, plus at most one schema call when the
  named product had no row. More than two means the entry gate was wrong and this
  was a `build-cypher-query` question.
- The row count is consistent with what you reported.

## References

- `subimage-mcp:build-cypher-query` for anything relational: joins, reachability,
  ownership, blast radius, absence validation.
- `subimage-mcp:investigate-ip`, `investigate-container`, `investigate-iam` for
  the per-domain investigation flows that start from one resource.
