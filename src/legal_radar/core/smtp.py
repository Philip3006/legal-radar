"""SMTP-Versand fuer den wochentlichen Digest.

Bei leerem smtp_url oder leerer Empfaengerliste: no-op. Kein Fehler.
So bleibt der Workflow auch ohne konfigurierten Mail-Kanal gruen.
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from urllib.parse import unquote, urlsplit


def send(
    subject: str,
    body: str,
    smtp_url: str,
    recipients: list[str],
    sender: str = "radar@legal-radar.local",
) -> bool:
    """Rueckgabe: True wenn versandt, False wenn uebersprungen."""
    if not smtp_url or not recipients:
        return False

    u = urlsplit(smtp_url)
    if u.scheme not in ("smtp", "smtps"):
        raise ValueError(f"SMTP-URL braucht Schema smtp:// oder smtps://, nicht {u.scheme!r}")

    host = u.hostname or "localhost"
    port = u.port or (465 if u.scheme == "smtps" else 587)
    user = unquote(u.username) if u.username else ""
    password = unquote(u.password) if u.password else ""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)

    if u.scheme == "smtps":
        server = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        server.starttls()
    try:
        if user:
            server.login(user, password)
        server.send_message(msg)
    finally:
        server.quit()
    return True
