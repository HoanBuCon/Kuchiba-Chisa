from typing import Protocol

class IDbSession(Protocol):
    """
    Opaque marker protocol for a database session.
    Infrastructure layers will provide the concrete implementation (e.g. AsyncSession).
    """
    pass
