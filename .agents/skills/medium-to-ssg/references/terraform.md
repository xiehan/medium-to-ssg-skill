# Terraform Infrastructure Reference

## Overview of files to create

```
terraform/
├── versions.tf          # Terraform and provider version requirements
├── variables.tf         # Input variables
├── providers.tf         # AWS provider + us-east-1 alias for ACM
├── s3.tf                # S3 bucket (private) + bucket policy
├── acm.tf               # ACM certificate + DNS validation
├── cloudfront.tf        # OAC, CloudFront Function, distribution
├── route53.tf           # Hosted zone, A/AAAA records, validation CNAMEs
├── iam.tf               # GitHub Actions OIDC provider + role + policy
├── budget.tf            # AWS Budget filtered by domain tag
├── resource_group.tf    # AWS Resource Group filtered by domain tag
├── outputs.tf           # Key values needed post-apply
├── backend.tf.example   # State backend template (local, S3, or HCP Terraform)
├── README.md            # Setup and apply instructions
└── functions/
    └── viewer_request.js  # CloudFront Function: www redirect + index rewrite
```

---

## Key design decisions

**Private S3 + OAC**: The bucket is private. CloudFront reads it using Origin Access Control (OAC), the modern replacement for Origin Access Identity (OAI). The bucket policy allows only the specific CloudFront distribution to call `s3:GetObject`.

**Two AWS providers**: ACM certificates for CloudFront must be in `us-east-1`. A provider alias handles this:
```hcl
provider "aws" { alias = "us_east_1"; region = "us-east-1" }
```
Use `provider = aws.us_east_1` on `aws_acm_certificate` and `aws_acm_certificate_validation` only.

**CloudFront Function**: A JavaScript function runs on every viewer request to handle two things:
1. `www.example.com` → `example.com` permanent redirect (301)
2. Directory requests (`/path/`) → `/path/index.html` rewrite (required because CloudFront's `default_root_object` only applies to the root `/`)

**403 = 404**: Because the bucket is private, S3 returns 403 (not 404) for missing objects. Map both 403 and 404 to Hugo's `404.html` in the CloudFront `custom_error_response` blocks.

**default_tags**: Apply a `domain` tag to all resources via `default_tags` on both provider configurations. This enables per-domain cost tracking via AWS Cost Explorer and the Budget filter.

---

## versions.tf

Require a modern Terraform. **1.10 is the hard minimum** for this project: the S3 backend's native state locking (`use_lockfile`) lands in 1.10, and pinning here keeps everyone on a supported, current release. Don't lower this floor to accommodate an older install — instead, have the user upgrade (`brew upgrade terraform`, or download the latest from <https://developer.hashicorp.com/terraform/install>).

```hcl
terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
```

## variables.tf

```hcl
variable "domain_name" {
  description = "The bare domain name without www."
  type        = string
}

variable "aws_region" {
  description = "AWS region for S3 and regional resources. ACM is always in us-east-1."
  type        = string
  default     = "us-east-1"
}

variable "github_repo" {
  description = "GitHub repository in 'username/repo' format."
  type        = string
}

variable "budget_amount" {
  description = "Monthly budget limit for this domain."
  type        = number
  default     = 1
}

variable "budget_currency" {
  description = "Currency for the budget limit."
  type        = string
  default     = "USD"
}
```

## providers.tf

```hcl
provider "aws" {
  region = var.aws_region
  default_tags { tags = { domain = var.domain_name } }
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags { tags = { domain = var.domain_name } }
}
```

## s3.tf

```hcl
resource "aws_s3_bucket" "site" {
  bucket = var.domain_name
}

resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_policy" "site" {
  bucket = aws_s3_bucket.site.id
  policy = data.aws_iam_policy_document.site_bucket.json
  depends_on = [aws_s3_bucket_public_access_block.site]
}

data "aws_iam_policy_document" "site_bucket" {
  statement {
    sid    = "AllowCloudFrontOAC"
    effect = "Allow"
    principals { type = "Service"; identifiers = ["cloudfront.amazonaws.com"] }
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.site.arn}/*"]
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.site.arn]
    }
  }
}
```

## acm.tf

```hcl
resource "aws_acm_certificate" "site" {
  provider                  = aws.us_east_1
  domain_name               = var.domain_name
  subject_alternative_names = ["www.${var.domain_name}"]
  validation_method         = "DNS"
  lifecycle { create_before_destroy = true }
}

resource "aws_acm_certificate_validation" "site" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.site.arn
  validation_record_fqdns = [for r in aws_route53_record.acm_validation : r.fqdn]
  timeouts { create = "30m" }
}
```

## functions/viewer_request.js

```javascript
function handler(event) {
    var request = event.request;
    var uri = request.uri;
    var host = request.headers.host.value;

    // Redirect www → bare domain
    if (host.startsWith('www.')) {
        return {
            statusCode: 301,
            statusDescription: 'Moved Permanently',
            headers: { location: { value: 'https://' + host.slice(4) + uri } }
        };
    }

    // Rewrite directory requests to index.html
    // (CloudFront default_root_object only handles the root /)
    var lastSegment = uri.split('/').pop();
    if (lastSegment === '') {
        request.uri = uri + 'index.html';
    } else if (!lastSegment.includes('.')) {
        request.uri = uri + '/index.html';
    }

    return request;
}
```

## cloudfront.tf

```hcl
resource "aws_cloudfront_origin_access_control" "site" {
  name                              = var.domain_name
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_function" "viewer_request" {
  name    = "${replace(var.domain_name, ".", "-")}-viewer-request"
  runtime = "cloudfront-js-2.0"
  publish = true
  code    = file("${path.module}/functions/viewer_request.js")
}

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

resource "aws_cloudfront_distribution" "site" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  aliases             = [var.domain_name, "www.${var.domain_name}"]

  origin {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = "s3-${var.domain_name}"
    origin_access_control_id = aws_cloudfront_origin_access_control.site.id
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-${var.domain_name}"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.caching_optimized.id

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.viewer_request.arn
    }
  }

  custom_error_response {
    error_code            = 403
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 10
  }

  custom_error_response {
    error_code            = 404
    response_code         = 404
    response_page_path    = "/404.html"
    error_caching_min_ttl = 10
  }

  restrictions { geo_restriction { restriction_type = "none" } }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.site.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}
```

## route53.tf

```hcl
resource "aws_route53_zone" "site" {
  name = var.domain_name
}

# A and AAAA alias records for both apex and www → CloudFront
resource "aws_route53_record" "apex_a" {
  zone_id = aws_route53_zone.site.zone_id; name = var.domain_name; type = "A"
  alias { name = aws_cloudfront_distribution.site.domain_name
          zone_id = aws_cloudfront_distribution.site.hosted_zone_id
          evaluate_target_health = false }
}
resource "aws_route53_record" "apex_aaaa" {
  zone_id = aws_route53_zone.site.zone_id; name = var.domain_name; type = "AAAA"
  alias { name = aws_cloudfront_distribution.site.domain_name
          zone_id = aws_cloudfront_distribution.site.hosted_zone_id
          evaluate_target_health = false }
}
resource "aws_route53_record" "www_a" {
  zone_id = aws_route53_zone.site.zone_id; name = "www.${var.domain_name}"; type = "A"
  alias { name = aws_cloudfront_distribution.site.domain_name
          zone_id = aws_cloudfront_distribution.site.hosted_zone_id
          evaluate_target_health = false }
}
resource "aws_route53_record" "www_aaaa" {
  zone_id = aws_route53_zone.site.zone_id; name = "www.${var.domain_name}"; type = "AAAA"
  alias { name = aws_cloudfront_distribution.site.domain_name
          zone_id = aws_cloudfront_distribution.site.hosted_zone_id
          evaluate_target_health = false }
}

# ACM DNS validation records (one per domain/SAN)
resource "aws_route53_record" "acm_validation" {
  for_each = {
    for dvo in aws_acm_certificate.site.domain_validation_options :
    dvo.domain_name => { name = dvo.resource_record_name
                         type = dvo.resource_record_type
                         record = dvo.resource_record_value }
  }
  zone_id         = aws_route53_zone.site.zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.record]
  ttl             = 60
  allow_overwrite = true
}
```

After the Route 53 zone is created, add any additional DNS records the user needs to preserve (email, verification records, etc.) to this file. See `references/dns-cutover.md` for guidance.

## iam.tf

```hcl
# GitHub Actions OIDC provider.
# If this already exists in your account, import it:
#   terraform import aws_iam_openid_connect_provider.github \
#     arn:aws:iam::ACCOUNT_ID:oidc-provider/token.actions.githubusercontent.com
resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1",
                     "1c58a3a8518e8759bf075b76b750d4f2df264fcd"]
}

resource "aws_iam_role" "github_actions" {
  name = "${replace(var.domain_name, ".", "-")}-github-actions"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = { "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com" }
        StringLike   = { "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:*" }
      }
    }]
  })
}

resource "aws_iam_policy" "github_actions_deploy" {
  name = "${replace(var.domain_name, ".", "-")}-deploy"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "S3Sync"; Effect = "Allow"
        Action = ["s3:PutObject", "s3:DeleteObject", "s3:GetObject"]
        Resource = "${aws_s3_bucket.site.arn}/*" },
      { Sid = "S3List"; Effect = "Allow"
        Action = ["s3:ListBucket"]
        Resource = aws_s3_bucket.site.arn },
      { Sid = "CFInvalidate"; Effect = "Allow"
        Action = ["cloudfront:CreateInvalidation"]
        Resource = aws_cloudfront_distribution.site.arn },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "github_actions_deploy" {
  role       = aws_iam_role.github_actions.name
  policy_arn = aws_iam_policy.github_actions_deploy.arn
}
```

## budget.tf

```hcl
resource "aws_budgets_budget" "site" {
  name         = "${var.domain_name}-domain-budget-monthly"
  budget_type  = "COST"
  time_unit    = "MONTHLY"
  limit_amount = tostring(var.budget_amount)
  limit_unit   = var.budget_currency
  cost_filter {
    name   = "TagKeyValue"
    values = [join("$", ["domain", var.domain_name])]
  }
}
```

Note: The `domain` tag must be activated as a cost allocation tag in AWS Billing settings before this filter works. Activate it at: AWS Console → Billing → Cost allocation tags.

## resource_group.tf

```hcl
resource "aws_resourcegroups_group" "site" {
  name = var.domain_name
  resource_query {
    query = jsonencode({
      ResourceTypeFilters = ["AWS::AllSupported"]
      TagFilters = [{ Key = "domain", Values = [var.domain_name] }]
    })
  }
}
```

## outputs.tf

```hcl
output "route53_nameservers" {
  description = "Update these at your registrar. Required before ACM validation completes."
  value       = aws_route53_zone.site.name_servers
}
output "s3_bucket_name" {
  value = aws_s3_bucket.site.id
}
output "cloudfront_distribution_id" {
  value = aws_cloudfront_distribution.site.id
}
output "cloudfront_domain_name" {
  description = "Use this to verify the site before DNS cutover."
  value       = aws_cloudfront_distribution.site.domain_name
}
output "github_actions_role_arn" {
  description = "Set as AWS_ROLE_ARN secret in GitHub."
  value       = aws_iam_role.github_actions.arn
}
```

## Choosing a state backend

This is a decision the user must make, and for someone newer to Terraform it is often the most confusing part — so walk them through it rather than just dropping a config file. Explain the concept first, then help them pick based on their situation. Record the chosen backend in `migration-status.md`.

### What "state" is and why the backend matters

Terraform records everything it creates in a **state file** (`terraform.tfstate`) — a JSON map between the resources in your `.tf` files and the real AWS resources. Terraform reads it on every `plan`/`apply` to know what already exists and what changed. Two things follow from that:

- **State is the source of truth.** Lose it and Terraform forgets it owns your CloudFront distribution, S3 bucket, etc. — a later `apply` may try to recreate things or leave orphaned resources you still pay for.
- **State can contain secrets in plaintext.** For this project that includes things like the ACM/IAM ARNs and any sensitive variable values, so it should never land in a public Git repo.

The **backend** is simply *where that state file lives and how access to it is coordinated*. Three properties matter when choosing one:

- **Durability** — is the state safe if your laptop dies?
- **Locking** — if two `apply`s run at once (e.g. you locally and a GitHub Actions run), does the backend stop them from corrupting state? This matters as soon as CI/CD also runs Terraform.
- **Setup cost** — how much do you have to stand up before you can run `terraform init`?

### The three realistic options

| Backend | State lives… | Locking | Setup effort | Good fit |
|---|---|---|---|---|
| **Local** (default if you write no `backend` block) | A `terraform.tfstate` file on your machine | None | Zero | Learning/experimenting solo, applying only from your own machine, fine with backing the file up yourself |
| **S3 + native locking** | An S3 bucket in your AWS account | Yes (native S3 lock via `use_lockfile`) | Low — create one bucket | The natural choice here: you already use AWS, want durable + locked state, and may add CI/CD later |
| **HCP Terraform** (Terraform Cloud) | HashiCorp-hosted, free tier | Yes (built in) | Low–medium — sign up, create an org + workspace, generate an API token | You want a hosted UI, run history, and PR plan comments without managing a state bucket |

Notes for the newcomer:

- **Local is a perfectly fine starting point** for a learning project. You can begin local and **migrate to a remote backend later** — add the `backend` block, run `terraform init`, and Terraform offers to copy your existing state across. Switching backends does not destroy or recreate any AWS resources.
- **S3 state locking is built in.** This project requires Terraform **1.10+** (see `versions.tf`), so the S3 backend locks state natively via `use_lockfile = true` — there's no separate DynamoDB table to create or pay for. (The old DynamoDB-based locking is legacy; don't use it here.)
- **CI/CD interaction.** The `terraform.yml` workflow in `references/cicd.md` assumes remote state. It is written for **HCP Terraform** (it reads `TF_API_TOKEN` and links to the run). If the user chooses the **S3 backend**, remove the `cli_config_credentials_token` input and have the workflow authenticate to AWS instead (the `configure-aws-credentials` action), exactly as the deploy workflow does. If the user stays on **local** state, don't generate `terraform.yml` at all — there's no shared state for CI to use; they apply from their machine like the AWS CLI path.

### Recommended default

For a user who is new to Terraform and treating this as a learning project: **start with local state** to keep the first `apply` friction-free, and recommend graduating to the **S3 backend with `use_lockfile = true`** once the site is live or as soon as they wire up GitHub Actions (whichever comes first), since they already have an AWS account. Reserve **HCP Terraform** for users who specifically want the hosted dashboard, run history, and automatic PR plan comments. Whichever they pick, make sure `*.tfstate` is gitignored (see below).

### backend.tf.example

Generate this file with all three options documented so the user can choose. Local state needs **no** `backend` block at all, so it's shown as a comment for clarity.

```hcl
# How to use this file: pick ONE option, uncomment it, rename this file to
# backend.tf, then run `terraform init`. See "Choosing a state backend" in
# references/terraform.md for help deciding.

# ---------------------------------------------------------------------------
# Option A: Local state (the default — simplest, good for learning)
# ---------------------------------------------------------------------------
# Do nothing. With no backend block, Terraform stores state in a local
# terraform.tfstate file. Back it up yourself and keep it out of Git
# (it's already in .gitignore). You can migrate to a remote backend later
# by adding one of the blocks below and re-running `terraform init`.

# ---------------------------------------------------------------------------
# Option B: S3 backend (durable + locked, stays within AWS) — recommended
#           once you go live or add CI/CD. Native state locking via
#           use_lockfile (no DynamoDB table needed; requires Terraform >= 1.10,
#           which this project already mandates).
# ---------------------------------------------------------------------------
# Create the state bucket first (a one-time step, separate from this project):
#   aws s3api create-bucket --bucket YOUR-STATE-BUCKET --region us-east-1
#   aws s3api put-bucket-versioning --bucket YOUR-STATE-BUCKET \
#     --versioning-configuration Status=Enabled   # lets you recover old state
# Then uncomment:
# terraform {
#   backend "s3" {
#     bucket       = "YOUR-STATE-BUCKET"
#     key          = "DOMAIN/terraform.tfstate"
#     region       = "us-east-1"
#     encrypt      = true
#     use_lockfile = true   # native S3 state locking (Terraform >= 1.10)
#   }
# }

# ---------------------------------------------------------------------------
# Option C: HCP Terraform / Terraform Cloud (hosted UI, run history,
#           PR plan comments). Free tier. Sign up at app.terraform.io,
#           create an organization and workspace, then uncomment:
# ---------------------------------------------------------------------------
# terraform {
#   cloud {
#     organization = "YOUR_ORG"
#     workspaces { name = "YOUR_WORKSPACE" }
#   }
# }
```

## .gitignore additions

The `.gitignore` created in Phase 3 (`references/hugo-setup.md`) only covers Hugo outputs. When the infrastructure method is Terraform, **append** the following Terraform entries to the project root `.gitignore` so local state, the provider cache, and any secret-bearing variable files are never committed:

```gitignore
# Terraform
terraform/.terraform/
*.tfstate
*.tfstate.*
crash.log
crash.*.log
*.tfvars
*.tfvars.json
override.tf
override.tf.json
*_override.tf
*_override.tf.json
.terraformrc
terraform.rc
```

**Important:**
- **Do commit `terraform/.terraform.lock.hcl`** — the dependency lock file pins provider versions and should be version-controlled. Do *not* add it to `.gitignore`.
- `*.tfstate` files can contain secrets in plaintext; never commit them. With the HCP Terraform or S3 backend, state lives remotely and isn't written locally, but the ignore entries are a safety net in case someone runs a local `terraform apply`.
- `*.tfvars` is ignored because it commonly holds sensitive values. If the user keeps a non-sensitive `terraform.tfvars` they want tracked, add an explicit exception (`!terraform/terraform.tfvars`) and confirm it contains no secrets first.
