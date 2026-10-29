"""Dashboard Page - Forensic audit metrics, distribution charts, and recent scans."""

import altair as alt
import pandas as pd
import streamlit as st

from ghost_records.database import get_dashboard_stats, init_db
from ghost_records.demo_generator import write_demo_files
from ghost_records.ui_utils import render_header, render_sidebar

st.set_page_config(
    page_title="Dashboard | Ghost Records",
    page_icon="👻",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
render_sidebar()
render_header("Forensic Dashboard", "Hunt down the ghosts haunting your data.")

stats = get_dashboard_stats()

# Top Metric Cards
c1, c2, c3, c4 = st.columns(4)

with c1:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-val">{stats['total_datasets']}</div>
            <div class="metric-lbl">Audited Datasets</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c2:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-val">{stats['total_anomalies']}</div>
            <div class="metric-lbl">Total Anomalies</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c3:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-val" style="color: #f85149;">{stats['high_critical_findings']}</div>
            <div class="metric-lbl">High & Critical Violations</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with c4:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-val" style="color: #3fb950;">{stats['resolved_dismissed_findings']}</div>
            <div class="metric-lbl">Resolved / Dismissed</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# Empty State or Active Dashboard
if stats["total_anomalies"] == 0:
    st.markdown(
        """
        <div class="forensic-card" style="text-align: center; padding: 40px 20px;">
            <div style="font-size: 48px; margin-bottom: 12px;">👻</div>
            <h3 style="color: #f0f6fc; margin-bottom: 8px;">No Datasets Scanned Yet</h3>
            <p style="color: #8b949e; max-width: 600px; margin: 0 auto 20px auto;">
                Ghost Records uses deterministic audit rules to unmask duplicate rows, colliding identifiers,
                orphaned foreign keys, and missing values—then explains the evidence using local Gemma inference.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    sc1, sc2, sc3 = st.columns([1, 2, 1])
    with sc2:
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("🚀 Load Synthetic Demo Data", type="primary", use_container_width=True):
                with st.spinner("Generating demo datasets and database..."):
                    write_demo_files()
                    st.success("Demo dataset generated in demo_data/! Head to Scan Data to audit.")
        with col_btn2:
            if st.button("🔍 Scan Your First Dataset", use_container_width=True):
                st.switch_page("pages/2_Scan_Data.py")

else:
    # Active Charts
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.subheader("Anomalies by Rule Category")
        cat_data = stats.get("category_distribution", {})
        if cat_data:
            df_cat = pd.DataFrame([{"Rule": k, "Count": v} for k, v in cat_data.items()])
            chart = (
                alt.Chart(df_cat)
                .mark_bar(cornerRadius=4, color="#d97706")
                .encode(
                    x=alt.X("Count:Q", title="Anomalies Detected"),
                    y=alt.Y("Rule:N", sort="-x", title=None),
                    tooltip=["Rule", "Count"],
                )
                .properties(height=260)
                .configure_axis(
                    labelColor="#8b949e",
                    titleColor="#8b949e",
                    gridColor="#21262d",
                    domainColor="#30363d",
                )
                .configure_view(strokeWidth=0)
            )
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("No categorical distribution data available.")

    with col_chart2:
        st.subheader("Severity Breakdown")
        sev_data = stats.get("severity_distribution", {})
        if sev_data:
            df_sev = pd.DataFrame([{"Severity": k, "Count": v} for k, v in sev_data.items()])
            color_scale = alt.Scale(
                domain=["Critical", "High", "Medium", "Low", "Info"],
                range=["#f85149", "#f0883e", "#d97706", "#58a6ff", "#8b949e"],
            )
            chart_sev = (
                alt.Chart(df_sev)
                .mark_bar(cornerRadius=4)
                .encode(
                    x=alt.X("Severity:N", title=None, sort=["Critical", "High", "Medium", "Low", "Info"]),
                    y=alt.Y("Count:Q", title="Total"),
                    color=alt.Color("Severity:N", scale=color_scale, legend=None),
                    tooltip=["Severity", "Count"],
                )
                .properties(height=260)
                .configure_axis(
                    labelColor="#8b949e",
                    titleColor="#8b949e",
                    gridColor="#21262d",
                    domainColor="#30363d",
                )
                .configure_view(strokeWidth=0)
            )
            st.altair_chart(chart_sev, use_container_width=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Recent Scans Table
    st.subheader("Recent Audit Scans")
    recent = stats.get("recent_scans", [])
    if recent:
        df_recent = pd.DataFrame(recent)
        df_recent = df_recent.rename(
            columns={
                "scan_id": "Scan ID",
                "dataset_name": "Dataset",
                "started_at": "Timestamp",
                "status": "Status",
                "total_anomalies": "Findings",
            }
        )
        st.dataframe(df_recent, use_container_width=True, hide_index=True)
    else:
        st.caption("No recent scans logged.")

    st.markdown("<br>", unsafe_allow_html=True)
    cta1, cta2 = st.columns([1, 4])
    with cta1:
        if st.button("🔍 New Forensic Scan", type="primary", use_container_width=True):
            st.switch_page("pages/2_Scan_Data.py")
    with cta2:
        if st.button("📋 Open Investigations", use_container_width=True):
            st.switch_page("pages/3_Investigations.py")
