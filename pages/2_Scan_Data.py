"""Scan Data Page - Import CSVs and SQLite databases, profile columns, and launch forensic scans."""

import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from ghost_records.config import CONFIG
from ghost_records.database import (
    add_audit_log,
    init_db,
    save_dataset,
    save_finding,
    save_scan,
)
from ghost_records.demo_generator import write_demo_files
from ghost_records.models import DatasetMetadata
from ghost_records.profiling import profile_dataframe
from ghost_records.scanner import run_comprehensive_audit
from ghost_records.ui_utils import render_header, render_sidebar

st.set_page_config(
    page_title="Scan Data | Ghost Records",
    page_icon="👻",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
render_sidebar()
render_header("Scan Dataset", "Profile datasets deterministically and audit for ghosts and anomalies.")

# Tabs for Input Methods
tab_csv, tab_sqlite, tab_demo = st.tabs(["📄 CSV Import", "🗄️ SQLite Database", "🚀 Synthetic Demo Datasets"])

active_df: pd.DataFrame | None = None
dataset_name: str = ""
source_type: str = "csv"
source_path: str = ""
table_name: str | None = None
related_dfs: dict[str, tuple[pd.DataFrame, str, str]] = {}

# --- TAB 1: CSV Import ---
with tab_csv:
    st.subheader("Upload CSV File")
    uploaded_file = st.file_uploader(
        "Choose a CSV file (Max 50MB)",
        type=["csv"],
        help="Upload untrusted CSV data. Data remains strictly on your local machine.",
    )

    if uploaded_file is not None:
        file_size_mb = uploaded_file.size / (1024 * 1024)
        if file_size_mb > CONFIG.max_upload_size_mb:
            st.error(f"File size ({file_size_mb:.1f} MB) exceeds limit of {CONFIG.max_upload_size_mb} MB.")
        else:
            CONFIG.uploads_dir.mkdir(parents=True, exist_ok=True)
            saved_csv_path = CONFIG.uploads_dir / uploaded_file.name
            with open(saved_csv_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            # Safe encoding fallback
            try:
                active_df = pd.read_csv(saved_csv_path, encoding="utf-8")
            except UnicodeDecodeError:
                active_df = pd.read_csv(saved_csv_path, encoding="latin1")

            default_name = Path(uploaded_file.name).stem
            dataset_name = st.text_input("Dataset Name", value=default_name, key="csv_ds_name")
            source_type = "csv"
            source_path = str(saved_csv_path)

# --- TAB 2: SQLite Import ---
with tab_sqlite:
    st.subheader("Connect to Local SQLite Database (Read-Only Mode)")
    st.caption("Ghost Records connects strictly with read-only flags to guarantee source database safety.")

    sqlite_source = st.radio(
        "SQLite Database Source",
        ["Upload .db / .sqlite file", "Specify local file path", "Use Demo SQLite Database"],
        horizontal=True,
    )

    db_file_path: Path | None = None

    if sqlite_source == "Upload .db / .sqlite file":
        up_db = st.file_uploader("Upload SQLite database", type=["db", "sqlite", "sqlite3"])
        if up_db is not None:
            CONFIG.uploads_dir.mkdir(parents=True, exist_ok=True)
            db_file_path = CONFIG.uploads_dir / up_db.name
            with open(db_file_path, "wb") as f:
                f.write(up_db.getbuffer())

    elif sqlite_source == "Specify local file path":
        path_input = st.text_input("Local absolute or relative path to .sqlite / .db file")
        if path_input and Path(path_input).exists():
            db_file_path = Path(path_input)
        elif path_input:
            st.warning("Path does not exist on local filesystem.")

    elif sqlite_source == "Use Demo SQLite Database":
        demo_db_path = CONFIG.demo_dir / "ghost_store_demo.sqlite"
        if not demo_db_path.exists():
            write_demo_files()
        db_file_path = demo_db_path
        st.success(f"Using demo database at {demo_db_path}")

    if db_file_path and db_file_path.exists():
        try:
            # Safe read-only connection
            uri_path = f"file:{db_file_path.resolve().as_posix()}?mode=ro"
            ro_conn = sqlite3.connect(uri_path, uri=True)
            cursor = ro_conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
            tables = [row[0] for row in cursor.fetchall()]

            if not tables:
                st.warning("Database contains no tables.")
            else:
                sel_table = st.selectbox("Select Primary Table to Audit", tables)
                if sel_table:
                    active_df = pd.read_sql_query(f'SELECT * FROM "{sel_table}"', ro_conn)
                    table_name = sel_table
                    dataset_name = f"{db_file_path.stem}_{sel_table}"
                    source_type = "sqlite"
                    source_path = str(db_file_path)

                    # Relationship mapping options if other tables exist
                    other_tables = [t for t in tables if t != sel_table]
                    if other_tables:
                        st.markdown("##### Map Foreign Key Relationships")
                        for ot in other_tables:
                            with st.expander(f"Relate '{sel_table}' to parent table '{ot}'"):
                                ot_df = pd.read_sql_query(f'SELECT * FROM "{ot}"', ro_conn)
                                ot_cols = list(ot_df.columns)
                                cur_cols = list(active_df.columns)

                                col_l, col_r = st.columns(2)
                                with col_l:
                                    child_fk = st.selectbox(
                                        f"Foreign Key in '{sel_table}'",
                                        ["(None)"] + cur_cols,
                                        key=f"fk_{ot}_child",
                                    )
                                with col_r:
                                    parent_pk = st.selectbox(
                                        f"Primary Key in '{ot}'",
                                        ["(None)"] + ot_cols,
                                        key=f"pk_{ot}_parent",
                                    )

                                if child_fk != "(None)" and parent_pk != "(None)":
                                    related_dfs[ot] = (ot_df, child_fk, parent_pk)

            ro_conn.close()
        except Exception as ex:
            st.error(f"Error reading SQLite database safely: {ex!s}")

# --- TAB 3: Demo Data Generator ---
with tab_demo:
    st.subheader("Load Seeded Forensic Demo Datasets")
    st.markdown(
        """
        Synthetically generated e-commerce datasets with **ground-truth seeded anomalies**:
        - **Customers (24 rows)**: Exact duplicates, colliding IDs, missing emails, invalid date formats, extreme spend outlier.
        - **Products (12 rows)**: Missing SKU, negative stock quantity, negative unit prices.
        - **Orders (23 rows)**: Orphaned customer IDs, orphaned product IDs, duplicate orders, malformed dates.
        """
    )

    demo_choice = st.selectbox(
        "Choose Demo Dataset",
        ["orders (references customers & products)", "customers", "products"],
    )

    if st.button("Load Selected Demo Dataset", type="primary"):
        paths = write_demo_files()
        if "orders" in demo_choice:
            active_df = pd.read_csv(paths["orders_csv"])
            dataset_name = "demo_orders"
            table_name = "orders"
            source_type = "csv"
            source_path = str(paths["orders_csv"])

            cust_df = pd.read_csv(paths["customers_csv"])
            prod_df = pd.read_csv(paths["products_csv"])
            related_dfs = {
                "customers": (cust_df, "customer_id", "customer_id"),
                "products": (prod_df, "product_id", "product_id"),
            }
            st.session_state["loaded_demo_df"] = active_df
            st.session_state["loaded_demo_name"] = dataset_name
            st.session_state["loaded_demo_table"] = table_name
            st.session_state["loaded_demo_path"] = source_path
            st.session_state["loaded_demo_related"] = related_dfs
            st.success("Loaded demo orders dataset with automatic mapping to customers and products!")

        elif "customers" in demo_choice:
            active_df = pd.read_csv(paths["customers_csv"])
            dataset_name = "demo_customers"
            table_name = "customers"
            source_type = "csv"
            source_path = str(paths["customers_csv"])
            st.session_state["loaded_demo_df"] = active_df
            st.session_state["loaded_demo_name"] = dataset_name
            st.session_state["loaded_demo_table"] = table_name
            st.session_state["loaded_demo_path"] = source_path
            st.session_state["loaded_demo_related"] = {}
            st.success("Loaded demo customers dataset!")

        elif "products" in demo_choice:
            active_df = pd.read_csv(paths["products_csv"])
            dataset_name = "demo_products"
            table_name = "products"
            source_type = "csv"
            source_path = str(paths["products_csv"])
            st.session_state["loaded_demo_df"] = active_df
            st.session_state["loaded_demo_name"] = dataset_name
            st.session_state["loaded_demo_table"] = table_name
            st.session_state["loaded_demo_path"] = source_path
            st.session_state["loaded_demo_related"] = {}
            st.success("Loaded demo products dataset!")

if active_df is None and "loaded_demo_df" in st.session_state:
    active_df = st.session_state["loaded_demo_df"]
    dataset_name = st.session_state.get("loaded_demo_name", "demo_dataset")
    table_name = st.session_state.get("loaded_demo_table", None)
    source_path = st.session_state.get("loaded_demo_path", "")
    related_dfs = st.session_state.get("loaded_demo_related", {})

# --- SECTION: Profiling & Audit Launcher ---
if active_df is not None:
    st.markdown("---")
    st.subheader(f"Data Profiling: {dataset_name or 'Uploaded Dataset'}")

    p_col1, p_col2, p_col3, p_col4 = st.columns(4)
    with p_col1:
        st.metric("Total Rows", len(active_df))
    with p_col2:
        st.metric("Total Columns", len(active_df.columns))
    with p_col3:
        dup_count = int(active_df.duplicated().sum())
        st.metric("Exact Duplicate Rows", dup_count)
    with p_col4:
        missing_count = int(active_df.isna().sum().sum())
        st.metric("Total Null Cells", missing_count)

    # Preview Data
    with st.expander("👁️ Data Preview (First 50 Rows)", expanded=False):
        st.dataframe(active_df.head(50), use_container_width=True)

    # Column Profiling Details
    profile = profile_dataframe(active_df)
    with st.expander("📊 Column Profiles & Candidate Keys", expanded=True):
        col_summary_rows = []
        for col_name, cp in profile.columns.items():
            col_summary_rows.append({
                "Column": col_name,
                "Inferred Type": cp.inferred_type,
                "Null Count": cp.null_count,
                "Null %": f"{cp.null_percentage}%",
                "Unique Values": cp.unique_count,
                "Candidate ID": "✓ Suggestion" if cp.is_candidate_id else "",
                "Numeric Range": f"[{cp.numeric_min} - {cp.numeric_max}]" if cp.numeric_min is not None else "N/A",
            })
        st.dataframe(pd.DataFrame(col_summary_rows), use_container_width=True, hide_index=True)

    # Rule Configuration & Execution
    st.markdown("---")
    st.subheader("⚙️ Audit Rule Configuration")

    col_cfg1, col_cfg2 = st.columns(2)
    with col_cfg1:
        id_candidates = list(active_df.columns)
        auto_id = profile.candidate_id_columns[0] if profile.candidate_id_columns else None
        if not auto_id:
            for c in active_df.columns:
                if str(c).lower().endswith("_id") or str(c).lower() == "id":
                    auto_id = c
                    break

        default_id_idx = id_candidates.index(auto_id) if auto_id in id_candidates else 0
        sel_id_col = st.selectbox(
            "Primary Key / Identifier Column (for Rule B Collision Check)",
            id_candidates,
            index=default_id_idx,
        )

    with col_cfg2:
        req_cols = st.multiselect(
            "Required Columns (cannot be blank/null)",
            list(active_df.columns),
            default=[c for c in active_df.columns if any(x in str(c).lower() for x in ["email", "name", "date", "sku", "status"]) and "lifetime" not in str(c).lower()],
        )

    if related_dfs:
        st.markdown(
            f"**Foreign Key Audits Active ({len(related_dfs)} relationship{'s' if len(related_dfs) > 1 else ''}):**"
        )
        for parent_t, (_, c_fk, p_pk) in related_dfs.items():
            st.markdown(f"- `{dataset_name}.{c_fk}` ➔ `{parent_t}.{p_pk}`")

    # Run Scan Button
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔎 Launch Forensic Audit Scan", type="primary", use_container_width=True):
        scan_id = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        ds_id = f"ds_{Path(source_path).stem}_{datetime.now().strftime('%H%M%S')}"

        with st.spinner("Executing deterministic audit rules..."):
            # 1. Register Dataset
            dataset_meta = DatasetMetadata(
                dataset_id=ds_id,
                dataset_name=dataset_name or "Audit Dataset",
                source_type=source_type,
                source_path=source_path,
                table_name=table_name,
                row_count=len(active_df),
                column_count=len(active_df.columns),
                columns=list(active_df.columns),
                column_types={c: str(active_df[c].dtype) for c in active_df.columns},
                created_at=datetime.now().isoformat(),
            )
            save_dataset(dataset_meta)

            # 2. Run Comprehensive Scan
            scan_config = {
                "id_columns": [sel_id_col] if sel_id_col else [],
                "required_columns": req_cols,
            }
            scan_record, findings = run_comprehensive_audit(
                df=active_df,
                scan_id=scan_id,
                dataset_id=ds_id,
                table_name=table_name or dataset_name,
                related_dfs=related_dfs if related_dfs else None,
                configured_rules=scan_config,
            )

            # 3. Save Scan and Findings
            save_scan(scan_record)
            for f in findings:
                save_finding(f)

            # 4. Audit Log
            add_audit_log(
                "SCAN_COMPLETED",
                scan_id,
                {
                    "dataset_id": ds_id,
                    "findings_count": len(findings),
                    "table_name": table_name,
                },
            )

            # Cache current dataframe in session for remediation workflow
            st.session_state["current_scanned_df"] = active_df
            st.session_state["current_dataset_id"] = ds_id
            st.session_state["current_scan_id"] = scan_id
            st.session_state["current_dataset_name"] = dataset_name

            st.success(f"Audit completed! Detected {len(findings)} anomalies across {len(scan_record.rules_run)} rules.")

            c_act1, c_act2 = st.columns(2)
            with c_act1:
                if st.button("📋 View in Investigations Panel", use_container_width=True):
                    st.switch_page("pages/3_Investigations.py")
            with c_act2:
                if st.button("🛠️ Review Safe Remediation Proposals", use_container_width=True):
                    st.switch_page("pages/4_Fix_Preview.py")
