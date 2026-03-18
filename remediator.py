import json
import os
from typing import Any

from openai import OpenAI

from evaluator import add_line_numbers
from prompts import REMEDIATION_PROMPT


def generate_remediation(
    code: str, primary_findings_by_dimension: dict[str, list[dict[str, Any]]], audit_findings_by_dimension: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    remediation_model = os.getenv("REMEDIATION_MODEL", os.getenv("PRIMARY_MODEL", "gpt-5.4"))
    code_with_line_numbers = add_line_numbers(code)
    prompt = REMEDIATION_PROMPT.format(
        primary_findings_json=json.dumps(primary_findings_by_dimension, indent=2),
        audit_findings_json=json.dumps(audit_findings_by_dimension, indent=2),
        code_with_line_numbers=code_with_line_numbers,
    )

    fallback_model = os.getenv("REMEDIATION_FALLBACK_MODEL", os.getenv("PRIMARY_FALLBACK_MODEL", "gpt-4o"))
    candidate_models = [remediation_model]
    if fallback_model and fallback_model not in candidate_models:
        candidate_models.append(fallback_model)

    last_exc: Exception | None = None
    for candidate_model in candidate_models:
        try:
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model=candidate_model,
                messages=[
                    {"role": "system", "content": "You are a precise code remediation specialist."},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                timeout=60,
            )
            return json.loads(response.choices[0].message.content or "{}")
        except Exception as exc:
            last_exc = exc
            continue

    return {
        "issues": [],
        "agent_prompt": f"Remediation generation failed: {last_exc}",
    }

