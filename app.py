import os
import json
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
from werkzeug.security import check_password_hash
import requests
import re
import uuid
import datetime
import threading
import time

DATA_DIR = os.environ.get("DATA_DIR", ".")
os.makedirs(DATA_DIR, exist_ok=True)

def datapad(bestandsnaam):
    return os.path.join(DATA_DIR, bestandsnaam)

# Eenmalige migratie: als de Volume nog leeg is, kopieer de data die met Git is meegekomen erheen.
if os.path.abspath(DATA_DIR) != os.path.abspath("."):
    import shutil
    _te_migreren = [
        "bedrijven.json", "papierfabrieken.json", "users.json", "status.json",
        "notities.json", "meldingen.json", "fotos.json", "transport_prijzen.json",
        "geocode_cache.json", "forwarder_wachtwoorden.json", "opgeslagen.json", "snapshots.json",
    ]
    for _bestand in _te_migreren:
        _doel = datapad(_bestand)
        if not os.path.exists(_doel) and os.path.exists(_bestand):
            shutil.copy(_bestand, _doel)
    if os.path.isdir("fotos_uploads") and not os.path.isdir(datapad("fotos_uploads")):
        shutil.copytree("fotos_uploads", datapad("fotos_uploads"))

NOTITIES_FILE = datapad("notities.json")
USERS_FILE = datapad("users.json")

def laad_users():
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}
STATUS_FILE = datapad("status.json")

def laad_status():
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def bewaar_status(data):
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

MELDINGEN_FILE = datapad("meldingen.json")

def laad_meldingen():
    try:
        with open(MELDINGEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def bewaar_meldingen(data):
    with open(MELDINGEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

FOTOS_FILE = datapad("fotos.json")
FOTOS_MAP = datapad("fotos_uploads")

def laad_fotos():
    try:
        with open(FOTOS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def bewaar_fotos(data):
    with open(FOTOS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def laad_notities():
    try:
        with open(NOTITIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def bewaar_notities(data):
    with open(NOTITIES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_user_id():
    return request.cookies.get("user_id") or getattr(request, "nieuw_user_id", "") or ""
GEOCODE_CACHE_FILE = datapad("geocode_cache.json")

def laad_geocode_cache():
    try:
        with open(GEOCODE_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def bewaar_geocode_cache(data):
    with open(GEOCODE_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

import math

def bereken_afstand_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c
def geocode_adres(adres, stad):
    query = ", ".join([x for x in [adres, stad] if x])
    if not query:
        return None
    cache = laad_geocode_cache()
    if query in cache:
        return cache[query]
    try:
        headers = {"User-Agent": "RecycleFind/1.0"}
        params = {"q": query, "format": "json", "limit": 1}
        resp = requests.get("https://nominatim.openstreetmap.org/search", params=params, headers=headers, timeout=8)
        resultaten = resp.json()
        if resultaten:
            lat = float(resultaten[0]["lat"])
            lon = float(resultaten[0]["lon"])
            cache[query] = {"lat": lat, "lon": lon}
            bewaar_geocode_cache(cache)
            return cache[query]
    except Exception as e:
        print(f"Geocode error: {e}")
    return None
from bs4 import BeautifulSoup

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "verander-dit-later-in-iets-geheims")
@app.before_request
def vereis_login():
    toegestaan = ["login", "static", "forwarder_upload"]
    if request.endpoint not in toegestaan and not session.get("ingelogd"):
        return redirect(url_for("login"))

@app.before_request
def zorg_voor_user_id():
    if not request.cookies.get("user_id"):
        request.nieuw_user_id = str(uuid.uuid4())
    else:
        request.nieuw_user_id = None

@app.after_request
def zet_user_cookie(response):
    if getattr(request, "nieuw_user_id", None):
        response.set_cookie("user_id", request.nieuw_user_id, max_age=60*60*24*365*5)
    return response

TENANT_ID = os.environ.get("TENANT_ID", "peute")

with open(datapad("bedrijven.json"), "r", encoding="utf-8") as f:
    ENF_BEDRIJVEN = json.load(f)
with open(datapad("papierfabrieken.json"), "r", encoding="utf-8") as f:
    PAPIERFABRIEKEN = json.load(f)

_bedrijven_gewijzigd = False
for _b in ENF_BEDRIJVEN:
    if "bedrijf_id" not in _b:
        _b["bedrijf_id"] = TENANT_ID
        _bedrijven_gewijzigd = True
if _bedrijven_gewijzigd:
    with open(datapad("bedrijven.json"), "w", encoding="utf-8") as f:
        json.dump(ENF_BEDRIJVEN, f, ensure_ascii=False, indent=2)

for fabriek in PAPIERFABRIEKEN:
    if "lat" not in fabriek or "lon" not in fabriek:
        geo = geocode_adres(fabriek.get("stad", ""), fabriek.get("land", ""))
        if geo:
            fabriek["lat"] = geo["lat"]
            fabriek["lon"] = geo["lon"]
def laad_transport_data():
    try:
        with open(datapad("transport_prijzen.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

TRANSPORT_DATA = laad_transport_data()

def vind_transport_tarieven_dichtbij(lat, lon, straal_km=40):
    resultaat = {}
    if not lat or not lon:
        return resultaat
    for forwarder, steden in TRANSPORT_DATA.items():
        dichtstbijzijnde = None
        for record in steden:
            geo = geocode_adres(record["stad"], "")
            if not geo:
                continue
            afstand = bereken_afstand_km(lat, lon, geo["lat"], geo["lon"])
            if afstand <= straal_km and (dichtstbijzijnde is None or afstand < dichtstbijzijnde["afstand"]):
                dichtstbijzijnde = {"stad": record["stad"], "tarieven": record["tarieven"], "afstand": round(afstand, 1)}
        if dichtstbijzijnde:
            resultaat[forwarder] = dichtstbijzijnde
    return resultaat

def laad_forwarder_wachtwoorden():
    try:
        with open(datapad("forwarder_wachtwoorden.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

UPLOAD_HTML = '''
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>Transportprijzen uploaden</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #f1f5f9; padding: 40px; }
        .box { background: white; padding: 30px; border-radius: 12px; max-width: 420px; margin: 0 auto; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        h1 { font-size: 18px; margin-bottom: 16px; }
        input, select { width: 100%; padding: 10px; margin-bottom: 12px; border: 1px solid #e2e8f0; border-radius: 6px; box-sizing: border-box; }
        button { width: 100%; padding: 10px; background: #2563eb; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; }
        .bericht { padding: 10px; border-radius: 6px; margin-bottom: 12px; font-size: 14px; }
        .succes { background: #f0fdf4; color: #16a34a; }
        .fout { background: #fef2f2; color: #ef4444; }
    </style>
</head>
<body>
    <div class="box">
        <h1>Transportprijzen uploaden</h1>
        {% if bericht %}<div class="bericht {{ 'succes' if succes else 'fout' }}">{{ bericht }}</div>{% endif %}
        <form method="POST" enctype="multipart/form-data">
            <input type="text" name="forwarder" placeholder="Forwarder naam (bv. MSC)" required>
            <input type="password" name="wachtwoord" placeholder="Wachtwoord" required>
            <input type="file" name="bestand" accept=".xlsx,.xls" required>
            <button type="submit">Uploaden</button>
        </form>
    </div>
</body>
</html>
'''

IMPORT_HTML = '''
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>Bedrijven importeren</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #f1f5f9; padding: 40px; }
        .box { background: white; padding: 30px; border-radius: 12px; max-width: 480px; margin: 0 auto; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        h1 { font-size: 18px; margin-bottom: 8px; }
        p { font-size: 13px; color: #64748b; margin-bottom: 16px; }
        input { width: 100%; padding: 10px; margin-bottom: 12px; border: 1px solid #e2e8f0; border-radius: 6px; box-sizing: border-box; }
        button { width: 100%; padding: 10px; background: #2563eb; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; }
        .bericht { padding: 10px; border-radius: 6px; margin-bottom: 12px; font-size: 14px; }
        .succes { background: #f0fdf4; color: #16a34a; }
        .fout { background: #fef2f2; color: #ef4444; }
        table { width: 100%; font-size: 11px; margin-top: 16px; border-collapse: collapse; }
        th, td { border: 1px solid #e2e8f0; padding: 4px 6px; text-align: left; }
    </style>
</head>
<body>
    <div class="box">
        <h1>Bedrijven / Fabrieken importeren</h1>
        <p>Kolommen: Naam, Type (Leverancier/Klant/Fabriek), Land, Stad, Adres, Telefoonnummer, Materialen, Klanttype, Volume, Certificeringen</p>
        {% if bericht %}<div class="bericht {{ 'succes' if succes else 'fout' }}">{{ bericht }}</div>{% endif %}
        <form method="POST" enctype="multipart/form-data">
            <input type="file" name="bestand" accept=".xlsx,.xls" required>
            <button type="submit">Importeren</button>
        </form>
        <table>
            <tr><th>Naam</th><th>Type</th><th>Land</th><th>Stad</th><th>Adres</th><th>Telefoonnummer</th><th>Materialen</th><th>Klanttype</th><th>Volume</th><th>Certificeringen</th></tr>
            <tr><td>Voorbeeld BV</td><td>Leverancier</td><td>Netherlands</td><td>Rotterdam</td><td>Kade 12</td><td>+31 10 1234567</td><td>Paper, Plastic</td><td>Commercial</td><td>5000</td><td>ISO 9001, FSC</td></tr>
            <tr><td>Fabriek XYZ</td><td>Fabriek</td><td>Germany</td><td>Hamburg</td><td></td><td></td><td>Paper, OCC</td><td></td><td></td></tr>
        </table>
        <a href="/importeer-osm" style="display:block;text-align:center;margin-top:16px;font-size:13px;color:#ea580c;">→ Of importeer automatisch vanuit OpenStreetMap (gratis, geen bestand nodig)</a>
    </div>
</body>
</html>
'''

OSM_LANDEN = {
    "Netherlands": "NL", "Germany": "DE", "Belgium": "BE", "France": "FR",
    "United Kingdom": "GB", "Spain": "ES", "Italy": "IT", "Poland": "PL",
    "Austria": "AT", "Switzerland": "CH", "Portugal": "PT", "Sweden": "SE",
    "Norway": "NO", "Denmark": "DK", "Finland": "FI", "Ireland": "IE",
    "Czech Republic": "CZ", "Hungary": "HU", "Greece": "GR", "Romania": "RO",
    "United States": "US", "Canada": "CA", "Australia": "AU", "Brazil": "BR",
    "Mexico": "MX", "India": "IN", "China": "CN", "Japan": "JP",
}

# ============================================
# SCRAPMONSTER.COM IMPORT (schroothandels/recyclingcentra)
# ============================================
SCRAPMONSTER_LANDEN = {
    "Netherlands": "netherlands", "Germany": "germany", "United Kingdom": "united-kingdom",
    "France": "france", "Belgium": "belgium", "Spain": "spain", "Italy": "italy",
    "Poland": "poland", "Switzerland": "switzerland", "Austria": "austria",
    "Sweden": "sweden", "Portugal": "portugal", "Ireland": "ireland", "Finland": "finland",
    "Greece": "greece", "Romania": "romania", "Norway": "norway", "Denmark": "denmark",
    "United States": "united-states", "Canada": "canada", "Australia": "australia",
}

def scrapmonster_importeer_land(land_naam, max_paginas=10):
    """Scrapet ScrapMonster.com voor schroothandels/recyclingcentra per land. Geeft (aantal_nieuw, aantal_gezien) terug."""
    slug = SCRAPMONSTER_LANDEN.get(land_naam)
    if not slug:
        raise ValueError(f"Onbekend land voor ScrapMonster: {land_naam}")

    bestaande = {(b["naam"].strip().lower(), b["land"].strip().lower(), b.get("regio","").strip().lower()) for b in ENF_BEDRIJVEN}
    aantal_nieuw = 0
    aantal_gezien = 0

    for pagina in range(1, max_paginas + 1):
        url = f"https://www.scrapmonster.com/scrap-yard/{slug}/" if pagina == 1 else f"https://www.scrapmonster.com/scrap-yard/{slug}/page/{pagina}"
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (RecycleFind/1.0)"}, timeout=30)
        except Exception:
            break
        if resp.status_code != 200:
            break

        html_tekst = resp.text
        # Elke yard-kaart heeft een link naar /scrap-yard/<naam-slug>/<numeriek-id>
        yard_pattern = re.compile(r'<a[^>]+href="(/scrap-yard/[a-z0-9\-]+/\d+)"[^>]*>([^<]+)</a>')
        matches = list(yard_pattern.finditer(html_tekst))
        if not matches:
            break

        gevonden_deze_pagina = 0
        for i, m in enumerate(matches):
            naam = m.group(2).strip()
            if not naam or len(naam) < 2:
                continue
            gevonden_deze_pagina += 1
            aantal_gezien += 1

            # Kaart-tekst = alles tussen deze link en de volgende (of einde bij de laatste)
            start = m.end()
            eind = matches[i + 1].start() if i + 1 < len(matches) else min(len(html_tekst), start + 4000)
            kaart_segment = html_tekst[start:eind]

            telefoon_match = re.search(r"tel:([+\d()\-\s]{6,20})", kaart_segment)
            telefoon = telefoon_match.group(1).strip() if telefoon_match else ""

            stad = ""
            stad_match = re.search(rf'href="/scrap-yard/{slug}/[a-z\-]+/([a-z\-]+)/?"[^>]*>([^<]+)</a>', kaart_segment)
            if stad_match:
                stad = stad_match.group(2).strip()

            sleutel = (naam.strip().lower(), land_naam.strip().lower(), stad.strip().lower())
            if sleutel in bestaande:
                continue
            bestaande.add(sleutel)

            ENF_BEDRIJVEN.append({
                "naam": naam, "land": land_naam, "regio": stad,
                "materialen": "Metal", "klanttype": "", "volume": "", "url": "",
                "lat": None, "lon": None,
                "adres": "", "telefoon": telefoon,
                "bedrijf_id": TENANT_ID, "brontype": "Schroothandel",
            })
            aantal_nieuw += 1

        if gevonden_deze_pagina == 0:
            break
        time.sleep(2)

    # Geocoderen van de nieuw toegevoegde bedrijven zonder coördinaten (op basis van stad + land)
    for b in ENF_BEDRIJVEN:
        if b.get("bedrijf_id") == TENANT_ID and b.get("brontype") == "Schroothandel" and not b.get("lat") and b.get("land") == land_naam:
            geo = geocode_adres(b.get("regio",""), land_naam)
            if geo:
                b["lat"] = geo["lat"]
                b["lon"] = geo["lon"]

    with open(datapad("bedrijven.json"), "w", encoding="utf-8") as f:
        json.dump(ENF_BEDRIJVEN, f, ensure_ascii=False, indent=2)

    return aantal_nieuw, aantal_gezien

SCRAPMONSTER_IMPORT_HTML = '''
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>ScrapMonster importeren</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #f1f5f9; padding: 40px; }
        .box { background: white; padding: 30px; border-radius: 12px; max-width: 480px; margin: 0 auto; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        h1 { font-size: 18px; margin-bottom: 8px; }
        p { font-size: 13px; color: #64748b; margin-bottom: 16px; }
        select, button { width: 100%; padding: 10px; margin-bottom: 12px; border: 1px solid #e2e8f0; border-radius: 6px; box-sizing: border-box; font-size: 14px; }
        button { background: #ea580c; color: white; border: none; cursor: pointer; font-weight: 600; }
        .bericht { padding: 10px; border-radius: 6px; margin-bottom: 12px; font-size: 14px; }
        .succes { background: #f0fdf4; color: #16a34a; }
        .fout { background: #fef2f2; color: #ef4444; }
    </style>
</head>
<body>
    <div class="box">
        <h1>Bedrijven importeren via ScrapMonster</h1>
        <p>Haalt schroothandels/recyclingcentra op van scrapmonster.com voor het gekozen land (max. 10 pagina's, ca. 200 bedrijven). Kan 30-60 seconden duren.</p>
        {% if bericht %}<div class="bericht {{ 'succes' if succes else 'fout' }}">{{ bericht }}</div>{% endif %}
        <form method="POST">
            <select name="land" required>
                {% for naam in landen %}<option value="{{ naam }}">{{ naam }}</option>{% endfor %}
            </select>
            <button type="submit">Importeren vanuit ScrapMonster</button>
        </form>
        <a href="/importeer-scrapmonster-alle" style="display:block;text-align:center;margin-top:16px;font-size:13px;color:#ea580c;">→ Of importeer in één keer álle landen op de achtergrond</a>
    </div>
</body>
</html>
'''

@app.route("/importeer-scrapmonster", methods=["GET", "POST"])
def importeer_scrapmonster():
    bericht = None
    succes = False
    if request.method == "POST":
        land_naam = request.form.get("land", "")
        try:
            aantal_nieuw, aantal_gezien = scrapmonster_importeer_land(land_naam)
            dubbel, _ = opschonen_bedrijven_en_fabrieken("streng")
            bericht = f"Gelukt! {aantal_nieuw} nieuwe bedrijven toegevoegd uit ScrapMonster voor {land_naam} ({aantal_gezien} gezien). {dubbel} dubbelingen automatisch opgeschoond."
            succes = True
        except Exception as e:
            bericht = f"Er ging iets mis: {e}"

    return render_template_string(SCRAPMONSTER_IMPORT_HTML, bericht=bericht, succes=succes, landen=sorted(SCRAPMONSTER_LANDEN.keys()))

SCRAPMONSTER_BULK_STATUS = {
    "bezig": False, "huidig_land": "", "klaar": 0, "totaal": len(SCRAPMONSTER_LANDEN),
    "nieuw_totaal": 0, "log": [], "mislukt": [],
}

def _scrapmonster_bulk_worker(gebruikersnaam, landen_lijst=None):
    landen_lijst = landen_lijst or sorted(SCRAPMONSTER_LANDEN.keys())
    SCRAPMONSTER_BULK_STATUS["bezig"] = True
    SCRAPMONSTER_BULK_STATUS["klaar"] = 0
    SCRAPMONSTER_BULK_STATUS["nieuw_totaal"] = 0
    SCRAPMONSTER_BULK_STATUS["log"] = []
    SCRAPMONSTER_BULK_STATUS["mislukt"] = []
    SCRAPMONSTER_BULK_STATUS["totaal"] = len(landen_lijst)

    for land_naam in landen_lijst:
        SCRAPMONSTER_BULK_STATUS["huidig_land"] = land_naam
        try:
            aantal_nieuw, aantal_gezien = scrapmonster_importeer_land(land_naam)
            regel = f"✓ {land_naam}: {aantal_nieuw} nieuw ({aantal_gezien} gezien)"
            SCRAPMONSTER_BULK_STATUS["nieuw_totaal"] += aantal_nieuw
        except Exception as e:
            regel = f"✗ {land_naam}: fout ({e})"
            SCRAPMONSTER_BULK_STATUS["mislukt"].append(land_naam)
        SCRAPMONSTER_BULK_STATUS["log"].append(regel)
        SCRAPMONSTER_BULK_STATUS["klaar"] += 1
        time.sleep(5)

    SCRAPMONSTER_BULK_STATUS["huidig_land"] = "Opschonen van dubbelingen..."
    dubbel_opgeschoond, _ = opschonen_bedrijven_en_fabrieken("streng")
    SCRAPMONSTER_BULK_STATUS["huidig_land"] = ""
    SCRAPMONSTER_BULK_STATUS["bezig"] = False

    if gebruikersnaam:
        alle_meldingen = laad_meldingen()
        mislukt_tekst = f" ({len(SCRAPMONSTER_BULK_STATUS['mislukt'])} landen mislukt, kun je opnieuw proberen)" if SCRAPMONSTER_BULK_STATUS["mislukt"] else ""
        alle_meldingen.append({
            "id": str(uuid.uuid4()),
            "tekst": f"ScrapMonster-import klaar! {SCRAPMONSTER_BULK_STATUS['nieuw_totaal']} nieuwe bedrijven toegevoegd over {SCRAPMONSTER_BULK_STATUS['totaal']} landen. {dubbel_opgeschoond} dubbelingen opgeschoond.{mislukt_tekst}",
            "bedrijf": "", "van": "Systeem", "voor_gebruiker": gebruikersnaam, "voor_team": "",
            "gelezen": False, "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
        })
        bewaar_meldingen(alle_meldingen)

@app.route("/importeer-scrapmonster-alle", methods=["GET", "POST"])
def importeer_scrapmonster_alle():
    if request.method == "POST":
        if not SCRAPMONSTER_BULK_STATUS["bezig"]:
            gebruikersnaam = session.get("gebruikersnaam", "")
            alleen_mislukte = request.form.get("alleen_mislukte") == "1"
            landen_lijst = list(SCRAPMONSTER_BULK_STATUS["mislukt"]) if alleen_mislukte and SCRAPMONSTER_BULK_STATUS["mislukt"] else None
            thread = threading.Thread(target=_scrapmonster_bulk_worker, args=(gebruikersnaam, landen_lijst), daemon=True)
            thread.start()
        return redirect(url_for("importeer_scrapmonster_alle"))

    inhoud = """
<style>
.bulk-log { max-height:300px; overflow-y:auto; background:var(--gray-50); border-radius:8px; padding:12px; font-size:0.8rem; font-family:monospace; margin-top:16px; }
.bulk-log div { padding:2px 0; }
.bulk-balk-track { background:var(--gray-100); border-radius:6px; height:14px; overflow:hidden; margin-top:12px; }
.bulk-balk-fill { background:linear-gradient(90deg,var(--brand-500),var(--brand-700)); height:100%; transition:width 0.3s; }
</style>
<div class="page-title">Alle landen importeren (ScrapMonster)</div>
<div class="info-kaart" style="max-width:600px;">
    <p style="color:var(--gray-500);font-size:0.85rem;margin-bottom:16px;">
        Haalt automatisch, land voor land, schroothandels op van scrapmonster.com voor alle {{ totaal }} ondersteunde landen.
        Kan lang duren. Je kunt deze pagina open laten staan of sluiten — het draait op de achtergrond door.
    </p>
    <div id="bulkKnopWrap">
        <button onclick="startBulk()" id="bulkStartBtn" style="padding:10px 20px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-weight:600;cursor:pointer;">Start import van alle landen</button>
    </div>
    <div id="bulkStatus" style="display:none;margin-top:16px;">
        <div style="font-size:0.85rem;color:var(--gray-600);">Bezig met: <b id="bulkHuidig">—</b></div>
        <div class="bulk-balk-track"><div class="bulk-balk-fill" id="bulkBalk" style="width:0%"></div></div>
        <div style="font-size:0.8rem;color:var(--gray-400);margin-top:6px;"><span id="bulkKlaar">0</span> / <span id="bulkTotaal">{{ totaal }}</span> landen · <span id="bulkNieuw">0</span> nieuwe bedrijven tot nu toe</div>
        <div class="bulk-log" id="bulkLog"></div>
        <button onclick="startRetry()" id="bulkRetryBtn" style="display:none;margin-top:12px;padding:8px 16px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-weight:600;cursor:pointer;">Probeer mislukte landen opnieuw</button>
    </div>
</div>
<script>
function startBulk() {
    fetch("/importeer-scrapmonster-alle", {method:"POST"}).then(() => pollBulk());
    document.getElementById("bulkKnopWrap").style.display = "none";
    document.getElementById("bulkStatus").style.display = "block";
}
function startRetry() {
    fetch("/importeer-scrapmonster-alle", {method:"POST", headers:{"Content-Type":"application/x-www-form-urlencoded"}, body:"alleen_mislukte=1"}).then(() => pollBulk());
    document.getElementById("bulkRetryBtn").style.display = "none";
}
async function pollBulk() {
    const res = await fetch("/api/scrapmonster-import-status");
    const data = await res.json();
    document.getElementById("bulkHuidig").textContent = data.huidig_land || (data.bezig ? "..." : "Klaar!");
    document.getElementById("bulkBalk").style.width = (data.klaar / data.totaal * 100) + "%";
    document.getElementById("bulkKlaar").textContent = data.klaar;
    document.getElementById("bulkTotaal").textContent = data.totaal;
    document.getElementById("bulkNieuw").textContent = data.nieuw_totaal;
    document.getElementById("bulkLog").innerHTML = data.log.slice().reverse().map(r => `<div>${r}</div>`).join("");
    if (data.bezig) {
        document.getElementById("bulkRetryBtn").style.display = "none";
        setTimeout(pollBulk, 3000);
    } else if (data.mislukt && data.mislukt.length > 0) {
        document.getElementById("bulkRetryBtn").style.display = "inline-block";
        document.getElementById("bulkRetryBtn").textContent = `Probeer ${data.mislukt.length} mislukte landen opnieuw`;
    }
}
fetch("/api/scrapmonster-import-status").then(r => r.json()).then(data => {
    if (data.bezig || data.klaar > 0) {
        document.getElementById("bulkKnopWrap").style.display = "none";
        document.getElementById("bulkStatus").style.display = "block";
        pollBulk();
    }
});
</script>
    """
    pagina = render_simple_page("Alle landen importeren (ScrapMonster)", "zoeken", inhoud)
    return render_template_string(pagina, totaal=len(SCRAPMONSTER_LANDEN))

@app.route("/api/scrapmonster-import-status")
def scrapmonster_import_status():
    return jsonify(SCRAPMONSTER_BULK_STATUS)

OSM_IMPORT_HTML = '''
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>OpenStreetMap importeren</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #f1f5f9; padding: 40px; }
        .box { background: white; padding: 30px; border-radius: 12px; max-width: 480px; margin: 0 auto; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        h1 { font-size: 18px; margin-bottom: 8px; }
        p { font-size: 13px; color: #64748b; margin-bottom: 16px; }
        select, button { width: 100%; padding: 10px; margin-bottom: 12px; border: 1px solid #e2e8f0; border-radius: 6px; box-sizing: border-box; font-size: 14px; }
        button { background: #ea580c; color: white; border: none; cursor: pointer; font-weight: 600; }
        .bericht { padding: 10px; border-radius: 6px; margin-bottom: 12px; font-size: 14px; }
        .succes { background: #f0fdf4; color: #16a34a; }
        .fout { background: #fef2f2; color: #ef4444; }
    </style>
</head>
<body>
    <div class="box">
        <h1>Bedrijven importeren via OpenStreetMap</h1>
        <p>Haalt gratis, publiek beschikbare recyclingbedrijven (schroothandels, recyclingcentra, papierfabrieken, afvalbeheerbedrijven) op uit OpenStreetMap voor het gekozen land. Kan 10-60 seconden duren.</p>
        {% if bericht %}<div class="bericht {{ 'succes' if succes else 'fout' }}">{{ bericht }}</div>{% endif %}
        <form method="POST">
            <select name="land" required>
                {% for naam in landen %}<option value="{{ naam }}">{{ naam }}</option>{% endfor %}
            </select>
            <button type="submit">Importeren vanuit OpenStreetMap</button>
        </form>
        <a href="/importeer-osm-alle" style="display:block;text-align:center;margin-top:16px;font-size:13px;color:#ea580c;">→ Of importeer in één keer álle landen op de achtergrond</a>
        <a href="/importeer-scrapmonster" style="display:block;text-align:center;margin-top:8px;font-size:13px;color:#ea580c;">→ Of importeer schroothandels vanuit ScrapMonster.com</a>
    </div>
</body>
</html>
'''

OPSCHOON_HTML = '''
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>Dubbele bedrijven opschonen</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #f1f5f9; padding: 40px; }
        .box { background: white; padding: 30px; border-radius: 12px; max-width: 480px; margin: 0 auto; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        h1 { font-size: 18px; margin-bottom: 8px; }
        p { font-size: 13px; color: #64748b; margin-bottom: 16px; }
        label { display:block; font-size:13px; margin-bottom:8px; padding:10px; border:1px solid #e2e8f0; border-radius:6px; cursor:pointer; }
        button { width: 100%; padding: 10px; background: #ea580c; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 14px; margin-top:8px; }
        .bericht { padding: 10px; border-radius: 6px; margin-bottom: 12px; font-size: 14px; }
        .succes { background: #f0fdf4; color: #16a34a; }
    </style>
</head>
<body>
    <div class="box">
        <h1>Dubbele bedrijven/fabrieken opschonen</h1>
        <p>Verwijdert bedrijven en fabrieken die dubbel voorkomen. Bij dubbelen wordt de meest complete versie bewaard (met adres/telefoon indien beschikbaar).</p>
        {% if bericht %}<div class="bericht succes">{{ bericht }}</div>{% endif %}
        <form method="POST">
            <label><input type="radio" name="modus" value="normaal" checked> <b>Normaal</b> — zelfde naam + land + stad</label>
            <label><input type="radio" name="modus" value="streng"> <b>Streng</b> — alleen zelfde naam + land (negeert verschillen in stad-notatie, spaties, hoofdletters, leestekens)</label>
            <button type="submit">Nu opschonen</button>
        </form>
    </div>
</body>
</html>
'''

def normaliseer_naam(naam):
    naam = str(naam or "").strip().lower()
    naam = re.sub(r"[.,]", "", naam)
    naam = re.sub(r"\s+", " ", naam)
    return naam

def volledigheid_score(item):
    return sum(1 for veld in ("adres", "telefoon", "materialen", "volume", "certificeringen") if item.get(veld))

def dedupliceer_lijst(lijst, plaatsveld, modus="streng"):
    def sleutel(item):
        if modus == "streng":
            return (normaliseer_naam(item.get("naam","")), str(item.get("land","")).strip().lower())
        return (normaliseer_naam(item.get("naam","")), str(item.get("land","")).strip().lower(), str(item.get(plaatsveld,"")).strip().lower())

    groepen = {}
    volgorde = []
    for item in lijst:
        s = sleutel(item)
        if s not in groepen:
            groepen[s] = item
            volgorde.append(s)
        else:
            if volledigheid_score(item) > volledigheid_score(groepen[s]):
                groepen[s] = item
    return [groepen[s] for s in volgorde], len(lijst) - len(volgorde)

def opschonen_bedrijven_en_fabrieken(modus="streng"):
    """Dedupliceert ENF_BEDRIJVEN en PAPIERFABRIEKEN in-place en slaat ze op. Geeft (aantal_bedrijven_verwijderd, aantal_fabrieken_verwijderd) terug."""
    global ENF_BEDRIJVEN, PAPIERFABRIEKEN
    ENF_BEDRIJVEN, dubbel_bedrijven = dedupliceer_lijst(ENF_BEDRIJVEN, "regio", modus)
    with open(datapad("bedrijven.json"), "w", encoding="utf-8") as f:
        json.dump(ENF_BEDRIJVEN, f, ensure_ascii=False, indent=2)

    PAPIERFABRIEKEN, dubbel_fabrieken = dedupliceer_lijst(PAPIERFABRIEKEN, "stad", modus)
    with open(datapad("papierfabrieken.json"), "w", encoding="utf-8") as f:
        json.dump(PAPIERFABRIEKEN, f, ensure_ascii=False, indent=2)

    return dubbel_bedrijven, dubbel_fabrieken

HERLABEL_HTML = '''
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>Bedrijfstypes aanvullen</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #f1f5f9; padding: 40px; }
        .box { background: white; padding: 30px; border-radius: 12px; max-width: 480px; margin: 0 auto; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        h1 { font-size: 18px; margin-bottom: 8px; }
        p { font-size: 13px; color: #64748b; margin-bottom: 16px; }
        button { width: 100%; padding: 10px; background: #ea580c; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 14px; margin-bottom: 10px; }
        button.secundair { background: #fff; color: #ea580c; border: 1px solid #ea580c; }
        .bericht { padding: 10px; border-radius: 6px; margin-bottom: 12px; font-size: 14px; }
        .succes { background: #f0fdf4; color: #16a34a; }
    </style>
</head>
<body>
    <div class="box">
        <h1>Bedrijfstypes aanvullen</h1>
        <p>Kent een Bedrijfstype toe aan bedrijven die er nog geen hebben, maar <b>alleen</b> als er precies één duidelijk materiaal is (bij twijfel wordt niets gegokt).</p>
        {% if bericht %}<div class="bericht succes">{{ bericht }}</div>{% endif %}
        <form method="POST">
            <input type="hidden" name="actie" value="aanvullen">
            <button type="submit">Nu aanvullen</button>
        </form>
        <p style="margin-top:20px;">Heb je eerder de knop gebruikt en staat er nu te vaak "Papierfabriek"? Corrigeer dat hiermee:</p>
        <form method="POST">
            <input type="hidden" name="actie" value="corrigeer">
            <button type="submit" class="secundair">Corrigeer verkeerd gegokte "Papierfabriek"-labels</button>
        </form>
        {% if telling_lijst %}
        <hr style="margin:20px 0;border:none;border-top:1px solid #e2e8f0;">
        <p style="font-weight:600;color:#334155;margin-bottom:8px;">Huidige verdeling:</p>
        <table style="width:100%;font-size:13px;">
            {% for type_naam, aantal in telling_lijst %}
            <tr><td style="padding:3px 0;color:#334155;">{{ type_naam }}</td><td style="padding:3px 0;text-align:right;color:#ea580c;font-weight:600;">{{ aantal }}</td></tr>
            {% endfor %}
        </table>
        {% endif %}
    </div>
</body>
</html>
'''

def _bepaal_brontype_uit_materiaal(materialen):
    """Kent een type toe op basis van materialen. Materiaal zegt niets over 'kantoor' vs 'afvalbeheerbedrijf'
    (dat is een bedrijfsvorm, geen materiaalsoort) - die twee blijven dus alleen uit echte OSM-tags komen.
    Bij twijfel/meerdere materialen -> generiek 'Recyclingcentrum'."""
    delen = [m.strip().lower() for m in (materialen or "").split(",") if m.strip()]
    if len(delen) == 1 and delen[0] == "metal":
        return "Schroothandel"
    if len(delen) == 1 and delen[0] == "paper":
        return "Papierfabriek"
    return "Recyclingcentrum"  # alle overige gevallen (ook geen materialen bekend): eerlijke, brede standaard

@app.route("/herlabel-brontype", methods=["GET", "POST"])
def herlabel_brontype():
    bericht = None
    if request.method == "POST":
        actie = request.form.get("actie", "aanvullen")
        if actie == "corrigeer":
            # Maakt de allereerste, te agressieve versie ongedaan: haalt "Papierfabriek" weg
            # bij bedrijven die MEERDERE materialen hebben (dus duidelijk fout gegokt).
            # "Paper" als enige materiaal is inmiddels wél een geldige, bewuste "Papierfabriek"-gok - die laten we staan.
            aantal_gecorrigeerd = 0
            for b in ENF_BEDRIJVEN:
                if b.get("brontype") == "Papierfabriek":
                    delen = [m.strip().lower() for m in (b.get("materialen","") or "").split(",") if m.strip()]
                    if delen != ["paper"]:
                        nieuw = "Recyclingcentrum" if delen else ""
                        b["brontype"] = nieuw
                        aantal_gecorrigeerd += 1
            with open(datapad("bedrijven.json"), "w", encoding="utf-8") as f:
                json.dump(ENF_BEDRIJVEN, f, ensure_ascii=False, indent=2)
            bericht = f"Klaar! {aantal_gecorrigeerd} verkeerd gegokte 'Papierfabriek'-labels zijn gecorrigeerd."
        else:
            aantal_aangevuld = 0
            for b in ENF_BEDRIJVEN:
                if not b.get("brontype"):
                    nieuw_type = _bepaal_brontype_uit_materiaal(b.get("materialen", ""))
                    if nieuw_type:
                        b["brontype"] = nieuw_type
                        aantal_aangevuld += 1
            with open(datapad("bedrijven.json"), "w", encoding="utf-8") as f:
                json.dump(ENF_BEDRIJVEN, f, ensure_ascii=False, indent=2)
            bericht = f"Klaar! {aantal_aangevuld} bedrijven hebben nu een Bedrijfstype gekregen."

    telling = {}
    for b in ENF_BEDRIJVEN:
        t = b.get("brontype") or "(geen type)"
        telling[t] = telling.get(t, 0) + 1
    telling_lijst = sorted(telling.items(), key=lambda x: -x[1])

    return render_template_string(HERLABEL_HTML, bericht=bericht, telling_lijst=telling_lijst)

@app.route("/opschonen-dubbelen", methods=["GET", "POST"])
def opschonen_dubbelen():
    bericht = None
    if request.method == "POST":
        modus = request.form.get("modus", "normaal")
        dubbel_bedrijven, dubbel_fabrieken = opschonen_bedrijven_en_fabrieken(modus)
        bericht = f"Klaar! ({modus}) {dubbel_bedrijven} dubbele bedrijven en {dubbel_fabrieken} dubbele fabrieken verwijderd. {len(ENF_BEDRIJVEN)} bedrijven en {len(PAPIERFABRIEKEN)} fabrieken over."

    return render_template_string(OPSCHOON_HTML, bericht=bericht)

def osm_importeer_land(land_naam):
    """Importeert bedrijven voor 1 land vanuit OpenStreetMap. Geeft (aantal_nieuw, aantal_gevonden) terug, of gooit een Exception."""
    iso = OSM_LANDEN.get(land_naam)
    if not iso:
        raise ValueError(f"Onbekend land: {land_naam}")

    query = (
        '[out:json][timeout:120];'
        f'area["ISO3166-1"="{iso}"][admin_level=2]->.a;'
        '('
        'node["shop"="scrap_yard"](area.a);'
        'way["shop"="scrap_yard"](area.a);'
        'node["amenity"="recycling"]["recycling_type"="centre"](area.a);'
        'way["amenity"="recycling"]["recycling_type"="centre"](area.a);'
        'node["office"="recycling"](area.a);'
        'way["office"="recycling"](area.a);'
        'node["craft"="paper"](area.a);'
        'way["craft"="paper"](area.a);'
        'node["shop"="waste_disposal"](area.a);'
        'way["shop"="waste_disposal"](area.a);'
        'node["office"="waste_management"](area.a);'
        'way["office"="waste_management"](area.a);'
        ');'
        'out center tags;'
    )

    laatste_fout = None
    elementen = None
    for poging in range(3):
        try:
            resp = requests.get(
                "https://overpass-api.de/api/interpreter",
                params={"data": query},
                headers={"User-Agent": "RecycleFind/1.0"},
                timeout=150
            )
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}: {resp.text[:150] or '(lege reactie)'}")
            elementen = resp.json().get("elements", [])
            break
        except Exception as e:
            laatste_fout = e
            if poging < 2:
                time.sleep(15 * (poging + 1))  # oplopende wachttijd: 15s, 30s
    if elementen is None:
        raise laatste_fout

    def _bepaal_materialen(tags):
        if tags.get("craft") == "paper":
            return "Paper"
        if tags.get("shop") == "scrap_yard":
            return "Metal"
        if tags.get("recycling:glass") == "yes":
            return "Glass"
        if tags.get("recycling:plastic") == "yes" or tags.get("recycling:plastic_packaging") == "yes":
            return "Plastic"
        return ""

    def _bepaal_brontype(tags):
        if tags.get("craft") == "paper":
            return "Papierfabriek"
        if tags.get("shop") == "scrap_yard":
            return "Schroothandel"
        if tags.get("amenity") == "recycling":
            return "Recyclingcentrum"
        if tags.get("office") == "recycling":
            return "Recycling-kantoor"
        if tags.get("office") == "waste_management" or tags.get("shop") == "waste_disposal":
            return "Afvalbeheer"
        return "Overig"

    bestaande = {(b["naam"].strip().lower(), b["land"].strip().lower(), b.get("regio","").strip().lower()) for b in ENF_BEDRIJVEN}
    aantal_nieuw = 0
    for el in elementen:
        tags = el.get("tags", {})
        naam = tags.get("name", "").strip()
        if not naam:
            continue
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if not lat or not lon:
            continue
        stad = tags.get("addr:city", "")
        sleutel = (naam.strip().lower(), land_naam.strip().lower(), stad.strip().lower())
        if sleutel in bestaande:
            continue
        bestaande.add(sleutel)
        ENF_BEDRIJVEN.append({
            "naam": naam, "land": land_naam, "regio": stad,
            "materialen": _bepaal_materialen(tags),
            "klanttype": "", "volume": "", "url": "",
            "lat": lat, "lon": lon,
            "adres": tags.get("addr:street", ""), "telefoon": tags.get("phone", tags.get("contact:phone", "")),
            "bedrijf_id": TENANT_ID,
            "brontype": _bepaal_brontype(tags),
        })
        aantal_nieuw += 1

    with open(datapad("bedrijven.json"), "w", encoding="utf-8") as f:
        json.dump(ENF_BEDRIJVEN, f, ensure_ascii=False, indent=2)

    return aantal_nieuw, len(elementen)

@app.route("/importeer-osm", methods=["GET", "POST"])
def importeer_osm():
    bericht = None
    succes = False
    if request.method == "POST":
        land_naam = request.form.get("land", "")
        try:
            aantal_nieuw, aantal_gevonden = osm_importeer_land(land_naam)
            dubbel, _ = opschonen_bedrijven_en_fabrieken("streng")
            bericht = f"Gelukt! {aantal_nieuw} nieuwe bedrijven toegevoegd uit OpenStreetMap voor {land_naam} ({aantal_gevonden} gevonden). {dubbel} dubbelingen automatisch opgeschoond."
            succes = True
        except Exception as e:
            bericht = f"Er ging iets mis: {e}"

    return render_template_string(OSM_IMPORT_HTML, bericht=bericht, succes=succes, landen=sorted(OSM_LANDEN.keys()))

OSM_BULK_STATUS = {
    "bezig": False, "huidig_land": "", "klaar": 0, "totaal": len(OSM_LANDEN),
    "nieuw_totaal": 0, "log": [], "mislukt": [],
}
OSM_BULK_LOCK = threading.Lock()

def _osm_bulk_worker(gebruikersnaam, landen_lijst=None):
    landen_lijst = landen_lijst or sorted(OSM_LANDEN.keys())
    with OSM_BULK_LOCK:
        OSM_BULK_STATUS["bezig"] = True
        OSM_BULK_STATUS["klaar"] = 0
        OSM_BULK_STATUS["nieuw_totaal"] = 0
        OSM_BULK_STATUS["log"] = []
        OSM_BULK_STATUS["mislukt"] = []
        OSM_BULK_STATUS["totaal"] = len(landen_lijst)

    for land_naam in landen_lijst:
        OSM_BULK_STATUS["huidig_land"] = land_naam
        try:
            aantal_nieuw, aantal_gevonden = osm_importeer_land(land_naam)
            regel = f"✓ {land_naam}: {aantal_nieuw} nieuw ({aantal_gevonden} gevonden)"
            OSM_BULK_STATUS["nieuw_totaal"] += aantal_nieuw
        except Exception as e:
            regel = f"✗ {land_naam}: fout ({e})"
            OSM_BULK_STATUS["mislukt"].append(land_naam)
        OSM_BULK_STATUS["log"].append(regel)
        OSM_BULK_STATUS["klaar"] += 1
        time.sleep(8)  # respecteer de gratis Overpass-dienst tussen landen

    OSM_BULK_STATUS["bezig"] = False
    OSM_BULK_STATUS["huidig_land"] = ""

    OSM_BULK_STATUS["huidig_land"] = "Opschonen van dubbelingen..."
    dubbel_opgeschoond, _ = opschonen_bedrijven_en_fabrieken("streng")
    OSM_BULK_STATUS["huidig_land"] = ""

    if gebruikersnaam:
        alle_meldingen = laad_meldingen()
        mislukt_tekst = f" ({len(OSM_BULK_STATUS['mislukt'])} landen mislukt, kun je opnieuw proberen)" if OSM_BULK_STATUS["mislukt"] else ""
        alle_meldingen.append({
            "id": str(uuid.uuid4()),
            "tekst": f"OpenStreetMap-import klaar! {OSM_BULK_STATUS['nieuw_totaal']} nieuwe bedrijven toegevoegd over {OSM_BULK_STATUS['totaal']} landen. {dubbel_opgeschoond} dubbelingen automatisch opgeschoond.{mislukt_tekst}",
            "bedrijf": "",
            "van": "Systeem",
            "voor_gebruiker": gebruikersnaam,
            "voor_team": "",
            "gelezen": False,
            "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
        })
        bewaar_meldingen(alle_meldingen)

@app.route("/importeer-osm-alle", methods=["GET", "POST"])
def importeer_osm_alle():
    if request.method == "POST":
        if not OSM_BULK_STATUS["bezig"]:
            gebruikersnaam = session.get("gebruikersnaam", "")
            alleen_mislukte = request.form.get("alleen_mislukte") == "1"
            landen_lijst = list(OSM_BULK_STATUS["mislukt"]) if alleen_mislukte and OSM_BULK_STATUS["mislukt"] else None
            thread = threading.Thread(target=_osm_bulk_worker, args=(gebruikersnaam, landen_lijst), daemon=True)
            thread.start()
        return redirect(url_for("importeer_osm_alle"))

    inhoud = """
<style>
.bulk-log { max-height:300px; overflow-y:auto; background:var(--gray-50); border-radius:8px; padding:12px; font-size:0.8rem; font-family:monospace; margin-top:16px; }
.bulk-log div { padding:2px 0; }
.bulk-balk-track { background:var(--gray-100); border-radius:6px; height:14px; overflow:hidden; margin-top:12px; }
.bulk-balk-fill { background:linear-gradient(90deg,var(--brand-500),var(--brand-700)); height:100%; transition:width 0.3s; }
</style>
<div class="page-title">Alle landen importeren (OpenStreetMap)</div>
<div class="info-kaart" style="max-width:600px;">
    <p style="color:var(--gray-500);font-size:0.85rem;margin-bottom:16px;">
        Haalt automatisch, land voor land, gratis recyclingbedrijven op uit OpenStreetMap voor alle {{ totaal }} ondersteunde landen.
        Dit duurt ongeveer {{ (totaal * 15 / 60)|round(0, 'ceil')|int }}-{{ (totaal * 30 / 60)|round(0, 'ceil')|int }} minuten. Je kunt deze pagina gewoon open laten staan of sluiten — het draait op de achtergrond door.
    </p>
    <div id="bulkKnopWrap">
        <button onclick="startBulk()" id="bulkStartBtn" style="padding:10px 20px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-weight:600;cursor:pointer;">Start import van alle landen</button>
    </div>
    <div id="bulkStatus" style="display:none;margin-top:16px;">
        <div style="font-size:0.85rem;color:var(--gray-600);">Bezig met: <b id="bulkHuidig">—</b></div>
        <div class="bulk-balk-track"><div class="bulk-balk-fill" id="bulkBalk" style="width:0%"></div></div>
        <div style="font-size:0.8rem;color:var(--gray-400);margin-top:6px;"><span id="bulkKlaar">0</span> / <span id="bulkTotaal">{{ totaal }}</span> landen · <span id="bulkNieuw">0</span> nieuwe bedrijven tot nu toe</div>
        <div class="bulk-log" id="bulkLog"></div>
        <button onclick="startRetry()" id="bulkRetryBtn" style="display:none;margin-top:12px;padding:8px 16px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-weight:600;cursor:pointer;">Probeer mislukte landen opnieuw</button>
    </div>
</div>
<script>
function startBulk() {
    fetch("/importeer-osm-alle", {method:"POST"}).then(() => pollBulk());
    document.getElementById("bulkKnopWrap").style.display = "none";
    document.getElementById("bulkStatus").style.display = "block";
}
function startRetry() {
    fetch("/importeer-osm-alle", {method:"POST", headers:{"Content-Type":"application/x-www-form-urlencoded"}, body:"alleen_mislukte=1"}).then(() => pollBulk());
    document.getElementById("bulkRetryBtn").style.display = "none";
}
async function pollBulk() {
    const res = await fetch("/api/osm-import-status");
    const data = await res.json();
    document.getElementById("bulkHuidig").textContent = data.huidig_land || (data.bezig ? "..." : "Klaar!");
    document.getElementById("bulkBalk").style.width = (data.klaar / data.totaal * 100) + "%";
    document.getElementById("bulkKlaar").textContent = data.klaar;
    document.getElementById("bulkTotaal").textContent = data.totaal;
    document.getElementById("bulkNieuw").textContent = data.nieuw_totaal;
    document.getElementById("bulkLog").innerHTML = data.log.slice().reverse().map(r => `<div>${r}</div>`).join("");
    if (data.bezig) {
        document.getElementById("bulkRetryBtn").style.display = "none";
        setTimeout(pollBulk, 3000);
    } else if (data.mislukt && data.mislukt.length > 0) {
        document.getElementById("bulkRetryBtn").style.display = "inline-block";
        document.getElementById("bulkRetryBtn").textContent = `Probeer ${data.mislukt.length} mislukte landen opnieuw`;
    }
}
// Als er al een import bezig is (bv. na herladen van de pagina), meteen tonen
fetch("/api/osm-import-status").then(r => r.json()).then(data => {
    if (data.bezig || data.klaar > 0) {
        document.getElementById("bulkKnopWrap").style.display = "none";
        document.getElementById("bulkStatus").style.display = "block";
        pollBulk();
    }
});
</script>
    """
    pagina = render_simple_page("Alle landen importeren", "zoeken", inhoud)
    return render_template_string(pagina, totaal=len(OSM_LANDEN))

@app.route("/api/osm-import-status")
def osm_import_status():
    return jsonify(OSM_BULK_STATUS)

@app.route("/importeer", methods=["GET", "POST"])
def importeer_bedrijven():
    bericht = None
    succes = False
    if request.method == "POST":
        bestand = request.files.get("bestand")
        if not bestand:
            bericht = "Geen bestand geselecteerd."
        else:
            try:
                import pandas as pd
                df = pd.read_excel(bestand)
                df.columns = [str(c).strip() for c in df.columns]

                aantal_bedrijven = 0
                aantal_fabrieken = 0
                aantal_dubbel = 0

                def maak_sleutel(naam_, land_, plaats_):
                    return (naam_.strip().lower(), land_.strip().lower(), plaats_.strip().lower())

                bestaande_bedrijven = {maak_sleutel(b["naam"], b["land"], b["regio"]) for b in ENF_BEDRIJVEN}
                bestaande_fabrieken = {maak_sleutel(f["naam"], f["land"], f["stad"]) for f in PAPIERFABRIEKEN}

                for _, rij in df.iterrows():
                    naam = str(rij.get("Naam", "")).strip()
                    if not naam or naam.lower() == "nan":
                        continue
                    type_ = str(rij.get("Type", "")).strip().lower()
                    land = str(rij.get("Land", "")).strip()
                    stad = str(rij.get("Stad", "")).strip()
                    materialen = str(rij.get("Materialen", "")).strip()
                    if materialen.lower() == "nan":
                        materialen = ""
                    klanttype = str(rij.get("Klanttype", "")).strip()
                    if klanttype.lower() == "nan":
                        klanttype = ""
                    adres = str(rij.get("Adres", "")).strip()
                    if adres.lower() == "nan":
                        adres = ""
                    telefoon = str(rij.get("Telefoonnummer", "")).strip()
                    if telefoon.lower() == "nan":
                        telefoon = ""
                    certificeringen = str(rij.get("Certificeringen", "")).strip()
                    if certificeringen.lower() == "nan":
                        certificeringen = ""
                    volume_raw = rij.get("Volume", "")
                    volume = "" if pd.isna(volume_raw) else str(volume_raw).strip()

                    lat_raw = rij.get("Lat", None)
                    lon_raw = rij.get("Lon", None)
                    if lat_raw is not None and lon_raw is not None and not pd.isna(lat_raw) and not pd.isna(lon_raw):
                        lat = float(lat_raw)
                        lon = float(lon_raw)
                    else:
                        geo = geocode_adres(stad, land)
                        lat = geo["lat"] if geo else None
                        lon = geo["lon"] if geo else None

                    sleutel = maak_sleutel(naam, land, stad)

                    if type_ == "fabriek":
                        if sleutel in bestaande_fabrieken:
                            aantal_dubbel += 1
                            continue
                        bestaande_fabrieken.add(sleutel)
                        PAPIERFABRIEKEN.append({
                            "naam": naam, "land": land, "stad": stad,
                            "materialen": materialen, "lat": lat, "lon": lon
                        })
                        aantal_fabrieken += 1
                    else:
                        if sleutel in bestaande_bedrijven:
                            aantal_dubbel += 1
                            continue
                        bestaande_bedrijven.add(sleutel)
                        ENF_BEDRIJVEN.append({
                            "naam": naam, "land": land, "regio": stad,
                            "materialen": materialen, "klanttype": klanttype,
                            "volume": volume, "url": "", "lat": lat, "lon": lon,
                            "adres": adres, "telefoon": telefoon, "certificeringen": certificeringen,
                            "bedrijf_id": TENANT_ID
                        })
                        aantal_bedrijven += 1

                with open(datapad("bedrijven.json"), "w", encoding="utf-8") as f:
                    json.dump(ENF_BEDRIJVEN, f, ensure_ascii=False, indent=2)
                with open(datapad("papierfabrieken.json"), "w", encoding="utf-8") as f:
                    json.dump(PAPIERFABRIEKEN, f, ensure_ascii=False, indent=2)

                bericht = f"Gelukt! {aantal_bedrijven} bedrijven/klanten en {aantal_fabrieken} fabrieken toegevoegd."
                if aantal_dubbel:
                    bericht += f" {aantal_dubbel} dubbele(n) overgeslagen (kwamen al voor)."
                succes = True
            except Exception as e:
                bericht = f"Er ging iets mis: {e}"

    return render_template_string(IMPORT_HTML, bericht=bericht, succes=succes)
@app.route("/forwarder-upload", methods=["GET", "POST"])
def forwarder_upload():
    bericht = None
    succes = False
    if request.method == "POST":
        forwarder = request.form.get("forwarder", "").strip()
        wachtwoord = request.form.get("wachtwoord", "")
        bestand = request.files.get("bestand")

        wachtwoorden = laad_forwarder_wachtwoorden()
        if forwarder not in wachtwoorden or wachtwoorden[forwarder] != wachtwoord:
            bericht = "Onjuiste forwarder-naam of wachtwoord."
        elif not bestand:
            bericht = "Geen bestand geselecteerd."
        else:
            try:
                import pandas as pd
                df = pd.read_excel(bestand, header=1)
                df = df.dropna(how="all", axis=1)
                df = df.dropna(how="all", axis=0)
                kolommen = list(df.columns)
                stad_kolom = kolommen[0]

                records = []
                for _, rij in df.iterrows():
                    stad = str(rij[stad_kolom]).strip()
                    if not stad or stad.lower() == "nan":
                        continue
                    tarieven = {}
                    for kolom in kolommen[1:]:
                        waarde = rij[kolom]
                        if pd.isna(waarde):
                            continue
                        tarieven[str(kolom).strip()] = str(waarde).strip()
                    records.append({"stad": stad, "tarieven": tarieven})

                global TRANSPORT_DATA
                TRANSPORT_DATA = laad_transport_data()
                TRANSPORT_DATA[forwarder] = records
                with open(datapad("transport_prijzen.json"), "w", encoding="utf-8") as f:
                    json.dump(TRANSPORT_DATA, f, ensure_ascii=False, indent=2)

                bericht = f"Gelukt! {len(records)} steden geimporteerd voor {forwarder}."
                succes = True
            except Exception as e:
                bericht = f"Er ging iets mis: {e}"

    return render_template_string(UPLOAD_HTML, bericht=bericht, succes=succes)

LANDEN = sorted(set(b["land"] for b in ENF_BEDRIJVEN))

REGIO_PER_LAND = {}
for b in ENF_BEDRIJVEN:
    land = b["land"]
    regio = b["regio"]
    if land not in REGIO_PER_LAND:
        REGIO_PER_LAND[land] = set()
    REGIO_PER_LAND[land].add(regio)
REGIO_PER_LAND = {l: sorted(r) for l, r in REGIO_PER_LAND.items()}

def haal_bedrijf_details(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        tekst = soup.get_text()
        details = {}
        website = soup.find("a", href=lambda h: h and h.startswith("http") and "enfpaper" not in h)
        if website:
            details["website"] = website["href"]
        for tag in soup.find_all(["td", "div", "span"]):
            t = tag.get_text(strip=True)
            if "+" in t and any(c.isdigit() for c in t) and len(t) < 30:
                details["telefoon"] = t
                break
        lines = [l.strip() for l in tekst.split("\n") if l.strip()]
        for i, line in enumerate(lines):
            if "No. Staff" in line and i+1 < len(lines):
                details["medewerkers"] = lines[i+1]
            if "Type of Recycled" in line and i+1 < len(lines):
                details["materialen_detail"] = lines[i+1]

        adres_tag = soup.find("span", {"itemprop": "streetAddress"})
        stad_tag = soup.find("span", {"itemprop": "addressLocality"})
        if adres_tag:
            details["adres"] = adres_tag.get_text(strip=True)
        if stad_tag:
            details["stad"] = stad_tag.get_text(strip=True)

        if details.get("adres") and details.get("stad"):
            geo = geocode_adres(details["adres"], details["stad"])
            if geo:
                details["lat_precies"] = geo["lat"]
                details["lon_precies"] = geo["lon"]

        return details
    except:
        return {}


PAGINA_HOOFD = """<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>__TITEL__ — RecycleFind</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        /* ============================================
           DESIGN SYSTEM — RECYCLEFIND
           ============================================ */

        /* TOKENS */
        :root {
            /* Colors */
            --brand-50:  #fff7ed;
            --brand-100: #ffedd5;
            --brand-200: #fed7aa;
            --brand-300: #fdba74;
            --brand-400: #fb923c;
            --brand-500: #f97316;
            --brand-600: #ea580c;
            --brand-700: #c2410c;
            --brand-800: #9a3412;
            --brand-900: #7c2d12;

            --gray-50:  #f8fafc;
            --gray-100: #f1f5f9;
            --gray-200: #e2e8f0;
            --gray-300: #cbd5e1;
            --gray-400: #94a3b8;
            --gray-500: #64748b;
            --gray-600: #475569;
            --gray-700: #334155;
            --gray-800: #1e293b;
            --gray-900: #0f172a;

            --green-50:  #f0fdf4;
            --green-500: #22c55e;
            --green-600: #16a34a;

            --orange-50:  #fff7ed;
            --orange-500: #f97316;
            --orange-600: #ea580c;

            --red-50:  #fef2f2;
            --red-500: #ef4444;

            /* Typography */
            --font: "Inter", -apple-system, sans-serif;
            --text-xs:   0.7rem;
            --text-sm:   0.8rem;
            --text-base: 0.9rem;
            --text-lg:   1.05rem;
            --text-xl:   1.2rem;
            --text-2xl:  1.5rem;
            --text-3xl:  2rem;
            --text-4xl:  2.8rem;
            --text-5xl:  3.5rem;

            /* Spacing */
            --space-1: 4px;
            --space-2: 8px;
            --space-3: 12px;
            --space-4: 16px;
            --space-5: 20px;
            --space-6: 24px;
            --space-8: 32px;
            --space-10: 40px;
            --space-12: 48px;
            --space-16: 64px;

            /* Radius */
            --radius-sm: 6px;
            --radius-md: 10px;
            --radius-lg: 14px;
            --radius-xl: 20px;
            --radius-full: 9999px;

            /* Shadows */
            --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
            --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
            --shadow-lg: 0 8px 24px rgba(0,0,0,0.1);
            --shadow-xl: 0 16px 48px rgba(0,0,0,0.12);
            --shadow-brand: 0 4px 14px rgba(37,99,235,0.25);

            /* Transitions */
            --transition: all 0.2s cubic-bezier(0.4,0,0.2,1);
        }

        /* RESET */
        *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
        html { scroll-behavior: smooth; }
        body { font-family: var(--font); background: var(--gray-50); color: var(--gray-800); min-height: 100vh; -webkit-font-smoothing: antialiased; }

        /* ============================================
           NAVBAR
           ============================================ */
        .navbar {
            position: sticky;
            top: 0;
            z-index: 100;
            background: rgba(255,255,255,0.9);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--gray-200);
            height: 56px;
            display: flex;
            align-items: center;
            padding: 0 var(--space-8);
            gap: var(--space-8);
        }
        .navbar-logo {
            font-size: var(--text-lg);
            font-weight: 800;
            color: var(--gray-900);
            letter-spacing: -0.5px;
            text-decoration: none;
            flex-shrink: 0;
        }
        .navbar-logo em { color: var(--brand-600); font-style: normal; }
        .navbar-divider { width: 1px; height: 20px; background: var(--gray-200); }
        .navbar-stat { font-size: var(--text-xs); color: var(--gray-400); white-space: nowrap; }
        .navbar-stat strong { color: var(--brand-600); font-weight: 600; }
        .navbar-right { margin-left: auto; display: flex; align-items: center; gap: var(--space-3); }
        .btn-nav {
            font-size: var(--text-sm);
            font-weight: 500;
            padding: 6px 14px;
            border-radius: var(--radius-sm);
            border: none;
            cursor: pointer;
            font-family: var(--font);
            transition: var(--transition);
            text-decoration: none;
        }
        .btn-nav-ghost { background: transparent; color: var(--gray-600); }
        .btn-nav-ghost:hover { background: var(--gray-100); color: var(--gray-900); }
        .btn-nav-primary { background: var(--brand-600); color: #fff; }
        .btn-nav-primary:hover { background: var(--brand-700); box-shadow: var(--shadow-brand); }

        /* ============================================
           HERO
           ============================================ */
        .search-bar-section {
            background: var(--gray-50);
            padding: var(--space-8) var(--space-10);
            border-bottom: 1px solid var(--gray-200);
        }
        .hero-content { max-width: 860px; margin: 0 auto; }

        /* ============================================
           SEARCH
           ============================================ */
        .search-container {
            background: #fff;
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-xl);
            padding: var(--space-5);
            max-width: 860px;
            margin: 0 auto;
            box-shadow: var(--shadow-sm);
        }
        .search-row {
            display: flex;
            gap: var(--space-2);
            flex-wrap: wrap;
            justify-content: center;
        }
        .search-input, .search-select {
            background: #fff;
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-sm);
            padding: 9px 13px;
            font-size: var(--text-sm);
            font-family: var(--font);
            color: var(--gray-800);
            outline: none;
            transition: var(--transition);
        }
        .search-input { width: 200px; }
        .search-input::placeholder { color: var(--gray-400); }
        .search-select { width: 155px; cursor: pointer; }
        .search-input:focus, .search-select:focus {
            border-color: var(--brand-400);
            box-shadow: 0 0 0 3px rgba(59,130,246,0.15);
        }
        .btn-search {
            background: var(--brand-500);
            color: #fff;
            border: none;
            border-radius: var(--radius-sm);
            padding: 9px 20px;
            font-size: var(--text-sm);
            font-weight: 700;
            font-family: var(--font);
            cursor: pointer;
            transition: var(--transition);
            white-space: nowrap;
        }
        .btn-search:hover { background: var(--brand-400); transform: translateY(-1px); box-shadow: var(--shadow-brand); }

        /* ============================================
           STATS BAR
           ============================================ */
        .stats-bar {
            background: #fff;
            border-bottom: 1px solid var(--gray-200);
            padding: var(--space-4) var(--space-10);
            display: flex;
            justify-content: center;
            gap: var(--space-12);
        }
        .stat { text-align: center; }
        .stat-num { font-size: var(--text-2xl); font-weight: 800; color: var(--brand-600); letter-spacing: -0.5px; }
        .stat-label { font-size: var(--text-xs); color: var(--gray-400); text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; margin-top: 2px; }

        /* ============================================
           MAIN LAYOUT
           ============================================ */
        .main {
            max-width: 1440px;
            margin: var(--space-6) auto;
            padding: 0 var(--space-6);
            display: flex;
            gap: var(--space-5);
            align-items: flex-start;
        }

        /* ============================================
           FILTERS SIDEBAR
           ============================================ */
        .filters-panel {
            width: 220px;
            flex-shrink: 0;
            background: #fff;
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-lg);
            padding: var(--space-5);
            box-shadow: var(--shadow-sm);
        }
        .filters-title {
            font-size: var(--text-xs);
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: var(--gray-400);
            margin-bottom: var(--space-4);
        }
        .filter-group { margin-bottom: var(--space-4); }
        .filter-label {
            font-size: var(--text-xs);
            font-weight: 600;
            color: var(--gray-600);
            margin-bottom: var(--space-2);
            display: block;
        }
        .filter-select {
            width: 100%;
            background: var(--gray-50);
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-sm);
            padding: 7px 10px;
            font-size: var(--text-sm);
            font-family: var(--font);
            color: var(--gray-700);
            outline: none;
            cursor: pointer;
            transition: var(--transition);
        }
        .filter-select:focus { border-color: var(--brand-400); background: #fff; }
        .filter-divider { border: none; border-top: 1px solid var(--gray-100); margin: var(--space-4) 0; }
        .btn-apply {
            width: 100%;
            background: var(--brand-600);
            color: #fff;
            border: none;
            border-radius: var(--radius-sm);
            padding: 9px;
            font-size: var(--text-sm);
            font-weight: 600;
            font-family: var(--font);
            cursor: pointer;
            transition: var(--transition);
        }
        .btn-apply:hover { background: var(--brand-700); }
        .btn-reset {
            width: 100%;
            background: transparent;
            color: var(--gray-400);
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-sm);
            padding: 8px;
            font-size: var(--text-xs);
            font-family: var(--font);
            cursor: pointer;
            margin-top: var(--space-2);
            transition: var(--transition);
        }
        .btn-reset:hover { color: var(--gray-600); border-color: var(--gray-300); }

        /* ============================================
           RESULTS PANEL
           ============================================ */
        .results-panel { width: 340px; flex-shrink: 0; }
        .results-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: var(--space-3);
            padding: 0 2px;
        }
        .results-count { font-size: var(--text-sm); color: var(--gray-400); }
        .results-count strong { color: var(--brand-600); font-weight: 700; }
        .results-list {
            max-height: 680px;
            overflow-y: auto;
            scrollbar-width: thin;
            scrollbar-color: var(--gray-200) transparent;
        }

        /* ============================================
           COMPANY CARD
           ============================================ */
        .company-card {
            background: #fff;
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-md);
            padding: var(--space-4);
            margin-bottom: var(--space-2);
            cursor: pointer;
            transition: var(--transition);
        }
        .company-card:hover {
            border-color: var(--brand-300);
            box-shadow: var(--shadow-md);
            transform: translateY(-1px);
        }
        .company-card-top { display: flex; align-items: flex-start; gap: var(--space-3); margin-bottom: var(--space-2); }
        .company-index {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 22px;
            height: 22px;
            min-width: 22px;
            background: var(--brand-600);
            color: #fff;
            border-radius: 5px;
            font-size: 0.65rem;
            font-weight: 700;
            margin-top: 1px;
        }
        .company-name { font-size: var(--text-base); font-weight: 600; color: var(--gray-800); line-height: 1.3; }
        .company-meta { font-size: var(--text-xs); color: var(--gray-400); margin-bottom: var(--space-2); padding-left: 34px; display: flex; align-items: center; gap: 4px; }
        .company-tags { display: flex; flex-wrap: wrap; gap: 4px; padding-left: 34px; }
        .tag {
            display: inline-flex;
            align-items: center;
            padding: 2px 7px;
            border-radius: 4px;
            font-size: 0.65rem;
            font-weight: 600;
            letter-spacing: 0.2px;
        }
        .tag-blue { background: var(--brand-50); color: var(--brand-700); border: 1px solid var(--brand-100); }
        .tag-green { background: var(--green-50); color: var(--green-600); border: 1px solid #bbf7d0; }
        .tag-orange { background: var(--orange-50); color: var(--orange-600); border: 1px solid #fed7aa; }
        .star-btn { font-size: 1.1em; color: var(--gray-300); cursor: pointer; padding: 0 2px; }
        .star-btn:hover { color: var(--brand-400); }
        .star-btn.opgeslagen { color: var(--brand-500); }

        /* ============================================
           MAP
           ============================================ */
        .map-panel { flex: 1; min-width: 0; }
        #kaart {
            height: 720px;
            border-radius: var(--radius-lg);
            border: 1px solid var(--gray-200);
            box-shadow: var(--shadow-sm);
        }

        /* ============================================
           DETAIL DRAWER
           ============================================ */
        .overlay {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(15,23,42,0.35);
            z-index: 9999;
            backdrop-filter: blur(3px);
        }
        .drawer {
            position: fixed;
            top: 0;
            right: -500px;
            width: 460px;
            height: 100vh;
            background: #fff;
            border-left: 1px solid var(--gray-200);
            box-shadow: var(--shadow-xl);
            z-index: 10000;
            overflow-y: auto;
            transition: right 0.3s cubic-bezier(0.4,0,0.2,1);
        }
        .drawer.open { right: 0; }
        .drawer-header {
            padding: var(--space-6) var(--space-6) var(--space-4);
            border-bottom: 1px solid var(--gray-100);
            position: sticky;
            top: 0;
            background: #fff;
            z-index: 1;
        }
        .drawer-close {
            position: absolute;
            top: var(--space-4);
            right: var(--space-4);
            width: 28px;
            height: 28px;
            background: var(--gray-100);
            border: none;
            border-radius: var(--radius-sm);
            color: var(--gray-500);
            cursor: pointer;
            font-size: 0.9em;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: var(--transition);
        }
        .drawer-close:hover { background: var(--gray-200); color: var(--gray-800); }
        .drawer-company-name { font-size: var(--text-xl); font-weight: 700; color: var(--gray-900); margin-bottom: 4px; padding-right: 36px; }
        .drawer-company-loc { font-size: var(--text-sm); color: var(--gray-400); }
        .drawer-body { padding: var(--space-5) var(--space-6); }
        .drawer-section { margin-bottom: var(--space-5); }
        .drawer-section-title {
            font-size: var(--text-xs);
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: var(--gray-400);
            margin-bottom: var(--space-3);
        }
        .drawer-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: var(--space-2) 0;
            border-bottom: 1px solid var(--gray-50);
        }
        .drawer-row:last-child { border-bottom: none; }
        .drawer-row-label { font-size: var(--text-sm); color: var(--gray-400); font-weight: 500; }
        .drawer-row-value { font-size: var(--text-sm); color: var(--gray-700); font-weight: 500; text-align: right; }
        .drawer-divider { border: none; border-top: 1px solid var(--gray-100); margin: var(--space-4) 0; }
        .btn-website {
            display: inline-flex;
            align-items: center;
            gap: var(--space-2);
            background: var(--brand-600);
            color: #fff;
            padding: 8px 16px;
            border-radius: var(--radius-sm);
            text-decoration: none;
            font-size: var(--text-sm);
            font-weight: 600;
            transition: var(--transition);
            margin-right: var(--space-2);
        }
        .btn-website:hover { background: var(--brand-700); box-shadow: var(--shadow-brand); }
        .btn-enf {
            display: inline-flex;
            align-items: center;
            gap: var(--space-2);
            background: var(--gray-100);
            color: var(--gray-600);
            padding: 8px 16px;
            border-radius: var(--radius-sm);
            text-decoration: none;
            font-size: var(--text-sm);
            font-weight: 600;
            transition: var(--transition);
        }
        .btn-enf:hover { background: var(--gray-200); color: var(--gray-800); }
        .score-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 36px;
            height: 36px;
            border-radius: var(--radius-sm);
            font-size: var(--text-sm);
            font-weight: 800;
        }
        .score-high { background: var(--green-50); color: var(--green-600); }
        .score-mid { background: var(--orange-50); color: var(--orange-600); }

        /* ============================================
           WELCOME STATE
           ============================================ */
        .welcome-state {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: var(--space-16);
            text-align: center;
        }
        .welcome-icon { font-size: 3em; margin-bottom: var(--space-4); }
        .welcome-title { font-size: var(--text-2xl); font-weight: 700; color: var(--gray-800); margin-bottom: var(--space-2); }
        .welcome-sub { font-size: var(--text-base); color: var(--gray-400); max-width: 400px; }

        /* ============================================
           SIDEBAR
           ============================================ */
        body { display: flex; }
        .sidebar {
            width: 220px;
            min-width: 220px;
            height: 100vh;
            position: sticky;
            top: 0;
            background: #fff;
            border-right: 1px solid var(--gray-200);
            display: flex;
            flex-direction: column;
            padding: var(--space-5) 0;
            flex-shrink: 0;
        }
        .sidebar-logo {
            font-size: var(--text-lg);
            font-weight: 800;
            color: var(--gray-900);
            letter-spacing: -0.5px;
            text-decoration: none;
            padding: 0 var(--space-5);
            margin-bottom: var(--space-6);
            display: block;
        }
        .sidebar-logo em { color: var(--brand-600); font-style: normal; }
        .sidebar-nav { display: flex; flex-direction: column; gap: 2px; padding: 0 var(--space-3); }
        .sidebar-link {
            display: flex;
            align-items: center;
            gap: var(--space-3);
            padding: 9px var(--space-3);
            border-radius: var(--radius-sm);
            color: var(--gray-600);
            text-decoration: none;
            font-size: var(--text-sm);
            font-weight: 500;
            transition: var(--transition);
        }
        .sidebar-link:hover { background: var(--gray-50); color: var(--gray-900); }
        .sidebar-link.active { background: var(--brand-50); color: var(--brand-700); font-weight: 700; }
        .sidebar-link .icoon { font-size: 1.05em; width: 20px; text-align: center; }
        .content-wrapper { flex: 1; min-width: 0; }
        .mobiel-menu-knop { display: none; }
        .mobiel-overlay { display: none; }
        @media (max-width: 900px) {
            .sidebar {
                position: fixed;
                left: -240px;
                top: 0;
                z-index: 2000;
                transition: left 0.25s ease;
                box-shadow: 0 0 24px rgba(0,0,0,0.18);
            }
            .sidebar.open { left: 0; }
            .mobiel-menu-knop {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 38px; height: 38px;
                border: 1px solid var(--gray-200); background: #fff;
                border-radius: 8px; cursor: pointer; font-size: 18px;
                position: fixed; top: 12px; left: 12px; z-index: 1500;
                box-shadow: var(--shadow-sm);
            }
            .mobiel-overlay.open {
                display: block;
                position: fixed; inset: 0; background: rgba(15,23,42,0.35); z-index: 1900;
            }
            .content-wrapper { padding-top: 52px; }
            .page-content { padding: var(--space-4) !important; }
            .main { flex-direction: column; padding: 0 var(--space-3); }
            .filters-panel { width: 100%; box-sizing: border-box; }
            .results-panel { width: 100%; }
            #kaart { height: 320px; }
            .map-panel { width: 100%; }
            .drawer { width: 100%; right: -100%; }
            .navbar { padding: 0 var(--space-4) 0 56px; flex-wrap: wrap; height: auto; min-height: 56px; gap: var(--space-3); }
            .navbar-stat { display: none; }
            .hero-content, .search-bar-section { padding-left: var(--space-3); padding-right: var(--space-3); }
            .search-row { flex-direction: column; align-items: stretch; }
            .search-input, .search-select { width: 100%; box-sizing: border-box; }
            .dg-grid { grid-template-columns: repeat(2, 1fr) !important; }
            .dg-rij-2 { flex-direction: column; }
            .profiel-grid { grid-template-columns: 1fr !important; }
        }


        /* ============================================
           COLLAPSIBLE (uitklapbare secties in het paneel)
           ============================================ */
        .collapsible-card { border: 1px solid var(--gray-200); border-radius: var(--radius-md); margin-bottom: var(--space-3); overflow: hidden; }
        .collapsible-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: var(--space-3) var(--space-4);
            background: var(--gray-50);
            cursor: pointer;
            user-select: none;
        }
        .collapsible-header-left { display: flex; align-items: center; gap: var(--space-2); font-weight: 700; font-size: var(--text-sm); color: var(--gray-800); }
        .collapsible-arrow { transition: transform 0.2s ease; color: var(--gray-400); }
        .collapsible-arrow.dicht { transform: rotate(-90deg); }
        .collapsible-body { padding: var(--space-4); }
        .collapsible-body.dicht { display: none; }

        /* ============================================
           SIMPELE PAGINA-KAARTEN (Dashboard/Inzichten/etc.)
           ============================================ */
        .page-content { padding: var(--space-8) var(--space-10); max-width: 1200px; }
        .page-title { font-size: var(--text-2xl); font-weight: 800; color: var(--gray-900); margin-bottom: var(--space-6); }
        .kaartjes-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: var(--space-4); margin-bottom: var(--space-8); }
        .info-kaart { background: #fff; border: 1px solid var(--gray-200); border-radius: var(--radius-lg); padding: var(--space-5); }
        .info-kaart-getal { font-size: var(--text-3xl); font-weight: 800; color: var(--brand-600); }
        .info-kaart-label { font-size: var(--text-sm); color: var(--gray-400); margin-top: 4px; }
        .eenvoudige-tabel { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid var(--gray-200); border-radius: var(--radius-lg); overflow: hidden; }
        .eenvoudige-tabel th { text-align: left; padding: 10px 14px; background: var(--gray-50); font-size: var(--text-xs); text-transform: uppercase; color: var(--gray-400); border-bottom: 1px solid var(--gray-200); }
        .eenvoudige-tabel td { padding: 10px 14px; border-bottom: 1px solid var(--gray-100); font-size: var(--text-sm); color: var(--gray-700); }
        .lege-staat { text-align: center; padding: var(--space-16); color: var(--gray-400); }
        .dg-rij-2 { display:flex; gap:20px; flex-wrap:wrap; margin-bottom:20px; }
        .dg-rij-2 > div { flex:1; min-width:280px; }
        .dg-kaart-titel { font-size:0.78rem; color:var(--gray-400); text-transform:uppercase; letter-spacing:1.2px; margin-bottom:16px; font-weight:700; }
        .dg-bar-rij { display:flex; align-items:center; gap:10px; margin-bottom:13px; font-size:0.82rem; }
        .dg-bar-label { width:110px; flex-shrink:0; }
        .dg-bar-track { flex:1; background:var(--gray-100); border-radius:6px; height:9px; overflow:hidden; }
        .dg-bar-fill { background:linear-gradient(90deg,var(--brand-500),var(--brand-700)); height:100%; border-radius:6px; }
        .dg-bar-getal { width:34px; text-align:right; color:var(--brand-700); font-weight:700; }
        .dg-activiteit-item { padding:11px 0; border-bottom:1px solid var(--gray-100); font-size:0.83rem; color:var(--gray-700); }
        .dg-activiteit-item:last-child { border-bottom:none; }
        .dg-activiteit-item small { color:var(--gray-400); display:block; margin-top:3px; }
        .mat-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:16px; }
        .mat-kaart { background:#fff; border:1px solid var(--gray-200); border-radius:14px; padding:20px; text-decoration:none; display:block; transition:var(--transition); }
        .mat-kaart:hover { border-color:var(--brand-300); box-shadow:var(--shadow-md); transform:translateY(-2px); }
        .mat-naam { font-size:1.05rem; font-weight:700; color:var(--gray-800); margin-bottom:4px; }
        .mat-sub { font-size:0.78rem; color:var(--gray-400); margin-bottom:12px; }
    </style>
</head>
"""

def sidebar_html(actief):
    items = [
        ("zoeken", "/", "🔍", "Zoeken"),
        ("wereldkaart", "/wereldkaart", "🌍", "World Map"),
        ("dashboard", "/dashboard", "📊", "Dashboard"),
        ("inzichten", "/inzichten", "📈", "Inzichten"),
        ("materialen", "/materialen", "🧱", "Materials"),
        ("certificeringen", "/certificeringen", "🏅", "Certifications"),
        ("contacten", "/contacten", "👥", "Contacten"),
        ("opslagen", "/opslagen", "⭐", "Opslagen"),
        ("notities", "/notities-overzicht", "📝", "Notities"),
        ("instellingen", "/instellingen", "⚙️", "Instellingen"),
    ]
    links = ""
    for key, href, icoon, label in items:
        cls = "sidebar-link active" if key == actief else "sidebar-link"
        links += "<a href=\"" + href + "\" class=\"" + cls + "\"><span class=\"icoon\">" + icoon + "</span> " + label + "</a>\n        "
    return '''<button class="mobiel-menu-knop" onclick="toggleMobielMenu()">☰</button>
<div class="mobiel-overlay" id="mobielOverlay" onclick="toggleMobielMenu()"></div>
<aside class="sidebar" id="mobielSidebar">
    <a href="/" class="sidebar-logo">Recycle<em>Find</em></a>
    <nav class="sidebar-nav">
        ITEMS_HIER
    </nav>
</aside>
<script>
function toggleMobielMenu() {
    document.getElementById("mobielSidebar").classList.toggle("open");
    document.getElementById("mobielOverlay").classList.toggle("open");
}
</script>'''.replace("ITEMS_HIER", links)

def render_simple_page(titel, actief, inhoud_html):
    kop = PAGINA_HOOFD.replace("__TITEL__", titel)
    volledige_html = kop + "<body>\n" + sidebar_html(actief) + '''
<div class="content-wrapper">
<div class="page-content">
''' + inhoud_html + '''
</div>
</div>
</body>
</html>'''
    return volledige_html

HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RecycleFind — Global Recycling Intelligence</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        /* ============================================
           DESIGN SYSTEM — RECYCLEFIND
           ============================================ */

        /* TOKENS */
        :root {
            /* Colors */
            --brand-50:  #fff7ed;
            --brand-100: #ffedd5;
            --brand-200: #fed7aa;
            --brand-300: #fdba74;
            --brand-400: #fb923c;
            --brand-500: #f97316;
            --brand-600: #ea580c;
            --brand-700: #c2410c;
            --brand-800: #9a3412;
            --brand-900: #7c2d12;

            --gray-50:  #f8fafc;
            --gray-100: #f1f5f9;
            --gray-200: #e2e8f0;
            --gray-300: #cbd5e1;
            --gray-400: #94a3b8;
            --gray-500: #64748b;
            --gray-600: #475569;
            --gray-700: #334155;
            --gray-800: #1e293b;
            --gray-900: #0f172a;

            --green-50:  #f0fdf4;
            --green-500: #22c55e;
            --green-600: #16a34a;

            --orange-50:  #fff7ed;
            --orange-500: #f97316;
            --orange-600: #ea580c;

            --red-50:  #fef2f2;
            --red-500: #ef4444;

            /* Typography */
            --font: "Inter", -apple-system, sans-serif;
            --text-xs:   0.7rem;
            --text-sm:   0.8rem;
            --text-base: 0.9rem;
            --text-lg:   1.05rem;
            --text-xl:   1.2rem;
            --text-2xl:  1.5rem;
            --text-3xl:  2rem;
            --text-4xl:  2.8rem;
            --text-5xl:  3.5rem;

            /* Spacing */
            --space-1: 4px;
            --space-2: 8px;
            --space-3: 12px;
            --space-4: 16px;
            --space-5: 20px;
            --space-6: 24px;
            --space-8: 32px;
            --space-10: 40px;
            --space-12: 48px;
            --space-16: 64px;

            /* Radius */
            --radius-sm: 6px;
            --radius-md: 10px;
            --radius-lg: 14px;
            --radius-xl: 20px;
            --radius-full: 9999px;

            /* Shadows */
            --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
            --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
            --shadow-lg: 0 8px 24px rgba(0,0,0,0.1);
            --shadow-xl: 0 16px 48px rgba(0,0,0,0.12);
            --shadow-brand: 0 4px 14px rgba(37,99,235,0.25);

            /* Transitions */
            --transition: all 0.2s cubic-bezier(0.4,0,0.2,1);
        }

        /* RESET */
        *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
        html { scroll-behavior: smooth; }
        body { font-family: var(--font); background: var(--gray-50); color: var(--gray-800); min-height: 100vh; -webkit-font-smoothing: antialiased; }

        /* ============================================
           NAVBAR
           ============================================ */
        .navbar {
            position: sticky;
            top: 0;
            z-index: 100;
            background: rgba(255,255,255,0.9);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--gray-200);
            height: 56px;
            display: flex;
            align-items: center;
            padding: 0 var(--space-8);
            gap: var(--space-8);
        }
        .navbar-logo {
            font-size: var(--text-lg);
            font-weight: 800;
            color: var(--gray-900);
            letter-spacing: -0.5px;
            text-decoration: none;
            flex-shrink: 0;
        }
        .navbar-logo em { color: var(--brand-600); font-style: normal; }
        .navbar-divider { width: 1px; height: 20px; background: var(--gray-200); }
        .navbar-stat { font-size: var(--text-xs); color: var(--gray-400); white-space: nowrap; }
        .navbar-stat strong { color: var(--brand-600); font-weight: 600; }
        .navbar-right { margin-left: auto; display: flex; align-items: center; gap: var(--space-3); }
        .btn-nav {
            font-size: var(--text-sm);
            font-weight: 500;
            padding: 6px 14px;
            border-radius: var(--radius-sm);
            border: none;
            cursor: pointer;
            font-family: var(--font);
            transition: var(--transition);
            text-decoration: none;
        }
        .btn-nav-ghost { background: transparent; color: var(--gray-600); }
        .btn-nav-ghost:hover { background: var(--gray-100); color: var(--gray-900); }
        .btn-nav-primary { background: var(--brand-600); color: #fff; }
        .btn-nav-primary:hover { background: var(--brand-700); box-shadow: var(--shadow-brand); }

        /* ============================================
           HERO
           ============================================ */
        .search-bar-section {
            background: var(--gray-50);
            padding: var(--space-8) var(--space-10);
            border-bottom: 1px solid var(--gray-200);
        }
        .hero-content { max-width: 860px; margin: 0 auto; }

        /* ============================================
           SEARCH
           ============================================ */
        .search-container {
            background: #fff;
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-xl);
            padding: var(--space-5);
            max-width: 860px;
            margin: 0 auto;
            box-shadow: var(--shadow-sm);
        }
        .search-row {
            display: flex;
            gap: var(--space-2);
            flex-wrap: wrap;
            justify-content: center;
        }
        .search-input, .search-select {
            background: #fff;
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-sm);
            padding: 9px 13px;
            font-size: var(--text-sm);
            font-family: var(--font);
            color: var(--gray-800);
            outline: none;
            transition: var(--transition);
        }
        .search-input { width: 200px; }
        .search-input::placeholder { color: var(--gray-400); }
        .search-select { width: 155px; cursor: pointer; }
        .search-input:focus, .search-select:focus {
            border-color: var(--brand-400);
            box-shadow: 0 0 0 3px rgba(59,130,246,0.15);
        }
        .btn-search {
            background: var(--brand-500);
            color: #fff;
            border: none;
            border-radius: var(--radius-sm);
            padding: 9px 20px;
            font-size: var(--text-sm);
            font-weight: 700;
            font-family: var(--font);
            cursor: pointer;
            transition: var(--transition);
            white-space: nowrap;
        }
        .btn-search:hover { background: var(--brand-400); transform: translateY(-1px); box-shadow: var(--shadow-brand); }

        /* ============================================
           STATS BAR
           ============================================ */
        .stats-bar {
            background: #fff;
            border-bottom: 1px solid var(--gray-200);
            padding: var(--space-4) var(--space-10);
            display: flex;
            justify-content: center;
            gap: var(--space-12);
        }
        .stat { text-align: center; }
        .stat-num { font-size: var(--text-2xl); font-weight: 800; color: var(--brand-600); letter-spacing: -0.5px; }
        .stat-label { font-size: var(--text-xs); color: var(--gray-400); text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; margin-top: 2px; }

        /* ============================================
           MAIN LAYOUT
           ============================================ */
        .main {
            max-width: 1440px;
            margin: var(--space-6) auto;
            padding: 0 var(--space-6);
            display: flex;
            gap: var(--space-5);
            align-items: flex-start;
        }

        /* ============================================
           FILTERS SIDEBAR
           ============================================ */
        .filters-panel {
            width: 220px;
            flex-shrink: 0;
            background: #fff;
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-lg);
            padding: var(--space-5);
            box-shadow: var(--shadow-sm);
        }
        .filters-title {
            font-size: var(--text-xs);
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: var(--gray-400);
            margin-bottom: var(--space-4);
        }
        .filter-group { margin-bottom: var(--space-4); }
        .filter-label {
            font-size: var(--text-xs);
            font-weight: 600;
            color: var(--gray-600);
            margin-bottom: var(--space-2);
            display: block;
        }
        .filter-select {
            width: 100%;
            background: var(--gray-50);
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-sm);
            padding: 7px 10px;
            font-size: var(--text-sm);
            font-family: var(--font);
            color: var(--gray-700);
            outline: none;
            cursor: pointer;
            transition: var(--transition);
        }
        .filter-select:focus { border-color: var(--brand-400); background: #fff; }
        .filter-divider { border: none; border-top: 1px solid var(--gray-100); margin: var(--space-4) 0; }
        .btn-apply {
            width: 100%;
            background: var(--brand-600);
            color: #fff;
            border: none;
            border-radius: var(--radius-sm);
            padding: 9px;
            font-size: var(--text-sm);
            font-weight: 600;
            font-family: var(--font);
            cursor: pointer;
            transition: var(--transition);
        }
        .btn-apply:hover { background: var(--brand-700); }
        .btn-reset {
            width: 100%;
            background: transparent;
            color: var(--gray-400);
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-sm);
            padding: 8px;
            font-size: var(--text-xs);
            font-family: var(--font);
            cursor: pointer;
            margin-top: var(--space-2);
            transition: var(--transition);
        }
        .btn-reset:hover { color: var(--gray-600); border-color: var(--gray-300); }

        /* ============================================
           RESULTS PANEL
           ============================================ */
        .results-panel { width: 340px; flex-shrink: 0; }
        .results-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: var(--space-3);
            padding: 0 2px;
        }
        .results-count { font-size: var(--text-sm); color: var(--gray-400); }
        .results-count strong { color: var(--brand-600); font-weight: 700; }
        .results-list {
            max-height: 680px;
            overflow-y: auto;
            scrollbar-width: thin;
            scrollbar-color: var(--gray-200) transparent;
        }

        /* ============================================
           COMPANY CARD
           ============================================ */
        .company-card {
            position: relative;
            background: #fff;
            border: 1px solid var(--gray-200);
            border-left: 3px solid transparent;
            border-radius: var(--radius-md);
            padding: var(--space-4);
            margin-bottom: var(--space-2);
            cursor: pointer;
            transition: var(--transition);
        }
        .company-card:hover {
            border-color: var(--brand-300);
            border-left-color: var(--brand-500);
            box-shadow: 0 8px 20px rgba(234,88,12,0.10);
            transform: translateY(-2px);
        }
        .company-card-top { display: flex; align-items: flex-start; gap: var(--space-3); margin-bottom: var(--space-2); }
        .company-index {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 22px;
            height: 22px;
            min-width: 22px;
            background: var(--brand-600);
            color: #fff;
            border-radius: 5px;
            font-size: 0.65rem;
            font-weight: 700;
            margin-top: 1px;
        }
        .company-name { font-size: var(--text-base); font-weight: 700; color: var(--gray-800); line-height: 1.3; letter-spacing: -0.2px; }
        .verificatie-badge {
            display: inline-flex; align-items: center; gap: 3px;
            font-size: 0.62rem; font-weight: 700; color: var(--green-600);
            background: var(--green-50); border: 1px solid #bbf7d0;
            padding: 1px 6px; border-radius: 4px; margin-left: 6px; vertical-align: middle;
        }
        .company-meta { font-size: var(--text-xs); color: var(--gray-400); margin-bottom: var(--space-2); padding-left: 34px; display: flex; align-items: center; gap: 4px; }
        .company-volume-badge {
            padding-left: 34px; margin-bottom: 6px; font-size: 0.72rem; font-weight: 700; color: var(--brand-700);
        }
        .company-tags { display: flex; flex-wrap: wrap; gap: 4px; padding-left: 34px; }
        .tag {
            display: inline-flex;
            align-items: center;
            padding: 2px 7px;
            border-radius: 4px;
            font-size: 0.65rem;
            font-weight: 600;
            letter-spacing: 0.2px;
        }
        .tag-blue { background: var(--brand-50); color: var(--brand-700); border: 1px solid var(--brand-100); }
        .tag-green { background: var(--green-50); color: var(--green-600); border: 1px solid #bbf7d0; }
        .tag-orange { background: var(--orange-50); color: var(--orange-600); border: 1px solid #fed7aa; }
        .tag-purple { background: #f5f3ff; color: #7c3aed; border: 1px solid #ddd6fe; }

        /* ============================================
           MAP
           ============================================ */
        .map-panel { flex: 1; min-width: 0; }
        #kaart {
            height: 720px;
            border-radius: var(--radius-lg);
            border: 1px solid var(--gray-200);
            box-shadow: var(--shadow-sm);
        }

        /* ============================================
           DETAIL DRAWER
           ============================================ */
        .overlay {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(15,23,42,0.35);
            z-index: 9999;
            backdrop-filter: blur(3px);
        }
        .drawer {
            position: fixed;
            top: 0;
            right: -500px;
            width: 460px;
            height: 100vh;
            background: #fff;
            border-left: 1px solid var(--gray-200);
            box-shadow: var(--shadow-xl);
            z-index: 10000;
            overflow-y: auto;
            transition: right 0.3s cubic-bezier(0.4,0,0.2,1);
        }
        .drawer.open { right: 0; }
        .drawer-header {
            padding: var(--space-6) var(--space-6) var(--space-4);
            border-bottom: 1px solid var(--gray-100);
            position: sticky;
            top: 0;
            background: #fff;
            z-index: 1;
        }
        .drawer-close {
            position: absolute;
            top: var(--space-4);
            right: var(--space-4);
            width: 28px;
            height: 28px;
            background: var(--gray-100);
            border: none;
            border-radius: var(--radius-sm);
            color: var(--gray-500);
            cursor: pointer;
            font-size: 0.9em;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: var(--transition);
        }
        .drawer-close:hover { background: var(--gray-200); color: var(--gray-800); }
        .drawer-company-name { font-size: var(--text-xl); font-weight: 700; color: var(--gray-900); margin-bottom: 4px; padding-right: 36px; }
        .drawer-company-loc { font-size: var(--text-sm); color: var(--gray-400); }
        .drawer-body { padding: var(--space-5) var(--space-6); }
        .drawer-section { margin-bottom: var(--space-5); }
        .drawer-section-title {
            font-size: var(--text-xs);
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: var(--gray-400);
            margin-bottom: var(--space-3);
        }
        .drawer-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: var(--space-2) 0;
            border-bottom: 1px solid var(--gray-50);
        }
        .drawer-row:last-child { border-bottom: none; }
        .drawer-row-label { font-size: var(--text-sm); color: var(--gray-400); font-weight: 500; }
        .drawer-row-value { font-size: var(--text-sm); color: var(--gray-700); font-weight: 500; text-align: right; }
        .drawer-divider { border: none; border-top: 1px solid var(--gray-100); margin: var(--space-4) 0; }
        .btn-website {
            display: inline-flex;
            align-items: center;
            gap: var(--space-2);
            background: var(--brand-600);
            color: #fff;
            padding: 8px 16px;
            border-radius: var(--radius-sm);
            text-decoration: none;
            font-size: var(--text-sm);
            font-weight: 600;
            transition: var(--transition);
            margin-right: var(--space-2);
        }
        .btn-website:hover { background: var(--brand-700); box-shadow: var(--shadow-brand); }
        .btn-enf {
            display: inline-flex;
            align-items: center;
            gap: var(--space-2);
            background: var(--gray-100);
            color: var(--gray-600);
            padding: 8px 16px;
            border-radius: var(--radius-sm);
            text-decoration: none;
            font-size: var(--text-sm);
            font-weight: 600;
            transition: var(--transition);
        }
        .btn-enf:hover { background: var(--gray-200); color: var(--gray-800); }
        .score-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 36px;
            height: 36px;
            border-radius: var(--radius-sm);
            font-size: var(--text-sm);
            font-weight: 800;
        }
        .score-high { background: var(--green-50); color: var(--green-600); }
        .score-mid { background: var(--orange-50); color: var(--orange-600); }

        /* ============================================
           WELCOME STATE
           ============================================ */
        .welcome-state {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: var(--space-16);
            text-align: center;
        }
        .welcome-icon { font-size: 3em; margin-bottom: var(--space-4); }
        .welcome-title { font-size: var(--text-2xl); font-weight: 700; color: var(--gray-800); margin-bottom: var(--space-2); }
        .welcome-sub { font-size: var(--text-base); color: var(--gray-400); max-width: 400px; }

        /* ============================================
           SIDEBAR
           ============================================ */
        body { display: flex; }
        .sidebar {
            width: 220px;
            min-width: 220px;
            height: 100vh;
            position: sticky;
            top: 0;
            background: #fff;
            border-right: 1px solid var(--gray-200);
            display: flex;
            flex-direction: column;
            padding: var(--space-5) 0;
            flex-shrink: 0;
        }
        .sidebar-logo {
            font-size: var(--text-lg);
            font-weight: 800;
            color: var(--gray-900);
            letter-spacing: -0.5px;
            text-decoration: none;
            padding: 0 var(--space-5);
            margin-bottom: var(--space-6);
            display: block;
        }
        .sidebar-logo em { color: var(--brand-600); font-style: normal; }
        .sidebar-nav { display: flex; flex-direction: column; gap: 2px; padding: 0 var(--space-3); }
        .sidebar-link {
            display: flex;
            align-items: center;
            gap: var(--space-3);
            padding: 9px var(--space-3);
            border-radius: var(--radius-sm);
            color: var(--gray-600);
            text-decoration: none;
            font-size: var(--text-sm);
            font-weight: 500;
            transition: var(--transition);
        }
        .sidebar-link:hover { background: var(--gray-50); color: var(--gray-900); }
        .sidebar-link.active { background: var(--brand-50); color: var(--brand-700); font-weight: 700; }
        .sidebar-link .icoon { font-size: 1.05em; width: 20px; text-align: center; }
        .content-wrapper { flex: 1; min-width: 0; }
        .mobiel-menu-knop { display: none; }
        .mobiel-overlay { display: none; }
        @media (max-width: 900px) {
            .sidebar {
                position: fixed;
                left: -240px;
                top: 0;
                z-index: 2000;
                transition: left 0.25s ease;
                box-shadow: 0 0 24px rgba(0,0,0,0.18);
            }
            .sidebar.open { left: 0; }
            .mobiel-menu-knop {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 38px; height: 38px;
                border: 1px solid var(--gray-200); background: #fff;
                border-radius: 8px; cursor: pointer; font-size: 18px;
                position: fixed; top: 12px; left: 12px; z-index: 1500;
                box-shadow: var(--shadow-sm);
            }
            .mobiel-overlay.open {
                display: block;
                position: fixed; inset: 0; background: rgba(15,23,42,0.35); z-index: 1900;
            }
            .content-wrapper { padding-top: 52px; }
            .page-content { padding: var(--space-4) !important; }
            .main { flex-direction: column; padding: 0 var(--space-3); }
            .filters-panel { width: 100%; box-sizing: border-box; }
            .results-panel { width: 100%; }
            #kaart { height: 320px; }
            .map-panel { width: 100%; }
            .drawer { width: 100%; right: -100%; }
            .navbar { padding: 0 var(--space-4) 0 56px; flex-wrap: wrap; height: auto; min-height: 56px; gap: var(--space-3); }
            .navbar-stat { display: none; }
            .hero-content, .search-bar-section { padding-left: var(--space-3); padding-right: var(--space-3); }
            .search-row { flex-direction: column; align-items: stretch; }
            .search-input, .search-select { width: 100%; box-sizing: border-box; }
            .dg-grid { grid-template-columns: repeat(2, 1fr) !important; }
            .dg-rij-2 { flex-direction: column; }
            .profiel-grid { grid-template-columns: 1fr !important; }
        }


        /* ============================================
           COLLAPSIBLE (uitklapbare secties in het paneel)
           ============================================ */
        .drawer-tabs { display: flex; gap: var(--space-1); border-bottom: 1px solid var(--gray-100); margin-bottom: var(--space-4); }
        .drawer-tab {
            background: none; border: none; cursor: pointer; font-family: var(--font);
            font-size: var(--text-sm); font-weight: 600; color: var(--gray-400);
            padding: var(--space-2) var(--space-1); margin-bottom: -1px;
            border-bottom: 2px solid transparent; transition: var(--transition);
        }
        .drawer-tab:hover { color: var(--gray-700); }
        .drawer-tab.actief { color: var(--brand-600); border-bottom-color: var(--brand-600); }
        .drawer-tab-paneel { display: none; }
        .drawer-tab-paneel.actief { display: block; }
        .collapsible-card { border: 1px solid var(--gray-200); border-radius: var(--radius-md); margin-bottom: var(--space-3); overflow: hidden; }
        .collapsible-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: var(--space-3) var(--space-4);
            background: var(--gray-50);
            cursor: pointer;
            user-select: none;
        }
        .collapsible-header-left { display: flex; align-items: center; gap: var(--space-2); font-weight: 700; font-size: var(--text-sm); color: var(--gray-800); }
        .collapsible-arrow { transition: transform 0.2s ease; color: var(--gray-400); }
        .collapsible-arrow.dicht { transform: rotate(-90deg); }
        .collapsible-body { padding: var(--space-4); }
        .collapsible-body.dicht { display: none; }

        /* ============================================
           SIMPELE PAGINA-KAARTEN (Dashboard/Inzichten/etc.)
           ============================================ */
        .page-content { padding: var(--space-8) var(--space-10); max-width: 1200px; }
        .page-title { font-size: var(--text-2xl); font-weight: 800; color: var(--gray-900); margin-bottom: var(--space-6); }
        .kaartjes-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: var(--space-4); margin-bottom: var(--space-8); }
        .info-kaart { background: #fff; border: 1px solid var(--gray-200); border-radius: var(--radius-lg); padding: var(--space-5); }
        .info-kaart-getal { font-size: var(--text-3xl); font-weight: 800; color: var(--brand-600); }
        .info-kaart-label { font-size: var(--text-sm); color: var(--gray-400); margin-top: 4px; }
        .eenvoudige-tabel { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid var(--gray-200); border-radius: var(--radius-lg); overflow: hidden; }
        .eenvoudige-tabel th { text-align: left; padding: 10px 14px; background: var(--gray-50); font-size: var(--text-xs); text-transform: uppercase; color: var(--gray-400); border-bottom: 1px solid var(--gray-200); }
        .eenvoudige-tabel td { padding: 10px 14px; border-bottom: 1px solid var(--gray-100); font-size: var(--text-sm); color: var(--gray-700); }
        .lege-staat { text-align: center; padding: var(--space-16); color: var(--gray-400); }
    </style>
</head>
<body>

<button class="mobiel-menu-knop" onclick="toggleMobielMenu()">☰</button>
<div class="mobiel-overlay" id="mobielOverlay" onclick="toggleMobielMenu()"></div>
<aside class="sidebar" id="mobielSidebar">
    <a href="/" class="sidebar-logo">Recycle<em>Find</em></a>
    <nav class="sidebar-nav">
        <a href="/" class="sidebar-link active"><span class="icoon">🔍</span> Zoeken</a>
        <a href="/wereldkaart" class="sidebar-link"><span class="icoon">🌍</span> World Map</a>
        <a href="/dashboard" class="sidebar-link"><span class="icoon">📊</span> Dashboard</a>
        <a href="/inzichten" class="sidebar-link"><span class="icoon">📈</span> Inzichten</a>
        <a href="/materialen" class="sidebar-link"><span class="icoon">🧱</span> Materials</a>
        <a href="/certificeringen" class="sidebar-link"><span class="icoon">🏅</span> Certifications</a>
        <a href="/contacten" class="sidebar-link"><span class="icoon">👥</span> Contacten</a>
        <a href="/opslagen" class="sidebar-link"><span class="icoon">⭐</span> Opslagen</a>
        <a href="/notities-overzicht" class="sidebar-link"><span class="icoon">📝</span> Notities</a>
        <a href="/instellingen" class="sidebar-link"><span class="icoon">⚙️</span> Instellingen</a>
    </nav>
</aside>
<script>
function toggleMobielMenu() {
    document.getElementById("mobielSidebar").classList.toggle("open");
    document.getElementById("mobielOverlay").classList.toggle("open");
}
</script>

<div class="content-wrapper">

<div class="ai-search-box">
  <input type="text" id="aiSearchInput" placeholder="Bijv. papierbedrijven in Duitsland met meer dan 50 werknemers" />
  <button id="aiSearchButton">Zoeken</button>
</div>
<div id="aiSearchResults"></div>
<script>
  const input = document.getElementById('aiSearchInput');
  const button = document.getElementById('aiSearchButton');
  const resultsDiv = document.getElementById('aiSearchResults');
  async function aiSearch(query) {
    const res = await fetch('/api/ai-search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });
    return await res.json();
  }
  async function handleSearch() {
    const query = input.value.trim();
    if (!query) return;
    resultsDiv.innerHTML = '<p>Zoeken...</p>';
    try {
      const data = await aiSearch(query);
      if (data.error) {
        resultsDiv.innerHTML = `<p>Fout: ${data.error}</p>`;
        return;
      }
      let html = `<p>${data.total} resultaten gevonden</p>`;
      data.results.forEach(company => {
        html += `<div class="company-card"><h3>${company.naam}</h3><p>${company.land || ''} - ${company.regio || ''}</p></div>`;
      });
      resultsDiv.innerHTML = html;
    } catch (err) {
      resultsDiv.innerHTML = '<p>Er ging iets mis.</p>';
      console.error(err);
    }
  }
  button.addEventListener('click', handleSearch);
  input.addEventListener('keypress', (e) => { if (e.key === 'Enter') handleSearch(); });
</script>

<!-- NAVBAR -->
<nav class="navbar">
    <a href="/" class="navbar-logo">Recycle<em>Find</em></a>
    <div class="navbar-divider"></div>
    <span class="navbar-stat"><strong>{{ totaal }}</strong> companies · <strong>{{ landen|length }}</strong> countries</span>
    <div class="navbar-right">
       <button onclick="toonMeldingen()" style="position:relative;background:none;border:none;cursor:pointer;font-size:18px;margin-right:8px;">
    🔔<span id="meldingBadge" style="display:none;position:absolute;top:-4px;right:-4px;background:#ef4444;color:white;font-size:10px;font-weight:700;border-radius:50%;width:16px;height:16px;display:flex;align-items:center;justify-content:center;"></span>
</button>
         <a href="#" class="btn-nav btn-nav-ghost">Sign in</a>
        <a href="#" class="btn-nav btn-nav-primary">Get started</a>
    </div>
</nav>

<!-- ZOEKBALK -->
<section class="search-bar-section">
    <div class="hero-content">
        <form method="POST" id="searchForm">
            <div class="search-container">
                <div class="search-row">
                    <input class="search-input" name="zoekterm" placeholder="🔍  Search company name..." value="{{ zoekterm }}">
                    <select class="search-select" name="land" id="landSelect" onchange="updateRegio()">
                        <option value="">All Countries</option>
                        {% for l in landen %}
                        <option value="{{ l }}" {% if land == l %}selected{% endif %}>{{ l }}</option>
                        {% endfor %}
                    </select>
                    <select class="search-select" name="regio" id="regioSelect">
                        <option value="">All Regions</option>
                        {% if land and land in regio_per_land %}
                        {% for r in regio_per_land[land] %}
                        <option value="{{ r }}" {% if regio == r %}selected{% endif %}>{{ r }}</option>
                        {% endfor %}
                        {% endif %}
                    </select>
                    <button type="submit" class="btn-search">Search →</button>
                </div>
            </div>
        </form>
    </div>
</section>

<!-- MAIN -->
<div class="main">

    {% if bedrijven %}
    <!-- FILTERS -->
    <form method="POST" id="filterForm">
        <input type="hidden" name="zoekterm" value="{{ zoekterm }}">
        <input type="hidden" name="land" value="{{ land }}">
        <input type="hidden" name="regio" value="{{ regio }}">
        <aside class="filters-panel">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-4);">
                <div class="filters-title" style="margin-bottom:0;display:flex;align-items:center;gap:6px;">🎚️ Filters</div>
                <a href="/" style="font-size:var(--text-xs);color:var(--gray-400);text-decoration:none;font-weight:600;">Wis filters</a>
            </div>

            <div class="filter-group">
                <label class="filter-label">Customer Type</label>
                <select class="filter-select" name="klanttype">
                    <option value="">All types</option>
                    <option value="Commercial" {% if klanttype == "Commercial" %}selected{% endif %}>Commercial</option>
                    <option value="Industrial" {% if klanttype == "Industrial" %}selected{% endif %}>Industrial</option>
                    <option value="Residential" {% if klanttype == "Residential" %}selected{% endif %}>Residential</option>
                </select>
            </div>

            <div class="filter-group">
                <label class="filter-label">Material</label>
                <select class="filter-select" name="materiaal">
                    <option value="">All materials</option>
                    <option value="Paper" {% if materiaal == "Paper" %}selected{% endif %}>Paper</option>
                    <option value="Plastic" {% if materiaal == "Plastic" %}selected{% endif %}>Plastic</option>
                    <option value="Metal" {% if materiaal == "Metal" %}selected{% endif %}>Metal</option>
                    <option value="Glass" {% if materiaal == "Glass" %}selected{% endif %}>Glass</option>
                    <option value="Wood" {% if materiaal == "Wood" %}selected{% endif %}>Wood</option>
                    <option value="Electronic" {% if materiaal == "Electronic" %}selected{% endif %}>Electronic</option>
                </select>
            </div>

            <div class="filter-group">
                <label class="filter-label">Annual Volume</label>
                <select class="filter-select" name="volume_filter">
                    <option value="">Any volume</option>
                    <option value="small">Under 1,000 t/y</option>
                    <option value="medium">1,000 – 10,000 t/y</option>
                    <option value="large">Over 10,000 t/y</option>
                </select>
            </div>

            <div class="filter-group">
                <label class="filter-label">Bedrijfstype</label>
                <select class="filter-select" name="brontype">
                    <option value="">Alle types</option>
                    <option value="Schroothandel" {% if brontype == "Schroothandel" %}selected{% endif %}>Schroothandel</option>
                    <option value="Recyclingcentrum" {% if brontype == "Recyclingcentrum" %}selected{% endif %}>Recyclingcentrum</option>
                    <option value="Papierfabriek" {% if brontype == "Papierfabriek" %}selected{% endif %}>Papierfabriek</option>
                    <option value="Recycling-kantoor" {% if brontype == "Recycling-kantoor" %}selected{% endif %}>Recycling-kantoor</option>
                    <option value="Afvalbeheer" {% if brontype == "Afvalbeheer" %}selected{% endif %}>Afvalbeheer</option>
                </select>
            </div>

            <hr class="filter-divider">
            <button type="submit" class="btn-apply">Filters toepassen</button>
        </aside>
    </form>

    <!-- RESULTS -->
    <div class="results-panel">
        <div class="results-header">
            <div class="results-count">
                <strong>{{ bedrijven|length }}</strong> of <strong>{{ totaal_gevonden }}</strong> results
                {% if totaal_paginas > 1 %}<span style="color:var(--gray-300);"> · pagina {{ pagina }}/{{ totaal_paginas }}</span>{% endif %}
            </div>
            <a href="/export-csv?{{ export_query }}" style="font-size:12px;font-weight:600;color:var(--brand-600);text-decoration:none;border:1px solid var(--gray-200);padding:5px 10px;border-radius:6px;">⬇ Export to CSV</a>
        </div>
        <div class="results-list">
            {% for bedrijf in bedrijven %}
            <div class="company-card"
                onclick="openDrawer('{{ bedrijf.naam|replace("'","&#39;") }}', '{{ bedrijf.regio }}', '{{ bedrijf.land }}', '{{ bedrijf.url }}', '{{ bedrijf.klanttype }}', '{{ bedrijf.materialen }}', '{{ bedrijf.volume }}', {{ bedrijf.lat }}, {{ bedrijf.lon }}, '{{ bedrijf.adres|default("", true)|replace("'","&#39;") }}', '{{ bedrijf.telefoon|default("", true) }}', '{{ bedrijf.certificeringen|default("", true)|replace("'","&#39;") }}')">
                <div class="company-card-top">
                    <span class="company-index">{{ loop.index }}</span>
                    <span class="company-name" style="flex:1;">{{ bedrijf.naam }}{% if bedrijf.adres or bedrijf.telefoon %}<span class="verificatie-badge">✓ Geverifieerd</span>{% endif %}</span>
                    <span class="star-btn {% if bedrijf.naam in opgeslagen_namen %}opgeslagen{% endif %}" onclick="toggleOpslaan(event, '{{ bedrijf.naam|replace("'","\\'") }}', this)">{% if bedrijf.naam in opgeslagen_namen %}★{% else %}☆{% endif %}</span>
                </div>
                <div class="company-meta">📍 {{ bedrijf.regio }}, {{ bedrijf.land }}{% if bedrijf.brontype %} · <span style="color:var(--gray-500);font-weight:600;">{{ bedrijf.brontype }}</span>{% endif %}</div>
                {% if bedrijf.volume %}<div class="company-volume-badge">⚙ {{ bedrijf.volume }} t/jaar capaciteit</div>{% endif %}
                <div class="company-tags">
                    {% if bedrijf.klanttype %}{% for t in bedrijf.klanttype.split(",")[:2] %}<span class="tag tag-blue">{{ t.strip() }}</span>{% endfor %}{% endif %}
                    {% if bedrijf.materialen %}{% for m in bedrijf.materialen.split(",")[:2] %}<span class="tag tag-green">{{ m.strip() }}</span>{% endfor %}{% endif %}
                    {% if bedrijf.certificeringen %}{% for c in bedrijf.certificeringen.split(",")[:2] %}<span class="tag tag-purple">🏅 {{ c.strip() }}</span>{% endfor %}{% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
        {% if totaal_paginas > 1 %}
        <div style="display:flex;gap:6px;justify-content:center;align-items:center;margin-top:14px;flex-wrap:wrap;">
            {% if pagina > 1 %}<a href="{{ maak_pagina_url(pagina - 1) }}" style="padding:6px 10px;border:1px solid var(--gray-200);border-radius:6px;text-decoration:none;color:var(--gray-600);font-size:13px;">←</a>{% endif %}
            {% if pagina > 2 %}<a href="{{ maak_pagina_url(1) }}" style="padding:6px 10px;border:1px solid var(--gray-200);border-radius:6px;text-decoration:none;color:var(--gray-600);font-size:13px;">1</a>{% endif %}
            {% if pagina > 3 %}<span style="color:var(--gray-300);">…</span>{% endif %}
            {% if pagina > 1 %}<a href="{{ maak_pagina_url(pagina - 1) }}" style="padding:6px 10px;border:1px solid var(--gray-200);border-radius:6px;text-decoration:none;color:var(--gray-600);font-size:13px;">{{ pagina - 1 }}</a>{% endif %}
            <span style="padding:6px 10px;border-radius:6px;background:var(--brand-600);color:#fff;font-weight:700;font-size:13px;">{{ pagina }}</span>
            {% if pagina < totaal_paginas %}<a href="{{ maak_pagina_url(pagina + 1) }}" style="padding:6px 10px;border:1px solid var(--gray-200);border-radius:6px;text-decoration:none;color:var(--gray-600);font-size:13px;">{{ pagina + 1 }}</a>{% endif %}
            {% if pagina < totaal_paginas - 2 %}<span style="color:var(--gray-300);">…</span>{% endif %}
            {% if pagina < totaal_paginas - 1 %}<a href="{{ maak_pagina_url(totaal_paginas) }}" style="padding:6px 10px;border:1px solid var(--gray-200);border-radius:6px;text-decoration:none;color:var(--gray-600);font-size:13px;">{{ totaal_paginas }}</a>{% endif %}
            {% if pagina < totaal_paginas %}<a href="{{ maak_pagina_url(pagina + 1) }}" style="padding:6px 10px;border:1px solid var(--gray-200);border-radius:6px;text-decoration:none;color:var(--gray-600);font-size:13px;">→</a>{% endif %}
        </div>
        {% endif %}
    </div>

    <!-- MAP -->
    <div class="map-panel">
        <div id="kaart"></div>
    </div>

    {% else %}
    <div class="welcome-state">
        <div class="welcome-icon">🔍</div>
        {% if er_is_gefilterd %}
        <div class="welcome-title">Geen bedrijven gevonden voor deze filters</div>
        <div class="welcome-sub">Probeer een andere combinatie, of klik op "Wis filters" om opnieuw te beginnen</div>
        {% else %}
        <div class="welcome-title">Search for recycling companies</div>
        <div class="welcome-sub">Use the search bar or filters above to find companies across {{ landen|length }} countries</div>
        {% endif %}
    </div>
    {% endif %}

</div>

<div id="fabriekAnalysePaneel" style="display:none;position:fixed;top:60px;right:20px;width:380px;max-height:600px;overflow-y:auto;background:white;border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,0.15);z-index:9998;padding:14px;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
        <div style="font-weight:700;" id="fabriekAnalyseTitel">Leveranciers</div>
        <button onclick="document.getElementById('fabriekAnalysePaneel').style.display='none'" style="background:none;border:none;cursor:pointer;font-size:16px;">✕</button>
    </div>
    <div id="fabriekAnalyseLijst"></div>
</div>
<div id="meldingenPaneel" style="display:none;position:fixed;top:60px;right:20px;width:340px;max-height:400px;overflow-y:auto;background:white;border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,0.15);z-index:9998;padding:12px;">
    <div style="font-weight:700;margin-bottom:8px;">Meldingen</div>
    <div id="meldingenLijst"></div>
</div>
<!-- DETAIL DRAWER -->
<div class="overlay" id="overlay" onclick="closeDrawer()"></div>
<div class="drawer" id="drawer">
    <div class="drawer-header">
        <button class="drawer-close" onclick="closeDrawer()">✕</button>
        <div class="drawer-company-name" id="drawerName"></div>
        <div class="drawer-company-loc" id="drawerLoc"></div>
    </div>
    <div class="drawer-body" id="drawerBody"></div>
</div>

<script>
var regioPer = {{ regio_per_land|tojson }};

function updateRegio() {
    var land = document.getElementById("landSelect").value;
    var sel = document.getElementById("regioSelect");
    sel.innerHTML = "<option value=''>All Regions</option>";
    if (land && regioPer[land]) {
        regioPer[land].forEach(function(r) {
            var o = document.createElement("option");
            o.value = r; o.text = r;
            sel.appendChild(o);
        });
    }
}

{% if bedrijven %}
var kaart = L.map("kaart").setView([{{ bedrijven[0].lat }}, {{ bedrijven[0].lon }}], 5);
var straatKaart = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {attribution:"© OpenStreetMap"});
var satellietKaart = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {attribution:"© Esri"});
straatKaart.addTo(kaart);
L.control.layers({"Kaart": straatKaart, "Satelliet": satellietKaart}).addTo(kaart);
var clusterGroep = L.markerClusterGroup();
{% for b in bedrijven %}
L.marker([{{ b.lat }}, {{ b.lon }}])
    .bindPopup("<b>{{ b.naam|replace('"','') }}</b><br><small>{{ b.regio }}, {{ b.land }}</small>")
    .on("click", function(){ openDrawer("{{ b.naam|replace("'","&#39;") }}","{{ b.regio }}","{{ b.land }}","{{ b.url }}","{{ b.klanttype }}","{{ b.materialen }}","{{ b.volume }}",{{ b.lat }},{{ b.lon }},"{{ b.adres|default('', true)|replace("'","&#39;") }}","{{ b.telefoon|default('', true) }}","{{ b.certificeringen|default('', true)|replace("'","&#39;") }}"); })
    .addTo(clusterGroep);
{% endfor %}
kaart.addLayer(clusterGroep);
var fabriekIcon = L.divIcon({
    html: '<div style="background:#ea580c;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:16px;box-shadow:0 2px 8px rgba(0,0,0,0.3);border:2px solid white;">🏭</div>',
    className: '',
    iconSize: [32, 32],
    iconAnchor: [16, 16]
});
{% for f in papierfabrieken %}{% if f.lat and f.lon %}
L.marker([{{ f.lat }}, {{ f.lon }}], {icon: fabriekIcon})
    .addTo(kaart)
.bindPopup('<b>🏭 {{ f.naam }}</b><br><small>{{ f.stad }}, {{ f.land }}</small><br><small>{{ f.materialen }}</small><br><button data-fabriek="{{ f.naam }}" onclick="toonFabriekAnalyse(this.dataset.fabriek)" style="margin-top:6px;padding:4px 10px;background:#ea580c;color:white;border:none;border-radius:6px;cursor:pointer;font-size:12px;">Toon leveranciers</button>');
{% endif %}{% endfor %}
{% endif %}

function kaartHTML(id, titel, icoon, inhoud, openStaan) {
    return `
        <div class="collapsible-card">
            <div class="collapsible-header" onclick="toggleKaart('${id}')">
                <span class="collapsible-header-left"><span>${icoon}</span> ${titel}</span>
                <span class="collapsible-arrow ${openStaan ? '' : 'dicht'}" id="pijl-${id}">▾</span>
            </div>
            <div class="collapsible-body ${openStaan ? '' : 'dicht'}" id="${id}">
                ${inhoud}
            </div>
        </div>`;
}

function toggleKaart(id) {
    document.getElementById(id).classList.toggle("dicht");
    document.getElementById("pijl-" + id).classList.toggle("dicht");
}

function wisselDrawerTab(naam) {
    ["info", "logistiek", "commercieel"].forEach(function(t) {
        var paneel = document.getElementById("tabpaneel-" + t);
        var knop = document.getElementById("tabknop-" + t);
        if (paneel) paneel.classList.toggle("actief", t === naam);
        if (knop) knop.classList.toggle("actief", t === naam);
    });
}

function bouwDrawerBody(klanttype, materialen, volume, contactHTML, websiteBtnHTML) {
    const geverifieerd = (window.currentDrawerData && (window.currentDrawerData.adres || window.currentDrawerData.telefoon))
        ? `<div class="drawer-row"><span class="drawer-row-label">Status</span><span class="drawer-row-value" style="color:var(--green-600);font-weight:700;">✓ Geverifieerd</span></div>` : "";

    const algemeen = `
        ${geverifieerd}
        <div class="drawer-row"><span class="drawer-row-label">Status</span><span class="drawer-row-value">
    <select id="statusSelect" onchange="wijzigStatus()" style="padding:4px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;">
        <option value="">Geen status</option>
        <option value="klant">🟢 Klant</option>
        <option value="potentie">🟡 Potentie</option>
        <option value="in_proces">🔵 In Proces</option>
        <option value="geen_interesse">⚪ Geen Interesse</option>
    </select>
</span></div>
        <div class="drawer-row"><span class="drawer-row-label">Customer Type</span><span class="drawer-row-value">${klanttype || "—"}</span></div>
        <div class="drawer-row"><span class="drawer-row-label">Materials</span><span class="drawer-row-value">${materialen || "—"}</span></div>
        <div class="drawer-row"><span class="drawer-row-label">Annual Volume</span><span class="drawer-row-value">${volume ? volume + " t/y" : "—"}</span></div>
        ${window.currentDrawerData && window.currentDrawerData.certificeringen ? `<div class="drawer-row"><span class="drawer-row-label">Certificeringen</span><span class="drawer-row-value">🏅 ${window.currentDrawerData.certificeringen}</span></div>` : ""}`;

    const logistiek = `<div id="transportInfo"><div style="color:var(--gray-400);font-size:var(--text-sm);">Laden...</div></div>`;

    const commercieel = `
        <div style="font-size:12px;color:#94a3b8;margin-bottom:6px;">Stuur melding naar:</div>
        <select id="meldingOntvanger" style="width:100%;padding:6px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;margin-bottom:6px;">
            <option value="">Kies persoon/team...</option>
        </select>
        <div style="display:flex;gap:8px;">
            <input type="text" id="meldingTekst" placeholder="Melding..." style="flex:1;padding:6px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;">
            <button onclick="stuurMelding()" style="padding:6px 14px;background:#ef4444;color:white;border:none;border-radius:6px;cursor:pointer;font-size:13px;">Stuur</button>
        </div>`;

    const aiAnalyse = `
        <button id="equipmentBtn" onclick="analyseUitrusting()" style="padding:8px 16px;background:var(--brand-600);color:white;border:none;border-radius:6px;cursor:pointer;">AI Analyseren</button>
        <div id="equipmentResults" style="margin-top:12px;"></div>`;

    const notities = `
        <div id="notitiesLijst" style="margin-bottom:12px;"></div>
        <textarea id="notitieInput" placeholder="Schrijf een notitie..." style="width:100%;min-height:60px;padding:8px;border:1px solid #e2e8f0;border-radius:6px;font-family:inherit;font-size:13px;resize:vertical;"></textarea>
        <div style="display:flex;align-items:center;gap:12px;margin-top:8px;">
            <label style="font-size:13px;"><input type="radio" name="notitieType" value="team" checked> Team</label>
            <label style="font-size:13px;"><input type="radio" name="notitieType" value="prive"> Privé</label>
            <button onclick="voegNotitieToe()" style="margin-left:auto;padding:6px 14px;background:var(--brand-600);color:white;border:none;border-radius:6px;cursor:pointer;font-size:13px;">Toevoegen</button>
        </div>`;

    const contactDetails = `
        <div id="fotosLijst" style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;"></div>
        <input type="file" id="fotoInput" accept="image/*" style="display:none;" onchange="uploadFoto()">
        <button onclick="document.getElementById('fotoInput').click()" style="padding:6px 14px;background:var(--brand-600);color:white;border:none;border-radius:6px;cursor:pointer;font-size:13px;margin-bottom:12px;">📷 Foto toevoegen</button>
        ${contactHTML}
        ${websiteBtnHTML}`;

    const tabbalk = `
        <div class="drawer-tabs">
            <button class="drawer-tab actief" id="tabknop-info" onclick="wisselDrawerTab('info')">Info</button>
            <button class="drawer-tab" id="tabknop-logistiek" onclick="wisselDrawerTab('logistiek')">Logistiek</button>
            <button class="drawer-tab" id="tabknop-commercieel" onclick="wisselDrawerTab('commercieel')">Commercieel</button>
        </div>`;

    const paneelInfo = `<div class="drawer-tab-paneel actief" id="tabpaneel-info">` +
        kaartHTML("kaartAlgemeen", "Algemene informatie", "ℹ️", algemeen, true) +
        kaartHTML("kaartNotities", "Notities", "📝", notities, false) +
        `</div>`;

    const paneelLogistiek = `<div class="drawer-tab-paneel" id="tabpaneel-logistiek">` +
        kaartHTML("kaartLogistiek", "Logistiek", "🚚", logistiek, true) +
        `</div>`;

    const paneelCommercieel = `<div class="drawer-tab-paneel" id="tabpaneel-commercieel">` +
        kaartHTML("kaartCommercieel", "Commercieel", "💬", commercieel, true) +
        kaartHTML("kaartAi", "AI-uitrusting analyse", "✨", aiAnalyse, false) +
        kaartHTML("kaartContact", "Contact & details", "📇", contactDetails, false) +
        `</div>`;

    return tabbalk + paneelInfo + paneelLogistiek + paneelCommercieel;
}

function openDrawer(naam, regio, land, url, klanttype, materialen, volume, lat, lon, adres, telefoon, certificeringen) {
    window.currentDrawerData = {naam: naam, land: land, regio: regio, klanttype: klanttype, materialen: materialen, volume: volume, lat: lat, lon: lon, adres: adres || "", telefoon: telefoon || "", certificeringen: certificeringen || ""};
    {% if bedrijven %}kaart.flyTo([lat,lon], 12);{% endif %}
    document.getElementById("drawerName").textContent = naam;
    document.getElementById("drawerLoc").innerHTML = "📍 " + regio + ", " + land + ' · <a href="/bedrijf/' + encodeURIComponent(naam) + '" style="color:var(--brand-600);font-weight:600;text-decoration:none;">Volledig profiel →</a>';
    document.getElementById("drawerBody").innerHTML = bouwDrawerBody(klanttype, materialen, volume, `<div style="color:var(--gray-400);font-size:var(--text-sm);">⏳ Loading details...</div>`, "");
    document.getElementById("overlay").style.display = "block";
    document.getElementById("drawer").classList.add("open");
    laadNotities();
    laadTransport();
    laadStatus();
    vulMeldingDropdowns();
    laadFotos();

    fetch("/details?url=" + encodeURIComponent(url))
        .then(r => r.json())
        .then(data => {
            window.currentDrawerData.stad = data.stad || "";
            if (data.lat_precies && data.lon_precies) {
                window.currentDrawerData.lat = data.lat_precies;
                window.currentDrawerData.lon = data.lon_precies;
            }
            var contactHTML = "";
            if (data.website) contactHTML += `<div class="drawer-row"><span class="drawer-row-label">Website</span><span class="drawer-row-value"><a href="${data.website}" target="_blank" style="color:var(--brand-600);font-weight:600;">${data.website.replace("https://","").replace("http://","").split("/")[0]}</a></span></div>`;
            var telefoon = data.telefoon || window.currentDrawerData.telefoon;
            var adres = data.adres || window.currentDrawerData.adres;
            if (telefoon) contactHTML += `<div class="drawer-row"><span class="drawer-row-label">Phone</span><span class="drawer-row-value">${telefoon}</span></div>`;
            if (adres) contactHTML += `<div class="drawer-row"><span class="drawer-row-label">Address</span><span class="drawer-row-value">${adres}${data.stad?", "+data.stad:""}</span></div>`;
            if (data.medewerkers) contactHTML += `<div class="drawer-row"><span class="drawer-row-label">Employees</span><span class="drawer-row-value">${data.medewerkers}</span></div>`;
            if (!contactHTML) contactHTML = `<div style="color:var(--gray-400);font-size:var(--text-sm);">No additional details available</div>`;
            if (data.lat_precies && data.lon_precies) {
                kaart.flyTo([data.lat_precies, data.lon_precies], 17);
                L.marker([data.lat_precies, data.lon_precies]).addTo(kaart)
                    .bindPopup("<b>" + naam + "</b>").openPopup();
            }
            var websiteBtnHTML = data.website ? `<a href="${data.website}" target="_blank" class="btn-website">🌐 Visit Website</a>` : "";

            document.getElementById("drawerBody").innerHTML = bouwDrawerBody(klanttype, materialen, volume, contactHTML, websiteBtnHTML);
            laadNotities();
            laadTransport();
            laadStatus();
            vulMeldingDropdowns();
            laadFotos();
        });
}

async function analyseUitrusting() {
    const btn = document.getElementById("equipmentBtn");
    const resultsDiv = document.getElementById("equipmentResults");
    btn.disabled = true;
    btn.innerText = "Bezig met analyseren...";
    resultsDiv.innerHTML = "";

    try {
        const res = await fetch('/api/company-analysis', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(window.currentDrawerData || {})
        });
        const data = await res.json();

        const labels = {
            baler: "Baler",
            mrf: "MRF",
            transfer_station: "Transfer Station",
            loading_ramp: "Loading Ramp",
            weighbridge: "Weighbridge",
            walking_floor: "Walking Floor",
            containers: "Containers",
            shredder: "Shredder",
            sorteerinstallatie: "Sorteerinstallatie"
        };

        let html = "";
        for (const key in labels) {
            const pct = data[key] || 0;
            html += `
                <div style="margin-bottom:8px;">
                    <div style="display:flex;justify-content:space-between;font-size:13px;">
                        <span>${labels[key]}</span><span>${pct}%</span>
                    </div>
                    <div style="background:#e2e8f0;border-radius:4px;height:6px;overflow:hidden;">
                        <div style="background:#2563eb;height:100%;width:${pct}%;"></div>
                    </div>
                </div>`;
        }
        resultsDiv.innerHTML = html;

    } catch (err) {
        resultsDiv.innerHTML = "<p>Er ging iets mis bij de analyse.</p>";
        console.error(err);
    }

    btn.disabled = false;
    btn.innerText = "AI Analyseren";
}
async function laadNotities() {
    const bedrijf = window.currentDrawerData.naam;
    const lijstDiv = document.getElementById("notitiesLijst");
    if (!lijstDiv) return;
    lijstDiv.innerHTML = "<p style='font-size:13px;color:#94a3b8;'>Laden...</p>";
    try {
        const res = await fetch("/api/notities?bedrijf=" + encodeURIComponent(bedrijf));
        const notities = await res.json();
        if (notities.length === 0) {
            lijstDiv.innerHTML = "<p style='font-size:13px;color:#94a3b8;'>Nog geen notities.</p>";
            return;
        }
        let html = "";
        notities.forEach(n => {
            const badge = n.type === "team" ? "🟢 Team" : "🔒 Privé";
            html += `
                <div style="background:#f8fafc;border-radius:6px;padding:8px 10px;margin-bottom:6px;font-size:13px;">
                    <div style="color:#334155;">${n.tekst}</div>
                    <div style="color:#94a3b8;font-size:11px;margin-top:4px;">${badge} · ${n.timestamp}</div>
                </div>`;
        });
        lijstDiv.innerHTML = html;
    } catch (err) {
        lijstDiv.innerHTML = "<p style='font-size:13px;color:#ef4444;'>Kon notities niet laden.</p>";
    }
}

async function voegNotitieToe() {
    const input = document.getElementById("notitieInput");
    const tekst = input.value.trim();
    if (!tekst) return;
    const type_ = document.querySelector('input[name="notitieType"]:checked').value;
    const bedrijf = window.currentDrawerData.naam;

    try {
        await fetch("/api/notities", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({bedrijf: bedrijf, tekst: tekst, type: type_})
        });
        input.value = "";
        laadNotities();
    } catch (err) {
        alert("Er ging iets mis bij het opslaan.");
    }
}
async function laadStatus() {
    const bedrijf = window.currentDrawerData.naam;
    const select = document.getElementById("statusSelect");
    if (!select) return;
    try {
        const res = await fetch("/api/status?bedrijf=" + encodeURIComponent(bedrijf));
        const data = await res.json();
        select.value = data.status || "";
    } catch (err) {
        console.error(err);
    }
}

async function wijzigStatus() {
    const bedrijf = window.currentDrawerData.naam;
    const select = document.getElementById("statusSelect");
    const nieuweStatus = select.value;
    try {
        await fetch("/api/status", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({bedrijf: bedrijf, status: nieuweStatus})
        });
    } catch (err) {
        alert("Er ging iets mis bij het opslaan van de status.");
    }
}
async function laadMeldingenBadge() {
    try {
        const res = await fetch("/api/meldingen");
        const meldingen = await res.json();
        const ongelezen = meldingen.filter(m => !m.gelezen).length;
        const badge = document.getElementById("meldingBadge");
        if (ongelezen > 0) {
            badge.style.display = "flex";
            badge.innerText = ongelezen;
        } else {
            badge.style.display = "none";
        }
    } catch (err) { console.error(err); }
}

async function toonMeldingen() {
    const paneel = document.getElementById("meldingenPaneel");
    const lijstDiv = document.getElementById("meldingenLijst");
    const isOpen = paneel.style.display === "block";
    paneel.style.display = isOpen ? "none" : "block";
    if (isOpen) return;

    try {
        const res = await fetch("/api/meldingen");
        const meldingen = await res.json();
        if (meldingen.length === 0) {
            lijstDiv.innerHTML = "<p style='font-size:13px;color:#94a3b8;'>Geen meldingen.</p>";
            return;
        }
        let html = "";
        meldingen.slice().reverse().forEach(m => {
            html += `
                <div style="background:${m.gelezen ? '#f8fafc' : '#eff6ff'};border-radius:6px;padding:8px 10px;margin-bottom:6px;font-size:13px;cursor:pointer;" onclick="markeerGelezen('${m.id}')">
                    <div style="color:#334155;">${m.tekst}</div>
                    <div style="color:#94a3b8;font-size:11px;margin-top:4px;">van ${m.van} · ${m.bedrijf || ''} · ${m.timestamp}</div>
                </div>`;
        });
        lijstDiv.innerHTML = html;
    } catch (err) { console.error(err); }
    laadMeldingenBadge();
}

async function markeerGelezen(id) {
    await fetch("/api/meldingen/" + id + "/lezen", {method: "POST"});
    toonMeldingen();
    laadMeldingenBadge();
}

laadMeldingenBadge();
setInterval(laadMeldingenBadge, 30000);
async function vulMeldingDropdowns() {
    try {
        const res = await fetch("/api/gebruikers");
        const gebruikers = await res.json();
        const teams = [...new Set(gebruikers.map(g => g.team).filter(t => t))];
        document.querySelectorAll("#meldingOntvanger").forEach(select => {
            let html = "<option value=''>Kies persoon/team...</option>";
            if (teams.length) {
                html += "<optgroup label='Teams'>";
                teams.forEach(t => html += `<option value='team:${t}'>Team: ${t}</option>`);
                html += "</optgroup>";
            }
            html += "<optgroup label='Personen'>";
            gebruikers.forEach(g => html += `<option value='persoon:${g.gebruikersnaam}'>${g.gebruikersnaam}</option>`);
            html += "</optgroup>";
            select.innerHTML = html;
        });
    } catch (err) { console.error(err); }
}

async function stuurMelding() {
    const selects = document.querySelectorAll("#meldingOntvanger");
    const inputs = document.querySelectorAll("#meldingTekst");
    let select, input;
    selects.forEach((s, i) => { if (s.offsetParent !== null) { select = s; input = inputs[i]; } });
    if (!select || !input) return;

    const keuze = select.value;
    const tekst = input.value.trim();
    if (!keuze || !tekst) return;

    const [type, waarde] = keuze.split(":");
    const bedrijf = window.currentDrawerData.naam;

    try {
        await fetch("/api/meldingen", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                tekst: tekst,
                bedrijf: bedrijf,
                voor_team: type === "team" ? waarde : "",
                voor_gebruiker: type === "persoon" ? waarde : ""
            })
        });
        input.value = "";
        select.value = "";
        alert("Melding verstuurd!");
    } catch (err) {
        alert("Er ging iets mis.");
    }
}
async function toonFabriekAnalyse(fabriekNaam) {
if (window.actieveRelatieLijnen) {
        window.actieveRelatieLijnen.forEach(lijn => kaart.removeLayer(lijn));
    }
    window.actieveRelatieLijnen = [];
    const paneel = document.getElementById("fabriekAnalysePaneel");
    const titel = document.getElementById("fabriekAnalyseTitel");
    const lijstDiv = document.getElementById("fabriekAnalyseLijst");
    paneel.style.display = "block";
    titel.innerText = "🏭 " + fabriekNaam;
    lijstDiv.innerHTML = "<p style='font-size:13px;color:#94a3b8;'>Laden...</p>";

    try {
        const res = await fetch("/api/fabriek-analyse?fabriek=" + encodeURIComponent(fabriekNaam));
        const resultaten = await res.json();
        if (resultaten.error) {
            lijstDiv.innerHTML = "<p style='font-size:13px;color:#ef4444;'>" + resultaten.error + "</p>";
            return;
        }
        if (resultaten.length === 0) {
            lijstDiv.innerHTML = "<p style='font-size:13px;color:#94a3b8;'>Geen passende leveranciers gevonden.</p>";
            return;
        }
        let html = "";
        resultaten.forEach((r, i) => {
            html += `
                <div style="background:#f8fafc;border-radius:8px;padding:10px;margin-bottom:8px;font-size:13px;">
                    <div style="font-weight:600;color:#1e293b;">${i+1}. ${r.naam}</div>
                    <div style="color:#64748b;font-size:12px;margin-top:2px;">${r.regio}, ${r.land}</div>
                    <div style="display:flex;justify-content:space-between;margin-top:6px;">
                        <span style="background:#dbeafe;color:#1d4ed8;padding:2px 8px;border-radius:4px;font-size:11px;">${r.gedeelde_materialen}</span>
                        <span style="font-weight:700;color:#ea580c;">${r.afstand_km} km</span>
                    </div>
                </div>`;
        });
        lijstDiv.innerHTML = html;
        const fabriek = {{ papierfabrieken|tojson }}.find(f => f.naam === fabriekNaam);
        if (fabriek) {
            resultaten.slice(0, 10).forEach(r => {
                const leverancier = {{ bedrijven|tojson if bedrijven else '[]' }}.find(b => b.naam === r.naam);
                if (leverancier) {
                    const kleur = r.afstand_km < 50 ? "#16a34a" : r.afstand_km < 150 ? "#2563eb" : "#94a3b8";
                    const dikte = Math.max(1, 5 - Math.floor(r.afstand_km / 100));
                    const lijn = L.polyline(
                        [[fabriek.lat, fabriek.lon], [leverancier.lat, leverancier.lon]],
                        {color: kleur, weight: dikte, opacity: 0.6, dashArray: r.afstand_km > 150 ? "6,6" : null}
                    ).addTo(kaart);
                    window.actieveRelatieLijnen.push(lijn);
                }
            });
        }
    } catch (err) {
        lijstDiv.innerHTML = "<p style='font-size:13px;color:#ef4444;'>Er ging iets mis.</p>";
        console.error(err);
    }
}

async function laadTransport() {
    const lat = window.currentDrawerData.lat;
    const lon = window.currentDrawerData.lon;
    const div = document.getElementById("transportInfo");
    if (!div) return;
    if (!lat || !lon) { div.innerHTML = ""; return; }

    try {
        const res = await fetch("/api/transport?lat=" + lat + "&lon=" + lon);
        const data = await res.json();
        const forwarders = Object.keys(data);
        if (forwarders.length === 0) {
            div.innerHTML = "";
            return;
        }

        const alleBestemmingen = [...new Set(forwarders.flatMap(fw => Object.keys(data[fw].tarieven)))].sort();

        let html = "<hr class='drawer-divider'><div class='drawer-section-title'>Logistiek</div>";
        html += "<div style='font-size:11px;color:#94a3b8;margin-bottom:6px;'>";
        html += forwarders.map(fw => `${fw}: nabij ${data[fw].stad} (${data[fw].afstand} km)`).join(" · ");
        html += "</div>";
        html += "<div style='overflow-x:auto;'><table style='width:100%;border-collapse:collapse;font-size:12px;'>";
        html += "<tr><th style='text-align:left;padding:6px 8px;color:#94a3b8;font-weight:600;border-bottom:1px solid #e2e8f0;'>Bestemming</th>";
        forwarders.forEach(fw => {
            html += `<th style='text-align:right;padding:6px 8px;color:#94a3b8;font-weight:600;border-bottom:1px solid #e2e8f0;'>${fw}</th>`;
        });
        html += "</tr>";

        alleBestemmingen.forEach(bestemming => {
            const prijzen = forwarders.map(fw => {
                const ruw = data[fw].tarieven[bestemming];
                const getal = ruw ? parseFloat(String(ruw).replace(/[^0-9.]/g, "")) : null;
                return { fw, ruw, getal };
            });
            const geldig = prijzen.filter(p => p.getal !== null && !isNaN(p.getal));
            const laagste = geldig.length ? Math.min(...geldig.map(p => p.getal)) : null;

            html += `<tr><td style='padding:6px 8px;color:#334155;border-bottom:1px solid #f1f5f9;'>${bestemming}</td>`;
            prijzen.forEach(p => {
                const isLaagste = p.getal === laagste && geldig.length > 1;
                const stijl = isLaagste
                    ? "font-weight:700;color:#16a34a;background:#f0fdf4;"
                    : "color:#64748b;";
                html += `<td style='text-align:right;padding:6px 8px;border-bottom:1px solid #f1f5f9;${stijl}'>${p.ruw || "—"}</td>`;
            });
            html += "</tr>";
        });

        html += "</table></div>";
        div.innerHTML = html;
    } catch (err) {
        console.error(err);
    }
}

async function laadFotos() {
    const bedrijf = window.currentDrawerData.naam;
    const lijstDiv = document.getElementById("fotosLijst");
    if (!lijstDiv) return;
    try {
        const res = await fetch("/api/fotos?bedrijf=" + encodeURIComponent(bedrijf));
        const fotos = await res.json();
        let html = "";
        fotos.forEach(f => {
            html += `<img src="/fotos_uploads/${f.bestandsnaam}" style="width:70px;height:70px;object-fit:cover;border-radius:6px;border:1px solid #e2e8f0;cursor:pointer;" onclick="window.open('/fotos_uploads/${f.bestandsnaam}', '_blank')" title="Door ${f.geupload_door} op ${f.timestamp}">`;
        });
        lijstDiv.innerHTML = html;
    } catch (err) {
        console.error(err);
    }
}

async function uploadFoto() {
    const input = document.getElementById("fotoInput");
    const bestand = input.files[0];
    if (!bestand) return;

    const formData = new FormData();
    formData.append("bedrijf", window.currentDrawerData.naam);
    formData.append("foto", bestand);

    try {
        const res = await fetch("/api/fotos", { method: "POST", body: formData });
        const data = await res.json();
        if (data.error) {
            alert(data.error);
        } else {
            laadFotos();
        }
    } catch (err) {
        alert("Er ging iets mis bij het uploaden.");
    }
    input.value = "";
}
function closeDrawer() {
    document.getElementById("overlay").style.display = "none";
    document.getElementById("drawer").classList.remove("open");
}
async function toggleOpslaan(event, naam, el) {
    event.stopPropagation();
    try {
        const res = await fetch("/api/opgeslagen", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({naam: naam})
        });
        const data = await res.json();
        el.textContent = data.opgeslagen ? "★" : "☆";
        el.classList.toggle("opgeslagen", data.opgeslagen);
    } catch (err) {
        console.error(err);
    }
}
</script>

</div>

</body>
</html>
'''

LOGIN_HTML = '''
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>Inloggen — RecycleFind</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: "Inter", -apple-system, sans-serif;
            background: radial-gradient(circle at 20% 10%, #fff7ed 0%, #f8fafc 45%, #f1f5f9 100%);
            min-height: 100vh; display: flex; align-items: center; justify-content: center; margin: 0;
            padding: 20px;
        }
        .box {
            background: #fff; padding: 44px 40px; border-radius: 20px; width: 100%; max-width: 360px;
            box-shadow: 0 24px 60px rgba(15,23,42,0.08), 0 2px 8px rgba(15,23,42,0.04);
            border: 1px solid #f1f5f9;
        }
        .logo { font-size: 1.4rem; font-weight: 800; color: #0f172a; letter-spacing: -0.5px; margin-bottom: 4px; }
        .logo em { color: #ea580c; font-style: normal; }
        .sub { font-size: 0.82rem; color: #94a3b8; margin-bottom: 28px; }
        label { display: block; font-size: 0.75rem; font-weight: 600; color: #475569; margin-bottom: 6px; margin-top: 14px; }
        label:first-of-type { margin-top: 0; }
        input {
            width: 100%; padding: 11px 13px; border: 1px solid #e2e8f0; border-radius: 8px;
            font-size: 14px; font-family: inherit; outline: none; transition: all 0.15s ease;
        }
        input:focus { border-color: #fb923c; box-shadow: 0 0 0 3px rgba(251,146,60,0.15); }
        button {
            width: 100%; padding: 12px; background: linear-gradient(135deg, #f97316, #ea580c); color: white;
            border: none; border-radius: 8px; font-size: 14px; font-weight: 700; font-family: inherit;
            cursor: pointer; margin-top: 22px; transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        button:hover { box-shadow: 0 8px 20px rgba(234,88,12,0.3); transform: translateY(-1px); }
        .fout { background: #fef2f2; color: #dc2626; font-size: 0.8rem; padding: 10px 12px; border-radius: 8px; margin-bottom: 16px; border: 1px solid #fecaca; }
    </style>
</head>
<body>
    <div class="box">
        <div class="logo">Recycle<em>Find</em></div>
        <div class="sub">Global Recycling Intelligence Platform</div>
        {% if fout %}<div class="fout">{{ fout }}</div>{% endif %}
        <form method="POST">
            <label>Gebruikersnaam</label>
            <input type="text" name="gebruikersnaam" placeholder="jouw.naam" required autofocus>
            <label>Wachtwoord</label>
            <input type="password" name="wachtwoord" placeholder="••••••••" required>
            <button type="submit">Inloggen →</button>
        </form>
    </div>
</body>
</html>
'''

@app.route("/login", methods=["GET", "POST"])
def login():
    fout = None
    if request.method == "POST":
        gebruikersnaam = request.form.get("gebruikersnaam", "")
        wachtwoord = request.form.get("wachtwoord", "")
        users = laad_users()
        if gebruikersnaam in users and check_password_hash(users[gebruikersnaam]["wachtwoord"], wachtwoord):
            session["ingelogd"] = True
            session["gebruikersnaam"] = gebruikersnaam
            session["team"] = users[gebruikersnaam].get("team", "")
            return redirect(url_for("index"))
        else:
            fout = "Onjuiste gebruikersnaam of wachtwoord."
    return render_template_string(LOGIN_HTML, fout=fout)

@app.route("/export-csv")
def export_csv():
    import csv
    import io

    zoekterm = request.args.get("zoekterm", "").lower()
    land     = request.args.get("land", "")
    regio    = request.args.get("regio", "")
    klanttype = request.args.get("klanttype", "")
    materiaal = request.args.get("materiaal", "")
    brontype  = request.args.get("brontype", "")

    bedrijven = ENF_BEDRIJVEN
    if zoekterm:  bedrijven = [b for b in bedrijven if zoekterm in b["naam"].lower()]
    if land:      bedrijven = [b for b in bedrijven if b.get("land","").strip().lower() == land.strip().lower()]
    if regio:     bedrijven = [b for b in bedrijven if b.get("regio","").strip().lower() == regio.strip().lower()]
    if klanttype: bedrijven = [b for b in bedrijven if klanttype.strip().lower() in b.get("klanttype","").lower()]
    if materiaal: bedrijven = [b for b in bedrijven if materiaal.strip().lower() in b.get("materialen","").lower()]
    if brontype:  bedrijven = [b for b in bedrijven if b.get("brontype","").strip().lower() == brontype.strip().lower()]

    output = io.StringIO()
    schrijver = csv.writer(output)
    schrijver.writerow(["Naam", "Land", "Stad/Regio", "Bedrijfstype", "Materialen", "Klanttype", "Volume (t/jaar)",
                         "Adres", "Telefoonnummer", "Certificeringen", "Website"])
    for b in bedrijven:
        schrijver.writerow([
            b.get("naam",""), b.get("land",""), b.get("regio",""), b.get("brontype",""),
            b.get("materialen",""), b.get("klanttype",""), b.get("volume",""),
            b.get("adres",""), b.get("telefoon",""), b.get("certificeringen",""), b.get("url",""),
        ])

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=recyclefind_export.csv"}
    )

@app.route("/export-data")
def export_data():
    from flask import Response
    pakket = {
        "bedrijven": ENF_BEDRIJVEN,
        "papierfabrieken": PAPIERFABRIEKEN,
    }
    return Response(
        json.dumps(pakket, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=live_data_export.json"}
    )

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
@app.route("/api/fabriek-analyse", methods=["GET"])
def fabriek_analyse():
    naam = request.args.get("fabriek", "")
    fabriek = next((f for f in PAPIERFABRIEKEN if f["naam"] == naam), None)
    if not fabriek or "lat" not in fabriek:
        return jsonify({"error": "Fabriek niet gevonden"}), 404

    fabriek_materialen = [m.strip().lower() for m in fabriek.get("materialen", "").split(",")]

    resultaten = []
    for b in ENF_BEDRIJVEN:
        if "lat" not in b or "lon" not in b:
            continue
        bedrijf_materialen = [m.strip().lower() for m in b.get("materialen", "").split(",")]
        gedeeld = [m for m in fabriek_materialen if m in bedrijf_materialen]
        if not gedeeld:
            continue
        afstand = bereken_afstand_km(fabriek["lat"], fabriek["lon"], b["lat"], b["lon"])
        resultaten.append({
            "naam": b["naam"],
            "land": b["land"],
            "regio": b["regio"],
            "materialen": b.get("materialen", ""),
            "gedeelde_materialen": ", ".join(gedeeld),
            "afstand_km": round(afstand, 1)
        })

    resultaten.sort(key=lambda x: x["afstand_km"])
    return jsonify(resultaten[:25])
@app.route("/api/fotos", methods=["GET"])
def get_fotos():
    bedrijf = request.args.get("bedrijf", "")
    alle = laad_fotos()
    return jsonify(alle.get(bedrijf, []))

@app.route("/api/fotos", methods=["POST"])
def upload_foto():
    bedrijf = request.form.get("bedrijf", "")
    bestand = request.files.get("foto")

    if not bedrijf or not bestand:
        return jsonify({"error": "Bedrijf en foto zijn verplicht"}), 400

    if not os.path.exists(FOTOS_MAP):
        os.makedirs(FOTOS_MAP)

    extensie = bestand.filename.rsplit(".", 1)[-1].lower()
    if extensie not in ["jpg", "jpeg", "png", "gif", "webp"]:
        return jsonify({"error": "Alleen afbeeldingen toegestaan (jpg, png, gif, webp)"}), 400

    bestandsnaam = f"{uuid.uuid4()}.{extensie}"
    pad = os.path.join(FOTOS_MAP, bestandsnaam)
    bestand.save(pad)

    alle = laad_fotos()
    if bedrijf not in alle:
        alle[bedrijf] = []
    alle[bedrijf].append({
        "bestandsnaam": bestandsnaam,
        "geupload_door": session.get("gebruikersnaam", ""),
        "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
    })
    bewaar_fotos(alle)

    return jsonify({"ok": True, "bestandsnaam": bestandsnaam})

from flask import send_from_directory

@app.route("/fotos_uploads/<bestandsnaam>")
def get_foto_bestand(bestandsnaam):
    return send_from_directory(FOTOS_MAP, bestandsnaam)
@app.route("/api/gebruikers", methods=["GET"])
def get_gebruikers():
    users = laad_users()
    lijst = [{"gebruikersnaam": naam, "team": info.get("team", "")} for naam, info in users.items()]
    return jsonify(lijst)

@app.route("/api/meldingen", methods=["GET"])
def get_meldingen():
    gebruiker = session.get("gebruikersnaam", "")
    team = session.get("team", "")
    alle = laad_meldingen()
    van_mij = [m for m in alle if m["voor_gebruiker"] == gebruiker or (m["voor_team"] and m["voor_team"] == team)]
    return jsonify(van_mij)

@app.route("/api/meldingen", methods=["POST"])
def add_melding():
    data = request.get_json()
    tekst = data.get("tekst", "").strip()
    bedrijf = data.get("bedrijf", "")
    voor_gebruiker = data.get("voor_gebruiker", "")
    voor_team = data.get("voor_team", "")
    van = session.get("gebruikersnaam", "")

    if not tekst or (not voor_gebruiker and not voor_team):
        return jsonify({"error": "Tekst en ontvanger zijn verplicht"}), 400

    alle = laad_meldingen()
    nieuwe = {
        "id": str(uuid.uuid4()),
        "tekst": tekst,
        "bedrijf": bedrijf,
        "van": van,
        "voor_gebruiker": voor_gebruiker,
        "voor_team": voor_team,
        "gelezen": False,
        "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
    }
    alle.append(nieuwe)
    bewaar_meldingen(alle)
    return jsonify(nieuwe)

@app.route("/api/meldingen/<melding_id>/lezen", methods=["POST"])
def markeer_gelezen(melding_id):
    alle = laad_meldingen()
    for m in alle:
        if m["id"] == melding_id:
            m["gelezen"] = True
    bewaar_meldingen(alle)
    return jsonify({"ok": True})
@app.route("/details")
def details():
    url = request.args.get("url", "")
    if not url or "enfpaper" not in url:
        return jsonify({})
    return jsonify(haal_bedrijf_details(url))

@app.route("/api/ai-search", methods=["POST"])
def ai_search():
    from ai_filter import parse_search_query, apply_filters

    data = request.get_json()
    query = data.get("query", "").strip()

    if not query:
        return jsonify({"error": "Geen zoekopdracht opgegeven"}), 400

    filters = parse_search_query(query)
    results = apply_filters(ENF_BEDRIJVEN, filters)

    return jsonify({
        "results": results[:200],
        "total": len(results),
        "detected_filters": filters,
    })
@app.route("/api/transport", methods=["GET"])
def get_transport():
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    return jsonify(vind_transport_tarieven_dichtbij(lat, lon))

@app.route("/api/status", methods=["GET"])
def get_status():
    bedrijf = request.args.get("bedrijf", "")
    alle = laad_status()
    return jsonify({"status": alle.get(bedrijf, "")})

@app.route("/api/status", methods=["POST"])
def set_status():
    data = request.get_json()
    bedrijf = data.get("bedrijf", "")
    nieuwe_status = data.get("status", "")
    if not bedrijf:
        return jsonify({"error": "Bedrijf is verplicht"}), 400
    alle = laad_status()
    alle[bedrijf] = nieuwe_status
    bewaar_status(alle)
    return jsonify({"status": nieuwe_status})
@app.route("/api/notities", methods=["GET"])
def get_notities():
    bedrijf = request.args.get("bedrijf", "")
    user_id = get_user_id()
    alle = laad_notities()
    lijst = alle.get(bedrijf, [])
    zichtbaar = [n for n in lijst if n["type"] == "team" or n["user_id"] == user_id]
    return jsonify(zichtbaar)

@app.route("/api/notities", methods=["POST"])
def add_notitie():
    data = request.get_json()
    bedrijf = data.get("bedrijf", "")
    tekst = data.get("tekst", "").strip()
    type_ = data.get("type", "team")
    user_id = get_user_id()

    if not bedrijf or not tekst:
        return jsonify({"error": "Bedrijf en tekst zijn verplicht"}), 400

    alle = laad_notities()
    if bedrijf not in alle:
        alle[bedrijf] = []

    nieuwe_notitie = {
        "tekst": tekst,
        "type": type_,
        "user_id": user_id,
        "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
    }
    alle[bedrijf].append(nieuwe_notitie)
    bewaar_notities(alle)

    return jsonify(nieuwe_notitie)
@app.route("/api/company-analysis", methods=["POST"])
def company_analysis():
    from ai_filter import analyseer_uitrusting

    data = request.get_json()
    resultaat = analyseer_uitrusting(data)

    return jsonify(resultaat)

PAGINA_GROOTTE = 200

@app.route("/", methods=["GET", "POST"])
def index():
    zoekterm = land = regio = klanttype = materiaal = brontype = ""
    pagina = 1

    if request.method == "POST":
        zoekterm = request.form.get("zoekterm", "").lower()
        land     = request.form.get("land", "")
        regio    = request.form.get("regio", "")
        klanttype = request.form.get("klanttype", "")
        materiaal = request.form.get("materiaal", "")
        brontype  = request.form.get("brontype", "")
        pagina    = request.form.get("pagina", "1")
    else:
        zoekterm = request.args.get("zoekterm", "").lower()
        land     = request.args.get("land", "")
        regio    = request.args.get("regio", "")
        klanttype = request.args.get("klanttype", "")
        materiaal = request.args.get("materiaal", "")
        brontype  = request.args.get("brontype", "")
        pagina    = request.args.get("pagina", "1")

    try:
        pagina = max(1, int(pagina))
    except (TypeError, ValueError):
        pagina = 1

    bedrijven = ENF_BEDRIJVEN
    if zoekterm:  bedrijven = [b for b in bedrijven if zoekterm in b["naam"].lower()]
    if land:      bedrijven = [b for b in bedrijven if b.get("land","").strip().lower() == land.strip().lower()]
    if regio:     bedrijven = [b for b in bedrijven if b.get("regio","").strip().lower() == regio.strip().lower()]
    if klanttype: bedrijven = [b for b in bedrijven if klanttype.strip().lower() in b.get("klanttype","").lower()]
    if materiaal: bedrijven = [b for b in bedrijven if materiaal.strip().lower() in b.get("materialen","").lower()]
    if brontype:  bedrijven = [b for b in bedrijven if b.get("brontype","").strip().lower() == brontype.strip().lower()]

    totaal_gevonden = len(bedrijven)
    er_is_gefilterd = bool(zoekterm or land or regio or klanttype or materiaal or brontype)
    totaal_paginas = max(1, (totaal_gevonden + PAGINA_GROOTTE - 1) // PAGINA_GROOTTE)
    pagina = min(pagina, totaal_paginas)
    start = (pagina - 1) * PAGINA_GROOTTE
    bedrijven = bedrijven[start:start + PAGINA_GROOTTE]
    opgeslagen_namen = set(laad_opgeslagen())

    def maak_pagina_url(p):
        params = {"zoekterm": zoekterm, "land": land, "regio": regio, "klanttype": klanttype,
                   "materiaal": materiaal, "brontype": brontype, "pagina": p}
        params = {k: v for k, v in params.items() if v}
        return "/?" + "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())

    export_params = {"zoekterm": zoekterm, "land": land, "regio": regio, "klanttype": klanttype,
                      "materiaal": materiaal, "brontype": brontype}
    export_params = {k: v for k, v in export_params.items() if v}
    export_query = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in export_params.items())

    return render_template_string(HTML,
        bedrijven=bedrijven, zoekterm=zoekterm, land=land, regio=regio,
        klanttype=klanttype, materiaal=materiaal, brontype=brontype,
        totaal=len(ENF_BEDRIJVEN), landen=LANDEN,
        totaal_gevonden=totaal_gevonden, regio_per_land=REGIO_PER_LAND,
        papierfabrieken=PAPIERFABRIEKEN, opgeslagen_namen=opgeslagen_namen,
        er_is_gefilterd=er_is_gefilterd, pagina=pagina, totaal_paginas=totaal_paginas,
        maak_pagina_url=maak_pagina_url, export_query=export_query)

OPGESLAGEN_FILE = datapad("opgeslagen.json")

def laad_opgeslagen():
    try:
        with open(OPGESLAGEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def bewaar_opgeslagen(data):
    with open(OPGESLAGEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.route("/api/opgeslagen", methods=["GET"])
def get_opgeslagen():
    return jsonify(laad_opgeslagen())

@app.route("/api/opgeslagen", methods=["POST"])
def toggle_opgeslagen():
    data = request.get_json()
    naam = data.get("naam", "")
    if not naam:
        return jsonify({"error": "Naam is verplicht"}), 400
    lijst = laad_opgeslagen()
    if naam in lijst:
        lijst.remove(naam)
        opgeslagen = False
    else:
        lijst.append(naam)
        opgeslagen = True
    bewaar_opgeslagen(lijst)
    return jsonify({"opgeslagen": opgeslagen})

SNAPSHOTS_FILE = datapad("snapshots.json")

def laad_snapshots():
    try:
        with open(SNAPSHOTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def maak_dagelijkse_snapshot():
    vandaag = datetime.date.today().isoformat()
    snapshots = laad_snapshots()
    if snapshots and snapshots[-1]["datum"] == vandaag:
        return snapshots
    status_alle = laad_status()
    nieuw = {
        "datum": vandaag,
        "totaal": len(ENF_BEDRIJVEN),
        "landen": len(LANDEN),
        "klant": sum(1 for s in status_alle.values() if s == "klant"),
        "potentie": sum(1 for s in status_alle.values() if s == "potentie"),
        "in_proces": sum(1 for s in status_alle.values() if s == "in_proces"),
    }
    snapshots.append(nieuw)
    snapshots = snapshots[-365:]
    with open(SNAPSHOTS_FILE, "w", encoding="utf-8") as f:
        json.dump(snapshots, f, ensure_ascii=False, indent=2)
    return snapshots

def bepaal_continent(land):
    land = (land or "").strip()
    europa = {"Netherlands","Germany","Belgium","France","United Kingdom","Spain","Italy","Portugal","Austria","Switzerland","Poland","Czech Republic","Hungary","Sweden","Norway","Finland","Denmark","Ireland","Greece","Romania","Bulgaria","Croatia","Slovenia","Slovakia","Ukraine","Belarus","Estonia","Latvia","Lithuania","Luxembourg","Serbia","Bosnia and Herzegovina","Iceland","Malta","Cyprus"}
    azie = {"China","Japan","South Korea","India","Indonesia","Vietnam","Thailand","Malaysia","Philippines","Singapore","Taiwan","Pakistan","Bangladesh","Saudi Arabia","United Arab Emirates","Turkey","Israel","Hong Kong"}
    n_amerika = {"United States","Canada","Mexico"}
    z_amerika = {"Brazil","Argentina","Chile","Colombia","Peru","Uruguay","Paraguay","Ecuador","Bolivia"}
    afrika = {"South Africa","Egypt","Nigeria","Kenya","Morocco","Ghana","Tunisia"}
    if land in europa: return "Europa"
    if land in azie: return "Azië"
    if land in n_amerika: return "Noord-Amerika"
    if land in z_amerika: return "Zuid-Amerika"
    if land in afrika: return "Afrika"
    return "Overig"

@app.route("/dashboard")
def dashboard():
    snapshots = maak_dagelijkse_snapshot()
    groei_pct = None
    groei_periode = None
    if len(snapshots) >= 2:
        eerste = snapshots[0]
        laatste = snapshots[-1]
        if eerste["totaal"] > 0:
            groei_pct = round((laatste["totaal"] - eerste["totaal"]) / eerste["totaal"] * 100, 1)
            groei_periode = eerste["datum"]

    status_alle = laad_status()
    aantal_klant = sum(1 for s in status_alle.values() if s == "klant")
    aantal_potentie = sum(1 for s in status_alle.values() if s == "potentie")
    aantal_proces = sum(1 for s in status_alle.values() if s == "in_proces")
    aantal_geen = sum(1 for s in status_alle.values() if s == "geen_interesse")
    status_totaal = max(aantal_klant + aantal_potentie + aantal_proces + aantal_geen, 1)

    per_materiaal = {}
    per_continent = {}
    per_continent_materiaal = {}
    for b in ENF_BEDRIJVEN:
        continent = bepaal_continent(b.get("land",""))
        per_continent[continent] = per_continent.get(continent, 0) + 1
        per_continent_materiaal.setdefault(continent, {})
        for m in [x.strip() for x in b.get("materialen", "").split(",") if x.strip()]:
            per_materiaal[m] = per_materiaal.get(m, 0) + 1
            per_continent_materiaal[continent][m] = per_continent_materiaal[continent].get(m, 0) + 1

    top_materialen = sorted(per_materiaal.items(), key=lambda x: -x[1])[:5]
    max_materiaal = max([a for _, a in top_materialen], default=1)

    # Donut-chart data: top 4 materialen + "Overig"
    donut_bron = sorted(per_materiaal.items(), key=lambda x: -x[1])
    donut_top4 = donut_bron[:4]
    donut_overig = sum(a for _, a in donut_bron[4:])
    donut_totaal = max(sum(a for _, a in donut_top4) + donut_overig, 1)
    donut_kleuren = ["#fbbf24", "#f97316", "#ea580c", "#c2410c", "#5c4326"]
    donut_segmenten = []
    cursor = 0
    for i, (naam, aantal) in enumerate(donut_top4 + ([("Overig", donut_overig)] if donut_overig else [])):
        pct = aantal / donut_totaal * 100
        donut_segmenten.append({"naam": naam, "aantal": aantal, "pct": round(pct,1), "van": round(cursor,2), "tot": round(cursor+pct,2), "kleur": donut_kleuren[i % len(donut_kleuren)]})
        cursor += pct

    # Regionaal intelligence: top 3 continenten
    top_continenten = sorted(per_continent.items(), key=lambda x: -x[1])[:3]
    regio_kaarten = []
    for naam, aantal in top_continenten:
        top_mat = sorted(per_continent_materiaal.get(naam, {}).items(), key=lambda x: -x[1])[:3]
        activiteit = "Hoog" if aantal > status_totaal else ("Gemiddeld" if aantal > status_totaal/3 else "Laag")
        regio_kaarten.append({"naam": naam, "aantal": aantal, "materialen": [m for m,_ in top_mat], "activiteit": activiteit})

    volume_klant = 0
    for b in ENF_BEDRIJVEN:
        if status_alle.get(b["naam"]) == "klant":
            try:
                volume_klant += float(str(b.get("volume","0")).replace(",",""))
            except:
                pass

    alle_meldingen = laad_meldingen()
    openstaand = [m for m in alle_meldingen if not m.get("gelezen")]
    openstaand = sorted(openstaand, key=lambda x: x.get("timestamp",""), reverse=True)[:8]

    kaart_bedrijven = [
        {"naam": b["naam"], "lat": b["lat"], "lon": b["lon"], "status": status_alle.get(b["naam"], "")}
        for b in ENF_BEDRIJVEN if b.get("lat") and b.get("lon")
    ][:1500]

    inhoud = """
<div class="dash-donker-wrap">
<style>
.dash-donker-wrap {
    background: var(--gray-50);
    margin:-32px -40px; padding:32px 40px; min-height:calc(100vh - 64px); color:var(--gray-800);
}
.dash-donker-wrap .page-title { color:var(--gray-900); font-weight:800; letter-spacing:-0.5px; }
.dg-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:16px; margin-bottom:24px; }
.dg-kaart {
    background: #fff;
    border: 1px solid var(--gray-200);
    border-radius: 18px;
    padding: 22px;
    box-shadow: var(--shadow-sm);
    transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}
.dg-kaart:hover { transform: translateY(-2px); border-color: var(--brand-300); box-shadow: var(--shadow-md); }
.dg-icoon { font-size:1.3rem; margin-bottom:10px; opacity:0.9; }
.dg-getal { font-size:2.1rem; font-weight:800; letter-spacing:-1px; background:linear-gradient(90deg,var(--brand-600),var(--brand-500)); -webkit-background-clip:text; background-clip:text; color:transparent; }
.dg-label { font-size:0.72rem; color:var(--gray-400); text-transform:uppercase; letter-spacing:1.2px; margin-top:6px; font-weight:600; }
.dg-kaart-titel { font-size:0.78rem; color:var(--gray-400); text-transform:uppercase; letter-spacing:1.2px; margin-bottom:18px; font-weight:700; display:flex; align-items:center; gap:8px; }
.dg-bar-rij { display:flex; align-items:center; gap:10px; margin-bottom:13px; font-size:0.82rem; }
.dg-bar-label { width:110px; color:var(--gray-600); flex-shrink:0; }
.dg-bar-track { flex:1; background:var(--gray-100); border-radius:6px; height:9px; overflow:hidden; }
.dg-bar-fill { background:linear-gradient(90deg,var(--brand-500),var(--brand-700)); height:100%; border-radius:6px; }
.dg-bar-getal { width:34px; text-align:right; color:var(--brand-700); font-weight:700; }
#dashKaart { height:280px; border-radius:14px; overflow:hidden; border:1px solid var(--gray-200); }
.dg-activiteit-item { padding:11px 0; border-bottom:1px solid var(--gray-100); font-size:0.83rem; color:var(--gray-700); }
.dg-activiteit-item:last-child { border-bottom:none; }
.dg-activiteit-item small { color:var(--gray-400); display:block; margin-top:3px; }
.dg-lege { color:var(--gray-400); font-size:0.83rem; }
.dg-rij-2 { display:flex; gap:20px; flex-wrap:wrap; margin-bottom:20px; }
.dg-rij-2 > div { flex:1; min-width:280px; }
</style>

<div class="page-title">Dashboard</div>
{% if groei_pct is none %}
<p style="color:var(--gray-400);margin-top:-16px;margin-bottom:20px;font-size:0.82rem;">📈 Groeitracking is vandaag gestart — kom over een paar dagen terug voor een echt groeicijfer.</p>
{% endif %}

<div class="dg-grid">
    <div class="dg-kaart"><div class="dg-icoon">🏢</div><div class="dg-getal">{{ totaal }}</div><div class="dg-label">Bedrijven</div>{% if groei_pct is not none %}<div style="font-size:0.72rem;font-weight:700;margin-top:4px;color:{{ 'var(--green-600)' if groei_pct >= 0 else 'var(--red-500)' }};">{{ '+' if groei_pct >= 0 else '' }}{{ groei_pct }}% sinds {{ groei_periode }}</div>{% endif %}</div>
    <div class="dg-kaart"><div class="dg-icoon">🌍</div><div class="dg-getal">{{ landen|length }}</div><div class="dg-label">Landen</div></div>
    <div class="dg-kaart"><div class="dg-icoon">📦</div><div class="dg-getal">{{ volume_klant|int }}</div><div class="dg-label">t/j bij klanten</div></div>
    <div class="dg-kaart"><div class="dg-icoon">🟢</div><div class="dg-getal">{{ klant }}</div><div class="dg-label">Klant</div></div>
    <div class="dg-kaart"><div class="dg-icoon">🟡</div><div class="dg-getal">{{ potentie }}</div><div class="dg-label">Potentie</div></div>
    <div class="dg-kaart"><div class="dg-icoon">🔵</div><div class="dg-getal">{{ proces }}</div><div class="dg-label">In proces</div></div>
</div>

<div class="dg-rij-2">
    <div class="dg-kaart">
        <div class="dg-kaart-titel">Status verdeling</div>
        <div class="dg-bar-rij"><span class="dg-bar-label">🟢 Klant</span><div class="dg-bar-track"><div class="dg-bar-fill" style="width:{{ (klant/status_totaal*100)|round(1) }}%"></div></div><span class="dg-bar-getal">{{ klant }}</span></div>
        <div class="dg-bar-rij"><span class="dg-bar-label">🟡 Potentie</span><div class="dg-bar-track"><div class="dg-bar-fill" style="width:{{ (potentie/status_totaal*100)|round(1) }}%"></div></div><span class="dg-bar-getal">{{ potentie }}</span></div>
        <div class="dg-bar-rij"><span class="dg-bar-label">🔵 In proces</span><div class="dg-bar-track"><div class="dg-bar-fill" style="width:{{ (proces/status_totaal*100)|round(1) }}%"></div></div><span class="dg-bar-getal">{{ proces }}</span></div>
        <div class="dg-bar-rij"><span class="dg-bar-label">⚪ Geen interesse</span><div class="dg-bar-track"><div class="dg-bar-fill" style="width:{{ (geen/status_totaal*100)|round(1) }}%"></div></div><span class="dg-bar-getal">{{ geen }}</span></div>
    </div>
    <div class="dg-kaart">
        <div class="dg-kaart-titel">Top materialen</div>
        {% for mat, aantal in top_materialen %}
        <div class="dg-bar-rij"><span class="dg-bar-label">{{ mat }}</span><div class="dg-bar-track"><div class="dg-bar-fill" style="width:{{ (aantal/max_materiaal*100)|round(1) }}%"></div></div><span class="dg-bar-getal">{{ aantal }}</span></div>
        {% else %}
        <div class="dg-lege">Nog geen materiaaldata.</div>
        {% endfor %}
    </div>
</div>

<div class="dg-rij-2">
    <div class="dg-kaart" style="flex:1.4;">
        <div class="dg-kaart-titel">Bedrijven wereldwijd</div>
        <div id="dashKaart"></div>
    </div>
    <div class="dg-kaart">
        <div class="dg-kaart-titel">Openstaande meldingen</div>
        {% for m in openstaand %}
        <div class="dg-activiteit-item">{{ m.tekst }}<small>{{ m.bedrijf }} · van {{ m.van }} · {{ m.timestamp }}</small></div>
        {% else %}
        <div class="dg-lege">Geen openstaande meldingen.</div>
        {% endfor %}
    </div>
</div>

<div class="dg-rij-2">
    <div class="dg-kaart">
        <div class="dg-kaart-titel">Materiaalverdeling</div>
        <div style="display:flex;align-items:center;gap:20px;">
            <div style="width:130px;height:130px;border-radius:50%;flex-shrink:0;
                background:conic-gradient({% for s in donut_segmenten %}{{ s.kleur }} {{ s.van }}% {{ s.tot }}%{% if not loop.last %}, {% endif %}{% endfor %});
                box-shadow:0 0 0 1px var(--gray-200), inset 0 0 0 22px #fff;"></div>
            <div style="flex:1;">
                {% for s in donut_segmenten %}
                <div style="display:flex;align-items:center;gap:8px;font-size:0.78rem;margin-bottom:8px;color:var(--gray-700);">
                    <span style="width:10px;height:10px;border-radius:3px;background:{{ s.kleur }};flex-shrink:0;"></span>
                    {{ s.naam }} <span style="margin-left:auto;color:var(--brand-700);font-weight:700;">{{ s.pct }}%</span>
                </div>
                {% endfor %}
            </div>
        </div>
    </div>
    <div class="dg-kaart">
        <div class="dg-kaart-titel">Regionale intelligence</div>
        {% for r in regio_kaarten %}
        <div style="padding:12px 0;{% if not loop.last %}border-bottom:1px solid var(--gray-100);{% endif %}">
            <div style="display:flex;justify-content:space-between;align-items:baseline;">
                <span style="font-weight:700;color:var(--gray-900);">{{ r.naam }}</span>
                <span style="color:var(--brand-700);font-weight:700;">{{ r.aantal }} bedrijven</span>
            </div>
            <div style="font-size:0.76rem;color:var(--gray-400);margin-top:4px;">
                Top materialen: {{ r.materialen|join(", ") if r.materialen else "—" }}
            </div>
            <div style="font-size:0.76rem;margin-top:2px;">
                Marktactiviteit:
                <span style="color:{% if r.activiteit=='Hoog' %}var(--green-600){% elif r.activiteit=='Gemiddeld' %}var(--brand-600){% else %}var(--gray-400){% endif %};font-weight:700;">{{ r.activiteit }}</span>
            </div>
        </div>
        {% else %}
        <div class="dg-lege">Nog geen regiodata.</div>
        {% endfor %}
    </div>
</div>

<div class="dg-kaart">
    <div class="dg-kaart-titel">Openstaande orders</div>
    <div class="dg-lege">Er is nog geen inkoop-/verkoop-ordermodule. Zodra die er is, komt hier een overzicht van openstaande verkoop- en inkooporders met bedragen en status. Zeg het als je wilt dat ik die nu bouw.</div>
</div>

</div>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script>
var dKaart = L.map("dashKaart", {zoomControl:false, attributionControl:false}).setView([30,10], 2);
L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {attribution:"© OpenStreetMap, © CARTO"}).addTo(dKaart);
var kleurPerStatus = {"klant":"#22c55e","potentie":"#fbbf24","in_proces":"#3b82f6","geen_interesse":"#6b7280","":"#f0a83c"};
var dCluster = L.markerClusterGroup({
    iconCreateFunction: function(cluster) {
        return L.divIcon({
            html: '<div style="background:#f0a83c;color:#1b1309;width:34px;height:34px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12px;border:2px solid #fbbf24;box-shadow:0 0 10px rgba(240,168,60,0.5);">' + cluster.getChildCount() + '</div>',
            className: '', iconSize: [34, 34]
        });
    }
});
{{ kaart_bedrijven|tojson }}.forEach(function(b){
    dCluster.addLayer(L.circleMarker([b.lat, b.lon], {radius:4, color: kleurPerStatus[b.status] || "#f0a83c", fillColor: kleurPerStatus[b.status] || "#f0a83c", fillOpacity:0.9, weight:1}));
});
dKaart.addLayer(dCluster);
</script>
    """
    pagina = render_simple_page("Dashboard", "dashboard", inhoud)
    return render_template_string(pagina,
        totaal=len(ENF_BEDRIJVEN), landen=LANDEN, fabrieken=len(PAPIERFABRIEKEN),
        klant=aantal_klant, potentie=aantal_potentie, proces=aantal_proces, geen=aantal_geen,
        status_totaal=status_totaal, top_materialen=top_materialen, max_materiaal=max_materiaal,
        volume_klant=volume_klant, openstaand=openstaand, kaart_bedrijven=kaart_bedrijven,
        donut_segmenten=donut_segmenten, regio_kaarten=regio_kaarten,
        groei_pct=groei_pct, groei_periode=groei_periode)

@app.route("/inzichten")
def inzichten():
    per_land = {}
    per_materiaal = {}
    for b in ENF_BEDRIJVEN:
        land = b.get("land", "Onbekend")
        per_land[land] = per_land.get(land, 0) + 1
        for m in [x.strip() for x in b.get("materialen", "").split(",") if x.strip()]:
            per_materiaal[m] = per_materiaal.get(m, 0) + 1

    top_landen = sorted(per_land.items(), key=lambda x: -x[1])[:10]
    top_materialen = sorted(per_materiaal.items(), key=lambda x: -x[1])[:10]
    max_land = max([a for _, a in top_landen], default=1)
    max_mat = max([a for _, a in top_materialen], default=1)

    inhoud = """
    <div class="page-title">Inzichten</div>
    <div class="dg-rij-2">
        <div class="info-kaart">
            <div class="dg-kaart-titel">Top 10 landen</div>
            {% for land, aantal in top_landen %}
            <a href="/?land={{ land }}" class="dg-bar-rij" style="text-decoration:none;">
                <span class="dg-bar-label" style="color:var(--gray-700);">{{ land }}</span>
                <div class="dg-bar-track"><div class="dg-bar-fill" style="width:{{ (aantal/max_land*100)|round(1) }}%"></div></div>
                <span class="dg-bar-getal">{{ aantal }}</span>
            </a>
            {% else %}
            <div class="lege-staat">Nog geen data.</div>
            {% endfor %}
        </div>
        <div class="info-kaart">
            <div class="dg-kaart-titel">Top 10 materialen</div>
            {% for mat, aantal in top_materialen %}
            <a href="/?materiaal={{ mat }}" class="dg-bar-rij" style="text-decoration:none;">
                <span class="dg-bar-label" style="color:var(--gray-700);">{{ mat }}</span>
                <div class="dg-bar-track"><div class="dg-bar-fill" style="width:{{ (aantal/max_mat*100)|round(1) }}%"></div></div>
                <span class="dg-bar-getal">{{ aantal }}</span>
            </a>
            {% else %}
            <div class="lege-staat">Nog geen data.</div>
            {% endfor %}
        </div>
    </div>
    """
    pagina = render_simple_page("Inzichten", "inzichten", inhoud)
    return render_template_string(pagina, top_landen=top_landen, top_materialen=top_materialen, max_land=max_land, max_mat=max_mat)

@app.route("/contacten")
def contacten():
    status_alle = laad_status()
    labels = {"klant": ("🟢 Klant","var(--green-600)"), "potentie": ("🟡 Potentie","var(--brand-600)"), "in_proces": ("🔵 In Proces","#3b82f6"), "geen_interesse": ("⚪ Geen Interesse","var(--gray-400)")}
    contacten_lijst = []
    for b in ENF_BEDRIJVEN:
        s = status_alle.get(b["naam"], "")
        if s:
            label, kleur = labels.get(s, (s, "var(--gray-400)"))
            contacten_lijst.append({"naam": b["naam"], "land": b["land"], "regio": b.get("regio",""), "materialen": b.get("materialen",""), "status_label": label, "status_kleur": kleur})

    inhoud = """
    <div class="page-title">Contacten</div>
    {% if contacten_lijst %}
    <div class="mat-grid">
        {% for c in contacten_lijst %}
        <a href="/bedrijf/{{ c.naam|urlencode }}" class="mat-kaart" style="padding:16px 20px;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                <div class="mat-naam" style="margin-bottom:2px;">{{ c.naam }}</div>
                <span style="font-size:0.7rem;font-weight:700;color:{{ c.status_kleur }};white-space:nowrap;">{{ c.status_label }}</span>
            </div>
            <div class="mat-sub" style="margin-bottom:8px;">📍 {{ c.regio }}, {{ c.land }}</div>
            <div class="company-tags" style="padding-left:0;">
                {% if c.materialen %}{% for m in c.materialen.split(",")[:3] %}<span class="tag tag-green">{{ m.strip() }}</span>{% endfor %}{% endif %}
            </div>
        </a>
        {% endfor %}
    </div>
    {% else %}
    <div class="lege-staat">Nog geen bedrijven met een status. Zet een status via het paneel op de zoekpagina.</div>
    {% endif %}
    """
    pagina = render_simple_page("Contacten", "contacten", inhoud)
    return render_template_string(pagina, contacten_lijst=contacten_lijst)

@app.route("/opslagen")
def opslagen():
    opgeslagen_namen = set(laad_opgeslagen())
    lijst = [b for b in ENF_BEDRIJVEN if b["naam"] in opgeslagen_namen]

    inhoud = """
    <div class="page-title">Opgeslagen bedrijven</div>
    {% if lijst %}
    <div class="mat-grid">
        {% for b in lijst %}
        <a href="/bedrijf/{{ b.naam|urlencode }}" class="mat-kaart" style="padding:16px 20px;">
            <div class="mat-naam" style="margin-bottom:2px;">⭐ {{ b.naam }}</div>
            <div class="mat-sub" style="margin-bottom:8px;">📍 {{ b.regio }}, {{ b.land }}</div>
            <div class="company-tags" style="padding-left:0;">
                {% if b.materialen %}{% for m in b.materialen.split(",")[:3] %}<span class="tag tag-green">{{ m.strip() }}</span>{% endfor %}{% endif %}
            </div>
        </a>
        {% endfor %}
    </div>
    {% else %}
    <div class="lege-staat">Nog geen bedrijven opgeslagen. Klik op het sterretje bij een bedrijf om het hier te laten verschijnen.</div>
    {% endif %}
    """
    pagina = render_simple_page("Opgeslagen", "opslagen", inhoud)
    return render_template_string(pagina, lijst=lijst)

@app.route("/notities-overzicht")
def notities_overzicht():
    alle = laad_notities()
    rijen = []
    for bedrijf, lijst in alle.items():
        for n in lijst:
            if n["type"] == "team":
                rijen.append({"bedrijf": bedrijf, "tekst": n["tekst"], "timestamp": n["timestamp"]})
    rijen.sort(key=lambda x: x["timestamp"], reverse=True)

    inhoud = """
    <div class="page-title">Notities</div>
    {% if rijen %}
    <div class="info-kaart" style="max-width:700px;">
        {% for r in rijen %}
        <div class="dg-activiteit-item">
            <a href="/bedrijf/{{ r.bedrijf|urlencode }}" style="color:var(--gray-800);font-weight:700;text-decoration:none;">{{ r.bedrijf }}</a><br>
            {{ r.tekst }}
            <small>{{ r.timestamp }}</small>
        </div>
        {% endfor %}
    </div>
    {% else %}
    <div class="lege-staat">Nog geen teamnotities.</div>
    {% endif %}
    """
    pagina = render_simple_page("Notities", "notities", inhoud)
    return render_template_string(pagina, rijen=rijen)

@app.route("/instellingen")
def instellingen():
    inhoud = """
    <div class="page-title">Instellingen</div>
    <div class="info-kaart" style="max-width:400px;margin-bottom:16px;">
        <div class="drawer-row"><span class="drawer-row-label">Ingelogd als</span><span class="drawer-row-value">{{ gebruikersnaam }}</span></div>
        <div class="drawer-row"><span class="drawer-row-label">Team</span><span class="drawer-row-value">{{ team or "—" }}</span></div>
        <hr class="drawer-divider">
        <a href="/logout" class="btn-nav btn-nav-primary" style="display:inline-block;">Uitloggen</a>
    </div>
    <div class="info-kaart" style="max-width:400px;">
        <div class="dg-kaart-titel">Beheer</div>
        <a href="/importeer" style="display:block;margin-bottom:8px;color:var(--brand-600);font-weight:600;text-decoration:none;">→ Excel-import</a>
        <a href="/importeer-osm" style="display:block;margin-bottom:8px;color:var(--brand-600);font-weight:600;text-decoration:none;">→ OpenStreetMap-import</a>
        <a href="/opschonen-dubbelen" style="display:block;margin-bottom:8px;color:var(--brand-600);font-weight:600;text-decoration:none;">→ Dubbele bedrijven opschonen</a>
        <a href="/herlabel-brontype" style="display:block;margin-bottom:8px;color:var(--brand-600);font-weight:600;text-decoration:none;">→ Bedrijfstypes aanvullen</a>
        <a href="/importeer-scrapmonster" style="display:block;margin-bottom:8px;color:var(--brand-600);font-weight:600;text-decoration:none;">→ ScrapMonster-import (schroothandels)</a>
        <a href="/export-data" style="display:block;color:var(--brand-600);font-weight:600;text-decoration:none;">→ Live data downloaden (backup/synchroniseren)</a>
    </div>
    """
    pagina = render_simple_page("Instellingen", "instellingen", inhoud)
    return render_template_string(pagina, gebruikersnaam=session.get("gebruikersnaam",""), team=session.get("team",""))

@app.route("/certificeringen")
def certificeringen_pagina():
    per_cert = {}
    for b in ENF_BEDRIJVEN:
        for c in [x.strip() for x in b.get("certificeringen", "").split(",") if x.strip()]:
            per_cert.setdefault(c, []).append(b)

    cert_lijst = sorted(per_cert.items(), key=lambda x: -len(x[1]))

    inhoud = """
<style>
.cert-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:16px; }
.cert-kaart { background:#fff; border:1px solid var(--gray-200); border-radius:14px; padding:20px; }
.cert-titel { font-size:1.05rem; font-weight:700; color:var(--gray-800); margin-bottom:2px; }
.cert-aantal { font-size:0.78rem; color:var(--gray-400); margin-bottom:12px; }
.cert-bedrijf { font-size:0.82rem; padding:6px 0; border-bottom:1px solid var(--gray-100); }
.cert-bedrijf:last-child { border-bottom:none; }
.cert-bedrijf a { color:var(--gray-700); text-decoration:none; font-weight:600; }
.cert-bedrijf a:hover { color:var(--brand-600); }
</style>

<div class="page-title">Certifications</div>

{% if cert_lijst %}
<div class="cert-grid">
    {% for cert, bedrijven_lijst in cert_lijst %}
    <div class="cert-kaart">
        <div class="cert-titel">🏅 {{ cert }}</div>
        <div class="cert-aantal">{{ bedrijven_lijst|length }} bedrijven</div>
        {% for b in bedrijven_lijst[:5] %}
        <div class="cert-bedrijf"><a href="/bedrijf/{{ b.naam|urlencode }}">{{ b.naam }}</a><br><span style="color:var(--gray-400);">{{ b.regio }}, {{ b.land }}</span></div>
        {% endfor %}
        {% if bedrijven_lijst|length > 5 %}<div style="font-size:0.76rem;color:var(--gray-400);margin-top:6px;">+ {{ bedrijven_lijst|length - 5 }} meer</div>{% endif %}
    </div>
    {% endfor %}
</div>
{% else %}
<div class="lege-staat">
    Nog geen bedrijven met certificeringen. Voeg de kolom "Certificeringen" toe bij je volgende Excel-import (bv. "ISO 9001, FSC") om deze pagina te vullen.
</div>
{% endif %}
    """
    pagina = render_simple_page("Certifications", "certificeringen", inhoud)
    return render_template_string(pagina, cert_lijst=cert_lijst)

@app.route("/materialen")
def materialen():
    per_materiaal = {}
    per_materiaal_landen = {}
    for b in ENF_BEDRIJVEN:
        for m in [x.strip() for x in b.get("materialen", "").split(",") if x.strip()]:
            per_materiaal[m] = per_materiaal.get(m, 0) + 1
            per_materiaal_landen.setdefault(m, set()).add(b.get("land",""))

    materialen_lijst = sorted(per_materiaal.items(), key=lambda x: -x[1])
    max_aantal = max([a for _, a in materialen_lijst], default=1)
    materialen_data = [
        {"naam": naam, "aantal": aantal, "landen": len(per_materiaal_landen.get(naam, [])), "pct": round(aantal/max_aantal*100,1)}
        for naam, aantal in materialen_lijst
    ]

    iconen = {"Paper":"📄","Plastic":"🧴","Metal":"🔩","Glass":"🍾","Wood":"🪵","Organic":"🌱","Electronic":"💻"}

    inhoud = """
<style>
.mat-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:16px; }
.mat-kaart { background:#fff; border:1px solid var(--gray-200); border-radius:14px; padding:20px; text-decoration:none; display:block; transition:var(--transition); }
.mat-kaart:hover { border-color:var(--brand-300); box-shadow:var(--shadow-md); transform:translateY(-2px); }
.mat-icoon { font-size:1.8rem; margin-bottom:10px; }
.mat-naam { font-size:1.05rem; font-weight:700; color:var(--gray-800); margin-bottom:4px; }
.mat-sub { font-size:0.78rem; color:var(--gray-400); margin-bottom:12px; }
.mat-bar-track { background:var(--gray-100); border-radius:6px; height:7px; overflow:hidden; }
.mat-bar-fill { background:linear-gradient(90deg,var(--brand-500),var(--brand-700)); height:100%; }
.mat-getal { font-weight:800; color:var(--brand-700); font-size:1.3rem; }
</style>

<div class="page-title">Materials</div>
<p style="color:var(--gray-400);margin-top:-16px;margin-bottom:24px;font-size:0.88rem;">{{ materialen_data|length }} materiaaltypen gevonden over {{ totaal }} bedrijven. Klik op een materiaal om gefilterd te zoeken.</p>

<div class="mat-grid">
    {% for m in materialen_data %}
    <a href="/?materiaal={{ m.naam }}" class="mat-kaart">
        <div class="mat-icoon">{{ iconen.get(m.naam, "♻️") }}</div>
        <div class="mat-naam">{{ m.naam }}</div>
        <div class="mat-sub">{{ m.landen }} landen</div>
        <div class="mat-getal">{{ m.aantal }}</div>
        <div class="mat-bar-track" style="margin-top:8px;"><div class="mat-bar-fill" style="width:{{ m.pct }}%"></div></div>
    </a>
    {% else %}
    <div class="lege-staat">Nog geen materiaaldata.</div>
    {% endfor %}
</div>
    """
    pagina = render_simple_page("Materials", "materialen", inhoud)
    return render_template_string(pagina, materialen_data=materialen_data, iconen=iconen, totaal=len(ENF_BEDRIJVEN))

@app.route("/wereldkaart")
def wereldkaart():
    status_alle = laad_status()
    kaart_data = [
        {"naam": b["naam"], "land": b["land"], "regio": b.get("regio",""), "lat": b["lat"], "lon": b["lon"],
         "materialen": b.get("materialen",""), "volume": b.get("volume",""), "status": status_alle.get(b["naam"],"")}
        for b in ENF_BEDRIJVEN if b.get("lat") and b.get("lon")
    ]

    inhoud = """
<style>
.wk-layout { display:flex; gap:20px; height:calc(100vh - 128px); }
.wk-filters { width:240px; flex-shrink:0; background:#fff; border:1px solid var(--gray-200); border-radius:14px; padding:18px; overflow-y:auto; }
.wk-map-wrap { flex:1; border-radius:14px; overflow:hidden; border:1px solid var(--gray-200); position:relative; }
#wereldKaart { width:100%; height:100%; }
.wk-stat { display:flex; justify-content:space-between; padding:6px 0; font-size:0.82rem; color:var(--gray-600); border-bottom:1px solid var(--gray-100); }
.wk-stat strong { color:var(--brand-700); }
.wk-legenda { display:flex; align-items:center; gap:6px; font-size:0.78rem; color:var(--gray-500); margin-top:4px; }
.wk-legenda span.stip { width:9px; height:9px; border-radius:50%; display:inline-block; }
</style>

<div class="page-title">World Map</div>

<div class="wk-layout">
    <aside class="wk-filters">
        <div class="filters-title" style="margin-bottom:14px;">🎚️ Filters</div>
        <div class="filter-group">
            <label class="filter-label">Land</label>
            <select class="filter-select" id="wkLand" onchange="wkFilter()">
                <option value="">Alle landen</option>
                {% for l in landen %}<option value="{{ l }}">{{ l }}</option>{% endfor %}
            </select>
        </div>
        <div class="filter-group">
            <label class="filter-label">Materiaal</label>
            <select class="filter-select" id="wkMateriaal" onchange="wkFilter()">
                <option value="">Alle materialen</option>
                <option value="Paper">Paper</option>
                <option value="Plastic">Plastic</option>
                <option value="Metal">Metal</option>
                <option value="Glass">Glass</option>
                <option value="Wood">Wood</option>
                <option value="Organic">Organic</option>
            </select>
        </div>
        <div class="filter-group">
            <label class="filter-label">Status</label>
            <select class="filter-select" id="wkStatus" onchange="wkFilter()">
                <option value="">Alle statussen</option>
                <option value="klant">🟢 Klant</option>
                <option value="potentie">🟡 Potentie</option>
                <option value="in_proces">🔵 In Proces</option>
            </select>
        </div>
        <hr class="filter-divider">
        <div class="wk-stat">Zichtbaar op kaart<strong id="wkAantal">0</strong></div>
        <div class="wk-stat">Totaal bedrijven<strong>{{ kaart_data|length }}</strong></div>
        <hr class="filter-divider">
        <div class="wk-legenda"><span class="stip" style="background:#22c55e;"></span> Klant</div>
        <div class="wk-legenda"><span class="stip" style="background:#f59e0b;"></span> Potentie</div>
        <div class="wk-legenda"><span class="stip" style="background:#3b82f6;"></span> In proces</div>
        <div class="wk-legenda"><span class="stip" style="background:#ea580c;"></span> Geen status</div>
    </aside>
    <div class="wk-map-wrap">
        <div id="wereldKaart"></div>
    </div>
</div>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script>
var ALLE_BEDRIJVEN_WK = {{ kaart_data|tojson }};
var wkKaart = L.map("wereldKaart").setView([30, 10], 2);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {attribution:"© OpenStreetMap"}).addTo(wkKaart);
var wkKleur = {"klant":"#22c55e","potentie":"#f59e0b","in_proces":"#3b82f6","geen_interesse":"#6b7280","":"#ea580c"};
var wkCluster = null;

function wkFilter() {
    var land = document.getElementById("wkLand").value;
    var mat = document.getElementById("wkMateriaal").value;
    var status = document.getElementById("wkStatus").value;

    if (wkCluster) wkKaart.removeLayer(wkCluster);
    wkCluster = L.markerClusterGroup({
        iconCreateFunction: function(cluster) {
            return L.divIcon({
                html: '<div style="background:#ea580c;color:#fff;width:34px;height:34px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12px;border:2px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,0.25);">' + cluster.getChildCount() + '</div>',
                className: '', iconSize: [34, 34]
            });
        }
    });

    var zichtbaar = 0;
    ALLE_BEDRIJVEN_WK.forEach(function(b) {
        if (land && b.land !== land) return;
        if (mat && b.materialen.indexOf(mat) === -1) return;
        if (status && b.status !== status) return;
        zichtbaar++;
        var kleur = wkKleur[b.status] || wkKleur[""];
        var marker = L.circleMarker([b.lat, b.lon], {radius:6, color:"#fff", weight:1, fillColor:kleur, fillOpacity:0.9});
        var popup = "<b>" + b.naam + "</b><br><small>" + b.regio + ", " + b.land + "</small>";
        popup += "<br><small>" + (b.materialen || "—") + "</small>";
        if (b.volume) popup += "<br><small>" + b.volume + " t/jaar</small>";
        popup += '<br><a href="/bedrijf/' + encodeURIComponent(b.naam) + '" style="color:#ea580c;font-weight:600;">Bekijk profiel →</a>';
        marker.bindPopup(popup);
        wkCluster.addLayer(marker);
    });
    wkKaart.addLayer(wkCluster);
    document.getElementById("wkAantal").textContent = zichtbaar;
}
wkFilter();
</script>
    """
    pagina = render_simple_page("World Map", "wereldkaart", inhoud)
    return render_template_string(pagina, landen=LANDEN, kaart_data=kaart_data)

@app.route("/bedrijf/<naam>")
def bedrijf_profiel(naam):
    bedrijf = next((b for b in ENF_BEDRIJVEN if b["naam"] == naam), None)
    if not bedrijf:
        inhoud = '<div class="page-title">Niet gevonden</div><div class="lege-staat">Dit bedrijf bestaat niet (meer).</div>'
        pagina = render_simple_page("Niet gevonden", "zoeken", inhoud)
        return render_template_string(pagina), 404

    status_alle = laad_status()
    status = status_alle.get(bedrijf["naam"], "")
    opgeslagen = bedrijf["naam"] in set(laad_opgeslagen())
    geverifieerd = bool(bedrijf.get("adres") or bedrijf.get("telefoon"))

    inhoud = """
<style>
.profiel-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:24px; }
.profiel-naam { font-size:1.6rem; font-weight:800; color:var(--gray-900); letter-spacing:-0.5px; }
.profiel-loc { color:var(--gray-400); font-size:0.9rem; margin-top:4px; }
.profiel-grid { display:grid; grid-template-columns:1.3fr 1fr; gap:20px; align-items:start; }
@media (max-width:900px) { .profiel-grid { grid-template-columns:1fr; } }
#profielKaart { height:260px; border-radius:14px; overflow:hidden; border:1px solid var(--gray-200); margin-top:16px; }
.profiel-terug { color:var(--gray-400); text-decoration:none; font-size:0.85rem; display:inline-block; margin-bottom:16px; }
.profiel-terug:hover { color:var(--brand-600); }
.verificatie-badge {
    display: inline-flex; align-items: center; gap: 3px;
    font-size: 0.68rem; font-weight: 700; color: var(--green-600);
    background: var(--green-50); border: 1px solid #bbf7d0;
    padding: 2px 8px; border-radius: 4px; vertical-align: middle;
}
.dg-kaart-titel { font-size:0.78rem; color:var(--gray-400); text-transform:uppercase; letter-spacing:1.2px; margin-bottom:14px; font-weight:700; }
.tag-purple { background: #f5f3ff; color: #7c3aed; border: 1px solid #ddd6fe; }
</style>

<a href="/" class="profiel-terug">← Terug naar zoeken</a>

<div class="profiel-header">
    <div>
        <div class="profiel-naam">{{ bedrijf.naam }}{% if geverifieerd %}<span class="verificatie-badge" style="margin-left:10px;">✓ Geverifieerd</span>{% endif %}</div>
        <div class="profiel-loc">📍 {{ bedrijf.regio }}, {{ bedrijf.land }}</div>
    </div>
    <span class="star-btn {% if opgeslagen %}opgeslagen{% endif %}" id="profielSterBtn" onclick="toggleOpslaanProfiel(this)" style="font-size:1.6rem;">{% if opgeslagen %}★{% else %}☆{% endif %}</span>
</div>

<div class="profiel-grid">
    <div>
        <div class="info-kaart" style="margin-bottom:16px;">
            <div class="dg-kaart-titel" style="color:var(--gray-400);">Company Overview</div>
            <div class="drawer-row"><span class="drawer-row-label">Status</span><span class="drawer-row-value">
                <select id="statusSelect" onchange="wijzigStatusProfiel()" style="padding:4px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;">
                    <option value="" {% if not status %}selected{% endif %}>Geen status</option>
                    <option value="klant" {% if status=='klant' %}selected{% endif %}>🟢 Klant</option>
                    <option value="potentie" {% if status=='potentie' %}selected{% endif %}>🟡 Potentie</option>
                    <option value="in_proces" {% if status=='in_proces' %}selected{% endif %}>🔵 In Proces</option>
                    <option value="geen_interesse" {% if status=='geen_interesse' %}selected{% endif %}>⚪ Geen Interesse</option>
                </select>
            </span></div>
            {% if bedrijf.brontype %}<div class="drawer-row"><span class="drawer-row-label">Type</span><span class="drawer-row-value">{{ bedrijf.brontype }}</span></div>{% endif %}
            <div class="drawer-row"><span class="drawer-row-label">Customer Type</span><span class="drawer-row-value">{{ bedrijf.klanttype or "—" }}</span></div>
            <div class="drawer-row"><span class="drawer-row-label">Materials</span><span class="drawer-row-value">{{ bedrijf.materialen or "—" }}</span></div>
        </div>

        <div class="info-kaart" style="margin-bottom:16px;">
            <div class="dg-kaart-titel" style="color:var(--gray-400);">Recycling Operations</div>
            <div class="drawer-row"><span class="drawer-row-label">Annual Capacity</span><span class="drawer-row-value">{{ (bedrijf.volume ~ " t/y") if bedrijf.volume else "—" }}</span></div>
            <div class="company-tags" style="padding-left:0;margin-top:8px;">
                {% if bedrijf.materialen %}{% for m in bedrijf.materialen.split(",") %}<span class="tag tag-green">{{ m.strip() }}</span>{% endfor %}{% endif %}
            </div>
        </div>

        {% if bedrijf.certificeringen %}
        <div class="info-kaart" style="margin-bottom:16px;">
            <div class="dg-kaart-titel" style="color:var(--gray-400);">Certifications</div>
            <div class="company-tags" style="padding-left:0;">
                {% for c in bedrijf.certificeringen.split(",") %}<span class="tag tag-purple">🏅 {{ c.strip() }}</span>{% endfor %}
            </div>
        </div>
        {% endif %}

        <div class="info-kaart">
            <div class="dg-kaart-titel" style="color:var(--gray-400);">Notities</div>
            <div id="notitiesLijst" style="margin-bottom:12px;"></div>
            <textarea id="notitieInput" placeholder="Schrijf een notitie..." style="width:100%;min-height:60px;padding:8px;border:1px solid #e2e8f0;border-radius:6px;font-family:inherit;font-size:13px;resize:vertical;"></textarea>
            <div style="display:flex;align-items:center;gap:12px;margin-top:8px;">
                <label style="font-size:13px;"><input type="radio" name="notitieType" value="team" checked> Team</label>
                <label style="font-size:13px;"><input type="radio" name="notitieType" value="prive"> Privé</label>
                <button onclick="voegNotitieToeProfiel()" style="margin-left:auto;padding:6px 14px;background:var(--brand-600);color:white;border:none;border-radius:6px;cursor:pointer;font-size:13px;">Toevoegen</button>
            </div>
        </div>
    </div>

    <div>
        <div class="info-kaart">
            <div class="dg-kaart-titel" style="color:var(--gray-400);">Contact Intelligence</div>
            <div id="profielContact"><div style="color:var(--gray-400);font-size:var(--text-sm);">Laden...</div></div>
            <div id="profielKaart"></div>
        </div>
    </div>
</div>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
var BEDRIJF_NAAM = {{ (bedrijf.naam or "")|tojson }};
var BEDRIJF_URL = {{ (bedrijf.url or "")|tojson }};
var pKaart = L.map("profielKaart", {zoomControl:true}).setView([{{ bedrijf.lat or 20 }}, {{ bedrijf.lon or 0 }}], {{ 12 if bedrijf.lat else 2 }});
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {attribution:"© OpenStreetMap"}).addTo(pKaart);
{% if bedrijf.lat and bedrijf.lon %}
L.marker([{{ bedrijf.lat }}, {{ bedrijf.lon }}]).addTo(pKaart).bindPopup({{ bedrijf.naam|tojson }});
{% endif %}

function vulContact(data) {
    var html = "";
    if (data.website) html += `<div class="drawer-row"><span class="drawer-row-label">Website</span><span class="drawer-row-value"><a href="${data.website}" target="_blank" style="color:var(--brand-600);font-weight:600;">${data.website.replace("https://","").replace("http://","").split("/")[0]}</a></span></div>`;
    var tel = data.telefoon || {{ (bedrijf.telefoon or "")|tojson }};
    var adr = data.adres || {{ (bedrijf.adres or "")|tojson }};
    if (tel) html += `<div class="drawer-row"><span class="drawer-row-label">Phone</span><span class="drawer-row-value">${tel}</span></div>`;
    if (adr) html += `<div class="drawer-row"><span class="drawer-row-label">Address</span><span class="drawer-row-value">${adr}</span></div>`;
    if (!html) html = '<div style="color:var(--gray-400);font-size:var(--text-sm);">Geen extra contactgegevens gevonden.</div>';
    document.getElementById("profielContact").innerHTML = html;
}

if (BEDRIJF_URL) {
    fetch("/details?url=" + encodeURIComponent(BEDRIJF_URL)).then(r => r.json()).then(vulContact);
} else {
    vulContact({});
}

async function laadNotities() {
    const res = await fetch("/api/notities?bedrijf=" + encodeURIComponent(BEDRIJF_NAAM));
    const notities = await res.json();
    const div = document.getElementById("notitiesLijst");
    if (notities.length === 0) { div.innerHTML = "<p style='font-size:13px;color:#94a3b8;'>Nog geen notities.</p>"; return; }
    let html = "";
    notities.forEach(n => {
        const badge = n.type === "team" ? "🟢 Team" : "🔒 Privé";
        html += `<div style="background:#f8fafc;border-radius:6px;padding:8px 10px;margin-bottom:6px;font-size:13px;"><div style="color:#334155;">${n.tekst}</div><div style="color:#94a3b8;font-size:11px;margin-top:4px;">${badge} · ${n.timestamp}</div></div>`;
    });
    div.innerHTML = html;
}
async function voegNotitieToeProfiel() {
    const input = document.getElementById("notitieInput");
    const tekst = input.value.trim();
    if (!tekst) return;
    const type_ = document.querySelector('input[name="notitieType"]:checked').value;
    await fetch("/api/notities", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, tekst: tekst, type: type_})});
    input.value = "";
    laadNotities();
}
async function wijzigStatusProfiel() {
    const select = document.getElementById("statusSelect");
    await fetch("/api/status", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, status: select.value})});
}
async function toggleOpslaanProfiel(el) {
    const res = await fetch("/api/opgeslagen", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({naam: BEDRIJF_NAAM})});
    const data = await res.json();
    el.textContent = data.opgeslagen ? "★" : "☆";
    el.classList.toggle("opgeslagen", data.opgeslagen);
}
laadNotities();
</script>
    """
    pagina = render_simple_page(bedrijf["naam"], "zoeken", inhoud)
    return render_template_string(pagina, bedrijf=bedrijf, status=status, opgeslagen=opgeslagen, geverifieerd=geverifieerd)

FOUTPAGINA_HTML = '''
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>{{ titel }} — RecycleFind</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: "Inter", -apple-system, sans-serif;
            background: radial-gradient(circle at 20% 10%, #fff7ed 0%, #f8fafc 45%, #f1f5f9 100%);
            min-height: 100vh; display: flex; align-items: center; justify-content: center; margin: 0; padding: 20px;
        }
        .box { text-align: center; max-width: 420px; }
        .code { font-size: 4.5rem; font-weight: 900; color: #ea580c; letter-spacing: -3px; line-height: 1; margin-bottom: 12px; }
        h1 { font-size: 1.3rem; font-weight: 800; color: #0f172a; margin-bottom: 8px; }
        p { color: #64748b; font-size: 0.9rem; margin-bottom: 24px; }
        a { display: inline-block; padding: 11px 22px; background: linear-gradient(135deg, #f97316, #ea580c); color: #fff;
            border-radius: 8px; text-decoration: none; font-weight: 700; font-size: 0.85rem; }
        a:hover { box-shadow: 0 8px 20px rgba(234,88,12,0.3); }
    </style>
</head>
<body>
    <div class="box">
        <div class="code">{{ code }}</div>
        <h1>{{ titel }}</h1>
        <p>{{ boodschap }}</p>
        <a href="/">← Terug naar RecycleFind</a>
    </div>
</body>
</html>
'''

@app.errorhandler(404)
def pagina_niet_gevonden(e):
    return render_template_string(FOUTPAGINA_HTML, code="404", titel="Pagina niet gevonden",
        boodschap="Deze pagina bestaat niet (meer). Check de link, of ga terug naar de zoekpagina."), 404

@app.errorhandler(500)
def server_fout(e):
    return render_template_string(FOUTPAGINA_HTML, code="500", titel="Er ging iets mis",
        boodschap="Er is een onverwachte fout opgetreden. Probeer het nog eens, of ga terug naar de zoekpagina."), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))