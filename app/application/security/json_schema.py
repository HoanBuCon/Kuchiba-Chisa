"""Fail-closed validation for the constrained JSON Schema dialect used by LLM ports.

Provider JSON-mode is only a transport hint.  This module validates the parsed
payload before it crosses the infrastructure/application boundary.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class StructuredOutputValidationError(ValueError):
    """The provider output does not satisfy the declared structured contract."""


def validate_structured_output(payload: object, schema: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a parsed LLM object against the supported strict JSON Schema subset."""
    _validate(payload, schema, path="$", reject_unspecified_properties=True)
    if not isinstance(payload, dict):
        raise StructuredOutputValidationError("$: expected object")
    return payload


def _validate(
    value: object,
    schema: Mapping[str, Any],
    *,
    path: str,
    reject_unspecified_properties: bool,
) -> None:
    value_types = schema.get("type")
    accepted_types = value_types if isinstance(value_types, list) else [value_types]
    if value_types is not None and not any(
        _matches_type(value, value_type) for value_type in accepted_types
    ):
        expected = " or ".join(str(value_type) for value_type in accepted_types)
        raise StructuredOutputValidationError(f"{path}: expected {expected}")

    if "enum" in schema and value not in schema["enum"]:
        raise StructuredOutputValidationError(f"{path}: value is outside the allowed enum")

    if isinstance(value, str):
        _validate_string(value, schema, path)
    elif isinstance(value, list):
        _validate_array(value, schema, path, reject_unspecified_properties)
    elif isinstance(value, dict):
        _validate_object(value, schema, path, reject_unspecified_properties)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        _validate_number(value, schema, path)


def _matches_type(value: object, value_type: object) -> bool:
    if not isinstance(value_type, str):
        return False
    return {
        "array": isinstance(value, list),
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "null": value is None,
        "number": isinstance(value, int | float) and not isinstance(value, bool),
        "object": isinstance(value, dict),
        "string": isinstance(value, str),
    }.get(value_type, False)


def _validate_string(value: str, schema: Mapping[str, Any], path: str) -> None:
    if len(value) < schema.get("minLength", 0):
        raise StructuredOutputValidationError(f"{path}: string is shorter than the minimum")
    maximum = schema.get("maxLength")
    if maximum is not None and len(value) > maximum:
        raise StructuredOutputValidationError(f"{path}: string exceeds the maximum length")


def _validate_number(value: int | float, schema: Mapping[str, Any], path: str) -> None:
    minimum = schema.get("minimum")
    if minimum is not None and value < minimum:
        raise StructuredOutputValidationError(f"{path}: number is below the minimum")
    maximum = schema.get("maximum")
    if maximum is not None and value > maximum:
        raise StructuredOutputValidationError(f"{path}: number exceeds the maximum")


def _validate_array(
    value: list[Any],
    schema: Mapping[str, Any],
    path: str,
    reject_unspecified_properties: bool,
) -> None:
    if len(value) < schema.get("minItems", 0):
        raise StructuredOutputValidationError(f"{path}: array is shorter than the minimum")
    maximum = schema.get("maxItems")
    if maximum is not None and len(value) > maximum:
        raise StructuredOutputValidationError(f"{path}: array exceeds the maximum length")
    item_schema = schema.get("items")
    if isinstance(item_schema, Mapping):
        for index, item in enumerate(value):
            _validate(
                item,
                item_schema,
                path=f"{path}[{index}]",
                reject_unspecified_properties=reject_unspecified_properties,
            )


def _validate_object(
    value: dict[str, Any],
    schema: Mapping[str, Any],
    path: str,
    reject_unspecified_properties: bool,
) -> None:
    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise StructuredOutputValidationError(f"{path}: object schema has invalid properties")
    required = schema.get("required", [])
    for field in required:
        if field not in value:
            raise StructuredOutputValidationError(f"{path}: missing required field {field!r}")

    additional_properties = schema.get("additionalProperties", not reject_unspecified_properties)
    if additional_properties is False:
        unexpected = set(value).difference(properties)
        if unexpected:
            raise StructuredOutputValidationError(f"{path}: contains undeclared fields")

    for field, item in value.items():
        field_schema = properties.get(field)
        if isinstance(field_schema, Mapping):
            _validate(
                item,
                field_schema,
                path=f"{path}.{field}",
                reject_unspecified_properties=reject_unspecified_properties,
            )
