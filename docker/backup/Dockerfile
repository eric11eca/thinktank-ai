# PostgreSQL Backup Container
# Runs scheduled pg_dump backups with optional S3 upload.
#
# Usage:
#   docker build -t thinktank-backup -f docker/backup/Dockerfile docker/backup/
#
# Environment variables: see backup.sh for full list.

FROM postgres:16-alpine

# Install aws-cli for S3 uploads and tini for PID 1 management
RUN apk add --no-cache \
    aws-cli \
    bash \
    tini \
    tzdata

# Copy backup scripts
COPY backup.sh /usr/local/bin/backup.sh
COPY restore.sh /usr/local/bin/restore.sh
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/backup.sh \
             /usr/local/bin/restore.sh \
             /usr/local/bin/entrypoint.sh

# Create backup directory
RUN mkdir -p /backups && chown postgres:postgres /backups

# Default backup schedule: daily at 2:00 AM UTC
ENV BACKUP_SCHEDULE="0 2 * * *"
ENV BACKUP_DIR="/backups"
ENV PGHOST="postgres"
ENV PGPORT="5432"
ENV PGUSER="thinktank"
ENV PGDATABASE="thinktank"

VOLUME ["/backups"]

USER postgres

ENTRYPOINT ["tini", "--"]
CMD ["/usr/local/bin/entrypoint.sh"]
