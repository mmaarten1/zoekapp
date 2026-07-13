import requests
from bs4 import BeautifulSoup
import json
import time

# Voeg hier de landen toe die je wilt scrapen.
# Gebruik dezelfde schrijfwijze als in de ENF Paper URL (met streepjes i.p.v. spaties)
LANDEN = [
    "United-Kingdom",
    "Germany",
    "France",
    "Netherlands",
    "Belgium",
    "Spain",
    "Italy",
    "U.S.A.",
]

def haal_bedrijven_pagina(land, pagina=1):
    url = f"https://www.enfpaper.com/directory/mrf/{land}?page={pagina}"
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")

    bedrijven = []
    rijen = soup.find_all("tr")
    for rij in rijen:
        cellen = rij.find_all("td")
        if len(cellen) >= 2:
            link = cellen[0].find("a")
            if link and "type=paper-mrf" in link.get("href", ""):
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

def zoek_coordinaten_regio(regio, land):
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": f"{regio} {land}",
            "format": "json",
            "limit": 1
        }
        headers = {"User-Agent": "zoekapp/1.0"}
        response = requests.get(url, headers=headers, params=params)
        resultaten = response.json()
        if resultaten:
            return float(resultaten[0]["lat"]), float(resultaten[0]["lon"])
    except:
        pass
    return None, None

alle_bedrijven = []

print("Bedrijven ophalen voor alle landen...")
for land in LANDEN:
    print(f"\n--- {land} ---")
    pagina = 1
    while True:
        print(f"Pagina {pagina}...")
        bedrijven = haal_bedrijven_pagina(land, pagina)
        if not bedrijven:
            # Lege pagina betekent: geen resultaten meer, ga naar volgend land
            break
        alle_bedrijven.extend(bedrijven)
        pagina += 1
        time.sleep(1)
        if pagina > 100:
            # Veiligheidsgrens, voorkomt oneindige loop bij onverwachte pagina's
            break

print(f"\nTotaal gevonden: {len(alle_bedrijven)} bedrijven (alle landen)")
print("Coordinaten ophalen...")

regio_cache = {}
resultaten = []
for b in alle_bedrijven:
    sleutel = (b["regio"], b["land"])
    if sleutel not in regio_cache:
        lat, lon = zoek_coordinaten_regio(b["regio"], b["land"])
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

print(f"\n✅ {len(resultaten)} bedrijven opgeslagen in bedrijven.json!")
