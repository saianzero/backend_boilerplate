"""
``FileUtil`` wraps a FastAPI ``UploadFile`` in a temp file and exposes
size/hash/preview/read helpers. Always call ``cleanup()``.

    fu = FileUtil(upload_file)
    try:
        size = fu.get_file_size()
        digest = fu.get_file_hash("md5")
        preview = fu.preview()          # first 1 KB of text (or 5 rows for csv/xlsx)
        content = fu.read_file()        # str or pandas.DataFrame depending on type
        fu.filepath                     # pathlib.Path of the temp copy
    finally:
        fu.cleanup()

``create_pdf_from_html`` renders HTML to PDF with WeasyPrint (reports, invoices).
"""

import csv
import hashlib
import tempfile
from pathlib import Path

import pandas as pd
import PyPDF2
from fastapi import UploadFile


class FileUtil:
    def __init__(self, upload_file: UploadFile | None = None):
        self.upload_file = upload_file

        if upload_file:
            self.filename = upload_file.filename or "uploaded_file"
            self.file_ext = Path(self.filename).suffix.lower()

            suffix = self.file_ext
            self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            self.temp_file.write(upload_file.file.read())
            self.temp_file.flush()

            self.filepath = Path(self.temp_file.name)

        else:
            self.filename = None  # type: ignore[assignment]
            self.file_ext = None  # type: ignore[assignment]
            self.temp_file = None  # type: ignore[assignment]
            self.filepath = None  # type: ignore[assignment]

    def get_file_size(self) -> int:
        """Return file size in bytes."""
        return self.filepath.stat().st_size

    def get_file_hash(self, algo: str = "sha256") -> str:
        """Return file hash (SHA-256 default)."""
        h = hashlib.new(algo)
        with open(self.filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    def read_file(self) -> str | pd.DataFrame:
        """Read file contents based on type."""
        if self.file_ext in [".txt", ".log", ".md"]:
            return self._read_text()

        elif self.file_ext == ".csv":
            return self._read_csv()

        elif self.file_ext in [".xls", ".xlsx"]:
            return self._read_excel()

        elif self.file_ext == ".pdf":
            return self._read_pdf()

        else:
            raise ValueError(f"Unsupported file type: {self.file_ext}")

    def preview(self, num_bytes: int = 1024) -> str:
        """Get first 1024 bytes/words depending on file type."""
        if self.file_ext in [".txt", ".log", ".md", ".csv"]:
            text = self._read_text()
            return text[:num_bytes]

        elif self.file_ext in [".xls", ".xlsx", ".csv"]:
            df = self.read_file()
            return df.head(5).to_string()  # type: ignore[union-attr]

        elif self.file_ext == ".pdf":
            text = self._read_pdf()
            return text[:num_bytes]

        else:
            with open(self.filepath, "rb") as f:
                return f.read(num_bytes).decode("utf-8", errors="ignore")

    def _read_text(self) -> str:
        with open(self.filepath, encoding="utf-8", errors="ignore") as f:
            return f.read()

    def _read_csv(self) -> pd.DataFrame:
        return pd.read_csv(self.filepath, quoting=csv.QUOTE_MINIMAL)

    def _read_excel(self) -> pd.DataFrame:
        return pd.read_excel(self.filepath)

    def _read_pdf(self) -> str:
        text = []
        with open(self.filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages[:10]:
                text.append(page.extract_text() or "")
        return "\n".join(text)

    async def save_upload_to_temp(self, attachment: UploadFile) -> str:
        temp_dir = tempfile.gettempdir()
        temp_path = f"{temp_dir}/{attachment.filename}"
        # Reset file pointer to the beginning before reading
        await attachment.seek(0)
        with open(temp_path, "wb") as f:
            f.write(await attachment.read())
        return temp_path

    async def create_pdf_from_html(self, html_content: str, filename: str) -> str:
        """Create PDF from HTML content and return temp file path."""
        from weasyprint import HTML

        temp_dir = tempfile.gettempdir()
        temp_path = f"{temp_dir}/{filename}"
        HTML(string=html_content).write_pdf(temp_path)
        return temp_path

    def cleanup(self):
        """Delete temporary file."""
        try:
            self.temp_file.close()
            self.filepath.unlink(missing_ok=True)
        except Exception:
            pass
