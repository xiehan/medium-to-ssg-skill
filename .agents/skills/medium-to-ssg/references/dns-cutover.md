# DNS Cutover Reference

> **Scope:** This reference covers the **AWS** hosting path (migrating DNS to Route 53 and cutting over via nameservers). For **GitHub Pages**, you do **not** migrate DNS providers — Part 1 (reviewing and preserving records) still applies, but the cutover is just adding GitHub Pages `A`/`AAAA`/`CNAME` records at the user's existing DNS host. See `references/github-pages.md` for the GitHub Pages cutover steps.

## Part 1: Pre-Cutover DNS Review

**Do this before provisioning CloudFront and the Route 53 records** (before the final `terraform apply`, or before running `infra/06-route53-records.sh` in the AWS CLI path).

### Step 1 — Get the user's current DNS records

Ask the user to provide a screenshot or export of all DNS records at their current registrar or DNS provider. You need to see every record, not just the A records.

### Step 2 — Categorize each record

Go through the records with the user and classify each one:

| Category | Examples | Action |
|---|---|---|
| **Old hosting** | A/CNAME records pointing to old server/CDN | ❌ Do not migrate — replaced by new CloudFront A records |
| **www redirect** | CNAME `www → bare domain` | ❌ Do not migrate — replaced by CloudFront + Function |
| **Email** | MX records, SPF TXT, DKIM TXT/CNAME, DMARC TXT | ✅ Must migrate |
| **Domain verification** | TXT or CNAME from Google, Mailchimp, etc. | ✅ Migrate if still needed |
| **Nameservers** | NS records | ❌ Do not migrate — Route 53 generates its own |
| **SOA record** | SOA record | ❌ Do not migrate — Route 53 manages this |
| **Unknown** | Anything not recognized | ⚠️ Research before deciding |

### Step 3 — Add preserved records to the zone

For each record that must be migrated, add it where it belongs for the chosen infrastructure method:

- **Terraform:** add it to `route53.tf` in the formats below.
- **AWS CLI:** add an `UPSERT` `change-resource-record-sets` call to `infra/06-route53-records.sh`. The record types and cautions are identical; only the syntax differs. Example for MX:
  ```bash
  aws route53 change-resource-record-sets --hosted-zone-id "$ZONE_ID" \
    --change-batch '{"Changes":[{"Action":"UPSERT","ResourceRecordSet":{
      "Name":"example.com","Type":"MX","TTL":3600,
      "ResourceRecords":[{"Value":"10 mail.example.com."},{"Value":"20 mail2.example.com."}]}}]}'
  ```

Common Terraform examples:

**MX records (email delivery):**
```hcl
resource "aws_route53_record" "mx" {
  zone_id = aws_route53_zone.site.zone_id
  name    = var.domain_name
  type    = "MX"
  ttl     = 3600
  records = [
    "10 mail.example.com.",
    "20 mail2.example.com.",
  ]
}
```

**Multiple TXT records at apex (SPF, verification, etc.):**
```hcl
resource "aws_route53_record" "txt_apex" {
  zone_id = aws_route53_zone.site.zone_id
  name    = var.domain_name
  type    = "TXT"
  ttl     = 3600
  records = [
    "\"v=spf1 include:PROVIDER.com ~all\"",
    "\"PROVIDER-verification=abc123...\"",
  ]
}
```

**DKIM TXT record (important: keys over 255 chars must be split):**
```hcl
resource "aws_route53_record" "dkim" {
  zone_id = aws_route53_zone.site.zone_id
  name    = "SELECTOR._domainkey.${var.domain_name}"
  type    = "TXT"
  ttl     = 3600
  # If the key value exceeds 255 characters, split into multiple quoted strings:
  records = ["\"v=DKIM1; k=rsa; p=FIRST_255_CHARS\" \"REMAINING_CHARS\""]
}
```

**CNAME for domain verification:**
```hcl
resource "aws_route53_record" "verify_cname" {
  zone_id = aws_route53_zone.site.zone_id
  name    = "SUBDOMAIN.${var.domain_name}"
  type    = "CNAME"
  ttl     = 3600
  records = ["target.provider.com."]
}
```

### Step 4 — Note any unrecognized records

If the user has DNS records they don't recognize, help them identify them before proceeding. Common sources of unrecognized records:
- Old SSL certificate validation CNAMEs (from Comodo/Sectigo, DigiCert, etc.) — these are typically stale and safe to drop once verified
- Old verification records from services the user no longer uses — can usually be dropped

When in doubt, advise the user to keep the record and investigate after cutover rather than risk breaking something.

### Step 5 — Verify in Route 53 before touching the registrar

After adding all records and provisioning the zone, verify each critical record resolves correctly in Route 53 **before** updating nameservers. Query a Route 53 nameserver directly (bypassing the current live DNS):

```bash
# Terraform: get a nameserver from the output
NS=$(terraform output -raw route53_nameservers | head -1)
# AWS CLI: source the saved zone id and read the delegation set
#   source infra/.zone_id
#   NS=$(aws route53 get-hosted-zone --id "$ZONE_ID" \
#     --query 'DelegationSet.NameServers[0]' --output text)

# Verify each record type
dig MX example.com @$NS
dig TXT example.com @$NS
dig A example.com @$NS
```

Confirm the output matches the expected values before proceeding to Part 2.

---

## Part 2: Cutover & Go-Live

### Step 1 — Two-phase provisioning

Both methods create the Route 53 zone first so the user can update nameservers, then create everything else once Route 53 is authoritative.

**Terraform — Phase 1 apply** (targets only the Route 53 zone, ACM cert, and validation records):

```bash
terraform apply \
  -target=aws_route53_zone.site \
  -target=aws_acm_certificate.site \
  -target=aws_route53_record.acm_validation
```

After this completes, get the Route 53 nameservers:
```bash
terraform output route53_nameservers
```

**AWS CLI — Phase 1** (run the zone script; it prints the nameservers):
```bash
./infra/03-route53-zone.sh
```

### Step 2 — Update nameservers at the registrar

Log into the registrar (iwantmyname, Namecheap, GoDaddy, etc.) and replace the current nameservers with the four Route 53 NS values from the output. This is the point of no return for DNS authority — after propagation, Route 53 is serving DNS for this domain.

Note: This transfers DNS authority only. It does not move the domain registration. The registrar still holds the registration; only the nameservers change.

### Step 3 — Wait for propagation

Monitor propagation:
```bash
# Keep running until NS records show Route 53 nameservers
watch dig NS example.com
```

Propagation typically takes 5 minutes to 1 hour, occasionally up to 24 hours depending on the registrar.

**Phase 2** (everything else — CloudFront, Route 53 A records, IAM, etc.):

**Terraform:**
```bash
terraform apply
```
This will wait for ACM certificate validation to complete (up to 30 minutes) before creating the CloudFront distribution. The `aws_acm_certificate_validation` resource blocks until validation succeeds.

**AWS CLI** (run the remaining scripts in order):
```bash
./infra/04-acm-validation.sh    # adds validation records, waits for the cert
./infra/05-cloudfront.sh        # OAC + function + distribution + bucket policy
./infra/06-route53-records.sh   # apex/www aliases + preserved records
# ./infra/07-iam-github.sh      # only if using GitHub Actions deploy
```
`04-acm-validation.sh` blocks (`aws acm wait certificate-validated`) until validation succeeds, so it must run after nameservers have propagated.

### Step 4 — Verify via CloudFront URL before DNS hits

Before DNS propagation reaches you, verify the site is working at the CloudFront URL:

```bash
# Terraform:
terraform output cloudfront_domain_name
# AWS CLI:
#   source infra/.dist_id
#   aws cloudfront get-distribution --id "$DIST_ID" \
#     --query Distribution.DomainName --output text
# → something like d1234abcd.cloudfront.net
```

Open that URL in a browser. Confirm:
- [ ] HTTPS works
- [ ] Home page loads
- [ ] At least one post loads at its canonical URL (`/posts/post-slug/`)
- [ ] A Medium-style alias URL redirects correctly (`/post-slug-a1b2c3d4` → `/posts/post-slug/`)
- [ ] 404 page shows for an invalid path

### Step 5 — Verify after DNS propagation

Once `dig A example.com` returns CloudFront's IP (verify via `dig A $(terraform output -raw cloudfront_domain_name)`):
- [ ] `https://example.com` loads the site
- [ ] `https://www.example.com` redirects to `https://example.com`
- [ ] HTTP redirects to HTTPS
- [ ] Email still works (send a test email to and from the custom domain if applicable)

### Step 6 — Set up deployment

- **GitHub Actions:** Add all required secrets and variables to the GitHub repository (see `references/cicd.md`). Trigger the deploy workflow manually (`workflow_dispatch`) and verify the site deploys successfully via the CloudFront URL.
- **Manual script (AWS CLI default):** Run `./infra/deploy.sh` to build and upload the site, then verify via the CloudFront URL.

### Step 7 — Mark migration complete

Update `migration-status.md`:
- Check off Phase 7
- Add a note confirming the live URL and date completed
- Note any follow-up items (e.g. domain registration transfer, removing old hosting subscription, cancelling old service)
