# compare
Description: Compare two or more items, concepts, or options across relevant dimensions.

## Input

A comparison request, e.g.
"Compare Python and Rust for systems programming" or
"Compare approach A and approach B: <description of each>".

## Instructions

1. Identify the items being compared.
2. Determine 3-5 relevant comparison dimensions based on the context.
3. Evaluate each item on each dimension concisely.
4. State which item performs better overall and why, with a caveat about
   use-case dependence where appropriate.

## Output Format

| Dimension | Item A | Item B |
|-----------|--------|--------|
| …         | …      | …      |

**Overall:** <one-sentence recommendation with use-case caveat>

## Constraints

- Be objective; do not pick a winner without justification.
- Include at least one dimension where each item has an advantage.
