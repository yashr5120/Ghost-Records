"""Unit tests for safe, non-destructive remediation and derived copies."""

import pandas as pd
import pytest

from ghost_records.database import init_db
from ghost_records.models import Finding, FindingStatus, Severity
from ghost_records.remediation import (
    apply_remediation_to_derived_copy,
    generate_remediation_proposal,
)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_remediation_proposal_leaves_original_df_unchanged():
    original_data = [
        {"id": "1", "name": "Alice"},
        {"id": "1", "name": "Alice"},  # duplicate
    ]
    df = pd.DataFrame(original_data)
    initial_len = len(df)

    finding = Finding(
        finding_id="find_test_dup",
        scan_id="scan_test",
        dataset_id="ds_test",
        rule_id="RULE_A_EXACT_DUP",
        rule_name="Exact Duplicate Rows",
        severity=Severity.MEDIUM,
        affected_rows_count=2,
        affected_row_indices=[0, 1],
        evidence={"sample_clusters": []},
        status=FindingStatus.NEW,
    )

    proposal = generate_remediation_proposal(finding, df)
    assert proposal.action_type == "DEDUPLICATE_ROWS"
    assert len(df) == initial_len  # Original DataFrame untouched

    # Apply to derived copy
    clean_df, clean_path, _, _ = apply_remediation_to_derived_copy(
        df=df,
        proposal=proposal,
        finding=finding,
        dataset_name="test_dataset",
    )

    # Derived copy has 1 row
    assert len(clean_df) == 1
    # Original DataFrame still has 2 rows
    assert len(df) == 2
    assert clean_path.exists()


def test_quarantine_remediation_creates_quarantine_file():
    data = [
        {"order_id": "O1", "cust_id": "VALID"},
        {"order_id": "O2", "cust_id": "ORPHAN_1"},
    ]
    df = pd.DataFrame(data)

    finding = Finding(
        finding_id="find_test_orphan",
        scan_id="scan_test",
        dataset_id="ds_test",
        rule_id="RULE_C_ORPHAN_FK",
        rule_name="Orphaned Foreign Key",
        severity=Severity.HIGH,
        affected_rows_count=1,
        affected_row_indices=[1],
        evidence={"child_foreign_key_column": "cust_id", "parent_table": "customers"},
        status=FindingStatus.NEW,
    )

    proposal = generate_remediation_proposal(finding, df)
    clean_df, clean_path, quar_df, quar_path = apply_remediation_to_derived_copy(
        df=df,
        proposal=proposal,
        finding=finding,
        dataset_name="orders_test",
    )

    assert len(clean_df) == 1
    assert clean_df.iloc[0]["cust_id"] == "VALID"
    assert quar_df is not None
    assert len(quar_df) == 1
    assert quar_df.iloc[0]["cust_id"] == "ORPHAN_1"
    assert quar_path is not None and quar_path.exists()
