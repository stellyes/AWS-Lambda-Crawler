"""
Main Crawler Lambda Handler
Processes tasks from SQS and performs browser automation using Playwright
"""

import asyncio
import time
import traceback
import uuid
from datetime import datetime
from typing import Any, Optional

from playwright.async_api import Page

from ..lib.browser import BrowserManager, create_browser_manager
from ..lib.logger import ContextLogger, get_logger
from ..lib.secrets import SecretsManager, create_secrets_manager
from ..lib.storage import StorageManager, create_storage_manager
from ..models.types import (
    ClickAction,
    CrawlerAction,
    CrawlerResult,
    CrawlerTask,
    ErrorInfo,
    EvaluateAction,
    ExtractAction,
    FillAction,
    HoverAction,
    LoginAction,
    NavigateAction,
    ScreenshotAction,
    ScreenshotResult,
    ScrollAction,
    SelectAction,
    SQSBatchResponse,
    TaskConfig,
    WaitAction,
)


def xpath_selector(xpath: str) -> str:
    """Convert XPath to Playwright selector format"""
    return f"xpath={xpath}"

# Initialize base logger at module level
base_logger = get_logger("crawler")


def handler(event: dict, context: Any) -> dict:
    """
    Lambda handler for SQS-triggered crawler tasks.
    Supports partial batch responses to only retry failed messages.
    """
    records = event.get("Records", [])
    logger = base_logger.with_context(
        handler="crawler",
        record_count=len(records),
    )

    logger.info("Processing SQS batch", record_count=len(records))

    # Run async handler
    response = asyncio.get_event_loop().run_until_complete(
        process_batch(records, logger)
    )

    return response.model_dump(by_alias=True)


async def process_batch(
    records: list[dict], logger: ContextLogger
) -> SQSBatchResponse:
    """Process a batch of SQS records"""
    batch_item_failures = []

    for record in records:
        message_id = record.get("messageId", "unknown")
        message_logger = logger.with_context(message_id=message_id)

        try:
            body = record.get("body", "{}")
            task = parse_task(body, message_logger)
            await process_task(task, message_logger)

        except Exception as e:
            message_logger.error(
                "Failed to process message",
                error=str(e),
                stack=traceback.format_exc(),
            )
            batch_item_failures.append({"itemIdentifier": message_id})

    logger.info(
        "Batch processing complete",
        total=len(records),
        failed=len(batch_item_failures),
        succeeded=len(records) - len(batch_item_failures),
    )

    return SQSBatchResponse(batchItemFailures=batch_item_failures)


def parse_task(body: str, logger: ContextLogger) -> CrawlerTask:
    """Parse and validate a crawler task from SQS message body"""
    import json

    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in message body: {e}")

    # Generate task ID if not provided
    if "task_id" not in data or not data["task_id"]:
        data["task_id"] = generate_task_id()

    task = CrawlerTask(**data)

    logger.info(
        "Task parsed",
        task_id=task.task_id,
        url=str(task.url),
        action_count=len(task.actions),
    )

    return task


async def process_task(task: CrawlerTask, logger: ContextLogger) -> None:
    """Process a single crawler task"""
    start_time = time.time()
    task_logger = logger.with_context(task_id=task.task_id, url=str(task.url))

    task_logger.info("Starting task processing")

    # Initialize services
    browser_manager = create_browser_manager(task_logger)
    secrets_manager = create_secrets_manager(task_logger)
    storage_manager = create_storage_manager(task_logger)

    result = CrawlerResult(
        task_id=task.task_id,
        url=str(task.url),
        success=False,
        duration=0,
        timestamp=datetime.utcnow(),
        data={},
        screenshots=[],
        errors=[],
        metadata=task.metadata,
    )

    page: Optional[Page] = None

    try:
        # Launch browser and navigate to URL
        async with browser_manager:
            await browser_manager.launch(task.config)
            page = await browser_manager.new_page(task.config)

            task_logger.info("Navigating to URL")
            await page.goto(
                str(task.url),
                wait_until=task.config.wait_until.value,
                timeout=task.config.timeout,
            )

            # Execute each action
            for i, action in enumerate(task.actions):
                task_logger.info(
                    "Executing action",
                    action_index=i,
                    action_type=action.type,
                )

                try:
                    action_result = await execute_action(
                        page=page,
                        action=action,
                        secrets_manager=secrets_manager,
                        storage_manager=storage_manager,
                        task_id=task.task_id,
                        logger=task_logger,
                    )

                    # Merge action results into main result
                    if action_result.get("data"):
                        result.data.update(action_result["data"])
                    if action_result.get("screenshot"):
                        result.screenshots.append(action_result["screenshot"])

                except Exception as e:
                    error_info = ErrorInfo(
                        action=f"{action.type}[{i}]",
                        message=str(e),
                        stack=traceback.format_exc(),
                    )
                    result.errors.append(error_info)
                    task_logger.warning("Action failed", **error_info.model_dump())

                    # Critical actions should stop execution
                    if action.type in ("login", "navigate"):
                        raise

            result.success = len(result.errors) == 0

    except Exception as e:
        result.errors.append(
            ErrorInfo(
                action="task",
                message=str(e),
                stack=traceback.format_exc(),
            )
        )
        task_logger.error("Task failed", error=str(e))

    finally:
        # Calculate duration
        result.duration = int((time.time() - start_time) * 1000)

        # Save result to S3
        try:
            s3_url = await storage_manager.save_result(result)
            task_logger.info(
                "Task complete",
                success=result.success,
                duration=result.duration,
                error_count=len(result.errors),
                s3_url=s3_url,
            )
        except Exception as e:
            task_logger.error("Failed to save result", error=str(e))

    # Re-throw if task failed to trigger SQS retry
    if not result.success and any(e.action == "task" for e in result.errors):
        raise RuntimeError(f"Task failed: {result.errors[0].message}")


async def execute_action(
    page: Page,
    action: CrawlerAction,
    secrets_manager: SecretsManager,
    storage_manager: StorageManager,
    task_id: str,
    logger: ContextLogger,
) -> dict[str, Any]:
    """Execute a single action and return results"""
    result: dict[str, Any] = {}

    if action.type == "login":
        await execute_login(page, action, secrets_manager, logger)

    elif action.type == "click":
        await execute_click(page, action, logger)

    elif action.type == "fill":
        await execute_fill(page, action, logger)

    elif action.type == "wait":
        await execute_wait(page, action, logger)

    elif action.type == "extract":
        result["data"] = await execute_extract(page, action, logger)

    elif action.type == "screenshot":
        result["screenshot"] = await execute_screenshot(
            page, action, storage_manager, task_id, logger
        )

    elif action.type == "navigate":
        await execute_navigate(page, action, logger)

    elif action.type == "select":
        await execute_select(page, action, logger)

    elif action.type == "hover":
        await execute_hover(page, action, logger)

    elif action.type == "scroll":
        await execute_scroll(page, action, logger)

    elif action.type == "evaluate":
        result["data"] = await execute_evaluate(page, action, logger)

    else:
        raise ValueError(f"Unknown action type: {action.type}")

    return result


# ============================================
# Action Implementations
# ============================================


async def execute_login(
    page: Page,
    action: LoginAction,
    secrets_manager: SecretsManager,
    logger: ContextLogger,
) -> None:
    """Execute a login action"""
    logger.info("Executing login action")

    # Get credentials from Secrets Manager
    credentials = secrets_manager.get_credentials(action.secret_key)

    # Fill username
    username_sel = xpath_selector(action.username_xpath)
    await page.wait_for_selector(username_sel, state="visible")
    await page.fill(username_sel, credentials.username)

    # Fill password
    password_sel = xpath_selector(action.password_xpath)
    await page.wait_for_selector(password_sel, state="visible")
    await page.fill(password_sel, credentials.password)

    # Click submit and wait for navigation
    submit_sel = xpath_selector(action.submit_xpath)
    async with page.expect_navigation(wait_until="domcontentloaded"):
        await page.click(submit_sel)

    # Optional wait after submit
    if action.wait_after_submit:
        await page.wait_for_timeout(action.wait_after_submit)

    logger.info("Login completed")


async def execute_click(
    page: Page,
    action: ClickAction,
    logger: ContextLogger,
) -> None:
    """Execute a click action"""
    logger.debug("Clicking element", xpath=action.xpath)

    selector = xpath_selector(action.xpath)
    await page.wait_for_selector(selector, state="visible")

    if action.delay:
        await page.wait_for_timeout(action.delay)

    if action.wait_for_navigation:
        async with page.expect_navigation(wait_until="domcontentloaded"):
            await page.click(selector)
    else:
        await page.click(selector)


async def execute_fill(
    page: Page,
    action: FillAction,
    logger: ContextLogger,
) -> None:
    """Execute a fill action"""
    logger.debug("Filling input", xpath=action.xpath)

    selector = xpath_selector(action.xpath)
    await page.wait_for_selector(selector, state="visible")

    if action.clear_first:
        await page.fill(selector, "")

    await page.fill(selector, action.value)


async def execute_wait(
    page: Page,
    action: WaitAction,
    logger: ContextLogger,
) -> None:
    """Execute a wait action"""
    if action.delay:
        logger.debug("Waiting for delay", delay=action.delay)
        await page.wait_for_timeout(action.delay)
        return

    if action.xpath:
        logger.debug(
            "Waiting for xpath",
            xpath=action.xpath,
            state=action.state.value if action.state else "visible",
        )
        selector = xpath_selector(action.xpath)
        await page.wait_for_selector(
            selector,
            state=action.state.value if action.state else "visible",
            timeout=action.timeout,
        )


async def execute_extract(
    page: Page,
    action: ExtractAction,
    logger: ContextLogger,
) -> dict[str, Any]:
    """Execute an extract action"""
    logger.debug(
        "Extracting data",
        xpath=action.xpath,
        attribute=action.attribute,
    )

    selector = xpath_selector(action.xpath)

    if action.multiple:
        elements = page.locator(selector)
        count = await elements.count()
        values = []

        for i in range(count):
            element = elements.nth(i)
            if action.attribute == "inner_text":
                values.append(await element.inner_text())
            elif action.attribute == "inner_html":
                values.append(await element.inner_html())
            else:
                values.append(await element.get_attribute(action.attribute) or "")

        return {action.name: values}

    else:
        element = page.locator(selector).first

        if action.attribute == "inner_text":
            value = await element.inner_text()
        elif action.attribute == "inner_html":
            value = await element.inner_html()
        else:
            value = await element.get_attribute(action.attribute) or ""

        return {action.name: value}


async def execute_screenshot(
    page: Page,
    action: ScreenshotAction,
    storage_manager: StorageManager,
    task_id: str,
    logger: ContextLogger,
) -> ScreenshotResult:
    """Execute a screenshot action"""
    logger.debug(
        "Taking screenshot",
        xpath=action.xpath,
        full_page=action.full_page,
    )

    name = action.name or f"screenshot-{int(time.time() * 1000)}"

    if action.xpath:
        selector = xpath_selector(action.xpath)
        element = page.locator(selector)
        data = await element.screenshot()
    else:
        data = await page.screenshot(full_page=action.full_page)

    return await storage_manager.save_screenshot(task_id, name, data)


async def execute_navigate(
    page: Page,
    action: NavigateAction,
    logger: ContextLogger,
) -> None:
    """Execute a navigate action"""
    logger.debug("Navigating to URL", url=action.url)

    await page.goto(
        action.url,
        wait_until=action.wait_until.value,
    )


async def execute_select(
    page: Page,
    action: SelectAction,
    logger: ContextLogger,
) -> None:
    """Execute a select action"""
    logger.debug("Selecting option", xpath=action.xpath, value=action.value)

    selector = xpath_selector(action.xpath)
    await page.wait_for_selector(selector, state="visible")

    if action.by_label:
        await page.select_option(selector, label=action.value)
    else:
        await page.select_option(selector, action.value)


async def execute_hover(
    page: Page,
    action: HoverAction,
    logger: ContextLogger,
) -> None:
    """Execute a hover action"""
    logger.debug("Hovering over element", xpath=action.xpath)

    selector = xpath_selector(action.xpath)
    await page.wait_for_selector(selector, state="visible")
    await page.hover(selector)


async def execute_scroll(
    page: Page,
    action: ScrollAction,
    logger: ContextLogger,
) -> None:
    """Execute a scroll action"""
    if action.xpath:
        logger.debug("Scrolling to element", xpath=action.xpath)
        selector = xpath_selector(action.xpath)
        element = page.locator(selector)
        await element.scroll_into_view_if_needed()
    else:
        logger.debug("Scrolling page", x=action.x, y=action.y)
        await page.evaluate(
            f"window.scrollTo({action.x or 0}, {action.y or 0})"
        )


async def execute_evaluate(
    page: Page,
    action: EvaluateAction,
    logger: ContextLogger,
) -> dict[str, Any]:
    """Execute an evaluate action"""
    logger.debug("Evaluating script")

    result = await page.evaluate(action.script)

    if action.name:
        return {action.name: result}

    return {"evaluate_result": result}


def generate_task_id() -> str:
    """Generate a unique task ID"""
    timestamp = hex(int(time.time() * 1000))[2:]
    random_part = uuid.uuid4().hex[:6]
    return f"task-{timestamp}-{random_part}"
