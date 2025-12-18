"""
Type definitions for AWS Web Crawler using Pydantic models
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field, HttpUrl


class WaitState(str, Enum):
    """States for wait actions"""
    ATTACHED = "attached"
    DETACHED = "detached"
    VISIBLE = "visible"
    HIDDEN = "hidden"


class WaitUntil(str, Enum):
    """Navigation wait conditions"""
    LOAD = "load"
    DOMCONTENTLOADED = "domcontentloaded"
    NETWORKIDLE = "networkidle"


# ============================================
# Action Models
# ============================================

class LoginAction(BaseModel):
    """Login to a website using stored credentials"""
    type: Literal["login"] = "login"
    username_xpath: str = Field(..., description="XPath to username input, e.g. //input[@id='email']")
    password_xpath: str = Field(..., description="XPath to password input, e.g. //input[@id='password']")
    submit_xpath: str = Field(..., description="XPath to submit button, e.g. //button[@type='submit']")
    secret_key: Optional[str] = None  # Key in Secrets Manager
    wait_after_submit: Optional[int] = None  # ms to wait after submit


class ClickAction(BaseModel):
    """Click an element"""
    type: Literal["click"] = "click"
    xpath: str = Field(..., description="XPath to element, e.g. //button[@id='submit']")
    wait_for_navigation: bool = False
    delay: Optional[int] = None  # ms delay before click


class FillAction(BaseModel):
    """Fill an input field"""
    type: Literal["fill"] = "fill"
    xpath: str = Field(..., description="XPath to input element, e.g. //input[@name='email']")
    value: str
    clear_first: bool = False


class WaitAction(BaseModel):
    """Wait for an element or delay"""
    type: Literal["wait"] = "wait"
    xpath: Optional[str] = Field(None, description="XPath to wait for, e.g. //div[@class='loaded']")
    state: Optional[WaitState] = WaitState.VISIBLE
    timeout: Optional[int] = None
    delay: Optional[int] = None  # Simple delay in ms


class ExtractAction(BaseModel):
    """Extract data from the page"""
    type: Literal["extract"] = "extract"
    xpath: str = Field(..., description="XPath to element(s), e.g. //span[@class='price']")
    attribute: str = "inner_text"  # inner_text, inner_html, or attribute name
    multiple: bool = False
    name: str  # Key for the extracted data


class ScreenshotAction(BaseModel):
    """Take a screenshot"""
    type: Literal["screenshot"] = "screenshot"
    xpath: Optional[str] = Field(None, description="XPath to element for screenshot, e.g. //div[@id='chart']")
    full_page: bool = False
    name: Optional[str] = None  # Filename for the screenshot


class NavigateAction(BaseModel):
    """Navigate to a URL"""
    type: Literal["navigate"] = "navigate"
    url: str
    wait_until: WaitUntil = WaitUntil.DOMCONTENTLOADED


class SelectAction(BaseModel):
    """Select from a dropdown"""
    type: Literal["select"] = "select"
    xpath: str = Field(..., description="XPath to select element, e.g. //select[@id='country']")
    value: str
    by_label: bool = False


class HoverAction(BaseModel):
    """Hover over an element"""
    type: Literal["hover"] = "hover"
    xpath: str = Field(..., description="XPath to element, e.g. //div[@class='menu-item']")


class ScrollAction(BaseModel):
    """Scroll the page"""
    type: Literal["scroll"] = "scroll"
    xpath: Optional[str] = Field(None, description="XPath to scroll to, e.g. //footer")
    x: Optional[int] = None
    y: Optional[int] = None


class EvaluateAction(BaseModel):
    """Execute custom JavaScript"""
    type: Literal["evaluate"] = "evaluate"
    script: str
    name: Optional[str] = None  # Key for the result


# Union of all action types
CrawlerAction = Union[
    LoginAction,
    ClickAction,
    FillAction,
    WaitAction,
    ExtractAction,
    ScreenshotAction,
    NavigateAction,
    SelectAction,
    HoverAction,
    ScrollAction,
    EvaluateAction,
]


# ============================================
# Configuration Models
# ============================================

class Viewport(BaseModel):
    """Browser viewport configuration"""
    width: int = 1920
    height: int = 1080


class ProxyConfig(BaseModel):
    """Proxy configuration"""
    server: str
    username: Optional[str] = None
    password: Optional[str] = None


class TaskConfig(BaseModel):
    """Configuration options for a crawler task"""
    timeout: int = 30000  # Page load timeout in ms
    wait_until: WaitUntil = WaitUntil.DOMCONTENTLOADED
    viewport: Viewport = Field(default_factory=Viewport)
    user_agent: Optional[str] = None
    headers: Optional[dict[str, str]] = None
    proxy: Optional[ProxyConfig] = None


# ============================================
# Task Models
# ============================================

class CrawlerTask(BaseModel):
    """A crawler task message from SQS"""
    task_id: Optional[str] = None
    url: HttpUrl
    actions: list[CrawlerAction]
    config: TaskConfig = Field(default_factory=TaskConfig)
    metadata: dict[str, str] = Field(default_factory=dict)


# ============================================
# Result Models
# ============================================

class ScreenshotResult(BaseModel):
    """Result of a screenshot action"""
    name: str
    s3_key: str
    s3_url: str


class ErrorInfo(BaseModel):
    """Information about an error during execution"""
    action: str
    message: str
    stack: Optional[str] = None


class CrawlerResult(BaseModel):
    """Result of a crawler task"""
    task_id: str
    url: str
    success: bool
    duration: int  # ms
    timestamp: datetime
    data: dict[str, Any] = Field(default_factory=dict)
    screenshots: list[ScreenshotResult] = Field(default_factory=list)
    errors: list[ErrorInfo] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


# ============================================
# Secrets Model
# ============================================

class WebsiteCredentials(BaseModel):
    """Website credentials stored in Secrets Manager"""
    username: str
    password: str
    otp_secret: Optional[str] = None  # For 2FA if needed


# ============================================
# SQS Event Models
# ============================================

class SQSMessageAttributes(BaseModel):
    """SQS message attributes"""
    approximate_receive_count: str = Field(alias="ApproximateReceiveCount")
    sent_timestamp: str = Field(alias="SentTimestamp")
    sender_id: str = Field(alias="SenderId")
    approximate_first_receive_timestamp: str = Field(alias="ApproximateFirstReceiveTimestamp")

    class Config:
        populate_by_name = True


class SQSRecord(BaseModel):
    """A single SQS record from the event"""
    message_id: str = Field(alias="messageId")
    receipt_handle: str = Field(alias="receiptHandle")
    body: str
    attributes: dict[str, str]
    message_attributes: dict[str, Any] = Field(alias="messageAttributes")
    md5_of_body: str = Field(alias="md5OfBody")
    event_source: str = Field(alias="eventSource")
    event_source_arn: str = Field(alias="eventSourceARN")
    aws_region: str = Field(alias="awsRegion")

    class Config:
        populate_by_name = True


class SQSEvent(BaseModel):
    """Lambda event from SQS"""
    records: list[SQSRecord] = Field(alias="Records")

    class Config:
        populate_by_name = True


class BatchItemFailure(BaseModel):
    """A failed item in a batch"""
    item_identifier: str = Field(alias="itemIdentifier")

    class Config:
        populate_by_name = True


class SQSBatchResponse(BaseModel):
    """Lambda response for SQS batch processing"""
    batch_item_failures: list[BatchItemFailure] = Field(
        alias="batchItemFailures",
        default_factory=list
    )

    class Config:
        populate_by_name = True
