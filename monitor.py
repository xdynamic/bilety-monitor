import requests
import json
import os
import hashlib

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
URL = "https://biletyczarterowe.r.pl/szukaj?dokad%5B%5D=BKK&dokad%5B%5D=HKT&oneWay=false&przylotDo&przylotOd&wiek%5B%5D=1989-10-30&wylotDo&wylotOd"
STATE_FILE = "last_state.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"})

def get_offers():
    # Try the API endpoint directly
    api_url = "https://biletyczarterowe.r.pl/api/szukaj?dokad%5B%5D=BKK&dokad%5B%5D=HKT&oneWay=false&przylotDo&przylotOd&wiek%5B%5D=1989-10-30&wylotDo&wylotOd"
    try:
        r = requests.get(api_url, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass

    # Fallback: fetch HTML and hash it
    try:
        r = requests.get(URL, headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return {"html_hash": hashlib.md5(r.text.encode()).hexdigest(), "raw": r.text[:500]}
    except Exception as e:
        send_telegram(f"⚠️ Błąd pobierania strony: {e}")
    return None

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def main():
    current = get_offers()
    if current is None:
        return

    previous = load_state()

    # If API returns structured offers
    if isinstance(current, list):
        current_ids = set(str(o.get("id", "") or o.get("flightId", "") or json.dumps(o)) for o in current)
        previous_ids = set(previous.get("ids", []))

        new_offers = [o for o in current if str(o.get("id", "") or o.get("flightId", "") or json.dumps(o)) not in previous_ids]

        if new_offers and previous_ids:  # Don't alert on first run
            for offer in new_offers:
                msg = (
                    f"✈️ <b>Nowy bilet do Tajlandii!</b>\n\n"
                    f"🗓 {offer.get('dataWylotu') or offer.get('departure') or 'brak daty'}\n"
                    f"💰 {offer.get('cena') or offer.get('price') or 'brak ceny'} zł\n"
                    f"🔗 <a href='{URL}'>Zobacz ofertę</a>"
                )
                send_telegram(msg)

        save_state({"ids": list(current_ids)})

    # Fallback: hash-based change detection
    elif isinstance(current, dict) and "html_hash" in current:
        old_hash = previous.get("html_hash")
        new_hash = current["html_hash"]

        if old_hash and old_hash != new_hash:
            send_telegram(
                f"✈️ <b>Strona z biletami się zmieniła!</b>\n\n"
                f"Mogły pojawić się nowe bilety do Tajlandii (BKK/HKT).\n\n"
                f"🔗 <a href='{URL}'>Sprawdź tutaj</a>"
            )

        save_state({"html_hash": new_hash})

if __name__ == "__main__":
    main()
