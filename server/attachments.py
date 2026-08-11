import base64

import pymupdf

PDF_RENDER_DPI = 200


def to_image_parts(file_bytes: bytes, filename: str) -> list:
    """Turns one uploaded file into a list of OpenAI/OpenRouter-style image_url content
    parts — one per PDF page, or a single part for a plain image file."""
    if filename.lower().endswith(".pdf"):
        images = _pdf_to_png_pages(file_bytes)
    else:
        images = [(file_bytes, _mime_type(filename))]

    return [_image_part(data, mime) for data, mime in images]


def _pdf_to_png_pages(file_bytes: bytes) -> list:
    pages = []
    with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            pixmap = page.get_pixmap(dpi=PDF_RENDER_DPI)
            pages.append((pixmap.tobytes("png"), "image/png"))
    return pages


def _mime_type(filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1]
    return "image/jpeg" if ext in ("jpg", "jpeg") else "image/png"


def _image_part(data: bytes, mime: str) -> dict:
    encoded = base64.b64encode(data).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime};base64,{encoded}"},
    }
