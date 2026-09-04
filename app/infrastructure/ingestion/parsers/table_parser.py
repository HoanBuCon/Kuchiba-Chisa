"""
MediaWiki Table Parser — Extract structured data from wiki table syntax.

Implements §3.2 Stage 3 (Table Normalization) of the Architecture Document.

MediaWiki tables use the syntax::

    {| class="article-table"
    !Header1 !! Header2 !! Header3
    |-
    |Cell1 || Cell2 || Cell3
    |-
    |Cell4
    |Cell5
    |Cell6
    |}

This parser handles:
    - Header rows (! and !! separators)
    - Data rows (| and || separators, also multi-line cells)
    - Nested bullet lists within cells (*, **)
    - Table attributes (class="...", style="...")
    - Multi-line cell content collapsed to single values
    - Malformed tables (graceful degradation)

Design:
    - Pure functions, no state, no I/O.
    - Returns List[Dict[str, str]] for each table.
    - Logs parsing failures with structured context for quality reporting.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)

# ─────────────────────────────────────────────────────────────
# Pre-compiled patterns
# ─────────────────────────────────────────────────────────────

# Match table start: {| with optional attributes
_RE_TABLE_START = re.compile(r"^\{\|.*$", re.MULTILINE)

# Match table end: |}
_RE_TABLE_END = re.compile(r"^\|\}\s*$", re.MULTILINE)

# Full table block extraction (non-greedy to handle consecutive tables)
_RE_TABLE_BLOCK = re.compile(
    r"(\{\|[^\n]*\n.*?\|\})",
    re.DOTALL,
)

# Row separator
_RE_ROW_SEP = re.compile(r"^\|-.*$", re.MULTILINE)

# Image size references in cells (e.g., "50px", "100px|link=...")
_RE_CELL_IMAGE = re.compile(r"\d+px(?:\|[^\s|]*)?")

# Wiki markup cleanup for cell values
_RE_CELL_BOLD = re.compile(r"'{3}(.+?)'{3}")
_RE_CELL_ITALIC = re.compile(r"'{2}(.+?)'{2}")
_RE_CELL_LINK_DISPLAY = re.compile(r"\[\[[^\]|]+\|([^\]]+)\]\]")
_RE_CELL_LINK_SIMPLE = re.compile(r"\[\[([^\]|]+)\]\]")


# ─────────────────────────────────────────────────────────────
# Table parsing
# ─────────────────────────────────────────────────────────────


def _clean_cell_value(raw: str) -> str:
    """
    Clean a single table cell value.

    Handles:
        - Wiki bold/italic markup
        - Wiki links
        - Bullet list items (*, **) → comma-separated text
        - Image references
        - Leading/trailing whitespace

    Args:
        raw: Raw cell content (may be multi-line with bullet items).

    Returns:
        Cleaned, human-readable cell text.
    """
    if not raw:
        return ""

    lines = raw.strip().split("\n")
    cleaned_parts: List[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Skip image-only lines
        if _RE_CELL_IMAGE.fullmatch(line.strip()):
            continue

        # Remove image references embedded in text
        line = _RE_CELL_IMAGE.sub("", line).strip()

        # Strip bullet prefixes: **, *, keeping content
        if line.startswith("**"):
            line = line[2:].strip()
        elif line.startswith("*"):
            line = line[1:].strip()

        # Clean wiki markup
        line = _RE_CELL_BOLD.sub(r"\1", line)
        line = _RE_CELL_ITALIC.sub(r"\1", line)
        line = _RE_CELL_LINK_DISPLAY.sub(r"\1", line)
        line = _RE_CELL_LINK_SIMPLE.sub(r"\1", line)

        if line:
            cleaned_parts.append(line)

    return ", ".join(cleaned_parts)


def _clean_header_value(raw: str) -> str:
    """Clean a table header name by stripping attributes and wikitext."""
    val = raw.strip()
    if "|" in val and ("style=" in val or "class=" in val or "width=" in val or "scope=" in val):
        val = val.split("|", 1)[1].strip()
    val = _RE_CELL_LINK_DISPLAY.sub(r"\1", val)
    val = _RE_CELL_LINK_SIMPLE.sub(r"\1", val)
    val = _RE_CELL_BOLD.sub(r"\1", val)
    val = _RE_CELL_ITALIC.sub(r"\1", val)
    return val.strip()


def _parse_header_row(row_text: str) -> List[str]:
    """
    Parse a header row (! delimited) into a list of column names.

    Handles both ``!H1!!H2!!H3`` (inline) and multi-line formats.

    Args:
        row_text: Raw header row text.

    Returns:
        List of cleaned header strings.
    """
    lines = [line.strip() for line in row_text.split("\n") if line.strip()]
    headers = []
    for line in lines:
        if line.startswith("!"):
            line = line[1:].strip()
        parts = re.split(r"\s*!{1,2}\s*", line)
        for p in parts:
            clean_h = _clean_header_value(p)
            if clean_h:
                headers.append(clean_h)
    return headers


def _split_into_raw_rows(table_body: str) -> List[str]:
    """
    Split table body into raw row strings using ``|-`` as separator.

    Args:
        table_body: Table content between {| and |} (excluding those markers).

    Returns:
        List of raw row text blocks.
    """
    rows = _RE_ROW_SEP.split(table_body)
    return [row.strip() for row in rows if row.strip()]


def _parse_data_cells(row_text: str) -> List[str]:
    """
    Parse a data row into individual cell values.

    Handles:
        - Inline separator: ``|Cell1||Cell2||Cell3``
        - Multi-line: each ``|Value`` on its own line
        - Mixed: bullet lists spanning multiple lines within a cell

    Args:
        row_text: Raw data row text (already stripped of ``|-``).

    Returns:
        List of raw cell value strings (before cleaning).
    """
    lines = row_text.split("\n")
    cells: List[str] = []
    current_cell_lines: List[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Check if this line starts a new cell (starts with | but not ||)
        if stripped.startswith("|") and not stripped.startswith("|}"):
            # If we have accumulated lines, save the previous cell
            if current_cell_lines:
                cells.append("\n".join(current_cell_lines))
                current_cell_lines = []

            # Handle inline || separator
            cell_content = stripped[1:]  # Remove leading |
            if "||" in cell_content:
                # Multiple cells on one line
                inline_cells = cell_content.split("||")
                # First N-1 cells are complete
                for ic in inline_cells[:-1]:
                    cells.append(ic.strip())
                # Last cell may continue on next lines
                current_cell_lines = [inline_cells[-1].strip()]
            else:
                current_cell_lines = [cell_content.strip()]

        elif stripped.startswith("*") or stripped.startswith("**"):
            # Continuation: bullet list item within the current cell
            current_cell_lines.append(stripped)
        else:
            # Continuation of the current cell
            current_cell_lines.append(stripped)

    # Don't forget the last cell
    if current_cell_lines:
        cells.append("\n".join(current_cell_lines))

    return cells


def parse_mediawiki_table(
    table_text: str,
    *,
    page_id: Optional[int] = None,
) -> List[Dict[str, str]]:
    """
    Parse a single MediaWiki table block into a list of row dicts.

    Implements §3.2 Stage 3 strategy:
        1. Detect header row (! syntax)
        2. Parse data rows (| syntax) with |- separators
        3. Map each row's cells to header columns
        4. Clean cell values (strip markup, images, collapse bullets)

    If headers cannot be detected, auto-generates Column_0, Column_1, etc.

    Args:
        table_text: Full table block including {| and |}.
        page_id: Optional page ID for structured log context.

    Returns:
        List of dicts, each mapping header → cleaned cell value.
        Returns empty list if parsing fails completely.

    Example::

        table = '''{| class="article-table"
        !Name!!Position
        |-
        |Lucilla
        |President
        |}'''
        result = parse_mediawiki_table(table)
        # [{"Name": "Lucilla", "Position": "President"}]
    """
    log_ctx = {"page_id": page_id} if page_id else {}

    if not table_text or "{|" not in table_text:
        return []

    try:
        # Strip the {| ... and |} markers
        lines = table_text.strip().split("\n")

        # Remove {| line (first line) and |} line (last line)
        if lines and lines[0].strip().startswith("{|"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("|}"):
            lines = lines[:-1]

        body = "\n".join(lines)

        # ── Extract headers ──
        headers: List[str] = []
        header_line_idx: Optional[int] = None

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("!"):
                headers = _parse_header_row(stripped)
                header_line_idx = i
                break

        # Remove header line from body for row parsing
        if header_line_idx is not None:
            remaining_lines = lines[header_line_idx + 1:]
            body = "\n".join(remaining_lines)

        # ── Split into rows ──
        raw_rows = _split_into_raw_rows(body)

        # ── Parse each row ──
        result: List[Dict[str, str]] = []

        for row_text in raw_rows:
            cells = _parse_data_cells(row_text)
            cleaned_cells = [_clean_cell_value(c) for c in cells]

            # Filter out empty cells (often image-only columns)
            # But preserve positional alignment with headers
            if not any(cleaned_cells):
                continue

            if headers:
                # Map to header columns
                row_dict: Dict[str, str] = {}
                for j, header in enumerate(headers):
                    if j < len(cleaned_cells):
                        value = cleaned_cells[j]
                        if value:  # Only include non-empty values
                            row_dict[header] = value
                    # Skip if fewer cells than headers

                if row_dict:
                    result.append(row_dict)
            else:
                # No headers — use auto-generated column names
                row_dict = {
                    f"Column_{j}": val
                    for j, val in enumerate(cleaned_cells)
                    if val
                }
                if row_dict:
                    result.append(row_dict)

        logger.debug(
            "table_parsed",
            rows_extracted=len(result),
            headers=headers,
            **log_ctx,
        )
        return result

    except Exception as exc:
        logger.warning(
            "table_parse_failed",
            error=str(exc),
            table_preview=table_text[:200],
            **log_ctx,
        )
        return []


# ─────────────────────────────────────────────────────────────
# Batch table extraction
# ─────────────────────────────────────────────────────────────


def extract_all_tables(
    text: str,
    *,
    page_id: Optional[int] = None,
) -> Tuple[List[List[Dict[str, str]]], int, int]:
    """
    Find and parse all MediaWiki tables in a wikitext document.

    Args:
        text: Full wikitext content (may contain multiple tables).
        page_id: Optional page ID for structured log context.

    Returns:
        Tuple of:
            - List of parsed tables (each is a list of row dicts)
            - Number of tables successfully parsed
            - Number of tables that failed to parse

    Example::

        tables, ok, fail = extract_all_tables(wikitext, page_id=54321)
        # tables = [[{"Name": "A"}, {"Name": "B"}], [{"Col": "X"}]]
        # ok = 2, fail = 0
    """
    table_blocks = _RE_TABLE_BLOCK.findall(text)

    if not table_blocks:
        return [], 0, 0

    parsed_tables: List[List[Dict[str, str]]] = []
    tables_ok = 0
    tables_failed = 0

    for block in table_blocks:
        result = parse_mediawiki_table(block, page_id=page_id)
        if result:
            parsed_tables.append(result)
            tables_ok += 1
        else:
            tables_failed += 1

    logger.debug(
        "all_tables_extracted",
        total=len(table_blocks),
        parsed=tables_ok,
        failed=tables_failed,
        page_id=page_id,
    )

    return parsed_tables, tables_ok, tables_failed
