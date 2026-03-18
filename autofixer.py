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
    autofix_model = os.getenv("AUTOFIX_MODEL", os.getenv("AUDIT_MODEL", "gpt-5-mini"))
    fallback_model = os.getenv("AUTOFIX_FALLBACK_MODEL", os.getenv("AUDIT_FALLBACK_MODEL", "gpt-4o-mini"))
    candidate_models = [autofix_model]
    if fallback_model and fallback_model not in candidate_models:
        candidate_models.append(fallback_model)

    last_exc: Exception | None = None
    for candidate_model in candidate_models:
        try:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model=candidate_model,
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
                timeout=60,
            )
            payload = json.loads(response.choices[0].message.content or "{}")
            fixed_code = payload.get("fixed_code")
            if isinstance(fixed_code, str) and fixed_code.strip():
                return {"fixed_code": fixed_code, "error": None}
        except Exception as exc:
            last_exc = exc
            continue

    if last_exc:
        return {"fixed_code": original_code, "error": f"Autofix failed: {last_exc}"}
    return {"fixed_code": original_code, "error": "Autofix did not return usable code."}

