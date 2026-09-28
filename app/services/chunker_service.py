"""
Chunker service: convert file -> text -> chunks, then embed and store in vector DB.

def chunking(filepath: str) -> list[Document]: dispatch based on file extension.

def embed_text(text: str) -> list[float]: call Ollama embedding API.

def get_deepest_heading(metadata: dict) -> str: return deepest heading in metadata.

def preprocess_text(text: str, source: str = "") -> str: full preprocessing pipeline before chunking.

def normalize_markdown_headings(md_text: str) -> str: fix heading levels in markdown.
"""
import re
import unicodedata
import uuid
import os
from collections import Counter
from pathlib import Path
from typing import Callable, Literal

from langdetect import detect_langs, LangDetectException

import pymupdf4llm
from docx import Document as DocxDocument
import httpx
import requests
from langchain_core.documents import Document
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)
from app.core.config import get_settings
from app.services.chunker_debug import ChunkerDebug

# ---- config ---------------------------------------------------------------
settings = get_settings()

OLLAMA_URL = os.getenv("OLLAMA_URL", settings.ollama_url)
QDRANT_URL = os.getenv(
    "QDRANT_URL",
    f"http://{os.getenv('QDRANT_HOST', 'localhost')}:{os.getenv('QDRANT_PORT', os.getenv('QDRANT_HTTP_PORT', '6333'))}",
)
EMBED_MODEL = os.getenv("EMBEDDING_MODEL", settings.embedding_model)
COLLECTION = settings.rag_collection_name
VECTOR_SIZE = settings.rag_vector_size

MAX_CHUNK_CHARS = settings.max_chunk_chars
CHUNK_OVERLAP_CHARS = settings.chunk_overlap_chars
TXT_CHUNK_WORDS = settings.txt_chunk_words
TXT_OVERLAP_RATIO = settings.txt_overlap_ratio

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MD_DECOR_RE = re.compile(r"[*_`~#>\-\[\]\(\)|]")
_HEADING_LINE = re.compile(r'^(#{1,6})\s+(.*)$')
_NUMBERED_TITLE = re.compile(r'^\**\s*(\d+(?:\.\d+)*)\.?\s')
_SENTENCE_SPLIT_RE = re.compile(r'(?:[.!?…]["\'”’)\]]*\s+)')
_HTML_BREAK_RE = re.compile(r"<\s*br\s*/?\s*>", re.IGNORECASE)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_PAGE_NUM_PATTERNS = [
    re.compile(r'^\s*(trang|page|P a g e)\s*\d+\s*$', re.IGNORECASE),
    re.compile(r'^\s*\d+\s*$'),              # dòng chỉ có mỗi số
    re.compile(r'^\s*-\s*\d+\s*-\s*$'),      # kiểu "- 5 -"
]

ChunkingMode = Literal["hybrid", "recursive_only"]

class ChunkerService:
    """Dispatch file chunking strategy based on extension."""

    @staticmethod
    def chunking(filepath: str, mode: ChunkingMode = "hybrid"):
        """Chunking theo mode và extension, trả về list[Document]."""
        mode_handlers: dict[ChunkingMode, dict[str, Callable[[str], list[Document]]]] = {
            "hybrid": {
                ".md": chunk_markdown,
                ".txt": chunk_txt,
                ".pdf": chunk_pdf,
                ".docx": chunk_docx,
            },
            "recursive_only": {
                ".md": chunk_markdown_recursive_only,
                ".txt": chunk_txt_recursive_only,
                ".pdf": chunk_pdf_recursive_only,
                ".docx": chunk_docx_recursive_only,
            },
        }

        if mode not in mode_handlers:
            raise ValueError(f"Chunking mode không hợp lệ: {mode}")

        ext = Path(filepath).suffix.lower()
        handler = mode_handlers[mode].get(ext)
        if handler is None:
            raise ValueError(f"Chưa support extension: {ext}")
        return handler(filepath)

    @staticmethod
    async def embed_batch_async(texts: list[str], batch_size: int = 32) -> list[list[float]]:
        """Gửi async mini-batch HTTP requests sang Ollama /api/embed (httpx + input array)."""
        import asyncio
        if not texts:
            return []

        base = OLLAMA_URL.rstrip("/")
        sem = asyncio.Semaphore(4)

        async def _process_batch(batch: list[str], client: httpx.AsyncClient) -> list[list[float]]:
            async with sem:
                try:
                    resp = await client.post(
                        f"{base}/api/embed",
                        json={"model": EMBED_MODEL, "input": batch},
                    )
                    if resp.status_code == 404:
                        batch_embeddings = []
                        for text in batch:
                            legacy = await client.post(
                                f"{base}/api/embeddings",
                                json={"model": EMBED_MODEL, "prompt": text},
                            )
                            legacy.raise_for_status()
                            body = legacy.json()
                            if "embedding" in body:
                                batch_embeddings.append(body["embedding"])
                            elif "embeddings" in body and body["embeddings"]:
                                batch_embeddings.append(body["embeddings"][0])
                        return batch_embeddings

                    resp.raise_for_status()
                    body = resp.json()
                    if "embeddings" in body and body["embeddings"]:
                        return body["embeddings"]
                    elif "embedding" in body:
                        return [body["embedding"]]
                    else:
                        raise RuntimeError("Ollama response missing embeddings")
                except httpx.ConnectError as exc:
                    raise RuntimeError(
                        f"Không kết nối được Ollama tại {base}. Hãy kiểm tra service ollama đang chạy và host/port đúng."
                    ) from exc

        async with httpx.AsyncClient(timeout=settings.embedding_timeout) as client:
            batches = [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]
            tasks = [_process_batch(batch, client) for batch in batches]
            results = await asyncio.gather(*tasks)

            all_embeddings = []
            for batch_result in results:
                all_embeddings.extend(batch_result)
            return all_embeddings

    @staticmethod
    async def embed_text_async(text: str) -> list[float]:
        """Gọi Ollama async cho 1 text đơn lẻ."""
        res = await ChunkerService.embed_batch_async([text])
        if not res:
            raise RuntimeError("Không tạo được embedding cho text")
        return res[0]

    @staticmethod
    def embed_text(text: str) -> list[float]:
        """Gọi Ollama embedding API (sync wrapper), trả về embedding vector (list[float])."""
        base = OLLAMA_URL.rstrip("/")
        try:
            resp = requests.post(
                f"{base}/api/embed",
                json={"model": EMBED_MODEL, "input": text},
                timeout=settings.embedding_timeout,
            )
            if resp.status_code == 404:
                legacy = requests.post(
                    f"{base}/api/embeddings",
                    json={"model": EMBED_MODEL, "prompt": text},
                    timeout=settings.embedding_timeout,
                )
                legacy.raise_for_status()
                body = legacy.json()
                if "embedding" in body:
                    return body["embedding"]
                if "embeddings" in body and body["embeddings"]:
                    return body["embeddings"][0]
                raise RuntimeError("Ollama trả response không có embedding")

            resp.raise_for_status()
            body = resp.json()
            if "embeddings" in body and body["embeddings"]:
                return body["embeddings"][0]
            if "embedding" in body:
                return body["embedding"]
            raise RuntimeError("Ollama trả response không có embedding")
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(
                f"Không kết nối được Ollama tại {base}. Hãy kiểm tra service ollama đang chạy và host/port đúng."
            ) from exc
        
    @staticmethod
    def get_deepest_heading(metadata: dict) -> str:
        """Lấy heading sâu nhất từ metadata, trả về 'untitled' nếu không có. Để dùng làm title cho chunk."""
        for level in ("h5", "h4", "h3", "h2", "h1"):
            value = metadata.get(level)
            if value:
                return value
        return "untitled"

# --- chunking --------------------------------------------------------------
def _split_text_into_sentences(text: str) -> list[str]:
    """Split text into sentences while preserving paragraph boundaries."""
    stripped = text.strip()
    if not stripped:
        return []

    sentences: list[str] = []
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", stripped) if p.strip()]
    for para in paragraphs:
        compact = re.sub(r"\s+", " ", para).strip()
        if not compact:
            continue
        parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(compact) if p.strip()]
        if parts:
            sentences.extend(parts)

    return sentences if sentences else [re.sub(r"\s+", " ", stripped)]


def _pack_sentences(
    sentences: list[str],
    max_size: int,
    overlap_sentences: int,
) -> list[str]:
    """Pack full sentences into chunks up to max_size characters."""
    if not sentences:
        return []

    chunks: list[str] = []
    current: list[str] = []

    for sentence in sentences:
        s = sentence.strip()
        if not s:
            continue

        if len(s) > max_size:
            if current:
                chunks.append(" ".join(current))
                current = []
            chunks.append(s)
            continue

        if not current:
            current = [s]
            continue

        projected = len(" ".join(current)) + 1 + len(s)
        if projected <= max_size:
            current.append(s)
            continue

        chunks.append(" ".join(current))
        if overlap_sentences > 0:
            current = current[-overlap_sentences:]
            while current and (len(" ".join(current)) + 1 + len(s)) > max_size:
                current = current[1:]
        else:
            current = []
        current.append(s)

    if current:
        chunks.append(" ".join(current))

    return chunks


def _sentence_aware_split_document(
    doc: Document,
    max_size: int,
    overlap_chars: int,
    fallback_splitter: RecursiveCharacterTextSplitter,
) -> list[Document]:
    """Prefer sentence boundaries; fallback to recursive splitter for very long sentences."""
    sentences = _split_text_into_sentences(doc.page_content)
    if not sentences:
        return []

    overlap_sentences = 1 if overlap_chars > 0 else 0
    packed_chunks = _pack_sentences(sentences, max_size, overlap_sentences)

    out: list[Document] = []
    for text in packed_chunks:
        chunk_doc = Document(page_content=text, metadata=doc.metadata.copy())
        if len(text) <= max_size:
            out.append(chunk_doc)
        else:
            out.extend(fallback_splitter.split_documents([chunk_doc]))

    return out


def chunk_markdown_text(md_text: str, source: str = ""):
    headers_to_split_on = [
        ("#", "h1"),("##", "h2"),("###", "h3"),("####", "h4"),("#####", "h5"),
    ]
    header_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    header_chunks = header_splitter.split_text(md_text)
    print(f"[md stage 1] {len(header_chunks)} section(s) theo heading")

    sub_splitter = RecursiveCharacterTextSplitter(
        chunk_size=MAX_CHUNK_CHARS, chunk_overlap=CHUNK_OVERLAP_CHARS
    )
    final_chunks = []
    for doc in header_chunks:
        doc.metadata["source"] = source
        final_chunks.extend(
            _sentence_aware_split_document(
                doc,
                max_size=MAX_CHUNK_CHARS,
                overlap_chars=CHUNK_OVERLAP_CHARS,
                fallback_splitter=sub_splitter,
            )
        )
    print(f"[md stage 2] {len(final_chunks)} chunk(s) sau khi giới hạn size")
    return final_chunks

def chunk_markdown(filepath: str):
    md_text = Path(filepath).read_text(encoding="utf-8")
    md_text = preprocess_text(md_text, source=filepath)
    return chunk_markdown_text(md_text, source=filepath)


def _recursive_split_text(text: str, source: str) -> list[Document]:
    """Split text with plain recursive splitter for all formats in recursive_only mode."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=MAX_CHUNK_CHARS,
        chunk_overlap=CHUNK_OVERLAP_CHARS,
    )
    base_doc = Document(page_content=text, metadata={"source": source})
    return splitter.split_documents([base_doc])


def chunk_markdown_recursive_only(filepath: str) -> list[Document]:
    md_text = Path(filepath).read_text(encoding="utf-8")
    md_text = preprocess_text(md_text, source=filepath)
    chunks = _recursive_split_text(md_text, source=filepath)
    print(f"[md recursive_only] {len(chunks)} chunk(s)")
    return chunks


# --------------------------------------------------------------------- txt --
def chunk_txt(
    filepath: str,
    chunk_size_chars: int = MAX_CHUNK_CHARS,
    chunk_overlap_chars: int = CHUNK_OVERLAP_CHARS,
):
    text = Path(filepath).read_text(encoding="utf-8")
    text = preprocess_text(text, source=filepath)

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size_chars,
        chunk_overlap=chunk_overlap_chars,
    )

    base_doc = Document(page_content=text, metadata={"source": filepath})
    chunks = _sentence_aware_split_document(
        base_doc,
        max_size=chunk_size_chars,
        overlap_chars=chunk_overlap_chars,
        fallback_splitter=splitter,
    )
    print(
        f"[txt] {len(chunks)} chunk(s), size={chunk_size_chars} chars, overlap={chunk_overlap_chars} chars"
    )
    return chunks


def chunk_txt_recursive_only(filepath: str) -> list[Document]:
    text = Path(filepath).read_text(encoding="utf-8")
    text = preprocess_text(text, source=filepath)
    chunks = _recursive_split_text(text, source=filepath)
    print(f"[txt recursive_only] {len(chunks)} chunk(s)")
    return chunks

# --- pdf conversion --------------------------------------------------------
def chunk_pdf(filepath: str, save_debug_md: bool = False) -> list[Document]:

    md_text = pymupdf4llm.to_markdown(filepath)
    if save_debug_md:
        ChunkerDebug.save_debug_markdown(filepath, "parser", md_text)

    md_text = preprocess_text(md_text, source=filepath)       # lọc header/footer/page-num trước
    if save_debug_md:
        ChunkerDebug.save_debug_markdown(filepath, "preprocess", md_text)

    md_text = normalize_markdown_headings(md_text)             # rồi mới fix cấp heading
    if save_debug_md:
        debug_path = ChunkerDebug.save_debug_markdown(filepath, "final", md_text)
        print(f"[pdf convert] Đã lưu bản markdown trung gian -> {debug_path}")

    return chunk_markdown_text(md_text, source=filepath)


def chunk_pdf_recursive_only(filepath: str, save_debug_md: bool = False) -> list[Document]:
    md_text = pymupdf4llm.to_markdown(filepath)
    if save_debug_md:
        ChunkerDebug.save_debug_markdown(filepath, "parser", md_text)

    md_text = preprocess_text(md_text, source=filepath)
    if save_debug_md:
        ChunkerDebug.save_debug_markdown(filepath, "preprocess", md_text)

    chunks = _recursive_split_text(md_text, source=filepath)
    if save_debug_md:
        ChunkerDebug.save_debug_markdown(
            filepath,
            "final_recursive_only",
            "\n\n".join(chunk.page_content for chunk in chunks),
        )
    print(f"[pdf recursive_only] {len(chunks)} chunk(s)")
    return chunks

def chunk_docx(filepath: str, save_debug_md: bool = False) -> list[Document]:
    doc = DocxDocument(filepath)
    md_lines = []
    for para in doc.paragraphs:
        style = para.style.name
        text = para.text.strip()
        if style.startswith("Heading"):
            md_lines.append("#" * int(style[-1]) + " " + text)
        elif len(text.split()) < 13 and len(text) > 0 and not any(punct in text for punct in ".?!;"):
            md_lines.append(f"# {text}")
        else:
            md_lines.append(text)
    md_text = "\n".join(md_lines)

    if save_debug_md:
        ChunkerDebug.save_debug_markdown(filepath, "parser", md_text)

    md_text = preprocess_text(md_text, source=filepath)
    if save_debug_md:
        ChunkerDebug.save_debug_markdown(filepath, "preprocess", md_text)

    md_text = normalize_markdown_headings(md_text)
    if save_debug_md:
        debug_path = ChunkerDebug.save_debug_markdown(filepath, "final", md_text)
        print(f"[docx convert] Đã lưu bản markdown trung gian -> {debug_path}")

    return chunk_markdown_text(md_text, source=filepath)

def chunk_docx_recursive_only(filepath: str, save_debug_md: bool = False) -> list[Document]:
    doc = DocxDocument(filepath)
    md_lines = []
    for para in doc.paragraphs:
        style = para.style.name
        text = para.text.strip()
        if style.startswith("Heading"):
            md_lines.append("#" * int(style[-1]) + " " + text)
        elif len(text.split()) < 13 and not any(punct in text for punct in ".?!;"):
            md_lines.append(f"# {text}")
        else:
            md_lines.append(text)
    md_text = "\n".join(md_lines)

    if save_debug_md:
        ChunkerDebug.save_debug_markdown(filepath, "parser", md_text)

    md_text = preprocess_text(md_text, source=filepath)
    if save_debug_md:
        ChunkerDebug.save_debug_markdown(filepath, "preprocess", md_text)

    chunks = _recursive_split_text(md_text, source=filepath)
    if save_debug_md:
        ChunkerDebug.save_debug_markdown(
            filepath,
            "final_recursive_only",
            "\n\n".join(chunk.page_content for chunk in chunks),
        )
    print(f"[docx recursive_only] {len(chunks)} chunk(s)")
    return chunks

def preprocess_text(text: str, source: str = "") -> str:
    """Pipeline preprocessing đầy đủ - gọi TRƯỚC bước chunking."""
    text = remove_boilerplate_lines(text)  # loại header/footer/page-number lặp lại
    text = normalize_text(text)            # chuẩn hóa UTF-8, Unicode NFC, gộp whitespace/blank-line thừa
    text = remove_markdown_syntax(text)    # loại bỏ cú pháp markdown (bold, italic, links, inline code...) trước khi chunking

    if flag_possible_glued_words(text):
        print(f"[preprocess] CẢNH BÁO ({source}): nghi ngờ có từ bị dính liền, nên kiểm tra tay")

    lang, conf = detect_text_language(text[:2000])  # lấy mẫu đầu, khỏi detect cả text dài
    print(f"[preprocess] ({source}) Ngôn ngữ detect: {lang} (confidence {conf:.2f})")

    return text


def normalize_markdown_headings(md_text: str) -> str:
    """
    pymupdf4llm gán số dấu '#' theo RANK FONT-SIZE toàn document, không theo
    ngữ nghĩa numbering (3 / 3.1 / 3.1.1) -> dễ bị nhảy cóc cấp (## -> ####).
    """
    out_lines = []
    for line in md_text.split("\n"):
        m = _HEADING_LINE.match(line)
        if not m:
            out_lines.append(line)
            continue

        hashes, title = m.groups()
        num_match = _NUMBERED_TITLE.match(title)
        if num_match:
            depth = num_match.group(1).count(".") + 1   # "3.1.1" -> 3 phần -> depth 3
            new_hashes = "#" * (depth + 1)               # +1 vì "# Tên đề tài" chiếm h1
            out_lines.append(f"{new_hashes} {title}")
        else:
            out_lines.append(line)   # không numbering -> giữ nguyên, không đoán mò

    return "\n".join(out_lines)

# --- preprocessing helpers -------------------------------------------------
# =================================================== PREPROCESSING (trước chunk) ==

def _canonical_line(line: str) -> str:
    """Chuẩn hóa dòng để detect boilerplate ổn định hơn."""
    s = line.strip()
    s = _HTML_TAG_RE.sub(" ", s)           # bỏ HTML tag như <br>
    s = _MD_DECOR_RE.sub(" ", s)           # bỏ markdown decoration
    s = re.sub(r"\d+", "#", s)             # số -> '#'
    s = re.sub(r"\s+", " ", s).strip()
    return s.casefold()

def _is_page_number_line(line: str) -> bool:
    stripped = line.strip()
    return any(p.match(stripped) for p in _PAGE_NUM_PATTERNS)

def _is_short_all_caps_slogan(line: str, max_len: int = 40) -> bool:
    raw = _HTML_TAG_RE.sub(" ", line).strip()
    raw = re.sub(r"[*_`~#>\-\[\]\(\)|]", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    if not raw or len(raw) > max_len:
        return False
    letters = [c for c in raw if c.isalpha()]
    return bool(letters) and raw == raw.upper()

def _normalize_key(line: str) -> str:
    """Thay số bằng '#' để 2 dòng chỉ khác nhau ở số trang vẫn coi là cùng 1 khuôn."""
    return _canonical_line(line)

def remove_boilerplate_lines(text: str, min_repeat: int = 3, max_line_len: int = 140, slogan_min_repeat: int = 2) -> str:
    """
    Loại header/footer lặp lại xuyên suốt document + page number đơn lẻ.
    Detect bằng cách đếm tần suất "khuôn" của từng dòng (đã thay số -> '#'),
    khuôn nào NGẮN và LẶP LẠI NHIỀU LẦN -> coi là boilerplate, xóa hết.
    """
    lines = text.split("\n")
    keys = [_normalize_key(l) for l in lines]
    counts = Counter(k for k in keys if k)

    boilerplate_keys = {
        k for k, freq in counts.items()
        if freq >= min_repeat and len(k) <= max_line_len
    }

    slogan_keys = {
        _normalize_key(l)
        for l in lines
        if _is_short_all_caps_slogan(l)
    }
    slogan_keys = {
        k for k in slogan_keys
        if k and counts.get(k, 0) >= slogan_min_repeat
    }

    kept, removed = [], 0
    for raw, key in zip(lines, keys):
        if (
            key in boilerplate_keys
            or key in slogan_keys
            or _is_page_number_line(raw)
        ):
            removed += 1
            continue
        kept.append(raw)

    print(f"[preprocess] Đã loại {removed} dòng header/footer/page-number")
    return "\n".join(kept)


def detect_text_language(text: str):
    """Trả về (lang_code, confidence) - dùng để phát hiện chunk bị garbled/lẫn ngôn ngữ lạ."""
    try:
        top = detect_langs(text)[0]
        return top.lang, top.prob
    except LangDetectException:
        return "unknown", 0.0

def flag_possible_glued_words(text: str, avg_word_len_threshold: float = 12.0) -> bool:
    """
    Heuristic CẢNH BÁO (không tự sửa) khả năng bị dính chữ khi extract PDF
    """
    words = text.split()
    if not words:
        return False
    avg_len = sum(len(w) for w in words) / len(words)
    return avg_len >= avg_word_len_threshold


def normalize_text(text: str) -> str:
    """
    - Ép UTF-8 hợp lệ (bỏ byte lỗi thay vì crash giữa chừng).
    - Unicode NFC normalize: BẮT BUỘC với tiếng Việt, vì ký tự có dấu (VD 'ệ')
      có thể lưu dưới 2 dạng byte khác nhau (NFC dựng sẵn vs NFD tổ hợp
      base+dấu). Không normalize -> cùng 1 chữ trông y hệt nhưng embedding
      coi là khác nhau, search bị miss.
    - Loại bỏ HTML artifacts do parser để lại (vd: <br>, <!-- comment -->).
    - Gộp whitespace/blank-line thừa cho gọn.
    """
    text = text.encode("utf-8", errors="ignore").decode("utf-8")
    text = unicodedata.normalize("NFC", text)

    # PDF -> markdown thường lẫn tag HTML trong cell bảng, ưu tiên đổi <br> thành khoảng trắng.
    text = _HTML_BREAK_RE.sub(" ", text)
    text = _HTML_COMMENT_RE.sub(" ", text)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.rstrip() for line in text.split("\n"))

    return text.strip()

# post-processing helpers (sau chunk) -------------------------------------------------
def remove_markdown_syntax(text: str) -> str:
    # Bỏ bold, italic (*, _): **text** -> text, *text* -> text (deactivate vì đôi khi *text* là bullet list)
    # text = re.sub(r'[\*_]{1,3}(.*?)([\*_]{1,3})', r'\1', text) 
    # Bỏ links: [text](url) -> text
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    # Bỏ inline code: `code` -> code
    text = re.sub(r'`(.*?)`', r'\1', text)
    return text.strip()