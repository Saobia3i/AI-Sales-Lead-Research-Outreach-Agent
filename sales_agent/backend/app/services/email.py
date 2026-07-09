import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

from app.schemas import SendEmailRequest

logger = logging.getLogger(__name__)

def _send_smtp_email_sync(req: SendEmailRequest) -> None:
    """Synchronous core for sending an email via SMTP."""
    sender = req.sender_email.strip()
    recipient = req.recipient_email.strip()
    
    # Create message container
    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = req.subject
    
    # Attach email body
    msg.attach(MIMEText(req.body, "plain", "utf-8"))
    
    # Connect and login using TLS/SSL
    server = None
    try:
        # Connect to server
        server = smtplib.SMTP(req.smtp_server, req.smtp_port, timeout=15)
        server.ehlo()
        server.starttls()  # Upgrade connection to TLS
        server.ehlo()
        
        # Login
        server.login(sender, req.smtp_app_password.strip())
        
        # Send mail
        server.sendmail(sender, [recipient], msg.as_string())
        logger.info(f"SMTP Email sent successfully to {recipient} via {sender}")
    except Exception as e:
        logger.error(f"SMTP sending error to {recipient} via {sender}: {e}")
        raise e
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass


async def send_smtp_email(request: SendEmailRequest) -> None:
    """Asynchronous wrapper to send SMTP emails without blocking the event loop."""
    await asyncio.get_event_loop().run_in_executor(
        None,
        _send_smtp_email_sync,
        request
    )
