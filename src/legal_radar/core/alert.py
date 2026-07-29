"""Alert-Mail bei Cron-Failures.

Duenner Wrapper um core.smtp.send. Nutzt Repo-Secrets ALERT_EMAIL und
SMTP_URL. Bei fehlenden Secrets: no-op statt Fehler - damit ein rotes
Alert-Step selbst nicht einen ohnehin roten Workflow noch roter macht.

Aufruf aus Workflow:
  python -m legal_radar.core.alert "<subject>" "<body>"
"""

from __future__ import annotations

import os
import sys

from legal_radar.core import smtp


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: python -m legal_radar.core.alert <subject> <body>", file=sys.stderr)
        return 2

    subject = sys.argv[1]
    body = sys.argv[2]
    smtp_url = os.getenv("SMTP_URL", "")
    empfaenger = os.getenv("ALERT_EMAIL", "").strip()

    if not smtp_url or not empfaenger:
        print("alert: SMTP_URL oder ALERT_EMAIL leer, uebersprungen.", file=sys.stderr)
        return 0

    try:
        gesendet = smtp.send(
            subject=subject,
            body=body,
            smtp_url=smtp_url,
            recipients=[empfaenger],
            sender=os.getenv("DIGEST_ABSENDER", "radar@legal-radar.local"),
        )
    except Exception as e:
        print(f"alert: SMTP-Fehler {e}", file=sys.stderr)
        return 1
    print("alert: mail gesendet" if gesendet else "alert: skipped (empty)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
