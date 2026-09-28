"""
Magic bytes detection for file type validation.

Provides mime type detection based on file signatures (magic bytes)
to prevent malicious file uploads disguised with fake extensions.
"""

from typing import Literal

# Magic bytes signatures for supported file types
# Format: (magic_bytes, mime_type, extension)
MAGIC_SIGNATURES = [
    # PDF
    (b'%PDF', 'application/pdf', '.pdf'),
    # DOCX (ZIP-based)
    (b'PK\x03\x04', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', '.docx'),
    # DOC (old binary format)
    (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1', 'application/msword', '.doc'),
    # TXT (plain text - no specific magic bytes, just check it's printable)
    (b'', 'text/plain', '.txt'),
    # Markdown (plain text with # or ---)
    (b'', 'text/markdown', '.md'),
]

# Magic bytes for dangerous file types to block
DANGEROUS_SIGNATURES = [
    (b'MZ', 'application/x-msdownload'),       # EXE, DLL, PIF, etc.
    (b'\x7fELF', 'application/x-executable'), # Linux executables
    (b'#!', 'application/x-shellscript'),     # Shell scripts
    (b'PK\x03\x04', 'application/zip'),      # ZIP (but need to distinguish from DOCX)
    (b'Rar', 'application/x-rar-compressed'),  # RAR
    (b'\x1f\x8b', 'application/gzip'),       # GZIP
]


def detect_mime_type(content: bytes) -> str:
    """
    Detect mime type from file content using magic bytes.
    Returns 'application/octet-stream' for unknown types.
    """
    if not content:
        return 'application/octet-stream'

    # Check for PDF
    if content.startswith(b'%PDF'):
        return 'application/pdf'

    # Check for DOCX (ZIP with specific internal structure)
    # DOCX files start with PK (ZIP) but we can't distinguish from other ZIPs here
    # We'll handle this at extension level

    # Check for old DOC format
    if content.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1'):
        return 'application/msword'

    # Check for executable files
    if content.startswith(b'MZ'):
        return 'application/x-msdownload'

    # Check for Linux executables
    if content.startswith(b'\x7fELF'):
        return 'application/x-executable'

    # Check for shell scripts
    if content.startswith(b'#!'):
        return 'application/x-shellscript'

    # Check for RAR
    if content.startswith(b'Rar'):
        return 'application/x-rar-compressed'

    # Check for GZIP
    if content.startswith(b'\x1f\x8b'):
        return 'application/gzip'

    return 'application/octet-stream'


def is_safe_file_type(content: bytes, extension: str) -> tuple[bool, str]:
    """
    Check if file content matches its extension.

    Returns:
        (is_safe, error_message)
    """
    mime = detect_mime_type(content)
    ext = extension.lower()

    # Block dangerous types
    dangerous_types = [
        'application/x-msdownload',
        'application/x-executable',
        'application/x-shellscript',
        'application/x-rar-compressed',
        'application/gzip',
    ]

    if mime in dangerous_types:
        return False, f"File type not allowed: {mime}"

    # For ZIP-based files, we can't verify content matches extension
    # Just check it's a valid ZIP if extension is docx/xlsx/etc
    if ext in ['.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp']:
        if content.startswith(b'PK\x03\x04'):
            # Valid ZIP-based format
            return True, ""
        else:
            return False, f"Extension {ext} requires ZIP-based file format"

    return True, ""


def validate_file_content(content: bytes, filename: str) -> tuple[bool, str]:
    """
    Validate file content against its filename extension.

    Returns:
        (is_valid, error_message)
    """
    import os
    ext = os.path.splitext(filename)[1].lower()

    if not ext:
        return False, "File must have an extension"

    # Check if extension is allowed
    allowed_extensions = {'.pdf', '.docx', '.doc', '.txt', '.md', '.zip'}
    if ext not in allowed_extensions:
        return False, f"Extension {ext} is not allowed"

    # Check content safety
    is_safe, error_msg = is_safe_file_type(content, ext)
    if not is_safe:
        return False, error_msg

    return True, ""
