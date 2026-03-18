import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Flask, redirect, render_template, request, url_for

from autofixer import generate_autofix_code
from database import (
    create_eval_run,
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
app.config["SECRET_KEY"] = "agentgrade-dev"
load_env_file()
init_db()


@app.route("/", methods=["GET"])
def index():
    from_run_id = request.args.get("from_run_id", type=int)
    source_run = get_eval_run(from_run_id) if from_run_id else None
    auto_fix = request.args.get("auto_fix", default=0, type=int) == 1
    prefilled_code = source_run.get("code_input", "") if source_run else ""
    autofix_message = None
    if source_run and auto_fix:
        fix_result = generate_autofix_code(
            original_code=source_run.get("code_input", ""),
            agent_prompt=source_run.get("agent_prompt", ""),
            language=source_run.get("language", "python"),
        )
        prefilled_code = fix_result["fixed_code"]
        autofix_message = (
            "Auto-fix generated from the agent prompt. Review before submitting."
            if not fix_result["error"]
            else f"{fix_result['error']} Showing original code instead."
        )

    return render_template(
        "index.html",
        source_run=source_run,
        prefilled_code=prefilled_code,
        autofix_message=autofix_message,
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
            executor.submit(run_eval, code_input, dim, "gpt-4o"): ("primary", dim[0]) for dim in DIMENSIONS
        }
        audit_futures = {
            executor.submit(run_eval, code_input, dim, "gpt-4o-mini"): ("audit", dim[0]) for dim in DIMENSIONS
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
    for dim_name, _desc in DIMENSIONS:
        primary = primary_results.get(dim_name, {"score": None, "justification": "Missing primary result", "findings": []})
        audit = audit_results.get(dim_name, {"score": None, "justification": "Missing audit result", "findings": []})
        confidence, score_gap = confidence_for_scores(primary.get("score"), audit.get("score"))

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

    remediation = generate_remediation(code_input, primary_findings, audit_findings)
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
    )


if __name__ == "__main__":
    app.run(debug=True)
