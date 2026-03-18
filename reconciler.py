from typing import Any
import difflib


def confidence_for_scores(primary_score: int | None, audit_score: int | None) -> tuple[str, int | None]:
    if primary_score is None or audit_score is None:
        return "LOW", None

    score_gap = abs(primary_score - audit_score)
    if score_gap == 0:
        confidence = "HIGH"
    elif score_gap == 1:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"
    return confidence, score_gap


def compute_overall_score(primary_results: dict[str, dict[str, Any]]) -> float | None:
    scores = [result.get("score") for result in primary_results.values() if result.get("score") is not None]
    if not scores:
        return None
    return round(sum(scores) / len(scores), 2)


def compute_audit_agreement(
    primary_results: dict[str, dict[str, Any]], audit_results: dict[str, dict[str, Any]]
) -> float | None:
    comparisons = []
    for dim_name, primary in primary_results.items():
        audit = audit_results.get(dim_name, {})
        p_score = primary.get("score")
        a_score = audit.get("score")
        if p_score is None or a_score is None:
            continue
        comparisons.append(1 if abs(p_score - a_score) <= 1 else 0)

    if not comparisons:
        return None
    return round((sum(comparisons) / len(comparisons)) * 100, 2)


def compute_exact_score_agreement(dimensions: list[dict[str, Any]]) -> float | None:
    comparisons = []
    for dim in dimensions:
        p_score = dim.get("primary_score")
        a_score = dim.get("audit_score")
        if p_score is None or a_score is None:
            continue
        comparisons.append(1 if p_score == a_score else 0)
    if not comparisons:
        return None
    return round((sum(comparisons) / len(comparisons)) * 100, 2)


def _findings_match(primary_findings: list[dict[str, Any]], audit_findings: list[dict[str, Any]]) -> bool:
    if not primary_findings and not audit_findings:
        return True
    if not primary_findings or not audit_findings:
        return False

    primary_lines = {f.get("line") for f in primary_findings if isinstance(f.get("line"), int)}
    audit_lines = {f.get("line") for f in audit_findings if isinstance(f.get("line"), int)}
    if primary_lines and audit_lines and primary_lines.intersection(audit_lines):
        return True

    primary_issues = [str(f.get("issue", "")).strip().lower() for f in primary_findings if f.get("issue")]
    audit_issues = [str(f.get("issue", "")).strip().lower() for f in audit_findings if f.get("issue")]
    for p_issue in primary_issues:
        for a_issue in audit_issues:
            if difflib.SequenceMatcher(None, p_issue, a_issue).ratio() >= 0.55:
                return True
    return False


def compute_finding_overlap(dimensions: list[dict[str, Any]]) -> float | None:
    if not dimensions:
        return None

    comparisons = []
    for dim in dimensions:
        primary_findings = dim.get("primary_findings", []) or []
        audit_findings = dim.get("audit_findings", []) or []
        comparisons.append(1 if _findings_match(primary_findings, audit_findings) else 0)

    if not comparisons:
        return None
    return round((sum(comparisons) / len(comparisons)) * 100, 2)
