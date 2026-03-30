import requests
import json
import os
from datetime import datetime

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
RUN_TYPE = os.environ.get("RUN_TYPE", "check")

API = {
    "tam_i_z_powrotem": "https://biletyczarterowe.r.pl/api/v4.0/wyszukiwanie/wyszukaj?iataDokad%5B%5D=BKK&iataDokad%5B%5D=HKT&oneWay=false&dataUrodzenia%5B%5D=1989-10-30&dataWylotuMin=&dataWylotuMax=&dataPrzylotuMin=&dataPrzylotuMax=",
    "tylko_tam":        "https://biletyczarterowe.r.pl/api/v4.0/wyszukiwanie/wyszukaj?iataDokad%5B%5D=BKK&iataDokad%5B%5D=HKT&oneWay=true&dataUrodzenia%5B%5D=1989-10-30&dataWylotuMin=&dataWylotuMax=&dataPrzylotuMin=&dataPrzylotuMax=",
}

LINKS = {
    "tam_i_z_powrotem": "https://biletyczarterowe.r.pl/szukaj?dokad%5B%5D=BKK&dokad%5B%5D=HKT&oneWay=false&przylotDo&przylotOd&wiek%5B%5D=1989-10-30&wylotDo&wylotOd",
    "tylko_tam":        "https://biletyczarterowe.r.pl/szukaj?dokad%5B%5D=BKK&dokad%5B%5D=HKT&oneWay=true&przylotDo&przylotOd&wiek%5B%5D=1989-10-30&wylotDo&wylotOd",
}

LABELS = {
    "tam_i_z_powrotem": "✈️↩️ Tam i z powrotem",
    "tylko_tam":        "✈️ Tylko tam (one-way)",
}

STATE_FILE = "last_state.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://biletyczarterowe.r.pl/",
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
        json.dump(state, f, ensure_ascii=False)

def fetch_offers(key):
    r = requests.get(API[key], headers=HEADERS, timeout=15)
    data = r.json()
    return data.get("Destynacje", [])

def format_offer(o):
    data_raw = o.get("TerminWyjazdu", "")
    try:
        data = datetime.fromisoformat(data_raw.replace("Z", "")).strftime("%d.%m.%Y")
    except Exception:
        data = data_raw[:10]
    cena = o.get("Cena", "?")
    nazwa = o.get("Nazwa", "")
    brand = o.get("DataLayer", {}).get("brand", "")
    flight_name = o.get("DataLayer", {}).get("name", "")
    return f"📅 {data}  |  💰 {cena} zł  |  🌏 {nazwa}\n   ✈️ {flight_name}  ({brand})"

def check_new_offers():
    previous = load_state()
    first_run = not previous
    new_state = dict(previous)
    any_new = False

    for key in API:
        print(f"Pobieram [{key}]...")
        offers = fetch_offers(key)
        print(f"  -> {len(offers)} ofert")

        current_ids = {str(o["DataLayer"]["id"]): o for o in offers if o.get("DataLayer", {}).get("id")}
        prev_ids = set(previous.get(f"{key}_ids", []))

        new_state[f"{key}_ids"] = list(current_ids.keys())
        new_state[f"{key}_offers"] = offers

        if not first_run:
            new_offers = [o for id, o in current_ids.items() if id not in prev_ids]
            if new_offers:
                any_new = True
                lines = "\n\n".join(format_offer(o) for o in new_offers)
                send_telegram(
                    f"🆕 <b>Nowe bilety — {LABELS[key]}!</b>\n\n"
                    f"{lines}\n\n"
                    f"🔗 <a href='{LINKS[key]}'>Zobacz na stronie</a>"
                )

    if first_run:
        parts = []
        for key in API:
            offers = new_state.get(f"{key}_offers", [])
            parts.append(f"{LABELS[key]}: <b>{len(offers)}</b> ofert")
        send_telegram(
            f"✅ <b>Monitor biletów uruchomiony!</b>\n\n"
            + "\n".join(parts) +
            f"\n\nSprawdzam co 15 minut, codziennie o 8:00 podsumowanie. ✈️"
        )
    elif not any_new:
        print("Brak nowych ofert.")

    save_state(new_state)

def daily_summary():
    today = datetime.now().strftime("%d.%m.%Y")
    parts = [f"☀️ <b>Podsumowanie biletów do Tajlandii</b>\n{today}\n"]

    for key in API:
        offers = fetch_offers(key)
        parts.append(f"\n<b>{LABELS[key]}:</b>")
        if offers:
            offers_sorted = sorted(offers, key=lambda o: o.get("Cena", 9999))
            lines = "\n\n".join(format_offer(o) for o in offers_sorted)
            parts.append(lines)
            parts.append(f"\n🔗 <a href='{LINKS[key]}'>Zobacz wszystkie ({len(offers)})</a>")
        else:
            parts.append(f"Brak ofert\n🔗 <a href='{LINKS[key]}'>Sprawdź ręcznie</a>")

    send_telegram("\n".join(parts))

if __name__ == "__main__":
    print(f"=== RUN_TYPE: {RUN_TYPE} ===")
    if RUN_TYPE == "summary":
        daily_summary()
    else:
        check_new_offers()
