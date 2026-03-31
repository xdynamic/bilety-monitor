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

def format_offer(o):
    data = format_date(o.get("TerminWyjazdu", ""))
    cena = o.get("Cena", "?")
    nazwa = o.get("Nazwa", "")
    flight = o.get("DataLayer", {}).get("name", "")
    return f"  📅 {data}  💰 <b>{cena} zł</b>  {nazwa}\n     🛫 {flight}"

def check_new_offers():
    previous = load_state()
    first_run = not previous
    new_state = {}
    new_lines = []
    price_lines = []
    gone_lines = []

    for dest in DESTINATIONS:
        for one_way in [False, True]:
            key = f"{'_'.join(dest['iata'])}_{'ow' if one_way else 'rt'}"
            offers = fetch_offers(dest["iata"], one_way)
            print(f"[{dest['label']} {'OW' if one_way else 'RT'}] → {len(offers)} ofert")

            current = {get_offer_id(o): o for o in offers if get_offer_id(o)}
            prev_data = previous.get(f"{key}_data", {})  # {id: {cena, nazwa, data, flight}}

            # Zapisz aktualny stan
            new_state[f"{key}_data"] = {
                oid: {
                    "cena": o.get("Cena"),
                    "nazwa": o.get("Nazwa"),
                    "data": format_date(o.get("TerminWyjazdu", "")),
                    "flight": o.get("DataLayer", {}).get("name", ""),
                }
                for oid, o in current.items()
            }

            if first_run or not prev_data:
                continue

            dir_label = "tylko tam" if one_way else "tam i z powrotem"
            link = build_link(dest["iata"], one_way)
            header = f"{dest['label']} <i>({dir_label})</i>"

            # Nowe oferty (ID których nie było)
            for oid, o in current.items():
                if oid not in prev_data:
                    new_lines.append(f"{header}\n{format_offer(o)}\n  🔗 <a href='{link}'>Zobacz</a>")

            # Zmiany cen (to samo ID, inna cena)
            for oid, o in current.items():
                if oid in prev_data:
                    stara = prev_data[oid]["cena"]
                    nowa = o.get("Cena")
                    if stara != nowa and stara is not None and nowa is not None:
                        roznica = nowa - stara
                        strzalka = "⬇️" if roznica < 0 else "⬆️"
                        flight = prev_data[oid]["flight"]
                        data = prev_data[oid]["data"]
                        price_lines.append(
                            f"{header}\n"
                            f"  🛫 {flight}\n"
                            f"  📅 {data}\n"
                            f"  {strzalka} <b>{stara} zł → {nowa} zł</b> ({roznica:+d} zł)\n"
                            f"  🔗 <a href='{link}'>Zobacz</a>"
                        )

            # Zniknięte oferty
            for oid, prev_o in prev_data.items():
                if oid not in current:
                    gone_lines.append(
                        f"{header}\n"
                        f"  🛫 {prev_o['flight']}\n"
                        f"  📅 {prev_o['data']}  💰 {prev_o['cena']} zł"
                    )

    if first_run:
        counts = []
        for dest in DESTINATIONS:
            key_rt = f"{'_'.join(dest['iata'])}_rt_data"
            n = len(new_state.get(key_rt, {}))
            counts.append(f"{dest['label']}: {n} ofert")
        send_telegram(
            "✅ <b>Monitor uruchomiony!</b>\n\n" +
            "\n".join(counts) +
            "\n\nSprawdzam co 15 minut.\nCodziennie o 8:00 podsumowanie. ✈️"
        )
    else:
        if new_lines:
            msg = "🆕 <b>Nowe bilety!</b>\n\n" + "\n\n".join(new_lines)
            send_telegram(msg[:4096])

        if price_lines:
            msg = "💸 <b>Zmiany cen!</b>\n\n" + "\n\n".join(price_lines)
            send_telegram(msg[:4096])

        if gone_lines:
            msg = "❌ <b>Oferty które zniknęły:</b>\n\n" + "\n\n".join(gone_lines)
            send_telegram(msg[:4096])

        if not new_lines and not price_lines and not gone_lines:
            print("Brak zmian.")

    save_state(new_state)

def daily_summary():
    today = datetime.now().strftime("%d.%m.%Y")
    parts = [f"☀️ <b>Podsumowanie biletów — {today}</b>\n"]

    for dest in DESTINATIONS:
        dest_parts = [f"\n<b>{dest['label']}</b>"]
        for one_way in [False, True]:
            offers = fetch_offers(dest["iata"], one_way)
            dir_label = "Tylko tam" if one_way else "Tam i z powrotem"
            if offers:
                offers_sorted = sorted(offers, key=lambda o: o.get("Cena", 9999))
                lines = "\n".join(format_offer(o) for o in offers_sorted)
                link = build_link(dest["iata"], one_way)
                dest_parts.append(f"<i>{dir_label}:</i>\n{lines}\n  🔗 <a href='{link}'>Wszystkie ({len(offers)})</a>")
            else:
                dest_parts.append(f"<i>{dir_label}:</i> brak ofert")
        parts.extend(dest_parts)

    full_msg = "\n".join(parts)
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
                    lines = "\n".join(format_offer(o) for o in offers_sorted)
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
