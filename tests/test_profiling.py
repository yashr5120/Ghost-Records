"""Unit tests for deterministic profiling engine."""

import pandas as pd

from ghost_records.profiling import profile_dataframe


def test_empty_dataframe_profiling():
    df = pd.DataFrame()
    profile = profile_dataframe(df)
    assert profile.row_count == 0
    assert profile.column_count == 0
    assert len(profile.columns) == 0


def test_missing_values_and_whitespace_profiling():
    data = {
        "text_col": ["alpha", "  ", "", None, "beta"],
        "num_col": [10.0, 20.0, None, 40.0, 50.0],
    }
    df = pd.DataFrame(data)
    profile = profile_dataframe(df)

    assert profile.row_count == 5
    assert profile.column_count == 2

    # text_col has 1 None + 2 blanks = 3 null/blank
    text_p = profile.columns["text_col"]
    assert text_p.blank_or_whitespace_count == 2
    assert text_p.null_count == 1
    assert text_p.null_percentage == 60.0

    # num_col has 1 None
    num_p = profile.columns["num_col"]
    assert num_p.null_count == 1
    assert num_p.numeric_min == 10.0
    assert num_p.numeric_max == 50.0
    assert num_p.numeric_mean == 30.0


def test_candidate_identifier_discovery():
    data = {
        "unique_id": ["ID-1", "ID-2", "ID-3"],
        "status": ["active", "active", "pending"],
    }
    df = pd.DataFrame(data)
    profile = profile_dataframe(df)

    assert "unique_id" in profile.candidate_id_columns
    assert "status" not in profile.candidate_id_columns
