# Kubernetes public-exposure Cypher templates

Schema-validate before running. Start from the service, ingress, or gateway and preserve the distinction between a public front door and a private backing workload.

## Ingress and service workload exposure

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

## Gateway API exposure

Gateway and route edges identify routing intent; still inspect the backing service/load-balancer path.

```cypher
CALL {
  MATCH (gateway:KubernetesGateway)
  WHERE gateway.id = $value OR gateway.name = $value
  MATCH (gateway)-[:ROUTES]->(route:KubernetesHTTPRoute)-[:TARGETS]->(svc:KubernetesService)
  RETURN gateway, route, svc
  UNION
  MATCH (route:KubernetesHTTPRoute)
  WHERE route.id = $value OR route.name = $value
  MATCH (gateway:KubernetesGateway)-[:ROUTES]->(route)-[:TARGETS]->(svc:KubernetesService)
  RETURN gateway, route, svc
  UNION
  MATCH (svc:KubernetesService)
  WHERE svc.id = $value OR svc.name = $value
  MATCH (gateway:KubernetesGateway)-[:ROUTES]->(route:KubernetesHTTPRoute)-[:TARGETS]->(svc)
  RETURN gateway, route, svc
}
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
