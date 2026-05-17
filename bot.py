import json
import time
import requests
import sqlite3
import os

# ── Load config ──────────────────────────────────────────────────────────────
with open("config.json") as f:
    config = json.load(f)

TELEGRAM_TOKEN = config["telegram_token"]
CHAT_ID = config["chat_id"]
WALLETS = config["wallets"]
POLL_INTERVAL = config.get("poll_interval_seconds", 60)

# ── Database setup (remembers trades we've already seen) ──────────────────────
conn = sqlite3.connect("seen_trades.db")
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS seen_trades (
        trade_id TEXT PRIMARY KEY
    )
""")
conn.commit()

def already_seen(trade_id):
    cursor.execute("SELECT 1 FROM seen_trades WHERE trade_id = ?", (trade_id,))
    return cursor.fetchone() is not None

def mark_seen(trade_id):
    cursor.execute("INSERT OR IGNORE INTO seen_trades (trade_id) VALUES (?)", (trade_id,))
    conn.commit()

# ── Telegram sender ───────────────────────────────────────────────────────────
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"[Telegram error] {e}")

# ── Polymarket API fetch ──────────────────────────────────────────────────────
def get_trades(wallet_address):
    url = "https://clob.polymarket.com/trades"
    params = {
        "maker_address": wallet_address,
        "limit": 20
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data.get("data", [])
    except Exception as e:
        print(f"[Polymarket error for {wallet_address}] {e}")
        return []

def get_market_title(condition_id):
    try:
        url = f"https://clob.polymarket.com/markets/{condition_id}"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data.get("question", "Unknown Market")
    except:
        return "Unknown Market"

# ── Format the alert message ─────────────────────────────────────────────────
def format_message(label, trade):
    side = trade.get("side", "?").upper()
    size = trade.get("size", "?")
    price = trade.get("price", "?")
    condition_id = trade.get("market", "")

    # Try to get a human-readable market title
    market_title = get_market_title(condition_id) if condition_id else "Unknown Market"

    emoji = "🟢" if side == "BUY" else "🔴"

    try:
        size_fmt = f"${float(size):,.2f}"
    except:
        size_fmt = size

    try:
        price_fmt = f"{float(price) * 100:.1f}¢"
    except:
        price_fmt = price

    return (
        f"{emoji} *{label}* just made a trade!\n"
        f"📊 *Market:* {market_title}\n"
        f"📈 *Side:* {side}\n"
        f"💰 *Size:* {size_fmt} at {price_fmt}"
    )

# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    print(f"🤖 Polymarket bot started. Watching {len(WALLETS)} wallet(s)...")
    send_telegram("🤖 *Polymarket Tracker is online!*\nI'll notify you when your tracked traders make a move.")

    while True:
        for wallet in WALLETS:
            address = wallet["address"]
            label = wallet["label"]
            trades = get_trades(address)

            for trade in trades:
                trade_id = trade.get("id") or trade.get("trade_id")
                if not trade_id:
                    continue
                if already_seen(trade_id):
                    continue

                # New trade found!
                mark_seen(trade_id)
                msg = format_message(label, trade)
                print(f"[New trade] {label}: {trade_id}")
                send_telegram(msg)

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
