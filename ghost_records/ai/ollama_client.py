"""Local Ollama client with robust structured output parsing and graceful degradation."""

import json
import re
import time
from typing import Any

import requests

from ghost_records.ai.prompts import build_evidence_explanation_prompt
from ghost_records.ai.schemas import FindingExplanationSchema
from ghost_records.config import CONFIG
from ghost_records.database import add_audit_log, save_ai_explanation
from ghost_records.models import AIExplanation, Finding


class OllamaClient:
    """Client for locally running Ollama instance."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: int | None = None,
    ):
        self.base_url = (base_url or CONFIG.ollama_base_url).rstrip("/")
        self.model = model or CONFIG.ollama_model
        self.timeout = timeout or CONFIG.ollama_timeout_seconds

    def check_connection(self) -> dict[str, Any]:
        """Check if local Ollama daemon is reachable and inspect installed models."""
        url = f"{self.base_url}/api/tags"
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                # Check if configured model or prefix matches
                model_installed = any(
                    self.model == m or m.startswith(self.model) or self.model.startswith(m.split(":")[0])
                    for m in models
                )
                return {
                    "online": True,
                    "endpoint": self.base_url,
                    "configured_model": self.model,
                    "available_models": models,
                    "model_installed": model_installed,
                    "error": None,
                }
            return {
                "online": False,
                "endpoint": self.base_url,
                "configured_model": self.model,
                "available_models": [],
                "model_installed": False,
                "error": f"Ollama returned HTTP status {resp.status_code}",
            }
        except requests.exceptions.ConnectionError:
            return {
                "online": False,
                "endpoint": self.base_url,
                "configured_model": self.model,
                "available_models": [],
                "model_installed": False,
                "error": f"Cannot connect to local Ollama at {self.base_url}. Ensure 'ollama serve' is running.",
            }
        except Exception as ex:
            return {
                "online": False,
                "endpoint": self.base_url,
                "configured_model": self.model,
                "available_models": [],
                "model_installed": False,
                "error": str(ex),
            }

    def test_inference(self, prompt: str = "Explain what a foreign key is in one concise sentence.") -> dict[str, Any]:
        """Run a lightweight inference test to verify end-to-end model execution."""
        status = self.check_connection()
        if not status["online"]:
            return {
                "success": False,
                "error": status["error"],
                "latency_seconds": 0.0,
                "response": None,
            }
        if not status["model_installed"]:
            return {
                "success": False,
                "error": f"Configured model '{self.model}' is not found in local Ollama. Installed: {status['available_models']}",
                "latency_seconds": 0.0,
                "response": None,
            }

        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 100},
        }

        t0 = time.time()
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            latency = round(time.time() - t0, 2)
            if resp.status_code == 200:
                result_text = resp.json().get("response", "").strip()
                return {
                    "success": True,
                    "error": None,
                    "latency_seconds": latency,
                    "response": result_text,
                }
            return {
                "success": False,
                "error": f"Ollama HTTP error {resp.status_code}: {resp.text}",
                "latency_seconds": latency,
                "response": None,
            }
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": f"Inference timed out after {self.timeout}s on local host.",
                "latency_seconds": round(time.time() - t0, 2),
                "response": None,
            }
        except Exception as ex:
            return {
                "success": False,
                "error": str(ex),
                "latency_seconds": round(time.time() - t0, 2),
                "response": None,
            }

    def explain_finding(self, finding: Finding) -> AIExplanation:
        """Generate an evidence-grounded forensic explanation for a specific finding."""
        diag = self.check_connection()
        if not diag["online"] or not diag["model_installed"]:
            reason = (
                f"Local Ollama is offline at {self.base_url}."
                if not diag["online"]
                else f"Model '{self.model}' is not installed locally. Available: {diag['available_models']}."
            )
            explanation = AIExplanation(
                finding_id=finding.finding_id,
                model_identifier=f"{self.model} (offline)",
                summary=f"Automated deterministic finding: {finding.rule_name} detected across {finding.affected_rows_count} records.",
                why_flagged=f"Rule {finding.rule_id} triggered on table {finding.table_name or 'dataset'}.",
                likely_explanations=["Local AI explanation unavailable because Ollama server/model is offline."],
                verification_steps=["Inspect the raw evidence table in the Investigations panel.", "Verify values directly in source dataset."],
                recommended_remediation="Review proposed fix in Fix Preview tab or perform manual verification.",
                confidence_statement="Deterministic rule engine match (100% confidence on rule condition).",
                raw_response=None,
                is_error=True,
                error_message=reason,
            )
            save_ai_explanation(explanation)
            return explanation

        prompt = build_evidence_explanation_prompt(finding)
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": 500},
        }

        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            if resp.status_code != 200:
                raise RuntimeError(f"Ollama returned HTTP {resp.status_code}: {resp.text}")

            raw_text = resp.json().get("response", "").strip()

            # Attempt to parse structured JSON
            parsed_data = None
            try:
                clean_json_str = raw_text
                # If wrapped in markdown block
                if "```json" in clean_json_str:
                    clean_json_str = clean_json_str.split("```json")[1].split("```")[0].strip()
                elif "```" in clean_json_str:
                    clean_json_str = clean_json_str.split("```")[1].split("```")[0].strip()

                parsed_json = json.loads(clean_json_str)
                schema_obj = FindingExplanationSchema(**parsed_json)
                parsed_data = schema_obj.model_dump()
            except Exception:
                # Fallback: extract with regex
                match = re.search(r"\{.*\}", raw_text, re.DOTALL)
                if match:
                    try:
                        extracted_json = json.loads(match.group(0))
                        schema_obj = FindingExplanationSchema(**extracted_json)
                        parsed_data = schema_obj.model_dump()
                    except Exception:
                        pass

            if parsed_data:
                explanation = AIExplanation(
                    finding_id=finding.finding_id,
                    model_identifier=self.model,
                    summary=parsed_data.get("summary", ""),
                    why_flagged=parsed_data.get("why_flagged", ""),
                    likely_explanations=parsed_data.get("likely_explanations", []),
                    verification_steps=parsed_data.get("verification_steps", []),
                    recommended_remediation=parsed_data.get("recommended_remediation", ""),
                    confidence_statement=parsed_data.get("confidence_statement", ""),
                    raw_response=raw_text,
                    is_error=False,
                )
            else:
                # Graceful degradation to plain text
                explanation = AIExplanation(
                    finding_id=finding.finding_id,
                    model_identifier=self.model,
                    summary="Evidence analysis generated by local AI (unstructured format).",
                    why_flagged=f"Flagged by rule {finding.rule_name}.",
                    likely_explanations=[raw_text[:300]],
                    verification_steps=["Review finding evidence against raw data."],
                    recommended_remediation="Inspect affected rows in Fix Preview.",
                    confidence_statement="Local Gemma output generated without full JSON schema conformancy.",
                    raw_response=raw_text,
                    is_error=False,
                )

            # Persist explanation and audit log
            save_ai_explanation(explanation)
            add_audit_log(
                "AI_EXPLAINED",
                finding.finding_id,
                {"model": self.model, "finding_id": finding.finding_id, "is_error": explanation.is_error},
            )
            return explanation

        except requests.exceptions.Timeout:
            err_msg = f"Local AI inference timed out after {self.timeout}s."
            explanation = AIExplanation(
                finding_id=finding.finding_id,
                model_identifier=self.model,
                summary="AI Explanation timed out.",
                why_flagged=f"Rule {finding.rule_name} triggered on {finding.affected_rows_count} records.",
                likely_explanations=["Inference took longer than timeout threshold."],
                verification_steps=["Check system CPU/RAM usage or increase timeout in Settings."],
                recommended_remediation="Review rule evidence directly in table.",
                confidence_statement="Inference incomplete due to timeout.",
                is_error=True,
                error_message=err_msg,
            )
            save_ai_explanation(explanation)
            return explanation
        except Exception as ex:
            err_msg = f"Local AI error: {ex!s}"
            explanation = AIExplanation(
                finding_id=finding.finding_id,
                model_identifier=self.model,
                summary="AI Explanation error.",
                why_flagged=f"Rule {finding.rule_name} triggered on {finding.affected_rows_count} records.",
                likely_explanations=[f"Error during Ollama generation: {ex!s}"],
                verification_steps=["Inspect local Ollama logs."],
                recommended_remediation="Proceed with deterministic remediation preview.",
                confidence_statement="Inference failed.",
                is_error=True,
                error_message=err_msg,
            )
            save_ai_explanation(explanation)
            return explanation


def get_ai_client(model: str | None = None) -> OllamaClient:
    """Factory for OllamaClient instance."""
    return OllamaClient(model=model)
