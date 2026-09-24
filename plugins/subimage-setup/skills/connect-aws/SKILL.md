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

`SubImageScanRole` needs the AWS managed policy `arn:aws:iam::aws:policy/SecurityAudit` plus these six inline policies. The names and actions match the canonical SubImage template, and every path below includes the full JSON.

| Inline policy | Grants |
|---|---|
| `AllowSSOResourceSpecificActions` | IAM Identity Center (SSO) reads that support resource-level permissions, scoped to SSO ARNs |
| `AllowSSOGlobalActions` | IAM Identity Center and Identity Store reads that do not support resource-level permissions |
| `AllowEKSIdentityRead` | EKS access entry and identity provider config reads |
| `AllowPublicSSMParameterRead` | AWS-managed public SSM parameters under `/aws/service/` |
| `AllowECRRead` | ECR image pulls used by the image scanner |
| `AllowGlueInspectorRead` | `glue:GetConnections` and `inspector2:ListMembers` for the glue and inspector sync stages |

`SecurityAudit` already covers most discovery actions including `eks:DescribeCluster` and `eks:ListAccessEntries`. Keep the policy names and action lists identical across paths.

## Gotchas

Read these before generating any commands; they correct the most common wrong assumptions.

- **Service-managed StackSets skip the management account.** Targeting the org root is not enough. Deploy a standalone stack on the management account separately if you want it scanned.
- **`SecurityAudit` is broad but not complete.** It covers `eks:DescribeCluster` and `eks:ListAccessEntries`. The inline `AllowEKSIdentityRead` adds only the three actions that are missing (`DescribeAccessEntry`, `ListIdentityProviderConfigs`, `DescribeIdentityProviderConfig`). Do not duplicate or you make the policy harder to audit.
- **Public SSM parameter reads need an explicit permission.** `SecurityAudit` does not include `ssm:GetParametersByPath`. Scope `AllowPublicSSMParameterRead` to the accountless `/aws/service/...` public parameter hierarchy so SubImage can ingest its default Bottlerocket and EKS optimized AMI recommendation paths.
- **Glue and Inspector reads need an explicit permission.** `SecurityAudit` does not include `glue:GetConnections` or `inspector2:ListMembers`. Without `AllowGlueInspectorRead`, the AWS glue and inspector sync stages fail with `AccessDenied`.
- **Keep the SSO policies as two scoped lists.** `AllowSSOResourceSpecificActions` scopes the Identity Center reads that support resource-level permissions to SSO ARNs. `AllowSSOGlobalActions` holds the SSO and Identity Store reads that do not support them, so it uses `Resource: '*'`. Do not collapse either one into `sso:Describe*`, `sso:Get*`, or `sso:List*` wildcards. Wildcards grant more than the canonical template does, and the role no longer matches what the SubImage docs tell customers to deploy.
- **Principal ARN format is non-obvious.** It is `arn:aws:iam::<TENANT_ACCOUNT_ID>:role/<TENANT_ID>-subimage-readonly`. The role name is `<TENANT_ID>-subimage-readonly`, NOT `subimage-readonly` or `<tenant>-readonly`. Copying the wrong form means the trust policy passes `terraform plan` but every sync fails with `AccessDenied`.
- **Service-managed StackSets need org-level prerequisites.** AWS Organizations must be set up with all-features enabled and trusted access for CloudFormation StackSets. If `create-stack-set --permission-model SERVICE_MANAGED` fails with "trusted access is not enabled", run `aws organizations enable-aws-service-access --service-principal=stacksets.cloudformation.amazonaws.com` first.
- **IAM is global; pick one StackSet region.** The role gets created once per account regardless of how many regions you target. Use `us-east-1` and stop. Multi-region targeting on an IAM-only stack just multiplies the work.
- **Do not pass the placeholder strings.** `<TENANT_ACCOUNT_ID>` and `<TENANT_ID>` are typed in this skill so it is obvious you must substitute. AWS will accept the literal string in the trust policy and the trust will silently never resolve.
- **Roles from an older copy of this skill need an update.** Earlier versions granted SSO through a single `AllowSSORead` wildcard policy and had no `AllowGlueInspectorRead`. Re-deploy with the current policies: update the StackSet and the management-account stack (Path A), or run `terraform apply` (Path B). Both remove `AllowSSORead` for you. For Path C, follow the update step at the end of that section, because `put-role-policy` never removes a policy.

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
           - PolicyName: AllowSSOResourceSpecificActions
             PolicyDocument:
               Version: '2012-10-17'
               Statement:
                 - Effect: Allow
                   Action:
                     - sso:DescribeAccountAssignmentCreationStatus
                     - sso:DescribeAccountAssignmentDeletionStatus
                     - sso:DescribeApplication
                     - sso:DescribeApplicationAssignment
                     - sso:DescribeApplicationProvider
                     - sso:DescribeInstance
                     - sso:DescribeInstanceAccessControlAttributeConfiguration
                     - sso:DescribePermissionSet
                     - sso:DescribePermissionSetProvisioningStatus
                     - sso:DescribeTrustedTokenIssuer
                     - sso:GetApplicationAccessScope
                     - sso:GetApplicationAssignmentConfiguration
                     - sso:GetApplicationAuthenticationMethod
                     - sso:GetApplicationGrant
                     - sso:GetInlinePolicyForPermissionSet
                     - sso:GetPermissionsBoundaryForPermissionSet
                     - sso:ListAccountAssignmentCreationStatus
                     - sso:ListAccountAssignmentDeletionStatus
                     - sso:ListAccountAssignments
                     - sso:ListAccountAssignmentsForPrincipal
                     - sso:ListAccountsForProvisionedPermissionSet
                     - sso:ListApplicationAccessScopes
                     - sso:ListApplicationAssignments
                     - sso:ListApplicationAssignmentsForPrincipal
                     - sso:ListApplicationAuthenticationMethods
                     - sso:ListApplicationGrants
                     - sso:ListApplicationProviders
                     - sso:ListCustomerManagedPolicyReferencesInPermissionSet
                     - sso:ListManagedPoliciesInPermissionSet
                     - sso:ListPermissionSetProvisioningStatus
                     - sso:ListPermissionSets
                     - sso:ListPermissionSetsProvisionedToAccount
                     - sso:ListTagsForResource
                     - sso:ListTrustedTokenIssuers
                   Resource:
                     - 'arn:aws:sso::*:application/*/*'
                     - 'arn:aws:sso::*:trustedTokenIssuer/*/*'
                     - 'arn:aws:sso:::account/*'
                     - 'arn:aws:sso:::instance/*'
                     - 'arn:aws:sso:::permissionSet/*/*'
                     - 'arn:aws:sso::aws:applicationProvider/*'
           - PolicyName: AllowSSOGlobalActions
             PolicyDocument:
               Version: '2012-10-17'
               Statement:
                 - Effect: Allow
                   Action:
                     - sso:DescribeRegisteredRegions
                     - sso:GetApplicationInstance
                     - sso:GetApplicationTemplate
                     - sso:GetManagedApplicationInstance
                     - sso:GetMfaDeviceManagementForDirectory
                     - sso:GetPermissionSet
                     - sso:GetProfile
                     - sso:GetSharedSsoConfiguration
                     - sso:GetSsoConfiguration
                     - sso:GetSSOStatus
                     - sso:GetTrust
                     - sso:ListApplicationInstanceCertificates
                     - sso:ListApplicationInstances
                     - sso:ListApplications
                     - sso:ListApplicationTemplates
                     - sso:ListDirectoryAssociations
                     - sso:ListInstances
                     - sso:ListProfileAssociations
                     - sso:ListProfiles
                     - identitystore:ListGroups
                     - identitystore:ListGroupMemberships
                     - identitystore:ListUsers
                   Resource: '*'
           - PolicyName: AllowEKSIdentityRead
             PolicyDocument:
               Version: '2012-10-17'
               Statement:
                 - Effect: Allow
                   Action:
                     - eks:DescribeAccessEntry
                     - eks:ListIdentityProviderConfigs
                     - eks:DescribeIdentityProviderConfig
                   Resource: '*'
           - PolicyName: AllowPublicSSMParameterRead
             PolicyDocument:
               Version: '2012-10-17'
               Statement:
                 - Effect: Allow
                   Action: ssm:GetParametersByPath
                   Resource: !Sub 'arn:${AWS::Partition}:ssm:*::parameter/aws/service/*'
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
   Outputs:
     SubImageScanRoleArn:
       Description: ARN of the created SubImage scanning IAM Role.
       Value: !GetAtt SubImageScanRole.Arn
   ```

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

resource "aws_iam_role_policy" "subimage_sso_resource_specific_actions" {
  name = "AllowSSOResourceSpecificActions"
  role = aws_iam_role.subimage_scan_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "sso:DescribeAccountAssignmentCreationStatus",
        "sso:DescribeAccountAssignmentDeletionStatus",
        "sso:DescribeApplication",
        "sso:DescribeApplicationAssignment",
        "sso:DescribeApplicationProvider",
        "sso:DescribeInstance",
        "sso:DescribeInstanceAccessControlAttributeConfiguration",
        "sso:DescribePermissionSet",
        "sso:DescribePermissionSetProvisioningStatus",
        "sso:DescribeTrustedTokenIssuer",
        "sso:GetApplicationAccessScope",
        "sso:GetApplicationAssignmentConfiguration",
        "sso:GetApplicationAuthenticationMethod",
        "sso:GetApplicationGrant",
        "sso:GetInlinePolicyForPermissionSet",
        "sso:GetPermissionsBoundaryForPermissionSet",
        "sso:ListAccountAssignmentCreationStatus",
        "sso:ListAccountAssignmentDeletionStatus",
        "sso:ListAccountAssignments",
        "sso:ListAccountAssignmentsForPrincipal",
        "sso:ListAccountsForProvisionedPermissionSet",
        "sso:ListApplicationAccessScopes",
        "sso:ListApplicationAssignments",
        "sso:ListApplicationAssignmentsForPrincipal",
        "sso:ListApplicationAuthenticationMethods",
        "sso:ListApplicationGrants",
        "sso:ListApplicationProviders",
        "sso:ListCustomerManagedPolicyReferencesInPermissionSet",
        "sso:ListManagedPoliciesInPermissionSet",
        "sso:ListPermissionSetProvisioningStatus",
        "sso:ListPermissionSets",
        "sso:ListPermissionSetsProvisionedToAccount",
        "sso:ListTagsForResource",
        "sso:ListTrustedTokenIssuers",
      ]
      Resource = [
        "arn:aws:sso::*:application/*/*",
        "arn:aws:sso::*:trustedTokenIssuer/*/*",
        "arn:aws:sso:::account/*",
        "arn:aws:sso:::instance/*",
        "arn:aws:sso:::permissionSet/*/*",
        "arn:aws:sso::aws:applicationProvider/*",
      ]
    }]
  })
}

resource "aws_iam_role_policy" "subimage_sso_global_actions" {
  name = "AllowSSOGlobalActions"
  role = aws_iam_role.subimage_scan_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "sso:DescribeRegisteredRegions",
        "sso:GetApplicationInstance",
        "sso:GetApplicationTemplate",
        "sso:GetManagedApplicationInstance",
        "sso:GetMfaDeviceManagementForDirectory",
        "sso:GetPermissionSet",
        "sso:GetProfile",
        "sso:GetSharedSsoConfiguration",
        "sso:GetSsoConfiguration",
        "sso:GetSSOStatus",
        "sso:GetTrust",
        "sso:ListApplicationInstanceCertificates",
        "sso:ListApplicationInstances",
        "sso:ListApplications",
        "sso:ListApplicationTemplates",
        "sso:ListDirectoryAssociations",
        "sso:ListInstances",
        "sso:ListProfileAssociations",
        "sso:ListProfiles",
        "identitystore:ListGroups",
        "identitystore:ListGroupMemberships",
        "identitystore:ListUsers",
      ]
      Resource = "*"
    }]
  })
}

resource "aws_iam_role_policy" "subimage_eks_identity_read" {
  name = "AllowEKSIdentityRead"
  role = aws_iam_role.subimage_scan_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "eks:DescribeAccessEntry",
        "eks:ListIdentityProviderConfigs",
        "eks:DescribeIdentityProviderConfig",
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
      ]
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

SSO_RESOURCE_SPECIFIC_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "sso:DescribeAccountAssignmentCreationStatus",
      "sso:DescribeAccountAssignmentDeletionStatus",
      "sso:DescribeApplication",
      "sso:DescribeApplicationAssignment",
      "sso:DescribeApplicationProvider",
      "sso:DescribeInstance",
      "sso:DescribeInstanceAccessControlAttributeConfiguration",
      "sso:DescribePermissionSet",
      "sso:DescribePermissionSetProvisioningStatus",
      "sso:DescribeTrustedTokenIssuer",
      "sso:GetApplicationAccessScope",
      "sso:GetApplicationAssignmentConfiguration",
      "sso:GetApplicationAuthenticationMethod",
      "sso:GetApplicationGrant",
      "sso:GetInlinePolicyForPermissionSet",
      "sso:GetPermissionsBoundaryForPermissionSet",
      "sso:ListAccountAssignmentCreationStatus",
      "sso:ListAccountAssignmentDeletionStatus",
      "sso:ListAccountAssignments",
      "sso:ListAccountAssignmentsForPrincipal",
      "sso:ListAccountsForProvisionedPermissionSet",
      "sso:ListApplicationAccessScopes",
      "sso:ListApplicationAssignments",
      "sso:ListApplicationAssignmentsForPrincipal",
      "sso:ListApplicationAuthenticationMethods",
      "sso:ListApplicationGrants",
      "sso:ListApplicationProviders",
      "sso:ListCustomerManagedPolicyReferencesInPermissionSet",
      "sso:ListManagedPoliciesInPermissionSet",
      "sso:ListPermissionSetProvisioningStatus",
      "sso:ListPermissionSets",
      "sso:ListPermissionSetsProvisionedToAccount",
      "sso:ListTagsForResource",
      "sso:ListTrustedTokenIssuers"
    ],
    "Resource": [
      "arn:aws:sso::*:application/*/*",
      "arn:aws:sso::*:trustedTokenIssuer/*/*",
      "arn:aws:sso:::account/*",
      "arn:aws:sso:::instance/*",
      "arn:aws:sso:::permissionSet/*/*",
      "arn:aws:sso::aws:applicationProvider/*"
    ]
  }]
}
EOF
)

aws iam put-role-policy \
  --role-name SubImageScanRole \
  --policy-name AllowSSOResourceSpecificActions \
  --policy-document "$SSO_RESOURCE_SPECIFIC_POLICY"

SSO_GLOBAL_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "sso:DescribeRegisteredRegions",
      "sso:GetApplicationInstance",
      "sso:GetApplicationTemplate",
      "sso:GetManagedApplicationInstance",
      "sso:GetMfaDeviceManagementForDirectory",
      "sso:GetPermissionSet",
      "sso:GetProfile",
      "sso:GetSharedSsoConfiguration",
      "sso:GetSsoConfiguration",
      "sso:GetSSOStatus",
      "sso:GetTrust",
      "sso:ListApplicationInstanceCertificates",
      "sso:ListApplicationInstances",
      "sso:ListApplications",
      "sso:ListApplicationTemplates",
      "sso:ListDirectoryAssociations",
      "sso:ListInstances",
      "sso:ListProfileAssociations",
      "sso:ListProfiles",
      "identitystore:ListGroups",
      "identitystore:ListGroupMemberships",
      "identitystore:ListUsers"
    ],
    "Resource": "*"
  }]
}
EOF
)

aws iam put-role-policy \
  --role-name SubImageScanRole \
  --policy-name AllowSSOGlobalActions \
  --policy-document "$SSO_GLOBAL_POLICY"

aws iam put-role-policy \
  --role-name SubImageScanRole \
  --policy-name AllowEKSIdentityRead \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["eks:DescribeAccessEntry","eks:ListIdentityProviderConfigs","eks:DescribeIdentityProviderConfig"],"Resource":"*"}]}'

AWS_PARTITION=$(aws sts get-caller-identity --query Arn --output text | cut -d: -f2)

aws iam put-role-policy \
  --role-name SubImageScanRole \
  --policy-name AllowPublicSSMParameterRead \
  --policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"ssm:GetParametersByPath\",\"Resource\":\"arn:${AWS_PARTITION}:ssm:*::parameter/aws/service/*\"}]}"

aws iam put-role-policy \
  --role-name SubImageScanRole \
  --policy-name AllowECRRead \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["ecr:GetAuthorizationToken","ecr:BatchCheckLayerAvailability","ecr:GetDownloadUrlForLayer","ecr:BatchGetImage"],"Resource":"*"}]}'

aws iam put-role-policy \
  --role-name SubImageScanRole \
  --policy-name AllowGlueInspectorRead \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["glue:GetConnections","inspector2:ListMembers"],"Resource":"*"}]}'
```

**Updating a role created by an earlier version of this skill:** run every command above except `create-role`, since the role already exists. `put-role-policy` overwrites a policy by name but never removes one, so delete the retired SSO wildcard policy after the new SSO policies are in place:

```bash
aws iam delete-role-policy \
  --role-name SubImageScanRole \
  --policy-name AllowSSORead
```

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
- **`AccessDenied` on `glue:GetConnections` or `inspector2:ListMembers`**: the role is missing `AllowGlueInspectorRead`, usually because it was deployed from an older copy of this skill. Add it through the same path you deployed with.
- **Management account missing from scans, StackSet otherwise healthy**: expected. Service-managed StackSets skip the management account; deploy the standalone stack there.

## References

- Canonical doc: https://app.subimage.io/docs/modules/aws
- StackSet limitations: AWS docs on service-managed permissions.
