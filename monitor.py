import requests
import json
import os
import hashlib
import re
from datetime import datetime

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
RUN_TYPE = os.environ.get("RUN_TYPE", "check")  # "check" lub "summary"

URLS = {
    "tam_i_z_powrotem": "https://biletyczarterowe.r.pl/szukaj?dokad%5B%5D=BKK&dokad%5B%5D=HKT&oneWay=false&przylotDo&przylotOd&wiek%5B%5D=1989-10-30&wylotDo&wylotOd",
    "tylko_tam": "https://biletyczarterowe.r.pl/szukaj?dokad%5B%5D=BKK&dokad%5B%5D=HKT&oneWay=true&przylotDo&przylotOd&wiek%5B%5D=1989-10-30&wylotDo&wylotOd",
}

API_URLS = {
    "tam_i_z_powrotem": "https://biletyczarterowe.r.pl/api/loty?dokad%5B%5D=BKK&dokad%5B%5D=HKT&oneWay=false&wiek%5B%5D=1989-10-30",
    "tylko_tam": "https://biletyczarterowe.r.pl/api/loty?dokad%5B%5D=BKK&dokad%5B%5D=HKT&oneWay=true&wiek%5B%5D=1989-10-30",
}

STATE_FILE = "last_state.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://biletyczarterowe.r.pl/",
}

LABELS = {
    "tam_i_z_powrotem": "✈️↩️ Tam i z powrotem",
    "tylko_tam": "✈️ Tylko tam (one-way)",
}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"})
    print(f"Telegram: {r.status_code}")

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def try_api(key):
    try:
        r = requests.get(API_URLS[key], headers=HEADERS, timeout=15)
        print(f"[{key}] API status: {r.status_code}, podgląd: {r.text[:150]}")
        if r.status_code == 200 and r.text.strip().startswith("["):
            data = r.json()
            print(f"[{key}] API zwróciło {len(data)} ofert")
            return data
    except Exception as e:
        print(f"[{key}] API błąd: {e}")
    return None

def get_page_hash(key):
    r = requests.get(URLS[key], headers=HEADERS, timeout=15)
    content = r.text
    content = re.sub(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', '', content)
    content = re.sub(r'"timestamp":\d+', '', content)
    return hashlib.md5(content.encode()).hexdigest()

def format_offer(offer, key):
    cena = offer.get('cena') or offer.get('price') or offer.get('cenaPln') or '?'
    data = offer.get('dataWylotu') or offer.get('departure') or offer.get('wylot') or '?'
    hotel = offer.get('hotel') or offer.get('nazwa') or offer.get('hotelNazwa') or ''
    dest = offer.get('dokad') or offer.get('destination') or ('BKK/HKT')
    hotel_str = f"\n🏨 {hotel}" if hotel else ""
    return f"📅 {data} | 💰 {cena} zł | 🌏 {dest}{hotel_str}"

def check_new_offers():
    """Sprawdza nowe oferty i wysyła alert jeśli coś nowego"""
    previous = load_state()
    first_run = not previous
    new_state = {}
    all_new = {}

    for key in URLS:
        offers = try_api(key)

        if offers is not None:
            offer_ids = set(
                str(o.get("id") or o.get("flightId") or o.get("lotId") or json.dumps(o, sort_keys=True))
                for o in offers
            )
            prev_ids = set(previous.get(f"{key}_ids", []))
            new_state[f"{key}_ids"] = list(offer_ids)
            new_state[f"{key}_offers"] = offers  # zapisz dla dziennego podsumowania

            if not first_run:
                new_offers = [o for o in offers if str(o.get("id") or o.get("flightId") or o.get("lotId") or json.dumps(o, sort_keys=True)) not in prev_ids]
                if new_offers:
                    all_new[key] = new_offers
            else:
                new_state[f"{key}_offers"] = offers
        else:
            # Fallback hash
            current_hash = get_page_hash(key)
            prev_hash = previous.get(f"{key}_hash")
            new_state[f"{key}_hash"] = current_hash

            if not first_run and prev_hash and current_hash != prev_hash:
                all_new[key] = []  # pusta lista = zmiana ale nie wiemy co

    if first_run:
        counts = []
        for key in URLS:
            offers = new_state.get(f"{key}_offers") or []
            counts.append(f"{LABELS[key]}: <b>{len(offers)}</b> ofert")
        send_telegram(
            f"✅ <b>Monitor biletów uruchomiony!</b>\n\n"
            + "\n".join(counts) +
            f"\n\nBędziesz powiadamiany o nowych ofertach co 15 minut.\n"
            f"Codziennie o 8:00 dostaniesz podsumowanie. ✈️"
        )
    elif all_new:
        for key, new_offers in all_new.items():
            if new_offers:
                lines = [format_offer(o, key) for o in new_offers[:5]]
                msg = (
                    f"🆕 <b>Nowe bilety — {LABELS[key]}!</b>\n\n"
                    + "\n\n".join(lines) +
                    f"\n\n🔗 <a href='{URLS[key]}'>Zobacz wszystkie</a>"
                )
            else:
                msg = (
                    f"🆕 <b>Zmiana na stronie — {LABELS[key]}!</b>\n\n"
                    f"Mogły pojawić się nowe bilety.\n"
                    f"🔗 <a href='{URLS[key]}'>Sprawdź teraz</a>"
                )
            send_telegram(msg)
    else:
        print("Brak nowych ofert.")

    save_state({**previous, **new_state})

def daily_summary():
    """Wysyła dzienne podsumowanie wszystkich ofert"""
    previous = load_state()
    msg_parts = [f"☀️ <b>Dzienne podsumowanie biletów do Tajlandii</b>\n{datetime.now().strftime('%d.%m.%Y')}\n"]

    for key in URLS:
        offers = previous.get(f"{key}_offers")
        msg_parts.append(f"\n<b>{LABELS[key]}:</b>")

        if offers:
            # Sortuj po cenie jeśli możliwe
            try:
                offers_sorted = sorted(offers, key=lambda o: float(str(o.get('cena') or o.get('price') or o.get('cenaPln') or 9999).replace(',', '.')))
            except Exception:
                offers_sorted = offers

            lines = [format_offer(o, key) for o in offers_sorted[:8]]
            msg_parts.append("\n".join(lines))
            if len(offers) > 8:
                msg_parts.append(f"... i {len(offers) - 8} więcej")
            msg_parts.append(f"🔗 <a href='{URLS[key]}'>Pokaż wszystkie ({len(offers)})</a>")
        else:
            msg_parts.append("Brak danych (strona nie udostępnia API)")
            msg_parts.append(f"🔗 <a href='{URLS[key]}'>Sprawdź ręcznie</a>")

    send_telegram("\n".join(msg_parts))

if __name__ == "__main__":
    print(f"=== RUN_TYPE: {RUN_TYPE} ===")
    if RUN_TYPE == "summary":
        daily_summary()
    else:
        check_new_offers()
