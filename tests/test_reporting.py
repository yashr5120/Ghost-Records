"""Unit tests for reporting and export engines."""

import pytest

from ghost_records.database import (
    init_db,
    save_dataset,
    save_finding,
    save_scan,
)
from ghost_records.models import (
    DatasetMetadata,
    Finding,
    FindingStatus,
    ScanRecord,
    Severity,
)
from ghost_records.reporting import (
    generate_audit_report_json,
    generate_findings_csv,
)


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_json_and_csv_report_generation(tmp_path):
    scan_id = "scan_rep_test"
    dataset_id = "ds_rep_test"

    ds = DatasetMetadata(
        dataset_id=dataset_id,
        dataset_name="Reports Test Data",
        source_type="csv",
        source_path="test.csv",
        row_count=10,
        column_count=2,
    )
    save_dataset(ds)

    scan = ScanRecord(
        scan_id=scan_id,
        dataset_id=dataset_id,
        started_at="2026-01-01T00:00:00",
        completed_at="2026-01-01T00:01:00",
        total_anomalies=1,
    )
    save_scan(scan)

    finding = Finding(
        finding_id="find_rep_1",
        scan_id=scan_id,
        dataset_id=dataset_id,
        rule_id="RULE_A_EXACT_DUP",
        rule_name="Exact Duplicate Rows",
        severity=Severity.MEDIUM,
        affected_rows_count=2,
        affected_row_indices=[0, 1],
        evidence={"detail": "Duplicate test row"},
        status=FindingStatus.NEW,
    )
    save_finding(finding)

    # Test JSON report
    json_path = tmp_path / "report.json"
    data, out_json = generate_audit_report_json(scan_id, output_path=json_path)
    assert out_json.exists()
    assert data["scan"]["scan_id"] == scan_id
    assert len(data["findings"]) == 1
    assert data["findings"][0]["finding_id"] == "find_rep_1"

    # Test CSV report
    csv_path = tmp_path / "findings.csv"
    df, out_csv = generate_findings_csv(scan_id, output_path=csv_path)
    assert out_csv.exists()
    assert len(df) == 1
    assert "finding_id" in df.columns
    assert "rule_id" in df.columns
    assert "severity" in df.columns
