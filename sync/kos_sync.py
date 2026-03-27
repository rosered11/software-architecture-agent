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
    from notion_client.errors import APIResponseError
except ImportError:
    print("ERROR: notion-client not installed. Run: pip install notion-client")
    sys.exit(1)

# ── Paths ────────────────────────────────────────────────────────────────────

ROOT         = Path(__file__).parent.parent
CONFIG_PATH  = Path(__file__).parent / "config.json"
KOS_SD_PATH  = ROOT / "skills/software-architecture-specialist/references/kos-system-design.md"
INCIDENT_PATH= ROOT / "skills/software-architecture-specialist/references/incident-log.md"

# ── Config ───────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"ERROR: {CONFIG_PATH} not found.")
        print("  Copy sync/config.example.json → sync/config.json and fill in your values.")
        sys.exit(1)
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

# ── Parsers ──────────────────────────────────────────────────────────────────

def parse_kv_block(block_text: str) -> dict:
    """
    Parse aligned 'Key:   Value' pairs from a KOS code block.
    Handles multi-line values where continuation lines are indented.
    """
    fields: dict = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in block_text.split("\n"):
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


def _join_value(lines: list[str]) -> str:
    """Join value lines, collapsing empty tail lines."""
    return "\n".join(lines).strip()


def extract_code_block(section_text: str) -> str | None:
    """Extract content between first ``` and last ``` in a section."""
    m = re.search(r"```\n(.*?)```", section_text, re.DOTALL)
    return m.group(1) if m else None


def parse_kos_system_design() -> dict[str, list[dict]]:
    """
    Parse kos-system-design.md into records grouped by type:
    knowledge (K), patterns (P), decisions (D), tech_assets (TA)
    """
    text = KOS_SD_PATH.read_text(encoding="utf-8")
    result: dict[str, list[dict]] = {
        "knowledge": [],
        "patterns": [],
        "decisions": [],
        "tech_assets": [],
    }

    # Split on section headers (### K1:, ### P1:, ### D1:, ### TA1:)
    sections = re.split(r"\n(?=### (?:K|P|D|TA)\d+:)", text)

    for section in sections:
        header_m = re.match(r"### (K|P|D|TA)(\d+):\s+(.+)", section)
        if not header_m:
            continue

        prefix   = header_m.group(1)   # K / P / D / TA
        number   = header_m.group(2)
        title    = header_m.group(3).strip()
        kos_id   = f"{prefix}{number}"

        block_text = extract_code_block(section)
        if not block_text:
            continue

        fields = parse_kv_block(block_text)
        fields["_id"]    = kos_id
        fields["_title"] = fields.get("Title") or fields.get("Name") or title

        db_map = {"K": "knowledge", "P": "patterns", "D": "decisions", "TA": "tech_assets"}
        result[db_map[prefix]].append(fields)

    return result


def parse_incident_log() -> list[dict]:
    """
    Parse incident-log.md — extracts the overview table fields for each incident.
    """
    text = INCIDENT_PATH.read_text(encoding="utf-8")
    incidents = []
    index = 1

    # Find each incident section
    for section in re.split(r"\n## \d+\.", text)[1:]:
        # Title from first line
        title_m = re.match(r"\s*(.+)", section)
        title = title_m.group(1).strip() if title_m else f"Incident {index}"

        # Overview table: | Field | Value |
        overview: dict = {}
        for row in re.finditer(r"\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|", section):
            overview[row.group(1).strip()] = row.group(2).strip()

        # Symptoms section
        symptoms_m = re.search(r"### Symptoms\n(.*?)(?=\n###)", section, re.DOTALL)
        symptoms = symptoms_m.group(1).strip() if symptoms_m else ""

        # Root Cause
        rc_m = re.search(r"### Root Cause\n(.*?)(?=\n###)", section, re.DOTALL)
        root_cause = rc_m.group(1).strip() if rc_m else ""

        # Lesson Learned
        lesson_m = re.search(r"### Lesson Learned\n(.*?)(?=\n###|\Z)", section, re.DOTALL)
        lesson = lesson_m.group(1).strip() if lesson_m else ""

        # Prevention checklist
        prevention_m = re.search(r"### Prevention\n(.*?)(?=\n###|\Z)", section, re.DOTALL)
        prevention = prevention_m.group(1).strip() if prevention_m else ""

        incidents.append({
            "_id":           f"I{index}",
            "_title":        title,
            "Title":         overview.get("Title", title),
            "Severity":      overview.get("Severity", ""),
            "System":        overview.get("System", ""),
            "Status":        overview.get("Status", ""),
            "Date":          overview.get("Date Identified", ""),
            "Problem":       symptoms[:2000],
            "Root Cause":    root_cause[:2000],
            "Lesson Learned":lesson[:2000],
            "Prevention":    prevention[:2000],
        })
        index += 1

    return incidents

# ── Notion Helpers ────────────────────────────────────────────────────────────

RATE_LIMIT_DELAY = 0.35   # seconds between API calls (~3 req/s)


def _rtext(value: str) -> dict:
    """Build a Notion rich_text property value (max 2000 chars)."""
    return {"rich_text": [{"type": "text", "text": {"content": value[:2000]}}]}


def _title(value: str) -> dict:
    return {"title": [{"type": "text", "text": {"content": value[:255]}}]}


def _select(value: str) -> dict:
    return {"select": {"name": value[:100]}} if value else {"select": None}


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


def record_to_blocks(record: dict) -> list:
    """Convert record fields to Notion paragraph blocks for the page body."""
    skip = {"_id", "_title", "Title", "Name"}
    blocks = []

    for key, value in record.items():
        if key in skip or not value:
            continue
        # Heading 3 for field name
        blocks.append({
            "object": "block", "type": "heading_3",
            "heading_3": {"rich_text": [{"type": "text", "text": {"content": key}}]},
        })
        # Paragraph for value (split every 2000 chars to avoid Notion limit)
        for chunk in _chunk(str(value), 2000):
            blocks.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]},
            })

    return blocks[:100]   # Notion allows max 100 children per request


def _chunk(text: str, size: int) -> list[str]:
    return [text[i:i+size] for i in range(0, len(text), size)] if text else []


def upsert_page(notion: Client, db_id: str, properties: dict, record: dict):
    """Create or update a Notion page. Returns ('created'|'updated', page_id)."""
    kos_id = record["_id"]
    existing_id = find_page(notion, db_id, kos_id)
    time.sleep(RATE_LIMIT_DELAY)

    if existing_id:
        notion.pages.update(page_id=existing_id, properties=properties)
        return "updated", existing_id
    else:
        page = notion.pages.create(
            parent={"database_id": db_id},
            properties=properties,
            children=record_to_blocks(record),
        )
        return "created", page["id"]

# ── Per-Database Sync ─────────────────────────────────────────────────────────

def sync_knowledge(notion: Client, db_id: str, records: list[dict]):
    print(f"\n📚 Knowledge — {len(records)} records → DB {db_id[:8]}...")
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
        action, _ = upsert_page(notion, db_id, props, r)
        print(f"  {'✓' if action == 'updated' else '+'} {action:7}  {r['_id']}: {r['_title']}")
        time.sleep(RATE_LIMIT_DELAY)


def sync_patterns(notion: Client, db_id: str, records: list[dict]):
    print(f"\n🧩 Patterns — {len(records)} records → DB {db_id[:8]}...")
    for r in records:
        props = {
            "Name":       _title(r["_title"]),
            "KOS ID":     _rtext(r["_id"]),
            "Category":   _select(r.get("Category", "")),
            "Complexity": _select(r.get("Complexity", "")),
            "Problem":    _rtext(r.get("Problem", "")),
        }
        action, _ = upsert_page(notion, db_id, props, r)
        print(f"  {'✓' if action == 'updated' else '+'} {action:7}  {r['_id']}: {r['_title']}")
        time.sleep(RATE_LIMIT_DELAY)


def sync_decisions(notion: Client, db_id: str, records: list[dict]):
    print(f"\n📋 Decision Log — {len(records)} records → DB {db_id[:8]}...")
    for r in records:
        props = {
            "Name":    _title(r["_title"]),
            "KOS ID":  _rtext(r["_id"]),
            "Context": _rtext(r.get("Context", "")),
            "Problem": _rtext(r.get("Problem", "")),
        }
        action, _ = upsert_page(notion, db_id, props, r)
        print(f"  {'✓' if action == 'updated' else '+'} {action:7}  {r['_id']}: {r['_title']}")
        time.sleep(RATE_LIMIT_DELAY)


def sync_tech_assets(notion: Client, db_id: str, records: list[dict]):
    print(f"\n🔧 Tech Assets — {len(records)} records → DB {db_id[:8]}...")
    for r in records:
        props = {
            "Name":     _title(r["_title"]),
            "KOS ID":   _rtext(r["_id"]),
            "Type":     _select(r.get("Type", "")),
            "Language": _select(r.get("Language", "")),
            "Usage":    _rtext(r.get("Usage", "")),
        }
        action, _ = upsert_page(notion, db_id, props, r)
        print(f"  {'✓' if action == 'updated' else '+'} {action:7}  {r['_id']}: {r['_title']}")
        time.sleep(RATE_LIMIT_DELAY)


def sync_incidents(notion: Client, db_id: str, records: list[dict]):
    print(f"\n🔴 Incidents — {len(records)} records → DB {db_id[:8]}...")
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
        action, _ = upsert_page(notion, db_id, props, r)
        print(f"  {'✓' if action == 'updated' else '+'} {action:7}  {r['_id']}: {r['_title']}")
        time.sleep(RATE_LIMIT_DELAY)

# ── Main ──────────────────────────────────────────────────────────────────────

DB_KEYS = {"k": "knowledge", "p": "patterns", "d": "decisions",
           "ta": "tech_assets", "i": "incidents"}

def main():
    parser = argparse.ArgumentParser(description="Sync KOS → Notion")
    parser.add_argument("--db", choices=list(DB_KEYS.keys()),
                        help="Sync only this database (default: all)")
    args = parser.parse_args()

    config  = load_config()
    token   = config["notion_token"]
    dbs     = config["databases"]
    notion  = Client(auth=token)

    target = DB_KEYS.get(args.db) if args.db else None

    print("🔄 KOS → Notion Sync")
    print(f"   Target: {target or 'all databases'}")

    # Parse source files
    kos_data = parse_kos_system_design()
    incidents = parse_incident_log()

    sync_map = {
        "knowledge":   (sync_knowledge,   dbs.get("knowledge"),   kos_data["knowledge"]),
        "patterns":    (sync_patterns,    dbs.get("patterns"),    kos_data["patterns"]),
        "decisions":   (sync_decisions,   dbs.get("decisions"),   kos_data["decisions"]),
        "tech_assets": (sync_tech_assets, dbs.get("tech_assets"), kos_data["tech_assets"]),
        "incidents":   (sync_incidents,   dbs.get("incidents"),   incidents),
    }

    for db_key, (fn, db_id, records) in sync_map.items():
        if target and db_key != target:
            continue
        if not db_id:
            print(f"\n⚠  Skipping {db_key} — no database ID in config.json")
            continue
        if not records:
            print(f"\n⚠  Skipping {db_key} — no records parsed")
            continue
        try:
            fn(notion, db_id, records)
        except APIResponseError as e:
            print(f"\n✗ Notion API error on {db_key}: {e}")

    print("\n✅ Sync complete.")


if __name__ == "__main__":
    main()
