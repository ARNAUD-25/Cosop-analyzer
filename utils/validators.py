"""
Validates that the uploaded file is a valid PDF.

Three checks :
  1. The file extension is .pdf
  2. The file is not empty
  3. The first bytes of the file are "%PDF" (magic bytes)
"""

# Maximum accepted file size: 500 MB
MAX_SIZE_MB = 500


def is_valid_pdf(uploaded_file) -> tuple[bool, str]:
    """
    Returns (True, "")           if the file is valid.
    Returns (False, "message")   if the file is invalid.
    """

    # Check 1: file extension
    if not uploaded_file.name.lower().endswith(".pdf"):
        return False, f"'{uploaded_file.name}' is not a PDF file. Please upload a .pdf file."

    # Check 2: file is not empty
    if uploaded_file.size == 0:
        return False, "The uploaded file is empty."

    # Check 3: maximum file size
    size_mb = uploaded_file.size / (1024 * 1024)
    if size_mb > MAX_SIZE_MB:
        return False, f"File is too large ({size_mb:.1f} MB). Maximum allowed is {MAX_SIZE_MB} MB."

    # Check 4: magic bytes (%PDF-). Every valid PDF starts with these 5 bytes
    uploaded_file.seek(0)
    first_bytes = uploaded_file.read(5)
    uploaded_file.seek(0) 

    if first_bytes != b"%PDF-":
        return False, "This file does not appear to be a valid PDF."

    return True, ""