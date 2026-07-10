# Scaleway public-exposure Cypher templates

Schema-validate before running. Treat reserved public IPs without a direct `POINTS_TO` or instance relationship as partial evidence.

## Public IP and target

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

## Instance public address

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
