# Cypher templates: public exposure investigation

Starting-point queries for `investigate-public-exposure`. Schema-validate first with `subimageGetNodesSchema` and `searchModelQueries`, then adjust labels, properties, and relationship directions to the live schema. Keep every probe bounded.

Templates use `$value` for readability. If the active MCP tool supports parameters, pass `$value` as a parameter. If the tool only accepts a query string, quote the exact literal safely and keep the query narrow.

## Cross-provider DNS/front-door pivot

Use when the input is a domain, hostname, load-balancer DNS name, CloudFront alias, API hostname, or provider default hostname.

```cypher
MATCH (record:DNSRecord)
WHERE record.name = $value
   OR record.value = $value
   OR record.id = $value
OPTIONAL MATCH (record)-[r_dns:DNS_POINTS_TO]->(target)
RETURN labels(record) AS record_labels,
       record.id AS record_id,
       record.name AS record_name,
       record.value AS record_value,
       record.type AS record_type,
       type(r_dns) AS relationship,
       labels(target) AS target_labels,
       target.id AS target_id,
       target.name AS target_name,
       target.dnsname AS target_dnsname,
       target.domain_name AS target_domain_name,
       target.exposed_internet AS target_exposed_internet,
       target.exposed_internet_type AS target_exposed_internet_type
LIMIT 100
```

## Cloudflare DNS and proxy signal

Use when the target may be a Cloudflare-managed DNS record. A proxied record proves Cloudflare is the public edge; it does not prove the origin is directly public.

```cypher
MATCH (record:CloudflareDNSRecord:DNSRecord)
WHERE record.name = $value
   OR record.value = $value
   OR record.id = $value
OPTIONAL MATCH (record)-[r_dns:DNS_POINTS_TO]->(target)
RETURN record.id AS record_id,
       record.name AS record_name,
       record.value AS record_value,
       record.type AS record_type,
       record.proxied AS proxied,
       record.proxiable AS proxiable,
       type(r_dns) AS relationship,
       labels(target) AS target_labels,
       target.id AS target_id,
       target.name AS target_name,
       target.exposed_internet AS target_exposed_internet,
       target.exposed_internet_type AS target_exposed_internet_type
LIMIT 100
```

## PublicIP ontology pivot

Use for IP addresses and provider public IP resources. `POINTS_TO` identifies the resource the IP reaches; `RESERVED_BY` identifies the provider allocation resource.

```cypher
MATCH (ip:PublicIP)
WHERE ip.id = $value
   OR ip.name = $value
   OR ip.address = $value
   OR ip.ip_address = $value
OPTIONAL MATCH (ip)-[r_points:POINTS_TO]->(target)
OPTIONAL MATCH (ip)-[r_reserved:RESERVED_BY]->(reservation)
RETURN ip.id AS public_ip_id,
       ip.name AS public_ip_name,
       ip.address AS public_ip_address,
       ip.ip_address AS provider_ip_address,
       type(r_points) AS points_relationship,
       labels(target) AS target_labels,
       target.id AS target_id,
       target.name AS target_name,
       target.exposed_internet AS target_exposed_internet,
       target.exposed_internet_type AS target_exposed_internet_type,
       type(r_reserved) AS reserved_relationship,
       labels(reservation) AS reservation_labels,
       reservation.id AS reservation_id,
       reservation.name AS reservation_name
LIMIT 100
```

## LoadBalancer EXPOSE ontology pivot

Use after resolving a load balancer, target service, instance, pod, or container. `EXPOSE` is produced by analysis jobs and should be paired with provider-specific proof when explaining why.

```cypher
MATCH (lb:LoadBalancer)
WHERE lb.id = $value
   OR lb.name = $value
   OR lb.dnsname = $value
   OR lb.dns_name = $value
   OR lb.ip_address = $value
OPTIONAL MATCH (lb)-[r_expose:EXPOSE]->(target)
RETURN labels(lb) AS load_balancer_labels,
       lb.id AS load_balancer_id,
       lb.name AS load_balancer_name,
       lb.dnsname AS load_balancer_dnsname,
       lb.scheme AS scheme,
       lb.type AS load_balancer_type,
       lb.exposed_internet AS load_balancer_exposed_internet,
       lb.exposed_internet_type AS load_balancer_exposed_internet_type,
       r_expose.exposure_type AS exposure_type,
       labels(target) AS target_labels,
       target.id AS target_id,
       target.name AS target_name,
       target.exposed_internet AS target_exposed_internet,
       target.exposed_internet_type AS target_exposed_internet_type
LIMIT 100
```

## AWS CloudFront/S3 public exposure cause

Use when the user asks whether a domain or bucket is public because of CloudFront, direct S3 bucket policy, or both. Validate the directed `CloudFrontDistribution` to `S3Bucket` and `S3Bucket` to `S3PolicyStatement` relationships before running.

```cypher
MATCH (b:S3Bucket)
WHERE b.name = $value OR b.id = $value
OPTIONAL MATCH (cf:CloudFrontDistribution)-[:SERVES_FROM]->(b)
OPTIONAL MATCH (b)-[:POLICY_STATEMENT]->(stmt:S3PolicyStatement)
RETURN 'bucket_name_or_id' AS match_path,
       b.id AS bucket_id,
       b.name AS bucket_name,
       b.anonymous_access AS bucket_anonymous_access,
       b.anonymous_actions AS bucket_anonymous_actions,
       b.block_public_policy AS bucket_block_public_policy,
       b.restrict_public_buckets AS bucket_restrict_public_buckets,
       b.block_public_acls AS bucket_block_public_acls,
       b.ignore_public_acls AS bucket_ignore_public_acls,
       cf.id AS cloudfront_id,
       cf.distribution_id AS distribution_id,
       cf.domain_name AS cloudfront_domain,
       cf.aliases AS cloudfront_aliases,
       cf.enabled AS cloudfront_enabled,
       cf.status AS cloudfront_status,
       stmt.id AS statement_id,
       stmt.sid AS statement_sid,
       stmt.effect AS statement_effect,
       stmt.principal AS statement_principal,
       stmt.action AS statement_action,
       stmt.resource AS statement_resource,
       stmt.condition AS statement_condition
UNION
MATCH (cf:CloudFrontDistribution)-[:SERVES_FROM]->(b:S3Bucket)
WHERE cf.domain_name = $value
   OR ANY(alias IN coalesce(cf.aliases, []) WHERE alias = $value)
OPTIONAL MATCH (b)-[:POLICY_STATEMENT]->(stmt:S3PolicyStatement)
RETURN 'cloudfront_domain_or_alias' AS match_path,
       b.id AS bucket_id,
       b.name AS bucket_name,
       b.anonymous_access AS bucket_anonymous_access,
       b.anonymous_actions AS bucket_anonymous_actions,
       b.block_public_policy AS bucket_block_public_policy,
       b.restrict_public_buckets AS bucket_restrict_public_buckets,
       b.block_public_acls AS bucket_block_public_acls,
       b.ignore_public_acls AS bucket_ignore_public_acls,
       cf.id AS cloudfront_id,
       cf.distribution_id AS distribution_id,
       cf.domain_name AS cloudfront_domain,
       cf.aliases AS cloudfront_aliases,
       cf.enabled AS cloudfront_enabled,
       cf.status AS cloudfront_status,
       stmt.id AS statement_id,
       stmt.sid AS statement_sid,
       stmt.effect AS statement_effect,
       stmt.principal AS statement_principal,
       stmt.action AS statement_action,
       stmt.resource AS statement_resource,
       stmt.condition AS statement_condition
LIMIT 100
```

## AWS direct S3 bucket policy statements

Use when the target bucket is already known and the answer requires direct policy-statement details.

```cypher
MATCH (b:S3Bucket)-[:POLICY_STATEMENT]->(stmt:S3PolicyStatement)
WHERE b.name = $value OR b.id = $value
RETURN b.id AS bucket_id,
       b.name AS bucket_name,
       b.anonymous_access AS bucket_anonymous_access,
       b.anonymous_actions AS bucket_anonymous_actions,
       b.block_public_policy AS bucket_block_public_policy,
       b.restrict_public_buckets AS bucket_restrict_public_buckets,
       stmt.id AS statement_id,
       stmt.sid AS statement_sid,
       stmt.effect AS statement_effect,
       stmt.principal AS statement_principal,
       stmt.action AS statement_action,
       stmt.resource AS statement_resource,
       stmt.condition AS statement_condition
LIMIT 100
```

## AWS EC2 direct security-group exposure

Use for EC2 instances, public IPs, and "which security group/rule exposes this" questions. Include IPv6-style all-internet ranges when represented as `AWSIpRange`.

```cypher
MATCH (cidr:AWSIpRange)-[:MEMBER_OF_IP_RULE]->(rule:AWSIpPermissionInbound)-[:MEMBER_OF_EC2_SECURITY_GROUP]->(sg:EC2SecurityGroup)
MATCH (sg)<-[:MEMBER_OF_EC2_SECURITY_GROUP|NETWORK_INTERFACE*..2]-(instance:EC2Instance)
WHERE (instance.id = $value
    OR instance.instanceid = $value
    OR instance.name = $value
    OR instance.publicipaddress = $value
    OR instance.publicdnsname = $value)
  AND cidr.range IN ['0.0.0.0/0', '::/0']
RETURN instance.id AS instance_id,
       instance.name AS instance_name,
       instance.publicipaddress AS public_ip,
       instance.publicdnsname AS public_dns,
       instance.exposed_internet AS exposed_internet,
       instance.exposed_internet_type AS exposed_internet_type,
       sg.id AS security_group_id,
       sg.name AS security_group_name,
       rule.id AS rule_id,
       rule.protocol AS protocol,
       rule.fromport AS from_port,
       rule.toport AS to_port,
       cidr.range AS source_range
LIMIT 100
```

## AWS ALB/NLB/classic ELB exposure and targets

Use for AWS load balancers. For ALB/classic ELB, security group rules help prove public listener reachability. For NLB, internet-facing scheme plus listener is often the key front-door evidence.

```cypher
MATCH (lb:AWSLoadBalancerV2:LoadBalancer)
WHERE lb.id = $value
   OR lb.name = $value
   OR lb.dnsname = $value
   OR lb.arn = $value
OPTIONAL MATCH (lb)-[:ELBV2_LISTENER]->(listener:ELBV2Listener)
OPTIONAL MATCH (lb)-[:MEMBER_OF_EC2_SECURITY_GROUP]->(sg:EC2SecurityGroup)<-[:MEMBER_OF_EC2_SECURITY_GROUP]-(rule:AWSIpPermissionInbound)<-[:MEMBER_OF_IP_RULE]-(cidr:AWSIpRange)
OPTIONAL MATCH (lb)-[r_expose:EXPOSE]->(target)
RETURN lb.id AS load_balancer_id,
       lb.name AS load_balancer_name,
       lb.dnsname AS dnsname,
       lb.scheme AS scheme,
       lb.type AS load_balancer_type,
       lb.exposed_internet AS exposed_internet,
       lb.exposed_internet_type AS exposed_internet_type,
       listener.id AS listener_id,
       listener.port AS listener_port,
       listener.protocol AS listener_protocol,
       sg.id AS security_group_id,
       rule.id AS rule_id,
       rule.protocol AS rule_protocol,
       rule.fromport AS rule_from_port,
       rule.toport AS rule_to_port,
       cidr.range AS source_range,
       r_expose.exposure_type AS exposure_type,
       labels(target) AS target_labels,
       target.id AS target_id,
       target.name AS target_name
LIMIT 100
```

For classic ELB, validate the classic labels and run the same shape with `AWSLoadBalancer` / `ELBListener`.

## AWS ECS behind load balancer

Use when a load balancer or ECS container/service/task is the suspected exposure path. This reconstructs the common ALB/NLB to private IP to ECS task/container chain when direct `LoadBalancer-[:EXPOSE]->Container` edges are absent.

```cypher
MATCH (lb:AWSLoadBalancerV2:LoadBalancer)-[r_expose:EXPOSE]->(private_ip:EC2PrivateIp)<-[:PRIVATE_IP_ADDRESS]-(eni:NetworkInterface)<-[:NETWORK_INTERFACE]-(task:ECSTask)
WHERE lb.id = $value
   OR lb.name = $value
   OR lb.dnsname = $value
   OR task.id = $value
OPTIONAL MATCH (task)-[:HAS_CONTAINER]->(container_from_task:ECSContainer)
OPTIONAL MATCH (container_from_parent:ECSContainer)-[:WORKLOAD_PARENT]->(task)
WITH lb, r_expose, private_ip, eni, task, coalesce(container_from_task, container_from_parent) AS container
OPTIONAL MATCH (task)-[:WORKLOAD_PARENT]->(service:ECSService)
RETURN lb.id AS load_balancer_id,
       lb.name AS load_balancer_name,
       lb.dnsname AS load_balancer_dnsname,
       lb.scheme AS scheme,
       r_expose.exposure_type AS exposure_type,
       private_ip.id AS private_ip_id,
       eni.id AS network_interface_id,
       task.id AS task_id,
       service.id AS service_id,
       service.name AS service_name,
       container.id AS container_id,
       container.name AS container_name,
       container.exposed_internet AS container_exposed_internet,
       container.exposed_internet_type AS container_exposed_internet_type
LIMIT 100
```

## AWS EKS control-plane exposure

Use for EKS public endpoint questions. This proves control-plane exposure, not workload exposure.

```cypher
MATCH (cluster:EKSCluster)
WHERE cluster.id = $value
   OR cluster.name = $value
   OR cluster.arn = $value
OPTIONAL MATCH (cluster)-[r_cluster]-(k8s:KubernetesCluster)
RETURN cluster.id AS eks_cluster_id,
       cluster.name AS eks_cluster_name,
       cluster.arn AS eks_cluster_arn,
       cluster.endpoint AS endpoint,
       cluster.endpoint_public_access AS endpoint_public_access,
       cluster.endpoint_private_access AS endpoint_private_access,
       cluster.public_access_cidrs AS public_access_cidrs,
       cluster.exposed_internet AS exposed_internet,
       cluster.exposed_internet_type AS exposed_internet_type,
       cluster._ont_control_plane_public_access AS ont_control_plane_public_access,
       type(r_cluster) AS kubernetes_mapping_relationship,
       k8s.id AS kubernetes_cluster_id,
       k8s.name AS kubernetes_cluster_name
LIMIT 100
```

## Kubernetes ingress/service workload exposure

Use for Kubernetes workloads. Start from service or ingress, then show load balancer, service target, pod, and container evidence.

```cypher
MATCH (svc:KubernetesService)
WHERE svc.id = $value
   OR svc.name = $value
   OR svc.load_balancer_ip = $value
OPTIONAL MATCH (svc)-[:USES_LOAD_BALANCER]->(lb:LoadBalancer)
OPTIONAL MATCH (svc)-[:TARGETS]->(pod:KubernetesPod)
OPTIONAL MATCH (pod)-[:CONTAINS]->(container_from_pod:KubernetesContainer)
OPTIONAL MATCH (container_from_parent:KubernetesContainer)-[:WORKLOAD_PARENT]->(pod)
WITH svc, lb, pod, coalesce(container_from_pod, container_from_parent) AS container
RETURN svc.id AS service_id,
       svc.name AS service_name,
       svc.type AS service_type,
       svc.load_balancer_ip AS service_load_balancer_ip,
       svc.load_balancer_ingress AS service_load_balancer_ingress,
       svc.exposed_internet AS service_exposed_internet,
       svc.exposed_internet_type AS service_exposed_internet_type,
       labels(lb) AS load_balancer_labels,
       lb.id AS load_balancer_id,
       lb.name AS load_balancer_name,
       lb.dnsname AS load_balancer_dnsname,
       lb.exposed_internet AS load_balancer_exposed_internet,
       pod.id AS pod_id,
       pod.name AS pod_name,
       pod.host_network AS pod_host_network,
       pod.exposed_internet AS pod_exposed_internet,
       pod.exposed_internet_type AS pod_exposed_internet_type,
       container.id AS container_id,
       container.name AS container_name,
       container.exposed_internet AS container_exposed_internet,
       container.exposed_internet_type AS container_exposed_internet_type
LIMIT 100
```

```cypher
MATCH (ingress:KubernetesIngress)
WHERE ingress.id = $value
   OR ingress.name = $value
   OR $value IN coalesce(ingress.host_names, [])
   OR $value IN coalesce(ingress.load_balancer_dns_names, [])
OPTIONAL MATCH (ingress)-[:USES_LOAD_BALANCER]->(lb:LoadBalancer)
OPTIONAL MATCH (ingress)-[:TARGETS]->(svc:KubernetesService)
OPTIONAL MATCH (svc)-[:TARGETS]->(pod:KubernetesPod)
OPTIONAL MATCH (pod)-[:CONTAINS]->(container_from_pod:KubernetesContainer)
OPTIONAL MATCH (container_from_parent:KubernetesContainer)-[:WORKLOAD_PARENT]->(pod)
WITH ingress, lb, svc, pod, coalesce(container_from_pod, container_from_parent) AS container
RETURN ingress.id AS ingress_id,
       ingress.name AS ingress_name,
       ingress.host_names AS host_names,
       ingress.load_balancer_dns_names AS load_balancer_dns_names,
       ingress.ingress_class_name AS ingress_class_name,
       labels(lb) AS load_balancer_labels,
       lb.id AS load_balancer_id,
       lb.name AS load_balancer_name,
       lb.dnsname AS load_balancer_dnsname,
       lb.exposed_internet AS load_balancer_exposed_internet,
       svc.id AS service_id,
       svc.name AS service_name,
       svc.type AS service_type,
       svc.exposed_internet AS service_exposed_internet,
       pod.id AS pod_id,
       pod.name AS pod_name,
       pod.exposed_internet AS pod_exposed_internet,
       container.id AS container_id,
       container.name AS container_name,
       container.exposed_internet AS container_exposed_internet
LIMIT 100
```

## Kubernetes Gateway API exposure

Use when a tenant uses Gateway API. Gateway and route edges identify routing intent; still inspect the backing service/load balancer path.

```cypher
MATCH (gateway:KubernetesGateway)-[:ROUTES]->(route:KubernetesHTTPRoute)-[:TARGETS]->(svc:KubernetesService)
WHERE gateway.id = $value
   OR gateway.name = $value
   OR route.id = $value
   OR route.name = $value
   OR svc.id = $value
   OR svc.name = $value
OPTIONAL MATCH (svc)-[:USES_LOAD_BALANCER]->(lb:LoadBalancer)
OPTIONAL MATCH (svc)-[:TARGETS]->(pod:KubernetesPod)
RETURN gateway.id AS gateway_id,
       gateway.name AS gateway_name,
       route.id AS route_id,
       route.name AS route_name,
       route.hostnames AS route_hostnames,
       svc.id AS service_id,
       svc.name AS service_name,
       svc.type AS service_type,
       svc.exposed_internet AS service_exposed_internet,
       labels(lb) AS load_balancer_labels,
       lb.id AS load_balancer_id,
       lb.name AS load_balancer_name,
       lb.exposed_internet AS load_balancer_exposed_internet,
       pod.id AS pod_id,
       pod.name AS pod_name,
       pod.exposed_internet AS pod_exposed_internet
LIMIT 100
```

## AWS API Gateway and Lambda public access

Use for API Gateway or Lambda exposure. REST API modeling is usually richer than API Gateway v2 modeling; report that gap if route/integration evidence is absent.

```cypher
MATCH (api:APIGatewayRestAPI)
WHERE api.id = $value
   OR api.name = $value
   OR api.arn = $value
   OR api.execution_arn = $value
OPTIONAL MATCH (api)-[:ASSOCIATED_WITH]->(stage:APIGatewayStage)
OPTIONAL MATCH (api)-[:RESOURCE]->(resource:APIGatewayResource)
OPTIONAL MATCH (resource)<-[:HAS_METHOD]-(method:APIGatewayMethod)
OPTIONAL MATCH (resource)<-[:HAS_INTEGRATION]-(integration:APIGatewayIntegration)
RETURN api.id AS api_id,
       api.name AS api_name,
       api.endpoint_type AS endpoint_type,
       api.disableexecuteapiendpoint AS disable_execute_api_endpoint,
       api.exposed_internet AS exposed_internet,
       api.anonymous_access AS anonymous_access,
       api.anonymous_actions AS anonymous_actions,
       stage.id AS stage_id,
       stage.name AS stage_name,
       resource.id AS resource_id,
       resource.path AS resource_path,
       method.id AS method_id,
       method.httpmethod AS http_method,
       method.authorization_type AS authorization_type,
       integration.id AS integration_id,
       integration.type AS integration_type,
       integration.uri AS integration_uri,
       integration.connection_type AS integration_connection_type
LIMIT 100
```

```cypher
MATCH (fn:AWSLambda:Function)
WHERE fn.id = $value
   OR fn.name = $value
   OR fn.arn = $value
RETURN fn.id AS function_id,
       fn.name AS function_name,
       fn.arn AS function_arn,
       fn.anonymous_access AS anonymous_access,
       fn.anonymous_actions AS anonymous_actions,
       fn.exposed_internet AS exposed_internet,
       fn.exposed_internet_type AS exposed_internet_type
LIMIT 100
```

## GCP Cloud Run and Cloud Functions public invocation

Use for GCP serverless public-invocation questions. Public Cloud Run invocation needs public ingress and public invoker IAM; do not treat ingress alone as anonymous invocation.

```cypher
MATCH (svc:GCPCloudRunService)
WHERE svc.id = $value
   OR svc.name = $value
   OR svc.uri = $value
OPTIONAL MATCH (svc)<-[:APPLIES_TO]-(binding:GCPPolicyBinding)
RETURN svc.id AS service_id,
       svc.name AS service_name,
       svc.location AS location,
       svc.uri AS uri,
       svc.ingress AS ingress,
       svc.exposed_internet AS exposed_internet,
       svc.exposed_internet_type AS exposed_internet_type,
       binding.id AS binding_id,
       binding.role AS binding_role,
       binding.is_public AS binding_is_public,
       binding.has_condition AS binding_has_condition,
       binding.members AS binding_members
LIMIT 100
```

```cypher
MATCH (fn:GCPCloudFunction:Function)
WHERE fn.id = $value
   OR fn.name = $value
   OR fn.https_trigger_url = $value
OPTIONAL MATCH (fn)<-[:APPLIES_TO]-(binding:GCPPolicyBinding)
RETURN fn.id AS function_id,
       fn.name AS function_name,
       fn.https_trigger_url AS https_trigger_url,
       fn.exposed_internet AS exposed_internet,
       fn.exposed_internet_type AS exposed_internet_type,
       binding.id AS binding_id,
       binding.role AS binding_role,
       binding.is_public AS binding_is_public,
       binding.has_condition AS binding_has_condition,
       binding.members AS binding_members
LIMIT 100
```

## GCP load balancer and direct compute exposure

Use for GCP external load balancers and instances. Include deny-rule checks before making high-confidence direct-exposure claims.

```cypher
MATCH (backend:GCPBackendService)-[:ROUTES_TO]->(group:GCPInstanceGroup)-[:HAS_MEMBER]->(instance:GCPInstance)
WHERE backend.id = $value
   OR backend.name = $value
   OR instance.id = $value
   OR instance.name = $value
OPTIONAL MATCH (fr:GCPForwardingRule)
WHERE fr.target = backend.self_link OR fr.target = backend.id
RETURN backend.id AS backend_service_id,
       backend.name AS backend_service_name,
       backend.load_balancing_scheme AS backend_load_balancing_scheme,
       fr.id AS forwarding_rule_id,
       fr.name AS forwarding_rule_name,
       fr.ip_address AS forwarding_rule_ip,
       fr.load_balancing_scheme AS forwarding_rule_scheme,
       fr.exposed_internet AS forwarding_rule_exposed_internet,
       group.id AS instance_group_id,
       group.name AS instance_group_name,
       instance.id AS instance_id,
       instance.name AS instance_name,
       instance.exposed_internet AS instance_exposed_internet,
       instance.exposed_internet_type AS instance_exposed_internet_type
LIMIT 100
```

```cypher
MATCH (instance:GCPInstance)<-[:FIREWALL_INGRESS]-(firewall:GCPFirewall)<-[:ALLOWED_BY]-(allow_rule:GCPIpRule)<-[:MEMBER_OF_IP_RULE]-(cidr:GCPIpRange)
MATCH (instance)-[:NETWORK_INTERFACE]->(:GCPNetworkInterface)-[:RESOURCE]->(access_config:GCPNicAccessConfig)
WHERE (instance.id = $value OR instance.name = $value OR access_config.public_ip = $value)
  AND cidr.id IN ['0.0.0.0/0', '::/0']
RETURN instance.id AS instance_id,
       instance.name AS instance_name,
       access_config.public_ip AS public_ip,
       firewall.id AS firewall_id,
       firewall.name AS firewall_name,
       firewall.priority AS firewall_priority,
       allow_rule.id AS allow_rule_id,
       allow_rule.protocol AS protocol,
       allow_rule.fromport AS from_port,
       allow_rule.toport AS to_port,
       cidr.id AS source_range,
       instance.exposed_internet AS exposed_internet,
       instance.exposed_internet_type AS exposed_internet_type
LIMIT 100
```

## GCP Cloud SQL and GCS public exposure

Use for public databases and buckets.

```cypher
MATCH (db:GCPCloudSQLInstance)-[:AUTHORIZED_NETWORK]->(network:GCPCloudSQLAuthorizedNetwork)
WHERE db.id = $value
   OR db.name = $value
   OR network.value = $value
RETURN db.id AS database_id,
       db.name AS database_name,
       db.database_version AS database_version,
       db.region AS region,
       db.exposed_internet AS exposed_internet,
       db.exposed_internet_type AS exposed_internet_type,
       network.id AS authorized_network_id,
       network.name AS authorized_network_name,
       network.value AS authorized_network_value
LIMIT 100
```

```cypher
MATCH (bucket:GCPBucket:ObjectStorage)
WHERE bucket.id = $value OR bucket.name = $value
RETURN bucket.id AS bucket_id,
       bucket.name AS bucket_name,
       bucket.acl_public AS acl_public,
       bucket.iam_config_public_access_prevention AS public_access_prevention,
       bucket._ont_public AS ont_public,
       bucket.anonymous_access AS anonymous_access,
       bucket.anonymous_actions AS anonymous_actions
LIMIT 100
```

## Azure load balancer, VM, and NSG exposure

Use for Azure public IP/LB/VM questions. Azure Firewall topology is not enough to prove effective access unless rules are modeled.

```cypher
MATCH (lb:AzureLoadBalancer:LoadBalancer)-[:CONTAINS]->(frontend:AzureLoadBalancerFrontendIPConfiguration)-[:ASSOCIATED_WITH]->(pip:AzurePublicIPAddress)
WHERE lb.id = $value
   OR lb.name = $value
   OR pip.ip_address = $value
OPTIONAL MATCH (lb)-[:CONTAINS]->(pool:AzureLoadBalancerBackendPool)-[:ROUTES_TO]->(nic:AzureNetworkInterface)-[:ATTACHED_TO]->(vm:AzureVirtualMachine)
OPTIONAL MATCH (lb)-[r_expose:EXPOSE]->(exposed_target)
RETURN lb.id AS load_balancer_id,
       lb.name AS load_balancer_name,
       lb.exposed_internet AS load_balancer_exposed_internet,
       lb.exposed_internet_type AS load_balancer_exposed_internet_type,
       frontend.id AS frontend_id,
       pip.id AS public_ip_id,
       pip.ip_address AS public_ip_address,
       pool.id AS backend_pool_id,
       nic.id AS network_interface_id,
       vm.id AS vm_id,
       vm.name AS vm_name,
       vm.exposed_internet AS vm_exposed_internet,
       vm.exposed_internet_type AS vm_exposed_internet_type,
       r_expose.exposure_type AS exposure_type,
       labels(exposed_target) AS exposed_target_labels,
       exposed_target.id AS exposed_target_id
LIMIT 100
```

```cypher
MATCH (vm:AzureVirtualMachine)<-[:ATTACHED_TO]-(nic:AzureNetworkInterface)-[:ASSOCIATED_WITH]->(pip:AzurePublicIPAddress)
WHERE vm.id = $value
   OR vm.name = $value
   OR pip.ip_address = $value
OPTIONAL MATCH (nic)-[:ASSOCIATED_WITH]->(nic_nsg:AzureNetworkSecurityGroup)<-[:MEMBER_OF_AZURE_NSG]-(nic_rule:AzureNetworkSecurityRule:IpPermissionInbound)
OPTIONAL MATCH (nic)-[:ATTACHED_TO]->(:AzureSubnet)-[:ASSOCIATED_WITH]->(subnet_nsg:AzureNetworkSecurityGroup)<-[:MEMBER_OF_AZURE_NSG]-(subnet_rule:AzureNetworkSecurityRule:IpPermissionInbound)
WITH vm, nic, pip,
     coalesce(nic_nsg, subnet_nsg) AS nsg,
     coalesce(nic_rule, subnet_rule) AS rule
WHERE rule IS NULL
   OR (
        rule.access = 'Allow'
        AND rule.direction = 'Inbound'
        AND (
              rule.source_address_prefix IN ['*', 'Internet', '0.0.0.0/0', '::/0']
              OR 'Internet' IN coalesce(rule.source_address_prefixes, [])
              OR '0.0.0.0/0' IN coalesce(rule.source_address_prefixes, [])
              OR '::/0' IN coalesce(rule.source_address_prefixes, [])
            )
      )
RETURN vm.id AS vm_id,
       vm.name AS vm_name,
       vm.exposed_internet AS exposed_internet,
       vm.exposed_internet_type AS exposed_internet_type,
       nic.id AS network_interface_id,
       pip.id AS public_ip_id,
       pip.ip_address AS public_ip_address,
       nsg.id AS nsg_id,
       nsg.name AS nsg_name,
       rule.id AS rule_id,
       rule.priority AS priority,
       rule.protocol AS protocol,
       rule.source_address_prefix AS source_address_prefix,
       rule.destination_port_range AS destination_port_range,
       rule.destination_port_ranges AS destination_port_ranges
LIMIT 100
```

## Azure public storage and databases

Use for Azure Blob, SQL, and Cosmos DB exposure. Validate exact labels in the tenant schema.

```cypher
MATCH (account:AzureStorageAccount)-[:USES]->(blob:AzureStorageBlobService)-[:CONTAINS]->(container:AzureStorageBlobContainer)
WHERE account.id = $value
   OR account.name = $value
   OR container.id = $value
   OR container.name = $value
RETURN account.id AS storage_account_id,
       account.name AS storage_account_name,
       blob.id AS blob_service_id,
       container.id AS container_id,
       container.name AS container_name,
       container.publicaccess AS public_access,
       container._ont_public AS ont_public
LIMIT 100
```

```cypher
MATCH (server:AzureSQLServer)
WHERE server.id = $value OR server.name = $value
OPTIONAL MATCH (server)-[:RESOURCE]->(rule:AzureSQLServerFirewallRule)
RETURN server.id AS sql_server_id,
       server.name AS sql_server_name,
       server.public_network_access AS public_network_access,
       rule.id AS firewall_rule_id,
       rule.name AS firewall_rule_name,
       rule.start_ip_address AS start_ip_address,
       rule.end_ip_address AS end_ip_address
LIMIT 100
```

## Public snapshots and images

Use for public data-copy exposure. These are public sharing paths, not network reachability paths.

```cypher
MATCH (snapshot:Snapshot)
WHERE snapshot.id = $value
   OR snapshot.name = $value
   OR snapshot._ont_public = true
RETURN labels(snapshot) AS snapshot_labels,
       snapshot.id AS snapshot_id,
       snapshot.name AS snapshot_name,
       snapshot._ont_public AS ont_public,
       snapshot.ispublic AS is_public,
       snapshot.visibility AS visibility,
       snapshot.region AS region,
       snapshot.accountid AS account_id,
       snapshot.project_id AS project_id,
       snapshot.subscription_id AS subscription_id
LIMIT 100
```

```cypher
MATCH (image)
WHERE (image:EC2Image OR image:AMI OR image:Image)
  AND (image.id = $value OR image.name = $value OR image.ispublic = true)
RETURN labels(image) AS image_labels,
       image.id AS image_id,
       image.name AS image_name,
       image.ispublic AS is_public,
       image.ownerid AS owner_id,
       image.region AS region
LIMIT 100
```

## Scaleway public IP and instance pivots

Use for Scaleway exposure. Treat reserved IPs without an instance relationship as partial evidence.

```cypher
MATCH (ip:ScalewayFlexibleIp)
WHERE ip.id = $value
   OR ip.name = $value
   OR ip.address = $value
OPTIONAL MATCH (public_ip:PublicIP)-[:RESERVED_BY]->(ip)
OPTIONAL MATCH (public_ip)-[:POINTS_TO]->(target)
RETURN ip.id AS flexible_ip_id,
       ip.name AS flexible_ip_name,
       ip.address AS flexible_ip_address,
       ip.state AS state,
       ip.type AS type,
       ip.zone AS zone,
       public_ip.id AS public_ip_id,
       labels(target) AS target_labels,
       target.id AS target_id,
       target.name AS target_name,
       target.public_ips AS target_public_ips,
       target.ipv6_address AS target_ipv6_address
LIMIT 100
```

```cypher
MATCH (instance:ScalewayInstance:ComputeInstance)
WHERE instance.id = $value
   OR instance.name = $value
   OR $value IN coalesce(instance.public_ips, [])
   OR instance.ipv6_address = $value
RETURN instance.id AS instance_id,
       instance.name AS instance_name,
       instance.public_ips AS public_ips,
       instance.dynamic_ip_required AS dynamic_ip_required,
       instance.routed_ip_enabled AS routed_ip_enabled,
       instance.enable_ipv6 AS enable_ipv6,
       instance.ipv6_address AS ipv6_address,
       instance.exposed_internet AS exposed_internet,
       instance.exposed_internet_type AS exposed_internet_type
LIMIT 100
```

## Analysis-job coverage probe

Use when raw paths exist but rollup fields or `EXPOSE` edges are missing. This helps distinguish ingestion/model data from analysis-job coverage.

```cypher
MATCH (n)
WHERE n.id = $value OR n.name = $value
OPTIONAL MATCH (lb:LoadBalancer)-[r_expose:EXPOSE]->(n)
OPTIONAL MATCH (ip:PublicIP)-[r_points:POINTS_TO]->(n)
RETURN labels(n) AS node_labels,
       n.id AS node_id,
       n.name AS node_name,
       n.exposed_internet AS exposed_internet,
       n.exposed_internet_type AS exposed_internet_type,
       n._ont_public AS ont_public,
       n.anonymous_access AS anonymous_access,
       labels(lb) AS exposing_load_balancer_labels,
       lb.id AS exposing_load_balancer_id,
       r_expose.exposure_type AS exposure_type,
       ip.id AS pointing_public_ip_id,
       ip.address AS pointing_public_ip_address
LIMIT 100
```
