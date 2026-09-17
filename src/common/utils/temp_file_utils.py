"""
Temp-file helpers for uploads, URLs and zip folders.

    path, handle = await tmp.create_temp_file(upload_file)      # UploadFile -> temp path
    path, handle = await tmp.create_temp_file_from_url(url)     # download -> temp path
    folder = await tmp.create_temp_folder(zip_upload)           # unzip -> temp dir (None if bad zip)

The "validation file" API stores an upload for a few minutes so a later request
can confirm/commit it (two-step upload UX):

    meta = await tmp.save_validation_file(upload)               # {"file_id": ..., ...}
    path, meta = await tmp.load_validation_file(meta["file_id"])
    tmp.cleanup_validation_file(file_id)
    tmp.cleanup_old_validation_files(max_age_minutes=5)

Always delete temp files in a ``finally`` block.
"""

import json
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import requests
from fastapi import UploadFile


class TempFileUtil:
    async def create_temp_file(
        self, file: UploadFile
    ) -> tuple[str, tempfile._TemporaryFileWrapper]:
        """
        Create a temporary file with the given name and content.
        :param file_name: Name of the temporary file.
        :param file_content: Content to write into the temporary file.
        :return: Path to the temporary file.
        """
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(await file.read())
            temp_file_path = temp_file.name

            return temp_file_path, temp_file

    async def create_temp_file_from_url(
        self, url: str
    ) -> tuple[str, tempfile._TemporaryFileWrapper]:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(response.content)
            temp_file_path = temp_file.name

        return temp_file_path, temp_file

    async def create_temp_file_from_file(
        self, file_content, extension=""
    ) -> tuple[str, tempfile._TemporaryFileWrapper]:
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temp_file:
            file_content.seek(0)
            shutil.copyfileobj(file_content, temp_file)
            temp_path = temp_file.name
        return temp_path, temp_file

    async def create_temp_folder(self, zip_folder: UploadFile) -> str | None:
        tempdir = tempfile.mkdtemp(prefix="_upload")
        zip_path = os.path.join(tempdir, zip_folder.filename)
        with open(zip_path, "wb") as f:
            content = await zip_folder.read()
            f.write(content)

        try:
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(tempdir)
        except zipfile.BadZipFile:
            shutil.rmtree(tempdir)
            return None

        macosx_path = os.path.join(tempdir, "__MACOSX")

        if os.path.exists(macosx_path):
            shutil.rmtree(macosx_path)

        os.remove(zip_path)
        return tempdir

    def _get_validation_temp_dir(self) -> Path:
        """Get or create the validation temp directory"""
        temp_dir = Path(tempfile.gettempdir()) / "app_validation_uploads"
        temp_dir.mkdir(exist_ok=True)
        return temp_dir

    async def save_validation_file(self, file: UploadFile) -> dict[str, str]:
        """Save a file for validation"""
        file_id = str(uuid.uuid4())
        temp_dir = self._get_validation_temp_dir()

        file_path = temp_dir / f"{file_id}.file"
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # Save metadata
        metadata = {
            "file_id": file_id,
            "file_name": file.filename,
            "file_size": file.size,
            "file_type": file.content_type,
            "timestamp": datetime.now().isoformat(),
        }
        metadata_path = temp_dir / f"{file_id}.meta"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f)

        return metadata

    async def load_validation_file(self, file_id: str) -> tuple[Path, dict] | None:
        """
        Load a validation file and its metadata.
        Returns (file_path, metadata) or None if not found.
        """
        temp_dir = self._get_validation_temp_dir()
        file_path = temp_dir / f"{file_id}.file"
        metadata_path = temp_dir / f"{file_id}.meta"

        if not file_path.exists() or not metadata_path.exists():
            return None

        with open(metadata_path) as f:
            metadata = json.load(f)

        return file_path, metadata

    def cleanup_validation_file(self, file_id: str):
        """Delete a specific validation file and its metadata"""
        temp_dir = self._get_validation_temp_dir()
        file_path = temp_dir / f"{file_id}.file"
        metadata_path = temp_dir / f"{file_id}.meta"

        if file_path.exists():
            file_path.unlink()
        if metadata_path.exists():
            metadata_path.unlink()

    def cleanup_old_validation_files(self, max_age_minutes: int = 5):
        """
        Delete validation files older than max_age_minutes.
        Returns count of files deleted.
        """
        temp_dir = self._get_validation_temp_dir()
        if not temp_dir.exists():
            return 0

        cutoff_time = datetime.now() - timedelta(minutes=max_age_minutes)
        deleted_count = 0

        for meta_file in temp_dir.glob("*.meta"):
            try:
                with open(meta_file) as f:
                    metadata = json.load(f)

                file_time = datetime.fromisoformat(metadata["timestamp"])
                if file_time < cutoff_time:
                    file_id = metadata["file_id"]
                    self.cleanup_validation_file(file_id)
                    deleted_count += 1
            except Exception:
                meta_file.unlink(missing_ok=True)
                file_path = meta_file.with_suffix(".file")
                file_path.unlink(missing_ok=True)
                deleted_count += 1

        return deleted_count
