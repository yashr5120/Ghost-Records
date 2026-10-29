"""Local AI explanation engine using Ollama and Gemma open-weight models."""

from ghost_records.ai.ollama_client import OllamaClient, get_ai_client
from ghost_records.ai.schemas import FindingExplanationSchema

__all__ = ["FindingExplanationSchema", "OllamaClient", "get_ai_client"]
