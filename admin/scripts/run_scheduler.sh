#!/bin/bash

# Function to calculate seconds until next hour
get_seconds_until_next_hour() {
    local now=$(date +%s)
    local next_hour=$(date -d "@$((($(date +%s) / 3600 + 1) * 3600))" +%s)
    echo $((next_hour - now))
}

# Run immediately on start
echo "[$(date)] Starting initial usage scan..."
cd /app && PYTHONPATH=/app python scripts/scan_and_backfill.py --database sqlite:////app/data/admin.db --base-dir /host_home
echo "[$(date)] Initial scan complete."

# Infinite loop to run scanner at the top of every hour
while true; do
    # Calculate seconds until next hour
    sleep_seconds=$(get_seconds_until_next_hour)
    echo "[$(date)] Next scan in $sleep_seconds seconds (at top of hour)..."
    sleep $sleep_seconds
    
    echo "[$(date)] Starting hourly usage scan..."
    cd /app && PYTHONPATH=/app python scripts/scan_and_backfill.py --database sqlite:////app/data/admin.db --base-dir /host_home
    echo "[$(date)] Scan complete."
done
