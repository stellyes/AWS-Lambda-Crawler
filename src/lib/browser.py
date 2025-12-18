"""
Browser setup for Playwright on AWS Lambda
Configures Chromium with anti-detection measures and Lambda-optimized settings
"""

import os
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from ..models.types import TaskConfig, Viewport
from .logger import ContextLogger

# Default browser configuration optimized for Lambda
DEFAULT_VIEWPORT = Viewport(width=1920, height=1080)

# Anti-detection user agent
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

# Chromium launch arguments for Lambda
LAMBDA_CHROMIUM_ARGS = [
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--disable-setuid-sandbox",
    "--no-first-run",
    "--no-sandbox",
    "--no-zygote",
    "--single-process",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-default-apps",
    "--disable-sync",
    "--disable-translate",
    "--hide-scrollbars",
    "--metrics-recording-only",
    "--mute-audio",
    "--safebrowsing-disable-auto-update",
    "--disable-blink-features=AutomationControlled",
]

# Anti-detection JavaScript to inject
ANTI_DETECTION_SCRIPT = """
() => {
    // Override navigator.webdriver
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
    });

    // Override navigator.plugins
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });

    // Override navigator.languages
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
    });

    // Override chrome runtime
    window.chrome = {
        runtime: {},
    };

    // Override permissions
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) =>
        parameters.name === 'notifications'
            ? Promise.resolve({ state: 'denied' })
            : originalQuery(parameters);
}
"""


class BrowserManager:
    """Manages Playwright browser lifecycle for Lambda"""

    def __init__(self, logger: ContextLogger):
        self.logger = logger
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._is_lambda = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - ensure cleanup"""
        await self.close()

    async def launch(self, config: Optional[TaskConfig] = None) -> Browser:
        """Launch a new browser instance"""
        config = config or TaskConfig()

        self.logger.info(
            "Launching browser",
            is_lambda=self._is_lambda,
            viewport=config.viewport.model_dump(),
        )

        self._playwright = await async_playwright().start()

        launch_args = LAMBDA_CHROMIUM_ARGS if self._is_lambda else [
            "--disable-blink-features=AutomationControlled",
        ]

        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=launch_args,
        )

        self.logger.info("Browser launched successfully")
        return self._browser

    async def create_context(
        self, config: Optional[TaskConfig] = None
    ) -> BrowserContext:
        """Create a new browser context with anti-detection measures"""
        if not self._browser:
            await self.launch(config)

        config = config or TaskConfig()
        viewport = config.viewport or DEFAULT_VIEWPORT

        context_options = {
            "viewport": {"width": viewport.width, "height": viewport.height},
            "user_agent": config.user_agent or DEFAULT_USER_AGENT,
            "locale": "en-US",
            "timezone_id": "America/Los_Angeles",
            "extra_http_headers": {
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                **(config.headers or {}),
            },
            "bypass_csp": True,
            "ignore_https_errors": True,
        }

        # Add proxy if configured
        if config.proxy:
            context_options["proxy"] = {
                "server": config.proxy.server,
                "username": config.proxy.username,
                "password": config.proxy.password,
            }

        self._context = await self._browser.new_context(**context_options)

        # Add anti-detection scripts
        await self._context.add_init_script(ANTI_DETECTION_SCRIPT)

        self.logger.info("Browser context created with anti-detection measures")
        return self._context

    async def new_page(self, config: Optional[TaskConfig] = None) -> Page:
        """Create a new page in the current context"""
        if not self._context:
            await self.create_context(config)

        config = config or TaskConfig()
        page = await self._context.new_page()

        # Set default timeouts
        page.set_default_timeout(config.timeout)
        page.set_default_navigation_timeout(config.timeout)

        self.logger.info("New page created")
        return page

    async def close(self) -> None:
        """Close all browser resources"""
        try:
            if self._context:
                await self._context.close()
                self._context = None

            if self._browser:
                await self._browser.close()
                self._browser = None

            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

            self.logger.info("Browser closed successfully")
        except Exception as e:
            self.logger.warning("Error closing browser", error=str(e))


def create_browser_manager(logger: ContextLogger) -> BrowserManager:
    """Create a BrowserManager instance"""
    return BrowserManager(logger)
