import json
import os
from typing import Any, Iterable

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


def _can_compile(code: str, language: str) -> tuple[bool, str | None]:
    if (language or "").lower() != "python":
        return True, None
    try:
        compile(code, "<autofix>", "exec")
        return True, None
    except Exception as exc:
        return False, f"Compile check failed: {exc}"


def _build_stage_prompt(issues: Iterable[dict[str, Any]], stage_name: str) -> str:
    lines = [
        f"Apply only the {stage_name.upper()} issues listed below.",
        "Keep behavior stable outside these fixes.",
        "Preserve clear outcome semantics where relevant: success, not-found, and failure should remain distinguishable.",
        "",
    ]
    count = 0
    for count, issue in enumerate(issues, start=1):
        line = issue.get("line")
        line_hint = f" (line {line})" if isinstance(line, int) else ""
        fix = str(issue.get("fix") or "").strip()
        if fix:
            lines.append(f"{count}. {fix}{line_hint}")
    if count == 0:
        return ""
    return "\n".join(lines)


def _issues_for_stage(issues: list[dict[str, Any]], severity: str) -> list[dict[str, Any]]:
    return [issue for issue in issues if str(issue.get("severity", "")).lower() == severity]


def generate_staged_autofix_code(
    original_code: str,
    remediation_issues: list[dict[str, Any]],
    language: str = "python",
) -> dict[str, Any]:
    current_code = original_code
    stage_notes: list[str] = []

    for stage in ("critical", "major"):
        stage_issues = _issues_for_stage(remediation_issues, stage)
        if not stage_issues:
            stage_notes.append(f"{stage.title()}: no issues.")
            continue

        stage_prompt = _build_stage_prompt(stage_issues, stage)
        if not stage_prompt:
            stage_notes.append(f"{stage.title()}: no usable fix instructions.")
            continue

        result = generate_autofix_code(current_code, stage_prompt, language=language)
        if result.get("error"):
            stage_notes.append(f"{stage.title()}: skipped ({result['error']}).")
            continue

        candidate_code = str(result.get("fixed_code") or current_code)
        valid, compile_error = _can_compile(candidate_code, language)
        if not valid:
            stage_notes.append(f"{stage.title()}: rejected ({compile_error}).")
            continue

        current_code = candidate_code
        stage_notes.append(f"{stage.title()}: applied.")

    final_valid, final_compile_error = _can_compile(current_code, language)
    if not final_valid:
        return {
            "fixed_code": original_code,
            "error": final_compile_error or "Compile check failed.",
            "stage_notes": stage_notes,
        }

    return {
        "fixed_code": current_code,
        "error": None,
        "stage_notes": stage_notes,
    }
