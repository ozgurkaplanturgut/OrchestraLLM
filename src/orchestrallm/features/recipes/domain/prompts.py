# src/orchestrallm/features/recipes/domain/prompts.py

RECIPE_RECOMMENDER_PROMPT = """
GOAL: Suggest EXACTLY 3 dishes that match the user's request.
FORMAT REQUIREMENTS:
1) Return ONLY a JSON code block (no extra text).
2) JSON schema:

{
  "dishes": [
    {"name": "...", "summary": "..."},
    {"name": "...", "summary": "..."},
    {"name": "...", "summary": "..."}
  ]
}

3) Do not add anything outside the JSON block. The list MUST contain exactly 3 items.
4) Write in the same language as the user’s request (if the user writes in English, reply in English).
"""

RECIPE_WRITER_PROMPT = """
TASK: For each dish in the JSON above, write the FULL recipe.
FORMAT REQUIREMENTS:
- Use the following structure for each dish (Markdown):

### {name} Recipe

#### Ingredients:
- ...

#### Instructions:
1. ...
2. ...

- Ingredients should have quantities and units where possible.
- Steps should be clear and concise.
- Produce this block for exactly 3 dishes.
- Write in the same language as the user’s request (if the user writes in English, reply in English).
"""
