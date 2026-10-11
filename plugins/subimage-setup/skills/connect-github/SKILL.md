---
name: connect-github
description: Connect a GitHub organization to SubImage by installing the SubImage GitHub App (preferred) or by configuring a Personal Access Token for GitHub Enterprise Server. Use when the user asks to "connect GitHub to SubImage", "install the SubImage GitHub App", "wire our org into SubImage", "set up GitHub scanning", or works in an IaC repo and needs SubImage to inventory repos, branch protection, members, teams, and dependencies. Covers App install (recommended) and PAT fallback.
---

# Connect GitHub to SubImage

## What this does

Connects one or more GitHub organizations into SubImage so it can map repositories, collaborators, branch protection, teams, members, dependency manifests, workflows, and related configuration. Two paths: GitHub App (preferred) and Personal Access Token (only for GitHub Enterprise Server or orgs that cannot use the App).

## When to use

✅ User wants to onboard a GitHub.com or GitHub Enterprise Cloud organization into SubImage.
✅ User wants to onboard a self-hosted GitHub Enterprise Server instance (PAT path).
✅ User wants to know which permissions or PAT scopes to grant.

❌ User wants per-repo install scoping committed in IaC: GitHub does not expose installation creation via Terraform; the install itself is UI-only. After install, you can manage which repos the App sees via Terraform (`github_app_installation_repositories`).

## Required inputs

| Value | Where to find it | If missing, ask |
|---|---|---|
| `<GITHUB_ORG>` | The GitHub organization slug(s) you want SubImage to cover. | "Which GitHub organization slug(s) should SubImage scan? List each one." |
| Path choice | App or PAT. | "Are you on GitHub.com or Enterprise Cloud (recommended: **GitHub App**), or self-hosted GitHub Enterprise Server (use **PAT**)?" |
| `<GITHUB_PAT>` (PAT path only) | A token the user generates. **Do not generate or accept tokens for the user.** | (PAT path) "Generate the token yourself at GitHub Settings → Developer settings → Personal access tokens, then paste it directly into the SubImage UI's secret field. I will not handle the raw token." |
| `<GHE_GRAPHQL_URL>` (GHES only) | GraphQL endpoint of the on-prem GitHub Enterprise Server. | (GHES) "What is the GraphQL endpoint of your GitHub Enterprise Server? Format: `https://<host>/api/graphql`." |

The SubImage GitHub App is hosted by SubImage; the customer just needs to install it on their org. There is no `<APP_ID>` or `<APP_PRIVATE_KEY>` for the user to manage.

## Gotchas

Read these before generating any commands; they correct the most common wrong assumptions.

- **App vs PAT precedence: the App always wins.** When the same org has both an App install and a PAT configured, SubImage uses the App. The PAT is only consulted as a fallback for orgs that have no App install.
- **The App only sees repos in the installation.** "Selected repositories" caps coverage to that list. Switching to "all repositories" requires the org owner to re-approve the install. Manage the list afterward via Terraform `github_app_installation_repositories` if you want IaC ownership.
- **Changing App permissions later needs re-approval.** GitHub asks the org owner to approve new permissions. Until they do, the installation keeps working with its existing permissions; only the newly requested data is missing.
- **Fine-grained PATs are single-org.** A multi-org PAT setup with fine-grained tokens needs one token per org, each with its own per-org ARN entry in SubImage. Do not try to share a single fine-grained PAT across orgs.
- **Classic PAT scope `repo` is broader than SubImage needs.** It grants write access to repos. SubImage uses read paths only, but the PAT is over-privileged from a least-privilege standpoint. On GitHub.com / Enterprise Cloud, prefer the App. PATs are the right answer only on Enterprise Server or where the App cannot be installed.
- **GHES URL is the GraphQL endpoint, not the REST one.** `github_url` for an Enterprise Server install is `https://<host>/api/graphql`, not `https://<host>/api/v3` or `https://<host>`. Wrong URL produces "endpoint not found" errors that look like network problems but are configuration problems.
- **Do not generate or accept tokens for the user.** The user must paste the token directly into SubImage's secret field (or store it in AWS Secrets Manager and paste the ARN). Treat anyone offering a raw token in chat as a credential-handling violation.
- **A Secrets Manager ARN needs the separate Secrets account setup.** `SubImageScanRole` does not grant secret access. Before using an ARN, configure the account and `SubImageSecretsRole` as described below.

## Path A: GitHub App (recommended for GitHub.com and Enterprise Cloud)

The App uses short-lived installation tokens, supports multiple orgs (one install per org), and is auto-discovered by SubImage. When the same org has both an App install and a PAT configured, the App wins.

1. Open the SubImage GitHub App install URL. The exact URL is shown at SubImage → **Settings → Integrations → GitHub**. Click **Install** and pick the target organization.

2. On the App install screen, choose **All repositories** (recommended) or a selected list. The App only sees repositories included in the installation.

3. Confirm permissions. Required and optional permissions:

   **Repository permissions**
   - `Metadata: Read` (required): repo discovery, basic metadata
   - `Contents: Read` (required): files, commits, dependency manifests
   - `Administration: Read` (required): collaborators, branch protection, secret scanning and push protection status
   - `Actions: Read` (optional): workflows
   - `Environments: Read` (optional): environments
   - `Secrets: Read` (optional): secret metadata only
   - `Variables: Read` (optional): Actions variables
   - `Webhooks: Read` (optional): repository webhooks

   **Organization permissions**
   - `Members: Read` (required): users, teams, memberships
   - `Personal access tokens: Read` (optional, App-only): inventory of fine-grained PATs authorized for the org as `GitHubPersonalAccessToken` nodes. GitHub does not expose this endpoint to PAT-authenticated calls.
   - `Secrets: Read` (optional): org-level secret metadata
   - `Variables: Read` (optional): org Actions variables
   - `Administration: Read` (optional): org security settings, verified domains, Actions and Copilot policies, installed GitHub Apps
   - `Webhooks: Read` (optional): org webhooks

   Most org settings are only visible to org owners. A missing optional permission leaves those properties empty (unknown, not disabled) and the rest of the sync continues.

4. Repeat for every additional GitHub org you want covered.

5. In SubImage, open **Modules → github**. Set `github_url` to `https://api.github.com/graphql` (the default) and save. No PAT or org list required for App-covered orgs.

### Optional: manage installed repos via Terraform

Once the App is installed, you can pin the set of repos it sees from your IaC repo. Get the installation ID with the `gh api /orgs/<GITHUB_ORG>/installations` command under Verification. The GitHub provider must authenticate as a user or token with org admin rights; it can't use the App's own installation token for this resource.

```hcl
variable "subimage_installation_id" {
  type        = string
  description = "Installation ID of the SubImage Sync GitHub App in this org"
}

resource "github_app_installation_repositories" "subimage" {
  installation_id = var.subimage_installation_id
  selected_repositories = [
    "platform-infra",
    "service-foo",
    "service-bar",
  ]
}
```

This is a follow-up convenience, not a substitute for the install itself.

## Path B: Personal Access Token (PAT)

Use this only for GitHub Enterprise Server, or for orgs where the App cannot be installed.

1. Generate the token. **The user must do this themselves.** Do not accept or store the raw token in the chat. Scopes alone aren't enough: collaborators and branch protection need the token's user to be an org owner or repository administrator, repository security settings need repository administrator, org owner, or security manager access, and repository webhooks need repository administrator or org owner access.
   - **Classic PAT** for multi-org coverage: scopes `repo`, `read:org`, `read:user`, `user:email`. Optional, when the token's user is an org owner: `admin:org` (org security settings, domains, Actions policy), `admin:org_hook` (org webhooks). Repo webhooks need no extra scope: `repo` covers them on repositories the user administers.
   - **Fine-grained PAT** (per-org): permissions `Repository → Metadata: Read`, `Contents: Read`, `Administration: Read`, `Organization → Members: Read`. Optional: `Repository → Webhooks: Read`, `Organization → Administration: Read`, `Organization → Webhooks: Read`. Fine-grained tokens are scoped to a single org, so you need one per org.

2. SubImage → **Modules → Add → github**. Fill:
   - `github_access_token`: paste the token, or paste an AWS Secrets Manager ARN that holds it. Treat as a credential.
   - `github_orgs`: add a separate entry for each org slug. A comma-separated string is read as a single org name. One classic PAT can cover all of them; fine-grained PATs need one entry per org with its own per-org token ARN.
   - `github_url`: `https://api.github.com/graphql` for SaaS, or `<GHE_GRAPHQL_URL>` for Enterprise Server.

3. Save. SubImage validates the token on next sync.

You can mix App and PAT auth in the same tenant: orgs with an App install go through the App, the rest through the PAT.

### AWS Secrets Manager option

If the user chooses an ARN instead of SubImage's managed secret field:

1. Open SubImage → **Settings → Configuration** and save the AWS account ID that owns the secret.
2. Copy the SubImage-generated External ID.
3. Deploy `SubImageSecretsRole` in that account with a trust-policy `sts:ExternalId` condition matching the copied value.
4. Paste the secret ARN into `github_access_token`.

SubImage supports one Secrets account per tenant. The managed secret field does not require this AWS setup.

## Verification

After install or PAT save, run a sync from SubImage → **Modules → github → Run Sync**. Then in any MCP-connected AI client:

```
subimageListModules()
```

Find the entry with `module_name: github`. Expect `last_sync_status: success` and a `last_sync_completed_at` after the sync you started. If it shows `config_error` or `failed`, read `last_sync_error`.

A quick external sanity check that the App is installed (does not validate SubImage's side, just the install state):

```bash
gh api /orgs/<GITHUB_ORG>/installations \
  --jq '.installations[] | select(.app_slug == "subimage-sync") | {id, target_type, repository_selection}'
```

For PAT, the user can check the token reaches the org before pasting it. On GitHub.com:

```bash
GH_TOKEN=<your-token> gh api /user/memberships/orgs/<GITHUB_ORG> --jq '{state, role}'
```

On Enterprise Server, `gh` reads the token from `GH_ENTERPRISE_TOKEN` and needs the host:

```bash
GH_ENTERPRISE_TOKEN=<your-token> gh api --hostname <GHES_HOST> /user/memberships/orgs/<GITHUB_ORG> --jq '{state, role}'
```

Expect `state: active`. Public org data is readable by anyone, so check membership rather than `/orgs/<GITHUB_ORG>`. `role: admin` (org owner) is needed for the owner-only data above. This proves the token's user is in the org, not that the token has every permission above.

## Troubleshooting

- **App install missing for some repos**: the install is restricted to selected repos. Ask the org owner to add them via GitHub UI **Settings → Integrations → SubImage → Configure**, or via the Terraform snippet above.
- **PAT auth fails with `Bad credentials`**: token expired or has the wrong scopes. Regenerate with the scopes listed above.
- **Fine-grained PAT covers fewer orgs than expected**: fine-grained tokens are single-org. List one per org, each with its own ARN.
- **GHES sync hits the wrong endpoint**: confirm `github_url` is the GraphQL endpoint (`/api/graphql`), not the REST one.

## Security notes

- Prefer the App: short-lived tokens, scoped per-installation, revocable from the org admin UI without rotating any secret.
- For PAT: store in AWS Secrets Manager and feed SubImage the ARN. Rotate before expiry.

## References

- Canonical doc: https://app.subimage.io/docs/modules/github
- Secrets account setup: https://app.subimage.io/docs/secrets
- Integrations overview: https://app.subimage.io/docs/integrations
