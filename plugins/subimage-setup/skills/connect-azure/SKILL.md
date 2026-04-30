---
name: connect-azure
description: Connect an Azure tenant to SubImage by creating a service principal with Reader role on the subscriptions you want scanned. Use when the user asks to "connect Azure to SubImage", "set up Azure scanning", "create the SubImage Azure SP", "wire Azure into SubImage", or works in a Terraform repo and wants SubImage to inventory their Azure subscriptions, resource groups, and Entra. Covers Terraform and az-cli paths.
---

# Connect Azure to SubImage

## What this does

Registers an application in Microsoft Entra (Azure AD), creates a service principal, generates a client secret, and grants `Reader` on the subscriptions to scan. Walks two paths: Terraform and `az` CLI.

## When to use

✅ User wants to onboard one or more Azure subscriptions, or a Management Group root, into SubImage.
✅ User asks for the Azure service principal, role assignment, or Terraform for SubImage scanning.
✅ User is in their IaC repo and wants the Azure setup committed as code.

❌ User wants Entra ID (users, groups, sign-ins) or Intune coverage: this skill only covers the Azure resource plane. Add the **microsoft** module on top.
❌ User wants to scan AKS at the cluster layer: Reader on the subscription gives metadata only; for in-cluster RBAC, use a separate Kubernetes path.

## Required inputs

Before running anything, collect these. **If any are missing, ask the user explicitly.**

| Value | Where to find it | If missing, ask |
|---|---|---|
| `<TENANT_DIRECTORY_ID>` | Azure Directory / Tenant ID. `az account show --query tenantId -o tsv`. | "What is your Azure Directory (Tenant) ID? Run `az account show --query tenantId -o tsv` to find it." |
| `<SUBSCRIPTION_IDS>` | One or more subscription IDs SubImage should scan. | "Which Azure subscription IDs should SubImage scan? Comma-separated list, or tell me to use a Management Group root instead." |
| `<MGMT_GROUP_ID>` | Optional: the Management Group ID if you want a single binding to cover many subs. | (Only if user picks the MG path) "What is the Management Group ID? `az account management-group list -o table`." |
| Sync-all toggle | Whether SubImage should sync every subscription the SP can see, or only the explicit list. | "Do you want SubImage to scan every subscription the SP can see (`azure_sync_all_subscriptions=true`), or only the specific subscription IDs you provided?" |
| Path choice | Terraform or `az`. | "Which path: Terraform (recommended for IaC repos) or `az` CLI (one-off setup)?" |

## Permissions baseline

`Reader` (built-in role) on each in-scope subscription, or once on the Management Group root.

`Reader` is enough for resource-plane inventory. Entra ID and Intune objects are NOT covered by this role; they need API permissions on Microsoft Graph, configured via the **microsoft** module.

## Gotchas

Read these before generating any commands; they correct the most common wrong assumptions.

- **Reader covers resources only, not Entra or Intune.** Users, groups, sign-ins, devices come from Microsoft Graph and need a separate `microsoft` module connection. If the user expects Entra coverage from this skill, redirect them.
- **`azure_sync_all_subscriptions=true` does NOT mean "scan every subscription that exists".** It scans every subscription the SP has been granted Reader on. New subscriptions auto-onboard only if the binding is at the Management Group root above them.
- **Management Group bindings propagate to current AND future child subscriptions.** Use them when the user wants automatic onboarding. Use per-subscription bindings only when the scope must stay frozen.
- **Client secrets expire.** Default expiry on `az ad sp create-for-rbac` is 1 year. Pre-create with `--years <N>` matching the customer's rotation policy, or queue a rotation reminder.
- **`Reader` does not allow listing role assignments by default in some hardened Azure configurations.** If `subimageListModules` shows azure stuck in `permission_denied` despite the role being attached, ask the user whether their tenant restricts `Microsoft.Authorization/roleAssignments/read` and add `User Access Administrator` (read-only via custom role) only if needed.
- **Do not pass the placeholder strings.** `<TENANT_DIRECTORY_ID>`, `<SUBSCRIPTION_IDS>`, `<APP_ID>`, `<CLIENT_SECRET>` must be substituted. `az` will reject obviously-malformed UUIDs but will sometimes accept partial garbage and fail later in unhelpful ways.

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
   - `azure_sync_all_subscriptions`: `true` to scan every sub the SP can see, `false` to scan only the ones you bound.
3. Save and **Run Sync**.

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

Look for `azure` with `status: synced`.

## Troubleshooting

- **`AuthorizationFailed` on a specific subscription**: that subscription is missing the Reader binding. Repeat `az role assignment create` for it, or add it to the Terraform list.
- **Sub list looks shorter than expected**: with `azure_sync_all_subscriptions=true`, SubImage only sees subs the SP has been granted access to. A Management Group binding fixes this in one shot.
- **Entra users / Intune devices missing**: expected. This module covers resources only; configure the **microsoft** module to also pull Entra and Intune.

## References

- Canonical doc: https://app.subimage.io/docs/modules/azure
- Microsoft module (Entra + Intune): https://app.subimage.io/docs/modules/microsoft
