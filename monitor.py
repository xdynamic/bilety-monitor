import requests
import json
import os
import hashlib
import re

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
URL = "https://biletyczarterowe.r.pl/szukaj?dokad%5B%5D=BKK&dokad%5B%5D=HKT&oneWay=false&przylotDo&przylotOd&wiek%5B%5D=1989-10-30&wylotDo&wylotOd"
API_URL = "https://biletyczarterowe.r.pl/api/loty?dokad%5B%5D=BKK&dokad%5B%5D=HKT&oneWay=false&wiek%5B%5D=1989-10-30"
STATE_FILE = "last_state.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://biletyczarterowe.r.pl/",
}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"})

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def try_api():
    """Próbuje pobrać dane z API jeśli istnieje"""
    try:
        r = requests.get(API_URL, headers=HEADERS, timeout=15)
        print(f"API status: {r.status_code}, pierwsze 200 znaków: {r.text[:200]}")
        if r.status_code == 200 and r.text.strip().startswith("["):
            data = r.json()
            print(f"API zwróciło {len(data)} ofert")
            return data
    except Exception as e:
        print(f"API niedostępne: {e}")
    return None

def get_page_hash():
    """Pobiera stronę i zwraca hash jej zawartości"""
    r = requests.get(URL, headers=HEADERS, timeout=15)
    # Wycinamy dynamiczne elementy (czas, daty itp.) żeby nie było fałszywych alarmów
    content = r.text
    # Usuwamy znaczniki czasu które mogą się zmieniać przy każdym odświeżeniu
    content = re.sub(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', '', content)
    content = re.sub(r'"timestamp":\d+', '', content)
    return hashlib.md5(content.encode()).hexdigest(), len(content)

def main():
    print("=== Monitor Bilety Tajlandia ===")
    previous = load_state()
    first_run = not previous

    # Najpierw spróbuj API
    offers = try_api()

    if offers is not None:
        # Mamy dane z API - śledzimy konkretne oferty
        current_ids = set(
            str(o.get("id") or o.get("flightId") or o.get("lotId") or json.dumps(o, sort_keys=True))
            for o in offers
        )
        previous_ids = set(previous.get("offer_ids", []))

        print(f"Obecne oferty: {len(current_ids)}, poprzednie: {len(previous_ids)}")

        if not first_run:
            new_offers = [o for o in offers if str(o.get("id") or o.get("flightId") or o.get("lotId") or json.dumps(o, sort_keys=True)) not in previous_ids]
            if new_offers:
                for offer in new_offers:
                    msg = (
                        f"✈️ <b>Nowy bilet do Tajlandii!</b>\n\n"
                        f"🗓 Wylot: {offer.get('dataWylotu') or offer.get('departure') or '?'}\n"
                        f"💰 Cena: {offer.get('cena') or offer.get('price') or '?'} zł\n"
                        f"🏨 {offer.get('hotel') or offer.get('nazwa') or ''}\n"
                        f"🔗 <a href='{URL}'>Zobacz ofertę</a>"
                    )
                    send_telegram(msg)
                    print(f"Wysłano powiadomienie o nowej ofercie!")
            else:
                print("Brak nowych ofert.")
        else:
            print(f"Pierwsze uruchomienie — zapisuję {len(current_ids)} ofert jako bazę.")
            send_telegram(f"✅ Monitor uruchomiony!\nZnaleziono <b>{len(current_ids)}</b> ofert do Tajlandii (BKK/HKT).\nBędziesz powiadamiany o nowych! ✈️")

        save_state({"offer_ids": list(current_ids)})

    else:
        # Fallback: hash całej strony
        print("Używam metody hash strony...")
        current_hash, page_size = get_page_hash()
        previous_hash = previous.get("page_hash")
        print(f"Hash obecny: {current_hash}, poprzedni: {previous_hash}, rozmiar: {page_size}")

        if first_run:
            print("Pierwsze uruchomienie — zapisuję hash.")
            send_telegram(f"✅ Monitor uruchomiony!\nŚledzę zmiany na stronie z biletami do Tajlandii (BKK/HKT).\nBędziesz powiadamiany gdy pojawią się nowe oferty! ✈️")
        elif current_hash != previous_hash:
            print("Strona się zmieniła! Wysyłam powiadomienie.")
            send_telegram(
                f"✈️ <b>Uwaga! Strona z biletami się zmieniła!</b>\n\n"
                f"Mogły pojawić się nowe bilety do Tajlandii (BKK/HKT).\n\n"
                f"🔗 <a href='{URL}'>Sprawdź teraz</a>"
            )
        else:
            print("Brak zmian.")

        save_state({"page_hash": current_hash})

if __name__ == "__main__":
    main()
