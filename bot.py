import os
import time
import requests
import sqlite3

# ── Load config from environment variables (Railway) ─────────────────────────
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", 60))

# Build wallet list from env vars
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
    print("ERROR: No wallets configured!")
    exit(1)

if not TELEGRAM_TOKEN or not CHAT_ID:
    print("ERROR: Missing TELEGRAM_TOKEN or CHAT_ID!")
    exit(1)

# ── Database setup ────────────────────────────────────────────────────────────
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

# ── Telegram sender (plain text, no markdown) ─────────────────────────────────
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if not r.ok:
            print(f"[Telegram error] {r.status_code}: {r.text}")
        else:
            print("[Telegram] Message sent!")
    except Exception as e:
        print(f"[Telegram error] {e}")

# ── Polymarket public data API ────────────────────────────────────────────────
def get_trades(wallet_address):
    url = "https://data-api.polymarket.com/activity"
    params = {
        "user": wallet_address.lower(),
        "limit": 20,
        "offset": 0
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            return data
        return data.get("data", [])
    except Exception as e:
        print(f"[Polymarket error for {wallet_address}] {e}")
        return []

# ── Format alert message ──────────────────────────────────────────────────────
def format_message(label, trade):
    side = str(trade.get("side", trade.get("type", "?"))).upper()
    size = trade.get("size", trade.get("amount", "?"))
    price = trade.get("price", "?")
    market_title = trade.get("title") or trade.get("question") or trade.get("market", "Unknown Market")
    outcome = trade.get("outcome", "")

    emoji = "🟢" if side in ["BUY", "YES"] else "🔴"

    try:
        size_fmt = f"${float(size):,.2f}"
    except:
        size_fmt = str(size)

    try:
        price_fmt = f"{float(price) * 100:.1f}c"
    except:
        price_fmt = str(price)

    msg = f"{emoji} {label} just made a trade!\n"
    msg += f"Market: {market_title}\n"
    msg += f"Side: {side}"
    if outcome:
        msg += f" ({outcome})"
    msg += f"\nSize: {size_fmt} at {price_fmt}"
    return msg

# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    print(f"Bot started. Watching {len(WALLETS)} wallet(s)...")
    send_telegram("Polymarket Tracker is online! I will notify you when your tracked traders make a move.")

    while True:
        for wallet in WALLETS:
            address = wallet["address"]
            label = wallet["label"]
            trades = get_trades(address)
            print(f"[{label}] Found {len(trades)} trades")

            for trade in trades:
                trade_id = (
                    trade.get("id") or
                    trade.get("tradeId") or
                    trade.get("txHash") or
                    trade.get("transactionHash")
                )
                if not trade_id:
                    continue
                if already_seen(trade_id):
                    continue

                mark_seen(trade_id)
                msg = format_message(label, trade)
                print(f"[New trade] {label}: {trade_id}")
                send_telegram(msg)

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
