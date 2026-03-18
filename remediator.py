import json
import os
from typing import Any

from openai import OpenAI

from evaluator import add_line_numbers
from prompts import REMEDIATION_PROMPT


def generate_remediation(
    code: str, primary_findings_by_dimension: dict[str, list[dict[str, Any]]], audit_findings_by_dimension: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    code_with_line_numbers = add_line_numbers(code)
    prompt = REMEDIATION_PROMPT.format(
        primary_findings_json=json.dumps(primary_findings_by_dimension, indent=2),
        audit_findings_json=json.dumps(audit_findings_by_dimension, indent=2),
        code_with_line_numbers=code_with_line_numbers,
    )

    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a precise code remediation specialist."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
            timeout=60,
        )
        return json.loads(response.choices[0].message.content or "{}")
    except Exception as exc:
        return {
            "issues": [],
            "agent_prompt": f"Remediation generation failed: {exc}",
        }
