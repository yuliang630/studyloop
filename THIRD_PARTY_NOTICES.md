# Third-Party Notices

The code in this project was written by the author. **No third-party source code was copied**, and no algorithm implementation requiring a licence is included.

---

## Algorithm attribution (published academic work)

| File | Algorithm | Source |
|---|---|---|
| `core/scripts/mastery.py` | Bayesian Knowledge Tracing (BKT) | Corbett, A. T., & Anderson, J. R. (1995). *Knowledge tracing: Modeling the acquisition of procedural knowledge.* User Modeling and User-Adapted Interaction, 4(4), 253–278. |
| `core/scripts/srs.py` | Exponential forgetting curve with half-life scheduling | Ebbinghaus, H. (1885). *Über das Gedächtnis.* Retention-versus-half-life modelling is the standard public approach in spaced repetition. |
| `core/scripts/retrieve.py` | BM25 ranking | Robertson, S., & Zaragoza, H. (2009). *The Probabilistic Relevance Framework: BM25 and Beyond.* |

All three are **published mathematical models**, not the proprietary implementation of any software project. Each was implemented independently from the published description; parameters use the literature defaults and are noted in the code.

---

## Third-party code

**None.** The pack contains no vendored third-party source. Every dependency below is optional and is invoked only if it already exists on the machine.

---

## Optional engines

The plugin **requires no engine**. `parsers.py` probes the machine and uses whatever it finds. Nothing is installed automatically, and nothing breaks when an engine is missing — the format is simply reported as unreadable, with the reason.

Licences are as published by each project at the time of writing; verify before redistributing.

### Python libraries

| Package | Used for | Licence |
|---|---|---|
| PyMuPDF (`pymupdf`, imported as `fitz`) | PDF text, PDF page rendering | AGPL-3.0 |
| pdfplumber | PDF text | MIT |
| pypdf | PDF text | BSD-3-Clause |
| PyPDF2 | PDF text | BSD-3-Clause |
| pdfminer.six | PDF text | MIT |
| python-docx | DOCX text | MIT |
| docx2txt | DOCX text | MIT |
| python-pptx | PPTX text | MIT |
| openpyxl | XLSX text | MIT |
| pandas | XLSX/XLS text | BSD-3-Clause |
| pytesseract | OCR driver | Apache-2.0 |
| Pillow (`PIL`) | image handling for OCR | MIT-CMU (HPND) |
| easyocr | OCR | Apache-2.0 |
| paddleocr | OCR | Apache-2.0 |

> PyMuPDF is AGPL. If you plan to distribute this project under a closed licence, prefer `pypdf`, `pdfplumber`, `pdfminer.six`, `pdftotext` or LibreOffice instead — the plugin will use whichever is installed.

### External programs (invoked, never bundled)

| Program | Used for | Licence |
|---|---|---|
| Tesseract | OCR | Apache-2.0 |
| Poppler (`pdftotext`, `pdftoppm`) | PDF text, PDF page rendering | GPL-2.0 / GPL-3.0 |
| MuPDF (`mutool`) | PDF text, PDF page rendering | AGPL-3.0 |
| pandoc | universal document conversion | GPL-2.0-or-later |
| LibreOffice (`soffice`) | legacy Office and generic conversion | MPL-2.0 |
| antiword, catdoc | legacy `.doc` | GPL-2.0 |

These are separate executables called through `subprocess`; no code is linked or redistributed with this project.
