# AWS Serverless Web Crawler (Python)

A cost-effective, scalable web crawler built on AWS serverless architecture with browser automation capabilities.

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   API Gateway   │────▶│   SQS Queue     │────▶│  Lambda Worker  │
│   (Optional)    │     │  (Task Queue)   │     │  (Playwright)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                │                        │
                                │                        ▼
                        ┌───────▼───────┐     ┌─────────────────┐
                        │  Dead Letter  │     │ Secrets Manager │
                        │    Queue      │     │ (Credentials)   │
                        └───────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                              ┌─────────────────┐
                                              │   S3 Bucket     │
                                              │ (Results/Logs)  │
                                              └─────────────────┘
```

## Technology Choices

### Language: Python 3.12
**Why Python is excellent for this use case:**

1. **Fastest Cold Starts**: Python has the fastest cold start times on Lambda (~200-300ms)
2. **Playwright Support**: Official Python bindings with excellent async support
3. **Lambda Container**: We use a Docker container to include Playwright + Chromium
4. **Memory Efficiency**: Works well with 2048MB Lambda memory allocation
5. **Cost Comparison** (based on 10,000 invocations/month @ 2s average):
   - Python: ~$3.33/month
   - Node.js: ~$3.33/month (similar performance)
   - Java: ~$6.66/month (higher memory requirements)

### AWS Services Used

| Service | Purpose | Cost Model |
|---------|---------|------------|
| **Lambda** | Execute browser automation | Pay per invocation + duration |
| **SQS** | Task queue management | $0.40 per million requests |
| **Secrets Manager** | Store website credentials | $0.40/secret/month |
| **S3** | Store crawl results | $0.023/GB/month |
| **CloudWatch** | Logging and monitoring | Pay per log data |
| **ECR** | Store Docker image | $0.10/GB/month |

### Why This Architecture Minimizes Cost

1. **Zero Idle Cost**: Lambda only runs when processing tasks
2. **Automatic Scaling**: Handles 1 to 1000 concurrent tasks seamlessly
3. **SQS Batching**: Process multiple URLs per Lambda invocation
4. **Dead Letter Queue**: Failed tasks don't clog your pipeline
5. **Reserved Concurrency**: Prevent runaway costs from scaling

## Project Structure

```
aws-web-crawler/
├── src/
│   ├── handlers/
│   │   ├── crawler.py          # Main crawler Lambda handler
│   │   └── task_submitter.py   # Optional: API to submit tasks
│   ├── lib/
│   │   ├── browser.py          # Playwright browser setup
│   │   ├── secrets.py          # Secrets Manager client
│   │   ├── storage.py          # S3 storage utilities
│   │   └── logger.py           # Structured logging
│   └── models/
│       └── types.py            # Pydantic models
├── infrastructure/
│   ├── template.yaml           # SAM/CloudFormation template
│   └── samconfig.toml          # SAM deployment config
├── scripts/
│   ├── deploy.sh               # Deployment script
│   ├── test-local.sh           # Local testing script
│   └── submit-task.sh          # Submit crawl task
├── tests/
│   └── test_crawler.py         # Unit tests
├── Dockerfile                  # Lambda container with Playwright
├── requirements.txt
└── README.md
```

## Quick Start

### Prerequisites

- Python 3.12+
- AWS CLI configured with appropriate credentials
- AWS SAM CLI installed
- Docker (required for building the container image)

### Installation

```bash
# Clone and install dependencies
cd aws-web-crawler
pip install -r requirements.txt

# Deploy to AWS (us-west-1)
./scripts/deploy.sh
```

### Store Your Credentials

```bash
# Create a secret for your website credentials
aws secretsmanager create-secret \
    --name "crawler/website-credentials" \
    --secret-string '{"username":"your-username","password":"your-password"}' \
    --region us-west-1
```

### Submit a Crawl Task

```bash
# Send a message to the SQS queue
aws sqs send-message \
    --queue-url "https://sqs.us-west-1.amazonaws.com/YOUR_ACCOUNT_ID/CrawlerTaskQueue" \
    --message-body '{"url":"https://example.com/login","actions":[{"type":"login"}]}' \
    --region us-west-1
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRETS_ARN` | ARN of Secrets Manager secret | Required |
| `RESULTS_BUCKET` | S3 bucket for results | Required |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `BROWSER_TIMEOUT` | Page load timeout (ms) | `30000` |

### Lambda Configuration

- **Memory**: 2048 MB (recommended for browser automation)
- **Timeout**: 60 seconds (adjustable up to 900 seconds max)
- **Reserved Concurrency**: 10 (prevents runaway scaling)
- **Architecture**: x86_64 (required for Playwright)

## Cost Estimation

### Low Usage (1,000 tasks/month)
| Service | Usage | Cost |
|---------|-------|------|
| Lambda | 1,000 invocations × 2s × 2048MB | ~$0.67 |
| SQS | 1,000 requests | ~$0.00 |
| Secrets Manager | 1 secret | $0.40 |
| S3 | 100MB storage | ~$0.01 |
| ECR | 500MB image | ~$0.05 |
| **Total** | | **~$1.13/month** |

### Medium Usage (10,000 tasks/month)
| Service | Usage | Cost |
|---------|-------|------|
| Lambda | 10,000 invocations × 2s × 2048MB | ~$6.67 |
| SQS | 10,000 requests | ~$0.01 |
| Secrets Manager | 1 secret | $0.40 |
| S3 | 1GB storage | ~$0.02 |
| ECR | 500MB image | ~$0.05 |
| **Total** | | **~$7.15/month** |

## Supported Actions

The crawler uses **XPath selectors** for all element references. Here are the supported actions:

```python
# Login to a website
{"type": "login", "username_xpath": "//input[@id='email']", "password_xpath": "//input[@id='password']", "submit_xpath": "//button[@type='submit']"}

# Click an element
{"type": "click", "xpath": "//button[@id='submit']"}

# Fill an input
{"type": "fill", "xpath": "//input[@name='search']", "value": "text to enter"}

# Wait for an element
{"type": "wait", "xpath": "//div[@class='loading']", "state": "hidden"}

# Extract data
{"type": "extract", "xpath": "//span[@class='price']", "attribute": "inner_text", "name": "price"}

# Screenshot
{"type": "screenshot", "full_page": true}
```

### XPath Examples

| Element | XPath |
|---------|-------|
| By ID | `//input[@id='email']` |
| By class | `//div[@class='container']` |
| By name | `//input[@name='username']` |
| By text | `//button[text()='Submit']` |
| Contains class | `//div[contains(@class, 'active')]` |
| Contains text | `//span[contains(text(), 'Price')]` |
| Nth child | `(//div[@class='item'])[1]` |
| Parent | `//span[@class='child']/..` |

## Submitting Tasks

**The API accepts an array of tasks (1-10 tasks per request):**

```bash
# Submit a single task (as array of 1)
curl -X POST https://your-api/tasks \
  -H "Content-Type: application/json" \
  -d '[{"url": "https://example.com", "actions": [{"type": "screenshot", "full_page": true}]}]'

# Submit multiple tasks
curl -X POST https://your-api/tasks \
  -H "Content-Type: application/json" \
  -d '[
    {"url": "https://site1.com", "actions": [...]},
    {"url": "https://site2.com", "actions": [...]}
  ]'
```

### Response Format

```json
{
  "queued": [
    {"task_id": "task-abc123", "message_id": "msg-xyz789"},
    {"task_id": "task-def456", "message_id": "msg-uvw012"}
  ],
  "failed": []
}
```

## Troubleshooting

### Common Issues

1. **Lambda Timeout**: Increase timeout or reduce task complexity
2. **Memory Error**: Increase Lambda memory to 2048MB+
3. **Chromium Launch Failure**: Ensure Docker image built correctly
4. **Rate Limiting**: Add delays between actions, reduce concurrency

### Debugging

```bash
# View Lambda logs
aws logs tail /aws/lambda/CrawlerFunction --follow --region us-west-1

# Check DLQ for failed tasks
aws sqs receive-message \
    --queue-url "https://sqs.us-west-1.amazonaws.com/YOUR_ACCOUNT_ID/CrawlerDLQ" \
    --region us-west-1
```

## Security Best Practices

1. ✅ Credentials stored in Secrets Manager (never in code)
2. ✅ Lambda runs in VPC with private subnets (optional)
3. ✅ IAM roles follow least-privilege principle
4. ✅ S3 bucket has encryption enabled
5. ✅ CloudWatch logs for audit trail

## License

MIT License - See LICENSE file
