# fact-check
Description: Evaluate whether a specific factual claim is likely to be true, false, or uncertain.

## Input

A factual claim to be evaluated, e.g.
"Python was first released in 1991" or "The Eiffel Tower is in Berlin".

## Instructions

1. Identify the core factual assertion in the claim.
2. Reason through what you know about the subject.
3. Assess whether the claim is true, false, or uncertain/contested.
4. Explain your reasoning in 2-3 sentences.
5. Assign a confidence level: high / medium / low.

## Output Format

**Verdict:** true | false | uncertain

**Reasoning:** <2-3 sentences>

**Confidence:** high | medium | low

**Note:** <any important context or caveats>

## Constraints

- Base your assessment on well-established facts only.
- Flag anything where your knowledge may be outdated.
- Never fabricate sources or citations.
