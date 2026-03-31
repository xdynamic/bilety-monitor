import requests
import json
import os
from datetime import datetime

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
RUN_TYPE = os.environ.get("RUN_TYPE", "check")
AGE = "1989-10-30"

DESTINATIONS = [
    {"label": "🇩🇴 Dominikana",  "iata": ["POP"]},
    {"label": "🇨🇷 Kostaryka",   "iata": ["LIR"]},
    {"label": "🇲🇾 Malezja",     "iata": ["PEN"]},
    {"label": "🇲🇽 Meksyk",      "iata": ["CUN", "PVR"]},
    {"label": "🇱🇰 Sri Lanka",   "iata": ["CMB"]},
    {"label": "🇹🇿 Tanzania",    "iata": ["ZNZ"]},
    {"label": "🇹🇭 Tajlandia",   "iata": ["BKK", "HKT"]},
    {"label": "🇻🇳 Wietnam",     "iata": ["SGN", "PQC"]},
    {"label": "🇻🇪 Wenezuela",   "iata": ["PMV"]},
]

STATE_FILE = "state.json"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://biletyczarterowe.r.pl/",
}

def build_api_url(iata_list, one_way):
    iata_params = "".join(f"&iataDokad%5B%5D={i}" for i in iata_list)
    return (
        f"https://biletyczarterowe.r.pl/api/v4.0/wyszukiwanie/wyszukaj?"
        f"dataUrodzenia%5B%5D={AGE}{iata_params}"
        f"&oneWay={'true' if one_way else 'false'}"
        f"&dataWylotuMin=&dataWylotuMax=&dataPrzylotuMin=&dataPrzylotuMax="
    )

def build_link(iata_list, one_way):
    iata_params = "".join(f"dokad%5B%5D={i}&" for i in iata_list)
    return (
        f"https://biletyczarterowe.r.pl/szukaj?{iata_params}"
        f"oneWay={'true' if one_way else 'false'}"
        f"&przylotDo&przylotOd&wiek%5B%5D={AGE}&wylotDo&wylotOd"
    )

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    })
    print(f"Telegram: {r.status_code}")

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def fetch_offers(iata_list, one_way):
    try:
        r = requests.get(build_api_url(iata_list, one_way), headers=HEADERS, timeout=15)
        return r.json().get("Destynacje", [])
    except Exception as e:
        print(f"Błąd pobierania {iata_list}: {e}")
        return []

def get_offer_id(o):
    return str(o.get("DataLayer", {}).get("id", ""))

def format_date(raw):
    try:
        return datetime.fromisoformat(raw.replace("Z", "")).strftime("%d.%m.%Y")
    except Exception:
        return raw[:10]

def format_offer_short(o):
    data = format_date(o.get("TerminWyjazdu", ""))
    cena = o.get("Cena", "?")
    nazwa = o.get("Nazwa", "")
    flight = o.get("DataLayer", {}).get("name", "")
    return f"  📅 {data}  💰 <b>{cena} zł</b>  {nazwa}\n     🛫 {flight}"

def check_new_offers():
    previous = load_state()
    first_run = not previous
    new_state = {}
    alert_lines = []  # zbieramy wszystkie nowe oferty do JEDNEJ wiadomości

    for dest in DESTINATIONS:
        for one_way in [False, True]:
            key = f"{'_'.join(dest['iata'])}_{'ow' if one_way else 'rt'}"
            offers = fetch_offers(dest["iata"], one_way)
            print(f"[{dest['label']} {'OW' if one_way else 'RT'}] → {len(offers)} ofert")

            current_ids = {get_offer_id(o): o for o in offers if get_offer_id(o)}
            prev_ids = set(previous.get(f"{key}_ids", []))

            new_state[f"{key}_ids"] = list(current_ids.keys())
            new_state[f"{key}_offers"] = offers

            if not first_run and prev_ids:  # prev_ids musi być niepuste żeby wykryć nowości
                new_offers = [o for oid, o in current_ids.items() if oid not in prev_ids]
                if new_offers:
                    dir_label = "tylko tam" if one_way else "tam i z powrotem"
                    link = build_link(dest["iata"], one_way)
                    lines = "\n".join(format_offer_short(o) for o in new_offers)
                    alert_lines.append(
                        f"{dest['label']} <i>({dir_label})</i>\n{lines}\n"
                        f"  🔗 <a href='{link}'>Zobacz na stronie</a>"
                    )

    if first_run:
        counts = []
        for dest in DESTINATIONS:
            rt = new_state.get(f"{'_'.join(dest['iata'])}_rt_offers", [])
            counts.append(f"{dest['label']}: {len(rt)} ofert")
        send_telegram(
            f"✅ <b>Monitor uruchomiony!</b>\n\n" +
            "\n".join(counts) +
            "\n\nSprawdzam co 15 minut. Codziennie o 8:00 podsumowanie. ✈️"
        )
    elif alert_lines:
        # JEDNA wiadomość ze wszystkimi nowościami
        msg = "🆕 <b>Nowe bilety!</b>\n\n" + "\n\n".join(alert_lines)
        # Telegram limit 4096 znaków
        if len(msg) > 4096:
            msg = msg[:4090] + "..."
        send_telegram(msg)
    else:
        print("Brak nowych ofert.")

    save_state(new_state)

def daily_summary():
    today = datetime.now().strftime("%d.%m.%Y")
    parts = [f"☀️ <b>Podsumowanie biletów — {today}</b>\n"]

    for dest in DESTINATIONS:
        dest_parts = [f"\n<b>{dest['label']}</b>"]
        has_offers = False

        for one_way in [False, True]:
            offers = fetch_offers(dest["iata"], one_way)
            dir_label = "Tylko tam" if one_way else "Tam i z powrotem"

            if offers:
                has_offers = True
                offers_sorted = sorted(offers, key=lambda o: o.get("Cena", 9999))
                lines = "\n".join(format_offer_short(o) for o in offers_sorted)
                link = build_link(dest["iata"], one_way)
                dest_parts.append(f"<i>{dir_label}:</i>\n{lines}\n  🔗 <a href='{link}'>Wszystkie ({len(offers)})</a>")
            else:
                dest_parts.append(f"<i>{dir_label}:</i> brak ofert")

        parts.extend(dest_parts)

    full_msg = "\n".join(parts)

    # Jeśli za długie — wyślij osobno per kraj
    if len(full_msg) <= 4096:
        send_telegram(full_msg)
    else:
        send_telegram(f"☀️ <b>Podsumowanie biletów — {today}</b>")
        for dest in DESTINATIONS:
            dest_parts = [f"<b>{dest['label']}</b>"]
            for one_way in [False, True]:
                offers = fetch_offers(dest["iata"], one_way)
                dir_label = "Tylko tam" if one_way else "Tam i z powrotem"
                if offers:
                    offers_sorted = sorted(offers, key=lambda o: o.get("Cena", 9999))
                    lines = "\n".join(format_offer_short(o) for o in offers_sorted)
                    link = build_link(dest["iata"], one_way)
                    dest_parts.append(f"<i>{dir_label}:</i>\n{lines}\n  🔗 <a href='{link}'>Wszystkie ({len(offers)})</a>")
                else:
                    dest_parts.append(f"<i>{dir_label}:</i> brak ofert")
            send_telegram("\n".join(dest_parts))

if __name__ == "__main__":
    print(f"=== RUN_TYPE: {RUN_TYPE} ===")
    if RUN_TYPE == "summary":
        daily_summary()
    else:
        check_new_offers()
