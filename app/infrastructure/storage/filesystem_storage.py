import os
import aiofiles
from app.domain.interfaces.storage import IRawStorage
from app.shared.utils.logger import get_logger

log = get_logger(__name__)

class FilesystemStorage(IRawStorage):
    """
    Local filesystem implementation of IRawStorage.
    Designed to be easily swapped with MinIO/S3 later.
    """

    def __init__(self, base_path: str = "data/raw_wiki"):
        self.base_path = base_path
        os.makedirs(self.base_path, exist_ok=True)

    async def save_raw_page(self, title: str, page_id: int, content: str) -> str:
        safe_title = "".join([c if c.isalnum() or c in " _-" else "_" for c in title])
        file_name = f"{safe_title}_{page_id}.wiki"
        file_path = os.path.join(self.base_path, file_name)

        try:
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(content)
            log.debug("Saved raw page to filesystem", file_path=file_path)
            return file_path
        except Exception as e:
            log.error("Failed to save raw page to filesystem", file_path=file_path, error=str(e))
            raise

    async def read_raw_page(self, file_path: str) -> str:
        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                content = await f.read()
            return content
        except Exception as e:
            log.error("Failed to read raw page from filesystem", file_path=file_path, error=str(e))
            raise
