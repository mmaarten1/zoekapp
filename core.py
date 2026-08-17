"""
core.py — Gedeeld fundament voor FTNext.

Bevat: bestandspad-helpers, alle laad_*/bewaar_*-functies voor de JSON-
databestanden (behalve ENF_BEDRIJVEN/PAPIERFABRIEKEN zelf — die blijven
voorlopig in app.py, want hun laadlogica is verweven met app-specifieke
setup; dat volgt in een latere stap), en rekenkundige hulpfuncties
(parse_hoeveelheid_getal, bereken_voorraad_status, bereken_afstand_km,
geocode_adres).

Deze module heeft GEEN afhankelijkheid van de Flask `app`-instantie zelf —
`request`/`session` zijn Flask's eigen thread-local proxy-objecten en werken
identiek ongeacht in welk bestand ze gebruikt worden, zolang de aanroep
binnen een actieve Flask-requestcontext gebeurt.

Wordt geïmporteerd door app.py met: from core import *
"""

import os
import json
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for
from werkzeug.security import check_password_hash, generate_password_hash
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
        "orders.json", "accountmanagers.json", "fotomappen.json", "materiaal_taxonomie.json", "voorraad_transacties.json",
        "voorraadmomenten.json", "voorraad_shipments.json", "contracten.json", "marktprijzen.json", "cert_vervaldatums.json",
        "contactpersonen.json",
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

ACCOUNTMANAGERS_FILE = datapad("accountmanagers.json")

def laad_accountmanagers():
    try:
        with open(ACCOUNTMANAGERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def bewaar_accountmanagers(data):
    with open(ACCOUNTMANAGERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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

ORDERS_FILE = datapad("orders.json")

VOORRAAD_FILE = datapad("voorraad_transacties.json")
VOORRAADMOMENTEN_FILE = datapad("voorraadmomenten.json")

def laad_voorraadmomenten():
    try:
        with open(VOORRAADMOMENTEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def bewaar_voorraadmomenten(data):
    with open(VOORRAADMOMENTEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

SHIPMENTS_FILE = datapad("voorraad_shipments.json")

def laad_shipments():
    try:
        with open(SHIPMENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def bewaar_shipments(data):
    with open(SHIPMENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

CONTRACTEN_FILE = datapad("contracten.json")

MARKTPRIJZEN_FILE = datapad("marktprijzen.json")

CERT_VERVALDATUMS_FILE = datapad("cert_vervaldatums.json")

def laad_cert_vervaldatums():
    try:
        with open(CERT_VERVALDATUMS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def bewaar_cert_vervaldatums(data):
    with open(CERT_VERVALDATUMS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _cert_sleutel(bedrijf_naam, certificaat):
    return f"{bedrijf_naam}|||{certificaat}"

CONTACTPERSONEN_FILE = datapad("contactpersonen.json")

def laad_contactpersonen():
    try:
        with open(CONTACTPERSONEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def bewaar_contactpersonen(data):
    with open(CONTACTPERSONEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def sync_contactpersoon_naar_contacten(bedrijf_naam, naam, rol="", email="", telefoon="", gebruiker=""):
    """Zet een contactpersoon (uit het bedrijfsformulier of losse veld-bewerking) automatisch
    ook in Contacten. Bestaat de combinatie naam+bedrijf al, dan vullen we alleen ontbrekende
    velden aan (rol/e-mail/telefoon) i.p.v. een dubbel record aan te maken."""
    naam = (naam or "").strip()
    bedrijf_naam = (bedrijf_naam or "").strip()
    if not naam or not bedrijf_naam:
        return
    personen = laad_contactpersonen()
    for p in personen:
        if p["naam"].strip().lower() == naam.lower() and p["bedrijf"].strip().lower() == bedrijf_naam.lower():
            if rol and not p.get("rol"):
                p["rol"] = rol
            if email and not p.get("email"):
                p["email"] = email
            if telefoon and not p.get("telefoon"):
                p["telefoon"] = telefoon
            bewaar_contactpersonen(personen)
            return
    personen.append({
        "id": str(uuid.uuid4()), "naam": naam, "bedrijf": bedrijf_naam, "rol": rol,
        "email": email, "telefoon": telefoon, "laatst": "",
        "gebruiker": gebruiker, "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
    })
    bewaar_contactpersonen(personen)

FACTUREN_FILE = datapad("facturen.json")

def laad_facturen():
    try:
        with open(FACTUREN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def bewaar_facturen(data):
    with open(FACTUREN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def bepaal_factuur_status(factuur):
    """Status wordt afgeleid: Betaald als betaalddatum is gezet, anders Open of Te laat t.o.v. vervaldatum."""
    if factuur.get("betaalddatum"):
        return "Betaald"
    vervaldatum = factuur.get("vervaldatum", "")
    if vervaldatum:
        try:
            if datetime.datetime.strptime(vervaldatum, "%Y-%m-%d").date() < datetime.date.today():
                return "Te laat"
        except (ValueError, TypeError):
            pass
    return "Open"

DOCUMENTEN_FILE = datapad("documenten.json")
DOCUMENTEN_MAP = datapad("documenten_uploads")
DOCUMENT_EXTENSIES_TOEGESTAAN = {"pdf", "doc", "docx"}

def laad_documenten():
    try:
        with open(DOCUMENTEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def bewaar_documenten(data):
    with open(DOCUMENTEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

UITNODIGINGEN_FILE = datapad("uitnodigingen.json")

def laad_uitnodigingen():
    try:
        with open(UITNODIGINGEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def bewaar_uitnodigingen(data):
    with open(UITNODIGINGEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def laad_marktprijzen():
    try:
        with open(MARKTPRIJZEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def bewaar_marktprijzen(data):
    with open(MARKTPRIJZEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def laad_contracten():
    try:
        with open(CONTRACTEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def bewaar_contracten(data):
    with open(CONTRACTEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)



def laad_voorraad():
    try:
        with open(VOORRAAD_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def bewaar_voorraad(data):
    with open(VOORRAAD_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def laad_orders():
    try:
        with open(ORDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def bewaar_orders(data):
    with open(ORDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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
FOTOMAPPEN_FILE = datapad("fotomappen.json")
FOTO_CATEGORIEEN = ["Algemeen", "Paper", "Karton", "Plastic"]

MATERIAAL_TAXONOMIE_FILE = datapad("materiaal_taxonomie.json")
_STANDAARD_TAXONOMIE = {
    "Paper": ["OCC (oud golfkarton)", "Krantenpapier", "Tijdschriften", "SOP (Sorted Office Paper)",
              "Multidruk", "Multiprint", "Wit A4 archief", "Mixed Paper (sorteerresten)"],
    "Karton": ["Kraftliner", "Testliner", "Fluting", "Gemengd karton", "Drankenkartons (Tetra Pak)"],
    "Plastic": ["HDPE", "LDPE", "PET", "PP", "PS", "PVC", "Folie (gemengd)"],
    "Metal": ["Ferro schroot", "Non-ferro (gemengd)", "Aluminium", "Koper", "RVS"],
    "Glass": ["Helder glas", "Groen glas", "Bruin glas", "Gemengd glas"],
}

def laad_materiaal_taxonomie():
    try:
        with open(MATERIAAL_TAXONOMIE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        bewaar_materiaal_taxonomie(_STANDAARD_TAXONOMIE)
        return dict(_STANDAARD_TAXONOMIE)

def bewaar_materiaal_taxonomie(data):
    with open(MATERIAAL_TAXONOMIE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def laad_fotos():
    try:
        with open(FOTOS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def bewaar_fotos(data):
    with open(FOTOS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def laad_fotomappen():
    try:
        with open(FOTOMAPPEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def bewaar_fotomappen(data):
    with open(FOTOMAPPEN_FILE, "w", encoding="utf-8") as f:
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

def parse_hoeveelheid_getal(tekst):
    """Haalt het eerste getal uit een vrije-tekst hoeveelheid zoals '500 ton', '1.250,5' of '1,250.5' -> float."""
    if not tekst:
        return 0.0
    match = re.search(r"[\d.,]+", str(tekst))
    if not match:
        return 0.0
    ruw = match.group(0).strip(".,")
    if not ruw:
        return 0.0

    if "," in ruw and "." in ruw:
        # Laatste teken bepaalt het decimaalteken (bv. "1.250,5" = EU, "1,250.5" = US)
        if ruw.rfind(",") > ruw.rfind("."):
            ruw = ruw.replace(".", "").replace(",", ".")
        else:
            ruw = ruw.replace(",", "")
    elif "," in ruw:
        # Alleen komma: duizendtal (3 cijfers erna) of decimaal
        deel_na = ruw.split(",")[-1]
        ruw = ruw.replace(",", "") if len(deel_na) == 3 else ruw.replace(",", ".")
    elif "." in ruw:
        # Alleen punt: duizendtal (3 cijfers erna) of decimaal
        deel_na = ruw.split(".")[-1]
        if len(deel_na) == 3:
            ruw = ruw.replace(".", "")

    try:
        return float(ruw)
    except ValueError:
        return 0.0

def bereken_voorraad_status():
    """
    Berekent de complete voorraadstatus (fysiek, te keuren, per locatie, transit, gereserveerd, aging)
    uit voorraad_transacties.json + voorraad_shipments.json + orders.json.
    Één centrale plek zodat dashboard, per-commodity-tabel en KPI's altijd consistent zijn.
    """
    transacties = laad_voorraad()
    shipments = laad_shipments()
    orders = laad_orders()

    def hoeveelheid(t):
        try:
            return float(str(t.get("hoeveelheid", "0")).replace(",", ""))
        except (ValueError, TypeError):
            return 0.0

    fysiek_per_materiaal = {}
    te_keuren_per_materiaal = {}
    per_locatie_materiaal = {}  # {(locatie, materiaal): hoeveelheid}
    aging_batches = []  # lijst van {materiaal, hoeveelheid, datum} voor goedgekeurde inbound

    for t in transacties:
        naam = t.get("materiaal", "")
        if not naam:
            continue
        aantal = hoeveelheid(t)
        type_ = t.get("type", "in")
        locatie = t.get("locatie", "") or "Alblasserdam"

        if type_ in ("in", "inbound"):
            keuring = t.get("keuringsstatus", "goedgekeurd")
            if keuring == "goedgekeurd":
                fysiek_per_materiaal[naam] = fysiek_per_materiaal.get(naam, 0) + aantal
                per_locatie_materiaal[(locatie, naam)] = per_locatie_materiaal.get((locatie, naam), 0) + aantal
                aging_batches.append({"materiaal": naam, "hoeveelheid": aantal, "datum": t.get("datum", "")})
            elif keuring == "te_keuren":
                te_keuren_per_materiaal[naam] = te_keuren_per_materiaal.get(naam, 0) + aantal
            # afgekeurd telt nergens mee

        elif type_ in ("uit", "outbound"):
            fysiek_per_materiaal[naam] = fysiek_per_materiaal.get(naam, 0) - aantal
            per_locatie_materiaal[(locatie, naam)] = per_locatie_materiaal.get((locatie, naam), 0) - aantal

        elif type_ == "transfer":
            # Totale voorraad blijft gelijk; alleen locatieverdeling verandert
            locatie_van = t.get("locatie_van", "")
            locatie_naar = t.get("locatie_naar", "")
            if locatie_van:
                per_locatie_materiaal[(locatie_van, naam)] = per_locatie_materiaal.get((locatie_van, naam), 0) - aantal
            if locatie_naar:
                per_locatie_materiaal[(locatie_naar, naam)] = per_locatie_materiaal.get((locatie_naar, naam), 0) + aantal

        elif type_ == "adjustment":
            teken = 1 if t.get("richting", "plus") == "plus" else -1
            fysiek_per_materiaal[naam] = fysiek_per_materiaal.get(naam, 0) + teken * aantal
            per_locatie_materiaal[(locatie, naam)] = per_locatie_materiaal.get((locatie, naam), 0) + teken * aantal

    # Drielaags model: elke actieve shipment valt in precies één bucket (geen dubbeltelling)
    # - inbound, nog niet Weighed/Received -> In Transit
    # - outbound, al Loaded (dus al van de fysieke voorraad af) maar nog niet Delivered -> In Transit
    # - direct (raakt Alblasserdam nooit) -> Direct Flow
    transit_per_materiaal = {}
    direct_flow_per_materiaal = {}
    flow_by_origin = {}
    flow_by_destination = {}
    inactieve_statussen = ("Cancelled",)
    for s in shipments:
        if s.get("status") in inactieve_statussen or not s.get("materiaal"):
            continue
        flow_type = bepaal_shipment_flow_type(s)
        aantal = shipment_hoeveelheid(s)

        if flow_type == "direct" and s.get("status") != "Delivered":
            direct_flow_per_materiaal[s["materiaal"]] = direct_flow_per_materiaal.get(s["materiaal"], 0) + aantal
        elif flow_type == "inbound" and s.get("status") not in ("Weighed", "Received"):
            transit_per_materiaal[s["materiaal"]] = transit_per_materiaal.get(s["materiaal"], 0) + aantal
        elif flow_type == "outbound" and s.get("status") in ("Loaded", "In Transit", "Arrived") :
            transit_per_materiaal[s["materiaal"]] = transit_per_materiaal.get(s["materiaal"], 0) + aantal

        if s.get("status") != "Delivered":
            if s.get("origin_land"):
                flow_by_origin[s["origin_land"]] = flow_by_origin.get(s["origin_land"], 0) + aantal
            if s.get("destination_land"):
                flow_by_destination[s["destination_land"]] = flow_by_destination.get(s["destination_land"], 0) + aantal

    # Gereserveerd: actieve verkooporders (nog niet verzonden/afgehandeld)
    gereserveerd_per_materiaal = {}
    inkooporders_per_materiaal = {}
    for o in orders:
        if o.get("status") not in ("Open", "Onderhandeling", "Gewonnen") or not o.get("materiaal"):
            continue
        aantal = parse_hoeveelheid_getal(o.get("hoeveelheid", ""))
        if o.get("ordertype", "verkoop") == "inkoop":
            inkooporders_per_materiaal[o["materiaal"]] = inkooporders_per_materiaal.get(o["materiaal"], 0) + aantal
        else:
            gereserveerd_per_materiaal[o["materiaal"]] = gereserveerd_per_materiaal.get(o["materiaal"], 0) + aantal

    # Aging: op basis van goedgekeurde inbound-batches (vereenvoudigd: netto verkoop wordt niet per-batch afgeboekt)
    vandaag = datetime.date.today()
    aging_buckets = {"0-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
    for batch in aging_batches:
        if not batch["datum"]:
            continue
        try:
            batch_datum = datetime.datetime.strptime(batch["datum"], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        dagen = (vandaag - batch_datum).days
        if dagen <= 30:
            aging_buckets["0-30"] += batch["hoeveelheid"]
        elif dagen <= 60:
            aging_buckets["31-60"] += batch["hoeveelheid"]
        elif dagen <= 90:
            aging_buckets["61-90"] += batch["hoeveelheid"]
        else:
            aging_buckets["90+"] += batch["hoeveelheid"]

    # Aankomende shipments (komende 7 dagen), voor forecast + KPI's
    over_7_dagen = vandaag + datetime.timedelta(days=7)
    inkomend_7d = 0.0
    uitgaand_7d = 0.0
    for s in shipments:
        if s.get("status") in ("Cancelled", "Received", "Delivered"):
            continue
        try:
            eta = datetime.datetime.strptime(s.get("datum", ""), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        if vandaag <= eta <= over_7_dagen:
            aantal = shipment_hoeveelheid(s)
            flow_type = bepaal_shipment_flow_type(s)
            if flow_type == "inbound":
                inkomend_7d += aantal
            elif flow_type == "outbound":
                uitgaand_7d += aantal

    return {
        "fysiek_per_materiaal": fysiek_per_materiaal,
        "te_keuren_per_materiaal": te_keuren_per_materiaal,
        "per_locatie_materiaal": per_locatie_materiaal,
        "transit_per_materiaal": transit_per_materiaal,
        "direct_flow_per_materiaal": direct_flow_per_materiaal,
        "flow_by_origin": flow_by_origin,
        "flow_by_destination": flow_by_destination,
        "gereserveerd_per_materiaal": gereserveerd_per_materiaal,
        "inkooporders_per_materiaal": inkooporders_per_materiaal,
        "aging_buckets": aging_buckets,
        "inkomend_7d": inkomend_7d,
        "uitgaand_7d": uitgaand_7d,
    }

def voldoet_aan_materiaal_min_volume(bedrijf, materiaal_naam, min_volume_str):
    """Check of een bedrijf voor het gegeven materiaal (of de kwaliteiten daaronder samen) minstens min_volume_str t/jaar heeft opgegeven."""
    if not min_volume_str:
        return True
    try:
        min_volume = float(min_volume_str)
    except (ValueError, TypeError):
        return True
    volumes = bedrijf.get("materiaal_volumes", {})
    if not isinstance(volumes, dict) or not volumes:
        return False
    materiaal_naam_laag = (materiaal_naam or "").strip().lower()
    taxonomie = laad_materiaal_taxonomie()
    kwaliteiten_onder_categorie = {k.strip().lower() for k in taxonomie.get(materiaal_naam, [])}

    totaal = 0.0
    gevonden = False
    for naam, waarde in volumes.items():
        naam_laag = naam.strip().lower()
        if naam_laag == materiaal_naam_laag or naam_laag in kwaliteiten_onder_categorie:
            try:
                totaal += float(str(waarde).replace(",", "").strip())
                gevonden = True
            except (ValueError, TypeError):
                pass
    if not gevonden:
        return False
    return totaal >= min_volume

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
        headers = {"User-Agent": "FTNext/1.0"}
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

ALBLASSERDAM_NAAM = "Alblasserdam"

def bepaal_shipment_flow_type(shipment):
    """Bepaalt puur op basis van origin/destination of dit inbound/outbound (Alblasserdam) of direct flow is."""
    origin = (shipment.get("origin_land","") or "").strip().lower()
    dest = (shipment.get("destination_land","") or "").strip().lower()
    alb = ALBLASSERDAM_NAAM.lower()
    if dest == alb:
        return "inbound"
    if origin == alb:
        return "outbound"
    return "direct"

def shipment_hoeveelheid(shipment):
    """Werkelijk gewogen gewicht heeft voorrang boven gepland gewicht."""
    werkelijk = shipment.get("werkelijk_hoeveelheid", "")
    if werkelijk:
        return parse_hoeveelheid_getal(werkelijk)
    return parse_hoeveelheid_getal(shipment.get("gepland_hoeveelheid", ""))

# ============================================================
# ENF_BEDRIJVEN / PAPIERFABRIEKEN — hoofddatabron + transport-data
# ============================================================
TENANT_ID = os.environ.get("TENANT_ID", "peute")

# ============================================
# COMPANIES HOUSE (UK) - status-check tegen faillissement/ontbinding
# ============================================
COMPANIES_HOUSE_API_KEY = os.environ.get("COMPANIES_HOUSE_API_KEY", "")
CH_FAILLIET_STATUSSEN = {
    "dissolved", "liquidation", "administration", "insolvency-proceedings",
    "receivership", "voluntary-arrangement", "converted-closed",
}

def companies_house_status(bedrijfsnaam):
    """Zoekt een bedrijfsnaam op bij Companies House. Geeft (status, gevonden_naam) terug, of (None, None) als niet gevonden/geen key."""
    if not COMPANIES_HOUSE_API_KEY:
        return None, None
    try:
        resp = requests.get(
            "https://api.company-information.service.gov.uk/search/companies",
            params={"q": bedrijfsnaam, "items_per_page": 1},
            auth=(COMPANIES_HOUSE_API_KEY, ""),
            timeout=15
        )
        if resp.status_code != 200:
            return None, None
        items = resp.json().get("items", [])
        if not items:
            return None, None
        return items[0].get("company_status"), items[0].get("title")
    except Exception:
        return None, None

def is_ch_financieel_gezond(bedrijfsnaam):
    """True = gezond of onbekend (geen key/geen match -> voordeel van de twijfel). False = aantoonbaar failliet/ontbonden."""
    status, _ = companies_house_status(bedrijfsnaam)
    if status is None:
        return True
    return status not in CH_FAILLIET_STATUSSEN

def laad_transport_data():
    try:
        with open(datapad("transport_prijzen.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def laad_forwarder_wachtwoorden():
    try:
        with open(datapad("forwarder_wachtwoorden.json"), "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}