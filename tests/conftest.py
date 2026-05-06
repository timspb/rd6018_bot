import os

# Ensure bot/config imports have a valid token during pytest collection.
os.environ.setdefault("TG_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ123456789")
