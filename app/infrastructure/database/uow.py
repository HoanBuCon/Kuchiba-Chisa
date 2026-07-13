from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from app.domain.interfaces.uow import IUnitOfWork

class UnitOfWork(IUnitOfWork):
    """
    Unit of Work pattern to ensure atomic transactions across multiple repositories.
    Automatically commits on success or rolls back on exception.
    """
    def __init__(self, session: AsyncSession):
        self.session = session
        self._savepoint = None

    async def __aenter__(self):
        # We assume the session is already active.
        # We can create a nested transaction (savepoint) for finer control.
        self._savepoint = await self.session.begin_nested()
        return self

    async def __aexit__(self, exc_type, exc_val, traceback):
        if exc_type is not None:
            await self._savepoint.rollback()
        else:
            await self._savepoint.commit()
            
    async def commit(self):
        """Force a commit explicitly if needed."""
        await self.session.commit()
        
    async def rollback(self):
        """Force a rollback explicitly if needed."""
        await self.session.rollback()
