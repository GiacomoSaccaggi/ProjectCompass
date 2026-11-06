"""Code-aware document chunker for RAG indexing.

Thin wrapper around scomp_link.llm.rag.chunking — all logic lives in scomp-link.
"""
from scomp_link.llm.rag.chunking import (
    Chunk,
    chunk_directory,
    chunk_file,
    chunk_markdown,
    chunk_python,
    chunk_sql,
    chunk_text,
    chunk_yaml,
)

# Alias for ProjectCompass convention
chunk_analysis = chunk_directory


def chunk_comments(analysis_name: str) -> list[Chunk]:
    """Chunk database comments for an analysis (ProjectCompass-specific)."""
    try:
        from models import Comment
        comments = Comment.query.filter_by(analysis_name=analysis_name).order_by(Comment.created_at.desc()).all()
        return [
            Chunk(
                text=c.text,
                source_file='[comments]',
                chunk_type='comment',
                start_line=0,
                end_line=0,
                metadata={'comment_id': c.id, 'created_at': str(c.created_at)},
            )
            for c in comments
        ]
    except Exception:
        return []


__all__ = [
    'Chunk', 'chunk_analysis', 'chunk_comments', 'chunk_directory',
    'chunk_file', 'chunk_python', 'chunk_yaml', 'chunk_markdown',
    'chunk_sql', 'chunk_text',
]
