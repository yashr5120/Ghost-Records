"""Reports Page - Export audit reports in JSON/CSV formats and view immutable audit trail."""

import json

import pandas as pd
import streamlit as st

from ghost_records.database import (
    init_db,
    list_audit_logs,
    list_findings,
    list_scans,
)
from ghost_records.reporting import (
    generate_audit_report_json,
    generate_findings_csv,
)
from ghost_records.ui_utils import render_header, render_sidebar

st.set_page_config(
    page_title="Reports | Ghost Records",
    page_icon="👻",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
render_sidebar()
render_header("Audit Reports & Exports", "Generate forensic reports, export flat findings spreadsheets, and review audit trail.")

scans = list_scans(limit=30)

if not scans:
    st.info("No audit scans recorded yet. Go to 'Scan Data' to perform your first audit.")
else:
    scan_options = {
        f"{s.scan_id} ({s.started_at[:19]}) — {s.total_anomalies} findings": s.scan_id
        for s in scans
    }
    sel_scan_label = st.selectbox("Select Audit Scan to Report", list(scan_options.keys()))
    sel_scan_id = scan_options[sel_scan_label]

    findings = list_findings(scan_id=sel_scan_id)

    st.markdown("---")
    st.subheader("📦 Generate & Download Exports")

    c_rep1, c_rep2 = st.columns(2)

    # 1. JSON Report
    with c_rep1:
        st.markdown("##### 📄 Comprehensive JSON Forensic Report")
        st.caption("Contains complete scan metadata, rule evidence, local AI explanations, and approval logs.")

        json_data, json_file_path = generate_audit_report_json(sel_scan_id)
        json_str = json.dumps(json_data, indent=2)

        st.download_button(
            label="⬇️ Download Audit Report (JSON)",
            data=json_str,
            file_name=f"ghost_audit_{sel_scan_id}.json",
            mime="application/json",
            type="primary",
            use_container_width=True,
        )

        with st.expander("Preview JSON Payload", expanded=False):
            st.json(json_data, expanded=False)

    # 2. CSV Report
    with c_rep2:
        st.markdown("##### 📊 Flat Findings Spreadsheet (CSV)")
        st.caption("Tabular export of all anomalies, severity levels, AI summaries, and remediation statuses.")

        csv_df, csv_file_path = generate_findings_csv(sel_scan_id)
        csv_bytes = csv_df.to_csv(index=False).encode("utf-8")

        st.download_button(
            label="⬇️ Download Findings (CSV)",
            data=csv_bytes,
            file_name=f"ghost_findings_{sel_scan_id}.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True,
        )

        with st.expander("Preview CSV Data", expanded=False):
            st.dataframe(csv_df, use_container_width=True, hide_index=True)

    # Findings Table Summary
    st.markdown("---")
    st.subheader(f"Findings in This Scan ({len(findings)})")
    if findings:
        summary_rows = []
        for f in findings:
            summary_rows.append({
                "Finding ID": f.finding_id,
                "Rule": f.rule_name,
                "Severity": f.severity.value,
                "Status": f.status.value,
                "Affected Rows": f.affected_rows_count,
                "Created At": f.created_at[:19],
            })
        st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)

# Section: Immutable Audit Trail
st.markdown("---")
st.subheader("🛡️ Forensic Audit Trail (Immutable Log)")
st.caption("Chronological record of every scan, AI explanation query, proposal, approval, and export.")

logs = list_audit_logs(limit=50)
if logs:
    log_rows = []
    for entry in logs:
        log_rows.append({
            "Timestamp": entry.timestamp[:19],
            "Action": entry.action_type,
            "Target ID": entry.target_id,
            "Details": json.dumps(entry.details),
        })
    st.dataframe(pd.DataFrame(log_rows), use_container_width=True, hide_index=True)
else:
    st.caption("No audit logs recorded.")
