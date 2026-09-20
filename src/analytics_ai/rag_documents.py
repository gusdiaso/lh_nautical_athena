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
    "docs/relatorio_analise_projeto.md",
    "docs/previsao_demanda_produto_loja.md",
    "docs/dicionario_features_ml_produto_loja_mes.md",
    "docs/xgboost_demand.md",
    "docs/implementacao-rag-documental-databricks.md",
    "docs/rag_evaluation.md",
    "docs/rag_operacao.md",
    "docs/rag_seguranca.md",
    "docs/rag_interface_interna.md",
    "docs/rag_app_producao.md",
)

_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|access[_-]?token|secret|password|passwd)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)databricks[_-]?token\s*[:=]\s*[^\s,;]+"),
)
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_MARKDOWN_HEADING_PATTERN = re.compile(r"(?m)^#{1,6}\s+(.+?)\s*$")


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
    headings = list(_MARKDOWN_HEADING_PATTERN.finditer(content))
    previous = [heading for heading in headings if heading.start() <= start]
    return previous[-1].group(1).strip() if previous else "document"


def _markdown_sections(content: str) -> list[tuple[str, str, str]]:
    """Return editorial section, hierarchical breadcrumb, and its own body."""
    headings: list[tuple[int, int, int, str]] = []
    offset = 0
    fence: str | None = None
    for line in content.splitlines(keepends=True):
        fence_match = re.match(r"^[ \t]{0,3}(`{3,}|~{3,})", line)
        if fence_match:
            marker = fence_match.group(1)[0]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
        elif fence is None:
            heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line.rstrip("\r\n"))
            if heading:
                headings.append(
                    (offset, offset + len(line.rstrip("\r\n")), len(heading.group(1)), heading.group(2).strip())
                )
        offset += len(line)

    if not headings:
        return [("document", "", content)] if content else []

    sections: list[tuple[str, str, str]] = []
    if content[: headings[0][0]].strip():
        sections.append(("document", "", content[: headings[0][0]].strip()))
    hierarchy: list[tuple[int, str]] = []
    for position, (_, heading_end, level, section) in enumerate(headings):
        while hierarchy and hierarchy[-1][0] >= level:
            hierarchy.pop()
        hierarchy.append((level, section))
        end = headings[position + 1][0] if position + 1 < len(headings) else len(content)
        body = content[heading_end:end].strip()
        substantive_body = re.sub(r"(?m)^\s{0,3}(?:-{3,}|\*{3,}|_{3,})\s*$", "", body).strip()
        if substantive_body:
            breadcrumb = " > ".join(title for _, title in hierarchy)
            sections.append((section, breadcrumb, body))
    return sections


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


_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}")


def _line_at(text: str, offset: int) -> tuple[int, str]:
    line_start = text.rfind("\n", 0, offset) + 1
    line_end = text.find("\n", line_start)
    return line_start, text[line_start : len(text) if line_end < 0 else line_end]


def _is_table_row(text: str, offset: int) -> bool:
    if offset < 0 or offset >= len(text):
        return False
    return _line_at(text, offset)[1].lstrip().startswith("|")


def _table_header_at(text: str, offset: int) -> str | None:
    """Header and separator rows of the table containing `offset`, unless that row is the header itself."""
    if not _is_table_row(text, offset):
        return None
    line_start, _ = _line_at(text, offset)
    rows: list[str] = []
    cursor = line_start
    while cursor > 0:
        previous_start, previous = _line_at(text, cursor - 1)
        if not previous.lstrip().startswith("|"):
            break
        rows.insert(0, previous)
        cursor = previous_start
    if len(rows) < 2 or not _TABLE_SEPARATOR.match(rows[1]):
        return None
    return rows[0].strip() + "\n" + rows[1].strip()


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
            # Inside a Markdown table a mid-row cut leaves half a row on each side.
            if _is_table_row(text, boundary) and text.rfind("\n", start, end) > start:
                boundary = text.rfind("\n", start, end)
            if boundary > start:
                end = boundary
        piece = text[start:end].strip()
        if piece:
            piece_start = start + len(text[start:end]) - len(text[start:end].lstrip())
            chunks.append((piece_start, piece))
        if end >= len(text):
            break
        next_start = max(end - chunk_overlap, start + 1)
        # The overlap opens on a whole line when one starts inside the window
        # (tables, bullets) and never in the middle of a word.
        newline = text.find("\n", next_start, end + 1)
        if newline != -1:
            next_start = newline + 1
        elif not text[next_start - 1].isspace():
            space = text.find(" ", next_start, end)
            if space != -1:
                next_start = space + 1
        start = next_start
    return chunks


def split_text(text: str, chunk_size: int = 800, chunk_overlap: int = 80) -> list[str]:
    """Split text into bounded overlapping fragments without breaking words when possible."""
    return [piece for _, piece in _split_text_with_offsets(text, chunk_size, chunk_overlap)]


def build_chunks(documents: Iterable[Document], chunk_size: int = 800, chunk_overlap: int = 80) -> list[Chunk]:
    """Create stable chunks suitable for a Delta table or local inspection."""
    chunks: list[Chunk] = []
    for document in documents:
        if Path(document.source_path).suffix.lower() == ".md":
            pieces: list[tuple[str, str]] = []
            for section, breadcrumb, body in _markdown_sections(document.content):
                prefix = f"CONTEXTO: {breadcrumb}\n\n" if breadcrumb else ""
                available_body_size = chunk_size - len(prefix)
                if available_body_size <= chunk_overlap:
                    raise ValueError(
                        f"chunk_size leaves no room for body and overlap in section {section!r}"
                    )
                for body_start, body_chunk in _split_text_with_offsets(
                    body, available_body_size, chunk_overlap
                ):
                    # A chunk that starts inside a table repeats the header so
                    # the column names travel with the rows.
                    header = _table_header_at(body, body_start)
                    if header and not body_chunk.startswith(header):
                        body_chunk = header + "\n" + body_chunk
                    pieces.append((section, prefix + body_chunk))
        else:
            pieces = [
                (_section_for(document.content, start), content)
                for start, content in _split_text_with_offsets(
                    document.content, chunk_size, chunk_overlap
                )
            ]
        for position, (section, content) in enumerate(pieces):
            chunk_key = f"{document.source_path}:{document.content_hash}:{position}:{content}"
            chunk_id = hashlib.sha256(chunk_key.encode("utf-8")).hexdigest()
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    source_path=document.source_path,
                    file_name=document.file_name,
                    source_type=document.source_type,
                    section=section,
                    content=content,
                    content_hash=document.content_hash,
                    last_modified=document.last_modified,
                    status=document.status,
                )
            )
    return chunks
