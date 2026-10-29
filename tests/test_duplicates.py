"""Unit tests for duplicate row and identifier detection rules."""

import pandas as pd

from ghost_records.scanner import (
    check_duplicate_identifiers,
    check_exact_duplicates,
)


def test_exact_duplicates_detected():
    data = [
        {"id": 1, "name": "Alice", "city": "NYC"},
        {"id": 2, "name": "Bob", "city": "LA"},
        {"id": 1, "name": "Alice", "city": "NYC"},  # Duplicate of row 0
    ]
    df = pd.DataFrame(data)
    findings = check_exact_duplicates(df, "scan_1", "ds_1")

    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "RULE_A_EXACT_DUP"
    assert f.affected_rows_count == 2
    assert 0 in f.affected_row_indices
    assert 2 in f.affected_row_indices


def test_unique_rows_not_flagged():
    data = [
        {"id": 1, "name": "Alice", "city": "NYC"},
        {"id": 2, "name": "Bob", "city": "LA"},
        {"id": 3, "name": "Charlie", "city": "Chicago"},
    ]
    df = pd.DataFrame(data)
    findings = check_exact_duplicates(df, "scan_1", "ds_1")
    assert len(findings) == 0


def test_duplicate_identifiers_detected():
    data = [
        {"cust_id": "C-101", "name": "Alice", "phone": "111-222"},
        {"cust_id": "C-102", "name": "Bob", "phone": "333-444"},
        {"cust_id": "C-101", "name": "Alice In Chains", "phone": "555-666"},  # Same ID, diff name
    ]
    df = pd.DataFrame(data)
    findings = check_duplicate_identifiers(df, "cust_id", "scan_1", "ds_1")

    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "RULE_B_DUP_ID"
    assert f.affected_rows_count == 2
    assert "C-101" in str(f.evidence)


def test_null_identifiers_not_treated_as_duplicate_identifiers():
    """Null IDs should not be flagged as colliding duplicate IDs."""
    data = [
        {"cust_id": "C-101", "name": "Alice"},
        {"cust_id": None, "name": "Ghost User 1"},
        {"cust_id": None, "name": "Ghost User 2"},
        {"cust_id": "", "name": "Ghost User 3"},
        {"cust_id": "C-102", "name": "Bob"},
    ]
    df = pd.DataFrame(data)
    findings = check_duplicate_identifiers(df, "cust_id", "scan_1", "ds_1")
    # Must NOT flag None/empty as duplicate identifier collisions
    assert len(findings) == 0
