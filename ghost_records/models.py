"""Domain models and schemas for Ghost Records."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """Transparent severity levels."""

    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFO = "Info"


class FindingStatus(str, Enum):
    """Lifecycle status of a finding."""

    NEW = "New"
    INVESTIGATING = "Investigating"
    FIX_PROPOSED = "Fix proposed"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    RESOLVED = "Resolved"
    DISMISSED = "Dismissed"


class RemediationApproval(str, Enum):
    """Approval state for a remediation proposal."""

    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"


@dataclass
class DatasetMetadata:
    """Represents an imported CSV file or SQLite table."""

    dataset_id: str
    dataset_name: str
    source_type: str  # 'csv' or 'sqlite'
    source_path: str
    table_name: str | None = None
    row_count: int = 0
    column_count: int = 0
    columns: list[str] = field(default_factory=list)
    column_types: dict[str, str] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_scanned_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DatasetMetadata":
        if isinstance(data.get("columns"), str):
            data["columns"] = json.loads(data["columns"])
        if isinstance(data.get("column_types"), str):
            data["column_types"] = json.loads(data["column_types"])
        return cls(**data)


@dataclass
class ScanRecord:
    """Represents a completed or ongoing data audit scan."""

    scan_id: str
    dataset_id: str
    started_at: str
    completed_at: str | None = None
    status: str = "completed"  # 'running', 'completed', 'failed'
    rules_run: list[str] = field(default_factory=list)
    total_anomalies: int = 0
    error_summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScanRecord":
        if isinstance(data.get("rules_run"), str):
            data["rules_run"] = json.loads(data["rules_run"])
        return cls(**data)


@dataclass
class Finding:
    """Represents a discrete anomaly detected by deterministic rules."""

    finding_id: str
    scan_id: str
    dataset_id: str
    rule_id: str
    rule_name: str
    severity: Severity
    affected_rows_count: int
    affected_row_indices: list[int]
    evidence: dict[str, Any]
    table_name: str | None = None
    status: FindingStatus = FindingStatus.NEW
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value if isinstance(self.severity, Severity) else str(self.severity)
        d["status"] = self.status.value if isinstance(self.status, FindingStatus) else str(self.status)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Finding":
        if isinstance(data.get("affected_row_indices"), str):
            data["affected_row_indices"] = json.loads(data["affected_row_indices"])
        if isinstance(data.get("evidence"), str):
            data["evidence"] = json.loads(data["evidence"])
        if "severity" in data and not isinstance(data["severity"], Severity):
            data["severity"] = Severity(data["severity"])
        if "status" in data and not isinstance(data["status"], FindingStatus):
            data["status"] = FindingStatus(data["status"])
        return cls(**data)


@dataclass
class AIExplanation:
    """Evidence-grounded explanation produced by local Ollama/Gemma."""

    finding_id: str
    model_identifier: str
    summary: str
    why_flagged: str
    likely_explanations: list[str]
    verification_steps: list[str]
    recommended_remediation: str
    confidence_statement: str
    raw_response: str | None = None
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    is_error: bool = False
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AIExplanation":
        if isinstance(data.get("likely_explanations"), str):
            data["likely_explanations"] = json.loads(data["likely_explanations"])
        if isinstance(data.get("verification_steps"), str):
            data["verification_steps"] = json.loads(data["verification_steps"])
        return cls(**data)


@dataclass
class RemediationProposal:
    """A safe, reviewable remediation proposal targeting derived copies."""

    remediation_id: str
    finding_id: str
    dataset_id: str
    action_type: str  # e.g., 'DEDUPLICATE_ROWS', 'QUARANTINE_ORPHANS', 'FILL_MISSING', 'STANDARDIZE_DATES'
    action_title: str
    action_description: str
    affected_rows_count: int
    before_preview: list[dict[str, Any]]
    after_preview: list[dict[str, Any]]
    approval_status: RemediationApproval = RemediationApproval.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    decided_at: str | None = None
    derived_file_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["approval_status"] = (
            self.approval_status.value
            if isinstance(self.approval_status, RemediationApproval)
            else str(self.approval_status)
        )
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RemediationProposal":
        if isinstance(data.get("before_preview"), str):
            data["before_preview"] = json.loads(data["before_preview"])
        if isinstance(data.get("after_preview"), str):
            data["after_preview"] = json.loads(data["after_preview"])
        if "approval_status" in data and not isinstance(data["approval_status"], RemediationApproval):
            data["approval_status"] = RemediationApproval(data["approval_status"])
        return cls(**data)


@dataclass
class AuditLogEntry:
    """Immutable audit trail of all auditor actions."""

    entry_id: str
    timestamp: str
    action_type: str
    target_id: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditLogEntry":
        if isinstance(data.get("details"), str):
            data["details"] = json.loads(data["details"])
        return cls(**data)
