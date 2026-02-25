# DNS & CDN Configuration Guide

This guide covers DNS record configuration, Cloudflare CDN setup, SSL/TLS certificates, and DDoS protection for Thinktank.ai deployments.

## Table of Contents

1. [DNS Records](#1-dns-records)
2. [Cloudflare Setup](#2-cloudflare-setup)
3. [SSL/TLS Certificates](#3-ssltls-certificates)
4. [CDN Caching Rules](#4-cdn-caching-rules)
5. [DDoS Protection](#5-ddos-protection)
6. [Rate Limiting](#6-rate-limiting-at-cdn-level)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. DNS Records

### Required Records

| Type  | Name              | Value                    | TTL  | Proxy |
|-------|-------------------|--------------------------|------|-------|
| A     | `@`               | `<server-ip>`            | Auto | Yes   |
| A     | `www`             | `<server-ip>`            | Auto | Yes   |
| A     | `staging`         | `<staging-server-ip>`    | Auto | Yes   |
| CNAME | `api`             | `@`                      | Auto | Yes   |

### Optional Records

| Type  | Name              | Value                              | TTL  | Proxy |
|-------|-------------------|------------------------------------|------|-------|
| MX    | `@`               | Mail provider records              | Auto | No    |
| TXT   | `@`               | `v=spf1 include:_spf.google.com ~all` | Auto | No |
| TXT   | `_dmarc`          | `v=DMARC1; p=quarantine; rua=mailto:...` | Auto | No |
| CAA   | `@`               | `0 issue "letsencrypt.org"`        | Auto | No    |

### Example: Cloudflare DNS Setup

```bash
# Using Cloudflare API (replace tokens and zone ID)
ZONE_ID="your-zone-id"
API_TOKEN="your-api-token"

# Create A record for root domain
curl -X POST "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{
    "type": "A",
    "name": "@",
    "content": "<server-ip>",
    "proxied": true
  }'

# Create A record for www subdomain
curl -X POST "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{
    "type": "A",
    "name": "www",
    "content": "<server-ip>",
    "proxied": true
  }'
```

---

## 2. Cloudflare Setup

### Initial Configuration

1. **Add site** in Cloudflare dashboard
2. **Update nameservers** at your domain registrar to Cloudflare's assigned NS records
3. **Wait for propagation** (up to 24 hours, usually minutes)

### Recommended Settings

| Setting                  | Value            | Location                    |
|--------------------------|------------------|-----------------------------|
| SSL/TLS mode             | Full (Strict)    | SSL/TLS > Overview          |
| Always Use HTTPS         | On               | SSL/TLS > Edge Certificates |
| Minimum TLS Version      | TLS 1.2          | SSL/TLS > Edge Certificates |
| Automatic HTTPS Rewrites | On               | SSL/TLS > Edge Certificates |
| HTTP/2                   | On               | Speed > Optimization        |
| HTTP/3 (QUIC)            | On               | Speed > Optimization        |
| Brotli Compression       | On               | Speed > Optimization        |
| Early Hints              | On               | Speed > Optimization        |

### Page Rules (if not using Cache Rules)

| Rule                     | URL Pattern              | Settings                        |
|--------------------------|--------------------------|---------------------------------|
| API no-cache             | `*domain.com/api/*`      | Cache Level: Bypass             |
| Health no-cache          | `*domain.com/health`     | Cache Level: Bypass             |
| Static assets            | `*domain.com/assets/*`   | Cache Level: Cache Everything, Edge TTL: 1 month |

---

## 3. SSL/TLS Certificates

### Option A: Cloudflare Universal SSL (Recommended)

With Cloudflare proxy enabled, SSL is automatic:

1. Set SSL mode to **Full (Strict)** in Cloudflare dashboard
2. Generate an **Origin Certificate** in Cloudflare for your server:
   - SSL/TLS > Origin Server > Create Certificate
   - Validity: 15 years
   - Key type: RSA (2048)
3. Install the origin certificate on your server:

```bash
# Save certificate and key
mkdir -p /opt/thinktank/certs
# Paste certificate content:
nano /opt/thinktank/certs/origin.pem
# Paste private key content:
nano /opt/thinktank/certs/origin-key.pem
chmod 600 /opt/thinktank/certs/origin-key.pem

# Update docker-compose environment
export TLS_CERTS_DIR=/opt/thinktank/certs
```

### Option B: Let's Encrypt (without Cloudflare proxy)

```bash
# Install certbot
apt-get install certbot

# Obtain certificate (stop nginx first)
certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com

# Certificate files will be at:
#   /etc/letsencrypt/live/yourdomain.com/fullchain.pem
#   /etc/letsencrypt/live/yourdomain.com/privkey.pem

# Set up auto-renewal cron
echo "0 0 1 * * certbot renew --quiet && docker compose restart nginx" | crontab -
```

---

## 4. CDN Caching Rules

### Cloudflare Cache Rules (recommended over Page Rules)

Create these rules in **Caching > Cache Rules**:

#### Rule 1: Bypass API & Dynamic Routes
- **When**: URI Path starts with `/api/` OR URI Path equals `/health` OR URI Path equals `/metrics`
- **Then**: Bypass cache

#### Rule 2: Cache Static Assets Aggressively
- **When**: URI Path starts with `/assets/`
- **Then**: Cache, Edge TTL = 30 days, Browser TTL = 30 days

#### Rule 3: Cache HTML with Revalidation
- **When**: URI Path equals `/` OR URI Path does not contain `.`
- **Then**: Cache, Edge TTL = 1 hour, Browser TTL = 0 (respect origin)

### Nginx Cache Headers (already configured)

The nginx configuration already sets appropriate cache headers:
- `/assets/*` — `Cache-Control: public, max-age=31536000, immutable`
- `index.html` — `Cache-Control: no-cache, no-store, must-revalidate`
- API responses — `Cache-Control: no-store`

---

## 5. DDoS Protection

### Cloudflare Built-in Protection

Cloudflare provides automatic L3/L4 DDoS protection when proxied. Additional measures:

#### Security Level
- **Settings**: Security > Settings
- **Recommended**: Medium (challenges suspicious visitors)

#### Bot Fight Mode
- **Settings**: Security > Bots
- **Enable**: Bot Fight Mode (free tier)

#### Firewall Rules

```
# Block known bad countries (if applicable)
# Security > WAF > Custom Rules

# Rate limit login attempts
Rule: URI Path equals "/api/auth/login" AND Request Method equals "POST"
Action: Block after 10 requests per minute per IP

# Rate limit API broadly
Rule: URI Path starts with "/api/"
Action: Block after 100 requests per minute per IP
```

#### Under Attack Mode
For active DDoS attacks, enable **Under Attack Mode** temporarily:
- Security > Settings > Under Attack Mode: On
- This adds a 5-second JavaScript challenge for all visitors

---

## 6. Rate Limiting at CDN Level

### Cloudflare Rate Limiting Rules

Create in **Security > WAF > Rate limiting rules**:

| Rule Name          | Expression                           | Requests | Period | Action    |
|--------------------|--------------------------------------|----------|--------|-----------|
| Login throttle     | URI Path eq `/api/auth/login`        | 10       | 1 min  | Block     |
| Registration limit | URI Path eq `/api/auth/register`     | 5        | 1 min  | Block     |
| API general limit  | URI Path starts with `/api/`         | 200      | 1 min  | Challenge |
| SSE connection     | URI Path contains `/stream`          | 20       | 1 min  | Block     |

### IP Access Rules

For known attackers:
- **Security > WAF > Tools > IP Access Rules**
- Block specific IPs or ranges

---

## 7. Troubleshooting

### DNS Not Resolving
```bash
# Check DNS propagation
dig +short yourdomain.com
nslookup yourdomain.com

# Check from multiple locations
# Use: https://www.whatsmydns.net/
```

### SSL Certificate Issues
```bash
# Test SSL configuration
curl -vI https://yourdomain.com 2>&1 | grep -E "SSL|certificate|subject"

# Check certificate chain
openssl s_client -connect yourdomain.com:443 -servername yourdomain.com < /dev/null 2>/dev/null | openssl x509 -noout -dates
```

### Cloudflare 521/522/523 Errors
- **521**: Web server is down — check `docker compose ps` and nginx logs
- **522**: Connection timed out — check firewall allows Cloudflare IPs
- **523**: Origin unreachable — verify server IP in DNS records

```bash
# Allow Cloudflare IPs through firewall
# https://www.cloudflare.com/ips/
for ip in $(curl -s https://www.cloudflare.com/ips-v4); do
  ufw allow from $ip to any port 443
done
```

### Cache Not Working
```bash
# Check cache status header
curl -sI https://yourdomain.com/assets/index-abc123.js | grep -i cf-cache-status
# Expected: HIT or MISS (first request)

# Purge cache
curl -X POST "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/purge_cache" \
  -H "Authorization: Bearer ${API_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"purge_everything": true}'
```
