#!/bin/bash
set -e

# Submit Task Script
# Usage: ./submit-task.sh [queue-url] [task-json-file]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGION="us-west-1"
ENVIRONMENT=${ENVIRONMENT:-dev}

# Get queue URL from CloudFormation if not provided
if [ -z "$1" ]; then
    STACK_NAME="aws-web-crawler-$ENVIRONMENT"
    QUEUE_URL=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query "Stacks[0].Outputs[?OutputKey=='TaskQueueUrl'].OutputValue" \
        --output text 2>/dev/null)
    
    if [ -z "$QUEUE_URL" ] || [ "$QUEUE_URL" = "None" ]; then
        echo "ERROR: Could not find queue URL. Stack may not be deployed."
        echo "Usage: $0 [queue-url] [task-json-file]"
        exit 1
    fi
else
    QUEUE_URL="$1"
fi

echo "Queue URL: $QUEUE_URL"

# Sample task for testing (array format with XPath)
read -r -d '' SAMPLE_TASK << 'EOF' || true
[
  {
    "url": "https://httpbin.org/forms/post",
    "actions": [
      {
        "type": "wait",
        "delay": 1000
      },
      {
        "type": "fill",
        "xpath": "//input[@name='custname']",
        "value": "Test User"
      },
      {
        "type": "fill",
        "xpath": "//input[@name='custtel']",
        "value": "555-1234"
      },
      {
        "type": "fill",
        "xpath": "//input[@name='custemail']",
        "value": "test@example.com"
      },
      {
        "type": "select",
        "xpath": "//select[@name='size']",
        "value": "medium"
      },
      {
        "type": "screenshot",
        "name": "form-filled",
        "full_page": true
      },
      {
        "type": "extract",
        "xpath": "//h1",
        "name": "page_title"
      }
    ],
    "config": {
      "timeout": 30000,
      "wait_until": "domcontentloaded"
    },
    "metadata": {
      "source": "test-script",
      "timestamp": "'"$(date -u +"%Y-%m-%dT%H:%M:%SZ")"'"
    }
  }
]
EOF

# Use provided task file or sample task
if [ -n "$2" ] && [ -f "$2" ]; then
    TASK_JSON=$(cat "$2")
    echo "Using task from file: $2"
else
    TASK_JSON="$SAMPLE_TASK"
    echo "Using sample task (no task file provided)"
fi

echo ""
echo "Submitting task:"
echo "$TASK_JSON" | python3 -m json.tool 2>/dev/null || echo "$TASK_JSON"
echo ""

# Send message to SQS
RESULT=$(aws sqs send-message \
    --queue-url "$QUEUE_URL" \
    --message-body "$TASK_JSON" \
    --region "$REGION")

MESSAGE_ID=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['MessageId'])")

echo "============================================"
echo "Task submitted successfully!"
echo "Message ID: $MESSAGE_ID"
echo "============================================"
echo ""
echo "To view Lambda logs:"
echo "  aws logs tail /aws/lambda/CrawlerFunction-$ENVIRONMENT --follow --region $REGION"
echo ""
echo "To check DLQ for failed tasks:"
echo "  aws sqs receive-message --queue-url \"\$(aws cloudformation describe-stacks --stack-name aws-web-crawler-$ENVIRONMENT --region $REGION --query \"Stacks[0].Outputs[?OutputKey=='DLQUrl'].OutputValue\" --output text)\" --region $REGION"
