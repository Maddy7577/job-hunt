import io


def extract_text(file_data: bytes, mime_type: str) -> str:
    """Extract plain text from a PDF or DOCX binary blob."""
    if mime_type == "application/pdf" or mime_type.endswith("/pdf"):
        return _extract_pdf(file_data)
    if mime_type in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ):
        return _extract_docx(file_data)
    raise ValueError(f"Unsupported MIME type: {mime_type}")


def _extract_pdf(data: bytes) -> str:
    from pdfminer.high_level import extract_text_to_fp
    from pdfminer.layout import LAParams

    out = io.StringIO()
    extract_text_to_fp(io.BytesIO(data), out, laparams=LAParams())
    return out.getvalue().strip()


def _extract_docx(data: bytes) -> str:
    import docx

    doc = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
