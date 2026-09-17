"""
Static constants that are *not* environment-dependent.

Environment-dependent values belong in ``src/core/config.py``.
"""

# Root python package that ``Database._import_models`` scans for ``models/`` dirs.
BASE_PACKAGE = "src"

# Accepted MIME types, keyed by short extension. Used by upload validators.
MIME_TYPES = {
    "pdf": ["application/pdf", "pdf"],
    "docx": [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "docx",
    ],
    "txt": ["text/plain", "txt"],
    "csv": ["text/csv", "csv"],
    "xlsx": [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx",
    ],
}
PDF_FILE_TYPE = "application/pdf"
DOCX_FILE_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# Upload limits (bytes).
MAX_DOCUMENT_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_SPREADSHEET_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

# Redis job tracking (see ``src/common/utils/job_tracker.py``).
JOB_TTL_SECONDS = 86400  # 24 h

# Common error message prefixes for log consistency.
FILE_PROCESSING_ERROR = "Error processing file: "
S3_FILE_UPLOAD_ERROR = "Error uploading file to S3: "
FILE_DOWNLOAD_ERROR = "Error downloading the file: "

# Minimal transactional email template. ``str.format`` placeholders:
# title, greeting, body_html, cta_url, cta_label, footer.
BASIC_EMAIL_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<body style="margin:0;padding:0;background:#f4f6f9;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:30px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#fff;border-radius:8px;overflow:hidden;">
        <tr><td style="background:#1f2937;padding:24px 36px;">
          <h1 style="margin:0;color:#fff;font-size:20px;">{title}</h1>
        </td></tr>
        <tr><td style="padding:28px 36px;">
          <p style="margin:0 0 16px;font-size:15px;color:#333;">{greeting}</p>
          <div style="font-size:14px;color:#555;line-height:1.6;">{body_html}</div>
          <table width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0;">
            <tr><td align="center">
              <a href="{cta_url}" style="display:inline-block;background:#1f2937;color:#fff;text-decoration:none;font-size:14px;font-weight:700;padding:12px 28px;border-radius:6px;">{cta_label}</a>
            </td></tr>
          </table>
        </td></tr>
        <tr><td style="background:#f8f9fb;padding:14px 36px;border-top:1px solid #e8ecf0;">
          <p style="margin:0;font-size:12px;color:#999;text-align:center;">{footer}</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
