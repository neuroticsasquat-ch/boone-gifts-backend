# SQLite Backup Setup

Daily backups of the SQLite database to a Hetzner Storage Box. The backup script runs on the Hetzner VM host via root's crontab.

## Prerequisites

- Hetzner Storage Box with SSH access configured via `~/.ssh/config` Host alias
- `sqlite3`, `gzip`, `rsync` installed on the VM
- Root access on the VM (needed to read Docker volume paths)

## 1. Set up root's SSH access to the Storage Box

The script runs as root (required to access Docker volume mount points), so root needs SSH access to the Storage Box:

    sudo mkdir -p /root/.ssh
    sudo cp ~/.ssh/config /root/.ssh/config
    sudo cp ~/.ssh/<your-storage-box-key> /root/.ssh/<your-storage-box-key>
    sudo chmod 600 /root/.ssh/<your-storage-box-key>

Test the connection as root:

    sudo ssh <your-ssh-alias> ls

## 2. Create remote directories

    sudo ssh <your-ssh-alias> "mkdir -p backups/boone-gifts/daily backups/boone-gifts/weekly"

Note: Hetzner Storage Boxes don't allow writing to `/` — paths are relative to your home directory.

## 3. Install the script

    sudo cp scripts/backup-sqlite.sh /usr/local/bin/backup-sqlite.sh
    sudo chmod +x /usr/local/bin/backup-sqlite.sh

## 4. Configure the environment

Create `/etc/boone-gifts-backup.env`:

    export SSH_HOST=<your-ssh-alias>
    export REMOTE_PATH=backups/boone-gifts
    export VOLUME_NAME=<your-docker-volume-name>

Find your volume name with:

    docker volume ls | grep sqlite

The script also accepts an optional override:

| Variable | Default | Description |
|---|---|---|
| `DB_FILENAME` | `boone_gifts.db` | SQLite filename within the volume |

## 5. Install the crontab entry

    sudo crontab -e

Add:

    0 3 * * * /usr/bin/bash -c '. /etc/boone-gifts-backup.env && /usr/local/bin/backup-sqlite.sh' >> /var/log/boone-gifts-backup.log 2>&1

This runs the backup daily at 03:00 UTC under root.

## 6. Verify

Run the script manually:

    sudo bash -c '. /etc/boone-gifts-backup.env && /usr/local/bin/backup-sqlite.sh'

Then check the Storage Box:

    sudo ssh <your-ssh-alias> ls -la backups/boone-gifts/daily/

You should see today's backup file.

## Retention

| Type | Kept | Max age |
|---|---|---|
| Daily | 14 | 14 days |
| Weekly | 8 | 56 days |

Weekly backups are created on Sundays by copying that day's daily backup.

## Restore procedure

### 1. Download the backup

    sudo scp <your-ssh-alias>:backups/boone-gifts/daily/boone_gifts_YYYY-MM-DD.db.gz /tmp/

### 2. Decompress

    gunzip /tmp/boone_gifts_YYYY-MM-DD.db.gz

### 3. Stop the backend container

Stop the app via Coolify, or:

    docker stop <container-name>

### 4. Replace the database

Find the volume mount point:

    docker volume inspect --format '{{ .Mountpoint }}' <your-docker-volume-name>

Copy the backup into place (back up the current file first):

    VOLUME_PATH=$(docker volume inspect --format '{{ .Mountpoint }}' <your-docker-volume-name>)
    sudo cp "$VOLUME_PATH/boone_gifts.db" "$VOLUME_PATH/boone_gifts.db.pre-restore"
    sudo cp /tmp/boone_gifts_YYYY-MM-DD.db "$VOLUME_PATH/boone_gifts.db"

### 5. Start the backend container

Restart via Coolify, or:

    docker start <container-name>

The `start.sh` entrypoint will run `alembic upgrade head` on boot, applying any migrations that postdate the backup.

### 6. Verify

    curl https://<your-api-domain>/health

Should return `{"status": "healthy"}`.
