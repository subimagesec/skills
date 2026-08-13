# Cypher templates: container & cluster investigation

Starting-point queries for `investigate-container`, grouped by mode. **Schema-validate before trusting**: run `subimageGetNodesSchema` (and `searchModelQueries`) for the labels each query uses and adjust to the live schema.

Two execution rules apply to every template here:

- **Inline your values as literals.** `subimageRunCypher` accepts one self-contained statement and no parameter bindings, so a `$param` left in the query fails with `ParameterMissing`. The `'<PLACEHOLDER>'` slots below are substitution points: escape backslashes and single quotes before substituting, because ARNs and fully-qualified GCP/Azure ids carry both.
- **The tool returns at most 100 rows**, whatever `LIMIT` you write; it takes `min(its cap, your limit)`. A `LIMIT 500` is a statement of intent, not a page size. It also returns `total_count`, so when the page is partial, quote that rather than presenting the page as the whole set. Keep every query `LIMIT`-bounded regardless.

Reused guardrail: any node count/listing for a cluster must filter `WHERE ec2.state = 'running'`; terminated/stopped instances stay linked via `MEMBER_OF_EKS_CLUSTER`.

## Image Provenance (Mode 1)

### Step 1: Resolve the image node

By digest:

```cypher
MATCH (img:Image)
WHERE img._ont_digest = '<IMAGE_DIGEST>'
OPTIONAL MATCH (tag:ImageTag)-[:IMAGE]->(img)
RETURN img.id AS image_id, img._ont_digest AS digest, img.uri AS image_uri,
       collect(DISTINCT coalesce(tag._ont_uri, tag.uri)) AS tags
LIMIT 10
```

By exact tag URI (swap `= '<TAG_URI>'` for `CONTAINS '<PARTIAL_URI>'` to fuzzy-match):

```cypher
MATCH (tag:ImageTag)-[:IMAGE]->(img:Image)
WHERE coalesce(tag._ont_uri, tag.uri) = '<TAG_URI>'
RETURN img.id AS image_id, img._ont_digest AS digest, img.uri AS image_uri,
       collect(DISTINCT coalesce(tag._ont_uri, tag.uri)) AS tags
LIMIT 10
```

Fallback directly on the Image URI:

```cypher
MATCH (img:Image)
WHERE img.uri CONTAINS '<PARTIAL_URI>'
OPTIONAL MATCH (tag:ImageTag)-[:IMAGE]->(img)
RETURN img.id AS image_id, img._ont_digest AS digest, img.uri AS image_uri,
       collect(DISTINCT coalesce(tag._ont_uri, tag.uri)) AS tags
LIMIT 10
```

### Step 2: Registry repository (ECR / GAR / GitLab)

```cypher
MATCH (img:Image) WHERE img.id = '<IMAGE_ID>'
OPTIONAL MATCH (img)<-[:IMAGE]-(ecr:AWSECRRepositoryImage)<-[:REPO_IMAGE]-(repo:AWSECRRepository)
OPTIONAL MATCH (img)<-[:IMAGE]-(gar:GCPArtifactRegistryRepositoryImage)<-[:REPO_IMAGE]-(garRepo:GCPArtifactRegistryRepository)
OPTIONAL MATCH (img)<-[:REFERENCES]-(gitTag:GitLabContainerRepositoryTag)<-[:HAS_TAG]-(gitRepo:GitLabContainerRepository)
RETURN img.id AS image_id,
       repo.name AS ecr_repo_name, repo.repo_uri AS ecr_repo_uri, ecr.uri AS ecr_image_uri,
       garRepo.id AS gar_repo_id, garRepo.registry_uri AS gar_registry_uri,
       gitRepo.id AS gitlab_repo_id, gitTag.repository_location AS gitlab_location
LIMIT 10
```

### Step 3: Running workloads

`WORKLOAD_PARENT` points at a `ComputePod` for cluster-backed providers (ECS, Kubernetes) **or** directly at a `ComputeService` for serverless providers (GCP Cloud Run). Resolve the service from either path so direct-parent workloads keep their service context:

```cypher
MATCH (container:Container)-[:RESOLVED_IMAGE|HAS_IMAGE]->(img:Image)
WHERE img.id = '<IMAGE_ID>'
  AND toLower(COALESCE(container._ont_state, '')) = 'running'
OPTIONAL MATCH (container)-[:WORKLOAD_PARENT]->(pod:ComputePod)
OPTIONAL MATCH (pod)-[:WORKLOAD_PARENT]->(svcViaPod:ComputeService)
OPTIONAL MATCH (container)-[:WORKLOAD_PARENT]->(svcDirect:ComputeService)
RETURN container._ont_name AS container_name, container.id AS container_id,
       container._ont_state AS state, pod._ont_name AS pod_name,
       coalesce(svcViaPod._ont_name, svcDirect._ont_name) AS service_name
ORDER BY service_name, pod_name
LIMIT 50
```

Functions running the image:

```cypher
MATCH (fn:Function)-[:RESOLVED_IMAGE]->(img:Image) WHERE img.id = '<IMAGE_ID>'
RETURN fn.id AS function_id, fn._ont_name AS function_name, fn.runtime AS runtime
LIMIT 20
```

### Step 4: Source origin

```cypher
MATCH (img:Image)-[r:PACKAGED_FROM]->(repo:GitHubRepository) WHERE img.id = '<IMAGE_ID>'
RETURN repo.fullname AS github_repo, repo.url AS repo_url,
       r.dockerfile_path AS dockerfile_path, properties(r) AS packaged_from_properties
LIMIT 10
```

### Step 5: Vulnerabilities

Vulnerabilities on an image are `:VulnerabilitySignal:Signal` nodes, each a
current `(cve_id, service_image)` observation pointing at one `:CVEMetadata`:

```cypher
MATCH (v:VulnerabilitySignal:Signal)-[:AFFECTS]->(img:Image)
      WHERE img.id = '<IMAGE_ID>' AND v.status IN ['active', 'accepted']
MATCH (v)-[:INSTANCE_OF]->(m:CVEMetadata)
OPTIONAL MATCH (m)-[:ENRICHES]->(:TrivyImageFinding:CVE)-[:AFFECTS]->(pkg:PackageVersion)
      WHERE EXISTS { (pkg)-[:DEPLOYED]->(img) }
RETURN m.id AS cve_id, m.description AS description,
       CASE
         WHEN m.base_severity IS NOT NULL THEN toUpper(m.base_severity)
         WHEN m.base_score >= 9 THEN 'CRITICAL'
         WHEN m.base_score >= 7 THEN 'HIGH'
         WHEN m.base_score >= 4 THEN 'MEDIUM'
         WHEN m.base_score > 0 THEN 'LOW'
         ELSE 'UNKNOWN'
       END AS severity,
       m.base_score AS cvss_score, m.epss_score AS epss_score,
       coalesce(m.is_kev, false) AS kev, v.status AS status,
       collect(DISTINCT pkg.name) AS affected_packages
ORDER BY coalesce(m.base_score, -1) DESC
LIMIT 50
```

Property names to keep straight, because the obvious guesses are wrong: severity
is `base_severity` (null often enough to need the score fallback), the CVSS score
is `base_score`, and KEV membership is `is_kev`. Packages are `:PackageVersion`,
not `:Package`, and the `EXISTS` clause keeps the join to packages actually
deployed on this image.

`status IN ['active','accepted']` matches what the product reads. Accepted means
a human signed off on the risk, so return `status` and label those rows rather
than folding them into an "open vulnerabilities" count.

This template deliberately carries no fix version. It aggregates packages per
CVE, and a fix is per package: `TrivyFix.version` reached through
`(pkg)-[:SHOULD_UPDATE_TO]->(:TrivyFix)-[:APPLIES_TO]->(finding)`, which needs
the finding bound per row. Use `subimage-mcp:investigate-cve` step 2 when the
question is "what do we upgrade to". Do not reach for `pkg.fixed_version`: the
property does not exist and returns null on every row.

## Cluster Exposure (Mode 2)

### Cluster overview

```cypher
MATCH (c:KubernetesCluster) WHERE c.name = '<CLUSTER_NAME>'
OPTIONAL MATCH (eks:AWSEKSCluster)-[:MAPS_TO]->(c)
RETURN c.name AS cluster, c.id AS cluster_id,
       eks.name AS eks_cluster, eks.region AS region,
       eks.exposed_internet AS eks_api_exposed,
       eks.endpoint_public_access AS endpoint_public_access, eks.version AS version
LIMIT 5
```

### Namespaces

```cypher
MATCH (c:KubernetesCluster)-[:RESOURCE]->(ns:KubernetesNamespace) WHERE c.name = '<CLUSTER_NAME>'
RETURN ns.name AS namespace, ns.id AS namespace_id ORDER BY ns.name
LIMIT 500
```

### Internet-exposed services

```cypher
MATCH (c:KubernetesCluster)-[:RESOURCE]->(svc:KubernetesService)
WHERE c.name = '<CLUSTER_NAME>'
  AND (svc.type IN ['LoadBalancer', 'NodePort'] OR svc.exposed_internet = true)
OPTIONAL MATCH (svc)-[:USES_LOAD_BALANCER]->(lb)
RETURN svc.name AS service, svc.namespace AS namespace, svc.type AS service_type,
       svc.cluster_ip AS cluster_ip, svc.load_balancer_ip AS lb_ip,
       svc.exposed_internet AS exposed_internet, svc.exposed_internet_type AS exposure_type,
       lb.dnsname AS aws_lb_dns, lb.scheme AS lb_scheme
ORDER BY svc.namespace, svc.name
LIMIT 500
```

### Ingress resources

```cypher
MATCH (c:KubernetesCluster)-[:RESOURCE]->(ing:KubernetesIngress) WHERE c.name = '<CLUSTER_NAME>'
RETURN ing.name AS ingress, ing.namespace AS namespace,
       ing.ingress_class_name AS ingress_class, ing.host_names AS hosts,
       ing.load_balancer_dns_names AS lb_dns_names, ing.ingress_group_name AS alb_group
ORDER BY ing.namespace, ing.name
LIMIT 500
```

### Backing nodes with public IPs (running EC2 only)

`KubernetesNode` has no edge or shared key to `AWSEC2Instance` in the schema (only `RESOURCE`→cluster and `RUNS_ON`↔pod), so joining the two produces a cartesian product and inflates counts. Report the cluster's internet-exposed backing instances from the EC2 side instead, without a node-name join:

```cypher
MATCH (c:KubernetesCluster) WHERE c.name = '<CLUSTER_NAME>'
MATCH (eks:AWSEKSCluster)-[:MAPS_TO]->(c)
MATCH (ec2:AWSEC2Instance)-[:MEMBER_OF_EKS_CLUSTER]->(eks)
WHERE ec2.state = 'running' AND ec2.publicipaddress IS NOT NULL
RETURN ec2.instanceid AS ec2_instance, ec2.publicipaddress AS public_ip,
       ec2.exposed_internet AS ec2_exposed, ec2.region AS region
ORDER BY ec2.instanceid
LIMIT 200
```

For Kubernetes node inventory (separately, no EC2 attribution): `MATCH (c:KubernetesCluster)-[:RESOURCE]->(n:KubernetesNode) WHERE c.name = '<CLUSTER_NAME>' RETURN n.name, n.id ORDER BY n.name LIMIT 500`.

### All exposed_internet=true objects

```cypher
MATCH (c:KubernetesCluster)-[:RESOURCE]->(obj)
WHERE c.name = '<CLUSTER_NAME>' AND obj.exposed_internet = true
RETURN labels(obj) AS node_labels, obj.name AS name,
       coalesce(obj.namespace, 'cluster-scoped') AS namespace,
       obj.exposed_internet_type AS exposure_type, obj.id AS id
ORDER BY namespace, name
LIMIT 500
```

## Node Reconciliation (Mode 3)

Per-cluster reconciliation with anomaly flags:

```cypher
MATCH (a:AWSAccount)-[:RESOURCE]->(eks:AWSEKSCluster)
OPTIONAL MATCH (ec2:AWSEC2Instance)-[:MEMBER_OF_EKS_CLUSTER]->(eks)
WITH a, eks,
  count(ec2) AS total_nodes,
  count(CASE WHEN ec2.state = 'running' THEN 1 END) AS running_nodes,
  count(CASE WHEN ec2.state IN ['terminated', 'stopped', 'shutting-down', 'stopping'] THEN 1 END) AS stale_nodes,
  collect(CASE WHEN ec2.state <> 'running' AND ec2.state IS NOT NULL
    THEN {instanceid: ec2.instanceid, state: ec2.state} END) AS stale_instances
RETURN a.name AS aws_account, a.id AS aws_account_id,
  eks.name AS cluster_name, eks.region AS region,
  total_nodes, running_nodes, stale_nodes,
  CASE
    WHEN running_nodes = 0 AND total_nodes > 0 THEN 'GHOST_CLUSTER'
    WHEN total_nodes > 0 AND toFloat(stale_nodes) / total_nodes > 0.1 THEN 'HIGH_STALENESS'
    WHEN stale_nodes > 0 THEN 'STALE_EDGES'
    ELSE 'OK'
  END AS anomaly_level,
  stale_instances
ORDER BY stale_nodes DESC, a.name, eks.name
LIMIT 200
```

Correct node-count pattern for any "how many nodes" question:

```cypher
MATCH (ec2:AWSEC2Instance)-[:MEMBER_OF_EKS_CLUSTER]->(eks:AWSEKSCluster)
WHERE ec2.state = 'running'
RETURN eks.name AS cluster, count(ec2) AS node_count
ORDER BY eks.name
LIMIT 200
```
