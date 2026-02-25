# Backup & Restore Guide

This document covers the automated PostgreSQL backup system, including scheduling, S3 integration, retention policies, WAL archiving, and restore procedures.

## Architecture

```
docker/backup/
  backup.sh                 # Automated pg_dump with S3 upload and retention
  restore.sh                # Restore from local file or S3
  entrypoint.sh             # Cron scheduler (default) or one-shot mode
  Dockerfile                # postgres:16-alpine + aws-cli
  postgresql-backup.conf    # WAL archiving configuration
```

The backup system runs as a dedicated Docker container (`thinktank-backup`) alongside the production stack. It uses `pg_dump` piped through `gzip` for compressed SQL dumps and the AWS CLI for optional S3 uploads.

```
                   cron schedule
                        |
                        v
 entrypoint.sh --> backup.sh --> pg_dump | gzip --> /backups/{daily,weekly,monthly}/
                                   |
                                   +--> verify_backup (gzip -t)
                                   |
                                   +--> aws s3 cp (if S3_BUCKET set)
                                   |
                                   +--> apply_retention (prune old files)
```

## Quick Start

### 1. Local-only backups (no S3)

No extra configuration needed. The backup container runs with the production stack by default:

```bash
docker compose -f docker/docker-compose-prod.yaml up -d
```

Backups are stored in the `backupdata` Docker volume at `/backups/`.

### 2. Enable S3 uploads

Add these variables to your **`.env`** file in the project root:

```bash
# S3 target bucket (setting this enables S3 uploads)
S3_BACKUP_BUCKET=my-thinktank-backups
S3_BACKUP_PREFIX=backups/               # optional, default: backups/

# AWS credentials
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1
```

Then restart the backup container:

```bash
docker compose -f docker/docker-compose-prod.yaml up -d backup
```

### 3. Using MinIO or S3-compatible storage

```bash
S3_BACKUP_BUCKET=thinktank-backups
S3_ENDPOINT_URL=https://minio.example.com   # custom endpoint
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
```

## Configuration Reference

All configuration is via environment variables, set in `.env` and passed through `docker-compose-prod.yaml`.

### Scheduling

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKUP_SCHEDULE` | `0 2 * * *` | Cron expression for backup frequency |

Common schedule examples:

| Schedule | Cron expression |
|----------|----------------|
| Daily at 2:00 AM UTC (default) | `0 2 * * *` |
| Twice daily (2 AM and 2 PM) | `0 2,14 * * *` |
| Every 6 hours | `0 */6 * * *` |
| Every hour | `0 * * * *` |
| Weekdays at midnight | `0 0 * * 1-5` |

### Database Connection

| Variable | Default | Description |
|----------|---------|-------------|
| `PGHOST` | `postgres` | PostgreSQL hostname |
| `PGPORT` | `5432` | PostgreSQL port |
| `PGUSER` | `thinktank` | PostgreSQL user |
| `PGPASSWORD` | *(required)* | PostgreSQL password (set via `DB_PASSWORD` in compose) |
| `PGDATABASE` | `thinktank` | Database name |

### S3 Upload

| Variable | Default | Description |
|----------|---------|-------------|
| `S3_BACKUP_BUCKET` | *(empty = disabled)* | S3 bucket name. **Setting this enables S3 uploads.** |
| `S3_BACKUP_PREFIX` | `backups/` | Key prefix within the bucket |
| `S3_ENDPOINT_URL` | *(empty = AWS)* | Custom S3 endpoint for MinIO, R2, etc. |
| `AWS_ACCESS_KEY_ID` | *(required if S3)* | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | *(required if S3)* | AWS secret key |
| `AWS_DEFAULT_REGION` | `us-east-1` | AWS region |

### Retention

| Variable | Default | Description |
|----------|---------|-------------|
| `RETENTION_DAILY` | `7` | Number of daily backups to keep |
| `RETENTION_WEEKLY` | `4` | Number of weekly backups to keep |
| `RETENTION_MONTHLY` | `3` | Number of monthly backups to keep |

## Backup Types and Schedule

The backup script automatically classifies each run:

| Type | When | Example S3 key |
|------|------|-----------------|
| **Daily** | Every scheduled run | `backups/daily/thinktank_daily_20260225_020000.sql.gz` |
| **Weekly** | Sundays (day 7) | `backups/weekly/thinktank_weekly_20260223_020000.sql.gz` |
| **Monthly** | 1st of the month | `backups/monthly/thinktank_monthly_20260201_020000.sql.gz` |

On a Sunday that is also the 1st of the month, all three types are created.

## Backup Lifecycle

Each backup goes through these stages:

1. **Pre-flight check** -- `pg_isready` verifies PostgreSQL is reachable
2. **Dump** -- `pg_dump --no-owner --no-acl --clean --if-exists | gzip -9`
3. **Verify** -- `gzip -t` integrity check + SQL content validation
4. **Upload** -- `aws s3 cp` to the configured bucket (skipped if `S3_BUCKET` is empty)
5. **Retention** -- Old local backups beyond the retention count are deleted

On container startup, an **initial backup runs immediately** before the cron scheduler takes over.

## S3 Bucket Structure

When S3 is enabled, backups are uploaded with this key structure:

```
s3://my-thinktank-backups/
  backups/
    daily/
      thinktank_daily_20260225_020000.sql.gz
      thinktank_daily_20260224_020000.sql.gz
      ...
    weekly/
      thinktank_weekly_20260223_020000.sql.gz
      ...
    monthly/
      thinktank_monthly_20260201_020000.sql.gz
      ...
```

> **Note:** S3 retention cleanup is not yet automated. Use [S3 Lifecycle Rules](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html) to expire old objects, or manage manually.

## Restore Procedures

### List available backups

```bash
# Local backups
docker exec thinktank-backup /usr/local/bin/restore.sh --list

# S3 backups (requires S3_BUCKET)
docker exec thinktank-backup /usr/local/bin/restore.sh --list-s3
```

### Restore latest local backup

```bash
docker exec -it thinktank-backup /usr/local/bin/restore.sh --latest
```

### Restore a specific local file

```bash
docker exec -it thinktank-backup /usr/local/bin/restore.sh \
  /backups/daily/thinktank_daily_20260225_020000.sql.gz
```

### Restore from S3

```bash
docker exec -it thinktank-backup /usr/local/bin/restore.sh \
  --from-s3 backups/daily/thinktank_daily_20260225_020000.sql.gz
```

This downloads the file from S3 to `/backups/restored/`, then restores it.

### What happens during a restore

1. **Integrity check** -- Verifies the `.sql.gz` file with `gzip -t`
2. **Connectivity check** -- Confirms PostgreSQL is reachable
3. **Confirmation prompt** -- In interactive mode, asks `Are you sure? Type 'yes' to confirm:`
4. **Safety backup** -- Automatically dumps the current database to `/backups/safety/` before restoring
5. **Restore** -- Runs `zcat | psql --single-transaction --set ON_ERROR_STOP=on`

If the restore fails, the safety backup is available at `/backups/safety/pre_restore_<timestamp>.sql.gz`.

## WAL Archiving (Point-in-Time Recovery)

For continuous archiving beyond periodic pg_dump snapshots, a WAL archiving configuration is provided at `docker/backup/postgresql-backup.conf`.

### Enable WAL archiving

1. Mount the config file into the PostgreSQL container by adding to `docker-compose-prod.yaml`:

   ```yaml
   postgres:
     volumes:
       - pgdata:/var/lib/postgresql/data
       - ./backup/postgresql-backup.conf:/etc/postgresql/backup.conf:ro
     command: >
       postgres -c 'include=/etc/postgresql/backup.conf'
   ```

2. Ensure the WAL archive directory exists:

   ```yaml
   postgres:
     volumes:
       - backupdata:/backups
   ```

3. For S3-based WAL archiving, uncomment the S3 `archive_command` in `postgresql-backup.conf` and comment out the local one.

### Configuration

The WAL config sets:

| Setting | Value | Purpose |
|---------|-------|---------|
| `wal_level` | `replica` | Enable archiving |
| `archive_mode` | `on` | Activate WAL archiving |
| `archive_command` | `cp %p /backups/wal/%f` | Copy WAL segments to backup volume |
| `max_wal_senders` | `3` | Support streaming replication |
| `wal_keep_size` | `256MB` | Retain WAL on disk |

## Manual Operations

### Trigger an immediate backup

```bash
docker exec thinktank-backup /usr/local/bin/entrypoint.sh backup
```

### Check backup container logs

```bash
docker logs thinktank-backup --tail=30
```

### Check latest backups on disk

```bash
docker exec thinktank-backup ls -lht /backups/daily/ | head -5
```

### Verify a backup file manually

```bash
docker exec thinktank-backup gzip -t /backups/daily/thinktank_daily_20260225_020000.sql.gz \
  && echo "OK" || echo "CORRUPTED"
```

## Monitoring

To confirm backups are running, check:

1. **Container is up**: `docker ps | grep backup`
2. **Recent logs show success**: `docker logs thinktank-backup --tail=5`
3. **Fresh files exist**: `docker exec thinktank-backup find /backups -name '*.sql.gz' -mtime -1`
4. **S3 objects exist** (if enabled): `docker exec thinktank-backup /usr/local/bin/restore.sh --list-s3`

Consider adding an alerting rule for missing backups. The backup script exits with a non-zero code on failure, which will appear in `docker logs`.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `PostgreSQL is not reachable` | Postgres not healthy or wrong `PGHOST` | Check `docker ps`, verify `PGHOST` in compose |
| `S3 upload failed` | Bad credentials or bucket policy | Verify `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, bucket exists |
| `gzip check failed` | Disk full during dump | Check disk space: `docker exec thinktank-backup df -h /backups` |
| No backups created | Cron not running | Check logs: `docker logs thinktank-backup`; verify `BACKUP_SCHEDULE` syntax |
| Old backups not pruned | Retention only applies to local files | For S3, configure [S3 Lifecycle Rules](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lifecycle-mgmt.html) |
