"""Text out of exchange PDFs, page by page, for quoting and verification.

Pages keep their order and numbering (page 1 is the first page of the file), so a quote
found by `finn.pull.quotes.verify_quote` can be cited as "p. N" and linked as `#page=N`.
A file whose pages carry almost no text is a scan; FINN does not quote scans, because a
quote it cannot find in a text layer cannot be verified.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SCANNED_CHARS_PER_PAGE = 200


@dataclass(frozen=True, slots=True)
class PdfText:
    pages: list[str]
    scanned: bool
    # The file's bookmarks as (level, title, page), when it has any. Annual reports
    # often name their sections here; some only carry the names of merged files.
    outline: tuple[tuple[int, str, int], ...] = ()

    def numbered(self, limit_chars: int = 400_000) -> str:
        """Pages joined with markers a model can cite: [[page 3]]."""
        out: list[str] = []
        used = 0
        for i, text in enumerate(self.pages, start=1):
            block = f"[[page {i}]]\n{text}\n"
            if used + len(block) > limit_chars:
                break
            out.append(block)
            used += len(block)
        return "\n".join(out)


def clean_page(text: str) -> str:
    s = text.replace("­", "").replace("ﬁ", "fi").replace("ﬂ", "fl")
    s = re.sub(r"[ \t ]+", " ", s)
    s = re.sub(r"[\x00-\x08\x0b-\x1f]", " ", s)  # bullets some PDFs encode as control characters
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()


class NotAPdf(ValueError):
    pass


def unwrap(data: bytes) -> bytes:
    """Exchange attachments are PDFs, or zips holding one; anything else is refused."""
    if data[:5] == b"%PDF-":
        return data
    if data[:2] == b"PK":
        import io
        import zipfile

        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names = sorted(n for n in z.namelist() if n.lower().endswith(".pdf"))
            if names:
                inner = z.read(names[0])
                if inner[:5] == b"%PDF-":
                    return inner
    raise NotAPdf(f"attachment is not a PDF (starts {data[:8]!r})")


def pdf_text(data: bytes, max_pages: int = 600) -> PdfText:
    import pymupdf

    data = unwrap(data)

    with pymupdf.open(stream=data, filetype="pdf") as doc:  # type: ignore[no-untyped-call]
        pages = [clean_page(doc[i].get_text("text")) for i in range(min(len(doc), max_pages))]
        outline = tuple(
            (int(level), str(title).strip(), int(page))
            for level, title, page, *_ in doc.get_toc(simple=True)
        )
    chars = sum(len(p) for p in pages)
    scanned = not pages or chars / len(pages) < SCANNED_CHARS_PER_PAGE
    return PdfText(pages, scanned, outline)
