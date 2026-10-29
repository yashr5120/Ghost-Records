"""Forensic, privacy-preserving prompt builder for local Gemma inference."""

import json
from typing import Any

from ghost_records.models import Finding


def build_evidence_explanation_prompt(finding: Finding) -> str:
    """Build a minimal, bounded, forensic prompt strictly grounded in finding evidence."""
    # Minimize evidence payload to avoid privacy leaks and keep context compact
    compact_evidence: dict[str, Any] = {
        "rule_id": finding.rule_id,
        "rule_name": finding.rule_name,
        "severity": finding.severity.value,
        "table": finding.table_name or "current_table",
        "affected_rows_count": finding.affected_rows_count,
    }

    raw_ev = finding.evidence or {}

    # Extract relevant fields based on rule
    if finding.rule_id == "RULE_A_EXACT_DUP":
        compact_evidence["duplicate_groups_count"] = raw_ev.get("duplicate_groups_count")
        compact_evidence["sample_clusters"] = raw_ev.get("sample_clusters", [])[:2]
    elif finding.rule_id == "RULE_B_DUP_ID":
        compact_evidence["identifier_column"] = raw_ev.get("identifier_column")
        compact_evidence["conflicts"] = raw_ev.get("sample_conflicts", [])[:2]
    elif finding.rule_id == "RULE_C_ORPHAN_FK":
        compact_evidence["child_foreign_key_column"] = raw_ev.get("child_foreign_key_column")
        compact_evidence["parent_table"] = raw_ev.get("parent_table")
        compact_evidence["parent_primary_key_column"] = raw_ev.get("parent_primary_key_column")
        compact_evidence["missing_keys_sample"] = raw_ev.get("missing_keys_sample", [])[:5]
    elif finding.rule_id == "RULE_D_MISSING_VAL":
        compact_evidence["column"] = raw_ev.get("column")
        compact_evidence["missing_count"] = raw_ev.get("missing_count")
        compact_evidence["missing_percentage"] = raw_ev.get("missing_percentage")
    elif "RULE_E" in finding.rule_id:
        compact_evidence["column"] = raw_ev.get("column")
        compact_evidence["invalid_count"] = raw_ev.get("invalid_count") or raw_ev.get("negative_count")
        compact_evidence["sample_invalid_values"] = raw_ev.get("sample_invalid_values") or raw_ev.get("sample_values", [])[:3]
    elif finding.rule_id == "RULE_F_OUTLIER":
        compact_evidence["column"] = raw_ev.get("column")
        compact_evidence["method"] = raw_ev.get("method")
        compact_evidence["bounds"] = {"lower": raw_ev.get("lower_bound"), "upper": raw_ev.get("upper_bound")}
        compact_evidence["sample_outliers"] = raw_ev.get("sample_outliers", [])[:3]

    evidence_json = json.dumps(compact_evidence, indent=2)

    prompt = f"""You are a specialized Data Quality Forensic Auditor.
Analyze the following observed evidence from a deterministic database audit and produce an evidence-grounded explanation.

OBSERVED EVIDENCE:
{evidence_json}

CRITICAL FORENSIC RULES:
1. Ground every statement strictly in the observed evidence above.
2. DO NOT invent missing IDs, customer names, or replacement keys.
3. DO NOT claim to have checked external servers, ERP systems, or live databases.
4. Clearly distinguish observed facts from hypotheses.
5. If the reason for a missing entity is unknown, explicitly state that verification against the authoritative source is required.
6. Provide a safe, non-destructive recommendation (e.g. quarantine, review, deduplicate only in a derived working copy).

You MUST respond ONLY with a valid JSON object matching this exact structure:
{{
  "summary": "Forensic summary of what occurred in 1-2 sentences.",
  "why_flagged": "Exact rule violation observed.",
  "likely_explanations": ["Hypothesis 1", "Hypothesis 2"],
  "verification_steps": ["Step 1 to verify", "Step 2 to verify"],
  "recommended_remediation": "Safe recommendation.",
  "confidence_statement": "Statement of confidence and limitations."
}}"""

    return prompt
