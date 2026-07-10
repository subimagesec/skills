# Public-exposure analysis diagnostics

## Analysis-job coverage probe

Use only when schema-directed raw paths exist but rollup fields or `EXPOSE` edges are missing. This is an intentional, label-agnostic last-resort lookup: `MATCH (n)` can scan broadly, and `LIMIT` bounds returned rows rather than the scan. Do not copy this shape into normal provider queries.

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
