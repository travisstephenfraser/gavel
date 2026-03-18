import json
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Flask, redirect, render_template, request, url_for

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
    return render_template("index.html")


@app.route("/evaluate", methods=["POST"])
def evaluate():
    code_input = request.form["code_input"]
    language = request.form.get("language", "python")
    eval_run_id = create_eval_run(code_input=code_input, language=language, status="running")

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
    return render_template(
        "scorecard.html",
        eval_run=eval_run,
        dimensions=dimensions,
        remediation=remediation,
        remediation_issues=remediation_issues,
    )


if __name__ == "__main__":
    app.run(debug=True)
