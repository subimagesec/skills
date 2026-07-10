# AWS public-exposure Cypher templates

Schema-validate before running. Use `$value` as a parameter when supported, keep starting patterns label-constrained, and treat `LIMIT` as a result bound rather than a scan bound.

## CloudFront/S3 public exposure cause

Use when the user asks whether a domain or bucket is public because of CloudFront, direct S3 bucket policy, or both. Validate the directed `CloudFrontDistribution` to `S3Bucket` and `S3Bucket` to `S3PolicyStatement` relationships before running.

```cypher
CALL {
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
  LIMIT 100
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
}
RETURN *
LIMIT 100
```

## Direct S3 bucket policy statements

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

## EC2 direct security-group exposure

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

## ALB/NLB/classic ELB exposure and targets

For ALB/classic ELB, security group rules help prove public listener reachability. For NLB, internet-facing scheme plus listener is often the key front-door evidence.

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

## ECS behind a load balancer

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

## EKS control-plane exposure

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

## API Gateway and Lambda public access

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
