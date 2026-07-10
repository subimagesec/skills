# Common Cypher pivots: public exposure investigation

Use these cross-provider starting points before loading a provider-specific template. Schema-validate first, keep starting patterns label-constrained, and treat `LIMIT` as a result bound rather than a scan bound.

Templates use `$value` for readability. If the active MCP tool supports parameters, pass `$value` as a parameter. If it only accepts a query string, quote the exact literal safely and keep the query narrow.

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

Use after resolving a load balancer, target service, instance, pod, or container. `EXPOSE` identifies a target path, but it can also exist for internal load balancers. Pair it with provider-specific proof of the front door's publicness when explaining why.

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
