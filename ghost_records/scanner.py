"""Deterministic audit rules engine for anomaly detection."""

import hashlib
import re
from datetime import datetime
from typing import Any

import pandas as pd

from ghost_records.models import Finding, FindingStatus, ScanRecord, Severity


def _generate_finding_id(rule_id: str, dataset_id: str, detail_key: str) -> str:
    """Generate a stable, deterministic finding ID."""
    raw = f"{rule_id}:{dataset_id}:{detail_key}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"find_{rule_id.lower()}_{digest}"


def check_exact_duplicates(
    df: pd.DataFrame,
    scan_id: str,
    dataset_id: str,
    table_name: str | None = None,
    subset_columns: list[str] | None = None,
) -> list[Finding]:
    """Rule A: Exact duplicate rows across all (or subset) columns."""
    findings: list[Finding] = []
    if df is None or df.empty:
        return findings

    cols = subset_columns if subset_columns else list(df.columns)
    # Identify duplicated rows (all occurrences including the first)
    is_dup = df.duplicated(subset=cols, keep=False)
    if not is_dup.any():
        return findings

    dup_df = df[is_dup]
    # Group by all columns to find distinct duplicate clusters using original DataFrame indices
    groups = dup_df.groupby(cols, dropna=False).groups

    total_affected_rows = int(is_dup.sum())
    duplicate_groups_count = len(groups)

    evidence_groups: list[dict[str, Any]] = []
    all_affected_indices: list[int] = []

    for group_idx, (group_val, indices) in enumerate(groups.items()):
        indices_list = [int(i) for i in list(indices)]
        all_affected_indices.extend(indices_list)
        if len(evidence_groups) < 10:  # Sample up to 10 duplicate clusters
            sample_row = df.iloc[indices_list[0]].to_dict()
            # Clean non-serializable objects
            clean_sample = {k: (None if pd.isna(v) else str(v)) for k, v in sample_row.items()}
            evidence_groups.append(
                {
                    "cluster_id": group_idx + 1,
                    "row_indices": indices_list,
                    "repeat_count": len(indices_list),
                    "matching_values": clean_sample,
                }
            )

    all_affected_indices.sort()

    fid = _generate_finding_id("RULE_A_EXACT_DUP", dataset_id, f"{table_name}:{total_affected_rows}")
    findings.append(
        Finding(
            finding_id=fid,
            scan_id=scan_id,
            dataset_id=dataset_id,
            table_name=table_name,
            rule_id="RULE_A_EXACT_DUP",
            rule_name="Exact Duplicate Rows",
            severity=Severity.MEDIUM,
            affected_rows_count=total_affected_rows,
            affected_row_indices=all_affected_indices,
            evidence={
                "duplicate_groups_count": duplicate_groups_count,
                "total_affected_rows": total_affected_rows,
                "columns_checked": cols,
                "sample_clusters": evidence_groups,
                "remediation_suggestion": "Review duplicate clusters and keep one authoritative row in derived copy.",
            },
            status=FindingStatus.NEW,
        )
    )
    return findings


def check_duplicate_identifiers(
    df: pd.DataFrame,
    id_column: str,
    scan_id: str,
    dataset_id: str,
    table_name: str | None = None,
) -> list[Finding]:
    """Rule B: Duplicate identifiers in a primary/candidate key column."""
    findings: list[Finding] = []
    if df is None or df.empty or id_column not in df.columns:
        return findings

    series = df[id_column]
    # Filter out nulls/blanks: nulls belong to missing values rule, NOT duplicate identifiers
    non_null_mask = series.notna() & (series.astype(str).str.strip() != "")
    valid_ids = df[non_null_mask]

    dup_mask = valid_ids.duplicated(subset=[id_column], keep=False)
    if not dup_mask.any():
        return findings

    conflicts_df = valid_ids[dup_mask]
    groups = conflicts_df.groupby(id_column).groups

    all_affected_indices: list[int] = []
    sample_conflicts: list[dict[str, Any]] = []

    for val, idx_list in groups.items():
        indices = [int(i) for i in list(idx_list)]
        all_affected_indices.extend(indices)
        if len(sample_conflicts) < 10:
            row_samples = []
            for r_idx in indices[:3]:
                r_dict = df.iloc[r_idx].to_dict()
                clean_r = {k: (None if pd.isna(v) else str(v)) for k, v in r_dict.items()}
                row_samples.append({"row_index": r_idx, "record": clean_r})
            sample_conflicts.append(
                {
                    "identifier_value": str(val),
                    "conflict_count": len(indices),
                    "row_indices": indices,
                    "rows_preview": row_samples,
                }
            )

    all_affected_indices.sort()
    total_affected = len(all_affected_indices)

    fid = _generate_finding_id("RULE_B_DUP_ID", dataset_id, f"{table_name}:{id_column}")
    findings.append(
        Finding(
            finding_id=fid,
            scan_id=scan_id,
            dataset_id=dataset_id,
            table_name=table_name,
            rule_id="RULE_B_DUP_ID",
            rule_name="Duplicate Identifiers (Primary Key Collision)",
            severity=Severity.HIGH,
            affected_rows_count=total_affected,
            affected_row_indices=all_affected_indices,
            evidence={
                "identifier_column": id_column,
                "distinct_conflicting_keys": len(groups),
                "total_affected_rows": total_affected,
                "sample_conflicts": sample_conflicts,
                "remediation_suggestion": "Investigate entity collisions before deduplicating or re-keying.",
            },
            status=FindingStatus.NEW,
        )
    )
    return findings


def check_orphaned_foreign_keys(
    child_df: pd.DataFrame,
    child_fk_column: str,
    parent_df: pd.DataFrame,
    parent_pk_column: str,
    parent_table_name: str,
    scan_id: str,
    dataset_id: str,
    child_table_name: str | None = None,
) -> list[Finding]:
    """Rule C: Orphaned Foreign Keys (child rows pointing to non-existent parent rows)."""
    findings: list[Finding] = []
    if child_df is None or parent_df is None:
        return findings
    if child_fk_column not in child_df.columns or parent_pk_column not in parent_df.columns:
        return findings

    # Respect nullability: do not flag null child foreign keys solely because they are null
    child_non_null = child_df[child_df[child_fk_column].notna()]
    if child_non_null.empty:
        return findings

    # Normalize parent keys to string stripped
    parent_keys = set(parent_df[parent_pk_column].dropna().astype(str).str.strip().unique())

    # Check which child values are missing from parent
    child_str_vals = child_non_null[child_fk_column].astype(str).str.strip()
    is_orphan = ~child_str_vals.isin(parent_keys)

    orphan_df = child_non_null[is_orphan]
    if orphan_df.empty:
        return findings

    affected_indices = [int(i) for i in orphan_df.index.tolist()]
    missing_values = orphan_df[child_fk_column].astype(str).unique().tolist()

    sample_orphans: list[dict[str, Any]] = []
    for r_idx in affected_indices[:10]:
        row_dict = child_df.iloc[r_idx].to_dict()
        clean_row = {k: (None if pd.isna(v) else str(v)) for k, v in row_dict.items()}
        sample_orphans.append(
            {
                "row_index": r_idx,
                "missing_fk_value": str(clean_row.get(child_fk_column)),
                "row_details": clean_row,
            }
        )

    fid = _generate_finding_id(
        "RULE_C_ORPHAN_FK",
        dataset_id,
        f"{child_table_name}:{child_fk_column}->{parent_table_name}:{parent_pk_column}",
    )
    findings.append(
        Finding(
            finding_id=fid,
            scan_id=scan_id,
            dataset_id=dataset_id,
            table_name=child_table_name,
            rule_id="RULE_C_ORPHAN_FK",
            rule_name="Orphaned Foreign Key References",
            severity=Severity.HIGH,
            affected_rows_count=len(affected_indices),
            affected_row_indices=affected_indices,
            evidence={
                "child_table": child_table_name or "current_table",
                "child_foreign_key_column": child_fk_column,
                "parent_table": parent_table_name,
                "parent_primary_key_column": parent_pk_column,
                "total_orphaned_rows": len(affected_indices),
                "distinct_missing_keys_count": len(missing_values),
                "missing_keys_sample": missing_values[:15],
                "sample_orphans": sample_orphans,
                "remediation_suggestion": "Verify missing parent entities or quarantine orphaned rows into separate report.",
            },
            status=FindingStatus.NEW,
        )
    )
    return findings


def check_missing_values(
    df: pd.DataFrame,
    required_columns: list[str],
    scan_id: str,
    dataset_id: str,
    table_name: str | None = None,
) -> list[Finding]:
    """Rule D: Missing-value anomalies in configured required columns."""
    findings: list[Finding] = []
    if df is None or df.empty or not required_columns:
        return findings

    for col in required_columns:
        if col not in df.columns:
            continue
        series = df[col]
        # Detect null, empty string, and whitespace-only
        is_na = series.isna()
        is_empty_str = series.astype(str).str.strip().isin(["", "nan", "none", "null", "undefined"])
        missing_mask = is_na | is_empty_str

        missing_count = int(missing_mask.sum())
        if missing_count == 0:
            continue

        affected_indices = [int(i) for i in df[missing_mask].index.tolist()]
        pct = round((missing_count / len(df)) * 100, 2)

        fid = _generate_finding_id("RULE_D_MISSING_VAL", dataset_id, f"{table_name}:{col}")
        findings.append(
            Finding(
                finding_id=fid,
                scan_id=scan_id,
                dataset_id=dataset_id,
                table_name=table_name,
                rule_id="RULE_D_MISSING_VAL",
                rule_name="Missing Required Values",
                severity=Severity.MEDIUM,
                affected_rows_count=missing_count,
                affected_row_indices=affected_indices,
                evidence={
                    "column": col,
                    "missing_count": missing_count,
                    "missing_percentage": pct,
                    "total_rows": len(df),
                    "sample_row_indices": affected_indices[:10],
                    "remediation_suggestion": "Review affected records. Fill values only with explicit user input.",
                },
                status=FindingStatus.NEW,
            )
        )
    return findings


def check_invalid_dates_and_values(
    df: pd.DataFrame,
    date_columns: list[str] | None = None,
    nonnegative_columns: list[str] | None = None,
    email_columns: list[str] | None = None,
    scan_id: str = "",
    dataset_id: str = "",
    table_name: str | None = None,
) -> list[Finding]:
    """Rule E: Invalid dates, negative values in nonnegative fields, and invalid formats."""
    findings: list[Finding] = []
    if df is None or df.empty:
        return findings

    # Check Date columns
    if date_columns:
        for col in date_columns:
            if col not in df.columns:
                continue
            series = df[col].dropna()
            str_series = series.astype(str).str.strip()
            # Exclude blank strings
            valid_strs = str_series[str_series != ""]
            invalid_indices: list[int] = []
            invalid_samples: list[dict[str, Any]] = []

            for idx, val in valid_strs.items():
                try:
                    dt = pd.to_datetime(val, errors="raise")
                    # Check year bounds (e.g. between 1900 and 2100)
                    if dt.year < 1900 or dt.year > 2100:
                        invalid_indices.append(int(idx))
                        if len(invalid_samples) < 5:
                            invalid_samples.append({"row_index": int(idx), "raw_value": val, "reason": "Year outside bounds (1900-2100)"})
                except Exception:
                    invalid_indices.append(int(idx))
                    if len(invalid_samples) < 5:
                        invalid_samples.append({"row_index": int(idx), "raw_value": val, "reason": "Failed to parse datetime format"})

            if invalid_indices:
                fid = _generate_finding_id("RULE_E_INVALID_DATE", dataset_id, f"{table_name}:{col}")
                findings.append(
                    Finding(
                        finding_id=fid,
                        scan_id=scan_id,
                        dataset_id=dataset_id,
                        table_name=table_name,
                        rule_id="RULE_E_INVALID_DATE",
                        rule_name="Invalid Date Values",
                        severity=Severity.MEDIUM,
                        affected_rows_count=len(invalid_indices),
                        affected_row_indices=invalid_indices,
                        evidence={
                            "column": col,
                            "invalid_count": len(invalid_indices),
                            "sample_invalid_values": invalid_samples,
                            "remediation_suggestion": "Standardize dates only when explicit format is configured, or quarantine records.",
                        },
                        status=FindingStatus.NEW,
                    )
                )

    # Check Nonnegative columns
    if nonnegative_columns:
        for col in nonnegative_columns:
            if col not in df.columns:
                continue
            series = pd.to_numeric(df[col], errors="coerce")
            neg_mask = series < 0
            if neg_mask.any():
                neg_indices = [int(i) for i in df[neg_mask].index.tolist()]
                sample_negs = [
                    {"row_index": i, "value": float(series.loc[i])}
                    for i in neg_indices[:5]
                ]
                fid = _generate_finding_id("RULE_E_NEGATIVE_VAL", dataset_id, f"{table_name}:{col}")
                findings.append(
                    Finding(
                        finding_id=fid,
                        scan_id=scan_id,
                        dataset_id=dataset_id,
                        table_name=table_name,
                        rule_id="RULE_E_NEGATIVE_VAL",
                        rule_name="Negative Value in Nonnegative Column",
                        severity=Severity.HIGH,
                        affected_rows_count=len(neg_indices),
                        affected_row_indices=neg_indices,
                        evidence={
                            "column": col,
                            "negative_count": len(neg_indices),
                            "sample_values": sample_negs,
                            "remediation_suggestion": "Review negative values with business domain owner before zeroing or correcting.",
                        },
                        status=FindingStatus.NEW,
                    )
                )

    # Check Email columns
    if email_columns:
        email_pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
        for col in email_columns:
            if col not in df.columns:
                continue
            series = df[col].dropna().astype(str).str.strip()
            # Only test non-empty strings
            valid_strs = series[series != ""]
            invalid_indices = [int(i) for i, val in valid_strs.items() if not email_pattern.match(val)]
            if invalid_indices:
                samples = [{"row_index": i, "value": str(df.loc[i, col])} for i in invalid_indices[:5]]
                fid = _generate_finding_id("RULE_E_INVALID_EMAIL", dataset_id, f"{table_name}:{col}")
                findings.append(
                    Finding(
                        finding_id=fid,
                        scan_id=scan_id,
                        dataset_id=dataset_id,
                        table_name=table_name,
                        rule_id="RULE_E_INVALID_EMAIL",
                        rule_name="Invalid Email Format",
                        severity=Severity.LOW,
                        affected_rows_count=len(invalid_indices),
                        affected_row_indices=invalid_indices,
                        evidence={
                            "column": col,
                            "invalid_count": len(invalid_indices),
                            "sample_values": samples,
                            "remediation_suggestion": "Validate email address syntax against user directory.",
                        },
                        status=FindingStatus.NEW,
                    )
                )

    return findings


def check_numeric_outliers(
    df: pd.DataFrame,
    numeric_columns: list[str] | None = None,
    scan_id: str = "",
    dataset_id: str = "",
    table_name: str | None = None,
) -> list[Finding]:
    """Rule F: Suspicious numeric outliers using transparent Interquartile Range (IQR)."""
    findings: list[Finding] = []
    if df is None or df.empty:
        return findings

    cols = numeric_columns if numeric_columns else [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

    for col in cols:
        if col not in df.columns or str(col).lower().endswith("_id"):
            continue
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(series) < 8:  # Insufficient sample size for statistical IQR
            continue

        q1 = float(series.quantile(0.25))
        q3 = float(series.quantile(0.75))
        iqr = q3 - q1
        if iqr <= 0:
            continue

        lower_bound = q1 - (1.5 * iqr)
        upper_bound = q3 + (1.5 * iqr)

        outlier_mask = (series < lower_bound) | (series > upper_bound)
        if not outlier_mask.any():
            continue

        outlier_indices = [int(i) for i in series[outlier_mask].index.tolist()]
        sample_outliers = [
            {"row_index": i, "value": float(series.loc[i])}
            for i in outlier_indices[:5]
        ]

        fid = _generate_finding_id("RULE_F_OUTLIER", dataset_id, f"{table_name}:{col}")
        findings.append(
            Finding(
                finding_id=fid,
                scan_id=scan_id,
                dataset_id=dataset_id,
                table_name=table_name,
                rule_id="RULE_F_OUTLIER",
                rule_name="Statistical Outlier (IQR Flag)",
                severity=Severity.INFO,  # Strictly labeled as statistical flag, not confirmed error
                affected_rows_count=len(outlier_indices),
                affected_row_indices=outlier_indices,
                evidence={
                    "column": col,
                    "method": "Interquartile Range (IQR x 1.5)",
                    "q1": round(q1, 2),
                    "q3": round(q3, 2),
                    "iqr": round(iqr, 2),
                    "lower_bound": round(lower_bound, 2),
                    "upper_bound": round(upper_bound, 2),
                    "outlier_count": len(outlier_indices),
                    "sample_outliers": sample_outliers,
                    "remediation_suggestion": "Statistical flag for human review. Verify whether genuine extreme business value.",
                },
                status=FindingStatus.NEW,
            )
        )
    return findings


def run_comprehensive_audit(
    df: pd.DataFrame,
    scan_id: str,
    dataset_id: str,
    table_name: str | None = None,
    related_dfs: dict[str, tuple[pd.DataFrame, str, str]] | None = None,
    configured_rules: dict[str, Any] | None = None,
) -> tuple[ScanRecord, list[Finding]]:
    """Execute all deterministic audit rules across the dataset."""
    started_at = datetime.now().isoformat()
    findings: list[Finding] = []
    rules_run: list[str] = []
    error_summary: str | None = None

    cfg = configured_rules or {}

    try:
        # 1. Rule A: Exact duplicate rows
        rules_run.append("RULE_A_EXACT_DUP")
        findings.extend(check_exact_duplicates(df, scan_id, dataset_id, table_name))

        # 2. Rule B: Duplicate identifiers
        rules_run.append("RULE_B_DUP_ID")
        id_cols = cfg.get("id_columns", [])
        if not id_cols:
            # Auto-detect table primary key column (prefer <table_singular>_id or id)
            tbl_sing = str(table_name or "").lower().rstrip("s")
            candidates = [f"{tbl_sing}_id", f"{str(table_name).lower()}_id", "id"]
            matched_id = None
            for c in df.columns:
                if str(c).lower() in candidates:
                    matched_id = c
                    break
            if matched_id:
                id_cols = [matched_id]
            else:
                # If no direct match, check if first column ends with _id
                for c in df.columns:
                    if str(c).lower().endswith("_id") and not str(c).lower().startswith(("customer", "product", "user", "parent", "fk")):
                        id_cols = [c]
                        break

        for id_col in id_cols:
            findings.extend(check_duplicate_identifiers(df, id_col, scan_id, dataset_id, table_name))

        # 3. Rule C: Orphaned Foreign Keys (if related tables provided)
        if related_dfs:
            rules_run.append("RULE_C_ORPHAN_FK")
            for parent_tbl_name, (parent_df, child_fk_col, parent_pk_col) in related_dfs.items():
                findings.extend(
                    check_orphaned_foreign_keys(
                        child_df=df,
                        child_fk_column=child_fk_col,
                        parent_df=parent_df,
                        parent_pk_column=parent_pk_col,
                        parent_table_name=parent_tbl_name,
                        scan_id=scan_id,
                        dataset_id=dataset_id,
                        child_table_name=table_name,
                    )
                )

        # 4. Rule D: Missing required values
        rules_run.append("RULE_D_MISSING_VAL")
        req_cols = cfg.get("required_columns", [])
        if not req_cols:
            # By default check columns with 'email', 'name', 'date', 'sku', 'status'
            for col in df.columns:
                cl = str(col).lower()
                if any(x in cl for x in ["email", "name", "date", "sku", "status"]) and "lifetime" not in cl:
                    req_cols.append(col)
        findings.extend(check_missing_values(df, req_cols, scan_id, dataset_id, table_name))

        # 5. Rule E: Invalid dates and nonnegative values
        rules_run.append("RULE_E_INVALID_VALUES")
        date_cols = cfg.get("date_columns", [])
        if not date_cols:
            for c in df.columns:
                cl = str(c).lower()
                # Exclude purely numeric columns like lifetime_spend
                if not pd.api.types.is_numeric_dtype(df[c]):
                    if any(x in cl for x in ["_date", "date_", "created_at", "updated_at", "order_date", "timestamp"]) or cl in ["date", "datetime"]:
                        date_cols.append(c)

        nonneg_cols = cfg.get("nonnegative_columns", [])
        if not nonneg_cols:
            for c in df.columns:
                cl = str(c).lower()
                if any(x in cl for x in ["quantity", "price", "amount", "spend", "cost", "stock"]):
                    nonneg_cols.append(c)

        email_cols = cfg.get("email_columns", [])
        if not email_cols:
            email_cols = [c for c in df.columns if "email" in str(c).lower()]

        findings.extend(
            check_invalid_dates_and_values(
                df=df,
                date_columns=date_cols,
                nonnegative_columns=nonneg_cols,
                email_columns=email_cols,
                scan_id=scan_id,
                dataset_id=dataset_id,
                table_name=table_name,
            )
        )

        # 6. Rule F: Numeric outliers
        rules_run.append("RULE_F_OUTLIER")
        findings.extend(check_numeric_outliers(df, None, scan_id, dataset_id, table_name))

    except Exception as ex:
        error_summary = f"Scan encountered rule processing error: {ex!s}"

    completed_at = datetime.now().isoformat()
    scan_record = ScanRecord(
        scan_id=scan_id,
        dataset_id=dataset_id,
        started_at=started_at,
        completed_at=completed_at,
        status="completed" if not error_summary else "failed",
        rules_run=rules_run,
        total_anomalies=len(findings),
        error_summary=error_summary,
    )

    return scan_record, findings
