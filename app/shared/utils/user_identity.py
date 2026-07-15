import uuid

_CHISA_USER_ID_NAMESPACE = uuid.UUID("7d5e3f19-9c4b-4d17-8ef6-2d9f6fdfcf6a")


def normalize_user_id(user_id: str) -> uuid.UUID:
    """
    Normalize any caller-provided user identifier into a UUID.

    Existing UUID strings are preserved. Non-UUID identifiers are mapped to a
    stable UUID5 so the same external id always resolves to the same database
    identity.
    """
    try:
        return uuid.UUID(str(user_id).strip())
    except (TypeError, ValueError, AttributeError):
        return uuid.uuid5(_CHISA_USER_ID_NAMESPACE, str(user_id).strip())


def normalize_user_id_str(user_id: str) -> str:
    """Canonical string form used across API, Postgres, and Qdrant filters."""
    return str(normalize_user_id(user_id))