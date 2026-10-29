"""Investigations Page - Filterable anomaly case files with evidence and Local AI forensic explanations."""

from pathlib import Path

import pandas as pd
import streamlit as st

from ghost_records.ai.ollama_client import get_ai_client
from ghost_records.database import (
    add_audit_log,
    get_ai_explanation,
    get_dataset,
    get_remediation_by_finding,
    init_db,
    list_datasets,
    list_findings,
    update_finding_status,
)
from ghost_records.models import FindingStatus, Severity
from ghost_records.remediation import generate_remediation_proposal
from ghost_records.ui_utils import render_header, render_sidebar

st.set_page_config(
    page_title="Investigations | Ghost Records",
    page_icon="👻",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
render_sidebar()
render_header("Forensic Investigations", "Examine evidence, query local AI for hypotheses, and manage cases.")

# --- Filter Bar ---
datasets = list_datasets()
dataset_options = {"(All Datasets)": None}
for d in datasets:
    dataset_options[f"{d.dataset_name} ({d.dataset_id[:8]})"] = d.dataset_id

f_col1, f_col2, f_col3, f_col4 = st.columns(4)

with f_col1:
    sel_ds_label = st.selectbox("Filter by Dataset", list(dataset_options.keys()))
    selected_dataset_id = dataset_options[sel_ds_label]

with f_col2:
    sev_choices = ["(All Severities)"] + [s.value for s in Severity]
    sel_sev = st.selectbox("Filter by Severity", sev_choices)
    selected_severity = None if sel_sev == "(All Severities)" else sel_sev

with f_col3:
    status_choices = ["(All Statuses)"] + [s.value for s in FindingStatus]
    sel_status = st.selectbox("Filter by Status", status_choices)
    selected_status = None if sel_status == "(All Statuses)" else sel_status

with f_col4:
    ai_filter = st.selectbox("AI Explanation", ["(All)", "Explained", "Pending Explanation"])

# Fetch filtered findings
all_findings = list_findings(
    dataset_id=selected_dataset_id,
    severity=selected_severity,
    status=selected_status,
)

# Apply AI filter
if ai_filter == "Explained":
    all_findings = [f for f in all_findings if get_ai_explanation(f.finding_id) is not None]
elif ai_filter == "Pending Explanation":
    all_findings = [f for f in all_findings if get_ai_explanation(f.finding_id) is None]

st.markdown(f"**Found {len(all_findings)} anomaly records matching criteria.**")

if not all_findings:
    st.info("No anomalies match the current filters. Run a scan from 'Scan Data' or adjust filter options.")
else:
    for idx, finding in enumerate(all_findings):
        # Color badge styling
        sev_class = f"badge-{finding.severity.value.lower()}"
        ai_exp = get_ai_explanation(finding.finding_id)
        rem_prop = get_remediation_by_finding(finding.finding_id)

        with st.expander(
            f"[{finding.severity.value}] {finding.rule_name} — {finding.table_name or 'Dataset'} ({finding.affected_rows_count} affected records)",
            expanded=(idx == 0),
        ):
            col_left, col_right = st.columns([1, 1], gap="medium")

            # --- LEFT COLUMN: Deterministic Evidence ---
            with col_left:
                st.markdown(
                    f"""
                    <div style="display: flex; gap: 8px; margin-bottom: 12px; align-items: center;">
                        <span class="badge {sev_class}">{finding.severity.value}</span>
                        <span class="badge badge-info">{finding.status.value}</span>
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #8b949e;">{finding.finding_id}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.markdown(f"**Rule:** `{finding.rule_id}`")
                st.markdown(f"**Table:** `{finding.table_name or 'N/A'}`")
                st.markdown(f"**Affected Rows:** `{finding.affected_rows_count}` records")
                st.markdown(
                    f"**Row Indices:** `{', '.join(str(i) for i in finding.affected_row_indices[:15])}`"
                    f"{'...' if len(finding.affected_row_indices) > 15 else ''}"
                )

                st.markdown("##### Ground-Truth Evidence")
                ev = finding.evidence or {}

                # Display structured evidence cleanly
                if ev.get("sample_clusters"):
                    st.caption("Duplicate Cluster Samples:")
                    for c in ev["sample_clusters"][:2]:
                        st.json(c.get("matching_values", {}), expanded=False)

                elif ev.get("sample_conflicts"):
                    st.caption("Conflicting Identifier Samples:")
                    for sc in ev["sample_conflicts"][:2]:
                        st.markdown(f"- Key: `{sc.get('identifier_value')}` ({sc.get('conflict_count')} occurrences)")
                        if "rows_preview" in sc:
                            st.json(sc["rows_preview"], expanded=False)

                elif "missing_keys_sample" in ev:
                    st.caption(f"Missing Referenced Parent Keys in `{ev.get('parent_table')}`:")
                    st.code(", ".join(str(x) for x in ev["missing_keys_sample"]))

                elif "sample_invalid_values" in ev:
                    st.caption("Invalid Date / Format Samples:")
                    st.json(ev["sample_invalid_values"], expanded=False)

                elif "sample_outliers" in ev:
                    st.caption(f"Outlier Values (IQR Bounds: [{ev.get('lower_bound')}, {ev.get('upper_bound')}]):")
                    st.json(ev["sample_outliers"], expanded=False)

                else:
                    st.json(ev, expanded=False)

                # Status Transition Action
                st.markdown("---")
                new_status = st.selectbox(
                    "Update Investigation Status",
                    [s.value for s in FindingStatus],
                    index=[s.value for s in FindingStatus].index(finding.status.value),
                    key=f"status_sel_{finding.finding_id}",
                )
                if new_status != finding.status.value:
                    update_finding_status(finding.finding_id, FindingStatus(new_status))
                    add_audit_log(
                        "FINDING_STATUS_UPDATED",
                        finding.finding_id,
                        {"old_status": finding.status.value, "new_status": new_status},
                    )
                    st.success(f"Status updated to '{new_status}'.")
                    st.rerun()

            # --- RIGHT COLUMN: Local AI Forensic Explanation ---
            with col_right:
                st.markdown("##### 🤖 Local AI Forensic Explanation")
                st.caption("Powered by local open-weight Gemma model running in Ollama (100% private).")

                if ai_exp is None:
                    st.info("No AI explanation generated yet for this finding.")
                    if st.button("✨ Explain with Local AI", key=f"ai_btn_{finding.finding_id}", type="primary"):
                        with st.spinner("Querying local Gemma model via Ollama..."):
                            client = get_ai_client()
                            ai_exp = client.explain_finding(finding)
                            st.rerun()
                else:
                    if ai_exp.is_error:
                        st.warning(f"⚠️ Local AI Note: {ai_exp.error_message}")
                        st.markdown(f"**Deterministic Summary:** {ai_exp.summary}")
                        if st.button("🔄 Retry Local AI", key=f"retry_{finding.finding_id}"):
                            with st.spinner("Retrying local inference..."):
                                client = get_ai_client()
                                client.explain_finding(finding)
                                st.rerun()
                    else:
                        st.markdown(
                            f"""
                            <div class="ai-box">
                                <div style="font-size: 11px; color: #d97706; font-weight: 700; text-transform: uppercase; margin-bottom: 6px;">
                                    Model: {ai_exp.model_identifier}
                                </div>
                                <div style="font-size: 14px; font-weight: 600; color: #f0f6fc; margin-bottom: 10px;">
                                    {ai_exp.summary}
                                </div>
                                <div style="font-size: 13px; color: #c9d1d9; margin-bottom: 10px;">
                                    <b>Why Flagged:</b> {ai_exp.why_flagged}
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )

                        if ai_exp.likely_explanations:
                            st.markdown("###### Plausible Hypotheses:")
                            for h in ai_exp.likely_explanations:
                                st.markdown(f"- {h}")

                        if ai_exp.verification_steps:
                            st.markdown("###### Human Verification Steps:")
                            for s in ai_exp.verification_steps:
                                st.markdown(f"1. {s}")

                        st.markdown(f"**Recommended Action:** {ai_exp.recommended_remediation}")
                        st.caption(f"Forensic Confidence: {ai_exp.confidence_statement}")

                # Remediation Section
                st.markdown("---")
                st.markdown("##### 🛠️ Remediation Action")
                if rem_prop is None:
                    if st.button("Generate Fix Proposal", key=f"gen_rem_{finding.finding_id}"):
                        # Grab dataframe if available
                        df_to_use = st.session_state.get("current_scanned_df")
                        if df_to_use is None:
                            # Try to reload dataset from disk
                            ds_meta = get_dataset(finding.dataset_id)
                            if ds_meta and Path(ds_meta.source_path).exists():
                                if ds_meta.source_type == "csv":
                                    df_to_use = pd.read_csv(ds_meta.source_path)
                        if df_to_use is not None:
                            proposal = generate_remediation_proposal(finding, df_to_use)
                            st.success(f"Proposed: {proposal.action_title}!")
                            st.rerun()
                        else:
                            st.warning("Original dataset not active in session. Open 'Scan Data' to scan first.")
                else:
                    st.markdown(f"**Proposal:** `{rem_prop.action_title}`")
                    st.markdown(f"**Status:** `{rem_prop.approval_status.value}`")
                    st.markdown(f"{rem_prop.action_description}")
                    if st.button("Review in Fix Preview ➔", key=f"go_fix_{finding.finding_id}"):
                        st.switch_page("pages/4_Fix_Preview.py")
