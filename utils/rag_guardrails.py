"""Lightweight guardrails for RAG queries and responses.

Thin wrapper around scomp_link.llm.rag.guardrails — all logic lives in scomp-link.
"""
from scomp_link.llm.rag.guardrails import (
    INJECTION_PATTERNS,
    build_rag_prompt,
    format_provenance,
    validate_query,
    validate_response,
)

__all__ = [
    'INJECTION_PATTERNS', 'validate_query', 'validate_response',
    'build_rag_prompt', 'format_provenance',
]
