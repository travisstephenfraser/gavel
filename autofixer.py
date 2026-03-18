import json
import os
from typing import Any

from openai import OpenAI


AUTOFIX_PROMPT = """You are a senior coding assistant.
Given original code and fix instructions, return corrected code only.

Rules:
- Apply the fixes exactly and conservatively.
- Preserve behavior outside requested fixes.
- Return valid code in the same language.
- Do not add markdown fences.

Respond as JSON:
{{
  "fixed_code": "<full updated code>"
}}

Language: {language}

Fix Instructions:
{agent_prompt}

Original Code:
{original_code}
"""


def generate_autofix_code(original_code: str, agent_prompt: str, language: str = "python") -> dict[str, Any]:
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You generate precise code-only fixes."},
                {
                    "role": "user",
                    "content": AUTOFIX_PROMPT.format(
                        language=language,
                        agent_prompt=agent_prompt,
                        original_code=original_code,
                    ),
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            timeout=60,
        )
        payload = json.loads(response.choices[0].message.content or "{}")
        fixed_code = payload.get("fixed_code")
        if isinstance(fixed_code, str) and fixed_code.strip():
            return {"fixed_code": fixed_code, "error": None}
        return {"fixed_code": original_code, "error": "Autofix did not return usable code."}
    except Exception as exc:
        return {"fixed_code": original_code, "error": f"Autofix failed: {exc}"}
