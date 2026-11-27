#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""素材解析层：能力探测 + 引擎登记表 + 明确降级。

原则：
    只探测、只调用、绝不自动安装。本机有什么引擎就用什么；一个都没有就跳过，并把原因写清楚。
    同一格式登记多个引擎，按登记顺序依次尝试，失败自动降级。
    不认识的扩展名也不是立刻放弃：先按文本嗅探，再用通用转换器（pandoc / LibreOffice）。

加一个引擎 = 在 ENGINES 里加一条（探测函数 + 读取函数），再把它挂到 CHAINS 里对应扩展名。

支持（取决于本机装了什么）：
    md/txt/csv/json/log        内置
    html/htm                   内置（去标签）
    ipynb                      内置（读 JSON 单元）
    epub                       内置（解 zip + 去标签）
    pdf                        pymupdf / pdfplumber / pypdf / PyPDF2 / pdfminer / pdftotext / mutool / LibreOffice
    docx                       python-docx / docx2txt / pandoc / LibreOffice
    doc                        LibreOffice / pandoc / antiword / catdoc
    pptx / ppt                 python-pptx / pandoc / LibreOffice
    xlsx / xlsm / xls          openpyxl / pandas / LibreOffice
    odt/odp/ods/rtf            pandoc / LibreOffice
    图片 png/jpg/...           pytesseract / tesseract CLI / easyocr / paddleocr
    其它任意格式               文本嗅探 → pandoc → LibreOffice

扫描件判定：抽到文本后平均每页字符 < 50，视为扫描件，转 OCR。
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TEXT_EXT = {".md", ".txt", ".csv", ".json", ".log", ".yaml", ".yml", ".rst", ".tex"}
WEB_EXT = {".html", ".htm", ".xhtml"}
NOTEBOOK_EXT = {".ipynb"}
EPUB_EXT = {".epub"}
PDF_EXT = {".pdf"}
DOCX_EXT = {".docx"}
DOC_EXT = {".doc"}
PPTX_EXT = {".pptx"}
PPT_EXT = {".ppt"}
XLSX_EXT = {".xlsx", ".xlsm"}
XLS_EXT = {".xls"}
ODF_EXT = {".odt", ".odp", ".ods", ".rtf"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".gif"}
ALL_EXT = (TEXT_EXT | WEB_EXT | NOTEBOOK_EXT | EPUB_EXT | PDF_EXT | DOCX_EXT | DOC_EXT
           | PPTX_EXT | PPT_EXT | XLSX_EXT | XLS_EXT | ODF_EXT | IMAGE_EXT)

SCANNED_CHARS_PER_PAGE = 20   # 每页平均不到 20 字才当扫描件（阈值过高会把短文档误送 OCR）
OCR_LANGS = ("chi_sim+eng", "eng")
CHUNK_LIMIT = 200000


def _has_mod(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _mod_any(*names: str) -> bool:
    return any(_has_mod(n) for n in names)


def _has_cmd(*names: str) -> str:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return ""


def _decode_bytes(raw: bytes) -> str:
    """按常见编码依次尝试，解码失败不静默：最后用 replace 并保留替换符。"""
    for enc in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")


def _looks_like_text(text: str) -> bool:
    if not text:
        return False
    sample = text[:4000]
    printable = sum(1 for ch in sample if ch.isprintable() or ch in "\r\n\t")
    return printable / max(1, len(sample)) > 0.9


# ---------------------------------------------------------------- 内置读取器


def _read_text_file(path: str, limit: int) -> tuple[str, str]:
    with open(path, "rb") as f:
        return _decode_bytes(f.read())[:limit], "builtin"


_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    import html as _html
    body = _SCRIPT_RE.sub(" ", html)
    body = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", body, flags=re.I)
    body = _TAG_RE.sub(" ", body)
    body = _html.unescape(body)
    body = re.sub(r"[ \t\u3000]+", " ", body)
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def _read_html(path: str, limit: int) -> tuple[str, str]:
    with open(path, "rb") as f:
        return _strip_html(_decode_bytes(f.read()))[:limit], "builtin:html"


def _read_ipynb(path: str, limit: int) -> tuple[str, str]:
    with open(path, "rb") as f:
        nb = json.loads(_decode_bytes(f.read()))
    parts = []
    for i, cell in enumerate(nb.get("cells", []), 1):
        src = cell.get("source") or []
        text = "".join(src) if isinstance(src, list) else str(src)
        if text.strip():
            parts.append(f"\n--- 单元 {i}（{cell.get('cell_type', '?')}）---\n{text}")
    return "\n".join(parts)[:limit], "builtin:ipynb"


def _read_epub(path: str, limit: int) -> tuple[str, str]:
    parts = []
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith((".xhtml", ".html", ".htm"))]
        for n in sorted(names):
            try:
                parts.append(f"\n--- {n} ---\n{_strip_html(_decode_bytes(z.read(n)))}")
            except Exception as exc:  # 单个条目坏了不影响整本
                parts.append(f"\n--- {n}（读取失败: {exc}）---")
            if sum(len(p) for p in parts) > limit:
                break
    return "\n".join(parts)[:limit], "builtin:epub"


# ---------------------------------------------------------------- 模块引擎


def _read_pymupdf(path: str, limit: int) -> tuple[str, str]:
    import fitz  # type: ignore
    doc = fitz.open(path)
    try:
        out = []
        total = 0
        for page in doc:
            t = page.get_text()
            out.append(f"\n--- 第 {page.number + 1} 页 ---\n{t}")
            total += len(t)
            if total > limit:
                out.append("\n…[已截断]")
                break
        return "".join(out)[:limit], f"pymupdf({doc.page_count}页)"
    finally:
        doc.close()


def _read_pdfplumber(path: str, limit: int) -> tuple[str, str]:
    import pdfplumber  # type: ignore
    out = []
    total = 0
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            t = page.extract_text() or ""
            out.append(f"\n--- 第 {i} 页 ---\n{t}")
            total += len(t)
            if total > limit:
                out.append("\n…[已截断]")
                break
        n = len(pdf.pages)
    return "".join(out)[:limit], f"pdfplumber({n}页)"


def _read_pypdf(path: str, limit: int) -> tuple[str, str]:
    from pypdf import PdfReader  # type: ignore
    reader = PdfReader(path)
    out = []
    total = 0
    for i, page in enumerate(reader.pages, 1):
        t = page.extract_text() or ""
        out.append(f"\n--- 第 {i} 页 ---\n{t}")
        total += len(t)
        if total > limit:
            out.append("\n…[已截断]")
            break
    return "".join(out)[:limit], f"pypdf({len(reader.pages)}页)"


def _read_pypdf2(path: str, limit: int) -> tuple[str, str]:
    from PyPDF2 import PdfReader  # type: ignore
    reader = PdfReader(path)
    out = []
    total = 0
    for i, page in enumerate(reader.pages, 1):
        t = page.extract_text() or ""
        out.append(f"\n--- 第 {i} 页 ---\n{t}")
        total += len(t)
        if total > limit:
            out.append("\n…[已截断]")
            break
    return "".join(out)[:limit], f"PyPDF2({len(reader.pages)}页)"


def _read_pdfminer(path: str, limit: int) -> tuple[str, str]:
    from pdfminer.high_level import extract_text  # type: ignore
    return extract_text(path)[:limit], "pdfminer"


def _read_pdftotext(path: str, limit: int) -> tuple[str, str]:
    exe = _has_cmd("pdftotext")
    p = subprocess.run([exe, "-enc", "UTF-8", path, "-"], capture_output=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:200])
    return p.stdout.decode("utf-8", "replace")[:limit], "pdftotext"


def _read_mutool(path: str, limit: int) -> tuple[str, str]:
    exe = _has_cmd("mutool")
    p = subprocess.run([exe, "draw", "-F", "txt", "-o", "-", path],
                       capture_output=True, timeout=180)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:200])
    return p.stdout.decode("utf-8", "replace")[:limit], "mutool"


def _read_docx(path: str, limit: int) -> tuple[str, str]:
    import docx  # type: ignore
    d = docx.Document(path)
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for table in d.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return "\n".join(parts)[:limit], "python-docx"


def _read_docx2txt(path: str, limit: int) -> tuple[str, str]:
    import docx2txt  # type: ignore
    return (docx2txt.process(path) or "")[:limit], "docx2txt"


def _read_pandoc(path: str, limit: int) -> tuple[str, str]:
    exe = _has_cmd("pandoc")
    p = subprocess.run([exe, path, "-t", "markdown", "--wrap=none"],
                       capture_output=True, timeout=180)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:200])
    return p.stdout.decode("utf-8", "replace")[:limit], "pandoc"


def _read_pptx(path: str, limit: int) -> tuple[str, str]:
    from pptx import Presentation  # type: ignore
    prs = Presentation(path)
    parts = []
    for i, slide in enumerate(prs.slides, 1):
        parts.append(f"\n--- 第 {i} 页 ---")
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                parts.append(shape.text)
    return "\n".join(parts)[:limit], f"python-pptx({len(prs.slides)}页)"


def _read_xlsx(path: str, limit: int) -> tuple[str, str]:
    import openpyxl  # type: ignore
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    parts = []
    for ws in wb.worksheets:
        parts.append(f"\n--- 工作表 {ws.title} ---")
        for row in ws.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None]
            if cells:
                parts.append(" | ".join(cells))
            if sum(len(x) for x in parts) > limit:
                break
    wb.close()
    return "\n".join(parts)[:limit], "openpyxl"


def _read_pandas_excel(path: str, limit: int) -> tuple[str, str]:
    import pandas as pd  # type: ignore
    sheets = pd.read_excel(path, sheet_name=None, header=None)
    parts = []
    for name, df in sheets.items():
        parts.append(f"\n--- 工作表 {name} ---")
        parts.append(df.fillna("").to_string(index=False, header=False))
        if sum(len(x) for x in parts) > limit:
            break
    return "\n".join(parts)[:limit], f"pandas({len(sheets)}表)"


def _read_antiword(path: str, limit: int) -> tuple[str, str]:
    exe = _has_cmd("antiword")
    p = subprocess.run([exe, path], capture_output=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:200])
    return _decode_bytes(p.stdout)[:limit], "antiword"


def _read_catdoc(path: str, limit: int) -> tuple[str, str]:
    exe = _has_cmd("catdoc")
    p = subprocess.run([exe, path], capture_output=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:200])
    return _decode_bytes(p.stdout)[:limit], "catdoc"


def _read_soffice(path: str, limit: int) -> tuple[str, str]:
    """用 LibreOffice 转换器兜底：表格转 csv，其余转 txt。"""
    exe = _has_cmd("soffice", "libreoffice")
    if not exe:
        raise RuntimeError("没有 soffice/libreoffice")
    ext = os.path.splitext(path)[1].lower()
    target = "csv" if ext in (XLSX_EXT | XLS_EXT | {".ods"}) else "txt"
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [exe, "--headless", "--norestore", "--convert-to", target, "--outdir", tmp, path]
        p = subprocess.run(cmd, capture_output=True, timeout=300)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.decode("utf-8", "replace")[:200])
        for fn in os.listdir(tmp):
            if fn.lower().endswith("." + target):
                with open(os.path.join(tmp, fn), "rb") as f:
                    return _decode_bytes(f.read())[:limit], f"libreoffice(.{target})"
    raise RuntimeError("LibreOffice 没有产出文本")


# ---------------------------------------------------------------- OCR


def _ocr_tesseract_py(path: str) -> tuple[str, str]:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
    img = Image.open(path)
    last = None
    for lang in OCR_LANGS:
        try:
            return pytesseract.image_to_string(img, lang=lang), f"pytesseract[{lang}]"
        except Exception as exc:
            last = exc
    raise RuntimeError(f"pytesseract 失败: {last}")


def _ocr_tesseract_cli(path: str) -> tuple[str, str]:
    exe = _has_cmd("tesseract")
    last = ""
    for lang in OCR_LANGS:
        p = subprocess.run([exe, path, "stdout", "-l", lang], capture_output=True, timeout=300)
        if p.returncode == 0:
            return _decode_bytes(p.stdout), f"tesseract[{lang}]"
        last = p.stderr.decode("utf-8", "replace")[:200]
    raise RuntimeError(f"tesseract 失败: {last}")


def _ocr_easyocr(path: str) -> tuple[str, str]:
    import easyocr  # type: ignore
    reader = easyocr.Reader(["ch_sim", "en"], gpu=False, verbose=False)
    lines = reader.readtext(path, detail=0, paragraph=True)
    return "\n".join(lines), "easyocr"


def _ocr_paddleocr(path: str) -> tuple[str, str]:
    from paddleocr import PaddleOCR  # type: ignore
    ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
    res = ocr.ocr(path, cls=True) or []
    lines = []
    for block in res:
        for item in block or []:
            try:
                lines.append(item[1][0])
            except Exception:
                continue
    return "\n".join(lines), "paddleocr"


def _ocr_chain() -> list[str]:
    names = []
    if _has_mod("pytesseract") and _has_mod("PIL"):
        names.append("pytesseract")
    if _has_cmd("tesseract"):
        names.append("tesseract-cli")
    if _has_mod("easyocr"):
        names.append("easyocr")
    if _has_mod("paddleocr"):
        names.append("paddleocr")
    return names


OCR = {
    "pytesseract": _ocr_tesseract_py,
    "tesseract-cli": _ocr_tesseract_cli,
    "easyocr": _ocr_easyocr,
    "paddleocr": _ocr_paddleocr,
}


def ocr_image(path: str) -> tuple[str, str]:
    errs = []
    for name in _ocr_chain():
        try:
            return OCR[name](path)
        except Exception as exc:
            errs.append(f"{name}: {str(exc)[:120]}")
    if not errs:
        raise RuntimeError("本机没有可用的 OCR 引擎")
    raise RuntimeError("OCR 全部失败: " + "; ".join(errs))


def _pdf_to_images(path: str, max_pages: int) -> list[str]:
    """把 PDF 前 N 页转成 PNG，返回临时文件路径列表。用完由调用方删。"""
    paths = []
    if _mod_any("fitz", "pymupdf"):
        import fitz  # type: ignore
        doc = fitz.open(path)
        try:
            for page in doc:
                if page.number >= max_pages:
                    break
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = tmp.name
                page.get_pixmap(dpi=150).save(tmp_path)
                paths.append(tmp_path)
        finally:
            doc.close()
        return paths

    exe = _has_cmd("pdftoppm")
    if exe:
        tmpdir = tempfile.mkdtemp()
        p = subprocess.run([exe, "-r", "150", "-png", "-l", str(max_pages), path,
                            os.path.join(tmpdir, "page")], capture_output=True, timeout=300)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.decode("utf-8", "replace")[:200])
        return [os.path.join(tmpdir, n) for n in sorted(os.listdir(tmpdir)) if n.endswith(".png")]

    exe = _has_cmd("mutool")
    if exe:
        tmpdir = tempfile.mkdtemp()
        p = subprocess.run([exe, "draw", "-r", "150", "-o", os.path.join(tmpdir, "page-%d.png"),
                            path, f"1-{max_pages}"], capture_output=True, timeout=300)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.decode("utf-8", "replace")[:200])
        return [os.path.join(tmpdir, n) for n in sorted(os.listdir(tmpdir)) if n.endswith(".png")]

    raise RuntimeError("没有能把 PDF 渲染成图片的引擎（pymupdf / pdftoppm / mutool）")


def ocr_pdf(path: str, max_pages: int = 20) -> tuple[str, str]:
    images = _pdf_to_images(path, max_pages)
    parts = []
    try:
        for i, img in enumerate(images, 1):
            try:
                text, _ = ocr_image(img)
            except Exception as exc:
                parts.append(f"\n--- 第 {i} 页（OCR 失败: {exc}）---")
                continue
            parts.append(f"\n--- 第 {i} 页（OCR）---\n{text}")
        if len(images) >= max_pages:
            parts.append(f"\n…[OCR 仅处理前 {max_pages} 页]")
        return "".join(parts), f"ocr({len(images)}页)"
    finally:
        for p in images:
            try:
                os.remove(p)
            except Exception:
                pass


# ---------------------------------------------------------------- 登记表


ENGINES = {
    "builtin": {"probe": lambda: True, "read": _read_text_file},
    "builtin:html": {"probe": lambda: True, "read": _read_html},
    "builtin:ipynb": {"probe": lambda: True, "read": _read_ipynb},
    "builtin:epub": {"probe": lambda: True, "read": _read_epub},
    "pymupdf": {"probe": lambda: _mod_any("fitz", "pymupdf"), "read": _read_pymupdf},
    "pdfplumber": {"probe": lambda: _has_mod("pdfplumber"), "read": _read_pdfplumber},
    "pypdf": {"probe": lambda: _has_mod("pypdf"), "read": _read_pypdf},
    "PyPDF2": {"probe": lambda: _has_mod("PyPDF2"), "read": _read_pypdf2},
    "pdfminer": {"probe": lambda: _has_mod("pdfminer"), "read": _read_pdfminer},
    "pdftotext": {"probe": lambda: bool(_has_cmd("pdftotext")), "read": _read_pdftotext},
    "mutool": {"probe": lambda: bool(_has_cmd("mutool")), "read": _read_mutool},
    "python-docx": {"probe": lambda: _has_mod("docx"), "read": _read_docx},
    "docx2txt": {"probe": lambda: _has_mod("docx2txt"), "read": _read_docx2txt},
    "python-pptx": {"probe": lambda: _has_mod("pptx"), "read": _read_pptx},
    "openpyxl": {"probe": lambda: _has_mod("openpyxl"), "read": _read_xlsx},
    "pandas": {"probe": lambda: _has_mod("pandas"), "read": _read_pandas_excel},
    "pandoc": {"probe": lambda: bool(_has_cmd("pandoc")), "read": _read_pandoc},
    "libreoffice": {"probe": lambda: bool(_has_cmd("soffice", "libreoffice")), "read": _read_soffice},
    "antiword": {"probe": lambda: bool(_has_cmd("antiword")), "read": _read_antiword},
    "catdoc": {"probe": lambda: bool(_has_cmd("catdoc")), "read": _read_catdoc},
}

CHAINS = {
    ".pdf": ["pymupdf", "pdfplumber", "pypdf", "PyPDF2", "pdfminer", "pdftotext", "mutool", "libreoffice"],
    ".docx": ["python-docx", "docx2txt", "pandoc", "libreoffice"],
    ".doc": ["libreoffice", "pandoc", "antiword", "catdoc"],
    ".pptx": ["python-pptx", "pandoc", "libreoffice"],
    ".ppt": ["libreoffice", "pandoc"],
    ".xlsx": ["openpyxl", "pandas", "libreoffice"],
    ".xlsm": ["openpyxl", "pandas", "libreoffice"],
    ".xls": ["pandas", "libreoffice"],
    ".epub": ["builtin:epub", "pandoc"],
    ".html": ["builtin:html", "pandoc", "libreoffice"],
    ".htm": ["builtin:html", "pandoc", "libreoffice"],
    ".xhtml": ["builtin:html", "pandoc", "libreoffice"],
    ".ipynb": ["builtin:ipynb"],
    ".rtf": ["pandoc", "libreoffice"],
    ".odt": ["pandoc", "libreoffice"],
    ".odp": ["libreoffice", "pandoc"],
    ".ods": ["libreoffice"],
}

GENERIC_CHAIN = ["pandoc", "libreoffice"]


def _available(name: str) -> bool:
    spec = ENGINES.get(name)
    try:
        return bool(spec and spec["probe"]())
    except Exception:
        return False


def available_engines() -> dict[str, list[str]]:
    """本机当前可用的引擎（按登记顺序）。"""
    return {ext: [n for n in chain if _available(n)] for ext, chain in CHAINS.items()}


def ocr_available() -> str:
    chain = _ocr_chain()
    return chain[0] if chain else ""


def capability_table() -> list[tuple[str, str]]:
    eng = available_engines()

    def show(*exts: str) -> str:
        seen = []
        for e in exts:
            for n in eng.get(e, []):
                if n not in seen:
                    seen.append(n)
        return ", ".join(seen) or "（无）"

    return [
        ("文本 md/txt/csv/json", "内置"),
        ("网页 html/htm", "内置"),
        ("Jupyter .ipynb", "内置"),
        ("EPUB", show(".epub")),
        ("PDF", show(".pdf")),
        ("扫描 PDF / 图片", ", ".join(_ocr_chain()) or "（无）"),
        ("PDF 渲染（供 OCR）", "pymupdf" if _mod_any("fitz", "pymupdf")
         else ("pdftoppm" if _has_cmd("pdftoppm") else ("mutool" if _has_cmd("mutool") else "（无）"))),
        ("DOCX", show(".docx")),
        ("DOC（旧版）", show(".doc")),
        ("PPTX", show(".pptx")),
        ("PPT（旧版）", show(".ppt")),
        ("XLSX", show(".xlsx")),
        ("XLS（旧版）", show(".xls")),
        ("ODF / RTF", show(".odt", ".ods", ".odp", ".rtf")),
        ("其它任意格式", ", ".join([n for n in GENERIC_CHAIN if _available(n)]) or "（仅文本嗅探）"),
    ]


def read(path: str, limit: int = CHUNK_LIMIT) -> dict:
    """读一个文件，返回 {text, engine, note} 或 {error}。"""
    ext = os.path.splitext(path)[1].lower()

    if ext in TEXT_EXT:
        try:
            text, engine = _read_text_file(path, limit)
            return {"text": text, "engine": engine, "note": ""}
        except Exception as exc:
            return {"error": f"读取失败: {exc}"}

    if ext in IMAGE_EXT:
        try:
            text, engine = ocr_image(path)
            return {"text": text, "engine": engine, "note": "OCR"}
        except Exception as exc:
            return {"error": f"OCR 不可用: {exc}"}

    chain = CHAINS.get(ext)
    tried = []
    if chain:
        for name in available_engines().get(ext, []):
            try:
                text, engine = ENGINES[name]["read"](path, limit)
                note = ""
                if ext in PDF_EXT:
                    pages = max(1, text.count("--- 第") or 1)
                    if len(text.strip()) / pages < SCANNED_CHARS_PER_PAGE:
                        if ocr_available():
                            try:
                                ocr_text, ocr_engine = ocr_pdf(path)
                                if len(ocr_text.strip()) > len(text.strip()):
                                    text, engine, note = ocr_text, ocr_engine, "扫描件，已转 OCR"
                            except Exception as exc:
                                note = f"扫描件但 PDF 渲染/OCR 失败: {str(exc)[:120]}"
                        else:
                            note = "疑似扫描件，但本机没有可用 OCR"
                return {"text": text, "engine": engine, "note": note}
            except Exception as exc:
                tried.append(f"{name}: {str(exc)[:120]}")
        if not tried:
            tried.append("本机没有登记表里任何一个引擎")

    # 不认识的扩展名 / 已知格式全部失败：文本嗅探 → 通用转换器
    try:
        with open(path, "rb") as f:
            raw = f.read(limit * 2)
        as_text = _decode_bytes(raw)
        if _looks_like_text(as_text):
            return {"text": as_text[:limit], "engine": "builtin:sniff",
                    "note": "按纯文本读取（扩展名未登记）"}
    except Exception as exc:
        tried.append(f"文本嗅探: {str(exc)[:80]}")

    for name in GENERIC_CHAIN:
        if not _available(name):
            continue
        try:
            text, engine = ENGINES[name]["read"](path, limit)
            return {"text": text, "engine": engine, "note": "通用转换器"}
        except Exception as exc:
            tried.append(f"{name}: {str(exc)[:120]}")

    if ext and ext not in CHAINS and not tried:
        return {"error": f"不支持的格式: {ext}"}
    return {"error": "全部引擎失败: " + "; ".join(tried)[:300]}
