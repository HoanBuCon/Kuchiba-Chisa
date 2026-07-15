from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class WikiPage(BaseModel):
    """
    Metadata for a Wiki Page during enumeration and sync.
    """
    page_id: int
    title: str
    latest_revision_id: int
    last_updated: datetime

class WikiRevision(BaseModel):
    """
    The actual content of a Wiki page revision downloaded from the API.
    """
    page_id: int
    title: str
    revision_id: int
    content: str
    timestamp: datetime

class DownloadedPage(BaseModel):
    """
    Output DTO for the DownloaderStage representing a successfully synced page.
    """
    page_id: int
    title: str
    revision_id: int
    file_path: str
