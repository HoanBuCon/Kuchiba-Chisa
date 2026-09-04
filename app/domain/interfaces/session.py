from typing import Protocol

class IDbSession(Protocol):
    """
    Database-session operations required by the application layer.

    Concrete infrastructure sessions (for example SQLAlchemy AsyncSession) satisfy this
    protocol without exposing their implementation to domain services.
    """

    async def commit(self) -> None:
        """Persist the active transaction."""
        ...
