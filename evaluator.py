import json
import os
from typing import Any

from openai import OpenAI

from prompts import AUDIT_PROMPT, PRIMARY_EVALUATOR_PROMPT


def add_line_numbers(code: str) -> str:
    lines = code.strip("\n").split("\n")
    return "\n".join(f"{i + 1}: {line}" for i, line in enumerate(lines))


def run_eval(code: str, dimension: tuple[str, str], model: str) -> dict[str, Any]:
    dimension_name, dimension_description = dimension
    code_with_line_numbers = add_line_numbers(code)
    prompt_template = PRIMARY_EVALUATOR_PROMPT if model == "gpt-4o" else AUDIT_PROMPT
    prompt = prompt_template.format(
        dimension_name=dimension_name,
        dimension_description=dimension_description,
        code=code_with_line_numbers,
    )

    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a precise code evaluator."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
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
        return {
            "dimension": dimension_name,
            "score": None,
            "justification": f"Eval failed: {exc}",
            "findings": [],
        }
