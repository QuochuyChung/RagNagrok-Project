"""
Debug helpers for the chunking pipeline.
Helps with saving debug markdown and chunk text files for inspection.
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.documents import Document

DEBUG_DOCS_DIR = Path("storage/documents")

class ChunkerDebug:
    """Debug helpers for the chunking pipeline."""

    @staticmethod
    def debug_stage_path(source_filepath: str, stage: str) -> Path:
        """Return the debug markdown path for a source file and processing stage."""
        DEBUG_DOCS_DIR.mkdir(parents=True, exist_ok=True)
        src = Path(source_filepath)
        return DEBUG_DOCS_DIR / f"{src.stem}.{stage}.debug.md"

    @staticmethod
    def save_debug_markdown(source_filepath: str, stage: str, content: str) -> Path:
        """Write debug markdown content for a processing stage and return its path."""
        debug_path = ChunkerDebug.debug_stage_path(source_filepath, stage)
        debug_path.write_text(content, encoding="utf-8")
        return debug_path

    @staticmethod
    def save_chunks_to_txt(chunks: list[Document], source_filepath: str) -> None:
        """Dump chunks with metadata to a text file for manual inspection."""
        DEBUG_DOCS_DIR.mkdir(parents=True, exist_ok=True)
        src = Path(source_filepath)
        debug_path = DEBUG_DOCS_DIR / f"{src.stem}.chunks.txt"
        lines = []
        for i, c in enumerate(chunks):
            lines.append(f"=== chunk {i} ===")
            lines.append(f"metadata: {c.metadata}")
            lines.append(f"length: {len(c.page_content)} ký tự")
            lines.append("content:")
            lines.append(c.page_content)
            lines.append("")

        debug_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"[debug] Đã lưu {len(chunks)} chunk(s) -> {debug_path}")