"""Synthetic PDF builder for tests (module §20) — hand-rolled minimal PDF
byte structure (no reportlab/wkhtmltopdf dependency). Every fixture is a
clearly fictional candidate; nothing here is a real person's resume.

Also provides MALFORMED_PDF_BYTES / TRUNCATED_PDF_BYTES / WRONG_SIGNATURE_BYTES
for the upload-validation tests.
"""

FICTIONAL_RESUME_LINES: list[str] = [
    "Alex Rivera",
    "Backend Engineer",
    "alex.rivera.fictional@example.com",
    "",
    "SUMMARY",
    "Backend engineer with 3 years of experience building distributed",
    "systems in Python and Go, with a focus on high-throughput APIs.",
    "",
    "SKILLS",
    "Python, JS, FastAPI, Postgres, Docker, AWS, Redis, Kubernetes",
    "",
    "EXPERIENCE",
    "Backend Engineer, Nimbus Systems (Jan 2022 - Present)",
    "Designed and scaled a payments microservice handling 2M requests/day",
    "using FastAPI and Postgres, reducing p99 latency by 40 percent.",
    "",
    "PROJECTS",
    "Placement Intelligence Assistant",
    "Built a multi-agent workflow using LangGraph to rank internal job",
    "postings against a candidate's resume, deployed on AWS Lambda.",
    "",
    "CERTIFICATIONS",
    "AWS Certified Solutions Architect - Associate, Amazon, 2023",
    "",
    "ACHIEVEMENTS",
    "Won first place at Nimbus Systems internal hackathon, 2023",
]


def _pdf_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def build_minimal_pdf(pages: list[list[str]]) -> bytes:
    """Builds a small, well-formed, single/multi-page PDF (Helvetica text
    only) with a real xref table and trailer, readable by pypdf. Each
    element of `pages` is the list of text lines on that page.
    """
    n_pages = max(len(pages), 1)
    pages = pages or [[]]

    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: (
            f"<< /Type /Pages /Kids [{' '.join(f'{5 + 2 * i} 0 R' for i in range(n_pages))}] "
            f"/Count {n_pages} >>"
        ).encode("latin-1"),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }

    for i, lines in enumerate(pages):
        content_num = 4 + 2 * i
        page_num = 5 + 2 * i

        stream_lines = ["BT", "/F1 12 Tf", "72 750 Td"]
        for j, line in enumerate(lines):
            if j > 0:
                stream_lines.append("0 -14 TD")
            stream_lines.append(f"({_pdf_escape(line)}) Tj")
        stream_lines.append("ET")
        stream_bytes = "\n".join(stream_lines).encode("latin-1")

        objects[content_num] = (
            f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("latin-1")
            + stream_bytes
            + b"\nendstream"
        )
        objects[page_num] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_num} 0 R >>"
        ).encode("latin-1")

    total_objs = 3 + 2 * n_pages
    buf = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for num in range(1, total_objs + 1):
        offsets[num] = len(buf)
        buf += f"{num} 0 obj\n".encode("latin-1") + objects[num] + b"\nendobj\n"

    xref_offset = len(buf)
    buf += f"xref\n0 {total_objs + 1}\n".encode("latin-1")
    buf += b"0000000000 65535 f \n"
    for num in range(1, total_objs + 1):
        buf += f"{offsets[num]:010d} 00000 n \n".encode("latin-1")
    buf += b"trailer\n"
    buf += f"<< /Size {total_objs + 1} /Root 1 0 R >>\n".encode("latin-1")
    buf += b"startxref\n"
    buf += f"{xref_offset}\n".encode("latin-1")
    buf += b"%%EOF"
    return bytes(buf)


def fictional_resume_pdf() -> bytes:
    """A small, well-formed, multi-page synthetic resume."""
    midpoint = len(FICTIONAL_RESUME_LINES) // 2
    return build_minimal_pdf([FICTIONAL_RESUME_LINES[:midpoint], FICTIONAL_RESUME_LINES[midpoint:]])


def blank_pdf() -> bytes:
    """A valid PDF with a page but no text content — the "scanned/image-only" case."""
    return build_minimal_pdf([[]])


WRONG_SIGNATURE_BYTES = b"This is not a PDF file at all, just plain text pretending to be one."
TRUNCATED_PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog"  # starts right, no trailer/EOF
EMPTY_BYTES = b""
