"""SQLite metadata store for persistent scan history and audit tracking."""

import json
import sqlite3
import uuid
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from ghost_records.config import CONFIG
from ghost_records.models import (
    AIExplanation,
    AuditLogEntry,
    DatasetMetadata,
    Finding,
    FindingStatus,
    RemediationApproval,
    RemediationProposal,
    ScanRecord,
    Severity,
)


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """Provide a transactional scope around database operations."""
    conn = sqlite3.connect(str(CONFIG.metadata_db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Initialize SQLite tables for persistent metadata."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Datasets
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS datasets (
                dataset_id TEXT PRIMARY KEY,
                dataset_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_path TEXT NOT NULL,
                table_name TEXT,
                row_count INTEGER DEFAULT 0,
                column_count INTEGER DEFAULT 0,
                columns TEXT NOT NULL,
                column_types TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_scanned_at TEXT
            )
            """
        )

        # Scans
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS scans (
                scan_id TEXT PRIMARY KEY,
                dataset_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                rules_run TEXT NOT NULL,
                total_anomalies INTEGER DEFAULT 0,
                error_summary TEXT,
                FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE
            )
            """
        )

        # Findings
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS findings (
                finding_id TEXT PRIMARY KEY,
                scan_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                rule_name TEXT NOT NULL,
                severity TEXT NOT NULL,
                affected_rows_count INTEGER DEFAULT 0,
                affected_row_indices TEXT NOT NULL,
                evidence TEXT NOT NULL,
                table_name TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (scan_id) REFERENCES scans(scan_id) ON DELETE CASCADE,
                FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE
            )
            """
        )

        # AI Explanations
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_explanations (
                finding_id TEXT PRIMARY KEY,
                model_identifier TEXT NOT NULL,
                summary TEXT NOT NULL,
                why_flagged TEXT NOT NULL,
                likely_explanations TEXT NOT NULL,
                verification_steps TEXT NOT NULL,
                recommended_remediation TEXT NOT NULL,
                confidence_statement TEXT NOT NULL,
                raw_response TEXT,
                generated_at TEXT NOT NULL,
                is_error INTEGER DEFAULT 0,
                error_message TEXT,
                FOREIGN KEY (finding_id) REFERENCES findings(finding_id) ON DELETE CASCADE
            )
            """
        )

        # Remediation Proposals
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS remediations (
                remediation_id TEXT PRIMARY KEY,
                finding_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                action_title TEXT NOT NULL,
                action_description TEXT NOT NULL,
                affected_rows_count INTEGER DEFAULT 0,
                before_preview TEXT NOT NULL,
                after_preview TEXT NOT NULL,
                approval_status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                decided_at TEXT,
                derived_file_path TEXT,
                FOREIGN KEY (finding_id) REFERENCES findings(finding_id) ON DELETE CASCADE,
                FOREIGN KEY (dataset_id) REFERENCES datasets(dataset_id) ON DELETE CASCADE
            )
            """
        )

        # Audit Log
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                entry_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                action_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                details TEXT NOT NULL
            )
            """
        )

        # Indexes for query performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_scan_id ON findings(scan_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_dataset_id ON findings(dataset_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_status ON findings(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_findings_severity ON findings(severity)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_scans_dataset_id ON scans(dataset_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(timestamp)")


def save_dataset(dataset: DatasetMetadata) -> None:
    """Insert or replace a dataset record."""
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO datasets (
                dataset_id, dataset_name, source_type, source_path, table_name,
                row_count, column_count, columns, column_types, created_at, last_scanned_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dataset.dataset_id,
                dataset.dataset_name,
                dataset.source_type,
                dataset.source_path,
                dataset.table_name,
                dataset.row_count,
                dataset.column_count,
                json.dumps(dataset.columns),
                json.dumps(dataset.column_types),
                dataset.created_at,
                dataset.last_scanned_at,
            ),
        )


def get_dataset(dataset_id: str) -> DatasetMetadata | None:
    """Retrieve dataset by ID."""
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM datasets WHERE dataset_id = ?", (dataset_id,)).fetchone()
        if not row:
            return None
        return DatasetMetadata.from_dict(dict(row))


def list_datasets() -> list[DatasetMetadata]:
    """List all registered datasets sorted by created timestamp descending."""
    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM datasets ORDER BY created_at DESC").fetchall()
        return [DatasetMetadata.from_dict(dict(r)) for r in rows]


def save_scan(scan: ScanRecord) -> None:
    """Insert or replace a scan record."""
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO scans (
                scan_id, dataset_id, started_at, completed_at, status, rules_run, total_anomalies, error_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scan.scan_id,
                scan.dataset_id,
                scan.started_at,
                scan.completed_at,
                scan.status,
                json.dumps(scan.rules_run),
                scan.total_anomalies,
                scan.error_summary,
            ),
        )
        if scan.completed_at:
            conn.execute(
                "UPDATE datasets SET last_scanned_at = ? WHERE dataset_id = ?",
                (scan.completed_at, scan.dataset_id),
            )


def get_scan(scan_id: str) -> ScanRecord | None:
    """Retrieve scan by ID."""
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM scans WHERE scan_id = ?", (scan_id,)).fetchone()
        if not row:
            return None
        return ScanRecord.from_dict(dict(row))


def list_scans(limit: int = 50) -> list[ScanRecord]:
    """List recent scans ordered by start time descending."""
    with get_db_connection() as conn:
        rows = conn.execute("SELECT * FROM scans ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        return [ScanRecord.from_dict(dict(r)) for r in rows]


def save_finding(finding: Finding) -> None:
    """Insert or replace a finding record."""
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO findings (
                finding_id, scan_id, dataset_id, rule_id, rule_name, severity,
                affected_rows_count, affected_row_indices, evidence, table_name,
                status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                finding.finding_id,
                finding.scan_id,
                finding.dataset_id,
                finding.rule_id,
                finding.rule_name,
                finding.severity.value if isinstance(finding.severity, Severity) else str(finding.severity),
                finding.affected_rows_count,
                json.dumps(finding.affected_row_indices),
                json.dumps(finding.evidence),
                finding.table_name,
                finding.status.value if isinstance(finding.status, FindingStatus) else str(finding.status),
                finding.created_at,
            ),
        )


def get_finding(finding_id: str) -> Finding | None:
    """Retrieve finding by ID."""
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM findings WHERE finding_id = ?", (finding_id,)).fetchone()
        if not row:
            return None
        return Finding.from_dict(dict(row))


def list_findings(
    scan_id: str | None = None,
    dataset_id: str | None = None,
    severity: str | None = None,
    status: str | None = None,
) -> list[Finding]:
    """Filter and retrieve findings."""
    query = "SELECT * FROM findings WHERE 1=1"
    params: list[Any] = []

    if scan_id:
        query += " AND scan_id = ?"
        params.append(scan_id)
    if dataset_id:
        query += " AND dataset_id = ?"
        params.append(dataset_id)
    if severity:
        query += " AND severity = ?"
        params.append(severity)
    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY created_at DESC"

    with get_db_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        return [Finding.from_dict(dict(r)) for r in rows]


def update_finding_status(finding_id: str, status: FindingStatus) -> None:
    """Update status of a specific finding."""
    status_str = status.value if isinstance(status, FindingStatus) else str(status)
    with get_db_connection() as conn:
        conn.execute("UPDATE findings SET status = ? WHERE finding_id = ?", (status_str, finding_id))


def save_ai_explanation(explanation: AIExplanation) -> None:
    """Insert or replace an AI explanation."""
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO ai_explanations (
                finding_id, model_identifier, summary, why_flagged, likely_explanations,
                verification_steps, recommended_remediation, confidence_statement,
                raw_response, generated_at, is_error, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                explanation.finding_id,
                explanation.model_identifier,
                explanation.summary,
                explanation.why_flagged,
                json.dumps(explanation.likely_explanations),
                json.dumps(explanation.verification_steps),
                explanation.recommended_remediation,
                explanation.confidence_statement,
                explanation.raw_response,
                explanation.generated_at,
                1 if explanation.is_error else 0,
                explanation.error_message,
            ),
        )


def get_ai_explanation(finding_id: str) -> AIExplanation | None:
    """Retrieve explanation for a finding."""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM ai_explanations WHERE finding_id = ?", (finding_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["is_error"] = bool(d.get("is_error", 0))
        return AIExplanation.from_dict(d)


def save_remediation(remediation: RemediationProposal) -> None:
    """Insert or replace a remediation proposal."""
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO remediations (
                remediation_id, finding_id, dataset_id, action_type, action_title,
                action_description, affected_rows_count, before_preview, after_preview,
                approval_status, created_at, decided_at, derived_file_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                remediation.remediation_id,
                remediation.finding_id,
                remediation.dataset_id,
                remediation.action_type,
                remediation.action_title,
                remediation.action_description,
                remediation.affected_rows_count,
                json.dumps(remediation.before_preview),
                json.dumps(remediation.after_preview),
                (
                    remediation.approval_status.value
                    if isinstance(remediation.approval_status, RemediationApproval)
                    else str(remediation.approval_status)
                ),
                remediation.created_at,
                remediation.decided_at,
                remediation.derived_file_path,
            ),
        )


def get_remediation_by_finding(finding_id: str) -> RemediationProposal | None:
    """Retrieve proposal by finding ID."""
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM remediations WHERE finding_id = ?", (finding_id,)
        ).fetchone()
        if not row:
            return None
        return RemediationProposal.from_dict(dict(row))


def list_remediations(dataset_id: str | None = None) -> list[RemediationProposal]:
    """List all remediation proposals."""
    query = "SELECT * FROM remediations"
    params: list[Any] = []
    if dataset_id:
        query += " WHERE dataset_id = ?"
        params.append(dataset_id)
    query += " ORDER BY created_at DESC"

    with get_db_connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        return [RemediationProposal.from_dict(dict(r)) for r in rows]


def update_remediation_approval(
    remediation_id: str,
    approval: RemediationApproval,
    derived_file: str | None = None,
) -> None:
    """Update approval status and record timestamp."""
    approval_str = approval.value if isinstance(approval, RemediationApproval) else str(approval)
    now_str = datetime.now().isoformat()
    with get_db_connection() as conn:
        if derived_file:
            conn.execute(
                """
                UPDATE remediations
                SET approval_status = ?, decided_at = ?, derived_file_path = ?
                WHERE remediation_id = ?
                """,
                (approval_str, now_str, derived_file, remediation_id),
            )
        else:
            conn.execute(
                """
                UPDATE remediations
                SET approval_status = ?, decided_at = ?
                WHERE remediation_id = ?
                """,
                (approval_str, now_str, remediation_id),
            )


def add_audit_log(action_type: str, target_id: str, details: dict[str, Any]) -> None:
    """Append an immutable audit entry."""
    entry_id = f"audit_{uuid.uuid4().hex[:12]}"
    now_str = datetime.now().isoformat()
    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO audit_logs (entry_id, timestamp, action_type, target_id, details)
            VALUES (?, ?, ?, ?, ?)
            """,
            (entry_id, now_str, action_type, target_id, json.dumps(details)),
        )


def list_audit_logs(limit: int = 100) -> list[AuditLogEntry]:
    """Retrieve audit log entries in reverse chronological order."""
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [AuditLogEntry.from_dict(dict(r)) for r in rows]


def get_dashboard_stats() -> dict[str, Any]:
    """Calculate real, un-fabricated dashboard metrics directly from the metadata DB."""
    with get_db_connection() as conn:
        total_datasets = conn.execute("SELECT COUNT(*) FROM datasets").fetchone()[0]
        total_anomalies = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]

        high_critical = conn.execute(
            "SELECT COUNT(*) FROM findings WHERE severity IN ('Critical', 'High')"
        ).fetchone()[0]

        resolved_dismissed = conn.execute(
            "SELECT COUNT(*) FROM findings WHERE status IN ('Resolved', 'Dismissed')"
        ).fetchone()[0]

        latest_scan_row = conn.execute(
            "SELECT started_at FROM scans ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        latest_scan = latest_scan_row[0] if latest_scan_row else None

        # Severity breakdown
        sev_rows = conn.execute(
            "SELECT severity, COUNT(*) FROM findings GROUP BY severity"
        ).fetchall()
        severity_dist = {r[0]: r[1] for r in sev_rows}

        # Rule / category breakdown
        cat_rows = conn.execute(
            "SELECT rule_name, COUNT(*) FROM findings GROUP BY rule_name"
        ).fetchall()
        category_dist = {r[0]: r[1] for r in cat_rows}

        # Status breakdown
        stat_rows = conn.execute(
            "SELECT status, COUNT(*) FROM findings GROUP BY status"
        ).fetchall()
        status_dist = {r[0]: r[1] for r in stat_rows}

        # Recent scans
        recent_scans_raw = conn.execute(
            """
            SELECT s.scan_id, s.started_at, s.status, s.total_anomalies, d.dataset_name
            FROM scans s
            LEFT JOIN datasets d ON s.dataset_id = d.dataset_id
            ORDER BY s.started_at DESC LIMIT 5
            """
        ).fetchall()
        recent_scans = [dict(r) for r in recent_scans_raw]

        return {
            "total_datasets": total_datasets,
            "total_anomalies": total_anomalies,
            "high_critical_findings": high_critical,
            "resolved_dismissed_findings": resolved_dismissed,
            "latest_scan_timestamp": latest_scan,
            "severity_distribution": severity_dist,
            "category_distribution": category_dist,
            "status_distribution": status_dist,
            "recent_scans": recent_scans,
        }
