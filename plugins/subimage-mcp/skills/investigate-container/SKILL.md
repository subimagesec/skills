---
name: investigate-container
description: Investigate containers, images, and Kubernetes/EKS clusters in SubImage. Three modes - trace an image's provenance (registry, running workloads, source repo, CVEs); audit a cluster's internet exposure (services, ingress, public-IP nodes); or reconcile EKS node counts (filter terminated EC2 still linked to a cluster). Use when the user pastes an image URI/digest, asks "where does this image run", "what's exposed in cluster X", "audit cluster attack surface", or "why is the EKS node count wrong".
---

# Investigate containers and clusters

## What this does

One skill, three investigation modes over container/Kubernetes data in the SubImage graph:

- **Mode 1: Image provenance**: given an image URI / tag / digest, resolve the full chain: registry repository → running workloads (Container → Pod → Service, and Functions) → source repo (`PACKAGED_FROM`) → vulnerabilities.
- **Mode 2: Cluster exposure**: given a cluster name, enumerate the internet-facing surface: LoadBalancer/NodePort services, ingress, public-IP nodes, and everything flagged `exposed_internet=true`.
- **Mode 3: Node reconciliation**: when EKS node counts look inflated, separate `running` EC2 instances from terminated/stopped ones still linked by `MEMBER_OF_EKS_CLUSTER`.

## When to use

✅ User pastes an image reference and asks where it runs / what's wrong with it → **Mode 1**.
✅ "What's exposed in cluster X?" / "audit the attack surface of this EKS cluster" → **Mode 2**.
✅ "The chatbot says cluster X has N nodes but kubectl shows fewer" → **Mode 3**.

❌ A single CVE across the whole environment → `subimage-mcp:investigate-cve`.
❌ An attack path from a workload → `subimage-mcp:review-attack-path`.
❌ Ambiguous which mode: ask the user which of the three they want before running.

## Picking the mode

- Input looks like an image (`sha256:…`, `…/repo:tag`, registry URI) → Mode 1.
- Input is a cluster name, or the question is about exposure/attack surface → Mode 2.
- Question is about node counts looking wrong / stale graph data → Mode 3.

## Prerequisites

- Relevant module synced (`subimageListModules`): ECS/EKS/Kubernetes for cluster modes, ECR/GAR/GitLab for registry data, GitHub for source provenance.
- The CVE section of Mode 1 reads `:VulnerabilitySignal:Signal` nodes off the image; see the Step 5 template in `references/cypher-templates.md`.
- All Cypher follows `subimage-mcp:build-cypher-query` discipline: schema-validate labels/properties with `subimageGetNodesSchema` / `searchModelQueries` before trusting a template, then run with `subimageRunCypher`. Templates live in `references/cypher-templates.md` and are starting points, not guarantees.

## Reusable correctness note (applies to Modes 1-3)

The graph retains `EC2Instance` nodes with `state != 'running'` (terminated/stopped) that still carry `MEMBER_OF_EKS_CLUSTER` edges. **Any** count or listing of cluster nodes must filter `WHERE ec2.state = 'running'`, or it over-reports. This is the whole of Mode 3 and a guardrail for the node parts of Mode 2.

## Workflow

### Mode 1: Image provenance

Run the § Image Provenance queries from the templates, threading the resolved `image_id` from step 1 into the rest:

1. **Resolve the image node**: by digest, exact tag URI, or fuzzy partial match. If several images match, list them and ask which (or report all if fewer than ~5).
2. **Registry repository**: ECR / GCP Artifact Registry / GitLab.
3. **Running workloads**: Containers (`state = 'running'`) → Pod → Service for cluster-backed providers, or Container → Service directly for serverless (Cloud Run); plus Functions.
4. **Source origin**: `PACKAGED_FROM` → GitHub repo + Dockerfile path.
5. **Vulnerabilities**: `:VulnerabilitySignal:Signal` affecting the image, via the Step 5 CVE template. The template returns both open and accepted rows, so bucket them by the `status` column: an accepted CVE is one a human signed off on, and folding it into the open count overstates the backlog. Omit the `+<n> accepted` clause when there are none.

### Mode 2: Cluster exposure

Resolve the cluster first: if the user gives an EKS name, map it to the backing `KubernetesCluster` via `(:EKSCluster)-[:MAPS_TO]->(:KubernetesCluster)`. If the cluster is not found, say so and stop. Then run the § Cluster Exposure queries: cluster overview, namespaces, internet-exposed services (LoadBalancer/NodePort or `exposed_internet=true`), ingress, backing nodes with public IPs (reported from the running `EC2Instance` side, since `KubernetesNode` has no reliable join key to EC2), and all `exposed_internet=true` objects.

### Mode 3: Node reconciliation

Run the § Node Reconciliation query: per cluster, count total vs running vs stale (terminated/stopped) linked instances, flag an `anomaly_level` (`GHOST_CLUSTER` / `HIGH_STALENESS` / `STALE_EDGES` / `OK`), and list the stale instance ids. Note that Cartography retains terminated instances until its next cleanup pass; extreme staleness (>50%) hints the AWS module has not synced recently for that account.

## Output

In-chat report (no file output). Tag resources with `[[entity:<Label>:<id>|<name>]]`. Pick the section for the mode you ran; if a query returns nothing, keep the heading and write "None found".

```
# Container investigation: <mode>: <image / cluster>

## (Mode 1) Image provenance
- identity: digest <…>, tags <…>
- registry: [[entity:ECRRepository:<id>|<name>]]
- running workloads: [[entity:Container:<id>|<name>]] in pod <…> / service <…> (+<rest>)
- source: [[entity:GitHubRepository:<id>|<org/repo>]] (Dockerfile <path>)
- vulns: <n> open CVEs (<n> critical, <n> high)<, +<n> accepted>; top: <CVE> (CVSS <x>, KEV <y/n>)

## (Mode 2) Cluster exposure
- overview: API public access <y/n>, version <…>, region <…>
- exposed services: <n> (LoadBalancer/NodePort): [[entity:KubernetesService:<id>|<name>]] (+<rest>)
- ingress: <n>: hosts <…>
- backing public-IP instances (running): <n>: [[entity:EC2Instance:<id>|<id>]] <public-ip>
- exposed_internet=true objects: <n>

## (Mode 3) EKS node reconciliation
- [[entity:EKSCluster:<id>|<name>]]: running <r>, stale <s>, total <t> → <anomaly_level>
- stale edges: i-… (terminated), i-… (stopped) (+<rest>)

## Summary / risk notes
<one or two lines: biggest exposure, most stale cluster, or worst CVE>
```

## Anti-patterns

- Counting cluster nodes without `WHERE ec2.state = 'running'`. This is the documented cause of inflated counts; always filter.
- Trusting a template label/relationship without schema-validating it. Container/K8s labels (`Image`, `Container`, `ComputePod`, `KubernetesService`, `EKSCluster`) drift; an unvalidated `MATCH` silently returns nothing.
- Reading severity off `m.severity` or KEV off `m.kev`. The properties are `base_severity` (null often enough to need the score fallback) and `is_kev`.
- Running all three modes when the user asked about one. Pick the mode; offer the others as follow-ups.
- Reformatting raw query output as a wall-of-text table. Summarize and tag the notable resources.
- Unbounded queries. `LIMIT` everything.

## References

- Cypher templates: [`references/cypher-templates.md`](references/cypher-templates.md) (schema-validate before trusting).
- Query discipline: `subimage-mcp:build-cypher-query`.
- CVE deep-dive on a surfaced vulnerability: `subimage-mcp:investigate-cve`.
- Attack path from an exposed workload: `subimage-mcp:review-attack-path`.
- Tool guide (loaded by `subimageReadMe`): Domain 3 "Vulnerability Management" and the graph-query domain.
