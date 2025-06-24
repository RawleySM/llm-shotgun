#!/bin/bash

# Weekly Token Pruning Script
# FD 9.1: Automated weekly prune job for data retention
# This script should be placed in /etc/cron.weekly/ inside the container

set -e

# Configuration
RETENTION_DAYS=${RETENTION_DAYS:-180}
LOG_FILE="/app/logs/prune.log"
API_URL="${API_URL:-http://localhost:8000}"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Function to log with timestamp
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" | tee -a "$LOG_FILE"
}

log "Starting weekly token pruning job"
log "Retention period: $RETENTION_DAYS days"

# Call the prune API endpoint
if command -v curl >/dev/null 2>&1; then
    response=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"retention_days\": $RETENTION_DAYS}" \
        "$API_URL/api/admin/maintenance/prune" \
        --max-time 300 \
        --retry 3) || {
        log "ERROR: Failed to call prune API endpoint"
        exit 1
    }
    
    # Check if prune was successful
    if echo "$response" | grep -q '"status": "completed"'; then
        tokens_deleted=$(echo "$response" | grep -o '"tokens_deleted": [0-9]*' | cut -d':' -f2 | tr -d ' ')
        attempts_deleted=$(echo "$response" | grep -o '"attempts_deleted": [0-9]*' | cut -d':' -f2 | tr -d ' ')
        requests_deleted=$(echo "$response" | grep -o '"requests_deleted": [0-9]*' | cut -d':' -f2 | tr -d ' ')
        
        log "Prune completed successfully:"
        log "  - Tokens deleted: ${tokens_deleted:-0}"
        log "  - Attempts deleted: ${attempts_deleted:-0}" 
        log "  - Requests deleted: ${requests_deleted:-0}"
    else
        log "ERROR: Prune operation failed"
        log "Response: $response"
        exit 1
    fi
else
    log "ERROR: curl not available - cannot call prune API"
    exit 1
fi

log "Weekly token pruning job completed successfully"

# Also trigger WAL file rotation if needed
log "Checking WAL file rotation"
if curl -s -X POST "$API_URL/api/admin/maintenance/wal-rotate" --max-time 30 >/dev/null 2>&1; then
    log "WAL file rotation check completed"
else
    log "WARNING: WAL file rotation check failed or endpoint not available"
fi

exit 0 