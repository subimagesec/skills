# GCP public-exposure Cypher templates

Schema-validate before running. `GCPIpRange.id` is the canonical CIDR property in the live schema; `range` may also exist but is not the documented identifier.

## Cloud Run and Cloud Functions public invocation

Public Cloud Run invocation needs public ingress and public invoker IAM; do not treat ingress alone as anonymous invocation.

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

## Load balancer and direct compute exposure

Forwarding rules and backend services do not have a direct modeled relationship, so inspect them with separate bounded probes. Include deny-rule checks before making high-confidence direct-exposure claims.

```cypher
MATCH (fr:GCPForwardingRule)
WHERE fr.id = $value
   OR fr.name = $value
   OR fr.ip_address = $value
RETURN fr.id AS forwarding_rule_id,
       fr.name AS forwarding_rule_name,
       fr.ip_address AS forwarding_rule_ip,
       fr.ip_protocol AS forwarding_rule_protocol,
       fr.port_range AS forwarding_rule_port_range,
       fr.ports AS forwarding_rule_ports,
       fr.target AS forwarding_rule_target,
       fr.load_balancing_scheme AS forwarding_rule_scheme,
       fr.exposed_internet AS forwarding_rule_exposed_internet,
       fr.exposed_internet_type AS forwarding_rule_exposed_internet_type
LIMIT 100
```

```cypher
CALL {
  MATCH (backend:GCPBackendService)
  WHERE backend.id = $value OR backend.name = $value
  MATCH (backend)-[:ROUTES_TO]->(group:GCPInstanceGroup)-[:HAS_MEMBER]->(instance:GCPInstance)
  RETURN backend, group, instance
  UNION
  MATCH (instance:GCPInstance)
  WHERE instance.id = $value OR instance.name = $value
  MATCH (backend:GCPBackendService)-[:ROUTES_TO]->(group:GCPInstanceGroup)-[:HAS_MEMBER]->(instance)
  RETURN backend, group, instance
}
RETURN backend.id AS backend_service_id,
       backend.name AS backend_service_name,
       backend.load_balancing_scheme AS backend_load_balancing_scheme,
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

## Cloud SQL and GCS public exposure

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
OPTIONAL MATCH (binding:GCPPolicyBinding)-[:APPLIES_TO]->(bucket)
RETURN bucket.id AS bucket_id,
       bucket.name AS bucket_name,
       bucket.acl_public AS acl_public,
       bucket.iam_config_public_access_prevention AS public_access_prevention,
       bucket._ont_public AS ont_public,
       binding.id AS binding_id,
       binding.role AS binding_role,
       binding.is_public AS binding_is_public,
       binding.has_condition AS binding_has_condition,
       binding.members AS binding_members
LIMIT 100
```
