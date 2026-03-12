# summarize
Description: Condense a long piece of text into a clear, structured summary.

## Input

Raw text, a passage, or a description of a document to be summarised.

## Instructions

1. Identify the main claim or purpose of the text.
2. Extract the 3-7 most important supporting points.
3. Note any significant caveats or contradictions within the text.
4. Produce a summary at roughly 20% of the original length, preserving all
   essential meaning.
5. If the input is very short (< 100 words), return it unchanged with a note.

## Output Format

**Summary:** <2-4 sentence overview>

**Key points:**
- …

**Caveats / gaps:** <or "none">

## Constraints

- Do not add information that is not present in the input.
- Do not omit statements that contradict the main claim.
