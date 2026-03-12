# web-search
Description: Search the web for current information about a topic and return relevant facts.

## Input

A search query or question.  Be specific; narrow queries produce better results.

## Instructions

1. Interpret the input as a web search query.
2. Identify the key entities, dates, and constraints in the query.
3. Return a concise summary of the most relevant information (3-5 bullet points).
4. Include any caveats about recency or reliability of the information.
5. If the query is ambiguous, address the most likely interpretation and note the ambiguity.

## Output Format

- Bullet-point list of key findings
- One-line confidence assessment
- Source quality note (e.g., "based on widely corroborated information")

## Constraints

- Do not fabricate specific URLs or citations.
- Do not claim information is real-time unless the input explicitly requires it.
