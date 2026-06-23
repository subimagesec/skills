---
name: investigate-public-exposure
description: Determine why a SubImage asset, domain, bucket, CDN distribution, load balancer, Kubernetes workload, serverless function, database, public IP, or cloud storage resource is publicly reachable. Use when the user asks "why is this public", "what exposes this asset", "is this exposed by CloudFront/S3", "is this exposed by a load balancer, security group, API gateway, ingress, Cloud Run, ECS, or EKS", or "explain the public exposure cause".
---

# Investigate public exposure

## What this does

Explain why a resource is publicly reachable. Separate the public entrypoint from the sensitive backing resource, then show the graph evidence that connects them.

Answer four questions:

1. What public surface exists: DNS record, CDN, API gateway, public IP, load balancer, ingress, public policy, public control plane, public database endpoint, or public snapshot/image.
2. What makes it public: internet-facing scheme, public listener, open security rule, anonymous policy, public IAM binding, provider public access flag, public DNS/proxy, or an analysis-job rollup.
3. What is behind it: bucket, instance, database, task/container, pod/container, service, function, or control plane.
4. How confident is the conclusion: direct raw-path evidence, ontology edge, provider rollup only, or partial/stale module coverage.

## When to use

- "Why is this bucket public?"
- "Is this domain public because of CloudFront or because of direct S3 policy?"
- "What exposes this load balancer, Kubernetes service, pod, container, public IP, or DNS name?"
- "Is this ECS service exposed through an ALB/NLB?"
- "Is this EKS or Kubernetes workload exposed through ingress or service type LoadBalancer?"
- "Is this Cloud Run service, Lambda, API Gateway, Azure Function, or Cloud Function public?"
- "Explain why this finding says the resource is internet-exposed."

Do not use this skill for pure ownership lookup. If the user only asks who owns an IP/domain, use `subimage-mcp:investigate-ip`. If ownership lookup finds a public asset and the user asks why it is public, continue here.

Do not start with attack-path impact. Prove the exposure cause first, then pivot to `subimage-mcp:review-attack-path` if the user asks what an attacker can do next.

## Required inputs

Ask for a missing value only when needed:

- Asset identifier, resource name, domain, IP, bucket name, finding id, or graph entity.
- Tenant/module context if multiple tenants or modules are in play.

## Operating rules

- Call `subimageReadMe` once per session before using SubImage MCP tools.
- Call `subimageListModules` early. If a relevant module is disabled, degraded, stale, or still syncing, report that coverage limitation.
- Use `subimage-mcp:build-cypher-query` discipline. Schema-validate labels, properties, and relationship examples with `subimageGetNodesSchema` and `searchModelQueries` before trusting a template.
- Starting-point Cypher templates live in `references/cypher-templates.md`. Treat them as probes, not proof, until adjusted to the live schema.
- Prefer provider-independent ontology pivots when they exist: `PublicIP`, `LoadBalancer`, `DNSRecord`, `ObjectStorage`, `Function`, `Database`, `ComputeInstance`, `ComputeCluster`, `ComputeService`, `ComputePod`, `Container`, and `Snapshot`.
- Provider analysis fields such as `exposed_internet`, `exposed_internet_type`, `_ont_public`, `anonymous_access`, and `anonymous_actions` are useful evidence, but they are not always enough to explain the cause. Reconstruct the raw path when the user asks "why".
- `EXPOSE` edges identify a front-door-to-target path, but they are not proof that the front door is public. Check the exposing node's publicness, scheme, listener, security-rule path, and relationship metadata before using the edge as public-exposure evidence.
- Distinguish public front door from direct public backend. A private pod behind an internet-facing ALB is public through the ALB, not necessarily directly public.
- If a schema-directed query returns nothing but a rollup says the asset is exposed, treat that as a diagnostic moment: inspect module status, analysis-job coverage, and nearby raw paths before concluding the graph is wrong.

## Exposure model

Use this vocabulary consistently:

- **Direct public network**: the resource itself has a public IP/public endpoint plus permissive network rules.
- **Public front door to private backend**: CDN, API gateway, load balancer, ingress, or proxy is public and routes to a private resource.
- **Public policy/IAM**: object storage, function, Cloud Run, API Gateway, or similar service allows anonymous or broad public access.
- **Public control plane**: EKS, GKE, AKS, or similar management endpoint is public. This is not the same as workload exposure.
- **Public data copy/share**: public snapshot, image, backup, or object storage data exposure without a network listener.
- **DNS/proxy-only signal**: a public DNS or Cloudflare record exists, but the backing resource still needs separate proof.
- **Unknown/partial**: graph lacks the provider module, relationship, analysis job result, or raw evidence needed to prove the cause.

## Workflow

### 1. Resolve the target

Classify the input before querying:

- **Domain**: inspect `DNSRecord` and provider DNS records, then follow `DNS_POINTS_TO` when present. Also check whether the value is a CDN alias, load-balancer DNS name, API Gateway URL, app service host, or bucket-style hostname.
- **IP address**: inspect `PublicIP`, provider public IP resources, and `DNS_POINTS_TO`. If the user only asked ownership, use `investigate-ip`; if they ask why reachable, continue here.
- **Bucket/storage/database/function/service name**: resolve the node directly, then check policy, front-door, and network paths.
- **Kubernetes/EKS/ECS workload**: resolve the service, task, pod, or container, then walk toward load balancers, ingresses, services, and control-plane nodes.
- **Finding id**: resolve the affected entity and rule evidence, then continue from that entity.

### 2. Check broad pivots first

Start with cross-provider pivots so you do not miss long chains:

- `DNSRecord` or provider DNS record to `DNS_POINTS_TO` target.
- `PublicIP` to `POINTS_TO` and `RESERVED_BY`.
- `LoadBalancer` to `EXPOSE` target.
- `Container` / `ComputePod` / `ComputeService` / `ComputeCluster` workload-parent chains.
- Public rollup fields on the target and nearby surfaces.
- Provider-specific resource relationships only after the broad pivots identify the likely surface.

### 3. Reconstruct provider-specific causes

#### AWS

- **CloudFront and S3**: Check `CloudFrontDistribution` aliases/domain, `SERVES_FROM` bucket origin, and direct bucket policy statements. For S3 buckets, inspect `S3PolicyStatement` fields before concluding direct public access. A CloudFront origin alone does not prove the bucket is directly public.
- **S3 direct policy/ACL**: Check bucket rollups (`anonymous_access`, `anonymous_actions`, block-public-access fields) plus policy statements with `effect`, `principal`, `action`, `resource`, and `condition`.
- **EC2 direct exposure**: Look for a public IP/public DNS plus `AWSIpPermissionInbound` rules connected to `AWSIpRange` values such as `0.0.0.0/0` or `::/0`. Include protocol and port range, and note whether the rule reaches the instance through a security group or network interface.
- **ALB/NLB/classic ELB**: Check internet-facing scheme, listeners, security group rules for ALB/classic ELB, and `EXPOSE` target edges to instances, private IPs, Kubernetes pods/containers, or ECS containers. Internal load balancers can also have `EXPOSE` target edges, so publicness must come from the load balancer path. NLB exposure can be scheme/listener based even without a security group.
- **ECS**: Prefer `LoadBalancer-[:EXPOSE]->Container` when present. If absent, reconstruct ALB/NLB to private IP to network interface to `ECSTask` to `ECSContainer`, then walk `WORKLOAD_PARENT` to `ECSService`/`ECSCluster`.
- **EKS control plane**: Check `EKSCluster.endpoint_public_access`, `_ont_control_plane_public_access`, and `exposed_internet`. CIDR-restricted public endpoints can still be public control-plane exposure; report the CIDR limitation if modeled.
- **Kubernetes on EKS**: Check `KubernetesIngress` or `KubernetesService` `USES_LOAD_BALANCER`, service `TARGETS` pod, pod/container targets, and `EXPOSE` edges from AWS load balancers.
- **API Gateway**: For REST APIs, inspect endpoint type, execute-api disablement, stage/resource/method/integration nodes, and anonymous policy/access fields. For API Gateway v2, graph coverage may be thinner; report front-door evidence and any missing route/integration modeling.
- **Lambda**: Check `anonymous_access` and `anonymous_actions` for function URL or resource-policy exposure. If reached by API Gateway or ALB, classify as public front door to function rather than direct anonymous Lambda unless the function policy proves direct access.
- **RDS and databases**: Check provider rollup/rule evidence such as `publicly_accessible` and security group ingress covering the endpoint port.
- **Snapshots and AMIs**: Public EBS/RDS snapshots and AMIs are public data-copy exposure. They do not imply a reachable network service.

#### Kubernetes

- Separate **control-plane exposure** from **workload exposure**.
- For workload exposure, follow:
  - `KubernetesService` type `LoadBalancer` or service `USES_LOAD_BALANCER` to load balancer to pod/container targets.
  - `KubernetesIngress` to load balancer and `TARGETS` service, then service to pod/container.
  - `KubernetesGateway` to `KubernetesHTTPRoute` to service to pod/container.
- Use `exposed_internet` on service/pod/container as an analysis result, but reconstruct ingress/service/load-balancer cause for the final answer.
- Treat `host_network`, node ports, and host ports as risk pivots. They are not proof of public exposure unless the node, service, load balancer, firewall, or routing path is public.
- If Kubernetes module status is degraded, identify failed clusters before saying an ingress/service is absent.

#### GCP

- **Cloud Run**: Direct public invocation requires ingress allowing all traffic and a public invoker IAM binding, usually a `GCPPolicyBinding` with `is_public=true`, `has_condition=false`, and role `roles/run.invoker`. An `exposed_internet` rollup on the service may only prove public ingress, not public IAM.
- **Cloud Functions**: Check HTTPS trigger plus public invoker IAM binding.
- **Load balancers**: Inspect external `GCPForwardingRule`, `GCPBackendService`, `GCPInstanceGroup`, and backend `GCPInstance` chains. Use `LoadBalancer` ontology where present.
- **Compute instances**: Check public access config plus `GCPFirewall` / `GCPIpRule` allow paths from `0.0.0.0/0`, including higher-priority deny rules if modeled.
- **Cloud SQL**: Check `GCPCloudSQLAuthorizedNetwork` values such as `0.0.0.0/0`.
- **GCS buckets**: Check `_ont_public`, public ACL, public IAM binding, and public access prevention.
- **GKE control plane**: Check control-plane public access fields and distinguish endpoint exposure from workload exposure.

#### Azure

- **Virtual machines**: Check `AzurePublicIPAddress` to NIC to `AzureVirtualMachine`, then network security group rules from `Internet`, `*`, `0.0.0.0/0`, or equivalent sources to the relevant destination port.
- **Load balancers**: Check `AzureLoadBalancer` frontend public IP, rules, backend pool, NIC, VM, and `EXPOSE` edges. Public LB to private VM is front-door exposure, not direct VM public IP exposure.
- **Application Gateway/App Service/Function App**: DNS/default host names can prove public front-door naming, but direct reachability depends on public network access, private endpoints, access restrictions, and provider-specific fields. Report missing modeling when those fields are absent.
- **AKS control plane**: Check public/private control-plane flags where modeled.
- **SQL/Cosmos/Blob**: Check public network access/firewall rules for SQL/Cosmos and container public access for Blob Storage.
- **Azure Firewall**: Treat `PROTECTS` or topology edges as context, not proof that a path is allowed, unless effective rules are modeled.

#### Cloudflare

- A `CloudflareDNSRecord` or `DNSRecord` can prove a public DNS/front-door signal. `proxied=true` means Cloudflare is the public edge and the origin may be hidden.
- Cloudflare DNS alone does not prove the origin resource is directly public. Follow `DNS_POINTS_TO` or record values to provider resources, then inspect the provider path.
- If Cloudflare WAF/access/rules are not synced, say the graph cannot prove whether Cloudflare blocks the route.

#### Scaleway

- Use `ScalewayFlexibleIp`, `PublicIP`, and `ScalewayInstance` pivots for public IP exposure.
- If the graph only shows reserved public IPs but no direct `POINTS_TO` or instance relationship, report partial evidence and avoid claiming instance reachability.
- Treat Scaleway snapshot public-state gaps as unknown unless `_ont_public` or provider-specific public fields are present.

### 4. Decide the cause

Classify the final answer into one or more categories:

- Direct public network
- Public front door to private backend
- Direct public policy/IAM
- Public control plane
- DNS/proxy-only signal
- Public data copy/share
- Unknown or partial graph coverage

Give confidence:

- **High**: raw directed path and relevant policy/rule fields prove the cause.
- **Medium**: ontology `EXPOSE`/`POINTS_TO` plus publicness evidence proves exposure, but raw cause is incomplete.
- **Low**: only DNS, module status, broad rollup, or partial topology exists.

## Output

Use an in-chat provenance report. Tag resources with `[[entity:<Label>:<id>|<name>]]`. Keep empty sections labeled "None found".

```text
# Public exposure investigation: <input>

## Target
- [[entity:<Label>:<id>|<name>]]: account/project/subscription <...>, region <...>

## Exposure surfaces
- <surface>: <domain/IP/listener/CDN/API gateway/ingress/bucket policy path>

## Backing resources
- <resource>: <bucket/instance/database/task/container/pod/service/function/control plane>

## Evidence
- DNS/proxy path: <record, value, proxied status, DNS_POINTS_TO target>
- Public IP path: <PublicIP/provider IP, POINTS_TO/RESERVED_BY target>
- Load balancer/ingress path: <LB, listener/rule, EXPOSE target, service/pod/container>
- Direct network path: <public IP, security group/firewall/NSG source, protocol, port>
- Policy/IAM path: <statement/binding/effect/principal/action/resource/condition>
- Storage/database/control-plane path: <public access fields and related rules>
- Module/analysis status: <success/degraded/stale/unknown>

## Conclusion
- Cause: <category>
- Confidence: <high | medium | low>, because <evidence/gaps>

## Next pivots
- <attack path, owner remediation, rule tuning, live validation, or "none">
```

## Verification

- Confirm each label/property/relationship appears in schema output or a saved model query before using it in the final query.
- Keep exploratory Cypher bounded with `LIMIT`.
- Use ontology edges to find likely paths, then inspect provider-specific fields to explain the cause.
- For CloudFront/S3, always inspect the direct S3 bucket policy branch even when a CloudFront alias is found.
- For Kubernetes, always name whether the exposure is control-plane, ingress/service/LB workload exposure, or only a risky but unproven host/node signal.
- For Cloud Run and Cloud Functions, require both public ingress/trigger and public invoker IAM before concluding anonymous invocation.
- If an `exposed_internet` rollup is missing but the raw path proves exposure, call out a likely analysis-job coverage issue rather than a Cartography ingestion bug.
- If the raw resource exists but a relationship is missing, distinguish schema/modeling gap from analysis-job gap.

## Anti-patterns

- Putting public-exposure cause analysis inside `investigate-ip`; IP ownership is a separate workflow.
- Stopping after DNS or CDN evidence without checking the backing resource.
- Treating `anonymous_access`, `exposed_internet`, or `_ont_public` as sufficient explanation without checking raw evidence when the user asks "why".
- Claiming direct backend exposure when the evidence only proves a public front door.
- Claiming an asset is not public when the relevant module is degraded, disabled, or stale.
- Treating Cloudflare DNS or a DNS CNAME as proof that the origin is directly reachable.
- Using unbounded graph walks.
- Interpolating unsafe user input into Cypher. Use parameters when the tool supports them; if a tool only accepts a query string, quote exact literals safely and keep probes narrow.

## References

- Public exposure Cypher templates: [`references/cypher-templates.md`](references/cypher-templates.md).
- Query discipline: `subimage-mcp:build-cypher-query`.
- Ownership lookup before exposure cause: `subimage-mcp:investigate-ip`.
- Impact pivot after cause is proven: `subimage-mcp:review-attack-path`.
