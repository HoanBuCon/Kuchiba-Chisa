from abc import ABC, abstractmethod

class IUnitOfWork(ABC):
    """
    Interface for Unit of Work to manage atomic database transactions.
    """
    @abstractmethod
    async def __aenter__(self) -> "IUnitOfWork":
        pass

    @abstractmethod
    async def __aexit__(self, exc_type, exc_val, traceback) -> None:
        pass

    @abstractmethod
    async def commit(self) -> None:
        pass

    @abstractmethod
    async def rollback(self) -> None:
        pass
