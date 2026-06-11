# AWS CLI Infrastructure Reference

This is the **alternative to Terraform** for users who do not want to install or learn Terraform — for example, when the blog is no longer actively updated and this is a one-time, set-and-forget setup. It creates the **same AWS resources** as `references/terraform.md` (private S3 + CloudFront + OAC + CloudFront Function + ACM + Route 53), using only the AWS CLI.

Generate a set of small, **idempotent** shell scripts under `infra/`. Each script can be run more than once safely (it checks for existing resources before creating). Run them in order.

> Requirements for the user: the [AWS CLI v2](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) installed and configured (`aws configure`) with credentials that can create S3, CloudFront, ACM, Route 53, and (optionally) IAM resources. **No Terraform required.**

---

## Key design decisions (identical to the Terraform path)

- **Private S3 + OAC**: The bucket is private; CloudFront reads it via Origin Access Control. The bucket policy allows only the specific CloudFront distribution to call `s3:GetObject`.
- **ACM in us-east-1**: The certificate for CloudFront must be requested in `us-east-1` regardless of where other resources live. All `aws acm ...` commands use `--region us-east-1`.
- **CloudFront Function**: Handles the `www → apex` 301 redirect and the directory → `index.html` rewrite. Identical JS to the Terraform path.
- **403 = 404**: The private bucket returns 403 for missing objects; map both 403 and 404 to `/404.html` in the distribution config.
- **Two-phase provisioning**: Create the Route 53 zone first, update nameservers at the registrar, then create the rest (ACM validation can only complete once Route 53 is authoritative). See Phase 7 in `references/dns-cutover.md`.

---

## `infra/00-config.sh`

Shared variables sourced by every other script. The agent fills in the real values.

```bash
#!/usr/bin/env bash
# Shared configuration. Edit these values, then: source 00-config.sh
export DOMAIN="example.com"
export REGION="us-east-1"            # region for S3/CloudFront-adjacent resources
export GITHUB_REPO="username/repo"   # only needed if you opt into GitHub Actions deploy
export BUCKET="$DOMAIN"              # bucket name == domain
export SAFE_NAME="${DOMAIN//./-}"    # e.g. example-com, for resource names

# AWS account id (used in policies)
export ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
```

Every other script begins with:

```bash
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/00-config.sh"
```

---

## `infra/01-s3.sh` — private bucket + public access block

```bash
# Create the bucket (skip if it already exists)
if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  if [ "$REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION"
  else
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
      --create-bucket-configuration LocationConstraint="$REGION"
  fi
fi

# Block all public access (CloudFront reads via OAC, not public ACLs)
aws s3api put-public-access-block --bucket "$BUCKET" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# Tag for cost tracking (mirrors the Terraform default_tags)
aws s3api put-bucket-tagging --bucket "$BUCKET" \
  --tagging "TagSet=[{Key=domain,Value=$DOMAIN}]"
```

The bucket **policy** is applied later in `05-cloudfront.sh`, because it must reference the CloudFront distribution ARN.

---

## `infra/02-acm.sh` — request the certificate (us-east-1)

```bash
# Request a cert for apex + www. DNS validation. Idempotent via a deterministic token.
CERT_ARN="$(aws acm list-certificates --region us-east-1 \
  --query "CertificateSummaryList[?DomainName=='$DOMAIN'].CertificateArn | [0]" \
  --output text)"

if [ "$CERT_ARN" = "None" ] || [ -z "$CERT_ARN" ]; then
  CERT_ARN="$(aws acm request-certificate --region us-east-1 \
    --domain-name "$DOMAIN" \
    --subject-alternative-names "www.$DOMAIN" \
    --validation-method DNS \
    --query CertificateArn --output text)"
fi
echo "CERT_ARN=$CERT_ARN"
# Save it for later scripts:
echo "export CERT_ARN=$CERT_ARN" > "$(dirname "$0")/.cert_arn"
```

The DNS validation **records** are added in `04-acm-validation.sh` after the hosted zone exists. Do not wait for validation here — it cannot succeed until Route 53 is authoritative.

---

## `infra/03-route53-zone.sh` — hosted zone (Phase 1 of cutover)

```bash
# Create the hosted zone if it doesn't exist
ZONE_ID="$(aws route53 list-hosted-zones-by-name --dns-name "$DOMAIN" \
  --query "HostedZones[?Name=='$DOMAIN.'].Id | [0]" --output text)"

if [ "$ZONE_ID" = "None" ] || [ -z "$ZONE_ID" ]; then
  ZONE_ID="$(aws route53 create-hosted-zone --name "$DOMAIN" \
    --caller-reference "$(date +%s)" \
    --query HostedZone.Id --output text)"
fi
ZONE_ID="${ZONE_ID##*/}"   # strip /hostedzone/ prefix
echo "export ZONE_ID=$ZONE_ID" > "$(dirname "$0")/.zone_id"

echo "=== Update these nameservers at your registrar ==="
aws route53 get-hosted-zone --id "$ZONE_ID" \
  --query DelegationSet.NameServers --output table
```

**Stop here and update nameservers at the registrar** before running the remaining scripts (see `references/dns-cutover.md`, Part 2). ACM validation and CloudFront come next.

---

## `infra/04-acm-validation.sh` — add DNS validation records

```bash
source "$(dirname "$0")/.cert_arn"
source "$(dirname "$0")/.zone_id"

# Read the validation CNAME(s) ACM expects and upsert them into the zone
aws acm describe-certificate --region us-east-1 --certificate-arn "$CERT_ARN" \
  --query 'Certificate.DomainValidationOptions[].ResourceRecord' --output json \
  | jq -c '.[]' | sort -u | while read -r rec; do
    NAME="$(echo "$rec" | jq -r .Name)"
    VALUE="$(echo "$rec" | jq -r .Value)"
    aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" \
      --change-batch "{\"Changes\":[{\"Action\":\"UPSERT\",\"ResourceRecordSet\":{
        \"Name\":\"$NAME\",\"Type\":\"CNAME\",\"TTL\":60,
        \"ResourceRecords\":[{\"Value\":\"$VALUE\"}]}}]}"
done

echo "Waiting for ACM validation (requires nameservers already updated at registrar)..."
aws acm wait certificate-validated --region us-east-1 --certificate-arn "$CERT_ARN"
echo "Certificate validated."
```

> Note: `jq` is used to parse JSON. It is preinstalled on most systems; if missing, install it (`brew install jq` / `apt-get install jq`). If the user cannot install `jq`, the agent can instead read the values from `aws acm describe-certificate` output and write the change-batch by hand.

---

## `infra/functions/viewer_request.js`

Identical to the Terraform path:

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
    var lastSegment = uri.split('/').pop();
    if (lastSegment === '') {
        request.uri = uri + 'index.html';
    } else if (!lastSegment.includes('.')) {
        request.uri = uri + '/index.html';
    }

    return request;
}
```

---

## `infra/05-cloudfront.sh` — OAC, function, distribution, bucket policy

This is the longest script. CloudFront's CLI takes a JSON config file, so the script writes one to a temp file and references the OAC and function it created. Outline:

```bash
source "$(dirname "$0")/.cert_arn"
DIR="$(dirname "$0")"

# 1. Origin Access Control (skip if present)
OAC_ID="$(aws cloudfront list-origin-access-controls \
  --query "OriginAccessControlList.Items[?Name=='$DOMAIN'].Id | [0]" --output text)"
if [ "$OAC_ID" = "None" ] || [ -z "$OAC_ID" ]; then
  OAC_ID="$(aws cloudfront create-origin-access-control \
    --origin-access-control-config \
    "Name=$DOMAIN,SigningProtocol=sigv4,SigningBehavior=always,OriginAccessControlOriginType=s3" \
    --query OriginAccessControl.Id --output text)"
fi

# 2. CloudFront Function (create + publish)
FN_NAME="${SAFE_NAME}-viewer-request"
if ! aws cloudfront describe-function --name "$FN_NAME" >/dev/null 2>&1; then
  ETAG="$(aws cloudfront create-function --name "$FN_NAME" \
    --function-config "Comment=viewer request,Runtime=cloudfront-js-2.0" \
    --function-code "fileb://$DIR/functions/viewer_request.js" \
    --query ETag --output text)"
  aws cloudfront publish-function --name "$FN_NAME" --if-match "$ETAG"
fi
FN_ARN="$(aws cloudfront describe-function --name "$FN_NAME" \
  --query FunctionSummary.FunctionMetadata.FunctionARN --output text)"

# 3. Build the distribution config JSON (apex + www aliases, OAC origin,
#    CachingOptimized managed policy, CloudFront Function on viewer-request,
#    403/404 → /404.html, ACM cert, default_root_object=index.html, PriceClass_100)
#    Write it to "$DIR/dist-config.json" then:
DIST_ID="$(aws cloudfront create-distribution \
  --distribution-config "file://$DIR/dist-config.json" \
  --query Distribution.Id --output text)"
DIST_ARN="$(aws cloudfront get-distribution --id "$DIST_ID" \
  --query Distribution.ARN --output text)"
echo "export DIST_ID=$DIST_ID" > "$DIR/.dist_id"

# 4. Bucket policy: allow only this distribution to read the bucket
aws s3api put-bucket-policy --bucket "$BUCKET" --policy "{
  \"Version\":\"2012-10-17\",
  \"Statement\":[{
    \"Sid\":\"AllowCloudFrontOAC\",\"Effect\":\"Allow\",
    \"Principal\":{\"Service\":\"cloudfront.amazonaws.com\"},
    \"Action\":\"s3:GetObject\",
    \"Resource\":\"arn:aws:s3:::$BUCKET/*\",
    \"Condition\":{\"StringEquals\":{\"AWS:SourceArn\":\"$DIST_ARN\"}}
  }]
}"
```

The `dist-config.json` the agent writes must mirror the Terraform `aws_cloudfront_distribution` in `references/terraform.md`:

- `Aliases`: `example.com` and `www.example.com`
- `DefaultRootObject`: `index.html`
- `PriceClass`: `PriceClass_100`
- One S3 origin using `OriginAccessControlId` (the OAC) and an **empty** `S3OriginConfig.OriginAccessIdentity`
- `DefaultCacheBehavior`: `GET`/`HEAD`, `ViewerProtocolPolicy=redirect-to-https`, `Compress=true`, the managed **CachingOptimized** `CachePolicyId` (`658327ea-f89d-4fab-a63d-7e88639e58f6`), and a `FunctionAssociations` entry binding `$FN_ARN` to `viewer-request`
- Two `CustomErrorResponses`: 403→/404.html (response code 404) and 404→/404.html
- `ViewerCertificate`: `ACMCertificateArn=$CERT_ARN`, `SSLSupportMethod=sni-only`, `MinimumProtocolVersion=TLSv1.2_2021`

---

## `infra/06-route53-records.sh` — alias records + preserved DNS

```bash
source "$(dirname "$0")/.zone_id"
source "$(dirname "$0")/.dist_id"

CF_DOMAIN="$(aws cloudfront get-distribution --id "$DIST_ID" \
  --query Distribution.DomainName --output text)"
# CloudFront's fixed hosted zone id for alias records:
CF_ZONE="Z2FDTNDATAQYW2"

upsert_alias () {  # $1 = record name
  aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" \
    --change-batch "{\"Changes\":[
      {\"Action\":\"UPSERT\",\"ResourceRecordSet\":{\"Name\":\"$1\",\"Type\":\"A\",
        \"AliasTarget\":{\"HostedZoneId\":\"$CF_ZONE\",\"DNSName\":\"$CF_DOMAIN\",\"EvaluateTargetHealth\":false}}},
      {\"Action\":\"UPSERT\",\"ResourceRecordSet\":{\"Name\":\"$1\",\"Type\":\"AAAA\",
        \"AliasTarget\":{\"HostedZoneId\":\"$CF_ZONE\",\"DNSName\":\"$CF_DOMAIN\",\"EvaluateTargetHealth\":false}}}
    ]}"
}

upsert_alias "$DOMAIN"
upsert_alias "www.$DOMAIN"
```

**Then add any preserved records** (MX, SPF/TXT, DKIM, verification CNAMEs) identified in the Phase 6 DNS review. Use the same `change-resource-record-sets` UPSERT pattern. See `references/dns-cutover.md` for which records to preserve — the categories and cautions are identical; only the syntax differs from the Terraform examples.

---

## `infra/07-iam-github.sh` — OPTIONAL (only for GitHub Actions deploys)

Skip this script entirely for the set-and-forget / manual-deploy default. Create it only if the user wants automated deployment via GitHub Actions. It creates the same GitHub OIDC provider + role + policy as `iam.tf` in `references/terraform.md`:

```bash
# Create the OIDC provider if it doesn't exist
if ! aws iam list-open-id-connect-providers \
    --query "OpenIDConnectProviderList[].Arn" --output text \
    | grep -q token.actions.githubusercontent.com; then
  aws iam create-open-id-connect-provider \
    --url "https://token.actions.githubusercontent.com" \
    --client-id-list "sts.amazonaws.com" \
    --thumbprint-list "6938fd4d98bab03faadb97b34396831e3780aea1"
fi

OIDC_ARN="arn:aws:iam::${ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
ROLE_NAME="${SAFE_NAME}-github-actions"

# Trust policy scoped to the repo, then create the role + inline deploy policy
# (S3 Put/Delete/Get + ListBucket on the site bucket, CloudFront CreateInvalidation).
# Mirror the JSON in references/terraform.md (iam.tf).
```

After creating the role, note its ARN — it becomes the `AWS_ROLE_ARN` GitHub secret (see `references/cicd.md`).

---

## `infra/deploy.sh` — build + deploy content (the set-and-forget default)

For users who don't want GitHub Actions, this is how they publish the site (and republish on the rare occasion they edit a post). Run it from the SSG project root — `hugo-site/` for Hugo, `eleventy-site/` for Eleventy, `astro-site/` for Astro.

```bash
#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/00-config.sh"
source "$(dirname "$0")/.dist_id"

# 1. Build (run from the site root)
hugo --minify

# 2. Sync to S3
aws s3 sync public/ "s3://$BUCKET/" --delete --cache-control "public, max-age=3600"

# 3. Invalidate the CloudFront cache
aws cloudfront create-invalidation --distribution-id "$DIST_ID" --paths "/*"

echo "Deployed. It can take a few minutes for the cache invalidation to complete."
```

> **Eleventy variant:** swap steps 1–2 for the Node toolchain and the Eleventy output directory; step 3 is unchanged:
>
> ```bash
> # 1. Build (run from eleventy-site/)
> npx @11ty/eleventy
>
> # 2. Sync to S3 (Eleventy builds into _site/, not public/)
> aws s3 sync _site/ "s3://$BUCKET/" --delete --cache-control "public, max-age=3600"
> ```
>
> The `npx @11ty/eleventy` build matches the `eleventy-base-blog` starter; if the chosen starter's `package.json` `scripts.build` does more than call `eleventy` (e.g. bundles JS or sets `ELEVENTY_ENV=production`), use that command (typically `npm run build`) here instead — see "Adapting to a different starter" in `references/eleventy-setup.md`.
>
> **Astro variant:** same shape — build with `npm run build` and sync `dist/` (not `public/`); step 3 is unchanged:
>
> ```bash
> # 1. Build (run from astro-site/)
> npm run build
>
> # 2. Sync to S3 (Astro builds into dist/, not public/)
> aws s3 sync dist/ "s3://$BUCKET/" --delete --cache-control "public, max-age=3600"
> ```
>
> Requires the Node version the starter pins (its `package.json` `engines` / `.nvmrc`) on the machine running the script. `npm run build` runs the starter's `astro build` (plus any extra steps it wraps) — see "Adapting to a different starter" in `references/astro-setup.md`.

---

## `infra/README.md` — run order

Generate a short README documenting the run order and the cutover pause:

```
1.  source 00-config.sh        # set/verify variables
2.  ./01-s3.sh                 # create private bucket
3.  ./02-acm.sh                # request certificate
4.  ./03-route53-zone.sh       # create zone, print nameservers
    >>> Update nameservers at your registrar now, wait for propagation <<<
5.  ./04-acm-validation.sh     # add validation records, wait for cert
6.  ./05-cloudfront.sh         # OAC + function + distribution + bucket policy
7.  ./06-route53-records.sh    # apex/www aliases + preserved DNS records
8.  (optional) ./07-iam-github.sh   # only for GitHub Actions deploys
9.  ./deploy.sh                # build + upload the site
```

Keep `.zone_id`, `.cert_arn`, and `.dist_id` (written by the scripts) — `deploy.sh` and re-runs rely on them. Add them to `.gitignore` if the repo is public.

---

## Tearing it down later

Because there is no Terraform state, document manual teardown in `infra/README.md` so the user can fully remove resources if they ever stop the blog: disable + delete the CloudFront distribution, delete the CloudFront Function and OAC, empty + delete the S3 bucket, delete the ACM certificate, and delete the Route 53 hosted zone (and the OIDC role/policy if created).
