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
    "United-States",
    "Canada",
    "Australia",
    "Japan",
    "China",
    "India",
    "Brazil",
    "Mexico",
    "South-Korea",
    "South-Africa",
    "Turkey",
    "Russia",
    "Indonesia",
    "Malaysia",
    "Thailand"
]

LAND_COORDINATEN = {
    "United Kingdom": (52.3555, -1.1743),
    "Germany": (51.1657, 10.4515),
    "Netherlands": (52.1326, 5.2913),
    "Belgium": (50.5039, 4.4699),
    "France": (46.2276, 2.2137),
    "Spain": (40.4637, -3.7492),
    "Italy": (41.8719, 12.5674),
    "Poland": (51.9194, 19.1451),
    "Sweden": (60.1282, 18.6435),
    "Denmark": (56.2639, 9.5018),
    "Norway": (60.4720, 8.4689),
    "Finland": (61.9241, 25.7482),
    "Austria": (47.5162, 14.5501),
    "Switzerland": (46.8182, 8.2275),
    "Portugal": (39.3999, -8.2245),
    "United States": (37.0902, -95.7129),
    "Canada": (56.1304, -106.3468),
    "Australia": (-25.2744, 133.7751),
    "Japan": (36.2048, 138.2529),
    "China": (35.8617, 104.1954),
    "India": (20.5937, 78.9629),
    "Brazil": (-14.2350, -51.9253),
    "Mexico": (23.6345, -102.5528),
    "South Korea": (35.9078, 127.7669),
    "South Africa": (-30.5595, 22.9375),
    "Turkey": (38.9637, 35.2433),
    "Russia": (61.5240, 105.3188),
    "Indonesia": (-0.7893, 113.9213),
    "Malaysia": (4.2105, 101.9758),
    "Thailand": (15.8700, 100.9925)
}

def haal_bedrijven_pagina(land, pagina=1):
    try:
        url = f"https://www.enfpaper.com/directory/mrf/{land}?page={pagina}"
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
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
        print(f"  Pagina {pagina}: {len(bedrijven)} bedrijven")
        return bedrijven
    except Exception as e:
        print(f"Fout bij {land} pagina {pagina}: {e}")
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
    land_naam = land.replace("-", " ")
    if land_naam in LAND_COORDINATEN:
        return LAND_COORDINATEN[land_naam]
    return None, None

alle_bedrijven = []
for land in LANDEN:
    print(f"\n--- {land} ---")
    land_bedrijven = []
    for pagina in range(1, 20):
        bedrijven = haal_bedrijven_pagina(land, pagina)
        if bedrijven:
            land_bedrijven.extend(bedrijven)
            time.sleep(3)
        else:
            break
    print(f"Totaal {land}: {len(land_bedrijven)}")
    alle_bedrijven.extend(land_bedrijven)
    time.sleep(5)

print(f"\nTotaal gevonden: {len(alle_bedrijven)} bedrijven")

per_land = {}
for b in alle_bedrijven:
    per_land[b["land"]] = per_land.get(b["land"], 0) + 1
print("\nBedrijven per land:")
for l, n in sorted(per_land.items()):
    print(f"  {l}: {n}")

print("\nCoordinaten ophalen...")
regio_cache = {}
resultaten = []
for b in alle_bedrijven:
    sleutel = b["regio"] + b["land"]
    if sleutel not in regio_cache:
        lat, lon = zoek_coordinaten(b["regio"], b["land"])
        regio_cache[sleutel] = (lat, lon)
        time.sleep(1)
    else:
        lat, lon = regio_cache[sleutel]
    if lat and lon:
        b["lat"] = lat
        b["lon"] = lon
        resultaten.append(b)

with open("bedrijven.json", "w", encoding="utf-8") as f:
    json.dump(resultaten, f, ensure_ascii=False)

print(f"\n✅ {len(resultaten)} bedrijven opgeslagen!")