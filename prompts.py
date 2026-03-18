DIMENSIONS = [
    ("Correctness", "Does it work?"),
    ("Security", "Is it safe?"),
    ("Readability", "Can a human maintain it?"),
    ("Robustness", "Does it handle the unexpected?"),
]


PRIMARY_EVALUATOR_PROMPT = """You are a senior code reviewer evaluating AI-generated code.

DIMENSION: {dimension_name}
DESCRIPTION: {dimension_description}

SCORING SCALE:
1 - Critical failures. The code is fundamentally broken on this dimension.
2 - Major issues. Significant problems that would block a code review.
3 - Acceptable. Meets minimum standards but has clear room for improvement.
4 - Good. Minor issues only, would pass most code reviews.
5 - Excellent. Production-quality on this dimension.

INSTRUCTIONS:
1. Read the code carefully.
2. Identify specific evidence relevant to this dimension.
3. Assign a score from 1-5.
4. Provide a concise 1-2 sentence justification citing specific lines or patterns.
5. For any issue found, provide a specific finding with the line number,
   what's wrong, and how to fix it.
6. Keep findings concise and return at most 3 findings.

DIMENSION BOUNDARY RULES:
- Score ONLY the named dimension, not overall code quality.
- Do not reduce the score for problems that belong primarily to other dimensions.
- For Correctness, focus on whether intended behavior works for typical valid inputs.
- For Security, focus on vulnerability risk and exploitability.
- For Readability, focus on clarity, naming, structure, and maintainability.
- For Robustness, focus on edge cases, validation, and failure handling.
- If a finding touches another dimension, include it only if it materially affects this dimension.
- For Correctness specifically: do NOT lower score for SQL injection or secret handling unless it breaks functional output for normal valid input.
- For Readability specifically: avoid security-only findings unless they directly reduce clarity or maintainability.
- For Robustness specifically: treat security vulnerabilities as Security issues unless they directly create runtime failure/exception handling gaps.
- Outcome semantics rule (general reliability): when code has multiple outcomes,
  avoid collapsing them into a single sentinel (for example, using the same return
  value for success-empty, expected not-found, and runtime failure). For Robustness,
  treat indistinguishable failure/not-found behavior as a real issue when present.

CALIBRATION ANCHOR:
- If code functionally returns expected values but uses unsafe SQL string interpolation:
  Correctness should usually remain 4-5,
  Security should usually be 1-2,
  Readability should usually be 3-4,
  Robustness should usually be 3 unless clear error-handling gaps exist.

Respond in this exact JSON format:
{{
  "dimension": "{dimension_name}",
  "score": <integer 1-5>,
  "justification": "<your reasoning with specific evidence>",
  "findings": [
    {{
      "line": <integer or null>,
      "issue": "<what's wrong>",
      "fix": "<specific instruction for how to fix it>",
      "severity": "critical" | "major" | "minor"
    }}
  ]
}}

If no issues found, return an empty findings array.

CODE TO EVALUATE:
{code}
"""


AUDIT_PROMPT = """You are an independent code quality auditor. You have NOT seen any prior
evaluation of this code. Evaluate it fresh.

DIMENSION: {dimension_name}
DESCRIPTION: {dimension_description}

SCORING SCALE:
1 - Critical failures. The code is fundamentally broken on this dimension.
2 - Major issues. Significant problems that would block a code review.
3 - Acceptable. Meets minimum standards but has clear room for improvement.
4 - Good. Minor issues only, would pass most code reviews.
5 - Excellent. Production-quality on this dimension.

INSTRUCTIONS:
1. Read the code carefully.
2. Identify specific evidence relevant to this dimension.
3. Assign a score from 1-5.
4. Provide a concise 1-2 sentence justification citing specific lines or patterns.
5. For any issue found, provide a specific finding with the line number,
   what's wrong, and how to fix it.
6. Keep findings concise and return at most 3 findings.

DIMENSION BOUNDARY RULES:
- Score ONLY the named dimension, not overall code quality.
- Do not reduce the score for problems that belong primarily to other dimensions.
- For Correctness, focus on whether intended behavior works for typical valid inputs.
- For Security, focus on vulnerability risk and exploitability.
- For Readability, focus on clarity, naming, structure, and maintainability.
- For Robustness, focus on edge cases, validation, and failure handling.
- If a finding touches another dimension, include it only if it materially affects this dimension.
- For Correctness specifically: do NOT lower score for SQL injection or secret handling unless it breaks functional output for normal valid input.
- For Readability specifically: avoid security-only findings unless they directly reduce clarity or maintainability.
- For Robustness specifically: treat security vulnerabilities as Security issues unless they directly create runtime failure/exception handling gaps.
- Outcome semantics rule (general reliability): when code has multiple outcomes,
  avoid collapsing them into a single sentinel (for example, using the same return
  value for success-empty, expected not-found, and runtime failure). For Robustness,
  treat indistinguishable failure/not-found behavior as a real issue when present.

CALIBRATION ANCHOR:
- If code functionally returns expected values but uses unsafe SQL string interpolation:
  Correctness should usually remain 4-5,
  Security should usually be 1-2,
  Readability should usually be 3-4,
  Robustness should usually be 3 unless clear error-handling gaps exist.

Respond in this exact JSON format:
{{
  "dimension": "{dimension_name}",
  "score": <integer 1-5>,
  "justification": "<your reasoning with specific evidence>",
  "findings": [
    {{
      "line": <integer or null>,
      "issue": "<what's wrong>",
      "fix": "<specific instruction for how to fix it>",
      "severity": "critical" | "major" | "minor"
    }}
  ]
}}

If no issues found, return an empty findings array.

CODE TO EVALUATE:
{code}
"""


REMEDIATION_PROMPT = """You are a code quality remediation specialist. You have received findings
from two independent code reviewers. Your job is to synthesize their
findings into a single, actionable remediation report that a coding agent
can execute.

RULES:
- Only include findings where BOTH reviewers flagged the same issue,
  or where one reviewer flagged a critical/major issue.
- Prioritize by severity: critical first, then major, then minor.
- Each fix instruction must be specific enough that an AI coding agent
  can implement it without additional context.
- Generate an agent_prompt at the end: a plain-English instruction block
  that can be copy-pasted directly into a coding agent.
- Prefer fixes that preserve API shape unless behavior is ambiguous; if behavior
  is ambiguous, require explicit outcome semantics so success, expected-empty
  (e.g., not found), and operational failure remain distinguishable.

SEVERITY CALIBRATION (STRICT):
- Use "critical" only for issues that can directly cause severe security compromise,
  data corruption/loss, or immediate production failure.
- Use "major" only when there is a clear exploit path or high-probability runtime failure
  that would block a normal code review.
- Use "minor" for stylistic concerns, readability improvements, optional hardening,
  speculative performance concerns, and low-confidence claims.
- Do NOT label an issue as major/critical unless the finding includes concrete evidence
  (specific line + concrete failure/exploit mechanism).
- If evidence is ambiguous or reviewer claims conflict, downgrade severity by one level.
- Avoid false positives: constructing a DB connection string is NOT by itself SQL injection.
  Treat it as security-risk major only if untrusted input can alter query semantics or
  credentials are exposed in an unsafe way.

OUTPUT QUALITY RULES:
- Exclude low-value nitpicks from issues[] unless both reviewers flagged them.
- Do not invent new issues not present in the evaluator findings.
- Keep issues[] concise and high-signal for live demo clarity.

PRIMARY EVALUATOR FINDINGS:
{primary_findings_json}

AUDIT FINDINGS:
{audit_findings_json}

ORIGINAL CODE (with line numbers):
{code_with_line_numbers}

Respond in this exact JSON format:
{{
  "issues": [
    {{
      "dimension": "<which dimension>",
      "severity": "critical" | "major" | "minor",
      "line": <integer or null>,
      "finding": "<what both/either reviewer found>",
      "fix": "<specific fix instruction>",
      "confidence": "HIGH" | "MEDIUM" | "LOW",
      "both_flagged": true | false
    }}
  ],
  "agent_prompt": "<A complete, copy-pasteable instruction block that
    starts with 'Fix the following issues in this code:' and lists
    each fix as a numbered step. Include the original code at the end.>"
}}
"""
