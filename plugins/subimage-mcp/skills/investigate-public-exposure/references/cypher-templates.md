# Cypher template index: public exposure investigation

Load only the template file needed for the target provider or query family:

- Cross-provider DNS, Cloudflare, public IP, or load balancer pivots: [`common-pivots.md`](common-pivots.md)
- AWS resources, including S3, EC2, load balancers, ECS, EKS, API Gateway, and Lambda: [`aws.md`](aws.md)
- Kubernetes services, ingresses, and Gateway API: [`kubernetes.md`](kubernetes.md)
- GCP resources: [`gcp.md`](gcp.md)
- Azure resources: [`azure.md`](azure.md)
- Public snapshots and EC2 images: [`data-sharing.md`](data-sharing.md)
- Scaleway resources: [`scaleway.md`](scaleway.md)
- Analysis-job coverage troubleshooting: [`diagnostics.md`](diagnostics.md)

Each file contains starting-point queries. Schema-validate labels, properties, and relationship directions with `subimageGetNodesSchema` and `searchModelQueries` before running them. Treat `LIMIT` as a result bound, not proof that the planner avoids scanning; keep the starting pattern label-constrained unless a template explicitly documents a last-resort exception.
