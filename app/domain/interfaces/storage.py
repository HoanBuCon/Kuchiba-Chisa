from typing import Protocol

class IRawStorage(Protocol):
    """
    Domain adapter port for storing raw downloaded contents (e.g., Filesystem, S3).
    """

    async def save_raw_page(self, title: str, page_id: int, content: str) -> str:
        """
        Saves the raw content and returns the storage URI/path.
        """
        ...
        
    async def read_raw_page(self, file_path: str) -> str:
        """
        Reads the raw content from the given storage URI/path.
        """
        ...
