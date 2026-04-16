#!/usr/bin/python3

"""Lightweight storage monitor for Raspberry Pi deployments.

The module exposes ``start_storage_monitor`` which spins up a background thread
that checks the configured filesystem at a fixed interval.  When disk usage
crosses the configured threshold the monitor sends an email using the same
credentials the rest of the project already relies on.
"""

import base64
import os
import shutil
import smtplib
import threading
import time
from datetime import datetime
from email.mime.text import MIMEText

try:
    import netifaces  # type: ignore
except Exception:  # pragma: no cover - optional dependency on the Pi
    netifaces = None


def _now_str():
    return datetime.now().strftime("%Y-%m-%d-%H-%M-%S")


def _strip_quotes(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def get_user_config(file_name="userInfo.in", splitter_char="="):
    """Parse ``userInfo.in`` into a dictionary."""
    cfg = {}
    try:
        with open(file_name) as handle:
            for raw_line in handle:
                line = raw_line.split("#", 1)[0].strip()
                if not line or splitter_char not in line:
                    continue
                key, value = line.split(splitter_char, 1)
                cfg[key.strip()] = _strip_quotes(value.strip())
    except Exception:
        pass
    return cfg


def _decode_password(encoded):
    rounds = 1
    secret = ""
    parts = encoded.split("|||") if encoded else []
    if parts:
        if parts[0].isdigit():
            rounds = int(parts[0])
        secret = parts[1] if len(parts) > 1 else ""
    for _ in range(max(1, rounds)):
        try:
            secret = base64.b64decode(secret)
        except Exception:
            break
    return secret


def _resolve_ip():
    if netifaces is None:
        return "unknown"
    try:
        return netifaces.ifaddresses("eth0")[netifaces.AF_INET][0]["addr"]
    except Exception:
        return "unknown"


def send_email(message, user_config, subject="Storage usage high"):
    """Send a notification email.  Returns ``True`` if the mail left the host."""
    try:
        if user_config.get("Enable_Email", "false").lower() != "true":
            return False

        recipient_email = user_config.get("Email", "")
        email_user = user_config.get("WD_Email", "")
        if not recipient_email or not email_user:
            return False

        body = (
            "Hello {name},\n\n"
            "This is an automated notification from the RPi watchdog.\n\n"
            "{body}\n\n"
            "Date and Time: {ts}\n"
            "IP address: {ip}\n\n"
            "-RPi Watchdog"
        ).format(
            name=user_config.get("Name", "User"),
            body=message,
            ts=_now_str(),
            ip=_resolve_ip(),
        )

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = email_user
        msg["To"] = recipient_email

        smtp_address = user_config.get("WD_SMTP", "")
        smtp_port = int(user_config.get("WD_SMTP_Port", 465))
        use_ssl = user_config.get("WD_SSL", "true").lower() == "true"
        password = _decode_password(user_config.get("WD_Pass", ""))

        server = None
        try:
            if use_ssl:
                server = smtplib.SMTP_SSL(smtp_address, smtp_port)
            else:
                server = smtplib.SMTP(smtp_address, smtp_port)

            server.ehlo()
            if email_user:
                try:
                    server.login(email_user, password)
                except Exception:
                    return False
            server.sendmail(email_user, [recipient_email], msg.as_string())
        finally:
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    pass
        return True
    except Exception:
        return False


def get_usage_percent(path="/"):
    try:
        total, used, _ = shutil.disk_usage(path)
        return (used * 100.0 / total) if total else 0.0
    except Exception:
        return 0.0


class StorageMonitor(threading.Thread):
    """Background thread that watches disk usage and sends email alerts."""

    def __init__(
        self,
        user_config,
        check_path="/",
        threshold_pct=85.0,
        interval_sec=600,
        cooldown_sec=86400,
        state_file=None,
        name="StorageMonitor",
    ):
        super(StorageMonitor, self).__init__(name=name)
        self.daemon = True
        self.user_config = dict(user_config or {})
        self.check_path = check_path
        self.threshold_pct = float(threshold_pct)
        self.interval_sec = int(max(10, interval_sec))
        self.cooldown_sec = int(max(60, cooldown_sec))
        self.state_file = state_file  # kept for backward compatibility
        self._stop_event = threading.Event()
        self._last_notified = 0.0
        self._was_above = False
        # Cache callables so the thread can keep running during interpreter shutdown
        self._send_email = send_email
        self._get_usage_percent = get_usage_percent

    def stop(self):
        self._stop_event.set()

    def _should_notify(self, now, above):
        if not above:
            return False
        if not self._was_above:
            return True
        return (now - self._last_notified) >= self.cooldown_sec

    def _build_message(self, pct):
        return (
            "Storage usage is {pct:.1f}% on filesystem for '{path}'.\n"
            "Threshold: {threshold:.1f}%\n"
            "Path checked: {real_path}\n"
        ).format(
            pct=pct,
            path=self.check_path,
            threshold=self.threshold_pct,
            real_path=os.path.realpath(self.check_path),
        )

    def run(self):
        while not self._stop_event.is_set():
            try:
                pct = self._get_usage_percent(self.check_path)
                now = time.time()
                above = pct >= self.threshold_pct
                if self._should_notify(now, above):
                    if self._send_email(self._build_message(pct), self.user_config):
                        self._last_notified = now
                self._was_above = above
            except Exception:
                # The monitor must never bring down the host application.
                pass

            if self._stop_event.wait(self.interval_sec):
                break


def start_storage_monitor(
    user_config=None,
    check_path="/",
    threshold_pct=85.0,
    interval_sec=600,
    cooldown_sec=86400,
    state_file=None,
):
    """Create and start the background storage monitor thread."""

    if user_config is None:
        user_config = get_user_config()

    monitor = StorageMonitor(
        user_config=user_config,
        check_path=check_path,
        threshold_pct=threshold_pct,
        interval_sec=interval_sec,
        cooldown_sec=cooldown_sec,
        state_file=state_file,
    )
    monitor.start()
    return monitor
