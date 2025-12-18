"""
Task Submitter Lambda Handler
Provides an API Gateway endpoint for submitting crawl tasks
"""

import json
import os
import time
import uuid
from typing import Any

import boto3

from ..lib.logger import get_logger

logger = get_logger("task_submitter")

# SQS client
sqs_client = boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "us-west-1"))
queue_url = os.environ.get("QUEUE_URL", "")


def handler(event: dict, context: Any) -> dict:
    """Lambda handler for API Gateway
    
    Accepts an array of tasks (minimum 1, maximum 10):
    POST /tasks
    Body: [
        {"url": "https://example.com", "actions": [...]},
        {"url": "https://example2.com", "actions": [...]}
    ]
    """
    request_logger = logger.with_context(
        request_id=event.get("requestContext", {}).get("requestId", "unknown"),
        path=event.get("path", ""),
        method=event.get("httpMethod", ""),
    )

    request_logger.info("Processing API request")

    # CORS headers
    cors_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "POST,OPTIONS",
        "Content-Type": "application/json",
    }

    # Handle CORS preflight
    if event.get("httpMethod") == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": cors_headers,
            "body": "",
        }

    # Only allow POST
    if event.get("httpMethod") != "POST":
        return {
            "statusCode": 405,
            "headers": cors_headers,
            "body": json.dumps({"error": "Method not allowed"}),
        }

    try:
        # Parse request body
        body_str = event.get("body")
        if not body_str:
            return {
                "statusCode": 400,
                "headers": cors_headers,
                "body": json.dumps({"error": "Request body is required"}),
            }

        body = json.loads(body_str)

        # Body must be an array of tasks
        if not isinstance(body, list):
            return {
                "statusCode": 400,
                "headers": cors_headers,
                "body": json.dumps({
                    "error": "Request body must be an array of tasks",
                    "example": [{"url": "https://example.com", "actions": []}]
                }),
            }

        return submit_tasks(body, cors_headers, request_logger)

    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "headers": cors_headers,
            "body": json.dumps({"error": "Invalid JSON in request body"}),
        }
    except Exception as e:
        request_logger.error("Request failed", error=str(e))
        return {
            "statusCode": 500,
            "headers": cors_headers,
            "body": json.dumps({"error": "Internal server error"}),
        }


def submit_tasks(
    tasks: list,
    headers: dict,
    request_logger: Any,
) -> dict:
    """Submit an array of tasks to SQS (1-10 tasks)"""
    if len(tasks) == 0:
        return {
            "statusCode": 400,
            "headers": headers,
            "body": json.dumps({"error": "Tasks array cannot be empty (minimum 1 task)"}),
        }

    if len(tasks) > 10:
        return {
            "statusCode": 400,
            "headers": headers,
            "body": json.dumps({"error": "Maximum 10 tasks per request"}),
        }

    # Validate all tasks
    validated_tasks = []
    errors = []

    for i, task in enumerate(tasks):
        validation_error = validate_task(task)
        if validation_error:
            errors.append({"index": i, "error": validation_error})
        else:
            if not task.get("task_id"):
                task["task_id"] = generate_task_id()
            validated_tasks.append(task)

    if errors:
        return {
            "statusCode": 400,
            "headers": headers,
            "body": json.dumps({"error": "Validation failed", "details": errors}),
        }

    request_logger.info("Submitting tasks", count=len(validated_tasks))

    # For single task, use send_message; for multiple, use batch
    if len(validated_tasks) == 1:
        task = validated_tasks[0]
        response = sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(task),
            MessageAttributes={
                "TaskId": {
                    "DataType": "String",
                    "StringValue": task["task_id"],
                }
            },
        )

        request_logger.info(
            "Task submitted",
            task_id=task["task_id"],
            message_id=response["MessageId"],
        )

        return {
            "statusCode": 202,
            "headers": headers,
            "body": json.dumps({
                "queued": [
                    {
                        "task_id": task["task_id"],
                        "message_id": response["MessageId"],
                    }
                ],
                "failed": [],
            }),
        }

    # Multiple tasks - use batch send
    response = sqs_client.send_message_batch(
        QueueUrl=queue_url,
        Entries=[
            {
                "Id": str(i),
                "MessageBody": json.dumps(task),
                "MessageAttributes": {
                    "TaskId": {
                        "DataType": "String",
                        "StringValue": task["task_id"],
                    }
                },
            }
            for i, task in enumerate(validated_tasks)
        ],
    )

    request_logger.info(
        "Batch submitted",
        successful=len(response.get("Successful", [])),
        failed=len(response.get("Failed", [])),
    )

    return {
        "statusCode": 202,
        "headers": headers,
        "body": json.dumps({
            "queued": [
                {
                    "task_id": validated_tasks[int(s["Id"])]["task_id"],
                    "message_id": s["MessageId"],
                }
                for s in response.get("Successful", [])
            ],
            "failed": [
                {
                    "task_id": validated_tasks[int(f["Id"])]["task_id"],
                    "error": f.get("Message", "Unknown error"),
                }
                for f in response.get("Failed", [])
            ],
        }),
    }


def validate_task(task: Any) -> str | None:
    """Validate a crawler task, returns error message or None if valid"""
    if not isinstance(task, dict):
        return "Task must be an object"

    if not task.get("url") or not isinstance(task["url"], str):
        return "Task must have a valid url field"

    # Validate URL format
    try:
        from urllib.parse import urlparse
        result = urlparse(task["url"])
        if not all([result.scheme, result.netloc]):
            return "Invalid URL format"
    except Exception:
        return "Invalid URL format"

    if not isinstance(task.get("actions"), list):
        return "Task must have an actions array"

    # Validate each action has a type
    for i, action in enumerate(task["actions"]):
        if not isinstance(action, dict):
            return f"Action at index {i} must be an object"
        if not action.get("type"):
            return f"Action at index {i} must have a type"

    return None


def generate_task_id() -> str:
    """Generate a unique task ID"""
    timestamp = hex(int(time.time() * 1000))[2:]
    random_part = uuid.uuid4().hex[:6]
    return f"task-{timestamp}-{random_part}"
