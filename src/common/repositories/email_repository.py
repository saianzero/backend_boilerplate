"""
SMTP email sender.

Synchronous ``smtplib`` under the hood; call it from a background task or wrap
in ``asyncio.to_thread`` when sending from a request handler.

Example
-------
    from src.common.repositories.email_repository import EmailRepository
    from src.constants import BASIC_EMAIL_HTML_TEMPLATE

    html = BASIC_EMAIL_HTML_TEMPLATE.format(
        title="Welcome", greeting="Hi Ada,", body_html="<p>Your account is ready.</p>",
        cta_url="https://app.example.com", cta_label="Open app", footer="Automated message.",
    )
    ok = EmailRepository.send_email(
        receiver_email="ada@example.com",
        subject="Welcome",
        body="Your account is ready.",      # plain-text fallback
        html_body=html,
        attachment_path="/tmp/report.pdf",  # optional
    )
"""

import logging
import os
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.core.config import (
    EMAIL_HOST,
    EMAIL_HOST_PASSWORD,
    EMAIL_HOST_USER,
    EMAIL_PORT,
    EMAIL_USE_TLS,
    SENDER_EMAIL,
)

logger = logging.getLogger(__name__)


class EmailRepository:
    @staticmethod
    def send_email(
        receiver_email: str,
        subject: str,
        body: str,
        attachment_path: str | None = None,
        attachment_filename: str | None = None,
        html_body: str | None = None,
    ) -> bool:
        """Send an email using SMTP. If html_body is provided, sends multipart/alternative with both plain and HTML parts."""

        server = None  # Initialize server variable

        try:
            msg = MIMEMultipart("mixed")
            msg["From"] = SENDER_EMAIL
            msg["To"] = receiver_email
            msg["Subject"] = subject

            if html_body:
                alternative = MIMEMultipart("alternative")
                alternative.attach(MIMEText(body, "plain"))
                alternative.attach(MIMEText(html_body, "html"))
                msg.attach(alternative)
            else:
                msg.attach(MIMEText(body, "plain"))

            if attachment_path:
                with open(attachment_path, "rb") as f:
                    file_part = MIMEBase("application", "octet-stream")
                    file_part.set_payload(f.read())

                encoders.encode_base64(file_part)
                # filename = attachment_path.split("/")[-1]
                filename = attachment_filename or os.path.basename(attachment_path)
                file_part.add_header("Content-Disposition", f'attachment; filename="{filename}"')

                msg.attach(file_part)

            server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
            if EMAIL_USE_TLS:
                server.starttls()

            server.login(EMAIL_HOST_USER, EMAIL_HOST_PASSWORD)
            server.sendmail(SENDER_EMAIL, receiver_email, msg.as_string())

            logger.info(f"Email sent successfully to {receiver_email}!")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {receiver_email}: {str(e)}", exc_info=True)
            return False

        finally:
            if server:
                try:
                    server.quit()
                except Exception as e:
                    logger.warning(f"Error closing SMTP connection: {str(e)}")

    @staticmethod
    async def generate_short_url(long_url: str) -> str:
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"http://tinyurl.com/api-create.php?url={long_url}")
                response.raise_for_status()
                return response.text.strip()
        except Exception as e:
            raise RuntimeError(f"URL shortening failed: {str(e)}") from e
