#!/bin/bash

# Test script for MithrilLog Go Admin API
# Run this after deployment to verify all endpoints work

SERVER="http://65.109.200.75:9999"

echo "🧪 Testing MithrilLog Go Admin API"
echo "==================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Test counter
PASSED=0
FAILED=0

# Helper function to test endpoint
test_endpoint() {
    local method=$1
    local endpoint=$2
    local description=$3
    local expected_status=${4:-200}
    local data=$5
    
    echo -n "Testing: $description... "
    
    if [ "$method" == "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" "$SERVER$endpoint")
    elif [ "$method" == "POST" ]; then
        response=$(curl -s -w "\n%{http_code}" -X POST -H "Content-Type: application/json" -d "$data" "$SERVER$endpoint")
    elif [ "$method" == "PUT" ]; then
        response=$(curl -s -w "\n%{http_code}" -X PUT -H "Content-Type: application/json" -d "$data" "$SERVER$endpoint")
    fi
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)
    
    if [ "$http_code" == "$expected_status" ]; then
        echo -e "${GREEN}✓ PASSED${NC} (HTTP $http_code)"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAILED${NC} (Expected $expected_status, got $http_code)"
        echo "Response: $body"
        ((FAILED++))
    fi
}

echo "=== Basic Endpoints ==="
test_endpoint "GET" "/health" "Health check"
echo ""

echo "=== Project Endpoints ==="
test_endpoint "GET" "/api/admin/projects" "List all projects"
test_endpoint "GET" "/api/admin/projects/xcr9" "Get project details" "200"
echo ""

echo "=== Config Endpoints ==="
test_endpoint "GET" "/api/admin/config/templates" "Get config templates"
echo ""

echo "=== Limit Endpoints ==="
test_endpoint "GET" "/api/admin/limits/status" "Get limits status"
echo ""

echo "=== Docker Endpoints ==="
test_endpoint "GET" "/api/admin/docker/xcr9/status" "Get Docker status" "200"
echo ""

echo "=== Suspend Page ==="
test_endpoint "GET" "/suspended?project=xcr9" "Suspend page" "200"
echo ""

echo "=================================="
echo -e "Results: ${GREEN}$PASSED passed${NC}, ${RED}$FAILED failed${NC}"
echo "=================================="

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}❌ Some tests failed${NC}"
    exit 1
fi
