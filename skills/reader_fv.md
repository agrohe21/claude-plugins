# reader-fv
Description: Translate a natural-language description into a valid Readwise Reader Filtered View (FV) query string ready to paste into Reader.

## Input

A plain-English description of the documents the user wants to see. Examples:
- "articles I haven't started about AI"
- "long PDFs saved this week"
- "everything tagged 'finance' in my shortlist"

---

## Reference: Filtered View Syntax

### Boolean Logic

| Concept | Syntax | Example |
|---|---|---|
| AND | `AND` | `tag:news AND published__after:"1 week ago"` |
| OR | `OR` | `tag:news OR tag:tech` |
| Grouping | `(…)` | `(tag:one OR tag:two) AND saved__after:"2 weeks ago"` |

### Operators (double-underscore suffix on a field)

| Operator | Type | Meaning |
|---|---|---|
| `__gt` | Numeral | Greater than |
| `__lt` | Numeral | Less than |
| `__gte` | Numeral | Greater than or equal |
| `__lte` | Numeral | Less than or equal |
| `__contains` | Text | Contains the text anywhere |
| `__exact` | Text | Exact match |
| `__before` | Date | Earlier than the date |
| `__after` | Date | Later than the date |
| `__not` | Any | Does not equal / does not contain |

Example: `highlights__gt:5`, `title__contains:"machine learning"`, `saved__after:"1 week ago"`

### Date Format

- **Relative**: quoted string — `"1 day ago"`, `"1 week ago"`, `"2 weeks ago"`, `"1 month ago"`
- **Absolute**: ISO date — `2024-09-15`
- Always pair with `__before` or `__after`: `saved__after:"1 week ago"`

### Date Parameters

| Field | Filters by |
|---|---|
| `saved` | Date document was saved |
| `last_opened` | Date document was most recently opened |
| `published` | Date document was published |
| `last_status` | Date of most recent action (e.g. moved to archive) |

### Text Parameters

| Field | Filters by | Notes |
|---|---|---|
| `tag` | Tag(s) applied to the document | Multi-word values in quotes |
| `domain` | Source domain | e.g. `nytimes.com`, `youtube.com` |
| `url` | Full URL of the document | |
| `category` or `type` | Document type | See Category values |
| `rss_source` | RSS feed name | Only works on RSS-added docs |
| `author` | Author name | Multi-word values in quotes |
| `location` or `in` | Current location in library | See Location values |
| `title` | Document title | Multi-word values in quotes |
| `saved_using` | Import source | `instapaper`, `pocket`, `omnivore`, `matter` |

Multi-word text values must be quoted: `title__contains:"machine learning"`, `author:"Paul Graham"`

### Category Values

`article` · `epub` · `email` · `pdf` · `tweet` · `rss` · `video` · `podcast`

### Location Values

Default (Triage) config: `inbox` · `later` · `archive`
Shortlist config: `later` · `shortlist` · `archive`

### Binary Parameters (true / false)

| Field | Filters by |
|---|---|
| `feed` | Whether document is in the feed |
| `seen` | Whether document has been opened or marked seen |
| `unseen` | Whether document has NOT been opened or marked seen |
| `shared` | Whether document has a public link enabled |

Example: `seen:false`, `shared:true`

### Numerical Parameters

| Field | Filters by |
|---|---|
| `words` | Word count |
| `progress` | Reading progress (0–100) |
| `highlights` | Number of highlights made |
| `minutes` | Estimated reading time |
| `saved_count` | Number of times saved |

Always use with a numeral operator: `words__gt:5000`, `progress__lt:100`

### `has` Parameter

Filters by presence of annotations:
- `has:highlights` — at least one highlight
- `has:tags` — at least one tag
- `has:notes` — content in the document note field

---

## Instructions

1. Identify the constraints in the user's request:
   - **Content**: topics, tags, authors, domains, keywords in title
   - **Type**: document category (`category:`)
   - **State**: location, read progress, seen/unseen, highlights
   - **Time**: when saved, published, last opened, or last acted on
   - **Size**: word count, reading time

2. Map each constraint to the correct field and operator from the reference above.
   - Numerical comparisons → `field__gt/lt/gte/lte:value`
   - Date ranges → `field__after/before:"relative"` or `field__after/before:2024-01-01`
   - Text matching → `field:value` (equality) or `field__contains:value` (partial match)
   - Negation → `field__not:value`

3. Combine constraints with `AND` (explicit) or `OR`. Use parentheses to group OR clauses before ANDing.

4. Use the minimal query that fully captures the request.

5. Wrap multi-word values in double quotes.

6. If the request is ambiguous, output the most likely query and state the assumption.

7. Never invent field names, operators, or values not in the reference above.

---

## Output Format

```
**Query:**
`<filter query>`

**What it matches:** <one-sentence plain-English description>

**Assumptions:** <interpretations made, or "none">
```

If multiple interpretations are reasonable, show 2–3 variants labelled A / B / C.

---

## Examples

| Natural language | Query |
|---|---|
| Unread articles about AI | `category:article AND tag:ai AND progress:0` |
| Long PDFs saved this week | `category:pdf AND words__gt:5000 AND saved__after:"1 week ago"` |
| Everything in inbox not yet started | `location:inbox AND progress:0` |
| Articles by Paul Graham | `category:article AND author:"Paul Graham"` |
| Videos or podcasts tagged 'startup' | `(category:video OR category:podcast) AND tag:startup` |
| Saved in the last 2 weeks, not archived | `saved__after:"2 weeks ago" AND location__not:archive` |
| Articles with more than 5 highlights I haven't finished | `category:article AND highlights__gt:5 AND progress__lt:100` |
| Anything from nytimes.com in my inbox | `domain:nytimes.com AND location:inbox` |
| Documents published last month I haven't opened | `published__after:"1 month ago" AND unseen:true` |
