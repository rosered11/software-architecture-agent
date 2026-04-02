#!/usr/bin/env python3
"""
KOS → Notion Real-Time Sync
Parses KOS markdown files and upserts records into Notion databases.

Usage:
  python sync/kos_sync.py              # full sync all databases
  python sync/kos_sync.py --db k       # sync Knowledge only
  python sync/kos_sync.py --db p       # sync Patterns only
  python sync/kos_sync.py --db d       # sync Decision Log only
  python sync/kos_sync.py --db ta      # sync Tech Assets only
  python sync/kos_sync.py --db i       # sync Incidents only

Triggered automatically by Claude Code hook on every KOS file edit.
"""

import json
import re
import sys
import time
import argparse
from pathlib import Path

# Ensure UTF-8 output on Windows (avoids cp874/cp1252 UnicodeEncodeError)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding and sys.stderr.encoding.lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

try:
    from notion_client import Client
    from notion_client.errors import APIResponseError, RequestTimeoutError as NotionTimeoutError
except ImportError:
    print("ERROR: notion-client not installed. Run: pip install notion-client")
    sys.exit(1)

# ── Paths ────────────────────────────────────────────────────────────────────

ROOT         = Path(__file__).parent.parent
CONFIG_PATH  = Path(__file__).parent / "config.json"
KOS_SD_PATH      = ROOT / "skills/software-architecture-specialist/references/kos-system-design.md"
KOS_KNOWLEDGE    = ROOT / "skills/software-architecture-specialist/references/kos-knowledge.md"
KOS_PATTERNS     = ROOT / "skills/software-architecture-specialist/references/kos-patterns.md"
KOS_DECISIONS    = ROOT / "skills/software-architecture-specialist/references/kos-decisions.md"
KOS_TECH_ASSETS  = ROOT / "skills/software-architecture-specialist/references/kos-tech-assets.md"
INCIDENT_PATH    = ROOT / "skills/software-architecture-specialist/references/kos-incident.md"
KOS_SPLIT_PATHS  = [KOS_KNOWLEDGE, KOS_PATTERNS, KOS_DECISIONS, KOS_TECH_ASSETS, INCIDENT_PATH]

# ── Config ───────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"ERROR: {CONFIG_PATH} not found.")
        print("  Copy sync/config.example.json → sync/config.json and fill in your values.")
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

# ── Parsers ──────────────────────────────────────────────────────────────────

_SNIPPET_MARKER = re.compile(r'^(?://|--)\s*Snippet:\s*$', re.IGNORECASE)


def parse_kv_block(block_text: str) -> dict:
    """
    Parse aligned 'Key:   Value' pairs from a KOS code block.
    Handles multi-line values where continuation lines are indented.
    Stops collecting continuation when a snippet marker (// Snippet: or -- Snippet:) is hit.
    """
    fields: dict = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in block_text.split("\n"):
        # Snippet marker — stop collecting continuation for current field
        if _SNIPPET_MARKER.match(line.strip()):
            if current_key:
                fields[current_key] = _join_value(current_lines)
                current_key = None
                current_lines = []
            continue

        # New field: starts at col 0 with word(s) followed by colon + 2+ spaces
        m = re.match(r"^([A-Za-z][A-Za-z\s/]*):\s{2,}(.*)", line)
        if m:
            if current_key:
                fields[current_key] = _join_value(current_lines)
            current_key = m.group(1).strip()
            current_lines = [m.group(2)]
        elif current_key and line.startswith("  "):
            # Continuation line — aligned to value column
            current_lines.append(line.strip())
        # bare empty line — ignore, don't break current field

    if current_key:
        fields[current_key] = _join_value(current_lines)

    return fields


def extract_snippet(block_text: str) -> str:
    """
    Extract the code snippet that follows a '// Snippet:' or '-- Snippet:' marker.
    Returns empty string if no marker found.
    Stops at the first non-indented, non-empty line that looks like a KV field.
    """
    lines = block_text.split("\n")
    in_snippet = False
    snippet_lines: list[str] = []

    for line in lines:
        if _SNIPPET_MARKER.match(line.strip()):
            in_snippet = True
            continue
        if in_snippet:
            # Stop when we hit a KV field header (new field starts)
            if re.match(r"^[A-Za-z][A-Za-z\s/]*:\s{2,}", line):
                break
            snippet_lines.append(line)

    return "\n".join(snippet_lines).strip()


def _join_value(lines: list[str]) -> str:
    """Join value lines, collapsing empty tail lines."""
    return "\n".join(lines).strip()


def extract_code_block(section_text: str) -> str | None:
    """Extract content between first ``` and last ``` in a section."""
    m = re.search(r"```\n(.*?)```", section_text, re.DOTALL)
    return m.group(1) if m else None


def parse_kos_system_design() -> dict[str, list[dict]]:
    """
    Parse all KOS split files into records.
    Handles ### K#:, ### P#:, ### D#:, ### TA#:, ### I#: headers uniformly.
    Falls back to legacy kos-system-design.md if split files are not present.
    """
    sources = [p for p in KOS_SPLIT_PATHS if p.exists()]
    if not sources:
        sources = [KOS_SD_PATH]
    text = "\n".join(p.read_text(encoding="utf-8") for p in sources)
    result: dict[str, list[dict]] = {
        "knowledge": [],
        "patterns": [],
        "decisions": [],
        "tech_assets": [],
        "incidents": [],
    }

    # Split on section headers (### K1:, ### P1:, ### D1:, ### TA1:, ### I1:)
    sections = re.split(r"\n(?=### (?:K|P|D|TA|I)\d+:)", text)

    for section in sections:
        header_m = re.match(r"### (K|P|D|TA|I)(\d+):\s+(.+)", section)
        if not header_m:
            continue

        prefix   = header_m.group(1)   # K / P / D / TA / I
        number   = header_m.group(2)
        title    = header_m.group(3).strip()
        kos_id   = f"{prefix}{number}"

        block_text = extract_code_block(section)
        if not block_text:
            continue

        fields = parse_kv_block(block_text)
        fields["_id"]    = kos_id
        fields["_title"] = fields.get("Title") or fields.get("Name") or title

        # For Tech Assets, extract the code snippet separately
        if prefix == "TA":
            snippet = extract_snippet(block_text)
            if snippet:
                fields["Snippet"] = snippet

        db_map = {"K": "knowledge", "P": "patterns", "D": "decisions", "TA": "tech_assets", "I": "incidents"}
        result[db_map[prefix]].append(fields)

    return result



# ── Notion Helpers ────────────────────────────────────────────────────────────

RATE_LIMIT_DELAY = 0.35   # seconds between API calls (~3 req/s)


def _rtext(value: str) -> dict:
    """Build a Notion rich_text property value (max 2000 chars)."""
    return {"rich_text": [{"type": "text", "text": {"content": value[:2000]}}]}


def _title(value: str) -> dict:
    return {"title": [{"type": "text", "text": {"content": value[:255]}}]}


def _select(value: str) -> dict:
    return {"select": {"name": value[:100]}} if value else {"select": None}


def _relation(page_ids: list[str]) -> dict:
    """Build a Notion relation property value from a list of Notion page IDs."""
    return {"relation": [{"id": pid} for pid in page_ids]}


def extract_kos_ids(text: str) -> list[str]:
    """Extract all KOS IDs (K1, P10, TA3, D2, etc.) from a text value."""
    return re.findall(r"\b(TA\d+|[KPDI]\d+)\b", text)


def build_id_map(notion: Client, db_id: str) -> dict[str, str]:
    """
    Query a Notion database and return a mapping of KOS ID → Notion page ID.
    Fetches all pages (handles pagination).
    """
    id_map: dict[str, str] = {}
    cursor = None

    while True:
        kwargs: dict = {"database_id": db_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        try:
            resp = notion.databases.query(**kwargs)
        except APIResponseError as e:
            print(f"  ⚠ Could not build ID map for {db_id[:8]}: {e}")
            break

        for page in resp.get("results", []):
            kos_prop = page.get("properties", {}).get("KOS ID", {})
            rich = kos_prop.get("rich_text", [])
            if rich:
                kos_id = rich[0].get("plain_text", "")
                if kos_id:
                    id_map[kos_id] = page["id"]

        if resp.get("has_more"):
            cursor = resp.get("next_cursor")
            time.sleep(RATE_LIMIT_DELAY)
        else:
            break

    return id_map


def find_page(notion: Client, db_id: str, kos_id: str) -> str | None:
    """Return page_id if a page with matching KOS ID exists, else None."""
    try:
        resp = notion.databases.query(
            database_id=db_id,
            filter={"property": "KOS ID", "rich_text": {"equals": kos_id}},
        )
        results = resp.get("results", [])
        return results[0]["id"] if results else None
    except APIResponseError as e:
        print(f"    ⚠ Query error for {kos_id}: {e}")
        return None


_NOTION_CODE_LANGS = {
    "python", "go", "sql", "c#", "javascript", "typescript",
    "bash", "shell", "json", "yaml", "java", "ruby", "rust",
    "kotlin", "swift", "php", "html", "css", "xml", "markdown",
}

def _lang(raw: str) -> str:
    raw = raw.lower().strip()
    if raw in ("csharp", "dotnet", ".net"):
        return "c#"
    return raw if raw in _NOTION_CODE_LANGS else "plain text"


def _parse_rich_text(text: str) -> list:
    """Parse **bold** and `code` inline markers into Notion rich_text segments."""
    parts = []
    pattern = re.compile(r'(\*\*[^*\n]+\*\*|`[^`\n]+`)')
    last = 0
    for m in pattern.finditer(text):
        if m.start() > last:
            parts.append({"type": "text", "text": {"content": text[last:m.start()]}})
        token = m.group(0)
        if token.startswith("**"):
            parts.append({"type": "text", "text": {"content": token[2:-2]},
                          "annotations": {"bold": True}})
        else:
            parts.append({"type": "text", "text": {"content": token[1:-1]},
                          "annotations": {"code": True}})
        last = m.end()
    if last < len(text):
        parts.append({"type": "text", "text": {"content": text[last:]}})
    if not parts:
        parts = [{"type": "text", "text": {"content": text}}]
    for p in parts:
        if len(p["text"]["content"]) > 2000:
            p["text"]["content"] = p["text"]["content"][:2000]
    return parts


def _parse_md_table(table_lines: list[str]) -> dict | None:
    """
    Convert a list of Markdown table lines into a Notion table block.
    Skips separator rows (e.g. |---|---|).
    Returns a Notion block dict, or None if there are no valid rows.
    """
    _sep = re.compile(r'^[\s|:\-]+$')

    rows = []
    for line in table_lines:
        # Strip leading/trailing pipes and whitespace
        inner = line.strip().strip("|")
        cells = [c.strip() for c in inner.split("|")]
        # Skip separator rows
        if all(_sep.match(c) for c in cells if c):
            continue
        rows.append(cells)

    if not rows:
        return None

    col_count = max(len(r) for r in rows)

    notion_rows = []
    for i, row in enumerate(rows):
        # Pad row to col_count
        padded = row + [""] * (col_count - len(row))
        cells = [_parse_rich_text(cell) for cell in padded]
        notion_rows.append({
            "type": "table_row",
            "table_row": {"cells": cells},
        })

    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": col_count,
            "has_column_header": True,
            "has_row_header": False,
            "children": notion_rows,
        },
    }


def _value_to_blocks(text: str) -> list:
    """Render a field value as structured Notion blocks (lists, code, headings, tables)."""
    blocks = []
    in_code = False
    code_lines: list[str] = []
    code_lang = "plain text"
    table_lines: list[str] = []

    def flush_table():
        if table_lines:
            tbl = _parse_md_table(table_lines)
            if tbl:
                blocks.append(tbl)
            table_lines.clear()

    for line in text.split("\n"):
        stripped = line.strip()

        # Code fence
        if stripped.startswith("```"):
            flush_table()
            if in_code:
                content = "\n".join(code_lines)
                if content.strip():
                    blocks.append({
                        "object": "block", "type": "code",
                        "code": {
                            "rich_text": [{"type": "text",
                                           "text": {"content": content[:2000]}}],
                            "language": code_lang,
                        },
                    })
                code_lines = []
                in_code = False
            else:
                code_lang = _lang(stripped[3:])
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        # Markdown table row: starts with |
        if stripped.startswith("|"):
            table_lines.append(stripped)
            continue

        # Non-table line — flush any buffered table first
        flush_table()

        if not stripped:
            continue

        # Bullet list: - item  or  * item
        if re.match(r'^[-*]\s+', stripped):
            blocks.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": _parse_rich_text(re.sub(r'^[-*]\s+', '', stripped))
                },
            })

        # Numbered list: 1. item  or  1) item
        elif re.match(r'^\d+[.)]\s+', stripped):
            blocks.append({
                "object": "block", "type": "numbered_list_item",
                "numbered_list_item": {
                    "rich_text": _parse_rich_text(re.sub(r'^\d+[.)]\s+', '', stripped))
                },
            })

        # Lettered option list: A. item  B. item  (decision option blocks)
        elif re.match(r'^[A-Z][.)]\s+', stripped):
            blocks.append({
                "object": "block", "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": _parse_rich_text(stripped)},
            })

        # ALL-CAPS subsection header: "WRITE PATH:", "ACK LEVELS:", etc.
        # Heuristic: first two chars both uppercase, line ends with ":"
        elif (stripped.endswith(":")
              and len(stripped) >= 4
              and stripped[0].isupper() and stripped[1].isupper()):
            blocks.append({
                "object": "block", "type": "heading_3",
                "heading_3": {
                    "rich_text": [{"type": "text",
                                   "text": {"content": stripped.rstrip(":")}}]
                },
            })

        # Regular paragraph
        else:
            blocks.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": _parse_rich_text(stripped)},
            })

    # Flush any remaining table or code block
    flush_table()
    if in_code and code_lines:
        content = "\n".join(code_lines)
        if content.strip():
            blocks.append({
                "object": "block", "type": "code",
                "code": {
                    "rich_text": [{"type": "text",
                                   "text": {"content": content[:2000]}}],
                    "language": code_lang,
                },
            })

    return blocks


def record_to_blocks(record: dict) -> list:
    """Convert record fields to well-structured Notion page blocks."""
    skip = {"_id", "_title", "Title", "Name"}
    blocks = []

    entries = [
        (k, str(v).strip())
        for k, v in record.items()
        if k not in skip and v and str(v).strip()
    ]

    for i, (key, value) in enumerate(entries):
        blocks.append({
            "object": "block", "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": key}}]
            },
        })
        if key == "Snippet":
            # Render as a code block using the Language field from the same record
            lang = _lang(record.get("Language", ""))
            blocks.append({
                "object": "block", "type": "code",
                "code": {
                    "rich_text": [{"type": "text", "text": {"content": value[:2000]}}],
                    "language": lang,
                },
            })
        else:
            blocks.extend(_value_to_blocks(value))
        if i < len(entries) - 1:
            blocks.append({"object": "block", "type": "divider", "divider": {}})

    return blocks[:100]


def _chunk(text: str, size: int) -> list[str]:
    return [text[i:i+size] for i in range(0, len(text), size)] if text else []


_NOTION_ERRORS = (APIResponseError, NotionTimeoutError)


def _append_children(notion: Client, parent_id: str, blocks: list):
    """Append blocks to a parent page/block in one call."""
    if blocks:
        notion.blocks.children.append(block_id=parent_id, children=blocks)
        time.sleep(RATE_LIMIT_DELAY)


def clear_page_body(notion: Client, page_id: str):
    """Archive all child blocks of a page to clear its body content."""
    try:
        resp = notion.blocks.children.list(block_id=page_id)
        for block in resp.get("results", []):
            for attempt in range(3):
                try:
                    notion.blocks.update(block_id=block["id"], archived=True)
                    time.sleep(RATE_LIMIT_DELAY)
                    break
                except NotionTimeoutError:
                    if attempt < 2:
                        time.sleep(5 * (attempt + 1))
                    # else silently skip this block
                except APIResponseError:
                    break
    except _NOTION_ERRORS:
        pass


def upsert_page(notion: Client, db_id: str, properties: dict, record: dict,
                rebuild_body: bool = False):
    """Create or update a Notion page. Returns ('created'|'updated', page_id)."""
    kos_id = record["_id"]
    existing_id = find_page(notion, db_id, kos_id)
    time.sleep(RATE_LIMIT_DELAY)

    if existing_id:
        notion.pages.update(page_id=existing_id, properties=properties)
        if rebuild_body:
            clear_page_body(notion, existing_id)
            children = record_to_blocks(record)
            if children:
                _append_children(notion, existing_id, children)
        return "updated", existing_id
    else:
        page = notion.pages.create(
            parent={"database_id": db_id},
            properties=properties,
            children=record_to_blocks(record),
        )
        return "created", page["id"]

# ── Per-Database Sync ─────────────────────────────────────────────────────────

def sync_knowledge(notion: Client, db_id: str, records: list[dict],
                   id_maps: dict[str, dict] | None = None,
                   rebuild_body: bool = False) -> dict[str, str]:
    print(f"\n📚 Knowledge — {len(records)} records → DB {db_id[:8]}...")
    p_map = (id_maps or {}).get("patterns", {})

    for r in records:
        props = {
            "Name":       _title(r["_title"]),
            "KOS ID":     _rtext(r["_id"]),
            "Domain":     _select(r.get("Domain", "")),
            "Type":       _select(r.get("Type", "")),
            "Difficulty": _select(r.get("Difficulty", "")),
            "Summary":    _rtext(r.get("Summary", "")),
            "Source":     _rtext(r.get("Source", "")),
        }

        # Relation: Related Patterns → Patterns DB
        if p_map:
            raw = r.get("Related Patterns", "")
            p_ids = [p_map[pid] for pid in extract_kos_ids(raw) if pid in p_map]
            if p_ids:
                props["Related Patterns"] = _relation(p_ids)

        try:
            action, _ = upsert_page(notion, db_id, props, r, rebuild_body)
            print(f"  {'✓' if action == 'updated' else '+'} {action:7}  {r['_id']}: {r['_title']}")
        except APIResponseError as e:
            props.pop("Related Patterns", None)
            action, _ = upsert_page(notion, db_id, props, r, rebuild_body)
            print(f"  {'✓' if action == 'updated' else '+'} {action:7}  {r['_id']}: {r['_title']}  ⚠ relation skipped: {e}")
        time.sleep(RATE_LIMIT_DELAY)

    return build_id_map(notion, db_id)


def sync_patterns(notion: Client, db_id: str, records: list[dict],
                  id_maps: dict[str, dict] | None = None,
                  rebuild_body: bool = False) -> dict[str, str]:
    print(f"\n🧩 Patterns — {len(records)} records → DB {db_id[:8]}...")
    k_map  = (id_maps or {}).get("knowledge", {})
    ta_map = (id_maps or {}).get("tech_assets", {})

    for r in records:
        props = {
            "Name":       _title(r["_title"]),
            "KOS ID":     _rtext(r["_id"]),
            "Category":   _select(r.get("Category", "")),
            "Complexity": _select(r.get("Complexity", "")),
            "Problem":    _rtext(r.get("Problem", "")),
        }

        # Relation: Based on Knowledge → Knowledge DB
        if k_map:
            raw = r.get("Based on Knowledge", "")
            k_ids = [k_map[kid] for kid in extract_kos_ids(raw) if kid in k_map]
            if k_ids:
                props["Based on Knowledge"] = _relation(k_ids)

        # Relation: Related Tech Assets → Tech Assets DB
        if ta_map:
            raw = r.get("Related Tech Assets", "")
            ta_ids = [ta_map[tid] for tid in extract_kos_ids(raw) if tid in ta_map]
            if ta_ids:
                props["Related Tech Assets"] = _relation(ta_ids)

        try:
            action, _ = upsert_page(notion, db_id, props, r, rebuild_body)
            print(f"  {'✓' if action == 'updated' else '+'} {action:7}  {r['_id']}: {r['_title']}")
        except APIResponseError as e:
            props.pop("Based on Knowledge", None)
            props.pop("Related Tech Assets", None)
            action, _ = upsert_page(notion, db_id, props, r, rebuild_body)
            print(f"  {'✓' if action == 'updated' else '+'} {action:7}  {r['_id']}: {r['_title']}  ⚠ relations skipped: {e}")
        time.sleep(RATE_LIMIT_DELAY)

    return build_id_map(notion, db_id)


def sync_decisions(notion: Client, db_id: str, records: list[dict],
                   id_maps: dict[str, dict] | None = None,
                   rebuild_body: bool = False) -> dict[str, str]:
    print(f"\n📋 Decision Log — {len(records)} records → DB {db_id[:8]}...")
    k_map = (id_maps or {}).get("knowledge", {})
    p_map = (id_maps or {}).get("patterns", {})

    for r in records:
        props = {
            "Name":    _title(r["_title"]),
            "KOS ID":  _rtext(r["_id"]),
            "Context": _rtext(r.get("Context", "")),
            "Problem": _rtext(r.get("Problem", "")),
        }

        # Relation: Related Knowledge → Knowledge DB
        if k_map:
            raw = r.get("Related Knowledge", "")
            k_ids = [k_map[kid] for kid in extract_kos_ids(raw) if kid in k_map]
            if k_ids:
                props["Related Knowledge"] = _relation(k_ids)

        # Relation: Related Pattern → Patterns DB
        if p_map:
            raw = r.get("Related Pattern", "")
            p_ids = [p_map[pid] for pid in extract_kos_ids(raw) if pid in p_map]
            if p_ids:
                props["Related Pattern"] = _relation(p_ids)

        try:
            action, _ = upsert_page(notion, db_id, props, r, rebuild_body)
            print(f"  {'✓' if action == 'updated' else '+'} {action:7}  {r['_id']}: {r['_title']}")
        except APIResponseError as e:
            props.pop("Related Knowledge", None)
            props.pop("Related Pattern", None)
            action, _ = upsert_page(notion, db_id, props, r, rebuild_body)
            print(f"  {'✓' if action == 'updated' else '+'} {action:7}  {r['_id']}: {r['_title']}  ⚠ relations skipped: {e}")
        time.sleep(RATE_LIMIT_DELAY)

    return build_id_map(notion, db_id)


def sync_tech_assets(notion: Client, db_id: str, records: list[dict],
                     id_maps: dict[str, dict] | None = None,
                     rebuild_body: bool = False) -> dict[str, str]:
    print(f"\n🔧 Tech Assets — {len(records)} records → DB {db_id[:8]}...")
    k_map = (id_maps or {}).get("knowledge", {})
    p_map = (id_maps or {}).get("patterns", {})
    has_relation = bool(k_map or p_map)

    for r in records:
        props = {
            "Name":     _title(r["_title"]),
            "KOS ID":   _rtext(r["_id"]),
            "Type":     _select(r.get("Type", "")),
            "Language": _select(r.get("Language", "")),
            "Usage":    _rtext(r.get("Usage", "")),
        }

        # Relation: Related Knowledge → Knowledge DB
        if k_map:
            raw = r.get("Related Knowledge", "")
            k_ids = [k_map[kid] for kid in extract_kos_ids(raw) if kid in k_map]
            if k_ids:
                props["Related Knowledge"] = _relation(k_ids)

        # Relation: Related Pattern → Patterns DB
        if p_map:
            raw = r.get("Related Pattern", "")
            p_ids = [p_map[pid] for pid in extract_kos_ids(raw) if pid in p_map]
            if p_ids:
                props["Related Pattern"] = _relation(p_ids)

        try:
            action, _ = upsert_page(notion, db_id, props, r, rebuild_body)
            print(f"  {'✓' if action == 'updated' else '+'} {action:7}  {r['_id']}: {r['_title']}")
        except APIResponseError as e:
            # Relation properties may not exist yet — retry without them
            props.pop("Related Knowledge", None)
            props.pop("Related Pattern", None)
            action, _ = upsert_page(notion, db_id, props, r, rebuild_body)
            print(f"  {'✓' if action == 'updated' else '+'} {action:7}  {r['_id']}: {r['_title']}  ⚠ relations skipped: {e}")
        time.sleep(RATE_LIMIT_DELAY)

    return build_id_map(notion, db_id)


def sync_incidents(notion: Client, db_id: str, records: list[dict],
                   id_maps: dict[str, dict] | None = None,
                   rebuild_body: bool = False) -> dict[str, str]:
    print(f"\n🔴 Incidents — {len(records)} records → DB {db_id[:8]}...")
    k_map = (id_maps or {}).get("knowledge", {})
    p_map = (id_maps or {}).get("patterns", {})
    d_map = (id_maps or {}).get("decisions", {})
    ta_map = (id_maps or {}).get("tech_assets", {})

    for r in records:
        props = {
            "Name":          _title(r["_title"]),
            "KOS ID":        _rtext(r["_id"]),
            "Severity":      _select(r.get("Severity", "")),
            "System":        _rtext(r.get("System", "")),
            "Status":        _rtext(r.get("Status", "")),
            "Root Cause":    _rtext(r.get("Root Cause", "")),
            "Lesson Learned":_rtext(r.get("Lesson Learned", "")),
        }

        # Relation: Related Knowledge → Knowledge DB
        if k_map:
            raw = r.get("Related Knowledge", "")
            k_ids = [k_map[kid] for kid in extract_kos_ids(raw) if kid in k_map]
            if k_ids:
                props["Related Knowledge"] = _relation(k_ids)

        # Relation: Related Pattern → Patterns DB
        if p_map:
            raw = r.get("Related Pattern", "")
            p_ids = [p_map[pid] for pid in extract_kos_ids(raw) if pid in p_map]
            if p_ids:
                props["Related Pattern"] = _relation(p_ids)

        # Relation: Related Decisions → Decisions DB
        if d_map:
            raw = r.get("Related Decisions", "")
            d_ids = [d_map[did] for did in extract_kos_ids(raw) if did in d_map]
            if d_ids:
                props["Related Decisions"] = _relation(d_ids)

        # Relation: Related Tech Assets → Tech Assets DB
        if ta_map:
            raw = r.get("Related Tech Assets", "")
            ta_ids = [ta_map[tid] for tid in extract_kos_ids(raw) if tid in ta_map]
            if ta_ids:
                props["Related Tech Assets"] = _relation(ta_ids)

        try:
            action, _ = upsert_page(notion, db_id, props, r, rebuild_body)
            print(f"  {'✓' if action == 'updated' else '+'} {action:7}  {r['_id']}: {r['_title']}")
        except APIResponseError as e:
            props.pop("Related Knowledge", None)
            props.pop("Related Pattern", None)
            action, _ = upsert_page(notion, db_id, props, r, rebuild_body)
            print(f"  {'✓' if action == 'updated' else '+'} {action:7}  {r['_id']}: {r['_title']}  ⚠ relations skipped: {e}")
        time.sleep(RATE_LIMIT_DELAY)

    return build_id_map(notion, db_id)

# ── Main ──────────────────────────────────────────────────────────────────────

DB_KEYS = {"k": "knowledge", "p": "patterns", "d": "decisions",
           "ta": "tech_assets", "i": "incidents"}

# Sync order matters:
# Pass 1: K → P → D → TA → I  (creates all pages; K synced without Patterns relations)
# Pass 2: K re-synced with Patterns id_map to wire Knowledge → Related Patterns
SYNC_ORDER = ["knowledge", "patterns", "decisions", "tech_assets", "incidents"]

SYNC_FNS = {
    "knowledge":   sync_knowledge,
    "patterns":    sync_patterns,
    "decisions":   sync_decisions,
    "tech_assets": sync_tech_assets,
    "incidents":   sync_incidents,
}

def main():
    parser = argparse.ArgumentParser(description="Sync KOS → Notion")
    parser.add_argument("--db", choices=list(DB_KEYS.keys()),
                        help="Sync only this database (default: all)")
    parser.add_argument("--rebuild-body", action="store_true",
                        help="Clear and rebuild page body blocks (for formatting updates)")
    args = parser.parse_args()

    config  = load_config()
    token   = config["notion_token"]
    dbs     = config["databases"]
    notion  = Client(auth=token)

    target       = DB_KEYS.get(args.db) if args.db else None
    rebuild_body = args.rebuild_body

    print("🔄 KOS → Notion Sync")
    print(f"   Target: {target or 'all databases'}")
    if rebuild_body:
        print("   Mode: rebuild page bodies")

    # Parse source files
    kos_data = parse_kos_system_design()

    records_map = {
        "knowledge":   kos_data["knowledge"],
        "patterns":    kos_data["patterns"],
        "decisions":   kos_data["decisions"],
        "tech_assets": kos_data["tech_assets"],
        "incidents":   kos_data["incidents"],
    }

    # id_maps accumulates as each DB syncs: {db_name: {kos_id: page_id}}
    id_maps: dict[str, dict] = {}

    for db_key in SYNC_ORDER:
        if target and db_key != target:
            # Even if skipping sync, we still need the id_map for downstream relations
            db_id = dbs.get(db_key)
            if db_id:
                id_maps[db_key] = build_id_map(notion, db_id)
            continue

        db_id = dbs.get(db_key)
        records = records_map[db_key]

        if not db_id:
            print(f"\n⚠  Skipping {db_key} — no database ID in config.json")
            continue
        if not records:
            print(f"\n⚠  Skipping {db_key} — no records parsed")
            continue

        try:
            id_maps[db_key] = SYNC_FNS[db_key](notion, db_id, records, id_maps, rebuild_body)
        except _NOTION_ERRORS as e:
            print(f"\n✗ Notion API error on {db_key}: {e}")

    # Pass 2: re-sync Knowledge with Patterns id_map to wire Related Patterns
    # (Patterns had to be created first before Knowledge can relate to them)
    if not target or target == "knowledge":
        k_db_id = dbs.get("knowledge")
        k_records = records_map["knowledge"]
        if k_db_id and k_records and id_maps.get("patterns"):
            print("\n🔁 Knowledge (pass 2) — wiring Related Patterns...")
            try:
                id_maps["knowledge"] = sync_knowledge(
                    notion, k_db_id, k_records, id_maps, rebuild_body
                )
            except _NOTION_ERRORS as e:
                print(f"\n✗ Notion API error on knowledge pass 2: {e}")

    # Pass 3: re-sync Patterns with Tech Assets id_map to wire Related Tech Assets
    # (Tech Assets had to be created first before Patterns can relate to them)
    if not target or target == "patterns":
        p_db_id = dbs.get("patterns")
        p_records = records_map["patterns"]
        if p_db_id and p_records and id_maps.get("tech_assets"):
            print("\n🔁 Patterns (pass 3) — wiring Related Tech Assets...")
            try:
                id_maps["patterns"] = sync_patterns(
                    notion, p_db_id, p_records, id_maps, rebuild_body
                )
            except _NOTION_ERRORS as e:
                print(f"\n✗ Notion API error on patterns pass 3: {e}")

    print("\n✅ Sync complete.")


if __name__ == "__main__":
    main()
