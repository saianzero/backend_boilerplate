import csv
import io
import logging

import chardet
import pandas as pd
from fastapi import HTTPException, UploadFile

from src.constants import MAX_SPREADSHEET_UPLOAD_BYTES

logger = logging.getLogger(__name__)


class CSVUtil:
    """
    CSV / Excel ingestion helpers.

        contents = await upload.read()
        await csv_util.validate_file(upload, contents)             # size + extension
        csv_text = await csv_util.detect_structured_file_format(contents)  # xlsx -> csv text, encoding sniff
        reader = await csv_util.parse_csv_contents(csv_text)       # csv.DictReader with dialect detection
        column = csv_util.find_column(reader.fieldnames, ["name", "item name"])  # tolerant header lookup
        for row in reader:
            ...
    """

    @staticmethod
    def find_column(fieldnames, candidates: list[str]) -> str | None:
        """Return the actual header matching any of ``candidates`` (case/space-insensitive)."""
        if not fieldnames:
            return None
        normalized = {f.lower().strip(): f for f in fieldnames}
        for c in candidates:
            if c.lower().strip() in normalized:
                return normalized[c.lower().strip()]
        return None

    async def validate_file(self, file: UploadFile, contents: bytes):
        """
        Validates uploaded file for corruption, password protection, and correct format.
        """

        if len(contents) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        if len(contents) > MAX_SPREADSHEET_UPLOAD_BYTES:
            raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")

        filename = file.filename.lower() if file.filename else ""
        allowed_extensions = {".csv", ".xlsx"}
        if not any(filename.endswith(ext) for ext in allowed_extensions):
            raise HTTPException(
                status_code=400,
                detail=f"File '{file.filename}' has unsupported format. Allowed: CSV, XLSX",
            )

        return

    async def detect_structured_file_format(self, contents: bytes):
        """Detect if uploaded file is Excel or CSV and convert to CSV text"""

        if contents[:2] == b"PK" or contents[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            logger.info("Detected Excel file, converting to CSV")
            try:
                df = pd.read_excel(io.BytesIO(contents))

                csv_text = df.to_csv(index=False)
                logger.info(f"Successfully converted Excel to CSV with {len(df)} rows")

            except Exception as e:
                logger.error(f"Failed to read Excel file: {e}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Failed to read Excel file. Please ensure it's a valid Excel file or convert it to CSV format. Error: {str(e)}",
                )
        else:
            logger.info("Processing as CSV file")

            encodings_to_try = []

            detected = chardet.detect(contents)
            if detected["encoding"] and detected.get("confidence", 0) > 0.7:
                encodings_to_try.append(detected["encoding"])

            encodings_to_try.extend(["utf-8", "latin-1", "cp1252", "iso-8859-1"])

            csv_text = None
            for encoding in encodings_to_try:
                try:
                    csv_text = contents.decode(encoding)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue

            if csv_text is None:
                raise HTTPException(
                    status_code=400,
                    detail="Unable to decode CSV file. Please ensure it's in UTF-8, Latin-1, or Windows-1252 encoding.",
                )
        return csv_text

    async def parse_csv_contents(self, csv_text: str):
        """Parse CSV text into a DictReader with dialect detection"""
        csv_sniffer = csv.Sniffer()
        logger.info("Detecting CSV dialect")
        try:
            sample = csv_text[:1024]
            dialect = csv_sniffer.sniff(sample, delimiters=",\t;|")
            lines = csv_text.splitlines()
            csv_reader = csv.DictReader(lines, dialect=dialect)
            logger.info(f"Detected CSV delimiter: {dialect.delimiter}")
        except csv.Error:
            logger.warning("Failed to detect CSV dialect, falling back to comma delimiter")
            lines = csv_text.splitlines()
            csv_reader = csv.DictReader(lines)

        if not csv_reader.fieldnames:
            raise HTTPException(
                status_code=400,
                detail="CSV has no header row, missing columns, or is empty",
            )
        return csv_reader
