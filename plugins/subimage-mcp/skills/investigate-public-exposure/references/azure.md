# Azure public-exposure Cypher templates

Schema-validate before running. Azure Firewall topology alone is not proof that a path is allowed unless effective rules are modeled.

## Load balancer, VM, and NSG exposure

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
CALL {
  WITH nic
  MATCH (nic)-[:ASSOCIATED_WITH]->(nsg:AzureNetworkSecurityGroup)<-[:MEMBER_OF_AZURE_NSG]-(rule:AzureNetworkSecurityRule:IpPermissionInbound)
  RETURN 'nic' AS nsg_scope, nsg, rule
  UNION
  WITH nic
  MATCH (nic)-[:ATTACHED_TO]->(:AzureSubnet)-[:ASSOCIATED_WITH]->(nsg:AzureNetworkSecurityGroup)<-[:MEMBER_OF_AZURE_NSG]-(rule:AzureNetworkSecurityRule:IpPermissionInbound)
  RETURN 'subnet' AS nsg_scope, nsg, rule
}
WITH vm, nic, pip, nsg_scope, nsg, rule
WHERE rule.access = 'Allow'
  AND rule.direction = 'Inbound'
  AND (
        rule.source_address_prefix IN ['*', 'Internet', '0.0.0.0/0', '::/0']
        OR 'Internet' IN coalesce(rule.source_address_prefixes, [])
        OR '0.0.0.0/0' IN coalesce(rule.source_address_prefixes, [])
        OR '::/0' IN coalesce(rule.source_address_prefixes, [])
      )
RETURN vm.id AS vm_id,
       vm.name AS vm_name,
       vm.exposed_internet AS exposed_internet,
       vm.exposed_internet_type AS exposed_internet_type,
       nic.id AS network_interface_id,
       pip.id AS public_ip_id,
       pip.ip_address AS public_ip_address,
       nsg_scope AS nsg_scope,
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

## Public storage and databases

For SQL firewall rules, `0.0.0.0` to `0.0.0.0` is the Azure-services exception, not arbitrary public internet.

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
OPTIONAL MATCH (rule:AzureSQLServerFirewallRule:IpPermissionInbound)-[:MEMBER_OF_AZURE_SQL_SERVER]->(server)
RETURN server.id AS sql_server_id,
       server.name AS sql_server_name,
       server.public_network_access AS public_network_access,
       rule.id AS firewall_rule_id,
       rule.name AS firewall_rule_name,
       rule.start_ip_address AS start_ip_address,
       rule.end_ip_address AS end_ip_address,
       CASE
         WHEN rule.start_ip_address = '0.0.0.0' AND rule.end_ip_address = '255.255.255.255' THEN 'public_internet'
         WHEN rule.start_ip_address = '0.0.0.0' AND rule.end_ip_address = '0.0.0.0' THEN 'azure_services_only'
         WHEN rule.id IS NOT NULL THEN 'specific_range'
         ELSE 'no_firewall_rule_found'
       END AS firewall_rule_exposure_class
LIMIT 100
```
