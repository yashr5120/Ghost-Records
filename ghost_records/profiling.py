"""Deterministic dataset and column profiling."""

import re
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd


@dataclass
class ColumnProfile:
    """Summary statistics for an individual column."""

    column_name: str
    inferred_type: str
    total_count: int
    null_count: int
    null_percentage: float
    blank_or_whitespace_count: int
    unique_count: int
    unique_percentage: float
    is_candidate_id: bool
    numeric_min: float | None = None
    numeric_max: float | None = None
    numeric_mean: float | None = None
    numeric_median: float | None = None
    sample_values: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DatasetProfile:
    """Holistic profile for a dataset or table."""

    row_count: int
    column_count: int
    duplicate_rows_count: int
    candidate_id_columns: list[str]
    potential_fk_columns: list[str]
    columns: dict[str, ColumnProfile]

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_count": self.row_count,
            "column_count": self.column_count,
            "duplicate_rows_count": self.duplicate_rows_count,
            "candidate_id_columns": self.candidate_id_columns,
            "potential_fk_columns": self.potential_fk_columns,
            "columns": {k: v.to_dict() for k, v in self.columns.items()},
        }


def infer_column_type(series: pd.Series) -> str:
    """Infer a human-readable high-level data type."""
    non_null = series.dropna()
    if non_null.empty:
        return "empty"

    dtype_str = str(series.dtype).lower()
    if "int" in dtype_str:
        return "integer"
    if "float" in dtype_str:
        return "float"
    if "bool" in dtype_str:
        return "boolean"
    if "datetime" in dtype_str:
        return "datetime"

    # Check sample of strings
    sample = non_null.astype(str).str.strip().head(50)
    # Check if looks like date
    date_pattern = re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}")
    if sample.apply(lambda x: bool(date_pattern.match(x))).all():
        return "date_string"

    # Check if looks like email
    email_pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    if sample.apply(lambda x: bool(email_pattern.match(x))).all():
        return "email"

    return "text"


def profile_dataframe(df: pd.DataFrame) -> DatasetProfile:
    """Perform deterministic profiling on a pandas DataFrame."""
    if df is None:
        return DatasetProfile(
            row_count=0,
            column_count=0,
            duplicate_rows_count=0,
            candidate_id_columns=[],
            potential_fk_columns=[],
            columns={},
        )

    row_count = len(df)
    column_count = len(df.columns)

    if row_count == 0 or column_count == 0:
        return DatasetProfile(
            row_count=row_count,
            column_count=column_count,
            duplicate_rows_count=0,
            candidate_id_columns=[],
            potential_fk_columns=[],
            columns={},
        )

    duplicate_rows_count = int(df.duplicated(keep=False).sum())
    col_profiles: dict[str, ColumnProfile] = {}
    candidate_id_cols: list[str] = []
    potential_fk_cols: list[str] = []

    for col in df.columns:
        series = df[col]
        total_count = row_count
        null_count = int(series.isna().sum())

        # Check for whitespace/empty strings if text
        blank_count = 0
        if series.dtype == object or pd.api.types.is_string_dtype(series):
            # Count empty string or pure whitespace
            str_series = series.dropna().astype(str)
            blank_count = int((str_series.str.strip() == "").sum())

        null_pct = round((null_count + blank_count) / total_count * 100, 2) if total_count > 0 else 0.0

        # Unique count excluding na
        non_null_series = series.dropna()
        unique_count = int(non_null_series.nunique())
        unique_pct = round(unique_count / total_count * 100, 2) if total_count > 0 else 0.0

        # Candidate ID criteria: 100% unique non-null and 0 nulls, or name matches id/key
        is_candidate_id = False
        if total_count > 0 and null_count == 0 and blank_count == 0 and unique_count == total_count:
            is_candidate_id = True
            candidate_id_cols.append(col)
        elif str(col).lower().endswith("_id") or str(col).lower() == "id":
            # Potential identifier or foreign key
            if is_candidate_id:
                pass
            else:
                potential_fk_cols.append(col)

        inferred = infer_column_type(series)

        # Numeric stats if applicable
        num_min, num_max, num_mean, num_median = None, None, None, None
        if pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series):
            clean_num = series.dropna()
            if not clean_num.empty:
                num_min = float(clean_num.min())
                num_max = float(clean_num.max())
                num_mean = round(float(clean_num.mean()), 2)
                num_median = round(float(clean_num.median()), 2)

        sample_vals = non_null_series.head(5).tolist()

        col_profiles[col] = ColumnProfile(
            column_name=col,
            inferred_type=inferred,
            total_count=total_count,
            null_count=null_count,
            null_percentage=null_pct,
            blank_or_whitespace_count=blank_count,
            unique_count=unique_count,
            unique_percentage=unique_pct,
            is_candidate_id=is_candidate_id,
            numeric_min=num_min,
            numeric_max=num_max,
            numeric_mean=num_mean,
            numeric_median=num_median,
            sample_values=sample_vals,
        )

    return DatasetProfile(
        row_count=row_count,
        column_count=column_count,
        duplicate_rows_count=duplicate_rows_count,
        candidate_id_columns=candidate_id_cols,
        potential_fk_columns=potential_fk_cols,
        columns=col_profiles,
    )
