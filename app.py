import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Flask, redirect, render_template, request, url_for

from autofixer import generate_autofix_code, generate_staged_autofix_code
from database import (
    create_eval_run,
    get_eval_history,
    get_dimension_scores,
    get_eval_run,
    init_db,
    insert_dimension_score,
    update_eval_run,
)
from env_loader import load_env_file
from evaluator import run_eval
from prompts import DIMENSIONS
from reconciler import (
    compute_audit_agreement,
    compute_overall_score,
    confidence_for_scores,
)
from remediator import generate_remediation


app = Flask(__name__)
app.config["SECRET_KEY"] = "gavel-dev"
load_env_file()
init_db()

PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "gpt-5.4")
AUDIT_MODEL = os.getenv("AUDIT_MODEL", "gpt-5-mini")
REMEDIATION_MODEL = os.getenv("REMEDIATION_MODEL", PRIMARY_MODEL)
AUTOFIX_MODEL = os.getenv("AUTOFIX_MODEL", AUDIT_MODEL)


@app.route("/", methods=["GET"])
def index():
    from_run_id = request.args.get("from_run_id", type=int)
    source_run = get_eval_run(from_run_id) if from_run_id else None
    auto_fix = request.args.get("auto_fix", default=0, type=int) == 1
    prefilled_code = source_run.get("code_input", "") if source_run else ""
    autofix_message = None
    if source_run and auto_fix:
        remediation_payload = {}
        try:
            remediation_payload = json.loads(source_run.get("remediation_json") or "{}")
        except json.JSONDecodeError:
            remediation_payload = {}

        remediation_issues = remediation_payload.get("issues") or []
        if isinstance(remediation_issues, list) and remediation_issues:
            fix_result = generate_staged_autofix_code(
                original_code=source_run.get("code_input", ""),
                remediation_issues=remediation_issues,
                language=source_run.get("language", "python"),
            )
        else:
            fix_result = generate_autofix_code(
                original_code=source_run.get("code_input", ""),
                agent_prompt=source_run.get("agent_prompt", ""),
                language=source_run.get("language", "python"),
            )
        prefilled_code = fix_result["fixed_code"]
        stage_notes = fix_result.get("stage_notes") or []
        stage_summary = f" ({' '.join(stage_notes)})" if stage_notes else ""
        autofix_message = (
            f"Auto-fix generated from remediation issues with compile gating.{stage_summary}"
            if not fix_result["error"]
            else f"{fix_result['error']} Showing original code instead.{stage_summary}"
        )

    return render_template(
        "index.html",
        source_run=source_run,
        prefilled_code=prefilled_code,
        autofix_message=autofix_message,
        primary_model=PRIMARY_MODEL,
        audit_model=AUDIT_MODEL,
        remediation_model=REMEDIATION_MODEL,
        autofix_model=AUTOFIX_MODEL,
    )


@app.route("/evaluate", methods=["POST"])
def evaluate():
    code_input = request.form["code_input"]
    language = request.form.get("language", "python")
    previous_eval_run_id = request.form.get("previous_eval_run_id", type=int)
    eval_run_id = create_eval_run(
        code_input=code_input,
        language=language,
        status="running",
        previous_eval_run_id=previous_eval_run_id,
    )

    with ThreadPoolExecutor(max_workers=8) as executor:
        primary_futures = {
            executor.submit(run_eval, code_input, dim, PRIMARY_MODEL, "primary"): ("primary", dim[0]) for dim in DIMENSIONS
        }
        audit_futures = {
            executor.submit(run_eval, code_input, dim, AUDIT_MODEL, "audit"): ("audit", dim[0]) for dim in DIMENSIONS
        }
        all_futures = {**primary_futures, **audit_futures}

        primary_results = {}
        audit_results = {}
        for future in as_completed(all_futures):
            role, dim_name = all_futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "dimension": dim_name,
                    "score": None,
                    "justification": f"Eval failed: {exc}",
                    "findings": [],
                }
            if role == "primary":
                primary_results[dim_name] = result
            else:
                audit_results[dim_name] = result

    primary_findings = {}
    audit_findings = {}
    dimension_meta = {}
    for dim_name, _desc in DIMENSIONS:
        primary = primary_results.get(dim_name, {"score": None, "justification": "Missing primary result", "findings": []})
        audit = audit_results.get(dim_name, {"score": None, "justification": "Missing audit result", "findings": []})
        confidence, score_gap = confidence_for_scores(primary.get("score"), audit.get("score"))
        dimension_meta[dim_name] = {
            "primary_score": primary.get("score"),
            "audit_score": audit.get("score"),
            "confidence": confidence,
            "score_gap": score_gap,
        }

        primary_findings[dim_name] = primary.get("findings", [])
        audit_findings[dim_name] = audit.get("findings", [])

        insert_dimension_score(
            eval_run_id=eval_run_id,
            dimension=dim_name,
            primary_score=primary.get("score"),
            primary_justification=primary.get("justification", ""),
            primary_findings=primary.get("findings", []),
            audit_score=audit.get("score"),
            audit_justification=audit.get("justification", ""),
            audit_findings=audit.get("findings", []),
            confidence=confidence,
            score_gap=score_gap,
        )

    remediation = generate_remediation(
        code_input,
        primary_findings,
        audit_findings,
        dimension_meta=dimension_meta,
    )
    overall_score = compute_overall_score(primary_results)
    audit_agreement = compute_audit_agreement(primary_results, audit_results)

    update_eval_run(
        eval_run_id,
        overall_score=overall_score,
        audit_agreement=audit_agreement,
        remediation_json=json.dumps(remediation),
        agent_prompt=remediation.get("agent_prompt", ""),
        status="completed",
    )

    return redirect(url_for("results", eval_run_id=eval_run_id))


@app.route("/history", methods=["GET"])
def history():
    runs = get_eval_history(limit=60)
    history_runs = []
    for run in runs:
        score = run.get("overall_score")
        if isinstance(score, (int, float)):
            score_pct = max(0, min(100, round((score / 5) * 100, 1)))
            if score >= 4:
                score_color = "bg-emerald-500"
                score_badge = "bg-emerald-100 text-emerald-700"
            elif score >= 3:
                score_color = "bg-amber-500"
                score_badge = "bg-amber-100 text-amber-700"
            else:
                score_color = "bg-red-500"
                score_badge = "bg-red-100 text-red-700"
        else:
            score_pct = 0
            score_color = "bg-slate-300"
            score_badge = "bg-slate-100 text-slate-700"

        agreement = run.get("audit_agreement")
        if isinstance(agreement, (int, float)):
            if agreement >= 90:
                agreement_badge = "bg-emerald-100 text-emerald-700"
            elif agreement >= 75:
                agreement_badge = "bg-amber-100 text-amber-700"
            else:
                agreement_badge = "bg-red-100 text-red-700"
        else:
            agreement_badge = "bg-slate-100 text-slate-700"

        run["score_pct"] = score_pct
        run["score_color"] = score_color
        run["score_badge"] = score_badge
        run["agreement_badge"] = agreement_badge
        history_runs.append(run)

    return render_template("history.html", runs=history_runs)


@app.route("/results/<int:eval_run_id>", methods=["GET"])
def results(eval_run_id: int):
    eval_run = get_eval_run(eval_run_id)
    if not eval_run:
        return "Run not found", 404

    dimensions = get_dimension_scores(eval_run_id)
    remediation = json.loads(eval_run.get("remediation_json") or '{"issues": [], "agent_prompt": ""}')
    severity_order = {"critical": 0, "major": 1, "minor": 2}
    remediation_issues = sorted(
        remediation.get("issues", []),
        key=lambda issue: (
            severity_order.get((issue.get("severity") or "").lower(), 3),
            issue.get("line") if isinstance(issue.get("line"), int) else 10**9,
        ),
    )

    previous_eval_run = None
    previous_dimensions = []
    score_deltas = {}
    overall_delta = None
    previous_eval_run_id = eval_run.get("previous_eval_run_id")
    if previous_eval_run_id:
        previous_eval_run = get_eval_run(previous_eval_run_id)
        if previous_eval_run:
            previous_dimensions = get_dimension_scores(previous_eval_run_id)
            previous_by_dimension = {dim["dimension"]: dim for dim in previous_dimensions}
            for dim in dimensions:
                prev = previous_by_dimension.get(dim["dimension"])
                current_score = dim.get("primary_score")
                prev_score = prev.get("primary_score") if prev else None
                if isinstance(current_score, int) and isinstance(prev_score, int):
                    score_deltas[dim["dimension"]] = current_score - prev_score
                else:
                    score_deltas[dim["dimension"]] = None
            current_overall = eval_run.get("overall_score")
            prev_overall = previous_eval_run.get("overall_score")
            if isinstance(current_overall, (int, float)) and isinstance(prev_overall, (int, float)):
                overall_delta = round(current_overall - prev_overall, 2)

    return render_template(
        "scorecard.html",
        eval_run=eval_run,
        dimensions=dimensions,
        remediation=remediation,
        remediation_issues=remediation_issues,
        previous_eval_run=previous_eval_run,
        previous_dimensions=previous_dimensions,
        score_deltas=score_deltas,
        overall_delta=overall_delta,
        primary_model=PRIMARY_MODEL,
        audit_model=AUDIT_MODEL,
        remediation_model=REMEDIATION_MODEL,
        autofix_model=AUTOFIX_MODEL,
    )


if __name__ == "__main__":
    app.run(debug=True)
