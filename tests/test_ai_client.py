"""Unit tests for Ollama client, schema validation, and graceful degradation."""

from unittest.mock import MagicMock, patch

import pytest

from ghost_records.ai.ollama_client import OllamaClient
from ghost_records.ai.schemas import FindingExplanationSchema
from ghost_records.database import init_db
from ghost_records.models import Finding, FindingStatus, Severity


@pytest.fixture(autouse=True)
def setup_db():
    init_db()


def test_schema_validation_success():
    payload = {
        "summary": "Detected 2 orphaned foreign keys.",
        "why_flagged": "Values CUST-9999 not present in customers table.",
        "likely_explanations": ["Customer was deleted", "Typo in order entry"],
        "verification_steps": ["Check primary CRM table", "Confirm order origin"],
        "recommended_remediation": "Quarantine affected rows into review dataset.",
        "confidence_statement": "High confidence based on exact key mismatch.",
    }
    schema = FindingExplanationSchema(**payload)
    assert schema.summary == payload["summary"]
    assert len(schema.likely_explanations) == 2


def test_ollama_offline_graceful_handling():
    # Target an unreachable port
    client = OllamaClient(base_url="http://127.0.0.1:59999", model="nonexistent")
    status = client.check_connection()
    assert status["online"] is False
    assert status["model_installed"] is False

    finding = Finding(
        finding_id="find_mock_01",
        scan_id="scan_mock",
        dataset_id="ds_mock",
        rule_id="RULE_A_EXACT_DUP",
        rule_name="Exact Duplicate Rows",
        severity=Severity.MEDIUM,
        affected_rows_count=2,
        affected_row_indices=[0, 1],
        evidence={},
        status=FindingStatus.NEW,
    )

    # Must return an explanation object with error diagnostic without crashing
    explanation = client.explain_finding(finding)
    assert explanation.is_error is True
    assert "offline" in explanation.error_message.lower() or "cannot connect" in explanation.error_message.lower()


def test_ollama_structured_response_parsing():
    client = OllamaClient(base_url="http://localhost:11434", model="gemma4:e4b")

    mock_resp = {
        "response": """```json
{
  "summary": "Orphaned order records detected.",
  "why_flagged": "Foreign key not in parent table.",
  "likely_explanations": ["Deleted customer"],
  "verification_steps": ["Verify in CRM"],
  "recommended_remediation": "Quarantine rows.",
  "confidence_statement": "100% verified against parent table."
}
```"""
    }

    mock_post = MagicMock()
    mock_post.status_code = 200
    mock_post.json.return_value = mock_resp

    with patch.object(client, "check_connection", return_value={"online": True, "model_installed": True, "available_models": ["gemma4:e4b"]}):
        with patch("requests.post", return_value=mock_post):
            finding = Finding(
                finding_id="find_mock_02",
                scan_id="scan_mock",
                dataset_id="ds_mock",
                rule_id="RULE_C_ORPHAN_FK",
                rule_name="Orphan Foreign Key",
                severity=Severity.HIGH,
                affected_rows_count=1,
                affected_row_indices=[0],
                evidence={"child_foreign_key_column": "customer_id", "parent_table": "customers"},
                status=FindingStatus.NEW,
            )
            explanation = client.explain_finding(finding)
            assert explanation.is_error is False
            assert "Orphaned order" in explanation.summary
            assert len(explanation.likely_explanations) == 1
