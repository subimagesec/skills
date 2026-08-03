---
name: connect-kubernetes-outpost
description: Deploy the SubImage Outpost so SubImage can reach private APIs (private Kubernetes clusters, on-prem Jamf, internal CrowdStrike, etc.) via an outbound Tailscale tunnel. Use when the user asks to "deploy SubImage Outpost", "connect a private Kubernetes cluster to SubImage", "scan an internal API with SubImage", "where do I get the outpost registration key", or works in a Helm/Terraform/Docker repo and needs SubImage to reach something not on the public internet. Covers Helm and Docker paths.
---

# Connect a SubImage Outpost (private API access)

## What this does

Deploys a lightweight container in the customer's private network that establishes an outbound Tailscale tunnel back to SubImage and proxies sync traffic to an internal HTTPS endpoint. SubImage modules that support outpost connectivity then route through this tunnel instead of the public internet.

## When to use

✅ The target API is not reachable from the public internet (private Kubernetes clusters, on-prem services, VPN-only IT tools).
✅ User wants to scan an internal Jamf, BigFix, Kandji, SnipeIT, CrowdStrike, LastPass, or Semgrep instance.
✅ User wants the deployment committed in their Helm/Terraform repo.

❌ The cluster's API endpoint is public: no outpost needed; configure the EKS/GKE module directly.
❌ The user only needs in-cluster RBAC for an already-reachable EKS cluster: that is the **EKS RBAC** step (Access Entries or `aws-auth`), covered in Step 5, not an outpost.

Outpost-eligible modules: `bigfix`, `crowdstrike`, `jamf`, `kandji`, `kubernetes` (private API endpoint, EKS or self-managed), `lastpass`, `semgrep`, `snipeit`.

## Step 1: Get the outpost registration key (self-serve)

Do this first. Everything else is deployment mechanics; without the key there is nothing to deploy.

1. Open **Settings → Outposts** at `/settings/outposts` on the tenant's SubImage URL. Deployments are single-tenant, so for most customers that is `https://<slug>.subimage.io/settings/outposts` (e.g. `https://acme.subimage.io/settings/outposts`).
2. In the **Outpost registration key** field, click **Reveal**, then copy the value.
3. The key starts with `tskey-client-`. It is a Tailscale OAuth client secret that SubImage provisions for the tenant; the user never signs up for Tailscale.

Facts that shape the rest of this flow:

- **Admin role required to reveal.** Operators can see the outpost list but the Reveal button is disabled for them, with the required role shown as the hint. If the user is not an admin, have an admin copy the key.
- **The key is not show-once.** It can be revealed again at any time from the same page, so there is no "I lost it, please reissue" path.
- **One key per tenant and environment.** Every outpost in the tenant registers with the same key; only the hostname differs. Do not ask SubImage for a per-outpost key.
- **Ask SubImage on Slack only if the page itself fails**, i.e. the key field shows an error or the deployment has no key configured. That is a provisioning gap on SubImage's side, not something the user can fix.

If the key is missing from the conversation, ask for it explicitly before generating any command:

> "Can an admin open Settings → Outposts (`/settings/outposts` on your SubImage URL, e.g. `https://acme.subimage.io/settings/outposts`), click Reveal on the Outpost registration key, and paste it here? It starts with `tskey-client-`."

## Step 2: Collect the remaining inputs

**If any input is missing, ask the user explicitly.** Never substitute a guess and never leave a placeholder in a command.

| Value | Where to find it | If missing, ask |
|---|---|---|
| `<TENANT_ID>` | SubImage tenant slug, i.e. the subdomain of the SubImage URL (`acme` in `https://acme.subimage.io`). Also shown at **Settings → Modules**. | "What is your SubImage tenant ID (the slug, e.g. `acme`)? It is the subdomain of your SubImage URL." |
| `<NAME>` | Optional. Unique name for this outpost; only matters if you deploy several. Default: `subimage`. | "Is this the only outpost for this tenant, or should I assign a unique `NAME` (e.g. `eks-prod`, `it`)?" |
| `<PROXY_TARGET>` | Internal HTTPS URL the outpost will proxy to (e.g. `https://kubernetes.default.svc` for in-cluster, or `https://jamf.corp.example.com`). | "What internal URL should this outpost proxy traffic to?" |
| `<VERIFY_TLS>` | `true` for valid public certs, `false` for self-signed. See the TLS gotcha before answering. | "Does the target endpoint use a publicly-signed TLS cert? If yes, `VERIFY_TLS=true`. If self-signed, `false`." |
| Deployment platform | Helm (Kubernetes) or Docker (ECS/EC2/Cloud Run). | "Will you deploy on Kubernetes (Helm chart) or as a standalone container (Docker)?" |

The Tailscale hostname is derived as `<TENANT_ID>-<NAME>-outpost`. You will paste this hostname into the SubImage module config in Step 5.

## Gotchas

Read these before generating any commands; they correct the most common wrong assumptions.

- **The Helm auth key lives at `outpost.authKey.value`, not `outpost.authKey`.** A bare string there makes the chart fail to render with `can't evaluate field secret in type interface {}`. The nested form is the only one the chart accepts.
- **`?ephemeral=true` is appended by the chart only when the chart creates the secret** (`authKey.secret.create: true`, the default). On the Docker path, and on the Helm path with a pre-existing secret (`secret.create: false`), you must include `?ephemeral=true` yourself. Without it the node registers once and refuses to reconnect after the first restart.
- **All outposts for the same tenant and environment share the same registration key and Tailscale tag.** Only the hostname (`<TENANT_ID>-<NAME>-outpost`) differs.
- **`ENVIRONMENT` is a SubImage-internal value, not the customer's environment.** It defaults to `prod` and feeds only the Tailscale tag `tag:<TENANT_ID>-<ENVIRONMENT>-outpost`. Leave it alone unless SubImage says otherwise; setting it to `staging` because the cluster is a staging cluster breaks discovery.
- **The outpost only opens an OUTBOUND WireGuard connection.** No inbound firewall changes are needed. If the security team asks "what ports do we open", the answer is "none". Do not invent ingress rules.
- **TLS verification defaults differ between the two paths.** The container image defaults `VERIFY_TLS` to `false`; the Helm chart defaults `verifyTls` to `true`. Always set it explicitly. For the in-cluster Kubernetes API, prefer keeping `verifyTls: true`: the outpost auto-detects the serviceaccount CA at `/var/run/secrets/kubernetes.io/serviceaccount/ca.crt` and verifies properly. Reach for `false` only when the target really self-signs and no CA bundle is available.
- **The Helm chart grants cluster-wide `list` on Secrets by default** (`rbac.secrets: true`), and `list` returns Secret values, not just names. If the outpost does not need Secret contents, set `rbac: {secrets: false}` in the values file before installing. Decide this with the customer rather than shipping the default silently.
- **Hostname mismatch is the silent failure mode.** The value entered in the SubImage module config must equal `<TENANT_ID>-<NAME>-outpost` exactly. A typo produces no log error; the sync just fails to connect.
- **Do not pass secrets via `--set`.** Helm puts `--set` values in shell history. Use a values file (`-f values.yaml`) for the auth key. Same caveat for any Terraform variable holding it: mark it `sensitive = true`.
- **Do not pass the placeholder strings.** `<TENANT_ID>`, `<TAILSCALE_AUTHKEY>`, `<PROXY_TARGET>` must be substituted. The container starts with literal angle-brackets in env vars and fails at the Tailscale handshake with an unhelpful "invalid auth" message.

## Step 3: Deploy

### Path A: Helm (recommended for Kubernetes)

```bash
helm repo add subimage https://subimagesec.github.io/helm-charts
helm repo update
```

Create `values.yaml` (do not pass secrets via `--set`, they end up in shell history):

```yaml
outpost:
  tenantId: "<TENANT_ID>"
  proxyTarget: "<PROXY_TARGET>"
  verifyTls: <VERIFY_TLS>              # boolean, no quotes; chart default is true
  # name: "<NAME>"                     # uncomment if not the only outpost
  authKey:
    value: "<TAILSCALE_AUTHKEY>"       # without ?ephemeral=true: the chart adds it

# Uncomment if the outpost does not need to read Secret values:
# rbac:
#   secrets: false
```

Install (the chart creates and deploys into the `subimage-outpost` namespace itself):

```bash
helm install subimage-outpost subimage/subimage-outpost -f values.yaml
```

Terraform wrapper if your repo is HCL-driven:

```hcl
resource "helm_release" "subimage_outpost" {
  name       = "subimage-outpost"
  repository = "https://subimagesec.github.io/helm-charts"
  chart      = "subimage-outpost"

  values = [yamlencode({
    outpost = {
      tenantId    = var.subimage_tenant_id
      proxyTarget = var.subimage_proxy_target
      verifyTls   = var.subimage_verify_tls
      # name      = var.subimage_outpost_name
      authKey = {
        value = var.subimage_tailscale_authkey # mark variable sensitive
      }
    }
  })]
}
```

Advanced options (RBAC tuning, corporate proxy, network policies, pod security, node selectors, timeouts) live in the chart README: https://github.com/subimagesec/helm-charts/blob/main/charts/subimage-outpost/README.md

### Path B: Docker

Pin an explicit image version rather than `:latest`, so restarts and rebuilds are reproducible and upgrades are deliberate. Before deploying, check the published tags at https://github.com/subimagesec/subimage-outpost/pkgs/container/subimage-outpost and set `OUTPOST_VERSION` to the newest release; `1.2.0` below (shipped by chart 1.4.0) is only the version current when this skill was written.

```bash
OUTPOST_VERSION=1.2.0

docker pull ghcr.io/subimagesec/subimage-outpost:${OUTPOST_VERSION}

docker run -d \
  --name subimage-outpost \
  --restart unless-stopped \
  -e TAILSCALE_AUTHKEY='<TAILSCALE_AUTHKEY>?ephemeral=true' \
  -e TENANT_ID=<TENANT_ID> \
  -e NAME=<NAME> \
  -e PROXY_TARGET=<PROXY_TARGET> \
  -e VERIFY_TLS=<VERIFY_TLS> \
  ghcr.io/subimagesec/subimage-outpost:${OUTPOST_VERSION}
```

`?ephemeral=true` is mandatory here: nothing appends it on the Docker path.

Optional env vars:

- `PROXY_HOST`: overrides the `Host` header sent to `PROXY_TARGET`. Useful when the target expects a virtual host different from the URL (e.g. `eks.internal.acme.com` while `PROXY_TARGET` is an IP).
- `CA_BUNDLE`: path to a CA bundle inside the container, honored when `VERIFY_TLS=true`.
- `PROXY_CONNECT_TIMEOUT` (default 15) and `PROXY_READ_TIMEOUT` (default 60), in seconds. Raise them for slow DNS or large list calls.

## Step 4: Verify the outpost is up

Start in the SubImage UI: **Settings → Outposts** (`/settings/outposts`) lists every registered outpost with its hostname, Online/Offline status, last-seen time, and outpost version (flagged when outdated). The **Logs** button streams that outpost's logs without cluster access, which is the fastest check and works even when the user cannot run `kubectl`.

Expect the hostname `<TENANT_ID>-<NAME>-outpost` to appear as Online within a minute or two of install.

If it does not show up, inspect locally.

Helm/Kubernetes:

```bash
kubectl get pods -n subimage-outpost -l app.kubernetes.io/name=subimage-outpost
kubectl logs -n subimage-outpost -l app.kubernetes.io/name=subimage-outpost --tail=50
kubectl exec -n subimage-outpost deployment/subimage-outpost -- tailscale status
```

(The deployment is named after the Helm release; `subimage-outpost` assumes the release name used above.)

Docker:

```bash
docker ps | grep subimage-outpost
docker logs subimage-outpost --tail 50
```

A healthy startup logs, in order: `Connected to Tailscale`, `Starting proxy server on port ...`, `Exposing proxy via Tailscale serve...`, and finally `Outpost is ready and serving`. Anything short of that last line means the outpost is not usable yet.

## Step 5: Connect a SubImage module to the outpost

Once the outpost is up, the actual scan still happens through whichever SubImage module needs to reach the private endpoint.

1. SubImage UI → **Modules**.
2. Find the target module (outpost-eligible ones show a cell tower icon).
3. **Config** → fill in the module's normal fields (URL, credentials, etc.).
4. **Tailscale outpost hostname** field: enter `<TENANT_ID>-<NAME>-outpost` (or `<TENANT_ID>-subimage-outpost` if you used the default name).
5. Save and **Run Sync**.

The Kubernetes module supports a per-row override that takes precedence over the module-level hostname:

- **EKS rows**: when adding a cluster ARN, check **override outpost hostname?** and enter the per-cluster hostname.
- **Self-managed rows**: enter the outpost hostname directly on the row.

### Kubernetes API authorization

Reachability and authorization are two different halves, and which half the outpost covers depends on the path:

- **Helm path**: the chart covers both. With `rbac.create: true` (the default) it creates a ServiceAccount plus ClusterRole/ClusterRoleBinding, mounts the SA token, and the proxy injects `Authorization: Bearer <token>` on every request to the Kubernetes API. Nothing else to grant.
- **Docker path, or Helm with `rbac.create: false`**: the outpost gives reachability only. Authorization has to come from elsewhere, e.g. a bearer token you supply (`BEARER_TOKEN` / `BEARER_TOKEN_PATH`), or the AWS-side path below for EKS.

For EKS scanned through the AWS module's `SubImageScanRole` rather than the chart's ServiceAccount, grant that role cluster access. The full Access Entries / `aws-auth` recipe lives at https://app.subimage.io/docs/modules/eks. The short version:

```bash
aws eks create-access-entry \
  --cluster-name <cluster-name> \
  --principal-arn arn:aws:iam::<aws-account-id>:role/SubImageScanRole \
  --type STANDARD \
  --username subimage-scan

# Then apply the subimage-viewer ClusterRole + ClusterRoleBinding from the doc.
```

## Updating the outpost

Helm:

```bash
helm repo update
helm upgrade subimage-outpost subimage/subimage-outpost -f values.yaml
```

Docker:

```bash
OUTPOST_VERSION=<newest-release-tag>   # from the package page linked in Step 3

docker pull ghcr.io/subimagesec/subimage-outpost:${OUTPOST_VERSION}
docker stop subimage-outpost && docker rm subimage-outpost
# Re-run the same docker run command with the new OUTPOST_VERSION.
```

Settings → Outposts flags an outdated outpost version next to the hostname, which is the signal to run this.

## Troubleshooting

- **Container exits immediately**: usually an invalid `TAILSCALE_AUTHKEY` or a missing `TENANT_ID`. Check the logs, then re-reveal the key at Settings → Outposts and compare it character for character; the key is stable, so a mismatch means a copy error, not a rotation. On Docker, also confirm `?ephemeral=true` is present.
- **`helm install` fails with `can't evaluate field secret in type interface {}`**: the values file uses `outpost.authKey: "<key>"` instead of `outpost.authKey.value`.
- **Outpost connects but module sync fails**: the `PROXY_TARGET` URL is wrong or unreachable from the outpost container. Verify with `docker exec subimage-outpost curl -v <PROXY_TARGET>` (or `kubectl exec -n subimage-outpost`).
- **Kubernetes API returns 403 through the outpost**: reachability is fine, authorization is not. Check the RBAC half for your path (see Step 5).
- **TLS errors talking to the target**: prefer pointing `CA_BUNDLE` / `caBundle` at the right CA. Set `VERIFY_TLS=false` only if the target really has a self-signed cert and no bundle is available.
- **Hostname mismatch**: the value in the module config and the value derived from `<TENANT_ID>-<NAME>-outpost` must match exactly.

## Security notes

- The outpost only opens an **outbound** WireGuard connection to Tailscale. No inbound firewall changes are needed.
- All traffic between SubImage and the outpost is encrypted via WireGuard.
- The registration key is a credential. Keep it out of shell history (use a values file, not `--set`) and mark any Terraform variable holding it `sensitive = true`.
- The Helm chart's default RBAC includes cluster-wide `list` on Secrets, which exposes Secret values. Opt out with `rbac: {secrets: false}` when the outpost does not need them.
- Outposts in the same tenant share a Tailscale tag but cannot reach each other: Tailscale ACLs block outpost-to-outpost traffic.

## References

- Canonical doc: https://app.subimage.io/docs/subimage_outpost
- Outpost settings and registration key: `/settings/outposts` on the tenant's SubImage URL (`https://<slug>.subimage.io/settings/outposts`)
- Outpost image: https://github.com/subimagesec/subimage-outpost
- Helm chart: https://github.com/subimagesec/helm-charts
