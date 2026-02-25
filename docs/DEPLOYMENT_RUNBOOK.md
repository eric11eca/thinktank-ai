# Deployment Runbook

Operational procedures for deploying, updating, and maintaining the Thinktank.ai production environment.

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Initial Deployment](#2-initial-deployment)
3. [Rolling Updates](#3-rolling-updates)
4. [Database Migration Procedures](#4-database-migration-procedures)
5. [Rollback Procedures](#5-rollback-procedures)
6. [Emergency Procedures](#6-emergency-procedures)
7. [Monitoring & Alerting Response](#7-monitoring--alerting-response)
8. [Backup & Restore Procedures](#8-backup--restore-procedures)
9. [Troubleshooting Guide](#9-troubleshooting-guide)

---

## 1. Prerequisites

### Server Requirements

| Resource     | Minimum         | Recommended       |
|--------------|-----------------|-------------------|
| CPU          | 4 cores         | 8 cores           |
| RAM          | 8 GB            | 16 GB             |
| Disk         | 50 GB SSD       | 100 GB NVMe       |
| OS           | Ubuntu 22.04+   | Ubuntu 24.04 LTS  |
| Docker       | 24.0+           | Latest stable     |
| Compose      | v2.20+          | Latest stable     |

### Required Software

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Docker Compose (included with Docker Desktop, or standalone)
# Verify:
docker --version
docker compose version

# Install additional tools
apt-get install -y curl git htop
```

### Required Secrets

| Secret               | Description                    | Where to Set            |
|----------------------|--------------------------------|-------------------------|
| `DB_PASSWORD`        | PostgreSQL password            | `.env` or GitHub Secret |
| `JWT_SECRET_KEY`     | JWT signing key                | `.env` or GitHub Secret |
| `ENCRYPTION_KEY`     | Data encryption key            | `.env` or GitHub Secret |
| `LANGCHAIN_API_KEY`  | LangSmith tracing (optional)   | `.env` or GitHub Secret |

Generate secrets:
```bash
# Generate random secrets
openssl rand -hex 32  # For JWT_SECRET_KEY
openssl rand -hex 32  # For ENCRYPTION_KEY
openssl rand -base64 24  # For DB_PASSWORD
```

---

## 2. Initial Deployment

### Step-by-Step

```bash
# 1. Clone repository
git clone https://github.com/<org>/thinktank-ai.git /opt/thinktank
cd /opt/thinktank

# 2. Create environment file
cp .env.example .env
nano .env  # Fill in all required secrets

# 3. Create TLS certificates directory
mkdir -p docker/certs
# Copy your TLS certificates here (see docs/DNS_CDN_SETUP.md)

# 4. Build and start the stack
./scripts/prod.sh start

# 5. Verify health
./scripts/prod.sh health

# 6. Run smoke tests (optional — requires Node.js on server)
./scripts/prod.sh test
```

### Post-Deployment Checklist

- [ ] All services show as healthy: `./scripts/prod.sh status`
- [ ] Health endpoint responds: `curl http://localhost/health`
- [ ] Frontend loads in browser
- [ ] Login/registration works
- [ ] API endpoints respond correctly
- [ ] SSL certificate is valid (if configured)
- [ ] DNS records point to server
- [ ] Backup service is running: `docker logs thinktank-backup`
- [ ] Monitoring endpoints available: `/metrics`

---

## 3. Rolling Updates

### Standard Update (Zero-Downtime)

```bash
cd /opt/thinktank

# 1. Pull latest code
git fetch origin main
git checkout main
git pull origin main

# 2. Review changes (especially migrations)
git log --oneline HEAD@{1}..HEAD
ls -la backend/alembic/versions/  # Check for new migrations

# 3. Build new images (does not affect running services)
./scripts/prod.sh build

# 4. Apply database migrations (if any)
docker compose -f docker/docker-compose-prod.yaml run --rm \
  gateway sh -c "cd backend && uv run alembic upgrade head"

# 5. Rolling restart (one service at a time)
docker compose -f docker/docker-compose-prod.yaml up -d --no-deps gateway
sleep 10
docker compose -f docker/docker-compose-prod.yaml up -d --no-deps langgraph
sleep 10
docker compose -f docker/docker-compose-prod.yaml up -d --no-deps worker
docker compose -f docker/docker-compose-prod.yaml up -d --no-deps nginx

# 6. Verify health
./scripts/prod.sh health
```

### Via GitHub Actions

1. Go to **Actions > Deploy** in the GitHub repository
2. Click **Run workflow**
3. Select environment: `production`
4. Optionally specify an image tag
5. Monitor the workflow run

---

## 4. Database Migration Procedures

### Pre-Migration Checklist

- [ ] Back up the database: `docker exec thinktank-backup /usr/local/bin/backup.sh`
- [ ] Review migration SQL: `cd backend && uv run alembic upgrade head --sql`
- [ ] Test migration on staging first
- [ ] Schedule maintenance window for destructive migrations

### Running Migrations

```bash
# Preview migration SQL (dry run)
docker compose -f docker/docker-compose-prod.yaml run --rm \
  gateway sh -c "cd backend && uv run alembic upgrade head --sql"

# Apply migrations
docker compose -f docker/docker-compose-prod.yaml run --rm \
  gateway sh -c "cd backend && uv run alembic upgrade head"

# Verify migration status
docker compose -f docker/docker-compose-prod.yaml run --rm \
  gateway sh -c "cd backend && uv run alembic current"
```

### Migration Rollback

```bash
# Check migration history
docker compose -f docker/docker-compose-prod.yaml run --rm \
  gateway sh -c "cd backend && uv run alembic history"

# Downgrade one revision
docker compose -f docker/docker-compose-prod.yaml run --rm \
  gateway sh -c "cd backend && uv run alembic downgrade -1"

# Downgrade to specific revision
docker compose -f docker/docker-compose-prod.yaml run --rm \
  gateway sh -c "cd backend && uv run alembic downgrade <revision_id>"
```

---

## 5. Rollback Procedures

### Image Rollback (fastest)

```bash
# 1. Check previous image tags
docker images | grep thinktank

# 2. Update compose to use previous tag or rebuild from previous commit
git log --oneline -5
git checkout <previous-commit-sha>

# 3. Rebuild and restart
./scripts/prod.sh build
docker compose -f docker/docker-compose-prod.yaml up -d

# 4. Verify
./scripts/prod.sh health
```

### Full Rollback (code + database)

```bash
# 1. Stop application services (keep database running)
docker compose -f docker/docker-compose-prod.yaml stop gateway langgraph worker nginx

# 2. Rollback database (see Section 8 for restore procedures)
docker exec thinktank-backup /usr/local/bin/restore.sh --latest

# 3. Checkout previous code
git checkout <previous-commit-sha>

# 4. Rebuild and restart
./scripts/prod.sh build
docker compose -f docker/docker-compose-prod.yaml up -d

# 5. Verify
./scripts/prod.sh health
```

---

## 6. Emergency Procedures

### Service Down — Quick Recovery

```bash
# Check what's running
./scripts/prod.sh status

# Restart specific service
docker compose -f docker/docker-compose-prod.yaml restart gateway

# Restart entire stack
./scripts/prod.sh restart

# Nuclear option: full rebuild
docker compose -f docker/docker-compose-prod.yaml down
docker compose -f docker/docker-compose-prod.yaml up --build -d
```

### Database Corruption

```bash
# 1. Stop all application services
docker compose -f docker/docker-compose-prod.yaml stop gateway langgraph worker

# 2. Check PostgreSQL status
docker exec thinktank-postgres pg_isready -U thinktank

# 3. If PostgreSQL is responsive, take an emergency backup
docker exec thinktank-backup /usr/local/bin/backup.sh

# 4. Restore from last known good backup
docker exec thinktank-backup /usr/local/bin/restore.sh --latest

# 5. Restart services
docker compose -f docker/docker-compose-prod.yaml start gateway langgraph worker
```

### Out of Disk Space

```bash
# Check disk usage
df -h
du -sh /var/lib/docker/

# Clean Docker resources
docker system prune -f          # Remove unused containers, networks
docker image prune -a -f        # Remove unused images
docker volume prune -f          # Remove unused volumes (CAREFUL!)

# Clean old backups
docker exec thinktank-backup ls -la /backups/daily/
```

### High Memory Usage

```bash
# Check container memory usage
docker stats --no-stream

# Restart memory-hungry service
docker compose -f docker/docker-compose-prod.yaml restart langgraph

# Scale down if needed
docker compose -f docker/docker-compose-prod.yaml up -d --scale langgraph=1
```

---

## 7. Monitoring & Alerting Response

### Health Check Endpoints

| Endpoint     | Expected Response              | Action on Failure         |
|--------------|--------------------------------|---------------------------|
| `/health`    | `{"status": "healthy"}`        | Check gateway logs        |
| `/metrics`   | Prometheus text format         | Check gateway process     |

### Key Metrics to Watch

| Metric                          | Warning Threshold | Critical Threshold |
|---------------------------------|-------------------|--------------------|
| `http_request_duration_seconds` | p95 > 2s          | p95 > 5s           |
| `http_requests_total` (5xx)     | > 1% of requests  | > 5% of requests   |
| Container CPU usage             | > 70%             | > 90%              |
| Container memory usage          | > 70%             | > 90%              |
| Disk usage                      | > 70%             | > 90%              |
| PostgreSQL connections           | > 80% of max      | > 95% of max       |

### Alert Response Playbook

**High Error Rate (5xx > 5%)**
1. Check gateway logs: `./scripts/prod.sh logs gateway`
2. Check if database is healthy: `docker exec thinktank-postgres pg_isready`
3. Check if Redis is healthy: `docker exec thinktank-redis redis-cli ping`
4. Restart gateway if needed: `docker compose restart gateway`

**High Latency (p95 > 5s)**
1. Check for slow database queries in gateway logs
2. Check Redis connection: `docker exec thinktank-redis redis-cli info memory`
3. Check CPU usage: `docker stats --no-stream`
4. Scale up if needed: increase `GATEWAY_REPLICAS`

**Disk Space Alert (> 90%)**
1. Clean Docker: `docker system prune -f`
2. Remove old backups: check `/backups/daily/`
3. Check log sizes
4. Expand disk if persistent issue

---

## 8. Backup & Restore Procedures

### Verify Backups are Running

```bash
# Check backup container is running
docker ps | grep backup

# Check latest backup
docker exec thinktank-backup ls -lht /backups/daily/ | head -5

# View backup logs
docker logs thinktank-backup --tail=20
```

### Manual Backup

```bash
# Trigger immediate backup
docker exec thinktank-backup /usr/local/bin/backup.sh
```

### Restore from Backup

```bash
# List available backups
docker exec thinktank-backup /usr/local/bin/restore.sh --list

# Restore latest backup (interactive confirmation required)
docker exec -it thinktank-backup /usr/local/bin/restore.sh --latest

# Restore specific backup file
docker exec -it thinktank-backup /usr/local/bin/restore.sh /backups/daily/thinktank_daily_20260225_020000.sql.gz

# Restore from S3
docker exec -it thinktank-backup /usr/local/bin/restore.sh --from-s3 backups/daily/thinktank_daily_20260225_020000.sql.gz
```

### Backup Retention Policy

| Type    | Frequency | Retention | Storage         |
|---------|-----------|-----------|-----------------|
| Daily   | Every day | 7 days    | Local + S3      |
| Weekly  | Sundays   | 4 weeks   | Local + S3      |
| Monthly | 1st       | 3 months  | Local + S3      |

---

## 9. Troubleshooting Guide

### Container Won't Start

```bash
# Check container logs
docker compose -f docker/docker-compose-prod.yaml logs <service> --tail=50

# Check Docker events
docker events --since 10m --filter type=container

# Inspect container
docker inspect <container-id> | jq '.[0].State'
```

### Database Connection Issues

```bash
# Test connectivity from gateway container
docker compose -f docker/docker-compose-prod.yaml exec gateway \
  python -c "import asyncio, asyncpg; asyncio.run(asyncpg.connect('postgresql://thinktank:pass@postgres:5432/thinktank'))"

# Check PostgreSQL logs
docker logs thinktank-postgres --tail=20

# Check active connections
docker exec thinktank-postgres psql -U thinktank -c "SELECT count(*) FROM pg_stat_activity;"
```

### Nginx Returns 502 Bad Gateway

```bash
# Check if upstream services are running
docker compose -f docker/docker-compose-prod.yaml ps gateway langgraph

# Check nginx error log
docker logs thinktank-nginx --tail=20

# Test gateway directly
docker compose -f docker/docker-compose-prod.yaml exec gateway curl http://localhost:8001/health
```

### High Memory in LangGraph

```bash
# Check memory usage
docker stats thinktank-langgraph --no-stream

# Check for memory leaks in logs
docker logs thinktank-langgraph --tail=50 | grep -i "memory\|oom"

# Restart with fresh state
docker compose -f docker/docker-compose-prod.yaml restart langgraph
```

### Redis Connection Refused

```bash
# Check Redis is running
docker exec thinktank-redis redis-cli ping

# Check Redis memory
docker exec thinktank-redis redis-cli info memory

# Flush cache if needed (non-destructive for sessions stored in DB)
docker exec thinktank-redis redis-cli FLUSHALL
```
