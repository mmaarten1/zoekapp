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
        "contactpersonen.json", "containers.json", "weegbrug.json", "logistieke_orders.json", "transport_planning.json",
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

def bewaar_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

# ============================================================
# Rechtensysteem — Fase 1: datamodel (afdeling + rol per gebruiker).
# Nog GEEN afscherming van schermen o.b.v. deze velden — dat komt in een
# latere fase. Dit legt alleen de basis vast.
# ============================================================
AFDELINGEN = ["accountmanager", "backoffice", "logistiek", "weegbrug", "finance"]
AFDELING_LABELS = {"accountmanager": "Accountmanager/Trader", "backoffice": "Backoffice", "logistiek": "Logistiek", "weegbrug": "Weegbrug", "finance": "Finance"}
ROLLEN = ["directeur", "manager", "medewerker"]
ROL_LABELS = {"directeur": "Directeur", "manager": "Manager", "medewerker": "Medewerker"}

# ============================================================
# Rechtensysteem — Fase 1, stap 2: schermen afschermen o.b.v. afdeling/rol.
#
# Belangrijk, bewust zo ontworpen (backward-compatible):
# - is_admin of rol "directeur" -> ziet altijd alles (ongeacht afdeling).
# - Gebruiker zonder afdeling ingesteld -> ziet ook alles (zodat bestaande
#   accounts, die nog geen afdeling toegewezen kregen, niets merken).
# - Alleen als een gebruiker EXPLICIET een afdeling heeft, en die afdeling
#   staat niet in de lijst voor een pagina, wordt de pagina verborgen/
#   geblokkeerd.
# - Pagina's die niet in PAGINA_AFDELINGEN staan zijn voor iedereen
#   zichtbaar (zoeken, dashboard, notities, instellingen, etc.).
# ============================================================
PAGINA_AFDELINGEN = {
    "klanten": ["accountmanager", "backoffice"],
    "leveranciers": ["accountmanager", "backoffice"],
    "contacten": ["accountmanager", "backoffice"],
    "orders": ["accountmanager"],
    "marktprijzen": ["accountmanager"],
    "materialen": ["accountmanager", "backoffice"],
    "certificeringen": ["accountmanager", "backoffice"],
    "voorraad": ["logistiek", "backoffice"],
    "logistiek": ["logistiek"],
    "weegbrug": ["logistiek", "weegbrug"],
    "logistieke_orders": ["logistiek", "weegbrug"],
    "afhandeling": ["logistiek", "weegbrug"],
    "logistieke_orders_finance": ["finance", "logistiek", "weegbrug"],
    "transport_planning": ["logistiek"],
    "facturen": ["finance"],
}

def mag_pagina_zien(pagina_key):
    """True als de ingelogde gebruiker deze pagina mag zien, o.b.v. afdeling/rol."""
    if is_huidige_gebruiker_admin():
        return True
    if session.get("rol", "") == "directeur":
        return True
    vereiste_afdelingen = PAGINA_AFDELINGEN.get(pagina_key)
    if not vereiste_afdelingen:
        return True
    afdeling = session.get("afdeling", "")
    if not afdeling:
        return True
    return afdeling in vereiste_afdelingen

def vereist_afdeling_of_403(pagina_key):
    """Geef een 403-response terug als de gebruiker deze pagina niet mag zien, anders None."""
    if mag_pagina_zien(pagina_key):
        return None
    pagina = render_simple_page("Geen toegang", pagina_key,
        '<div class="page-title">Geen toegang</div><div class="lege-staat">Dit onderdeel is niet beschikbaar voor jouw afdeling. Vraag een admin of directeur om je afdeling aan te passen als dit niet klopt.</div>')
    return render_template_string(pagina), 403

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

CONTAINERS_FILE = datapad("containers.json")
CONTAINER_TYPES = ["20ft", "40ft", "40ft HC", "Open top", "Flat rack", "Reefer"]
CONTAINER_STATUSSEN = ["Leeg", "Beladen", "Onderweg", "Op locatie", "Gelost", "Retour"]

def laad_containers():
    try:
        with open(CONTAINERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def bewaar_containers(data):
    with open(CONTAINERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

WEEGBRUG_FILE = datapad("weegbrug.json")
# Status-badges: Ingewogen (🟠 wacht op uitwegen), Compleet (🟢 in+uitgewogen),
# Probleem (🔴 gewicht-afwijking), Geannuleerd (⚪). Het "wacht op koppeling met
# order" (🔵) is geen eigen status maar wordt afgeleid: leeg ordernummer.
WEEGBRUG_STATUS_BADGES = {
    "Ingewogen": {"kleur": "#f59e0b", "bol": "🟠", "label": "Aan het lossen — wacht op uitwegen"},
    "Compleet": {"kleur": "#16a34a", "bol": "🟢", "label": "Ingewogen + uitgewogen"},
    "Probleem": {"kleur": "#dc2626", "bol": "🔴", "label": "Probleem/afwijking"},
    "Geannuleerd": {"kleur": "#94a3b8", "bol": "⚪", "label": "Geannuleerd"},
}

def laad_weegbrug():
    try:
        with open(WEEGBRUG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def bewaar_weegbrug(data):
    with open(WEEGBRUG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def genereer_weegnummer(bestaande_records):
    """WB-YYYYMMDD-NNN, volgnummer per dag zodat weegnummers menselijk leesbaar en uniek blijven."""
    vandaag_str = datetime.date.today().strftime("%Y%m%d")
    prefix = f"WB-{vandaag_str}-"
    vandaag_nummers = [int(r["weegnummer"].replace(prefix, "")) for r in bestaande_records if r.get("weegnummer","").startswith(prefix) and r["weegnummer"].replace(prefix,"").isdigit()]
    volgnummer = (max(vandaag_nummers) + 1) if vandaag_nummers else 1
    return f"{prefix}{volgnummer:03d}"

# ============================================================
# Logistieke Orders (Weegbrug Fase 2) — LET OP: dit is een ANDER concept dan
# ENF_BEDRIJVEN-gerelateerde "orders" (orders.py, /orders, voor
# accountmanagers/trading — klant, prijs, marge). Dit volgt de fysieke
# aflevering/weging van een inkomende vracht, los daarvan. Vandaar het eigen
# bestand LOGISTIEKE_ORDERS_FILE (niet ORDERS_FILE) om verwarring/overlap
# met dat systeem te voorkomen.
# ============================================================
LOGISTIEKE_ORDERS_FILE = datapad("logistieke_orders.json")
LOGISTIEKE_ORDER_STATUSSEN = [
    "Order aangemaakt", "Transport verwacht", "Truck aangekomen", "Ingewogen",
    "Order gekoppeld", "Uitgewogen", "Weegbon compleet", "Afhandeling",
    "Klaar voor Finance", "Gefactureerd", "Afgerond",
]

def laad_logistieke_orders():
    try:
        with open(LOGISTIEKE_ORDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def bewaar_logistieke_orders(data):
    with open(LOGISTIEKE_ORDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def genereer_logistiek_ordernummer(bestaande_orders):
    """LO-YYYYMMDD-NNN, zelfde patroon als weegnummers."""
    vandaag_str = datetime.date.today().strftime("%Y%m%d")
    prefix = f"LO-{vandaag_str}-"
    vandaag_nummers = [int(o["ordernummer"].replace(prefix, "")) for o in bestaande_orders if o.get("ordernummer","").startswith(prefix) and o["ordernummer"].replace(prefix,"").isdigit()]
    volgnummer = (max(vandaag_nummers) + 1) if vandaag_nummers else 1
    return f"{prefix}{volgnummer:03d}"

# ============================================================
# Transport Planning (uitgaande logistiek: Peute -> fabrieken in Europa).
# Los van de inkomende Weegbrug/Logistieke Orders-keten hierboven — dit
# volgt een heel andere flow (planning vooraf i.p.v. registratie bij
# aankomst).
# ============================================================
TRANSPORT_PLANNING_FILE = datapad("transport_planning.json")
TRANSPORT_PLANNING_STATUSSEN = [
    "Te plannen", "Transport aangevraagd", "Transporteur toegewezen", "Bevestigd",
    "Geladen", "Onderweg", "Geleverd", "Afgerond",
]

def laad_transport_planning():
    try:
        with open(TRANSPORT_PLANNING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def bewaar_transport_planning(data):
    with open(TRANSPORT_PLANNING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def genereer_transport_referentie(bestaande_transporten):
    """TP-YYYYMMDD-NNN, zelfde patroon als weeg-/ordernummers."""
    vandaag_str = datetime.date.today().strftime("%Y%m%d")
    prefix = f"TP-{vandaag_str}-"
    vandaag_nummers = [int(t["referentienummer"].replace(prefix, "")) for t in bestaande_transporten if t.get("referentienummer","").startswith(prefix) and t["referentienummer"].replace(prefix,"").isdigit()]
    volgnummer = (max(vandaag_nummers) + 1) if vandaag_nummers else 1
    return f"{prefix}{volgnummer:03d}"

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


# ============================================================
# Gedeeld template-systeem (PAGINA_HOOFD-shell, zijbalk, render_simple_page)
# + is_huidige_gebruiker_admin — nodig door vrijwel elke pagina/blueprint
# ============================================================
PAGINA_HOOFD = """<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>__TITEL__ — FTNext</title>
    <link href="https://fonts.googleapis.com/css2?family=Libre+Franklin:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        /* ============================================
           DESIGN SYSTEM — RECYCLEFIND
           ============================================ */

        /* TOKENS */
        :root {
            /* Colors */
            --brand-50:  #eef6f6;
            --brand-100: #d9ecec;
            --brand-200: #b3d9da;
            --brand-300: #7fb9bb;
            --brand-400: #3f9295;
            --brand-500: #14767b;
            --brand-600: #0d5c62;
            --brand-700: #0a4a4f;
            --brand-800: #083c40;
            --brand-900: #062f33;

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

            --orange-50:  #eef6f6;
            --orange-500: #14767b;
            --orange-600: #0d5c62;

            --red-50:  #fef2f2;
            --red-500: #ef4444;

            /* Typography */
            --font: "Libre Franklin", -apple-system, sans-serif;
            --font-mono: "IBM Plex Mono", monospace;
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
            background: transparent;
            padding: 16px 24px 16px 20px;
            border-bottom: none;
        }
        @media (max-width: 1200px) { .search-bar-section { padding: 16px 16px 16px 0; } }
        @media (max-width: 768px)  { .search-bar-section { padding: 12px 12px 12px 0; } }
        .hero-content {
            width: 100%;
            max-width: min(1700px, calc(100vw - 260px));
            box-sizing: border-box;
            margin: 0;
        }

        /* ============================================
           SEARCH
           ============================================ */
        .search-container {
            background: #fff;
            border: 1px solid #E5E7EB;
            border-radius: 10px;
            width: 100%;
            max-width: 820px;
            margin: 0;
            box-shadow: none;
            overflow: hidden;
            height: 44px;
        }
        .search-row {
            display: flex;
            align-items: stretch;
            height: 44px;
        }
        .search-input, .search-select {
            background: transparent;
            border: none;
            border-right: 1px solid var(--gray-100);
            border-radius: 0;
            padding: 0 14px;
            font-size: 14px;
            font-family: var(--font);
            color: var(--gray-800);
            outline: none;
            transition: var(--transition);
            height: 44px;
            box-sizing: border-box;
        }
        .search-input { flex: 1; min-width: 140px; }
        .search-input::placeholder { color: #94A3B8; }
        .search-select { width: 130px; cursor: pointer; flex: none; }
        .search-input:focus, .search-select:focus {
            background: var(--gray-50);
        }
        .btn-search {
            background: var(--brand-600);
            color: #fff;
            border: none;
            border-radius: 0;
            padding: 0 20px;
            font-size: 14px;
            font-weight: 700;
            font-family: var(--font);
            cursor: pointer;
            transition: var(--transition);
            white-space: nowrap;
            flex: none;
            height: 44px;
            box-sizing: border-box;
        }
        .btn-search:hover { background: var(--brand-700); }
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
            width: 100%;
            max-width: min(1700px, calc(100vw - 260px));
            box-sizing: border-box;
            margin: var(--space-6) 0 0 0;
            padding: 0 24px 0 0;
            display: flex;
            gap: 0;
            align-items: flex-start;
            position: relative;
        }
        @media (max-width: 1200px) { .main { padding: 0 16px 0 0; } }
        @media (max-width: 768px)  { .main { padding: 0 12px; max-width: 100%; } }

        /* ============================================
           FILTERS SIDEBAR
           ============================================ */
        .filters-panel {
            width: 300px;
            max-width: calc(100vw - 32px);
            position: fixed;
            top: 44px;
            left: 16px;
            z-index: 9999;
            background: #fff;
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-lg);
            padding: var(--space-5);
            box-shadow: 0 18px 44px -12px rgba(27,31,38,.28);
            max-height: 70vh;
            overflow-y: auto;
            box-sizing: border-box;
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
        .results-panel { flex: 1; min-width: 0; }
        .results-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 0;
            padding: 10px 16px;
            background: var(--gray-50);
            border-top: 1px solid var(--gray-200);
        }
        .results-count { font-size: var(--text-sm); color: var(--gray-400); }
        .results-count strong { color: var(--brand-600); font-weight: 700; }
        .results-list { }
        .data-thead, .data-row { display: flex; align-items: center; padding: 0 var(--space-3); }
        .data-thead {
            padding-top: 10px; padding-bottom: 10px;
            background: var(--gray-50); border-bottom: 1px solid var(--gray-200);
            font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: #7d8792;
            position: sticky; top: 0; z-index: 2; border-radius: var(--radius-md) var(--radius-md) 0 0;
        }
        .data-thead span[data-sort] { cursor: pointer; user-select: none; }
        .data-thead span[data-sort]:hover { color: var(--brand-600); }
        .data-row {
            padding-top: 9px; padding-bottom: 9px;
            border-bottom: 1px solid var(--gray-100);
            font-size: 13px; cursor: pointer; text-decoration: none; color: inherit;
        }
        .data-row:hover { background: #f9fbfc; }
        .data-row .num { font-family: var(--font-mono); font-size: 12.5px; }
        .data-row .zacht { color: #4b5563; font-size: 12.5px; }

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
        .tag-orange { background: var(--orange-50); color: var(--orange-600); border: 1px solid #b3d9da; }
        .star-btn { font-size: 1.1em; color: var(--gray-300); cursor: pointer; padding: 0 2px; }
        .star-btn:hover { color: var(--brand-400); }
        .star-btn.opgeslagen { color: var(--brand-500); }

        /* ============================================
           MAP
           ============================================ */
        .kaart-tabel-blok {
            width: 100%;
            border: none;
            border-radius: 0;
            box-shadow: none;
            overflow: visible;
            background: transparent;
        }
        .map-panel { width: 100%; margin-bottom: 0; }
        #kaart {
            height: 340px;
            border-radius: 0;
            border: 1px solid var(--gray-200);
            box-shadow: none;
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
            width: 240px;
            min-width: 240px;
            height: 100vh;
            position: sticky;
            top: 0;
            background: #1b1f26;
            display: flex;
            flex-direction: column;
            padding: var(--space-5) 0;
            flex-shrink: 0;
        }
        .sidebar-logo {
            font-size: var(--text-lg);
            font-weight: 600;
            color: #fff;
            letter-spacing: -0.5px;
            text-decoration: none;
            padding: 0 var(--space-5);
            margin-bottom: var(--space-2);
            display: flex;
            align-items: center;
            gap: 9px;
        }
        .sidebar-mark {
            width: 22px; height: 22px; flex: none;
            background: var(--brand-600); border-radius: 3px;
            display: inline-flex; align-items: center; justify-content: center;
            color: #fff; font-size: 11px; font-weight: 700; font-family: var(--font-mono);
            margin-right: 9px; vertical-align: middle;
        }
        .sidebar-logo em { color: #fff; font-style: normal; }
        .sidebar-cap { padding: 0 var(--space-5) 8px; font-family: var(--font-mono); font-size: 9px; letter-spacing: .16em; text-transform: uppercase; color: #626d7a; margin-bottom: var(--space-2); }
        .sidebar-nav { display: flex; flex-direction: column; gap: 1px; padding: 0 var(--space-3); }
        .sidebar-link {
            display: flex;
            align-items: center;
            gap: var(--space-3);
            padding: 9px var(--space-3);
            border-radius: var(--radius-sm);
            color: #aeb7c2;
            text-decoration: none;
            font-size: var(--text-sm);
            font-weight: 500;
            transition: var(--transition);
        }
        .sidebar-link:hover { background: #232830; color: #fff; }
        .sidebar-link.active { background: #232830; color: #fff; font-weight: 600; box-shadow: inset 3px 0 0 var(--brand-600); }
        .sidebar-link .icoon { font-family: var(--font-mono); font-size: 9px; color: #59636f; width: 18px; text-align: left; }
        .sidebar-me { margin-top: auto; padding: var(--space-4) var(--space-5) 0; border-top: 1px solid #2b3138; display: flex; align-items: center; gap: 9px; }
        .sidebar-avatar { width: 26px; height: 26px; flex: none; border-radius: 50%; background: #2f3641; display: flex; align-items: center; justify-content: center; font-size: 11px; color: #cdd4dc; }
        .sidebar-me-naam { font-size: 12.5px; color: #e6eaef; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .sidebar-me-rol { font-size: 10.5px; color: #6d7783; }
        .sidebar-me-uit { margin-left: auto; font-size: 15px; color: #6d7783; text-decoration: none; }
        .sidebar-me-uit:hover { color: #fff; }
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
            .drawer-row { flex-direction: column; align-items: flex-start; gap: 4px; }
            .drawer-row-value { text-align: left; width: 100%; }
            .drawer-row-value input[type="text"] { width: 100% !important; text-align: left !important; box-sizing: border-box; }
            .vrd-2koloms { grid-template-columns: 1fr !important; }
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
        .page-title { font-size: 24px; font-weight: 600; letter-spacing: -0.025em; color: var(--gray-900); margin: 0 0 5px; }
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
    """
    LET OP bij een nieuw zijbalk-item: de zoekpagina (zoeken.py, route '/')
    heeft een EIGEN, hardcoded kopie van de zijbalk in zijn HTML-template
    (niet via deze functie) — dit is al twee keer over het hoofd gezien.
    Elk nieuw item hier moet OOK handmatig toegevoegd worden in zoeken.py,
    naast de link voor 'logistiek' (zoek op 'class="sidebar-link"').
    """
    try:
        aantal_open_orders = sum(1 for o in laad_orders() if o.get("status") in ("Open", "Onderhandeling"))
    except Exception:
        aantal_open_orders = 0

    items = [
        ("zoeken", "/", "ZK", "Zoeken"),
        ("wereldkaart", "/wereldkaart", "WM", "World Map"),
        ("dashboard", "/dashboard", "DB", "Dashboard"),
        ("inzichten", "/inzichten", "IZ", "Inzichten"),
        ("materialen", "/materialen", "MT", "Materials"),
        ("klanten", "/klanten", "KL", "Klanten"),
        ("leveranciers", "/leveranciers", "LV", "Leveranciers"),
        ("certificeringen", "/certificeringen", "CF", "Certifications"),
        ("contacten", "/contacten", "CT", "Contacten"),
        ("orders", "/orders", "OR", "Orders"),
        ("logistiek", "/logistiek", "LG", "Logistiek"),
        ("weegbrug", "/weegbrug", "WB", "Weegbrug"),
        ("logistieke_orders", "/logistiek/orders", "LO", "Orders (logistiek)"),
        ("afhandeling", "/logistiek/afhandeling", "AF", "Afhandeling"),
        ("transport_planning", "/transport-planning", "TP", "Transport Planning"),
        ("facturen", "/facturen", "FA", "Facturen"),
        ("marktprijzen", "/marktprijzen", "MP", "Marktprijzen"),
        ("voorraad", "/voorraad", "VR", "Voorraad"),
        ("notities", "/notities-overzicht", "NT", "Notities"),
        ("instellingen", "/instellingen", "IN", "Instellingen"),
    ]
    links = ""
    for key, href, icoon, label in items:
        if not mag_pagina_zien(key):
            continue
        cls = "sidebar-link active" if key == actief else "sidebar-link"
        badge_html = ""
        if key == "orders" and aantal_open_orders > 0:
            badge_html = f'<span style="background:var(--brand-600);color:#fff;font-size:10px;font-weight:700;padding:1px 6px;border-radius:9px;margin-left:auto;">{aantal_open_orders}</span>'
        links += "<a href=\"" + href + "\" class=\"" + cls + "\" style=\"display:flex;align-items:center;\"><span class=\"icoon\">" + icoon + "</span> " + label + badge_html + "</a>\n        "
    return '''<button class="mobiel-menu-knop" onclick="toggleMobielMenu()">☰</button>
<div class="mobiel-overlay" id="mobielOverlay" onclick="toggleMobielMenu()"></div>
<aside class="sidebar" id="mobielSidebar">
    <a href="/" class="sidebar-logo"><span class="sidebar-mark">FT</span><em>Next</em></a>
    <nav class="sidebar-nav">
        ITEMS_HIER
    </nav>
    <div class="sidebar-me">
        <span class="sidebar-avatar">GEBRUIKERSNAAM_INITIALEN</span>
        <div style="min-width:0;">
            <div class="sidebar-me-naam">GEBRUIKERSNAAM_HIER</div>
            <div class="sidebar-me-rol">TEAM_HIER</div>
        </div>
        <a class="sidebar-me-uit" href="/logout" title="Uitloggen">⏻</a>
    </div>
</aside>
<script>
function toggleMobielMenu() {
    document.getElementById("mobielSidebar").classList.toggle("open");
    document.getElementById("mobielOverlay").classList.toggle("open");
}
</script>'''.replace("ITEMS_HIER", links) \
             .replace("GEBRUIKERSNAAM_HIER", session.get("gebruikersnaam", "Gast")) \
             .replace("GEBRUIKERSNAAM_INITIALEN", (session.get("gebruikersnaam", "??")[:2]).upper()) \
             .replace("TEAM_HIER", session.get("team", "") or "Teamlid")

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

def is_huidige_gebruiker_admin():
    users = laad_users()
    gebruikersnaam = session.get("gebruikersnaam", "")
    if gebruikersnaam not in users:
        return False  # onbekende/niet-bestaande gebruiker: nooit admin
    # Backwards-compatible: bestaande gebruikers zonder is_admin-veld blijven admin
    return users[gebruikersnaam].get("is_admin", True)

def vereist_admin_of_403():
    """Geef een 403-response terug als de ingelogde gebruiker geen admin is, anders None."""
    if not is_huidige_gebruiker_admin():
        pagina = render_simple_page("Geen toegang", "instellingen", '<div class="page-title">Geen toegang</div><div class="lege-staat">Deze functie is alleen voor admins. Vraag een admin om je rechten aan te passen.</div>')
        return render_template_string(pagina), 403
    return None

# ============================================================
# ENF_BEDRIJVEN / PAPIERFABRIEKEN / TRANSPORT_DATA — hoofddatabron.
# Veilig deelbaar tussen app.py en Blueprints ZOLANG deze lijsten/dict
# altijd IN-PLACE gemuteerd worden (lijst[:] = ..., dict.update(...)) en
# NOOIT volledig herwezen (lijst = [...]) — anders raakt de module die
# herwijst uit sync met alle andere modules die nog de oude referentie
# vasthouden. Zie de git-geschiedenis voor het incident dat dit opleverde.
# ============================================================
with open(datapad("bedrijven.json"), "r", encoding="utf-8") as f:
    ENF_BEDRIJVEN = json.load(f)
with open(datapad("papierfabrieken.json"), "r", encoding="utf-8") as f:
    PAPIERFABRIEKEN = json.load(f)

def bewaar_bedrijven():
    """Centrale save-functie voor ENF_BEDRIJVEN. Schrijft de huidige staat van de globale lijst weg."""
    with open(datapad("bedrijven.json"), "w", encoding="utf-8") as f:
        json.dump(ENF_BEDRIJVEN, f, ensure_ascii=False, indent=2)

def bewaar_papierfabrieken():
    """Centrale save-functie voor PAPIERFABRIEKEN. Schrijft de huidige staat van de globale lijst weg."""
    with open(datapad("papierfabrieken.json"), "w", encoding="utf-8") as f:
        json.dump(PAPIERFABRIEKEN, f, ensure_ascii=False, indent=2)

_bedrijven_gewijzigd = False
for _b in ENF_BEDRIJVEN:
    if "bedrijf_id" not in _b:
        _b["bedrijf_id"] = TENANT_ID
        _bedrijven_gewijzigd = True
if _bedrijven_gewijzigd:
    bewaar_bedrijven()

for fabriek in PAPIERFABRIEKEN:
    if "lat" not in fabriek or "lon" not in fabriek:
        geo = geocode_adres(fabriek.get("stad", ""), fabriek.get("land", ""))
        if geo:
            fabriek["lat"] = geo["lat"]
            fabriek["lon"] = geo["lon"]

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

ORDER_STATUSSEN = ["Open", "Onderhandeling", "Gewonnen", "Verloren"]
ORDER_KLEUREN = {"Open": "#3b82f6", "Onderhandeling": "var(--brand-600)", "Gewonnen": "var(--green-600)", "Verloren": "var(--gray-400)"}

SHIPMENT_STATUSSEN = ["Planned", "Confirmed", "Loading", "Loaded", "In Transit", "Arrived", "Weighed", "Received", "Delivered", "Cancelled"]

LANDEN = sorted(set(b["land"] for b in ENF_BEDRIJVEN))