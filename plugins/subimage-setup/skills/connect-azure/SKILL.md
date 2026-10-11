---
name: connect-azure
description: Connect an Azure tenant to SubImage by creating a service principal with Reader role on the subscriptions you want scanned. Use when the user asks to "connect Azure to SubImage", "set up Azure scanning", "create the SubImage Azure SP", "wire Azure into SubImage", or works in a Terraform repo and wants SubImage to inventory their Azure subscriptions, resource groups, and Entra. Covers Terraform and az-cli paths, plus a one-time delegated sync for tenants that can't create a service principal.
---

# Connect Azure to SubImage

## What this does

Registers an application in Microsoft Entra (Azure AD), creates a service principal, generates a client secret, and grants `Reader` on the subscriptions to scan. Walks two paths: Terraform and `az` CLI. A third, one-time delegated sync covers tenants that can't create a service principal at all.

## When to use

✅ User wants to onboard one or more Azure subscriptions, or a Management Group root, into SubImage.
✅ User asks for the Azure service principal, role assignment, or Terraform for SubImage scanning.
✅ User is in their IaC repo and wants the Azure setup committed as code.

❌ User wants Entra ID (users, groups, sign-ins) or Intune coverage: this skill only covers the Azure resource plane. Add the **microsoft** module on top.
❌ User wants to scan AKS at the cluster layer: Reader on the subscription gives metadata only; for in-cluster RBAC, use a separate Kubernetes path.

## Required inputs

Before running anything, collect these. **If any are missing, ask the user explicitly.** For the one-time delegated sync, only the tenant ID is needed; skip the subscription and Management Group rows.

| Value | Where to find it | If missing, ask |
|---|---|---|
| `<TENANT_DIRECTORY_ID>` | Azure Directory / Tenant ID. `az account show --query tenantId -o tsv`. | "What is your Azure Directory (Tenant) ID? Run `az account show --query tenantId -o tsv` to find it." |
| `<SUBSCRIPTION_IDS>` | One or more subscription IDs SubImage should scan. | "Which Azure subscription IDs should SubImage scan? Comma-separated list, or tell me to use a Management Group root instead." |
| `<MGMT_GROUP_ID>` | Optional: the Management Group ID if you want a single binding to cover many subs. | (Only if user picks the MG path) "What is the Management Group ID? `az account management-group list -o table`." |
| Path choice | Terraform, `az`, or the one-time delegated sync. | "Which path: Terraform (recommended for IaC repos) or `az` CLI (one-off setup)? If you can't create a service principal at all, there is also a one-time delegated sync with your own sign-in." |

## Permissions baseline

`Reader` (built-in role) on each in-scope subscription, or once on the Management Group root.

With subscription-scoped Reader, also assign `Management Group Reader` at the Tenant Root Group (or the management groups to cover). Without it, SubImage can't read the management-group hierarchy, subscription placement, or management-group role assignments. `Reader` on a management group already covers this for the groups under it.

`Reader` is enough for resource-plane inventory. Entra ID and Intune objects are NOT covered by this role; they need API permissions on Microsoft Graph, configured via the **microsoft** module.

## Gotchas

Read these before generating any commands; they correct the most common wrong assumptions.

- **Reader covers resources only, not Entra or Intune.** Users, groups, sign-ins, devices come from Microsoft Graph and need a separate `microsoft` module connection. If the user expects Entra coverage from this skill, redirect them.
- **SubImage scans every subscription the SP can see, not every subscription that exists.** There is no subscription toggle; control the scope with Reader bindings. New subscriptions auto-onboard only if the binding is at the Management Group root above them.
- **Management Group bindings propagate to current AND future child subscriptions.** Use them when the user wants automatic onboarding. Use per-subscription bindings only when the scope must stay frozen.
- **Client secrets expire.** Default expiry on `az ad sp create-for-rbac` is 1 year. Pre-create with `--years <N>` matching the customer's rotation policy, or queue a rotation reminder.
- **An `AuthorizationFailed` on one scope usually means a missing binding, not a missing privileged role.** `Reader` grants `*/read`, including role assignments. Find the subscription or management group in the error and add `Reader` (or `Management Group Reader`) there. If `Reader` is already effective at that scope, look for a deny assignment blocking it (`az role assignment list --scope <SCOPE> --include-inherited` shows the bindings; deny assignments are under **Access control (IAM) → Deny assignments**). Never grant `User Access Administrator`: it can change access, which a read-only scanner must not have.
- **Do not pass the placeholder strings.** `<TENANT_DIRECTORY_ID>`, `<SUBSCRIPTION_IDS>`, `<APP_ID>`, `<CLIENT_SECRET>` must be substituted. `az` will reject obviously-malformed UUIDs but will sometimes accept partial garbage and fail later in unhelpful ways.
- **A Secrets Manager ARN needs the separate Secrets account setup.** `SubImageScanRole` does not grant secret access. Before using an ARN for the client secret, configure the account and `SubImageSecretsRole` as described below.

## Path A: az CLI

```bash
# Pick a name for the SP.
APP_NAME="subimage-sp"

# 1. Create the SP and a client secret. Scope it to the Reader role on the
#    first subscription so the command both creates and binds in one shot.
az ad sp create-for-rbac \
  --name "$APP_NAME" \
  --role Reader \
  --scopes /subscriptions/<FIRST_SUBSCRIPTION_ID>
# This prints { appId, password, tenant }. Save them now.

# 2. For every additional subscription, add another Reader binding.
APP_ID=<appId-from-step-1>
for SUB in <SUBSCRIPTION_ID_2> <SUBSCRIPTION_ID_3>; do
  az role assignment create \
    --assignee "$APP_ID" \
    --role Reader \
    --scope "/subscriptions/$SUB"
done
```

For Management Group scope (covers every current and future subscription under it):

```bash
az role assignment create \
  --assignee "$APP_ID" \
  --role Reader \
  --scope "/providers/Microsoft.Management/managementGroups/<MGMT_GROUP_ID>"
```

With subscription-scoped Reader only, grant hierarchy read at the Tenant Root Group (its ID is the tenant ID):

```bash
az role assignment create \
  --assignee "$APP_ID" \
  --role "Management Group Reader" \
  --scope "/providers/Microsoft.Management/managementGroups/<TENANT_DIRECTORY_ID>"
```

## Path B: Terraform

```hcl
# subimage_azure.tf
variable "subimage_subscription_ids" {
  type        = list(string)
  description = "Subscription IDs SubImage should be granted Reader on."
}

resource "azuread_application" "subimage" {
  display_name = "subimage-sp"
}

resource "azuread_service_principal" "subimage" {
  client_id = azuread_application.subimage.client_id
}

resource "azuread_application_password" "subimage" {
  application_id = azuread_application.subimage.id
  display_name   = "subimage-default"
  # end_date_relative = "8760h"  # 1 year, rotate before expiry
}

resource "azurerm_role_assignment" "subimage_reader" {
  for_each             = toset(var.subimage_subscription_ids)
  scope                = "/subscriptions/${each.key}"
  role_definition_name = "Reader"
  principal_id         = azuread_service_principal.subimage.object_id
}

# With subscription-scoped Reader only: read the management-group hierarchy.
resource "azurerm_role_assignment" "subimage_mg_reader" {
  scope                = "/providers/Microsoft.Management/managementGroups/<TENANT_DIRECTORY_ID>"
  role_definition_name = "Management Group Reader"
  principal_id         = azuread_service_principal.subimage.object_id
}

output "subimage_client_id" {
  value = azuread_application.subimage.client_id
}

output "subimage_client_secret" {
  value     = azuread_application_password.subimage.value
  sensitive = true
}
```

For Management Group scope, replace the role assignment with:

```hcl
resource "azurerm_role_assignment" "subimage_reader_mg" {
  scope                = "/providers/Microsoft.Management/managementGroups/<MGMT_GROUP_ID>"
  role_definition_name = "Reader"
  principal_id         = azuread_service_principal.subimage.object_id
}
```

Pull the secret:

```bash
terraform output -raw subimage_client_secret
```

## Register the module in SubImage

1. SubImage → **Modules → Add → azure**.
2. Fill:
   - `azure_tenant_id`: `<TENANT_DIRECTORY_ID>`
   - `azure_client_id`: the app id from Step 1 (or Terraform output)
   - `azure_client_secret`: the password (or its AWS Secrets Manager ARN)
3. Save and **Run Sync**. SubImage scans every subscription the SP can see.

### One-time delegated sync (no service principal)

Only when the user can't create a service principal or grant admin consent, and needs a snapshot of what one signed-in user can read. It is attended, manual and short-lived, so don't propose it as a default.

Before the run, tell the user what it changes, because it writes to the same inventory a service principal would:
- Coverage is whatever the user's Azure roles allow. Subscriptions from earlier runs that the user can't see are **removed**. Don't use it to refresh an existing inventory with a narrower identity.
- The token only reaches Azure Resource Manager. Key Vault secrets, keys and certificates aren't synced, but existing ones are kept. Synapse pipelines and linked services are treated as empty, so earlier ones are removed.
- The token can't be refreshed; the sync stops if it expires.

1. The user signs in on a trusted workstation: `az login --tenant <TENANT_DIRECTORY_ID>`.
2. Immediately before the run, the user mints an Azure Resource Manager token. **The user runs this themselves; never ask for or handle the output:**

   ```bash
   az account get-access-token \
     --tenant <TENANT_DIRECTORY_ID> \
     --resource https://management.azure.com \
     --query '{accessToken: accessToken, expires_on: expires_on}' \
     --output json
   ```

3. In **Modules → azure**: schedule **Manual**, `azure_tenant_id`, enable `azure_delegated_auth`, paste the JSON into `azure_delegated_access_token`, leave the client ID and secret empty. Save and **Run Sync**.
4. Afterwards: disable delegated auth, clear the token, save.

A Microsoft Graph token is rejected: the **microsoft** module has its own delegated sync with a Graph token. Full steps: https://app.subimage.io/docs/modules/azure/setup#one-time-delegated-sync

### AWS Secrets Manager option

If the user chooses an ARN instead of SubImage's managed secret field:

1. Open SubImage → **Settings → Configuration** and save the AWS account ID that owns the secret.
2. Copy the SubImage-generated External ID.
3. Deploy `SubImageSecretsRole` in that account with a trust-policy `sts:ExternalId` condition matching the copied value.
4. Paste the secret ARN into `azure_client_secret`.

SubImage supports one Secrets account per tenant. The managed secret field does not require this AWS setup.

## Verification

```bash
az login --service-principal \
  --username <APP_ID> \
  --password <CLIENT_SECRET> \
  --tenant <TENANT_DIRECTORY_ID>

az account list --query "[].{id:id, name:name, state:state}" -o table
az resource list --subscription <SUBSCRIPTION_ID> --query "[0:3].{name:name, type:type}" -o table
```

The first command should authenticate; the second should show every subscription the SP has been bound to.

Then in any MCP-connected AI client:

```
subimageListModules()
```

Find the entry with `module_name: azure`. Expect `last_sync_status: success` and a `last_sync_completed_at` after the sync you started. If it shows `config_error` or `failed`, read `last_sync_error`.

## Troubleshooting

- **`AuthorizationFailed` on a specific subscription**: that subscription is missing the Reader binding. Repeat `az role assignment create` for it, or add it to the Terraform list.
- **Sub list looks shorter than expected**: SubImage only sees subs the SP has been granted access to. A Management Group binding fixes this in one shot.
- **Entra users / Intune devices missing**: expected. This module covers resources only; configure the **microsoft** module to also pull Entra and Intune.

## References

- Canonical doc: https://app.subimage.io/docs/modules/azure
- Secrets account setup: https://app.subimage.io/docs/secrets
- Microsoft module (Entra + Intune): https://app.subimage.io/docs/modules/microsoft
