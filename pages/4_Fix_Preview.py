"""Fix Preview Page - Review before/after proposals, approve/reject changes, and download derived copies."""

from pathlib import Path

import pandas as pd
import streamlit as st

from ghost_records.database import (
    get_dataset,
    get_finding,
    init_db,
    list_remediations,
)
from ghost_records.models import RemediationApproval
from ghost_records.remediation import (
    apply_remediation_to_derived_copy,
    reject_remediation_proposal,
)
from ghost_records.scanner import run_comprehensive_audit
from ghost_records.ui_utils import render_header, render_sidebar

st.set_page_config(
    page_title="Fix Preview | Ghost Records",
    page_icon="👻",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
render_sidebar()
render_header("Fix Preview & Approval", "Inspect proposed remediations, approve derived working copies, and verify fixes.")

proposals = list_remediations()

if not proposals:
    st.info("No remediation proposals generated yet. Head to 'Investigations' to propose fixes for detected anomalies.")
else:
    # Filter by Approval Status
    filter_status = st.radio(
        "Filter Proposals",
        ["All Proposals", "Pending Review", "Approved", "Rejected"],
        horizontal=True,
    )

    if filter_status == "Pending Review":
        filtered_props = [p for p in proposals if p.approval_status == RemediationApproval.PENDING]
    elif filter_status == "Approved":
        filtered_props = [p for p in proposals if p.approval_status == RemediationApproval.APPROVED]
    elif filter_status == "Rejected":
        filtered_props = [p for p in proposals if p.approval_status == RemediationApproval.REJECTED]
    else:
        filtered_props = proposals

    st.markdown(f"**Showing {len(filtered_props)} remediation proposal(s):**")

    for prop in filtered_props:
        finding = get_finding(prop.finding_id)
        dataset = get_dataset(prop.dataset_id)

        # Status badge color
        status_color = "#f59e0b"
        if prop.approval_status == RemediationApproval.APPROVED:
            status_color = "#3fb950"
        elif prop.approval_status == RemediationApproval.REJECTED:
            status_color = "#f85149"

        with st.expander(
            f"[{prop.approval_status.value.upper()}] {prop.action_title} (Affects {prop.affected_rows_count} records)",
            expanded=(prop.approval_status == RemediationApproval.PENDING),
        ):
            st.markdown(
                f"""
                <div style="background: #161b22; border-left: 4px solid {status_color}; padding: 12px 16px; border-radius: 4px; margin-bottom: 16px;">
                    <div style="font-size: 14px; font-weight: 700; color: #f0f6fc;">
                        {prop.action_title}
                    </div>
                    <div style="font-size: 13px; color: #8b949e; margin-top: 4px;">
                        {prop.action_description}
                    </div>
                    <div style="font-size: 12px; color: #d97706; margin-top: 8px;">
                        Target: Derived working copy only • Source data is strictly read-only and preserved
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # Before and After Previews
            c_before, c_after = st.columns(2)

            with c_before:
                st.markdown("##### ❌ Before (Current Raw Anomaly Samples)")
                if prop.before_preview:
                    df_before = pd.DataFrame(prop.before_preview)
                    st.dataframe(df_before, use_container_width=True, hide_index=True)
                else:
                    st.caption("No before preview available.")

            with c_after:
                st.markdown("##### ✅ After (Proposed Clean Transformation)")
                if prop.after_preview:
                    df_after = pd.DataFrame(prop.after_preview)
                    st.dataframe(df_after, use_container_width=True, hide_index=True)
                else:
                    st.caption("No after preview available.")

            # Decision Action Buttons
            if prop.approval_status == RemediationApproval.PENDING:
                st.markdown("---")
                st.markdown("##### ⚖️ Human Decision Gate")

                fill_input = None
                if prop.action_type == "FILL_MISSING_EXPLICIT":
                    fill_input = st.text_input(
                        "Explicit Value to Fill (Will NOT modify source file)",
                        value="UNSPECIFIED",
                        key=f"fill_{prop.remediation_id}",
                    )

                btn_col1, btn_col2 = st.columns([1, 1])

                with btn_col1:
                    if st.button("✅ Approve & Generate Derived Copy", key=f"app_{prop.remediation_id}", type="primary", use_container_width=True):
                        # Load original dataframe to transform
                        df_to_transform = st.session_state.get("current_scanned_df")
                        if df_to_transform is None and dataset:
                            if dataset.source_type == "csv" and Path(dataset.source_path).exists():
                                df_to_transform = pd.read_csv(dataset.source_path)

                        if df_to_transform is not None and finding is not None:
                            with st.spinner("Applying non-destructive transformation to derived copy..."):
                                clean_df, clean_path, quar_df, quar_path = apply_remediation_to_derived_copy(
                                    df=df_to_transform,
                                    proposal=prop,
                                    finding=finding,
                                    dataset_name=dataset.dataset_name if dataset else "dataset",
                                    fill_value=fill_input,
                                )
                                st.session_state[f"last_derived_{prop.remediation_id}"] = str(clean_path)
                                st.session_state[f"last_clean_df_{prop.remediation_id}"] = clean_df
                                st.success(f"Derived clean copy created at: {clean_path.name}")
                                st.rerun()
                        else:
                            st.error("Could not locate active dataset. Please re-run scan from 'Scan Data'.")

                with btn_col2:
                    if st.button("❌ Reject Proposal", key=f"rej_{prop.remediation_id}", use_container_width=True):
                        reject_remediation_proposal(prop, finding.finding_id if finding else "")
                        st.info("Proposal rejected. Recorded in audit log.")
                        st.rerun()

            elif prop.approval_status == RemediationApproval.APPROVED:
                st.markdown("---")
                st.markdown("##### 📥 Approved Artifacts & Verification")

                if prop.derived_file_path and Path(prop.derived_file_path).exists():
                    clean_file_path = Path(prop.derived_file_path)
                    with open(clean_file_path, "rb") as f:
                        file_bytes = f.read()

                    d_col1, d_col2 = st.columns(2)
                    with d_col1:
                        st.download_button(
                            label=f"⬇️ Download Clean Copy ({clean_file_path.name})",
                            data=file_bytes,
                            file_name=clean_file_path.name,
                            mime="text/csv",
                            use_container_width=True,
                        )

                    with d_col2:
                        # Re-scan derived copy to verify resolution
                        if st.button("🔄 Re-Scan Clean Copy to Verify Resolution", key=f"rescan_{prop.remediation_id}", use_container_width=True):
                            with st.spinner("Auditing derived copy for residual anomalies..."):
                                clean_df = pd.read_csv(clean_file_path)
                                v_scan_id = f"verify_{prop.remediation_id[:6]}"
                                v_rec, v_findings = run_comprehensive_audit(
                                    df=clean_df,
                                    scan_id=v_scan_id,
                                    dataset_id=prop.dataset_id,
                                    table_name="verified_clean",
                                )
                                if len(v_findings) == 0:
                                    st.success("🎉 Verification Succeeded! Zero anomalies detected in derived copy.")
                                else:
                                    st.warning(f"Residual anomalies remaining: {len(v_findings)}")
                else:
                    st.caption("Derived clean copy path recorded: " + str(prop.derived_file_path))
