import base64
import binascii
import logging
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

MAX_BYTES = 2 * 1024 * 1024

# Parser diagnostics can contain bytes copied from damaged input files.
pdf_log = logging.getLogger("pypdf")
pdf_log.addHandler(logging.NullHandler())
pdf_log.propagate = False


class InvalidFile(ValueError):
    """A client-safe ingestion diagnostic containing no original file bytes."""


def decode_upload(encoded):
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise InvalidFile("文件编码无效") from exc
    if not 0 < len(raw) <= MAX_BYTES:
        raise InvalidFile("仅接受 1 字节至 2 MiB 的文件")
    return raw


def parse(filename, raw):
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        try:
            pdf = PdfReader(BytesIO(raw), strict=False)
            if pdf.is_encrypted or len(pdf.pages) > 80:
                raise InvalidFile("PDF 加密或超过 80 页")
            pages = [page.extract_text() or "" for page in pdf.pages]
        except InvalidFile:
            raise
        except Exception as exc:
            raise InvalidFile("PDF 损坏或无法解析") from exc
    elif suffix in {".txt", ".md"}:
        try:
            pages = [raw.decode("utf-8-sig")]
        except UnicodeDecodeError as exc:
            raise InvalidFile("TXT 和 Markdown 需要 UTF-8 编码") from exc
    else:
        raise InvalidFile("支持格式为 TXT、Markdown、PDF")
    if not any(p.strip() for p in pages):
        raise InvalidFile("未提取到文字，扫描版 PDF 需要先做 OCR")
    if sum(map(len, pages)) > 200_000 or any("\x00" in p for p in pages):
        raise InvalidFile("提取文本超过 20 万字符或含二进制内容")
    return pages


def split(pages, size=420, overlap=60):
    for page, text in enumerate(pages, 1):
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            if text[start:end].strip():
                yield page, start, end, text[start:end]
            if end == len(text):
                break
            start = end - overlap
