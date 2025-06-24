#!/bin/bash

# Daily Database Backup Script
# FD 10.1: Automated daily backup job using pg_dump
# This script should be placed in /etc/cron.daily/ inside the container

set -e

# Configuration
LOG_FILE="/app/logs/backup.log"
API_URL="${API_URL:-http://localhost:8000}"
BACKUP_RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-30}

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Function to log with timestamp
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

log "Starting daily database backup job"

# Call the backup API endpoint
if command -v curl >/dev/null 2>&1; then
    response=$(curl -s -X POST \
        "$API_URL/api/admin/maintenance/backup" \
        --max-time 600 \
        --retry 2) || {
        log "ERROR: Failed to call backup API endpoint"
        exit 1
    }
    
    # Check if backup was successful
    if echo "$response" | grep -q '"status": "completed"'; then
        backup_file=$(echo "$response" | grep -o '"backup_file": "[^"]*"' | cut -d'"' -f4)
        file_size=$(echo "$response" | grep -o '"file_size": [0-9]*' | cut -d':' -f2 | tr -d ' ')
        duration=$(echo "$response" | grep -o '"duration_seconds": [0-9.]*' | cut -d':' -f2 | tr -d ' ')
        
        log "Backup completed successfully:"
        log "  - Backup file: $backup_file"
        log "  - File size: ${file_size:-0} bytes"
        log "  - Duration: ${duration:-0} seconds"
        
        # Convert bytes to human readable format
        if [ -n "$file_size" ] && [ "$file_size" -gt 0 ]; then
            if [ "$file_size" -gt 1073741824 ]; then
                size_human=$(echo "scale=2; $file_size / 1073741824" | bc -l 2>/dev/null || echo "unknown")
                log "  - Size: ${size_human}GB"
            elif [ "$file_size" -gt 1048576 ]; then
                size_human=$(echo "scale=2; $file_size / 1048576" | bc -l 2>/dev/null || echo "unknown")
                log "  - Size: ${size_human}MB"
            elif [ "$file_size" -gt 1024 ]; then
                size_human=$(echo "scale=2; $file_size / 1024" | bc -l 2>/dev/null || echo "unknown")
                log "  - Size: ${size_human}KB"
            fi
        fi
    else
        log "ERROR: Backup operation failed"
        log "Response: $response"
        exit 1
    fi
else
    log "ERROR: curl not available - cannot call backup API"
    exit 1
fi

log "Daily database backup job completed successfully"

# Optional: Check disk space and warn if getting low
BACKUP_DIR="/app/data/backups"
if [ -d "$BACKUP_DIR" ]; then
    # Check available space (in KB)
    available_space=$(df "$BACKUP_DIR" | awk 'NR==2 {print $4}')
    if [ -n "$available_space" ] && [ "$available_space" -lt 1048576 ]; then  # Less than 1GB
        log "WARNING: Low disk space available: $(echo "scale=2; $available_space / 1024" | bc -l 2>/dev/null || echo "unknown")MB"
    fi
fi

exit 0 