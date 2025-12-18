#!/bin/bash
set -e

# Local Testing Script
# Tests the crawler locally using SAM CLI

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "============================================"
echo "AWS Web Crawler - Local Testing (Python)"
echo "============================================"

# Check prerequisites
if ! command -v sam &> /dev/null; then
    echo "ERROR: AWS SAM CLI is not installed"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker is not installed (required for local testing)"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    exit 1
fi

# Create test event
TEST_EVENT_FILE="$SCRIPT_DIR/test-event.json"

cat > "$TEST_EVENT_FILE" << 'EOF'
{
  "Records": [
    {
      "messageId": "test-message-001",
      "receiptHandle": "test-receipt-handle",
      "body": "{\"url\":\"https://example.com\",\"actions\":[{\"type\":\"wait\",\"delay\":1000},{\"type\":\"screenshot\",\"name\":\"test-screenshot\",\"full_page\":true},{\"type\":\"extract\",\"selector\":\"h1\",\"name\":\"page_title\"}],\"config\":{\"timeout\":30000}}",
      "attributes": {
        "ApproximateReceiveCount": "1",
        "SentTimestamp": "1234567890123",
        "SenderId": "test-sender",
        "ApproximateFirstReceiveTimestamp": "1234567890123"
      },
      "messageAttributes": {},
      "md5OfBody": "test-md5",
      "eventSource": "aws:sqs",
      "eventSourceARN": "arn:aws:sqs:us-west-1:123456789012:test-queue",
      "awsRegion": "us-west-1"
    }
  ]
}
EOF

echo ""
echo "Test event created at: $TEST_EVENT_FILE"
echo ""

# Create environment variables file
ENV_VARS_FILE="$SCRIPT_DIR/env-vars.json"

cat > "$ENV_VARS_FILE" << 'EOF'
{
  "CrawlerFunction": {
    "SECRETS_ARN": "arn:aws:secretsmanager:us-west-1:123456789012:secret:test-secret",
    "RESULTS_BUCKET": "test-results-bucket",
    "LOG_LEVEL": "DEBUG",
    "AWS_REGION": "us-west-1"
  }
}
EOF

# Build SAM application
echo "Building SAM application..."
cd "$PROJECT_DIR/infrastructure"
sam build

# Invoke function locally
echo ""
echo "Invoking function locally..."
echo "Note: Browser automation requires the Docker container to have Playwright installed"
echo ""

sam local invoke CrawlerFunction \
    --event "$TEST_EVENT_FILE" \
    --env-vars "$ENV_VARS_FILE" \
    --docker-network host \
    2>&1 | tee "$SCRIPT_DIR/local-test.log"

echo ""
echo "============================================"
echo "Test complete! Check local-test.log for details"
echo "============================================"
