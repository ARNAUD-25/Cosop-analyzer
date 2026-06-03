import io
import pypdf


def read_pdf(uploaded_file) -> str:
    """
    Reads all pages of the PDF.
    """
    uploaded_file.seek(0)
    pdf_bytes = uploaded_file.read()
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))

    all_text = ""
    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            all_text += page_text + "\n"

    return all_text