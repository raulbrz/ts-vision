from google.cloud import vision


def extract_text(file_bytes: bytes, filename: str) -> str:
    client = vision.ImageAnnotatorClient()

    if filename.lower().endswith(".pdf"):
        return _extract_text_from_pdf(client, file_bytes)
    return _extract_text_from_image(client, file_bytes)


def _extract_text_from_image(client: "vision.ImageAnnotatorClient", file_bytes: bytes) -> str:
    image = vision.Image(content=file_bytes)
    response = client.document_text_detection(image=image)
    if response.error.message:
        raise RuntimeError(response.error.message)
    return response.full_text_annotation.text


def _extract_text_from_pdf(client: "vision.ImageAnnotatorClient", file_bytes: bytes) -> str:
    input_config = vision.InputConfig(content=file_bytes, mime_type="application/pdf")
    feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
    request = vision.AnnotateFileRequest(input_config=input_config, features=[feature])

    response = client.batch_annotate_files(requests=[request])
    file_response = response.responses[0]

    pages_text = []
    for page_response in file_response.responses:
        if page_response.error.message:
            raise RuntimeError(page_response.error.message)
        pages_text.append(page_response.full_text_annotation.text)
    return "\n".join(pages_text)
