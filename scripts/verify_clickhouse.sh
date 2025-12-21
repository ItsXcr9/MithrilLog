#!/bin/bash
# Verify MithrilLog ClickHouse connectivity

SERVER="root@65.109.200.75"
CH_URL="http://127.0.0.1:6123"
CH_USER="AncientReport"
CH_PASS="AncientReport"
API_URL="http://127.0.0.1:9900"

echo "=========================================="
echo "MithrilLog ClickHouse Verification Script"
echo "=========================================="
echo ""

# Test 1: ClickHouse Basic Connectivity
echo "1. Testing ClickHouse connectivity..."
result=$(ssh ${SERVER} "curl -sS '${CH_URL}/?query=SELECT+1'")
if [ "$result" = "1" ]; then
    echo "   ✅ ClickHouse is reachable"
else
    echo "   ❌ ClickHouse connection failed: $result"
    exit 1
fi

# Test 2: Verify mithrillog database exists
echo ""
echo "2. Checking mithrillog database..."
result=$(ssh ${SERVER} "curl -sS '${CH_URL}/?user=${CH_USER}&password=${CH_PASS}&query=SHOW+DATABASES' | grep mithrillog")
if [ -n "$result" ]; then
    echo "   ✅ Database 'mithrillog' exists"
else
    echo "   ❌ Database 'mithrillog' not found"
    echo "   Run: ./deploy.sh --init-schema"
    exit 1
fi

# Test 3: Verify tables exist
echo ""
echo "3. Checking tables in mithrillog database..."
tables=$(ssh ${SERVER} "curl -sS '${CH_URL}/?user=${CH_USER}&password=${CH_PASS}&database=mithrillog&query=SHOW+TABLES'")
if [ -n "$tables" ]; then
    echo "   ✅ Tables found:"
    echo "$tables" | sed 's/^/      - /'
else
    echo "   ❌ No tables found in mithrillog database"
fi

# Test 4: MithrilLog containers status
echo ""
echo "4. Checking MithrilLog container status..."
ssh ${SERVER} "docker ps --filter 'name=mithrillog' --format 'table {{.Names}}\t{{.Status}}'"

# Test 5: MithrilLog API analytics health
echo ""
echo "5. Testing MithrilLog Analytics API health..."
result=$(ssh ${SERVER} "curl -sS ${API_URL}/api/analytics/health" 2>/dev/null)
if [ -n "$result" ]; then
    echo "   API Response: $result"
else
    echo "   ❌ API not responding (may need network access)"
    # Try from inside container
    result=$(ssh ${SERVER} "docker exec mithrillog-xcr9-api-1 curl -sS localhost:9000/api/analytics/health" 2>/dev/null)
    if [ -n "$result" ]; then
        echo "   Container Response: $result"
    fi
fi

echo ""
echo "=========================================="
echo "Verification complete!"
echo "=========================================="
