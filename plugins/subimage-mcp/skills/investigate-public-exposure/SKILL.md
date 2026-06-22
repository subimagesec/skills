---
name: investigate-public-exposure
description: Determine why a SubImage asset, domain, bucket, CDN distribution, load balancer, security group path, or cloud storage resource is publicly reachable. Use when the user asks "why is this public", "is this exposed because of CloudFront", "is this bucket public because of S3 policy", "what is exposing this asset", or "explain the public exposure cause".
---

# Investigate public exposure

## What this does

Explains why a resource is publicly reachable and separates the exposure surface from the sensitive resource behind it. Use graph evidence to answer:

1. **What is reachable from the internet?** CDN, load balancer, public IP, DNS record, security-group path, public bucket policy, or public cloud storage ACL/policy.
2. **Why is it reachable?** Direct anonymous grant, CDN origin path, public listener/rule/security group, or another modeled exposure path.
3. **What evidence proves it?** Relationship path, policy statement fields, rollup exposure fields, and relevant account/project/subscription context.

## When to use

✅ "Why is this bucket public?"
✅ "Is this domain public because of CloudFront or because of S3 policy?"
✅ "What is exposing this load balancer / Kubernetes service / public IP?"
✅ "Explain why this finding says the resource is internet-exposed."
✅ "Is this bucket directly anonymous, CloudFront-only, or both?"

❌ "Who owns this IP/domain?" → `subimage-mcp:investigate-ip`.
❌ "List all public IPs" → `subimageGetInventory` with `inventory_type=publicips`.
❌ "What attack path follows from this exposure?" → finish the exposure cause first, then pivot to `subimage-mcp:review-attack-path` if the user wants impact.

## Required inputs

Ask for the missing value if it is not present:

- Asset identifier, resource name, domain, bucket name, finding id, or graph entity.
- Tenant/module context only if multiple tenants or modules are in play.

## Prerequisites

- Call `subimageReadMe` once per session before using SubImage MCP tools.
- Use `subimageListModules` to confirm relevant modules are synced.
- Follow `subimage-mcp:build-cypher-query` discipline: schema-validate labels/properties/relationships with `subimageGetNodesSchema` and `searchModelQueries` before trusting a template, then run bounded queries with `subimageRunCypher`.
- Starting-point Cypher templates live in `references/cypher-templates.md`.

## Workflow

### 1. Classify the target

- **Domain**: resolve DNS/CDN/load-balancer paths and also check whether the value is a direct bucket name. Bucket names can look like hostnames and may not appear as CloudFront aliases.
- **Bucket or cloud storage resource**: inspect the resource directly, then check CDN/origin paths and policy/ACL statements.
- **Cloud resource id/name**: resolve the node first, then walk outward to internet-facing surfaces and inward to sensitive backing resources.
- **Finding id**: resolve the affected resource and rule evidence, then continue from the affected node.

If the task is only ownership of an IP/domain, switch to `subimage-mcp:investigate-ip`. If ownership lookup discovers a public asset and the user asks why it is public, continue with this skill.

### 2. Validate the schema before querying

Call `subimageGetNodesSchema` for the labels you will use. Relationship direction in schema examples is authoritative.

For CloudFront/S3 exposure cause, validate and use these directed patterns:

```cypher
(:CloudFrontDistribution)-[:SERVES_FROM]->(:S3Bucket)
(:S3Bucket)-[:POLICY_STATEMENT]->(:S3PolicyStatement)
```

Do not infer direction from relationship names or prose. Do not reverse bucket policy statements to `(stmt:S3PolicyStatement)-[:POLICY_STATEMENT]->(bucket:S3Bucket)`. If a schema-directed query unexpectedly returns no rows, run one bounded diagnostic probe using the same typed relationship undirected, inspect `startNode(r)` / `endNode(r)`, then correct the directed query.

### 3. Gather exposure evidence

Collect the specific mechanism, not just the final resource:

- **CDN path**: distribution id/domain/aliases, enabled/status, origin relationship, and the backing resource.
- **Direct bucket/storage exposure**: anonymous/public rollup fields plus policy/ACL statement nodes.
- **Network exposure**: load balancer listeners, public IP, security group ingress, DNS chain, and target resource.
- **Finding context**: rule name, affected entity, evidence fields, and related graph path.

For S3 buckets, inspect `S3PolicyStatement` nodes before answering. Bucket rollup fields such as `anonymous_access` are not enough to distinguish CloudFront-only access from direct anonymous bucket policy grants. Include statement `sid`, `effect`, `principal`, `action`, `resource`, and `condition` values when present.

### 4. Decide the cause

Use the evidence to classify the exposure:

- **CloudFront-only**: CloudFront serves the bucket, and bucket policy statements are scoped to CloudFront/OAI/OAC or have restrictive conditions.
- **Direct anonymous bucket policy**: a statement grants anonymous or broad public principal access to the bucket or objects.
- **Both**: CloudFront serves the bucket and a separate direct public statement also grants access.
- **Network public**: exposure comes from public IP/listener/security-group path rather than storage policy.
- **Unknown or partial**: schema/module data is missing, a query failed, or only rollup fields are present.

## Output

In-chat provenance report. Tag resources with `[[entity:<Label>:<id>|<name>]]`. Keep empty sections labeled "None found".

```text
# Public exposure investigation: <input>

## Target
- [[entity:<Label>:<id>|<name>]]: account/project/subscription <...>, region <...>

## Exposure surfaces
- <surface>: <domain/IP/listener/CDN/bucket policy path>

## Evidence
- CloudFront path: <distribution id/domain/aliases, enabled/status, served bucket>
- Direct policy statements: <sid, effect, principal, action, resource, condition>
- Network path: <DNS/load balancer/public IP/security group path>
- Finding context: <rule/evidence if applicable>

## Conclusion
- Cause: <CloudFront-only | direct anonymous policy | both | network public | unknown>
- Confidence: <high | medium | low>, because <evidence/gaps>

## Next pivots
- <attack path, owner remediation, rule tuning, or "none">
```

## Verification

- Confirm every queried label/property/relationship appears in schema output or a saved model query.
- Re-run the final Cypher with `LIMIT` and inspect enough rows to support the conclusion.
- For CloudFront/S3, verify the direct `S3Bucket` branch was checked even when a CloudFront alias was found.
- For direct public policy conclusions, quote the relevant policy statement fields in the answer.

## Anti-patterns

- Keeping CloudFront/S3 public exposure cause logic inside `investigate-ip`; IP/domain ownership is a different workflow.
- Stopping after a CloudFront alias match and failing to inspect the backing bucket policy.
- Trusting `anonymous_access` alone to distinguish direct public policy from CDN-mediated access.
- Reversing directed schema relationships or using undirected matches as the final query.
- Interpolating user input into Cypher. Always pass values as parameters.
- Unbounded graph walks. Keep probes narrow and `LIMIT` bounded.

## References

- Public exposure Cypher templates: [`references/cypher-templates.md`](references/cypher-templates.md).
- Query discipline: `subimage-mcp:build-cypher-query`.
- Ownership lookup before exposure cause: `subimage-mcp:investigate-ip`.
- Impact pivot after cause is proven: `subimage-mcp:review-attack-path`.
