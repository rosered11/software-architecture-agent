---
name: Notion KOS Sync Standard
description: Always apply the established rendering and sync format when adding or updating any KOS record (I, K, P, D, TA) that syncs to Notion
type: feedback
---

Always follow this sync standard for all KOS records. Never skip or simplify these rules.

**Why:** User explicitly established this standard after multiple sessions of incremental improvements to `sync/kos_sync.py` and `kos-tech-assets.md`. Any regression breaks readability in Notion.

**How to apply:** Any time a KOS record is created, updated, or a sync is run, verify all rules below are met.

---

## KOS File Rules

### Snippet label (Tech Assets + Patterns with inline code)
Every TA and P record that contains a code snippet MUST have a language-appropriate label before the code inside the KV block:
- SQL → `-- Snippet:`
- C# / Go → `// Snippet:`
- Python → `# Snippet:`

Without the label, `extract_snippet()` cannot find the code and Notion receives nothing.

### Pattern records — below-KV content
Patterns (P#) have rich markdown below their KV block (`**Trade-offs**`, `**Decision Rule**`, `**Your Stack**`, etc.).
This content is extracted automatically by `extract_pattern_rich_content()` in `sync/kos_sync.py`.
Never move this content out of the section or change the `**Heading**:` format — the parser depends on it.
Any `**Custom Heading**:` section below the KV block is also promoted as a named field automatically.

---

## Notion Page Body Rendering Rules (enforced in `kos_sync.py`)

| Content type | Renders as |
|---|---|
| `Snippet` field | Code block with syntax highlighting + [Copy] button |
| `→ item` lines | Bulleted list item |
| `Pros: text` / `Cons: text` lines | **Pros:** / **Cons:** bold-labeled bullet |
| `When to Use`, `When NOT to Use` field lines | Bullet list (one bullet per line) |
| `Rules`, `Decision Rule` field lines | Bullet list (one bullet per line) |
| Markdown `\| table \|` rows | Notion table with column headers |
| ALL-CAPS heading ending in `:` | heading_3 |
| Numbered `1. item` lines | Numbered list |
| `A. option` lines | Bulleted list |
| Pattern `**Trade-offs**:` table | Notion table |
| Pattern `**Your Stack**:` code | Code block (Snippet + Language fields) |
| `**bold**` inline markup | Notion bold annotation |
| `` `backtick` `` inline markup | Notion inline-code annotation |

## Fields skipped from page body (already in DB properties)
`Type`, `Domain`, `Difficulty`, `Category`, `Complexity`, `Language`, `Stack Language`

## Block limit
200 blocks per page (never truncate rich records like K1 Deep Dive or I1 root cause).

## Snippet chunking
Snippets > 2000 chars are split into multiple `rich_text` segments within one code block — never use `value[:2000]` truncation.

---

## Sync Commands

```bash
# Sync all databases
python sync/kos_sync.py

# Sync one database only
python sync/kos_sync.py --db ta     # tech assets
python sync/kos_sync.py --db p      # patterns
python sync/kos_sync.py --db k      # knowledge
python sync/kos_sync.py --db d      # decisions
python sync/kos_sync.py --db i      # incidents

# Rebuild page bodies (apply rendering changes to existing pages)
python sync/kos_sync.py --rebuild-body
python sync/kos_sync.py --db p --rebuild-body
```
