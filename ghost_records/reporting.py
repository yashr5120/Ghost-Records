"""Audit report generation in JSON and flat CSV formats."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Tuple

import pandas as pd

from ghost_records.config import CONFIG
from ghost_records.database import (
    add_audit_log,
    get_ai_explanation,
    get_dataset,
    get_remediation_by_finding,
    get_scan,
    list_findings,
)


def generate_audit_report_json(
    scan_id: str,
    output_path: Path | None = None,
) -> Tuple[dict[str, Any], Path]:
    """Generate a comprehensive JSON audit report for a given scan."""
    scan = get_scan(scan_id)
    if not scan:
        raise ValueError(f"Scan {scan_id} not found.")

    dataset = get_dataset(scan.dataset_id)
    findings = list_findings(scan_id=scan_id)

    findings_payload: list[dict[str, Any]] = []
    for f in findings:
        ai_exp = get_ai_explanation(f.finding_id)
        rem = get_remediation_by_finding(f.finding_id)

        item: dict[str, Any] = {
            "finding_id": f.finding_id,
            "rule_id": f.rule_id,
            "rule_name": f.rule_name,
            "severity": f.severity.value,
            "table_name": f.table_name,
            "status": f.status.value,
            "affected_rows_count": f.affected_rows_count,
            "evidence": f.evidence,
            "created_at": f.created_at,
            "ai_explanation": ai_exp.to_dict() if ai_exp else None,
            "remediation_proposal": rem.to_dict() if rem else None,
        }
        findings_payload.append(item)

    report_data: dict[str, Any] = {
        "report_type": "Ghost Records Forensic Data Quality Audit",
        "app_version": CONFIG.version,
        "generated_at": datetime.now().isoformat(),
        "scan": scan.to_dict(),
        "dataset": dataset.to_dict() if dataset else None,
        "summary": {
            "total_findings": len(findings),
            "critical_high_count": len([f for f in findings if f.severity.value in ["Critical", "High"]]),
            "resolved_approved_count": len([f for f in findings if f.status.value in ["Approved", "Resolved"]]),
        },
        "findings": findings_payload,
        "disclaimer": (
            "Ghost Records deterministic rules detect integrity anomalies. AI explanations "
            "are locally-generated hypotheses. No dataset rows were transmitted to any external service."
        ),
    }

    CONFIG.reports_dir.mkdir(parents=True, exist_ok=True)
    if not output_path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = CONFIG.reports_dir / f"audit_report_{scan_id}_{stamp}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)

    add_audit_log(
        "REPORT_EXPORTED_JSON",
        scan_id,
        {"report_path": str(output_path), "findings_count": len(findings)},
    )

    return report_data, output_path


def generate_findings_csv(
    scan_id: str,
    output_path: Path | None = None,
) -> Tuple[pd.DataFrame, Path]:
    """Generate a flat, spreadsheet-friendly CSV of all findings in a scan."""
    findings = list_findings(scan_id=scan_id)
    records: list[dict[str, Any]] = []

    for f in findings:
        ai_exp = get_ai_explanation(f.finding_id)
        rem = get_remediation_by_finding(f.finding_id)

        rec = {
            "finding_id": f.finding_id,
            "rule_id": f.rule_id,
            "rule_name": f.rule_name,
            "severity": f.severity.value,
            "table_name": f.table_name or "default",
            "status": f.status.value,
            "affected_rows_count": f.affected_rows_count,
            "ai_summary": ai_exp.summary if ai_exp else "Not generated",
            "ai_why_flagged": ai_exp.why_flagged if ai_exp else "Not generated",
            "ai_confidence": ai_exp.confidence_statement if ai_exp else "N/A",
            "remediation_action": rem.action_title if rem else "None proposed",
            "remediation_status": rem.approval_status.value if rem else "N/A",
            "created_at": f.created_at,
        }
        records.append(rec)

    df = pd.DataFrame(records)

    CONFIG.reports_dir.mkdir(parents=True, exist_ok=True)
    if not output_path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = CONFIG.reports_dir / f"findings_{scan_id}_{stamp}.csv"

    df.to_csv(output_path, index=False)

    add_audit_log(
        "REPORT_EXPORTED_CSV",
        scan_id,
        {"csv_path": str(output_path), "rows": len(df)},
    )

    return df, output_path
