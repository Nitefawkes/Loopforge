import smtplib
import json
import os
from email.mime.text import MIMEText
import requests

# Add root directory to path for imports
script_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
config_path = os.path.join(script_path, "config", "config.json")

def load_notification_config():
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        return config.get("notifications", {})
    except Exception:
        return {}

def send_email(subject, message):
    cfg = load_notification_config().get("email", {})
    if not cfg.get("enabled", False):
        return
    try:
        msg = MIMEText(message)
        msg['Subject'] = subject
        msg['From'] = cfg.get("from")
        msg['To'] = ", ".join(cfg.get("to", []))
        with smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"]) as server:
            server.starttls()
            server.login(cfg["smtp_user"], cfg["smtp_password"])
            server.sendmail(cfg["from"], cfg["to"], msg.as_string())
    except Exception as e:
        print(f"[Notification] Email send failed: {e}")

def send_slack(message):
    cfg = load_notification_config().get("slack", {})
    if not cfg.get("enabled", False):
        return
    try:
        payload = {"text": message}
        requests.post(cfg["webhook_url"], json=payload, timeout=10)
    except Exception as e:
        print(f"[Notification] Slack send failed: {e}")

def send_discord(message):
    cfg = load_notification_config().get("discord", {})
    if not cfg.get("enabled", False):
        return
    try:
        payload = {"content": message}
        requests.post(cfg["webhook_url"], json=payload, timeout=10)
    except Exception as e:
        print(f"[Notification] Discord send failed: {e}")

def send_alert(subject, message):
    send_email(subject, message)
    send_slack(f"*{subject}*\n{message}")
    send_discord(f"**{subject}**\n{message}") 