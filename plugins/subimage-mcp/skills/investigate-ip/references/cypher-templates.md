# Cypher templates: IP / domain investigation

Starting-point queries for `investigate-ip`. **Schema-validate before trusting** (`subimageGetNodesSchema`, `searchModelQueries`) and adjust to the live schema. Always pass the IP/domain as the `$value` parameter; never interpolate it. For **list-typed** properties (`CloudFrontDistribution.aliases`, `GCPRecordSet.data`, security-group rule lists) use `ANY(x IN prop WHERE x = $value)`, never `prop = $value`. Each query is `LIMIT`-bounded.

## IP Address Queries

### EC2 instances

```cypher
MATCH (a:AWSAccount)-[:RESOURCE]->(i:EC2Instance)
WHERE i.publicipaddress = $value OR i.privateipaddress = $value
RETURN 'EC2Instance' AS resource_type, i.instanceid AS resource_id, i.instanceid AS name,
       a.name AS account, i.region AS region,
       CASE WHEN i.publicipaddress = $value THEN 'publicipaddress' ELSE 'privateipaddress' END AS matched_field
LIMIT 100
```

### Elastic IP addresses

```cypher
MATCH (a:AWSAccount)-[:RESOURCE]->(eip:ElasticIPAddress)
WHERE eip.public_ip = $value OR eip.private_ip_address = $value
RETURN 'ElasticIPAddress' AS resource_type, eip.id AS resource_id, eip.public_ip AS name,
       a.name AS account, eip.region AS region,
       CASE WHEN eip.public_ip = $value THEN 'public_ip' ELSE 'private_ip_address' END AS matched_field
LIMIT 100
```

### Network interfaces (ENI)

```cypher
MATCH (a:AWSAccount)-[:RESOURCE]->(n:NetworkInterface)
WHERE n.public_ip = $value OR n.private_ip_address = $value
RETURN 'NetworkInterface' AS resource_type, n.id AS resource_id, n.description AS name,
       a.name AS account, n.region AS region,
       CASE WHEN n.public_ip = $value THEN 'public_ip' ELSE 'private_ip_address' END AS matched_field
LIMIT 100
```

### DNS A/AAAA records (Route53): `value` is scalar

```cypher
MATCH (z:AWSDNSZone)<-[:MEMBER_OF_DNS_ZONE]-(r:AWSDNSRecord)
WHERE r.value = $value AND r.type IN ['A', 'AAAA']
RETURN 'AWSDNSRecord' AS resource_type, r.id AS resource_id, r.name AS name,
       z.name AS account, null AS region, 'value (A/AAAA)' AS matched_field
LIMIT 100
```

### Load balancers (via DNS records pointing to them)

LoadBalancers store DNS names, not IPs. Reach them through a DNS record whose value is the IP:

```cypher
MATCH (r:AWSDNSRecord)-[:DNS_POINTS_TO]->(l:LoadBalancer)
WHERE r.value = $value
RETURN 'LoadBalancer (via DNS)' AS resource_type, l.id AS resource_id, l.dnsname AS name,
       l.region AS region, 'dns_value' AS matched_field
LIMIT 100
```

### GCP forwarding rules

```cypher
MATCH (p:GCPProject)-[:RESOURCE]->(f:GCPForwardingRule)
WHERE f.ip_address = $value
RETURN 'GCPForwardingRule' AS resource_type, f.id AS resource_id, f.name AS name,
       p.displayname AS account, f.region AS region, 'ip_address' AS matched_field
LIMIT 100
```

### GCP instances (via NIC access configs): scalar

```cypher
MATCH (p:GCPProject)-[:RESOURCE]->(i:GCPInstance)-[:NETWORK_INTERFACE]->(nic:GCPNetworkInterface)-[:RESOURCE]->(ac:GCPNicAccessConfig)
WHERE ac.public_ip = $value OR nic.private_ip = $value
RETURN 'GCPInstance' AS resource_type, i.id AS resource_id, i.instancename AS name,
       p.displayname AS account, null AS region,
       CASE WHEN ac.public_ip = $value THEN 'public_ip' ELSE 'private_ip' END AS matched_field
LIMIT 100
```

### Azure public IPs

```cypher
MATCH (s:AzureSubscription)-[:RESOURCE]->(pip:AzurePublicIPAddress)
WHERE pip.ip_address = $value
RETURN 'AzurePublicIPAddress' AS resource_type, pip.id AS resource_id, pip.name AS name,
       s.name AS account, pip.location AS region, 'ip_address' AS matched_field
LIMIT 100
```

## Domain Name Queries

### DNS records by name (Route53)

```cypher
MATCH (z:AWSDNSZone)<-[:MEMBER_OF_DNS_ZONE]-(r:AWSDNSRecord)
WHERE r.name = $value OR r.name = $value + '.'
RETURN 'AWSDNSRecord' AS resource_type, r.id AS resource_id, r.name AS name,
       z.name AS account, 'name' AS matched_field, r.value AS resolved_value, r.type AS record_type
LIMIT 100
```

### DNS records by CNAME target

```cypher
MATCH (z:AWSDNSZone)<-[:MEMBER_OF_DNS_ZONE]-(r:AWSDNSRecord)
WHERE r.value = $value OR r.value = $value + '.'
RETURN 'AWSDNSRecord (target)' AS resource_type, r.id AS resource_id, r.name AS name,
       z.name AS account, 'value' AS matched_field, r.value AS resolved_value, r.type AS record_type
LIMIT 100
```

### CloudFront distributions: `aliases` is a LIST (use `ANY`)

```cypher
MATCH (a:AWSAccount)-[:RESOURCE]->(cf:CloudFrontDistribution)
WHERE cf.domain_name = $value OR ANY(alias IN cf.aliases WHERE alias = $value)
RETURN 'CloudFrontDistribution' AS resource_type, cf.id AS resource_id, cf.domain_name AS name,
       a.name AS account,
       CASE WHEN cf.domain_name = $value THEN 'domain_name' ELSE 'aliases' END AS matched_field
LIMIT 100
```

### Load balancer DNS names (v1 + v2)

```cypher
MATCH (a:AWSAccount)-[:RESOURCE]->(l:LoadBalancer) WHERE l.dnsname = $value
RETURN 'LoadBalancer' AS resource_type, l.id AS resource_id, l.name AS name,
       a.name AS account, l.region AS region, 'dnsname' AS matched_field
LIMIT 100
UNION ALL
MATCH (a:AWSAccount)-[:RESOURCE]->(l:LoadBalancerV2) WHERE l.dnsname = $value
RETURN 'LoadBalancerV2' AS resource_type, l.id AS resource_id, l.name AS name,
       a.name AS account, l.region AS region, 'dnsname' AS matched_field
LIMIT 100
```

### GCP DNS record sets: `data` is a LIST (use `ANY`)

```cypher
MATCH (p:GCPProject)-[:RESOURCE]->(z:GCPDNSZone)-[:HAS_RECORD]->(s:GCPRecordSet)
WHERE s.name = $value OR s.name = $value + '.'
   OR ANY(d IN s.data WHERE d = $value OR d = $value + '.')
RETURN 'GCPRecordSet' AS resource_type, s.id AS resource_id, s.name AS name,
       p.displayname AS account,
       CASE WHEN s.name = $value OR s.name = $value + '.' THEN 'name' ELSE 'data' END AS matched_field,
       s.type AS record_type
LIMIT 100
```

### EC2 instance public DNS

```cypher
MATCH (a:AWSAccount)-[:RESOURCE]->(i:EC2Instance) WHERE i.publicdnsname = $value
RETURN 'EC2Instance' AS resource_type, i.instanceid AS resource_id, i.instanceid AS name,
       a.name AS account, i.region AS region, 'publicdnsname' AS matched_field
LIMIT 100
```

## DNS Chain

Trace `domain → CNAME → A record → IP → resource`:

```cypher
MATCH path = (r:AWSDNSRecord)-[:DNS_POINTS_TO*1..5]->(target)
WHERE r.name = $value OR r.name = $value + '.'
RETURN [node IN nodes(path) | {
  label: labels(node)[0],
  id: node.id,
  name: coalesce(node.name, node.dnsname, node.public_ip, node.instanceid)
}] AS chain
LIMIT 20
```
