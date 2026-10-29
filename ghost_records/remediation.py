"""Safe remediation workflow targeting derived working copies without altering source data."""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from ghost_records.config import CONFIG
from ghost_records.database import (
    add_audit_log,
    save_remediation,
    update_finding_status,
    update_remediation_approval,
)
from ghost_records.models import (
    Finding,
    FindingStatus,
    RemediationApproval,
    RemediationProposal,
)


def generate_remediation_proposal(finding: Finding, df: pd.DataFrame) -> RemediationProposal:
    """Generate a reviewable, non-destructive remediation proposal based on finding evidence."""
    rem_id = f"rem_{uuid.uuid4().hex[:10]}"
    rule_id = finding.rule_id
    affected_indices = finding.affected_row_indices
    evidence = finding.evidence or {}

    before_preview: list[dict[str, Any]] = []
    after_preview: list[dict[str, Any]] = []
    action_type = "REVIEW_RECORDS"
    action_title = "Manual Review"
    action_desc = "Inspect records manually before making changes."

    if rule_id == "RULE_A_EXACT_DUP":
        action_type = "DEDUPLICATE_ROWS"
        action_title = "Deduplicate Exact Rows"
        action_desc = (
            "Deduplicate identical rows in a derived working copy, retaining the first instance "
            "of each cluster. Original dataset remains untouched."
        )
        # Sample before: duplicate rows
        sample_indices = affected_indices[:4]
        for idx in sample_indices:
            if idx < len(df):
                row = df.iloc[idx].to_dict()
                clean_row = {k: (None if pd.isna(v) else str(v)) for k, v in row.items()}
                clean_row["_row_index"] = idx
                before_preview.append(clean_row)

        # Sample after: deduplicated slice
        if sample_indices:
            sub = df.iloc[sample_indices].drop_duplicates()
            for idx in sub.index:
                row = sub.loc[idx].to_dict()
                clean_row = {k: (None if pd.isna(v) else str(v)) for k, v in row.items()}
                clean_row["_action"] = "Retained 1 unique copy"
                after_preview.append(clean_row)

    elif rule_id == "RULE_B_DUP_ID":
        id_col = evidence.get("identifier_column", "id")
        action_type = "QUARANTINE_CONFLICTING_IDS"
        action_title = f"Quarantine Conflicting Identifiers ({id_col})"
        action_desc = (
            f"Isolate rows with colliding '{id_col}' primary keys into a quarantine dataset for investigation. "
            "The derived clean copy will exclude unverified conflicting keys."
        )
        sample_indices = affected_indices[:4]
        for idx in sample_indices:
            if idx < len(df):
                row = df.iloc[idx].to_dict()
                clean_row = {k: (None if pd.isna(v) else str(v)) for k, v in row.items()}
                clean_row["_row_index"] = idx
                before_preview.append(clean_row)
        after_preview.append({
            "status": "Quarantine Action",
            "conflicting_count": len(affected_indices),
            "detail": f"{len(affected_indices)} colliding rows routed to separate quarantine file.",
        })

    elif rule_id == "RULE_C_ORPHAN_FK":
        fk_col = evidence.get("child_foreign_key_column", "foreign_key")
        parent_tbl = evidence.get("parent_table", "parent")
        action_type = "QUARANTINE_ORPHANS"
        action_title = f"Quarantine Orphaned References ({fk_col} -> {parent_tbl})"
        action_desc = (
            f"Extract orphaned records referencing missing {parent_tbl} entities into an audit quarantine file. "
            "Never invent replacement IDs. Derived clean copy preserves data integrity."
        )
        for idx in affected_indices[:4]:
            if idx < len(df):
                row = df.iloc[idx].to_dict()
                clean_row = {k: (None if pd.isna(v) else str(v)) for k, v in row.items()}
                clean_row["_row_index"] = idx
                clean_row["_missing_parent_id"] = str(clean_row.get(fk_col))
                before_preview.append(clean_row)
        after_preview.append({
            "status": "Quarantined",
            "orphaned_count": len(affected_indices),
            "remediation": "Extracted to isolated quarantine artifact for data steward review.",
        })

    elif rule_id == "RULE_D_MISSING_VAL":
        col = evidence.get("column", "column")
        action_type = "FILL_MISSING_EXPLICIT"
        action_title = f"Fill Missing Values in '{col}'"
        action_desc = (
            f"Populate blank/null entries in '{col}' with an explicit user-approved replacement "
            "or default marker (e.g., 'UNSPECIFIED') in a derived copy."
        )
        for idx in affected_indices[:4]:
            if idx < len(df):
                row = df.iloc[idx].to_dict()
                clean_row = {k: (None if pd.isna(v) else str(v)) for k, v in row.items()}
                clean_row["_row_index"] = idx
                before_preview.append(clean_row)
                # After preview with placeholder
                after_row = dict(clean_row)
                after_row[col] = "[UNSPECIFIED]"
                after_preview.append(after_row)

    elif "RULE_E" in rule_id:
        col = evidence.get("column", "column")
        action_type = "STANDARDIZE_OR_QUARANTINE"
        action_title = f"Sanitize / Quarantine Invalid '{col}'"
        action_desc = (
            f"Quarantine rows with malformed dates or illegal negative numbers in '{col}' into a rejected records file."
        )
        for idx in affected_indices[:4]:
            if idx < len(df):
                row = df.iloc[idx].to_dict()
                clean_row = {k: (None if pd.isna(v) else str(v)) for k, v in row.items()}
                clean_row["_row_index"] = idx
                before_preview.append(clean_row)
        after_preview.append({
            "status": "Quarantined",
            "invalid_count": len(affected_indices),
            "detail": f"{len(affected_indices)} malformed rows quarantined for manual review.",
        })

    elif rule_id == "RULE_F_OUTLIER":
        col = evidence.get("column", "column")
        action_type = "TAG_OUTLIER_COLUMN"
        action_title = f"Tag Outliers in '{col}'"
        action_desc = (
            f"Add a boolean column '_outlier_{col}' to the derived dataset to allow analytical filtering "
            "without deleting legitimate extreme data points."
        )
        for idx in affected_indices[:3]:
            if idx < len(df):
                row = df.iloc[idx].to_dict()
                clean_row = {k: (None if pd.isna(v) else str(v)) for k, v in row.items()}
                clean_row["_row_index"] = idx
                before_preview.append(clean_row)
                after_row = dict(clean_row)
                after_row[f"_outlier_{col}"] = True
                after_preview.append(after_row)

    proposal = RemediationProposal(
        remediation_id=rem_id,
        finding_id=finding.finding_id,
        dataset_id=finding.dataset_id,
        action_type=action_type,
        action_title=action_title,
        action_description=action_desc,
        affected_rows_count=len(affected_indices),
        before_preview=before_preview,
        after_preview=after_preview,
        approval_status=RemediationApproval.PENDING,
    )

    save_remediation(proposal)
    update_finding_status(finding.finding_id, FindingStatus.FIX_PROPOSED)
    add_audit_log(
        "REMEDIATION_PROPOSED",
        rem_id,
        {"finding_id": finding.finding_id, "action_type": action_type, "affected_rows": len(affected_indices)},
    )
    return proposal


def apply_remediation_to_derived_copy(
    df: pd.DataFrame,
    proposal: RemediationProposal,
    finding: Finding,
    dataset_name: str,
    fill_value: str | None = "UNSPECIFIED",
) -> tuple[pd.DataFrame, Path, pd.DataFrame | None, Path | None]:
    """Apply approved remediation to a derived copy only, never touching source files."""
    CONFIG.derived_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{dataset_name}_derived_{proposal.remediation_id[:6]}_{stamp}"

    # Always work on a fresh copy
    clean_df = df.copy()
    quarantine_df: pd.DataFrame | None = None
    affected_idx = finding.affected_row_indices

    if proposal.action_type == "DEDUPLICATE_ROWS":
        # Drop duplicates, keeping the first
        clean_df = clean_df.drop_duplicates()

    elif proposal.action_type in ["QUARANTINE_ORPHANS", "QUARANTINE_CONFLICTING_IDS", "STANDARDIZE_OR_QUARANTINE"]:
        # Isolate affected rows into quarantine DataFrame
        valid_indices = [i for i in affected_idx if i in clean_df.index]
        quarantine_df = clean_df.loc[valid_indices].copy()
        clean_df = clean_df.drop(index=valid_indices)

    elif proposal.action_type == "FILL_MISSING_EXPLICIT":
        col = finding.evidence.get("column")
        if col and col in clean_df.columns:
            val_to_fill = fill_value if fill_value is not None else "UNSPECIFIED"
            # Replace NaN or whitespace
            mask = clean_df[col].isna() | (clean_df[col].astype(str).str.strip() == "")
            clean_df.loc[mask, col] = val_to_fill

    elif proposal.action_type == "TAG_OUTLIER_COLUMN":
        col = finding.evidence.get("column")
        if col:
            tag_col = f"_outlier_{col}"
            clean_df[tag_col] = False
            valid_indices = [i for i in affected_idx if i in clean_df.index]
            clean_df.loc[valid_indices, tag_col] = True

    # Save clean derived CSV
    clean_path = CONFIG.derived_dir / f"{base_name}_clean.csv"
    clean_df.to_csv(clean_path, index=False)

    quarantine_path: Path | None = None
    if quarantine_df is not None and not quarantine_df.empty:
        quarantine_path = CONFIG.derived_dir / f"{base_name}_quarantined.csv"
        quarantine_df.to_csv(quarantine_path, index=False)

    # Update metadata DB
    update_remediation_approval(
        proposal.remediation_id,
        RemediationApproval.APPROVED,
        derived_file=str(clean_path),
    )
    update_finding_status(finding.finding_id, FindingStatus.APPROVED)
    add_audit_log(
        "REMEDIATION_APPROVED",
        proposal.remediation_id,
        {
            "finding_id": finding.finding_id,
            "action_type": proposal.action_type,
            "clean_file": str(clean_path),
            "quarantine_file": str(quarantine_path) if quarantine_path else None,
        },
    )

    return clean_df, clean_path, quarantine_df, quarantine_path


def reject_remediation_proposal(proposal: RemediationProposal, finding_id: str) -> None:
    """Record user rejection of proposed remediation."""
    update_remediation_approval(proposal.remediation_id, RemediationApproval.REJECTED)
    update_finding_status(finding_id, FindingStatus.REJECTED)
    add_audit_log(
        "REMEDIATION_REJECTED",
        proposal.remediation_id,
        {"finding_id": finding_id, "action_type": proposal.action_type},
    )
