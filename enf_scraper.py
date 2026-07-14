import requests
from bs4 import BeautifulSoup
import json
import time

LANDEN = [
    "United-Kingdom",
    "Germany",
    "Netherlands",
    "Belgium",
    "France",
    "Spain",
    "Italy",
    "Poland",
    "Sweden",
    "Denmark",
    "Norway",
    "Finland",
    "Austria",
    "Switzerland",
    "Portugal",
    "Czech-Republic",
    "Hungary",
    "Romania",
    "Turkey",
    "United-States",
    "Canada",
    "Australia",
    "China",
    "Japan",
    "India"
]

def haal_bedrijven_pagina(land, pagina=1):
    try:
        url = f"https://www.enfpaper.com/directory/mrf/{land}?page={pagina}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        bedrijven = []
        rijen = soup.find_all("tr")
        for rij in rijen:
            cellen = rij.find_all("td")
            if len(cellen) >= 2:
                link = cellen[0].find("a")
                if link and "paper-mrf" in link.get("href", ""):
                    naam = link.text.strip()
                    regio = cellen[1].text.strip()
                    klanttype = cellen[2].text.strip() if len(cellen) > 2 else ""
                    materialen = cellen[3].text.strip() if len(cellen) > 3 else ""
                    volume = cellen[5].text.strip() if len(cellen) > 5 else ""
                    bedrijven.append({
                        "naam": naam,
                        "regio": regio,
                        "land": land.replace("-", " "),
                        "klanttype": klanttype,
                        "materialen": materialen,
                        "volume": volume
                    })
        return bedrijven
    except:
        return []

def zoek_coordinaten(regio, land):
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": regio + " " + land.replace("-", " "),
            "format": "json",
            "limit": 1
        }
        headers = {"User-Agent": "zoekapp/1.0"}
        response = requests.get(url, headers=headers, params=params, timeout=10)
        resultaten = response.json()
        if resultaten:
            return float(resultaten[0]["lat"]), float(resultaten[0]["lon"])
    except:
        pass
    return None, None

alle_bedrijven = []
for land in LANDEN:
    print(f"\n--- {land} ---")
    for pagina in range(1, 11):
        print(f"Pagina {pagina}...")
        bedrijven = haal_bedrijven_pagina(land, pagina)
        if not bedrijven:
            print(f"Geen bedrijven meer, stop.")
            break
        alle_bedrijven.extend(bedrijven)
        time.sleep(2)

print(f"\nTotaal gevonden: {len(alle_bedrijven)} bedrijven")
print("Coordinaten ophalen...")

regio_cache = {}
resultaten = []
for b in alle_bedrijven:
    sleutel = b["regio"] + b["land"]
    if sleutel not in regio_cache:
        lat, lon = zoek_coordinaten(b["regio"], b["land"])
        regio_cache[sleutel] = (lat, lon)
        time.sleep(2)
    else:
        lat, lon = regio_cache[sleutel]
    if lat and lon:
        b["lat"] = lat
        b["lon"] = lon
        resultaten.append(b)

with open("bedrijven.json", "w", encoding="utf-8") as f:
    json.dump(resultaten, f, ensure_ascii=False)

print(f"\n✅ {len(resultaten)} bedrijven opgeslagen!")