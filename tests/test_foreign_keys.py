"""Unit tests for foreign key integrity and orphaned record detection."""

import pandas as pd

from ghost_records.scanner import check_orphaned_foreign_keys


def test_valid_foreign_keys_accepted():
    parents = pd.DataFrame([{"id": "P1", "name": "Alpha"}, {"id": "P2", "name": "Beta"}])
    children = pd.DataFrame([{"child_id": "C1", "parent_id": "P1"}, {"child_id": "C2", "parent_id": "P2"}])

    findings = check_orphaned_foreign_keys(
        child_df=children,
        child_fk_column="parent_id",
        parent_df=parents,
        parent_pk_column="id",
        parent_table_name="parents",
        scan_id="s1",
        dataset_id="d1",
        child_table_name="children",
    )
    assert len(findings) == 0


def test_missing_parent_references_detected():
    parents = pd.DataFrame([{"id": "P1", "name": "Alpha"}])
    children = pd.DataFrame([
        {"child_id": "C1", "parent_id": "P1"},
        {"child_id": "C2", "parent_id": "GHOST-999"},  # Missing
        {"child_id": "C3", "parent_id": "GHOST-888"},  # Missing
    ])

    findings = check_orphaned_foreign_keys(
        child_df=children,
        child_fk_column="parent_id",
        parent_df=parents,
        parent_pk_column="id",
        parent_table_name="parents",
        scan_id="s1",
        dataset_id="d1",
        child_table_name="children",
    )
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "RULE_C_ORPHAN_FK"
    assert f.affected_rows_count == 2
    assert 1 in f.affected_row_indices
    assert 2 in f.affected_row_indices
    assert "GHOST-999" in f.evidence["missing_keys_sample"]


def test_nullable_foreign_keys_not_falsely_flagged():
    """Null foreign keys represent optional relationships and must not be flagged as orphans."""
    parents = pd.DataFrame([{"id": "P1", "name": "Alpha"}])
    children = pd.DataFrame([
        {"child_id": "C1", "parent_id": "P1"},
        {"child_id": "C2", "parent_id": None},  # Nullable optional link
    ])

    findings = check_orphaned_foreign_keys(
        child_df=children,
        child_fk_column="parent_id",
        parent_df=parents,
        parent_pk_column="id",
        parent_table_name="parents",
        scan_id="s1",
        dataset_id="d1",
        child_table_name="children",
    )
    assert len(findings) == 0


def test_empty_parent_table_flags_all_non_null_children():
    parents = pd.DataFrame(columns=["id", "name"])
    children = pd.DataFrame([{"child_id": "C1", "parent_id": "P1"}])

    findings = check_orphaned_foreign_keys(
        child_df=children,
        child_fk_column="parent_id",
        parent_df=parents,
        parent_pk_column="id",
        parent_table_name="parents",
        scan_id="s1",
        dataset_id="d1",
    )
    assert len(findings) == 1
    assert findings[0].affected_rows_count == 1
