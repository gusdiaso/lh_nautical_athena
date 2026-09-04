"""Offline document preparation for the project's documentation-only RAG."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Sequence

DEFAULT_ALLOWED_PATHS: tuple[str, ...] = (
    "README.md",
    "src/dbt/README.md",
    "docs/documento_projeto_lh_nautical.md",
    "docs/dictionary.md",
    "docs/star_schema.md",
    "docs/mapeamento_dependencias.md",
    "docs/orquestracao_transform.md",
    "docs/extract_lh_nautical.md",
    "docs/extract_exchange_rates.md",
    "docs/dbt_configuration.md",
    "docs/staging.md",
    "docs/intermediate.md",
    "docs/marts.md",
    "docs/marts_tests.md",
    "docs/macros.md",
    "docs/dab_configuration.md",
    "docs/ci_cd_pipeline.md",
    "docs/transform_after_extract.md",
)

_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|secret|password|passwd)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)databricks[_-]?token\s*[:=]\s*[^\s,;]+"),
)
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)


@dataclass(frozen=True)
class Document:
    """A sanitized source document ready to be split into chunks."""

    source_path: str
    file_name: str
    source_type: str
    section: str
    content: str
    last_modified: str
    content_hash: str
    status: str = "approved"


@dataclass(frozen=True)
class Chunk:
    """A stable, citable fragment of a document."""

    chunk_id: str
    source_path: str
    file_name: str
    source_type: str
    section: str
    content: str
    content_hash: str
    last_modified: str
    status: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


class _VisibleTextParser(HTMLParser):
    """Extract visible HTML while ignoring executable and layout-only nodes."""

    _IGNORED = {"head", "script", "style", "nav", "footer", "noscript"}

    def __init__(self) -> None:
        super().__init__()
        self._ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._IGNORED:
            self._ignored_depth += 1
        elif not self._ignored_depth and re.fullmatch(r"h[1-6]", tag.lower()):
            self.parts.append(f"\n{'#' * int(tag[1])} ")
        elif not self._ignored_depth:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._IGNORED and self._ignored_depth:
            self._ignored_depth -= 1
        elif not self._ignored_depth and re.fullmatch(r"h[1-6]", tag.lower()):
            self.parts.append("\n")
        elif not self._ignored_depth:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


def sanitize_text(content: str) -> str:
    """Remove secrets and direct contact identifiers before indexing."""
    for pattern in _SECRET_PATTERNS:
        content = pattern.sub("[REDACTED]", content)
    content = _EMAIL_PATTERN.sub("[EMAIL_REDACTED]", content)
    content = re.sub(r"[ \t\r\f\v]+", " ", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


def parse_content(path: Path) -> str:
    """Read Markdown/TXT or extract visible text from HTML."""
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".html", ".htm"}:
        parser = _VisibleTextParser()
        parser.feed(raw)
        raw = " ".join(parser.parts)
    return sanitize_text(raw)


def _source_type(path: Path) -> str:
    if path.suffix.lower() in {".html", ".htm"}:
        return "dbt_docs"
    if path.name.lower().startswith("readme"):
        return "readme"
    return path.suffix.lower().lstrip(".") or "text"


def _section_for(content: str, start: int) -> str:
    headings = list(re.finditer(r"(?m)^#{1,6}\s+(.+?)\s*$", content))
    previous = [heading for heading in headings if heading.start() <= start]
    return previous[-1].group(1).strip() if previous else "document"


def load_documents(root: Path, allowed_paths: Sequence[str] = DEFAULT_ALLOWED_PATHS) -> list[Document]:
    """Load only explicitly approved files under ``root``."""
    documents: list[Document] = []
    for relative_path in allowed_paths:
        path = (root / relative_path).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            continue
        content = parse_content(path)
        if not content:
            continue
        stat = path.stat()
        documents.append(
            Document(
                source_path=relative_path.replace("\\", "/"),
                file_name=path.name,
                source_type=_source_type(path),
                section=_section_for(content, 0),
                content=content,
                last_modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            )
        )
    return documents


def _split_text_with_offsets(text: str, chunk_size: int, chunk_overlap: int) -> list[tuple[int, str]]:
    if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_size must be positive and overlap must be smaller than chunk_size")
    if not text:
        return []
    chunks: list[tuple[int, str]] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n\n", start, end), text.rfind("\n", start, end), text.rfind(" ", start, end))
            if boundary > start:
                end = boundary
        piece = text[start:end].strip()
        if piece:
            piece_start = start + len(text[start:end]) - len(text[start:end].lstrip())
            chunks.append((piece_start, piece))
        if end >= len(text):
            break
        next_start = max(end - chunk_overlap, start + 1)
        start = next_start
    return chunks


def split_text(text: str, chunk_size: int = 800, chunk_overlap: int = 80) -> list[str]:
    """Split text into bounded overlapping fragments without breaking words when possible."""
    return [piece for _, piece in _split_text_with_offsets(text, chunk_size, chunk_overlap)]


def build_chunks(documents: Iterable[Document], chunk_size: int = 800, chunk_overlap: int = 80) -> list[Chunk]:
    """Create stable chunks suitable for a Delta table or local inspection."""
    chunks: list[Chunk] = []
    for document in documents:
        for position, (start, content) in enumerate(
            _split_text_with_offsets(document.content, chunk_size, chunk_overlap)
        ):
            chunk_key = f"{document.source_path}:{document.content_hash}:{position}:{content}"
            chunk_id = hashlib.sha256(chunk_key.encode("utf-8")).hexdigest()
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    source_path=document.source_path,
                    file_name=document.file_name,
                    source_type=document.source_type,
                    section=_section_for(document.content, start),
                    content=content,
                    content_hash=document.content_hash,
                    last_modified=document.last_modified,
                    status=document.status,
                )
            )
    return chunks
