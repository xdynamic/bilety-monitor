import requests
import json
import os
import hashlib

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
URL = "https://biletyczarterowe.r.pl/szukaj?dokad%5B%5D=BKK&dokad%5B%5D=HKT&oneWay=false&przylotDo&przylotOd&wiek%5B5D=1989-10-30&wylotDo&wylotOd"
STATE_FILE = "last_state.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"})
    print(f"Telegram response: {r.status_code} {r.text}")

def main():
    print("=== START ===")
    
    # Test Telegram
    print("Testuję Telegram...")
    send_telegram("✅ Monitor biletów działa! Sprawdzam oferty co 15 minut.")
    
    # Test strony
    print(f"Pobieram: {URL}")
    try:
        r = requests.get(URL, headers=HEADERS, timeout=15)
        print(f"Status: {r.status_code}")
        print(f"Pierwsze 300 znaków: {r.text[:300]}")
    except Exception as e:
        print(f"Błąd: {e}")

if __name__ == "__main__":
    main()
