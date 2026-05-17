import os
import time
import requests
import sqlite3

# ── Load config from environment variables (Railway) ─────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", 60))

# Build wallet list from env vars (WALLET_1, WALLET_1_LABEL, WALLET_2, etc.)
WALLETS = []
i = 1
while True:
    address = os.environ.get(f"WALLET_{i}")
    label = os.environ.get(f"WALLET_{i}_LABEL", f"Trader {i}")
    if not address:
        break
    WALLETS.append({"address": address, "label": label})
    i += 1

if not WALLETS:
    print("ERROR: No wallets configured! Add WALLET_1 and WALLET_1_LABEL environment variables.")
    exit(1)

if not TELEGRAM_TOKEN or not CHAT_ID:
    print("ERROR: Missing TELEGRAM_TOKEN or CHAT_ID environment variables.")
    exit(1)

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
