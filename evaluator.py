import json
import os
from typing import Any

from openai import OpenAI

from prompts import AUDIT_PROMPT, PRIMARY_EVALUATOR_PROMPT


def add_line_numbers(code: str) -> str:
    lines = code.strip("\n").split("\n")
    return "\n".join(f"{i + 1}: {line}" for i, line in enumerate(lines))


def run_eval(code: str, dimension: tuple[str, str], model: str, role: str = "primary") -> dict[str, Any]:
    dimension_name, dimension_description = dimension
    code_with_line_numbers = add_line_numbers(code)
    prompt_template = PRIMARY_EVALUATOR_PROMPT if role == "primary" else AUDIT_PROMPT
    prompt = prompt_template.format(
        dimension_name=dimension_name,
        dimension_description=dimension_description,
        code=code_with_line_numbers,
    )

    fallback_model = os.getenv("PRIMARY_FALLBACK_MODEL", "gpt-4o") if role == "primary" else os.getenv("AUDIT_FALLBACK_MODEL", "gpt-4o-mini")
    candidate_models = [model]
    if fallback_model and fallback_model not in candidate_models:
        candidate_models.append(fallback_model)

    last_exc: Exception | None = None
    for candidate_model in candidate_models:
        try:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model=candidate_model,
                messages=[
                    {"role": "system", "content": "You are a precise code evaluator."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                timeout=60,
            )
            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)
            return {
                "dimension": parsed.get("dimension", dimension_name),
                "score": parsed.get("score"),
                "justification": parsed.get("justification", ""),
                "findings": parsed.get("findings", []),
            }
        except Exception as exc:
            last_exc = exc
            continue

    return {
        "dimension": dimension_name,
        "score": None,
        "justification": f"Eval failed: {last_exc}",
        "findings": [],
    }

