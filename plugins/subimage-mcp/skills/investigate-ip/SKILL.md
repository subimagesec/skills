---
name: investigate-ip
description: Resolve who owns an IP address or domain across all cloud resource types in SubImage (EC2, EIP, ENI, Route53/DNS, CloudFront, ELB, GCP, Azure), trace the DNS resolution chain, and - for public IPs - add external attribution (ASN, geo, VPN/proxy/Tor) via Spur. Use when the user asks "who owns this IP", "is this IP ours", "what does this domain resolve to", "trace this IP/domain", or hands off an IP/domain from a log or alert.
---

# Investigate an IP or domain

## What this does

Given an IP address or a domain name, answers two questions:

1. **Is it ours, and where?** Resolves ownership across every cloud resource type in the SubImage graph (compute, network interfaces, elastic IPs, DNS records, CDN, load balancers, GCP, Azure), and traces the DNS resolution chain (`domain → CNAME → A → IP → resource`).
2. **What is it on the internet?** For a public IP, enriches with `subimageEnrichIp` (Spur): owning ASN/org, geolocation, and whether it is a datacenter, VPN, proxy, Tor exit, or residential proxy.

The graph is authoritative for internal ownership; `subimageEnrichIp` adds the external attribution you need to judge whether inbound/outbound traffic is suspicious.

## When to use

✅ "Who owns 203.0.113.42?" / "is this IP one of ours?"
✅ "What does app.example.com resolve to / point at?"
✅ Triaging an IP or domain from a log line, alert, or finding.
✅ Tracing a domain's resolution chain to the resource behind it.

❌ Listing all your public IPs → `subimage-mcp:inventory-via-cypher` (the `:PublicIP` label).
❌ Explaining why a resource is public/exposed → `subimage-mcp:investigate-public-exposure`.
❌ The attack path from an exposed resource → `subimage-mcp:review-attack-path`.

## Prerequisites

- Relevant cloud modules synced (`subimageListModules`): AWS for EC2/EIP/ENI/Route53/CloudFront/ELB, GCP and Azure for their equivalents.
- `subimageEnrichIp` for public-IP attribution (public IPs only; it returns `invalid_input` for private/RFC1918 addresses).
- Cypher follows `subimage-mcp:build-cypher-query` discipline: schema-validate labels/properties with `subimageGetNodesSchema` / `searchModelQueries` before trusting a template, then run with `subimageRunCypher`. Templates are in `references/cypher-templates.md`.

## List-typed property safety (read before running)

Some graph properties are **lists**, not scalars. Comparing a scalar parameter against a list with `n.prop = $value` raises `Neo.ClientError.Statement.TypeError: expected String but was List<String>`. For list properties, use `ANY(x IN n.prop WHERE x = $value)` (or `$value IN n.prop`).

Known list-typed properties (schema-validate, as this drifts):

| Node label | Property |
|---|---|
| `AWSCloudFrontDistribution` | `aliases`, `geo_restriction_locations` |
| `GCPRecordSet` | `data` |
| `AWSEC2SecurityGroup` | `inbound_rules`, `outbound_rules` |

When unsure whether a property is scalar or list, probe one row: `MATCH (n:Label) WHERE n.prop IS NOT NULL RETURN apoc.meta.cypher.type(n.prop) LIMIT 1`.

## Workflow

### 1. Classify the input

- Matches `^\d{1,3}(\.\d{1,3}){3}$` (or a valid IPv6) → **IP**.
- Otherwise → **domain**.

### 2. Run the matching query set (parameterized, `$value`)

- **IP**: the § IP Address Queries (EC2 public/private, Elastic IP, ENI, DNS A/AAAA records, GCP forwarding rules and instances, Azure public IPs; load balancers only via DNS records that point to them).
- **Domain**: the § Domain Name Queries (Route53 records by name and by CNAME target, CloudFront aliases (**list-safe**), load balancer DNS names, GCP record sets (**list-safe**), EC2 public DNS).

If one query errors (e.g. a type error on an unexpected list property), log it and continue with the rest rather than aborting the whole lookup.

If the investigation turns into "why is this resource public/exposed?", switch to `subimage-mcp:investigate-public-exposure`. Keep this skill focused on IP/domain ownership and DNS/resource attribution.

### 3. Trace the DNS chain (domains, and IPs reachable via DNS)

Run the § DNS Chain query (`DNS_POINTS_TO*1..5`) to follow `domain → CNAME → A record → IP → resource`.

### 4. External attribution (public IPs only)

If the input is a public IP (or the chain resolves to one), call `subimageEnrichIp(ip=<public-ip>)`. Capture ASN/organization, geolocation, `is_datacenter`, and any anonymizer flags (`is_anonymous`, `anonymizer_types`, `is_residential_proxy`). Skip for private/internal addresses.

## Output

In-chat provenance report (no file output). Tag resources with `[[entity:<Label>:<id>|<name>]]`. Keep empty sections labeled "None found".

```
# IP / domain investigation: <input>

## Direct matches
- [[entity:<Label>:<id>|<name>]]: account <…>, region <…>, matched on <field>
- ...

## DNS chain (if applicable)
- <name> → <CNAME/A> → <target> → [[entity:<Label>:<id>|<resource>]]

## External attribution (public IP only)
- owner: <org> (ASN <n>)   •   location: <city, country>
- datacenter: <y/n>   •   anonymizer: <VPN/proxy/Tor/residential-proxy/none>

## Ownership summary
- **Owner**: <account / project / subscription>
- **Resource path**: <account → resource type → resource id>
- **Risk notes**: <exposed_internet=true, public IP on sensitive asset, anonymizer-sourced traffic, …>

```

## Anti-patterns

- Comparing a scalar against a list property with `=`. Use `ANY(...)` / `IN` for `aliases`, `data`, security-group rule lists, etc. (see the safety section).
- Interpolating the IP/domain into the query string. Always pass it as the `$value` parameter.
- Calling `subimageEnrichIp` on a private/internal address. It only attributes routable public IPs.
- Trusting template labels/properties without schema-validating. Network/DNS labels drift across tenants.
- Answering public-exposure-cause questions here. Use `subimage-mcp:investigate-public-exposure`.
- Aborting the whole lookup when one query errors. Skip the failing query, keep the rest.
- Unbounded queries. `LIMIT` everything (templates default to 100).

## References

- Cypher templates: [`references/cypher-templates.md`](references/cypher-templates.md) (schema-validate; mind list-typed properties).
- Query discipline: `subimage-mcp:build-cypher-query`.
- External IP attribution: `subimageEnrichIp` (Spur).
- Public exposure cause: `subimage-mcp:investigate-public-exposure`.
- Pivot to attack surface from a resolved resource: `subimage-mcp:review-attack-path`.
- Tool guide (loaded by `subimageReadMe`): the enrichment and graph-query domains.
