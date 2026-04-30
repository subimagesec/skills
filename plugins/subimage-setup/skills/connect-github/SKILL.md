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
| `<GITHUB_ORG>` | The GitHub organization slug(s) you want SubImage to cover. | "Which GitHub organization slug(s) should SubImage scan? Comma-separated if more than one." |
| Path choice | App or PAT. | "Are you on GitHub.com or Enterprise Cloud (recommended: **GitHub App**), or self-hosted GitHub Enterprise Server (use **PAT**)?" |
| `<GITHUB_PAT>` (PAT path only) | A token the user generates. **Do not generate or accept tokens for the user.** | (PAT path) "Generate the token yourself at GitHub Settings → Developer settings → Personal access tokens, then paste it directly into the SubImage UI's secret field. I will not handle the raw token." |
| `<GHE_GRAPHQL_URL>` (GHES only) | GraphQL endpoint of the on-prem GitHub Enterprise Server. | (GHES) "What is the GraphQL endpoint of your GitHub Enterprise Server? Format: `https://<host>/api/graphql`." |

The SubImage GitHub App is hosted by SubImage; the customer just needs to install it on their org. There is no `<APP_ID>` or `<APP_PRIVATE_KEY>` for the user to manage.

## Gotchas

Read these before generating any commands; they correct the most common wrong assumptions.

- **App vs PAT precedence: the App always wins.** When the same org has both an App install and a PAT configured, SubImage uses the App. The PAT is only consulted as a fallback for orgs that have no App install.
- **The App only sees repos in the installation.** "Selected repositories" caps coverage to that list. Switching to "all repositories" requires the org owner to re-approve the install. Manage the list afterward via Terraform `github_app_installation_repositories` if you want IaC ownership.
- **Changing App permissions later may force re-approval.** GitHub treats permission changes on an installed App as a new consent step; the org owner gets a re-approve banner and the install pauses until it is accepted.
- **Fine-grained PATs are single-org.** A multi-org PAT setup with fine-grained tokens needs one token per org, each with its own per-org ARN entry in SubImage. Do not try to share a single fine-grained PAT across orgs.
- **Classic PAT scope `repo` is broader than SubImage needs.** It grants write access to repos. SubImage uses read paths only, but the PAT is over-privileged from a least-privilege standpoint. On GitHub.com / Enterprise Cloud, prefer the App. PATs are the right answer only on Enterprise Server or where the App cannot be installed.
- **GHES URL is the GraphQL endpoint, not the REST one.** `github_url` for an Enterprise Server install is `https://<host>/api/graphql`, not `https://<host>/api/v3` or `https://<host>`. Wrong URL produces "endpoint not found" errors that look like network problems but are configuration problems.
- **Do not generate or accept tokens for the user.** The user must paste the token directly into SubImage's secret field (or store it in AWS Secrets Manager and paste the ARN). Treat anyone offering a raw token in chat as a credential-handling violation.

## Path A: GitHub App (recommended for GitHub.com and Enterprise Cloud)

The App uses short-lived installation tokens, supports multiple orgs (one install per org), and is auto-discovered by SubImage. When the same org has both an App install and a PAT configured, the App wins.

1. Open the SubImage GitHub App install URL. The exact URL is shown at SubImage → **Settings → Integrations → GitHub**. Click **Install** and pick the target organization.

2. On the App install screen, choose **All repositories** (recommended) or a selected list. The App only sees repositories included in the installation.

3. Confirm permissions. Required and optional permissions:

   **Repository permissions**
   - `Metadata: Read` (required): repo discovery, basic metadata
   - `Contents: Read` (required): files, commits, dependency manifests
   - `Administration: Read` (required): collaborators, branch protection
   - `Actions: Read` (optional): workflows
   - `Environments: Read` (optional): environments
   - `Secrets: Read` (optional): secret metadata only
   - `Variables: Read` (optional): Actions variables

   **Organization permissions**
   - `Members: Read` (required): users, teams, memberships
   - `Secrets: Read` (optional): org-level secret metadata
   - `Variables: Read` (optional): org Actions variables

   If you change permissions after install, GitHub may ask the org owner to re-approve.

4. Repeat for every additional GitHub org you want covered.

5. In SubImage, open **Modules → github**. Set `github_url` to `https://api.github.com/graphql` (the default) and save. No PAT or org list required for App-covered orgs.

### Optional: manage installed repos via Terraform

Once the App is installed, you can pin the set of repos it sees from your IaC repo:

```hcl
data "github_app_installation" "subimage" {
  app_slug = "subimage"
}

resource "github_app_installation_repositories" "subimage" {
  installation_id = data.github_app_installation.subimage.installation_id
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

1. Generate the token. **The user must do this themselves.** Do not accept or store the raw token in the chat.
   - **Classic PAT** for multi-org coverage: scopes `repo`, `read:org`, `read:user`, `user:email`.
   - **Fine-grained PAT** (per-org): permissions `Repository → Metadata: Read`, `Contents: Read`, `Administration: Read`, `Organization → Members: Read`. Fine-grained tokens are scoped to a single org, so you need one per org.

2. SubImage → **Modules → Add → github**. Fill:
   - `github_access_token`: paste the token, or paste an AWS Secrets Manager ARN that holds it. Treat as a credential.
   - `github_orgs`: comma-separated list of org slugs. One classic PAT can cover all of them; fine-grained PATs need one entry per org with its own per-org token ARN.
   - `github_url`: `https://api.github.com/graphql` for SaaS, or `<GHE_GRAPHQL_URL>` for Enterprise Server.

3. Save. SubImage validates the token on next sync.

You can mix App and PAT auth in the same tenant: orgs with an App install go through the App, the rest through the PAT.

## Verification

After install or PAT save, run a sync from SubImage → **Modules → github → Run Sync**. Then in any MCP-connected AI client:

```
subimageListModules()
```

Look for `github` with `status: synced` and a non-zero `lastSyncEndedAt`.

A quick external sanity check that the App is installed (does not validate SubImage's side, just the install state):

```bash
gh api /orgs/<GITHUB_ORG>/installations \
  --jq '.installations[] | select(.app_slug == "subimage") | {id, target_type, repository_selection}'
```

For PAT, validate the token reaches the right scopes before pasting it:

```bash
GH_TOKEN=<your-token> gh auth status
GH_TOKEN=<your-token> gh api /user
```

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
- Integrations overview: https://app.subimage.io/docs/integrations
