# SQLite Backup Setup

Daily backups of the SQLite database to a Hetzner Storage Box. The backup script runs on the Hetzner VM host via crontab.

## Prerequisites

- Hetzner Storage Box with SSH access already configured (an `~/.ssh/config` Host alias that handles hostname, user, port, and key)
- `sqlite3`, `gzip`, `rsync` installed on the VM (standard on most distros)

## 1. Create remote directories

Using your SSH config alias (e.g., `neuroticsasquatch-backups`):

    ssh neuroticsasquatch-backups "mkdir -p /backups/boone-gifts/daily /backups/boone-gifts/weekly"

## 2. Configure the backup

Create `/etc/boone-gifts-backup.env` on the VM:

    SSH_HOST=neuroticsasquatch-backups
    REMOTE_PATH=/backups/boone-gifts

The script also accepts these optional overrides:

| Variable | Default | Description |
|---|---|---|
| `VOLUME_NAME` | `boone-gifts-backend_sqlite-data` | Docker volume name |
| `DB_FILENAME` | `boone_gifts.db` | SQLite filename within the volume |

## 3. Install the crontab entry

    sudo crontab -e

Add:

    0 3 * * * . /etc/boone-gifts-backup.env && /path/to/scripts/backup-sqlite.sh >> /var/log/boone-gifts-backup.log 2>&1

This runs the backup daily at 03:00 UTC.

## 4. Verify

Run the script manually to confirm everything works:

    . /etc/boone-gifts-backup.env && /path/to/scripts/backup-sqlite.sh

Then check the Storage Box:

    ssh neuroticsasquatch-backups ls -la /backups/boone-gifts/daily/

You should see today's backup file.

## Retention

| Type | Kept | Max age |
|---|---|---|
| Daily | 14 | 14 days |
| Weekly | 8 | 56 days |

Weekly backups are created on Sundays by copying that day's daily backup.

## Restore procedure

### 1. Download the backup

From the VM:

    scp neuroticsasquatch-backups:/backups/boone-gifts/daily/boone_gifts_YYYY-MM-DD.db.gz /tmp/

### 2. Decompress

    gunzip /tmp/boone_gifts_YYYY-MM-DD.db.gz

### 3. Stop the backend container

    docker compose -f docker-compose.prod.yml stop app

### 4. Replace the database

Find the volume mount point:

    docker volume inspect --format '{{ .Mountpoint }}' boone-gifts-backend_sqlite-data

Copy the backup into place (back up the current file first):

    VOLUME_PATH=$(docker volume inspect --format '{{ .Mountpoint }}' boone-gifts-backend_sqlite-data)
    cp "$VOLUME_PATH/boone_gifts.db" "$VOLUME_PATH/boone_gifts.db.pre-restore"
    cp /tmp/boone_gifts_YYYY-MM-DD.db "$VOLUME_PATH/boone_gifts.db"

### 5. Start the backend container

    docker compose -f docker-compose.prod.yml up -d app

The `start.sh` entrypoint will run `alembic upgrade head` on boot, applying any migrations that postdate the backup.

### 6. Verify

    curl https://your-api-domain/health

Should return `{"status": "healthy"}`.
