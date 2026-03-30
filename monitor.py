import requests
import json
import os
from datetime import datetime

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
RUN_TYPE = os.environ.get("RUN_TYPE", "check")
AGE = "1989-10-30"

DESTINATIONS = [
    {"label": "🇩🇴 Dominikana",  "iata": ["POP"],       },
    {"label": "🇨🇷 Kostaryka",   "iata": ["LIR"],       },
    {"label": "🇲🇾 Malezja",     "iata": ["PEN"],       },
    {"label": "🇲🇽 Meksyk",      "iata": ["CUN", "PVR"],},
    {"label": "🇱🇰 Sri Lanka",   "iata": ["CMB"],       },
    {"label": "🇹🇿 Tanzania",    "iata": ["ZNZ"],       },
    {"label": "🇹🇭 Tajlandia",   "iata": ["BKK", "HKT"],},
    {"label": "🇻🇳 Wietnam",     "iata": ["SGN", "PQC"],},
    {"label": "🇻🇪 Wenezuela",   "iata": ["PMV"],       },
]

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

def fetch_offers(iata_list, one_way):
    url = build_api_url(iata_list, one_way)
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        return r.json().get("Destynacje", [])
    except Exception as e:
        print(f"Błąd pobierania {iata_list}: {e}")
        return []

def format_offer(o):
    data_raw = o.get("TerminWyjazdu", "")
    try:
        data = datetime.fromisoformat(data_raw.replace("Z", "")).strftime("%d.%m.%Y")
    except Exception:
        data = data_raw[:10]
    cena = o.get("Cena", "?")
    nazwa = o.get("Nazwa", "")
    flight_name = o.get("DataLayer", {}).get("name", "")
    return f"📅 {data}  |  💰 <b>{cena} zł</b>  |  {nazwa}\n   🛫 {flight_name}"

def get_offer_id(o):
    return str(o.get("DataLayer", {}).get("id", json.dumps(o, sort_keys=True)))

def check_new_offers():
    previous = load_state()
    first_run = not previous
    new_state = dict(previous)
    any_new = False

    for dest in DESTINATIONS:
        for one_way in [False, True]:
            key = f"{'_'.join(dest['iata'])}_{'ow' if one_way else 'rt'}"
            direction = "tylko tam" if one_way else "tam i z powrotem"
            offers = fetch_offers(dest["iata"], one_way)
            print(f"[{dest['label']} {direction}] → {len(offers)} ofert")

            current_ids = {get_offer_id(o): o for o in offers}
            prev_ids = set(previous.get(f"{key}_ids", []))

            new_state[f"{key}_ids"] = list(current_ids.keys())
            new_state[f"{key}_offers"] = offers

            if not first_run:
                new_offers = [o for id, o in current_ids.items() if id not in prev_ids]
                if new_offers:
                    any_new = True
                    dir_label = "✈️ Tylko tam" if one_way else "✈️↩️ Tam i z powrotem"
                    lines = "\n\n".join(format_offer(o) for o in new_offers)
                    send_telegram(
                        f"🆕 <b>Nowe bilety — {dest['label']}!</b>\n"
                        f"{dir_label}\n\n"
                        f"{lines}\n\n"
                        f"🔗 <a href='{build_link(dest['iata'], one_way)}'>Zobacz na stronie</a>"
                    )

    if first_run:
        lines = []
        for dest in DESTINATIONS:
            rt = new_state.get(f"{'_'.join(dest['iata'])}_rt_offers", [])
            ow = new_state.get(f"{'_'.join(dest['iata'])}_ow_offers", [])
            lines.append(f"{dest['label']}: {len(rt)} (RT) / {len(ow)} (OW)")
        send_telegram(
            f"✅ <b>Monitor biletów uruchomiony!</b>\n\n"
            + "\n".join(lines) +
            f"\n\nSprawdzam co 15 minut.\nCodziennie o 8:00 podsumowanie. ✈️"
        )
    elif not any_new:
        print("Brak nowych ofert.")

    save_state(new_state)

def daily_summary():
    today = datetime.now().strftime("%d.%m.%Y")
    parts = [f"☀️ <b>Podsumowanie biletów — {today}</b>\n"]

    for dest in DESTINATIONS:
        has_any = False
        dest_lines = [f"\n<b>{dest['label']}</b>"]

        for one_way in [False, True]:
            offers = fetch_offers(dest["iata"], one_way)
            dir_label = "✈️ Tylko tam" if one_way else "✈️↩️ Tam i z powrotem"

            if offers:
                has_any = True
                offers_sorted = sorted(offers, key=lambda o: o.get("Cena", 9999))
                lines = "\n".join(format_offer(o) for o in offers_sorted)
                dest_lines.append(f"<i>{dir_label}:</i>\n{lines}")
                dest_lines.append(f"🔗 <a href='{build_link(dest['iata'], one_way)}'>Wszystkie ({len(offers)})</a>")
            else:
                dest_lines.append(f"<i>{dir_label}:</i> brak ofert")

        parts.extend(dest_lines)

    # Telegram ma limit 4096 znaków - podziel jeśli za długie
    full_msg = "\n".join(parts)
    if len(full_msg) <= 4096:
        send_telegram(full_msg)
    else:
        # Wyślij po jednym kraju
        send_telegram(f"☀️ <b>Podsumowanie biletów — {today}</b>")
        for dest in DESTINATIONS:
            dest_parts = [f"<b>{dest['label']}</b>"]
            for one_way in [False, True]:
                offers = fetch_offers(dest["iata"], one_way)
                dir_label = "✈️ Tylko tam" if one_way else "✈️↩️ Tam i z powrotem"
                if offers:
                    offers_sorted = sorted(offers, key=lambda o: o.get("Cena", 9999))
                    lines = "\n".join(format_offer(o) for o in offers_sorted)
                    dest_parts.append(f"<i>{dir_label}:</i>\n{lines}")
                    dest_parts.append(f"🔗 <a href='{build_link(dest['iata'], one_way)}'>Wszystkie ({len(offers)})</a>")
                else:
                    dest_parts.append(f"<i>{dir_label}:</i> brak ofert")
            send_telegram("\n".join(dest_parts))

if __name__ == "__main__":
    print(f"=== RUN_TYPE: {RUN_TYPE} ===")
    if RUN_TYPE == "summary":
        daily_summary()
    else:
        check_new_offers()
