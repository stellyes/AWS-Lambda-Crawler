"""
Unit tests for AWS Web Crawler
"""

import json
import pytest
from pydantic import ValidationError

from src.models.types import (
    ClickAction,
    CrawlerTask,
    ExtractAction,
    FillAction,
    LoginAction,
    ScreenshotAction,
    TaskConfig,
    WaitAction,
    WaitState,
    WaitUntil,
)


class TestCrawlerTaskValidation:
    """Tests for CrawlerTask model validation"""

    def test_valid_task_structure(self):
        """Should accept valid task structure"""
        task = CrawlerTask(
            task_id="test-task-001",
            url="https://example.com",
            actions=[
                WaitAction(type="wait", delay=1000),
                ScreenshotAction(type="screenshot", name="test", full_page=True),
            ],
            config=TaskConfig(timeout=30000, wait_until=WaitUntil.DOMCONTENTLOADED),
            metadata={"source": "test"},
        )

        assert str(task.url) == "https://example.com/"
        assert len(task.actions) == 2
        assert task.config.timeout == 30000

    def test_invalid_url_rejected(self):
        """Should reject invalid URLs"""
        with pytest.raises(ValidationError):
            CrawlerTask(
                url="not-a-valid-url",
                actions=[],
            )

    def test_empty_actions_allowed(self):
        """Should allow empty actions array"""
        task = CrawlerTask(
            url="https://example.com",
            actions=[],
        )
        assert len(task.actions) == 0


class TestActionModels:
    """Tests for action model validation"""

    def test_login_action(self):
        """Should validate login action structure"""
        action = LoginAction(
            type="login",
            username_selector="#email",
            password_selector="#password",
            submit_selector="#submit",
            wait_after_submit=2000,
        )

        assert action.type == "login"
        assert action.username_selector == "#email"
        assert action.wait_after_submit == 2000

    def test_click_action(self):
        """Should validate click action structure"""
        action = ClickAction(
            type="click",
            selector="#button",
            wait_for_navigation=True,
            delay=500,
        )

        assert action.type == "click"
        assert action.selector == "#button"
        assert action.wait_for_navigation is True

    def test_fill_action(self):
        """Should validate fill action structure"""
        action = FillAction(
            type="fill",
            selector="#input",
            value="test value",
            clear_first=True,
        )

        assert action.type == "fill"
        assert action.value == "test value"
        assert action.clear_first is True

    def test_wait_action_with_delay(self):
        """Should validate wait action with delay"""
        action = WaitAction(
            type="wait",
            delay=1000,
        )

        assert action.type == "wait"
        assert action.delay == 1000
        assert action.selector is None

    def test_wait_action_with_selector(self):
        """Should validate wait action with selector"""
        action = WaitAction(
            type="wait",
            selector=".loading",
            state=WaitState.HIDDEN,
            timeout=5000,
        )

        assert action.type == "wait"
        assert action.selector == ".loading"
        assert action.state == WaitState.HIDDEN

    def test_extract_action(self):
        """Should validate extract action structure"""
        action = ExtractAction(
            type="extract",
            selector=".data",
            attribute="inner_text",
            multiple=True,
            name="extracted_data",
        )

        assert action.type == "extract"
        assert action.multiple is True
        assert action.name == "extracted_data"

    def test_screenshot_action(self):
        """Should validate screenshot action structure"""
        action = ScreenshotAction(
            type="screenshot",
            name="test-screenshot",
            full_page=True,
        )

        assert action.type == "screenshot"
        assert action.full_page is True


class TestTaskParsing:
    """Tests for task parsing from JSON"""

    def test_parse_valid_json(self):
        """Should parse valid JSON task"""
        json_str = json.dumps({
            "url": "https://example.com",
            "actions": [{"type": "wait", "delay": 1000}],
        })

        data = json.loads(json_str)
        task = CrawlerTask(**data)

        assert str(task.url) == "https://example.com/"
        assert len(task.actions) == 1

    def test_parse_with_all_fields(self):
        """Should parse task with all optional fields"""
        json_str = json.dumps({
            "task_id": "custom-id",
            "url": "https://example.com",
            "actions": [
                {"type": "wait", "delay": 1000},
                {"type": "screenshot", "name": "test"},
            ],
            "config": {
                "timeout": 60000,
                "wait_until": "networkidle",
                "viewport": {"width": 1440, "height": 900},
            },
            "metadata": {"key": "value"},
        })

        data = json.loads(json_str)
        task = CrawlerTask(**data)

        assert task.task_id == "custom-id"
        assert task.config.timeout == 60000
        assert task.config.viewport.width == 1440
        assert task.metadata["key"] == "value"


class TestTaskConfig:
    """Tests for TaskConfig model"""

    def test_default_config(self):
        """Should have sensible defaults"""
        config = TaskConfig()

        assert config.timeout == 30000
        assert config.wait_until == WaitUntil.DOMCONTENTLOADED
        assert config.viewport.width == 1920
        assert config.viewport.height == 1080

    def test_custom_config(self):
        """Should accept custom configuration"""
        config = TaskConfig(
            timeout=60000,
            wait_until=WaitUntil.NETWORKIDLE,
            viewport={"width": 1440, "height": 900},
            user_agent="Custom User Agent",
        )

        assert config.timeout == 60000
        assert config.wait_until == WaitUntil.NETWORKIDLE
        assert config.user_agent == "Custom User Agent"


class TestURLValidation:
    """Tests for URL validation"""

    def test_valid_https_urls(self):
        """Should accept valid HTTPS URLs"""
        valid_urls = [
            "https://example.com",
            "https://example.com/path",
            "https://example.com/path?query=1",
            "https://sub.example.com",
        ]

        for url in valid_urls:
            task = CrawlerTask(url=url, actions=[])
            assert task.url is not None

    def test_valid_http_urls(self):
        """Should accept valid HTTP URLs"""
        task = CrawlerTask(url="http://example.com", actions=[])
        assert task.url is not None

    def test_invalid_urls(self):
        """Should reject invalid URLs"""
        invalid_urls = [
            "not-a-url",
            "example.com",  # Missing scheme
            "",
        ]

        for url in invalid_urls:
            with pytest.raises(ValidationError):
                CrawlerTask(url=url, actions=[])


class TestActionTypeIdentification:
    """Tests for identifying action types"""

    def test_all_action_types(self):
        """Should correctly identify all action types"""
        actions = [
            LoginAction(
                type="login",
                username_selector="#u",
                password_selector="#p",
                submit_selector="#s",
            ),
            ClickAction(type="click", selector="#btn"),
            FillAction(type="fill", selector="#input", value="test"),
            WaitAction(type="wait", delay=1000),
            ExtractAction(type="extract", selector=".data", name="data"),
            ScreenshotAction(type="screenshot", name="test"),
        ]

        expected_types = ["login", "click", "fill", "wait", "extract", "screenshot"]

        for action, expected_type in zip(actions, expected_types):
            assert action.type == expected_type
