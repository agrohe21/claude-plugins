# reader-fv
Description: Translate a natural-language description into a valid Readwise Reader Filtered View (FV) query string ready to paste into Reader.

## Input

A plain-English description of the documents the user wants to see. Examples:
- "articles I haven't started about AI"
- "long PDFs saved this week"
- "everything tagged 'finance' in my shortlist"

## Reference: Filtered View Syntax

### Fields

| Field | Description | Example |
|---|---|---|
| `title:` | Title contains keyword | `title:python` |
| `author:` | Author name contains | `author:"Paul Graham"` |
| `tag:` | Has this tag (exact) | `tag:ai`, `tag:"machine learning"` |
| `category:` | Document type | see Category values |
| `location:` | Reading list bucket | see Location values |
| `site:` | Source domain | `site:nytimes.com` |
| `source:` | Feed/subscription name | `source:"Hacker News"` |
| `read_percent:` | Reading progress 0–100 | `read_percent:0`, `read_percent:>50` |
| `word_count:` | Word count | `word_count:>5000` |
| `saved:` | Date document was saved | `saved:today`, `saved:>2024-01-01` |
| `published:` | Publication date | `published:>-30d` |
| `last_opened:` | Date last opened | `last_opened:today` |
| `has:highlights` | Has at least one highlight | `has:highlights` |
| `has:notes` | Has at least one note | `has:notes` |

### Operators

| Syntax | Meaning |
|---|---|
| `field:value` | Equals / contains |
| `field:>value` | Greater than |
| `field:<value` | Less than |
| `field:>=value` | Greater than or equal |
| `field:<=value` | Less than or equal |
| `-field:value` | Negation (exclude) |

### Boolean Logic

- **AND** (implicit): space between terms → `tag:ai category:article`
- **OR** (explicit): `category:article OR category:pdf`
- **NOT**: `-tag:read` or `NOT tag:read`
- **Grouping**: `(category:article OR category:pdf) tag:finance`

### Date Values

| Value | Meaning |
|---|---|
| `today` | Current day |
| `yesterday` | Previous day |
| `last_week` | Previous 7 days |
| `last_month` | Previous 30 days |
| `-7d` | 7 days ago (use with `>`: `saved:>-7d`) |
| `-30d` | 30 days ago |
| `2024-01-15` | Absolute date (ISO format) |

### Category Values

`article` · `pdf` · `epub` · `tweet` · `video` · `rss`

### Location Values

`new` (inbox) · `later` · `shortlist` · `archive` · `feed`

---

## Instructions

1. Identify the constraints in the user's request:
   - **Content**: topics, tags, authors, sites, keywords in title
   - **Type**: document category
   - **State**: location, read progress, whether highlighted/noted
   - **Time**: when saved, published, or last opened
   - **Size**: word count

2. Map each constraint to the appropriate field and operator from the reference above.

3. Combine constraints using implicit AND (space), explicit OR, or negation (`-`).

4. Use the minimal query that fully captures the request — do not add constraints not implied by the input.

5. Wrap multi-word values in double quotes: `author:"Simon Willison"`.

6. If the request is ambiguous, output the most likely query and call out the assumption.

7. Never invent field names, operators, or values not in the reference above.

## Output Format

```
**Query:**
`<filter query>`

**What it matches:** <one-sentence plain-English description>

**Assumptions:** <interpretations made, or "none">
```

If multiple interpretations are reasonable, show 2–3 variants labelled A / B / C.

## Examples

| Natural language | Query |
|---|---|
| Unread articles about AI | `category:article tag:ai read_percent:0` |
| Long PDFs saved this week | `category:pdf word_count:>5000 saved:>last_week` |
| Everything in shortlist not yet started | `location:shortlist read_percent:0` |
| Articles by Paul Graham | `category:article author:"Paul Graham"` |
| Videos or tweets tagged 'startup' | `(category:video OR category:tweet) tag:startup` |
| Saved in the last 7 days, not archived | `saved:>-7d -location:archive` |
| Articles with highlights I haven't finished | `category:article has:highlights read_percent:<100` |
| Anything from nytimes.com in my inbox | `site:nytimes.com location:new` |
