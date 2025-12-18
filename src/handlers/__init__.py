# AWS Web Crawler - Handlers Package
from .crawler import handler as crawler_handler
from .task_submitter import handler as task_submitter_handler

__all__ = [
    "crawler_handler",
    "task_submitter_handler",
]
