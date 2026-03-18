import json
import os
import re
from typing import Any

from openai import OpenAI

from evaluator import add_line_numbers
from prompts import REMEDIATION_PROMPT

SEVERITY_ORDER = {"critical": 0, "major": 1, "minor": 2}


def _downgrade_severity(severity: str) -> str:
    if severity == "critical":
        return "major"
    if severity == "major":
        return "minor"
    return severity


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _is_demo_dismissable_issue(dimension: str, finding: str, fix: str) -> bool:
    dim = (dimension or "").strip().lower()
    text = f"{finding} {fix}".lower()

    hardcoded_path_signals = [
        "hard-code",
        "hardcoded",
        "relative sqlite database path",
        "app.db",
        "db_path",
        "working directory",
        "deploy/test flexibility",
    ]

    is_hardcoded_path_issue = any(signal in text for signal in hardcoded_path_signals)
    is_non_security_dimension = dim in {"robustness", "readability", "general"}
    return is_hardcoded_path_issue and is_non_security_dimension


def _normalize_and_filter_issues(
    issues: list[dict[str, Any]],
    dimension_meta: dict[str, dict[str, Any]] | None = None,
    max_issues_per_dimension: int = 3,
    max_total_issues: int = 8,
) -> list[dict[str, Any]]:
    dimension_meta = dimension_meta or {}
    normalized: list[dict[str, Any]] = []

    for raw in issues:
        dimension = _normalize_text(raw.get("dimension"))
        severity = _normalize_text(raw.get("severity")).lower()
        if severity not in {"critical", "major", "minor"}:
            severity = "minor"

        line = raw.get("line")
        if not isinstance(line, int):
            line = None

        both_flagged = bool(raw.get("both_flagged", False))
        confidence = _normalize_text(raw.get("confidence")).upper() or "LOW"
        if confidence not in {"HIGH", "MEDIUM", "LOW"}:
            confidence = "LOW"

        finding = _normalize_text(raw.get("finding"))
        fix = _normalize_text(raw.get("fix"))
        if not finding or not fix:
            continue

        meta = dimension_meta.get(dimension, {})
        dim_conf = str(meta.get("confidence", confidence)).upper()
        primary_score = meta.get("primary_score")

        # Deterministic anti-noise rule for beginner-friendly output.
        if severity in {"major", "critical"} and not both_flagged:
            if dim_conf != "HIGH" or (isinstance(primary_score, (int, float)) and primary_score >= 4):
                severity = _downgrade_severity(severity)
        # Demo-only noise trimming: deprioritize hard-coded local DB path/configurability warnings.
        if severity in {"major", "critical"} and _is_demo_dismissable_issue(dimension, finding, fix):
            severity = "minor"

        normalized.append(
            {
                "dimension": dimension or "General",
                "severity": severity,
                "line": line,
                "finding": finding,
                "fix": fix,
                "confidence": dim_conf if dim_conf in {"HIGH", "MEDIUM", "LOW"} else confidence,
                "both_flagged": both_flagged,
            }
        )

    deduped: dict[tuple[str, int | None, str], dict[str, Any]] = {}
    for issue in normalized:
        key = (
            issue["dimension"],
            issue["line"],
            re.sub(r"[^a-z0-9 ]+", "", issue["finding"].lower())[:100],
        )
        existing = deduped.get(key)
        if not existing or SEVERITY_ORDER[issue["severity"]] < SEVERITY_ORDER[existing["severity"]]:
            deduped[key] = issue

    final = list(deduped.values())
    final.sort(
        key=lambda i: (
            SEVERITY_ORDER.get(i.get("severity", "minor"), 2),
            i.get("dimension", ""),
            i.get("line") if isinstance(i.get("line"), int) else 10**9,
        )
    )

    per_dim_counts: dict[str, int] = {}
    trimmed: list[dict[str, Any]] = []
    for issue in final:
        dim = issue["dimension"]
        if per_dim_counts.get(dim, 0) >= max_issues_per_dimension:
            continue
        if len(trimmed) >= max_total_issues:
            break
        trimmed.append(issue)
        per_dim_counts[dim] = per_dim_counts.get(dim, 0) + 1

    return trimmed


def _build_agent_prompt_from_issues(issues: list[dict[str, Any]], code_with_line_numbers: str) -> str:
    if not issues:
        return "Fix the following issues in this code:\n\nNo actionable issues found."

    lines = ["Fix the following issues in this code:", ""]
    for idx, issue in enumerate(issues, start=1):
        line = issue.get("line")
        line_hint = f" (line {line})" if isinstance(line, int) else ""
        lines.append(
            f"{idx}. [{issue.get('dimension')}/{issue.get('severity').upper()}]{line_hint} {issue.get('fix')}"
        )

    lines.append("")
    lines.append("Original code:")
    lines.append(code_with_line_numbers)
    return "\n".join(lines)


def generate_remediation(
    code: str,
    primary_findings_by_dimension: dict[str, list[dict[str, Any]]],
    audit_findings_by_dimension: dict[str, list[dict[str, Any]]],
    dimension_meta: dict[str, dict[str, Any]] | None = None,
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
            payload = json.loads(response.choices[0].message.content or "{}")
            raw_issues = payload.get("issues", [])
            normalized_issues = _normalize_and_filter_issues(raw_issues, dimension_meta=dimension_meta)
            payload["issues"] = normalized_issues
            payload["agent_prompt"] = _build_agent_prompt_from_issues(normalized_issues, code_with_line_numbers)
            return payload
        except Exception as exc:
            last_exc = exc
            continue

    return {
        "issues": [],
        "agent_prompt": f"Remediation generation failed: {last_exc}",
    }
