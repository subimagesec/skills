---
name: connect-aws
description: 'Wire one or more AWS accounts into SubImage by deploying the SubImageScanRole IAM role. Use when the user asks to "connect AWS to SubImage", "add an AWS account", "deploy SubImageScanRole", "set up AWS scanning", "wire an org into SubImage", or works in a Terraform/CloudFormation repo and wants SubImage to start collecting AWS data. Covers three deployment paths: CloudFormation StackSet (org-wide), Terraform, and manual aws-cli for one-off accounts.'
---

# Connect AWS to SubImage

## What this does

Deploys a read-only IAM role named `SubImageScanRole` in one or more AWS accounts so SubImage can assume it and inventory the account. Walks the user through three paths and asks for the values it needs before running anything.

## When to use

✅ User wants to onboard an AWS account, an Organization, or the management account into SubImage.
✅ User asks for the IAM role definition, StackSet template, or Terraform for SubImage scanning.
✅ User is in their IaC repo and wants to commit the setup as code.

❌ User wants to scan EKS clusters but already has the AWS module connected: use `subimage-setup:connect-kubernetes-outpost` (and the EKS RBAC steps reachable from there) instead.
❌ User wants to remove an account: this skill only adds; deletion goes through their CloudFormation/Terraform tooling.

## Required inputs

Before generating any commands or HCL, collect these values. **If any are missing, ask the user explicitly.** Do not invent, guess, or paste a literal placeholder string into a command.

| Value | Where to find it | If missing, ask |
|---|---|---|
| `<TENANT_ACCOUNT_ID>` | The AWS account number SubImage runs under for this tenant. Visible at **Settings → Modules → AWS** in the SubImage UI, in the principal ARN line. | "What is your SubImage tenant AWS account ID? You can find it in Settings → Modules → AWS, in the principal ARN. Format: 12 digits." |
| `<TENANT_ID>` | The customer's SubImage tenant slug (e.g. `acme`). Same screen as above. | "What is your SubImage tenant ID (the slug, e.g. `acme`)? It is part of the principal ARN at Settings → Modules → AWS." |
| `<AWS_ACCOUNT_IDS>` | The AWS account(s) to onboard. | "Which AWS account IDs should SubImage scan? Comma-separated list of 12-digit IDs." |
| Path choice | A, B, or C below. | "Which deployment path do you want? **A** CloudFormation StackSet (recommended for AWS Organizations), **B** Terraform (recommended for an IaC repo), or **C** manual `aws-cli` (one-off accounts)." |

The SubImage principal ARN that the trust policy must allow is:

```
arn:aws:iam::<TENANT_ACCOUNT_ID>:role/<TENANT_ID>-subimage-readonly
```

## Permissions baseline

`SubImageScanRole` needs:

- AWS managed policy `arn:aws:iam::aws:policy/SecurityAudit`
- Inline policies for SSO permission set read, EKS identity provider read, public SSM parameter read, ECR read, Glue and Inspector read, and SES read (full JSON in every path below)

`SecurityAudit` already covers most discovery actions, including `eks:DescribeCluster`, `eks:ListAccessEntries`, `eks:DescribeAccessEntry`, and the Identity Center and Identity Store list and describe calls. The inline additions cover only what it omits: `sso:GetPermissionSet` (AWS also evaluates it for `DescribePermissionSet`), EKS identity provider configs, AWS-managed public SSM parameters, ECR image pulls used by the image scanner, ECR pull through cache rules, Glue connections, Inspector members, and SES email identities.

## Gotchas

Read these before generating any commands; they correct the most common wrong assumptions.

- **Service-managed StackSets skip the management account.** Targeting the org root is not enough. Deploy a standalone stack on the management account separately if you want it scanned.
- **`SecurityAudit` is broad but not complete.** It covers `eks:DescribeCluster`, `eks:ListAccessEntries`, `eks:DescribeAccessEntry`, and the Identity Center list and describe calls. The inline policies add only actions it omits, such as `eks:ListIdentityProviderConfigs`, `eks:DescribeIdentityProviderConfig`, and `sso:GetPermissionSet`. Do not duplicate `SecurityAudit` actions or widen the SSO policy to `sso:*` wildcards; both make the policy harder to audit.
- **Public SSM parameter reads need an explicit permission.** `SecurityAudit` does not include `ssm:GetParametersByPath`. Scope `AllowPublicSSMParameterRead` to the accountless `/aws/service/...` public parameter hierarchy so SubImage can ingest its default Bottlerocket and EKS optimized AMI recommendation paths.
- **Principal ARN format is non-obvious.** It is `arn:aws:iam::<TENANT_ACCOUNT_ID>:role/<TENANT_ID>-subimage-readonly`. The role name is `<TENANT_ID>-subimage-readonly`, NOT `subimage-readonly` or `<tenant>-readonly`. Copying the wrong form means the trust policy passes `terraform plan` but every sync fails with `AccessDenied`.
- **Service-managed StackSets need org-level prerequisites.** AWS Organizations must be set up with all-features enabled and trusted access for CloudFormation StackSets. If `create-stack-set --permission-model SERVICE_MANAGED` fails with "trusted access is not enabled", run `aws organizations enable-aws-service-access --service-principal=stacksets.cloudformation.amazonaws.com` first.
- **IAM is global; pick one StackSet region.** The role gets created once per account regardless of how many regions you target. Use `us-east-1` and stop. Multi-region targeting on an IAM-only stack just multiplies the work.
- **Do not pass the placeholder strings.** `<TENANT_ACCOUNT_ID>` and `<TENANT_ID>` are typed in this skill so it is obvious you must substitute. AWS will accept the literal string in the trust policy and the trust will silently never resolve.

## Path A: CloudFormation StackSet (recommended for AWS Organizations)

Deploys the role into every existing and future account in the organization. Service-managed StackSets do **not** deploy to the management account. Run a standalone stack there if you want it scanned too.

1. Save this template as `subimage-scan-role.yaml`. Substitute `<TENANT_ACCOUNT_ID>` and `<TENANT_ID>` first; do not pass the angle-bracket form to AWS.

   ```yaml
   AWSTemplateFormatVersion: '2010-09-09'
   Description: IAM role used by SubImage to inventory this AWS account.
   Resources:
     SubImageScanRole:
       Type: AWS::IAM::Role
       Properties:
         RoleName: SubImageScanRole
         AssumeRolePolicyDocument:
           Version: '2012-10-17'
           Statement:
             - Effect: Allow
               Principal:
                 AWS:
                   - 'arn:aws:iam::<TENANT_ACCOUNT_ID>:role/<TENANT_ID>-subimage-readonly'
               Action: sts:AssumeRole
         ManagedPolicyArns:
           - arn:aws:iam::aws:policy/SecurityAudit
         Policies:
           - PolicyName: AllowEKSIdentityRead
             PolicyDocument:
               Version: '2012-10-17'
               Statement:
                 - Effect: Allow
                   Action:
                     - eks:ListIdentityProviderConfigs
                     - eks:DescribeIdentityProviderConfig
                   Resource: '*'
           - PolicyName: AllowECRRead
             PolicyDocument:
               Version: '2012-10-17'
               Statement:
                 - Effect: Allow
                   Action:
                     - ecr:GetAuthorizationToken
                     - ecr:BatchCheckLayerAvailability
                     - ecr:GetDownloadUrlForLayer
                     - ecr:BatchGetImage
                     - ecr:DescribePullThroughCacheRules
                   Resource: '*'
           - PolicyName: AllowPublicSSMParameterRead
             PolicyDocument:
               Version: '2012-10-17'
               Statement:
                 - Effect: Allow
                   Action: ssm:GetParametersByPath
                   Resource: !Sub 'arn:${AWS::Partition}:ssm:*::parameter/aws/service/*'
           - PolicyName: AllowSSOGlobalActions
             PolicyDocument:
               Version: '2012-10-17'
               Statement:
                 - Effect: Allow
                   Action:
                     - sso:GetPermissionSet
                   Resource: '*'
           - PolicyName: AllowGlueInspectorRead
             PolicyDocument:
               Version: '2012-10-17'
               Statement:
                 - Effect: Allow
                   Action:
                     - glue:GetConnections
                     - inspector2:ListMembers
                   Resource: '*'
           - PolicyName: AllowSESRead
             PolicyDocument:
               Version: '2012-10-17'
               Statement:
                 - Effect: Allow
                   Action:
                     - ses:ListEmailIdentities
                   Resource: '*'
   Outputs:
     SubImageScanRoleArn:
       Description: ARN of the created SubImage scanning IAM Role.
       Value: !GetAtt SubImageScanRole.Arn
   ```

   This matches the canonical template at https://app.subimage.io/docs/modules/aws. Every inline policy grants only read actions that `SecurityAudit` omits, so do not add actions that `SecurityAudit` already covers.

2. Create the StackSet with service-managed permissions:

   ```bash
   aws cloudformation create-stack-set \
     --stack-set-name SubImageScanRole \
     --template-body file://subimage-scan-role.yaml \
     --permission-model SERVICE_MANAGED \
     --auto-deployment Enabled=true,RetainStacksOnAccountRemoval=false \
     --capabilities CAPABILITY_NAMED_IAM
   ```

3. Target every account and every region:

   ```bash
   aws cloudformation create-stack-instances \
     --stack-set-name SubImageScanRole \
     --deployment-targets OrganizationalUnitIds=<root-ou-id> \
     --regions us-east-1
   ```

   Replace `<root-ou-id>` with your org root or specific OU IDs (`aws organizations list-roots` returns the root id).

4. **For the management account**, deploy the same template as a standalone stack:

   ```bash
   aws cloudformation create-stack \
     --stack-name SubImageScanRole \
     --template-body file://subimage-scan-role.yaml \
     --capabilities CAPABILITY_NAMED_IAM
   ```

## Path B: Terraform

Use this when the IAM is owned by IaC. For a single account, drop the file in your existing module. For org-wide deployment, wrap the same template in `aws_cloudformation_stack_set` plus `aws_cloudformation_stack_set_instance`.

```hcl
# subimage_scan_role.tf
resource "aws_iam_role" "subimage_scan_role" {
  name = "SubImageScanRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        AWS = [
          "arn:aws:iam::<TENANT_ACCOUNT_ID>:role/<TENANT_ID>-subimage-readonly",
        ]
      }
      Action = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "subimage_security_audit" {
  role       = aws_iam_role.subimage_scan_role.name
  policy_arn = "arn:aws:iam::aws:policy/SecurityAudit"
}

resource "aws_iam_role_policy" "subimage_eks_identity_read" {
  name = "AllowEKSIdentityRead"
  role = aws_iam_role.subimage_scan_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "eks:ListIdentityProviderConfigs",
        "eks:DescribeIdentityProviderConfig",
      ]
      Resource = "*"
    }]
  })
}

resource "aws_iam_role_policy" "subimage_ecr_read" {
  name = "AllowECRRead"
  role = aws_iam_role.subimage_scan_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:DescribePullThroughCacheRules",
      ]
      Resource = "*"
    }]
  })
}

data "aws_partition" "current" {}

resource "aws_iam_role_policy" "subimage_public_ssm_parameter_read" {
  name = "AllowPublicSSMParameterRead"
  role = aws_iam_role.subimage_scan_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "ssm:GetParametersByPath"
      Resource = "arn:${data.aws_partition.current.partition}:ssm:*::parameter/aws/service/*"
    }]
  })
}

resource "aws_iam_role_policy" "subimage_sso_global_actions" {
  name = "AllowSSOGlobalActions"
  role = aws_iam_role.subimage_scan_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sso:GetPermissionSet"]
      Resource = "*"
    }]
  })
}

resource "aws_iam_role_policy" "subimage_glue_inspector_read" {
  name = "AllowGlueInspectorRead"
  role = aws_iam_role.subimage_scan_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "glue:GetConnections",
        "inspector2:ListMembers",
      ]
      Resource = "*"
    }]
  })
}

resource "aws_iam_role_policy" "subimage_ses_read" {
  name = "AllowSESRead"
  role = aws_iam_role.subimage_scan_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ses:ListEmailIdentities"]
      Resource = "*"
    }]
  })
}

output "subimage_scan_role_arn" {
  value = aws_iam_role.subimage_scan_role.arn
}
```

Substitute `<TENANT_ACCOUNT_ID>` and `<TENANT_ID>` before `terraform apply`. If the user wants the values pulled from variables, suggest:

```hcl
variable "subimage_tenant_account_id" { type = string }
variable "subimage_tenant_id"         { type = string }
```

and reference `var.subimage_tenant_account_id`, `var.subimage_tenant_id` in the principal ARN.

## Path C: Manual aws-cli

For a one-off account or environments without IaC. Run with credentials in the target account.

```bash
TRUST_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "AWS": "arn:aws:iam::<TENANT_ACCOUNT_ID>:role/<TENANT_ID>-subimage-readonly" },
    "Action": "sts:AssumeRole"
  }]
}
EOF
)

aws iam create-role \
  --role-name SubImageScanRole \
  --assume-role-policy-document "$TRUST_POLICY"

aws iam attach-role-policy \
  --role-name SubImageScanRole \
  --policy-arn arn:aws:iam::aws:policy/SecurityAudit

aws iam put-role-policy \
  --role-name SubImageScanRole \
  --policy-name AllowEKSIdentityRead \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["eks:ListIdentityProviderConfigs","eks:DescribeIdentityProviderConfig"],"Resource":"*"}]}'

aws iam put-role-policy \
  --role-name SubImageScanRole \
  --policy-name AllowECRRead \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["ecr:GetAuthorizationToken","ecr:BatchCheckLayerAvailability","ecr:GetDownloadUrlForLayer","ecr:BatchGetImage","ecr:DescribePullThroughCacheRules"],"Resource":"*"}]}'

AWS_PARTITION=$(aws sts get-caller-identity --query Arn --output text | cut -d: -f2)

aws iam put-role-policy \
  --role-name SubImageScanRole \
  --policy-name AllowPublicSSMParameterRead \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"ssm:GetParametersByPath\",\"Resource\":\"arn:${AWS_PARTITION}:ssm:*::parameter/aws/service/*\"}]}"

aws iam put-role-policy \
  --role-name SubImageScanRole \
  --policy-name AllowSSOGlobalActions \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["sso:GetPermissionSet"],"Resource":"*"}]}'

aws iam put-role-policy \
  --role-name SubImageScanRole \
  --policy-name AllowGlueInspectorRead \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["glue:GetConnections","inspector2:ListMembers"],"Resource":"*"}]}'

aws iam put-role-policy \
  --role-name SubImageScanRole \
  --policy-name AllowSESRead \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["ses:ListEmailIdentities"],"Resource":"*"}]}'
```

**Updating a role created with an earlier version of this path.** Skip `create-role` and rerun everything else in the block above, including the `AWS_PARTITION` assignment that the `AllowPublicSSMParameterRead` document depends on. `put-role-policy` only adds or replaces the named policy, so the old `AllowSSORead` wildcard policy stays attached until you delete it:

```bash
aws iam delete-role-policy \
  --role-name SubImageScanRole \
  --policy-name AllowSSORead

aws iam list-role-policies --role-name SubImageScanRole
```

`delete-role-policy` returns `NoSuchEntity` if the policy is already gone. The listing should show exactly `AllowEKSIdentityRead`, `AllowECRRead`, `AllowPublicSSMParameterRead`, `AllowSSOGlobalActions`, `AllowGlueInspectorRead`, and `AllowSESRead`. If the role is managed by CloudFormation or Terraform, update it through Path A or B instead; both remove renamed policies automatically, and deleting a policy those tools own by hand causes drift.

## Register the accounts in SubImage

After the role exists, the user must add the accounts to the AWS module:

1. Open SubImage → **Modules → Add → aws** (or edit if already present).
2. Set `aws_account_ids` to a comma-separated list of every account ID that has the role deployed (include the management account if you ran the standalone stack there).
3. Optional: set `aws_resource_functions` to a subset (e.g. `s3,iam,ssm`) for faster targeted scans. Leave empty for all collectors.
4. Save. Hit **Run Sync** to trigger immediately, or wait for the hourly schedule.

## Verification

Run from a host that has SubImage's tenant credentials, or call the MCP tool from a connected client:

```bash
aws sts assume-role \
  --role-arn arn:aws:iam::<one-account-id>:role/SubImageScanRole \
  --role-session-name verify
```

A successful response with `Credentials` confirms the trust policy. Then in any MCP-connected AI client:

```
subimageListModules()
```

Look for `aws` with `status: synced` and a recent `lastSyncEndedAt`.

## Troubleshooting

- **`AccessDenied` on `sts:AssumeRole`**: trust policy does not list the SubImage principal ARN, or you copied a placeholder literal. Re-run path A/B/C with the substituted `<TENANT_ACCOUNT_ID>` / `<TENANT_ID>`.
- **`AccessDenied` on a service action**: managed policy missing or inline policy missing. Confirm `SecurityAudit` is attached and the inline policies above are present.
- **`AccessDenied` on `ssm:GetParametersByPath`**: add or update `AllowPublicSSMParameterRead`. If the AWS module uses public parameter prefixes outside `/aws/service/...`, scope the policy to those exact accountless parameter ARNs too.
- **Management account missing from scans, StackSet otherwise healthy**: expected. Service-managed StackSets skip the management account; deploy the standalone stack there.

## References

- Canonical doc: https://app.subimage.io/docs/modules/aws
- StackSet limitations: AWS docs on service-managed permissions.
