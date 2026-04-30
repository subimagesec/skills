# subimage-setup

Onboarding recipes for [SubImage](https://subimage.io) data sources from your IaC or CLI environment. Each skill walks the agent through deploying the credentials and IAM SubImage needs to inventory a cloud or SaaS account.

## Install

```bash
claude plugin marketplace add subimagesec/skills
claude plugin install subimage-setup@subimage
```

## Skills

| Skill | What it does |
|---|---|
| [`subimage-setup:connect-aws`](./skills/connect-aws/SKILL.md) | Deploy `SubImageScanRole` via CloudFormation StackSet, Terraform, or `aws-cli`. |
| [`subimage-setup:connect-gcp`](./skills/connect-gcp/SKILL.md) | Create the org-level service account and grant the IAM read roles via Terraform or `gcloud`. |
| [`subimage-setup:connect-azure`](./skills/connect-azure/SKILL.md) | Create a service principal with `Reader` on subscriptions or a Management Group via Terraform or `az`. |
| [`subimage-setup:connect-kubernetes-outpost`](./skills/connect-kubernetes-outpost/SKILL.md) | Deploy the SubImage Outpost (Helm or Docker) so SubImage can reach private APIs (private EKS/GKE/AKS, on-prem Jamf, etc.). |
| [`subimage-setup:connect-github`](./skills/connect-github/SKILL.md) | Install the SubImage GitHub App, or wire a PAT for GitHub Enterprise Server. |

## Prerequisites

None on the SubImage side : these skills generate the IaC / CLI artifacts; they do not require an authenticated SubImage tenant connection. To **verify** the result after deploying, install [`subimage-mcp`](../subimage-mcp/) and run `subimageListModules` against your tenant.

## Conventions

Every skill follows the same shape:

1. **Required inputs** : the agent asks the user for tenant slug, account ids, etc. It never invents values or pastes literal `{{...}}` placeholders.
2. **Gotchas** : environment-specific facts that defy reasonable assumptions (StackSet skipping the management account, Helm-vs-Docker `?ephemeral=true` quirk, Reader-vs-Entra split, etc.).
3. **Multiple paths** when several deployment styles are valid; the recommended path is marked.
4. **Verification** : a concrete CLI check the user can run before declaring the skill done.
