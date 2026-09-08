import os
import secrets
import json
import io
import csv
from flask import Flask, render_template_string, request, jsonify, session, redirect, url_for, Response
from werkzeug.security import check_password_hash, generate_password_hash
import requests
import re
import uuid
import datetime
import threading
import time

from core import (
    datapad, laad_users, laad_accountmanagers, bewaar_accountmanagers,
    laad_status, bewaar_status, laad_voorraadmomenten, bewaar_voorraadmomenten,
    toegewezen_klant_fabrieken,
    laad_shipments, bewaar_shipments, laad_cert_vervaldatums, bewaar_cert_vervaldatums,
    _cert_sleutel, laad_contactpersonen, bewaar_contactpersonen, sync_contactpersoon_naar_contacten,
    laad_facturen, bewaar_facturen, bepaal_factuur_status, laad_documenten,
    laad_eigen_bedrijfsgegevens, bewaar_eigen_bedrijfsgegevens, haal_factuurgegevens_bedrijf,
    genereer_factuurnummer, bereken_factuur_bedragen,
    bewaar_documenten, laad_uitnodigingen, bewaar_uitnodigingen, laad_marktprijzen,
    bewaar_marktprijzen, laad_contracten, bewaar_contracten, laad_voorraad,
    bewaar_voorraad, laad_orders, bewaar_orders, laad_meldingen,
    bewaar_meldingen, laad_materiaal_taxonomie, bewaar_materiaal_taxonomie, laad_fotos,
    bewaar_fotos, laad_fotomappen, bewaar_fotomappen, laad_notities,
    bewaar_notities, get_user_id, laad_geocode_cache, bewaar_geocode_cache,
    parse_hoeveelheid_getal, parse_ton_intern, bereken_voorraad_status, voldoet_aan_materiaal_min_volume, bereken_afstand_km, leverancier_instelling_voor,
    geocode_adres, ACCOUNTMANAGERS_FILE, CERT_VERVALDATUMS_FILE, CONTACTPERSONEN_FILE,
    CONTRACTEN_FILE, DATA_DIR, DOCUMENTEN_FILE, DOCUMENTEN_MAP,
    DOCUMENT_EXTENSIES_TOEGESTAAN, FACTUREN_FILE, FOTOMAPPEN_FILE, FOTOS_FILE,
    FOTOS_MAP, FOTO_CATEGORIEEN, GEOCODE_CACHE_FILE, MARKTPRIJZEN_FILE,
    MATERIAAL_TAXONOMIE_FILE, MELDINGEN_FILE, NOTITIES_FILE, ORDERS_FILE,
    SHIPMENTS_FILE, STATUS_FILE, UITNODIGINGEN_FILE, USERS_FILE,
    VOORRAADMOMENTEN_FILE, VOORRAAD_FILE, _STANDAARD_TAXONOMIE,
    ALBLASSERDAM_NAAM, bepaal_shipment_flow_type, shipment_hoeveelheid,
    TENANT_ID, COMPANIES_HOUSE_API_KEY, CH_FAILLIET_STATUSSEN,
    companies_house_status, is_ch_financieel_gezond, laad_transport_data, laad_forwarder_wachtwoorden,
    bewaar_forwarder_wachtwoorden, is_account_tijdelijk_geblokkeerd, registreer_mislukte_inlogpoging,
    reset_mislukte_inlogpogingen, haal_of_maak_csrf_token,
    laad_organisatiestructuur, bewaar_organisatiestructuur,
    laad_layout_voorkeuren, bewaar_layout_voorkeuren, ZIJBALK_ITEMS, _sorteer_op_voorkeur,
    effectieve_layout_voorkeur,
    PAGINA_HOOFD, sidebar_html, render_simple_page, is_huidige_gebruiker_admin, vereist_admin_of_403,
    ENF_BEDRIJVEN, PAPIERFABRIEKEN, bewaar_bedrijven, bewaar_papierfabrieken,
    TRANSPORT_DATA, vind_transport_tarieven_dichtbij, ORDER_KLEUREN, SHIPMENT_STATUSSEN, LANDEN,
    bewaar_users, AFDELINGEN, AFDELING_LABELS, ROLLEN, ROL_LABELS,
    mag_pagina_zien, vereist_afdeling_of_403, PAGINA_AFDELINGEN,
    laad_containers, bewaar_containers, CONTAINER_TYPES, CONTAINER_STATUSSEN,
    laad_logistieke_orders, bewaar_logistieke_orders, laad_weegbrug, laad_documenten,
    laad_handelsorders, laad_transport_planning, bewaar_transport_planning,
    laad_bedrijfslogo_instelling, bewaar_bedrijfslogo_instelling, LOGO_MAP, LOGO_POSITIES,
)

from bs4 import BeautifulSoup

app = Flask(__name__)

def _bepaal_secret_key():
    """Gebruikt de SECRET_KEY-omgevingsvariabele als die is ingesteld (aanbevolen,
    zeker in productie). Is die er niet, dan wordt GEEN vast, voorspelbaar
    noodwoord meer gebruikt (dat was een echt beveiligingslek — iedereen die de
    broncode kent, kende dan ook de sleutel waarmee sessies ondertekend worden).
    In plaats daarvan wordt eenmalig een willekeurige, veilige sleutel gegenereerd
    en weggeschreven naar een lokaal bestand, zodat sessies wél consistent blijven
    over herstarts heen — zonder dat de sleutel ooit in de broncode terechtkomt."""
    omgevingssleutel = os.environ.get("SECRET_KEY")
    if omgevingssleutel:
        return omgevingssleutel
    # Zelfde DATA_DIR-conventie als core.py (Railway Volume indien ingesteld, anders lokale map)
    # — bewust hier los gehouden i.p.v. core.py te importeren, want dit moet al werken
    # vóórdat de rest van de app (inclusief core.py) geladen wordt.
    data_map = os.environ.get("DATA_DIR", ".")
    sleutelpad = os.path.join(data_map, ".secret_key")
    try:
        with open(sleutelpad, "r", encoding="utf-8") as f:
            bestaande = f.read().strip()
            if bestaande:
                return bestaande
    except FileNotFoundError:
        pass
    nieuwe_sleutel = secrets.token_hex(32)
    try:
        os.makedirs(os.path.dirname(sleutelpad), exist_ok=True)
        with open(sleutelpad, "w", encoding="utf-8") as f:
            f.write(nieuwe_sleutel)
    except OSError:
        pass  # Kan niet wegschrijven (bv. read-only filesystem) — sleutel blijft dan wel deze sessie werken
    return nieuwe_sleutel

app.secret_key = _bepaal_secret_key()

# Sessie-cookies verharden. SESSION_COOKIE_SECURE alleen aanzetten in productie
# (Railway) — anders werkt lokaal inloggen niet meer, want dat draait meestal
# over gewoon http zonder ssl, en een 'Secure'-cookie wordt dan nooit verstuurd.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = bool(os.environ.get("RAILWAY_ENVIRONMENT"))

@app.context_processor
def _injecteer_csrf_token_overal():
    """Maakt {{ csrf_token }} beschikbaar in ELKE Jinja-render in de hele app,
    ook de handvol standalone admin-pagina's die niet via render_simple_page
    lopen (die krijgen het token al automatisch via de client-side injectie
    daar) — zonder dat elke individuele render_template_string-aanroep
    aangepast hoeft te worden."""
    return dict(csrf_token=haal_of_maak_csrf_token())

from marktprijzen import marktprijzen_bp
app.register_blueprint(marktprijzen_bp)

from notities import notities_bp
app.register_blueprint(notities_bp)

from meldingen import meldingen_bp
app.register_blueprint(meldingen_bp)

from relaties import relaties_bp
app.register_blueprint(relaties_bp)

from materialen import materialen_bp
app.register_blueprint(materialen_bp)

from contacten import contacten_bp
app.register_blueprint(contacten_bp)

from taken import taken_bp
app.register_blueprint(taken_bp)

from orders import orders_bp
app.register_blueprint(orders_bp)

from voorraad import voorraad_bp
app.register_blueprint(voorraad_bp)

from dashboard import dashboard_bp, DASHBOARD_WIDGET_LABELS
app.register_blueprint(dashboard_bp)

from zoeken import zoeken_bp
app.register_blueprint(zoeken_bp)

from weegbrug import weegbrug_bp
app.register_blueprint(weegbrug_bp)

from logistieke_orders import logistieke_orders_bp
app.register_blueprint(logistieke_orders_bp)

from transport_planning import transport_planning_bp
app.register_blueprint(transport_planning_bp)

from commercieel_instellingen import commercieel_instellingen_bp
app.register_blueprint(commercieel_instellingen_bp)

from handelsorders import handelsorders_bp
app.register_blueprint(handelsorders_bp)

# ============================================================
# GEDEELD FORMULIER-FRAGMENT: bedrijfsprofiel (uitgebreid, naar
# voorbeeld van het externe Zoho-formulier: algemeen, financieel,
# facturatie). Wordt gebruikt door zowel de interne "zelf invullen"
# -pagina als het publieke uitnodigingsformulier.
# ============================================================
def uitgebreid_bedrijfsformulier_html():
    return """
<style>
.ubf-sectiekop { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:0.06em; color:var(--brand-600); margin:22px 0 12px; padding-bottom:8px; border-bottom:1px solid var(--gray-200); }
.ubf-sectiekop:first-of-type { margin-top:0; }
.ubf-label { font-size:10px; letter-spacing:0.06em; text-transform:uppercase; color:var(--gray-400); margin-bottom:4px; display:block; }
.ubf-input { width:100%; padding:9px 11px; border:1px solid var(--gray-200); border-radius:6px; font-size:13.5px; box-sizing:border-box; font-family:inherit; }
.ubf-rij2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:14px; }
.ubf-rij3 { display:grid; grid-template-columns:1fr 1fr 1fr; gap:16px; margin-bottom:14px; }
</style>

<div class="ubf-sectiekop">Algemene bedrijfsgegevens</div>
<div class="ubf-rij2">
    <div><span class="ubf-label">Bedrijfsnaam *</span><input type="text" name="naam" value="{{ waarden.naam|default('',true) }}" required class="ubf-input"></div>
    <div><span class="ubf-label">Land</span><input type="text" name="land" value="{{ waarden.land|default('',true) }}" class="ubf-input"></div>
</div>
<div class="ubf-rij2">
    <div><span class="ubf-label">Adres</span><input type="text" name="adres" value="{{ waarden.adres|default('',true) }}" class="ubf-input"></div>
    <div><span class="ubf-label">Postcode</span><input type="text" name="postcode" value="{{ waarden.postcode|default('',true) }}" class="ubf-input"></div>
</div>
<div class="ubf-rij2">
    <div><span class="ubf-label">Stad/regio</span><input type="text" name="stad" value="{{ waarden.stad|default('',true) }}" class="ubf-input"></div>
    <div><span class="ubf-label">KvK-nummer</span><input type="text" name="kvk_nummer" value="{{ waarden.kvk_nummer|default('',true) }}" class="ubf-input"></div>
</div>
<div class="ubf-rij2">
    <div><span class="ubf-label">Algemeen e-mailadres</span><input type="text" name="email_algemeen" value="{{ waarden.email_algemeen|default('',true) }}" class="ubf-input"></div>
    <div><span class="ubf-label">Telefoonnummer</span><input type="text" name="telefoon" value="{{ waarden.telefoon|default('',true) }}" class="ubf-input"></div>
</div>
<div class="ubf-rij2">
    <div><span class="ubf-label">Contactpersoon (algemeen)</span><input type="text" name="contactpersoon" value="{{ waarden.contactpersoon|default('',true) }}" class="ubf-input"></div>
    <div><span class="ubf-label">Materialen (bv. Paper, Plastic)</span><input type="text" name="materialen" value="{{ waarden.materialen|default('',true) }}" class="ubf-input"></div>
</div>
<div class="ubf-rij2">
    <div><span class="ubf-label">Volume (t/jaar)</span><input type="text" name="volume" value="{{ waarden.volume|default('',true) }}" class="ubf-input"></div>
    <div><span class="ubf-label">Betalingstermijn</span><input type="text" name="betalingstermijn" value="{{ waarden.betalingstermijn|default('',true) }}" placeholder="bv. 30 dagen" class="ubf-input"></div>
</div>

<div class="ubf-sectiekop">Financiële gegevens</div>
<div class="ubf-rij2">
    <div><span class="ubf-label">Naam bank</span><input type="text" name="bank_naam" value="{{ waarden.bank_naam|default('',true) }}" class="ubf-input"></div>
    <div><span class="ubf-label">Begunstigde</span><input type="text" name="begunstigde" value="{{ waarden.begunstigde|default('',true) }}" class="ubf-input"></div>
</div>
<div class="ubf-rij2">
    <div><span class="ubf-label">Bankadres</span><input type="text" name="bank_adres" value="{{ waarden.bank_adres|default('',true) }}" class="ubf-input"></div>
    <div><span class="ubf-label">SWIFT / BIC-code</span><input type="text" name="swift_bic" value="{{ waarden.swift_bic|default('',true) }}" class="ubf-input"></div>
</div>
<div class="ubf-rij3">
    <div><span class="ubf-label">IBAN (EUR)</span><input type="text" name="iban_eur" value="{{ waarden.iban_eur|default('',true) }}" class="ubf-input"></div>
    <div><span class="ubf-label">IBAN (USD)</span><input type="text" name="iban_usd" value="{{ waarden.iban_usd|default('',true) }}" class="ubf-input"></div>
    <div><span class="ubf-label">IBAN (GBP)</span><input type="text" name="iban_gbp" value="{{ waarden.iban_gbp|default('',true) }}" class="ubf-input"></div>
</div>
<div class="ubf-rij2">
    <div><span class="ubf-label">VAT / BTW-nummer</span><input type="text" name="vat_nummer" value="{{ waarden.vat_nummer|default('',true) }}" class="ubf-input"></div>
    <div></div>
</div>

<div class="ubf-sectiekop">Facturatie</div>
<div class="ubf-rij2">
    <div><span class="ubf-label">E-mail voor facturatie</span><input type="text" name="factuur_email" value="{{ waarden.factuur_email|default('',true) }}" class="ubf-input"></div>
    <div><span class="ubf-label">Contactpersoon facturatie</span><input type="text" name="factuur_contactpersoon" value="{{ waarden.factuur_contactpersoon|default('',true) }}" class="ubf-input"></div>
</div>
<div class="ubf-rij2">
    <div><span class="ubf-label">E-mail vragen over betalingen</span><input type="text" name="vragen_betalingen_email" value="{{ waarden.vragen_betalingen_email|default('',true) }}" class="ubf-input"></div>
    <div><span class="ubf-label">E-mail sales-facturatie</span><input type="text" name="sales_facturatie_email" value="{{ waarden.sales_facturatie_email|default('',true) }}" class="ubf-input"></div>
</div>

<div class="ubf-sectiekop">Contact per afdeling</div>
<div class="ubf-rij3">
    <div><span class="ubf-label">E-mail logistiek</span><input type="text" name="email_logistiek" value="{{ waarden.email_logistiek|default('',true) }}" class="ubf-input"></div>
    <div><span class="ubf-label">E-mail finance</span><input type="text" name="email_finance" value="{{ waarden.email_finance|default('',true) }}" class="ubf-input"></div>
    <div><span class="ubf-label">E-mail sales</span><input type="text" name="email_sales" value="{{ waarden.email_sales|default('',true) }}" class="ubf-input"></div>
</div>

<div class="ubf-sectiekop">Overige contacten</div>
<table id="contactenTabel" style="width:100%;border-collapse:collapse;margin-bottom:10px;font-size:12.5px;">
    <thead><tr style="text-align:left;color:var(--gray-400);font-size:10px;text-transform:uppercase;">
        <th style="padding:4px 6px;">Afdeling</th><th style="padding:4px 6px;">Naam</th><th style="padding:4px 6px;">E-mail</th><th style="padding:4px 6px;">Telefoon</th><th style="padding:4px 6px;">Functie</th><th></th>
    </tr></thead>
    <tbody id="contactenTabelBody"></tbody>
</table>
<button type="button" onclick="voegContactRijToe()" style="padding:6px 12px;background:var(--gray-100);color:var(--gray-700);border:none;border-radius:6px;cursor:pointer;font-size:12.5px;font-weight:600;margin-bottom:20px;">+ Contactpersoon toevoegen</button>

<div class="ubf-sectiekop">Depot-adressen</div>
<table id="depotsTabel" style="width:100%;border-collapse:collapse;margin-bottom:10px;font-size:12.5px;">
    <thead><tr style="text-align:left;color:var(--gray-400);font-size:10px;text-transform:uppercase;">
        <th style="padding:4px 6px;">Bedrijfsnaam</th><th style="padding:4px 6px;">Adres</th><th style="padding:4px 6px;">Telefoon</th><th style="padding:4px 6px;">E-mail</th><th style="padding:4px 6px;">Openingsuren</th><th style="padding:4px 6px;">Overig</th><th></th>
    </tr></thead>
    <tbody id="depotsTabelBody"></tbody>
</table>
<button type="button" onclick="voegDepotRijToe()" style="padding:6px 12px;background:var(--gray-100);color:var(--gray-700);border:none;border-radius:6px;cursor:pointer;font-size:12.5px;font-weight:600;margin-bottom:20px;">+ Depot-adres toevoegen</button>

<script>
function voegContactRijToe() {
    var tbody = document.getElementById("contactenTabelBody");
    var rij = document.createElement("tr");
    rij.innerHTML = '<td style="padding:3px;"><input type="text" name="contact_afdeling[]" class="ubf-input" style="font-size:12px;padding:5px 7px;"></td>' +
        '<td style="padding:3px;"><input type="text" name="contact_naam[]" class="ubf-input" style="font-size:12px;padding:5px 7px;"></td>' +
        '<td style="padding:3px;"><input type="text" name="contact_email[]" class="ubf-input" style="font-size:12px;padding:5px 7px;"></td>' +
        '<td style="padding:3px;"><input type="text" name="contact_telefoon[]" class="ubf-input" style="font-size:12px;padding:5px 7px;"></td>' +
        '<td style="padding:3px;"><input type="text" name="contact_functie[]" class="ubf-input" style="font-size:12px;padding:5px 7px;"></td>' +
        '<td style="padding:3px;"><button type="button" onclick="this.closest(\\'tr\\').remove()" style="background:none;border:none;color:var(--gray-300);cursor:pointer;">✕</button></td>';
    tbody.appendChild(rij);
}
function voegDepotRijToe() {
    var tbody = document.getElementById("depotsTabelBody");
    var rij = document.createElement("tr");
    rij.innerHTML = '<td style="padding:3px;"><input type="text" name="depot_naam[]" class="ubf-input" style="font-size:12px;padding:5px 7px;"></td>' +
        '<td style="padding:3px;"><input type="text" name="depot_adres[]" class="ubf-input" style="font-size:12px;padding:5px 7px;"></td>' +
        '<td style="padding:3px;"><input type="text" name="depot_telefoon[]" class="ubf-input" style="font-size:12px;padding:5px 7px;"></td>' +
        '<td style="padding:3px;"><input type="text" name="depot_email[]" class="ubf-input" style="font-size:12px;padding:5px 7px;"></td>' +
        '<td style="padding:3px;"><input type="text" name="depot_openingsuren[]" class="ubf-input" style="font-size:12px;padding:5px 7px;"></td>' +
        '<td style="padding:3px;"><input type="text" name="depot_overig[]" class="ubf-input" style="font-size:12px;padding:5px 7px;"></td>' +
        '<td style="padding:3px;"><button type="button" onclick="this.closest(\\'tr\\').remove()" style="background:none;border:none;color:var(--gray-300);cursor:pointer;">✕</button></td>';
    tbody.appendChild(rij);
}
</script>

<div class="ubf-sectiekop">Overig</div>
<div style="margin-bottom:14px;">
    <span class="ubf-label">Overige informatie</span>
    <textarea name="overige_informatie" rows="3" class="ubf-input" style="resize:vertical;">{{ waarden.overige_informatie|default('',true) }}</textarea>
</div>
    """

def verwerk_bedrijf_toevoegen(form, type_bedrijf, huidige_gebruiker=""):
    """Verwerkt het uitgebreide bedrijfsformulier (gedeeld door de interne 'zelf invullen'-pagina
    en het publieke uitnodigingsformulier). Geeft (succes: bool, boodschap: str, bedrijf_naam: str) terug."""
    naam_nieuw = form.get("naam", "").strip()
    land_nieuw = form.get("land", "").strip()
    stad_nieuw = form.get("stad", "").strip()

    if not naam_nieuw:
        return False, "Bedrijfsnaam is verplicht.", ""

    doellijst = ENF_BEDRIJVEN if type_bedrijf == "leverancier" else PAPIERFABRIEKEN
    if any(b["naam"].strip().lower() == naam_nieuw.lower() and b.get("land","").strip().lower() == land_nieuw.lower() for b in doellijst):
        return False, f"'{naam_nieuw}' ({land_nieuw or 'onbekend land'}) staat al in het systeem.", ""

    velden_tekst = {}
    for veldnaam in ("adres", "postcode", "materialen", "volume", "email_algemeen", "telefoon", "kvk_nummer",
                      "contactpersoon", "betalingstermijn", "bank_naam", "begunstigde", "bank_adres", "swift_bic",
                      "iban_eur", "iban_usd", "iban_gbp", "vat_nummer", "factuur_email", "factuur_contactpersoon",
                      "vragen_betalingen_email", "sales_facturatie_email", "email_logistiek", "email_finance",
                      "email_sales", "overige_informatie"):
        velden_tekst[veldnaam] = form.get(veldnaam, "").strip()

    status_nieuw = form.get("status", "").strip()
    geo = geocode_adres(stad_nieuw, land_nieuw) if (stad_nieuw or land_nieuw) else None

    # Dynamische rijen: "Overige contacten" en "Depot-adressen" (herhaalbare velden, bv. contact_afdeling[])
    overige_contacten = []
    afdelingen = form.getlist("contact_afdeling[]")
    namen_c = form.getlist("contact_naam[]")
    emails_c = form.getlist("contact_email[]")
    telefoons_c = form.getlist("contact_telefoon[]")
    functies_c = form.getlist("contact_functie[]")
    for i in range(len(afdelingen)):
        if not any([afdelingen[i].strip(), namen_c[i].strip() if i < len(namen_c) else "", emails_c[i].strip() if i < len(emails_c) else ""]):
            continue
        overige_contacten.append({
            "afdeling": afdelingen[i].strip(),
            "naam": namen_c[i].strip() if i < len(namen_c) else "",
            "email": emails_c[i].strip() if i < len(emails_c) else "",
            "telefoon": telefoons_c[i].strip() if i < len(telefoons_c) else "",
            "functie": functies_c[i].strip() if i < len(functies_c) else "",
        })

    depot_adressen = []
    depot_namen = form.getlist("depot_naam[]")
    depot_adres_lijst = form.getlist("depot_adres[]")
    depot_telefoons = form.getlist("depot_telefoon[]")
    depot_emails = form.getlist("depot_email[]")
    depot_uren = form.getlist("depot_openingsuren[]")
    depot_overig = form.getlist("depot_overig[]")
    for i in range(len(depot_namen)):
        if not any([depot_namen[i].strip(), depot_adres_lijst[i].strip() if i < len(depot_adres_lijst) else ""]):
            continue
        depot_adressen.append({
            "naam": depot_namen[i].strip(),
            "adres": depot_adres_lijst[i].strip() if i < len(depot_adres_lijst) else "",
            "telefoon": depot_telefoons[i].strip() if i < len(depot_telefoons) else "",
            "email": depot_emails[i].strip() if i < len(depot_emails) else "",
            "openingsuren": depot_uren[i].strip() if i < len(depot_uren) else "",
            "overig": depot_overig[i].strip() if i < len(depot_overig) else "",
        })

    if type_bedrijf == "leverancier":
        nieuw_record = {
            "naam": naam_nieuw, "land": land_nieuw, "regio": stad_nieuw,
            "klanttype": "", "url": "", "lat": geo["lat"] if geo else None, "lon": geo["lon"] if geo else None,
            "bedrijf_id": TENANT_ID, "brontype": "Handmatig ingevoerd",
            "overige_contacten": overige_contacten, "depot_adressen": depot_adressen,
            **velden_tekst,
        }
    else:
        nieuw_record = {
            "naam": naam_nieuw, "land": land_nieuw, "stad": stad_nieuw,
            "lat": geo["lat"] if geo else None, "lon": geo["lon"] if geo else None,
            "overige_contacten": overige_contacten, "depot_adressen": depot_adressen,
            **velden_tekst,
        }
    doellijst.append(nieuw_record)
    bestandsnaam = "bedrijven.json" if type_bedrijf == "leverancier" else "papierfabrieken.json"
    with open(datapad(bestandsnaam), "w", encoding="utf-8") as f:
        json.dump(doellijst, f, ensure_ascii=False, indent=2)

    if huidige_gebruiker:
        alle_am = laad_accountmanagers()
        alle_am[naam_nieuw] = huidige_gebruiker
        bewaar_accountmanagers(alle_am)
    if status_nieuw:
        alle_status = laad_status()
        alle_status[naam_nieuw] = status_nieuw
        bewaar_status(alle_status)

    # Ingevulde contactpersonen automatisch ook in Contacten laten verschijnen
    if velden_tekst.get("contactpersoon"):
        sync_contactpersoon_naar_contacten(naam_nieuw, velden_tekst["contactpersoon"], email=velden_tekst.get("email_algemeen",""), telefoon=velden_tekst.get("telefoon",""), gebruiker=huidige_gebruiker)
    for c in overige_contacten:
        sync_contactpersoon_naar_contacten(naam_nieuw, c.get("naam",""), rol=c.get("functie") or c.get("afdeling",""), email=c.get("email",""), telefoon=c.get("telefoon",""), gebruiker=huidige_gebruiker)

    label = "leveranciers" if type_bedrijf == "leverancier" else "klanten"
    return True, f"'{naam_nieuw}' toegevoegd aan je {label}.", naam_nieuw

@app.route("/bedrijf-toevoegen", methods=["GET", "POST"])
def bedrijf_toevoegen_pagina():
    type_bedrijf = request.args.get("type", "leverancier")
    if type_bedrijf not in ("leverancier", "klant"):
        type_bedrijf = "leverancier"
    terug_url = "/leveranciers" if type_bedrijf == "leverancier" else "/klanten"
    label = "leverancier" if type_bedrijf == "leverancier" else "klant"

    bericht = None
    uitnodiging_link = None

    if request.method == "POST":
        actie = request.form.get("actie", "zelf")
        if actie == "zelf":
            huidige_gebruiker = session.get("gebruikersnaam", "")
            succes, tekst, _ = verwerk_bedrijf_toevoegen(request.form, type_bedrijf, huidige_gebruiker)
            if succes:
                return redirect(terug_url + "?toegevoegd=1")
            bericht = ("fout", tekst)
        elif actie == "uitnodigen":
            email_uitn = request.form.get("uitnodiging_email", "").strip()
            bedrijfsnaam_uitn = request.form.get("uitnodiging_bedrijfsnaam", "").strip()
            naam_uitn = request.form.get("uitnodiging_naam", "").strip()
            if not (email_uitn and bedrijfsnaam_uitn and naam_uitn):
                bericht = ("fout", "E-mail, bedrijfsnaam en naam zijn alle drie verplicht om een uitnodiging te versturen.")
            else:
                token = uuid.uuid4().hex
                alle_uitnodigingen = laad_uitnodigingen()
                alle_uitnodigingen[token] = {
                    "type": type_bedrijf, "email": email_uitn, "bedrijfsnaam": bedrijfsnaam_uitn, "naam": naam_uitn,
                    "verzonden_door": session.get("gebruikersnaam", ""),
                    "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
                    "ingevuld": False, "ingevuld_op": "",
                }
                bewaar_uitnodigingen(alle_uitnodigingen)
                uitnodiging_link = url_for("profiel_invullen", token=token, _external=True)
                bericht = ("succes", f"Uitnodigingslink aangemaakt voor {bedrijfsnaam_uitn}.")

    inhoud = """
<div style="padding-left:20px;max-width:820px;">
    <a href="{{ terug_url }}" style="color:var(--gray-400);text-decoration:none;font-size:0.85rem;">← Terug naar {{ 'Leveranciers' if type_bedrijf == 'leverancier' else 'Klanten' }}</a>
    <div style="font-size:28px;font-weight:600;letter-spacing:-0.02em;color:var(--gray-900);margin:8px 0 20px;">Nieuwe {{ label }} toevoegen</div>

    <div style="display:flex;gap:8px;margin-bottom:20px;">
        <button type="button" onclick="wisselModus('zelf')" id="tabZelfBtn" class="tvf-modus-tab actief">Zelf invullen</button>
        <button type="button" onclick="wisselModus('uitnodigen')" id="tabUitnodigenBtn" class="tvf-modus-tab">Formulier versturen</button>
    </div>

    {% if bericht %}
    <div style="background:{{ '#f0fdf4' if bericht[0] == 'succes' else '#fef2f2' }};color:{{ '#16a34a' if bericht[0] == 'succes' else '#dc2626' }};padding:10px 16px;border-radius:8px;margin-bottom:16px;font-size:13.5px;">{{ bericht[1] }}</div>
    {% endif %}
    {% if uitnodiging_link %}
    <div style="background:#fff;border:1px solid var(--gray-200);border-radius:10px;padding:16px 18px;margin-bottom:20px;">
        <div class="ubf-label">Uitnodigingslink</div>
        <div style="display:flex;gap:8px;align-items:center;">
            <input type="text" readonly value="{{ uitnodiging_link }}" id="uitnodigingLinkVeld" style="flex:1;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;background:var(--gray-50);">
            <button type="button" onclick="kopieerLink()" style="padding:8px 14px;background:var(--gray-100);color:var(--gray-700);border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;">Kopieer</button>
        </div>
        <a id="mailtoLink" href="#" style="display:inline-block;margin-top:10px;padding:8px 16px;background:var(--brand-600);color:#fff;border-radius:6px;text-decoration:none;font-size:13px;font-weight:600;">✉ Open in e-mailprogramma</a>
    </div>
    {% endif %}

    <style>
    .tvf-modus-tab { padding:8px 16px; border-radius:6px; font-size:13px; font-weight:600; border:1px solid var(--gray-200); background:#fff; color:var(--gray-600); cursor:pointer; }
    .tvf-modus-tab.actief { background:var(--brand-600); color:#fff; border-color:var(--brand-600); }
    </style>

    <div id="modusZelf">
        <form method="POST">
            <input type="hidden" name="actie" value="zelf">
            {{ formulier_html|safe }}
            <button type="submit" style="padding:10px 20px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-weight:600;cursor:pointer;font-size:13.5px;">+ {{ label|capitalize }} toevoegen</button>
        </form>
    </div>

    <div id="modusUitnodigen" style="display:none;background:#fff;border:1px solid var(--gray-200);border-radius:10px;padding:20px 22px;">
        <p style="font-size:13px;color:var(--gray-500);margin-bottom:16px;">De {{ label }} ontvangt een link naar een openbaar formulier en vult zijn eigen bedrijfsgegevens in. Vul de volgende 3 dingen in om de link aan te maken:</p>
        <form method="POST">
            <input type="hidden" name="actie" value="uitnodigen">
            <div class="ubf-rij3">
                <div><span class="ubf-label">E-mailadres *</span><input type="email" name="uitnodiging_email" required class="ubf-input"></div>
                <div><span class="ubf-label">Bedrijfsnaam *</span><input type="text" name="uitnodiging_bedrijfsnaam" required class="ubf-input"></div>
                <div><span class="ubf-label">Naam contactpersoon *</span><input type="text" name="uitnodiging_naam" required class="ubf-input"></div>
            </div>
            <button type="submit" style="padding:10px 20px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-weight:600;cursor:pointer;font-size:13.5px;">Link aanmaken</button>
        </form>
    </div>
</div>

<script>
function wisselModus(modus) {
    document.getElementById("modusZelf").style.display = modus === "zelf" ? "block" : "none";
    document.getElementById("modusUitnodigen").style.display = modus === "uitnodigen" ? "block" : "none";
    document.getElementById("tabZelfBtn").classList.toggle("actief", modus === "zelf");
    document.getElementById("tabUitnodigenBtn").classList.toggle("actief", modus === "uitnodigen");
}
function kopieerLink() {
    var veld = document.getElementById("uitnodigingLinkVeld");
    veld.select();
    document.execCommand("copy");
}
{% if uitnodiging_link %}
(function() {
    var onderwerp = encodeURIComponent("Vul jullie bedrijfsprofiel in bij Peute");
    var body = encodeURIComponent("Beste,\\n\\nKun je onderstaande link openen om jullie bedrijfsgegevens bij ons in te vullen?\\n\\n{{ uitnodiging_link }}\\n\\nMet vriendelijke groet,\\nPeute Papierrecycling");
    document.getElementById("mailtoLink").href = "mailto:{{ uitnodiging_email_js }}?subject=" + onderwerp + "&body=" + body;
})();
{% endif %}
</script>
    """
    pagina = render_simple_page(f"Nieuwe {label}", "leveranciers" if type_bedrijf == "leverancier" else "klanten", inhoud)
    return render_template_string(pagina, terug_url=terug_url, type_bedrijf=type_bedrijf, label=label,
                                    bericht=bericht, uitnodiging_link=uitnodiging_link,
                                    uitnodiging_email_js=request.form.get("uitnodiging_email", "") if request.method == "POST" else "",
                                    formulier_html=uitgebreid_bedrijfsformulier_html(), waarden={})

PROFIEL_INVULLEN_HTML_KOP = """
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bedrijfsprofiel invullen — Peute Papierrecycling</title>
    <link href="https://fonts.googleapis.com/css2?family=Libre+Franklin:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --brand-50:#eef6f6; --brand-100:#d9ecec; --brand-200:#b3d9da; --brand-300:#7fb9bb;
            --brand-400:#3f9295; --brand-500:#14767b; --brand-600:#0d5c62; --brand-700:#0a4a4f;
            --gray-50:#f8fafc; --gray-100:#f1f5f9; --gray-200:#e2e8f0; --gray-300:#cbd5e1;
            --gray-400:#94a3b8; --gray-500:#64748b; --gray-600:#475569; --gray-700:#334155;
            --gray-800:#1e293b; --gray-900:#0f172a; --font:"Libre Franklin",sans-serif;
        }
        * { box-sizing:border-box; }
        body { font-family:var(--font); background:var(--gray-50); margin:0; padding:40px 20px; }
        .pi-kaart { max-width:820px; margin:0 auto; background:#fff; border:1px solid var(--gray-200); border-radius:14px; padding:32px 36px; }
        .pi-logo { font-size:1.3rem; font-weight:800; color:var(--gray-900); margin-bottom:4px; }
        .pi-logo em { color:var(--brand-600); font-style:normal; }
        .pi-sub { font-size:0.85rem; color:var(--gray-400); margin-bottom:28px; }
    </style>
</head>
<body>
<div class="pi-kaart">
    <div class="pi-logo">Peute <em>Papierrecycling</em></div>
"""

@app.route("/profiel-invullen/<token>", methods=["GET", "POST"])
def profiel_invullen(token):
    alle_uitnodigingen = laad_uitnodigingen()
    uitnodiging = alle_uitnodigingen.get(token)

    if not uitnodiging:
        return PROFIEL_INVULLEN_HTML_KOP + '<div class="pi-sub">Deze link is niet (meer) geldig. Neem contact op met Peute Papierrecycling voor een nieuwe link.</div></div></body></html>', 404

    if uitnodiging.get("ingevuld"):
        return PROFIEL_INVULLEN_HTML_KOP + '<div class="pi-sub">Dit formulier is al ingevuld. Bedankt! Neem contact op met Peute Papierrecycling als er iets moet worden aangepast.</div></div></body></html>'

    bericht = None
    if request.method == "POST":
        succes, tekst, _ = verwerk_bedrijf_toevoegen(request.form, uitnodiging["type"], "")
        if succes:
            uitnodiging["ingevuld"] = True
            uitnodiging["ingevuld_op"] = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
            bewaar_uitnodigingen(alle_uitnodigingen)
            return PROFIEL_INVULLEN_HTML_KOP + '<div class="pi-sub">Bedankt! Jullie bedrijfsgegevens zijn ontvangen.</div></div></body></html>'
        bericht = ("fout", tekst)

    inhoud = PROFIEL_INVULLEN_HTML_KOP + """
    <div class="pi-sub">Kunt u onderstaand formulier invullen zodat wij jullie gegevens correct hebben staan?</div>
    {% if bericht %}<div style="background:#fef2f2;color:#dc2626;padding:10px 16px;border-radius:8px;margin-bottom:16px;font-size:13.5px;">{{ bericht[1] }}</div>{% endif %}
    <form method="POST">
        """ + uitgebreid_bedrijfsformulier_html() + """
        <button type="submit" style="padding:11px 22px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-weight:600;cursor:pointer;font-size:14px;">Versturen</button>
    </form>
</div>
</body>
</html>
    """
    waarden = {"naam": uitnodiging.get("bedrijfsnaam", ""), "contactpersoon": uitnodiging.get("naam", ""), "email_algemeen": uitnodiging.get("email", "")}
    return render_template_string(inhoud, bericht=bericht, waarden=waarden)

_CSRF_VRIJGESTELDE_ENDPOINTS = {"login", "static", "forwarder_upload", "profiel_invullen"}

@app.before_request
def valideer_csrf_token():
    """Centrale CSRF-bescherming voor de hele app. Het token zelf wordt altijd
    beschikbaar gemaakt (ook op GET, zodat een formulier het al heeft vóór de
    eerste keer versturen); de daadwerkelijke check geldt alleen voor
    state-wijzigende requests. Vrijgesteld: 'login' (CSRF hierop is een laag
    risico t.o.v. het risico dat een fout hier iedereen buitensluit), en
    'forwarder_upload'/'profiel_invullen' (externe, niet-ingelogde pagina's
    met hun EIGEN toegangsbeveiliging — forwarder-wachtwoord resp. een
    geheime uitnodigingslink — die niet via render_simple_page lopen en dus
    het token niet automatisch krijgen)."""
    haal_of_maak_csrf_token()
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        if request.endpoint in _CSRF_VRIJGESTELDE_ENDPOINTS:
            return
        verstuurd = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        verwacht = session.get("csrf_token")
        if not verstuurd or not verwacht or not secrets.compare_digest(verstuurd, verwacht):
            if request.path.startswith("/api/"):
                return jsonify({"error": "Ongeldige sessie (CSRF-token ontbreekt of is verlopen). Herlaad de pagina en probeer opnieuw."}), 400
            pagina = render_simple_page("Sessie verlopen", "", '<div class="page-title">Sessie verlopen</div><div class="lege-staat">Je sessie is verlopen of het formulier was verouderd. Herlaad de pagina en probeer het opnieuw.</div>')
            return render_template_string(pagina), 400

@app.before_request
def vereis_login():
    toegestaan = ["login", "static", "forwarder_upload", "profiel_invullen"]
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
            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
            <input type="file" name="bestand" accept=".xlsx,.xls" required>
            <button type="submit">Importeren</button>
        </form>
        <table>
            <tr><th>Naam</th><th>Type</th><th>Land</th><th>Stad</th><th>Adres</th><th>Telefoonnummer</th><th>Materialen</th><th>Klanttype</th><th>Volume</th><th>Certificeringen</th></tr>
            <tr><td>Voorbeeld BV</td><td>Leverancier</td><td>Netherlands</td><td>Rotterdam</td><td>Kade 12</td><td>+31 10 1234567</td><td>Paper, Plastic</td><td>Commercial</td><td>5000</td><td>ISO 9001, FSC</td></tr>
            <tr><td>Fabriek XYZ</td><td>Fabriek</td><td>Germany</td><td>Hamburg</td><td></td><td></td><td>Paper, OCC</td><td></td><td></td></tr>
        </table>
        <a href="/importeer-osm" style="display:block;text-align:center;margin-top:16px;font-size:13px;color:#0d5c62;">→ Of importeer automatisch vanuit OpenStreetMap (gratis, geen bestand nodig)</a>
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

def scrapmonster_importeer_land(land_naam, max_paginas=50):
    """Scrapet ScrapMonster.com voor schroothandels/recyclingcentra per land. Geeft (aantal_nieuw, aantal_gezien) terug."""
    slug = SCRAPMONSTER_LANDEN.get(land_naam)
    if not slug:
        raise ValueError(f"Onbekend land voor ScrapMonster: {land_naam}")

    bestaande = {(b["naam"].strip().lower(), b["land"].strip().lower(), b.get("regio","").strip().lower()) for b in ENF_BEDRIJVEN}
    aantal_nieuw = 0
    aantal_gezien = 0
    pagina_zonder_nieuw_op_rij = 0

    for pagina in range(1, max_paginas + 1):
        url = f"https://www.scrapmonster.com/scrap-yard/{slug}/" if pagina == 1 else f"https://www.scrapmonster.com/scrap-yard/{slug}/page/{pagina}"
        try:
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (FTNext/1.0)"}, timeout=30)
        except Exception:
            break
        if resp.status_code != 200:
            break

        html_tekst = resp.text
        # Elke bedrijfsnaam-link staat in <div class="companynamehead"><a href="https://www.scrapmonster.com/scrap-yard/<slug>/<id>">Naam</a></div>
        yard_pattern = re.compile(
            r'<div class="companynamehead"><a href="https://www\.scrapmonster\.com/scrap-yard/[a-z0-9\-]+/\d+">([^<]*)</a>'
        )
        matches = list(yard_pattern.finditer(html_tekst))
        if not matches:
            break

        gevonden_deze_pagina = 0
        nieuw_deze_pagina = 0
        for i, m in enumerate(matches):
            naam = m.group(1).strip()
            naam = re.sub(r"\s*-\s*$", "", naam).strip()  # ScrapMonster zet soms een lege " - " achter de naam
            if not naam or len(naam) < 2:
                continue
            gevonden_deze_pagina += 1
            aantal_gezien += 1

            # Kaart-tekst = alles tussen deze link en de volgende (of een vast venster bij de laatste)
            start = m.end()
            eind = matches[i + 1].start() if i + 1 < len(matches) else min(len(html_tekst), start + 3000)
            kaart_segment = html_tekst[start:eind]

            telefoon_match = re.search(r"tel:([+\d()\-\s]{6,20})", kaart_segment)
            telefoon = telefoon_match.group(1).strip() if telefoon_match else ""

            stad = ""
            straat = ""
            adres_match = re.search(r'<div class="yardaddress">(.*?)</div>', kaart_segment, re.S)
            if adres_match:
                regels_ruw = re.split(r"<br\s*/?>", adres_match.group(1))
                regels = [re.sub(r"<[^>]+>", "", r).strip() for r in regels_ruw]
                regels = [r for r in regels if r]
                if len(regels) >= 1:
                    stad = regels[0]
                if len(regels) >= 2:
                    straat = regels[1]

            sleutel = (naam.strip().lower(), land_naam.strip().lower(), stad.strip().lower())
            if sleutel in bestaande:
                continue
            bestaande.add(sleutel)
            nieuw_deze_pagina += 1

            _geo = geocode_adres(straat, stad) if (straat and stad) else None
            ENF_BEDRIJVEN.append({
                "naam": naam, "land": land_naam, "regio": stad,
                "materialen": "Metal", "klanttype": "", "volume": "", "url": "",
                "lat": _geo["lat"] if _geo else None, "lon": _geo["lon"] if _geo else None,
                "adres": straat, "telefoon": telefoon,
                "bedrijf_id": TENANT_ID, "brontype": "Schroothandel",
            })
            aantal_nieuw += 1

        if gevonden_deze_pagina == 0:
            break

        if nieuw_deze_pagina == 0:
            pagina_zonder_nieuw_op_rij += 1
        else:
            pagina_zonder_nieuw_op_rij = 0
        if pagina_zonder_nieuw_op_rij >= 3:
            break

        time.sleep(2)

    # Geocoderen van de nieuw toegevoegde bedrijven zonder coördinaten (op basis van stad + land)
    for b in ENF_BEDRIJVEN:
        if b.get("bedrijf_id") == TENANT_ID and b.get("brontype") == "Schroothandel" and not b.get("lat") and b.get("land") == land_naam:
            geo = geocode_adres(b.get("regio",""), land_naam)
            if geo:
                b["lat"] = geo["lat"]
                b["lon"] = geo["lon"]

    bewaar_bedrijven()

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
        button { background: #0d5c62; color: white; border: none; cursor: pointer; font-weight: 600; }
        .bericht { padding: 10px; border-radius: 6px; margin-bottom: 12px; font-size: 14px; }
        .succes { background: #f0fdf4; color: #16a34a; }
        .fout { background: #fef2f2; color: #ef4444; }
    </style>
</head>
<body>
    <div class="box">
        <h1>Bedrijven importeren via ScrapMonster</h1>
        <p>Haalt schroothandels/recyclingcentra op van scrapmonster.com voor het gekozen land (max. 50 pagina's, tot ~1000 bedrijven). Kan 2-3 minuten duren per land.</p>
        {% if bericht %}<div class="bericht {{ 'succes' if succes else 'fout' }}">{{ bericht }}</div>{% endif %}
        <form method="POST">
            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
            <select name="land" required>
                {% for naam in landen %}<option value="{{ naam }}">{{ naam }}</option>{% endfor %}
            </select>
            <button type="submit">Importeren vanuit ScrapMonster</button>
        </form>
        <a href="/importeer-scrapmonster-alle" style="display:block;text-align:center;margin-top:16px;font-size:13px;color:#0d5c62;">→ Of importeer in één keer álle landen op de achtergrond</a>
    </div>
</body>
</html>
'''

# ============================================
# UK OVERHEIDSREGISTER (Waste Carriers, Brokers and Dealers)
# ============================================
GOV_UK_TREFWOORDEN = [
    "recycl", "scrap", "waste", "skip", "salvage", "reclamation", "metal",
    "demolition", "haulage", "disposal", "environmental services", "container",
    "aggregate", "landfill", "tip ", "materials recovery", "mrf",
]

GOV_UK_BULK_STATUS = {"bezig": False, "voortgang": "", "totaal_gezien": 0, "totaal_nieuw": 0, "klaar": False, "fout": ""}

def _gov_uk_bulk_worker(gebruikersnaam, max_nieuw=3000):
    import zipfile, io as io_module, csv as csv_module

    GOV_UK_BULK_STATUS.update({"bezig": True, "klaar": False, "fout": "", "voortgang": "Bestand downloaden...", "totaal_gezien": 0, "totaal_nieuw": 0})
    try:
        resp = requests.get("https://environment.data.gov.uk/public-register/downloads/waste-carriers-brokers",
                             headers={"User-Agent": "Mozilla/5.0 (FTNext/1.0)"}, timeout=180)
        zip_bestand = zipfile.ZipFile(io_module.BytesIO(resp.content))
        csv_naam = next(n for n in zip_bestand.namelist() if n.lower().endswith(".csv"))

        GOV_UK_BULK_STATUS["voortgang"] = "Bestand inlezen en filteren..."
        bestaande = {(b["naam"].strip().lower(), b["land"].strip().lower(), b.get("regio","").strip().lower()) for b in ENF_BEDRIJVEN}
        aantal_nieuw = 0
        aantal_gezien = 0
        nieuwe_bedrijven_tmp = []

        with zip_bestand.open(csv_naam) as f:
            tekst_stream = io_module.TextIOWrapper(f, encoding="utf-8", errors="replace")
            lezer = csv_module.DictReader(tekst_stream)
            for rij in lezer:
                aantal_gezien += 1
                if aantal_gezien % 20000 == 0:
                    GOV_UK_BULK_STATUS["voortgang"] = f"{aantal_gezien} regels doorzocht, {aantal_nieuw} relevante gevonden..."
                    GOV_UK_BULK_STATUS["totaal_gezien"] = aantal_gezien

                if aantal_nieuw >= max_nieuw:
                    break

                naam = (rij.get("Business Name") or "").strip()
                tier = (rij.get("Registration Tier") or "").strip()
                if not naam or tier != "Upper":
                    continue
                naam_laag = naam.lower()
                if not any(kw in naam_laag for kw in GOV_UK_TREFWOORDEN):
                    continue

                adres = (rij.get("Address") or "").strip()
                postcode = (rij.get("Postcode") or "").strip()
                stad = ""
                adresdelen = [d.strip() for d in adres.split(",") if d.strip()]
                if len(adresdelen) >= 2:
                    stad = adresdelen[-2]

                sleutel = (naam.lower(), "united kingdom", stad.lower())
                if sleutel in bestaande:
                    continue
                bestaande.add(sleutel)

                # Voorzichtige materiaal-gok: alleen bij duidelijke signalen, anders leeg laten (liever niks dan fout gokken)
                gegokt_materiaal = ""
                if any(w in naam_laag for w in ("metal", "scrap")):
                    gegokt_materiaal = "Metal"

                _geo = geocode_adres(adres, stad) if (adres and stad) else None
                nieuwe_bedrijven_tmp.append({
                    "naam": naam, "land": "United Kingdom", "regio": stad,
                    "materialen": gegokt_materiaal, "klanttype": "", "volume": "", "url": "",
                    "lat": _geo["lat"] if _geo else None, "lon": _geo["lon"] if _geo else None,
                    "adres": adres, "telefoon": "",
                    "bedrijf_id": TENANT_ID, "brontype": "Afvalbeheer",
                })
                aantal_nieuw += 1

        aantal_failliet = 0
        if COMPANIES_HOUSE_API_KEY:
            GOV_UK_BULK_STATUS["voortgang"] = f"Financiële status checken bij Companies House ({len(nieuwe_bedrijven_tmp)} bedrijven)..."
            nog_gezond = []
            for i, b in enumerate(nieuwe_bedrijven_tmp):
                if is_ch_financieel_gezond(b["naam"]):
                    nog_gezond.append(b)
                else:
                    aantal_failliet += 1
                if i % 20 == 0:
                    GOV_UK_BULK_STATUS["voortgang"] = f"Companies House-check: {i+1}/{len(nieuwe_bedrijven_tmp)} ({aantal_failliet} failliet overgeslagen)..."
            nieuwe_bedrijven_tmp = nog_gezond
            aantal_nieuw = len(nieuwe_bedrijven_tmp)

        GOV_UK_BULK_STATUS["voortgang"] = f"Geocoderen van {len(nieuwe_bedrijven_tmp)} nieuwe bedrijven..."
        for i, b in enumerate(nieuwe_bedrijven_tmp):
            zoekterm = b.get("regio") or b.get("adres","").split(",")[0]
            geo = geocode_adres(zoekterm, "United Kingdom")
            if geo:
                b["lat"] = geo["lat"]
                b["lon"] = geo["lon"]
            ENF_BEDRIJVEN.append(b)
            if i % 25 == 0:
                GOV_UK_BULK_STATUS["voortgang"] = f"Geocoderen: {i+1}/{len(nieuwe_bedrijven_tmp)}..."

        bewaar_bedrijven()

        dubbel, _ = opschonen_bedrijven_en_fabrieken("streng")

        GOV_UK_BULK_STATUS["totaal_gezien"] = aantal_gezien
        GOV_UK_BULK_STATUS["totaal_nieuw"] = aantal_nieuw
        GOV_UK_BULK_STATUS["voortgang"] = "Klaar!"

        if gebruikersnaam:
            alle_meldingen = laad_meldingen()
            alle_meldingen.append({
                "id": str(uuid.uuid4()),
                "tekst": f"UK overheidsregister-import klaar! {aantal_nieuw} nieuwe bedrijven toegevoegd (van {aantal_gezien} doorzochte registraties). {aantal_failliet} failliete/ontbonden bedrijven overgeslagen. {dubbel} dubbelingen opgeschoond.",
                "bedrijf": "", "van": "Systeem", "voor_gebruiker": gebruikersnaam, "voor_team": "",
                "gelezen": False, "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
            })
            bewaar_meldingen(alle_meldingen)
    except Exception as e:
        GOV_UK_BULK_STATUS["fout"] = str(e)
        GOV_UK_BULK_STATUS["voortgang"] = f"Fout: {e}"
    finally:
        GOV_UK_BULK_STATUS["bezig"] = False
        GOV_UK_BULK_STATUS["klaar"] = True

@app.route("/importeer-gov-uk", methods=["GET", "POST"])
def importeer_gov_uk():
    _guard = vereist_admin_of_403()
    if _guard: return _guard
    if request.method == "POST":
        if not GOV_UK_BULK_STATUS["bezig"]:
            gebruikersnaam = session.get("gebruikersnaam", "")
            thread = threading.Thread(target=_gov_uk_bulk_worker, args=(gebruikersnaam,), daemon=True)
            thread.start()
        return redirect(url_for("importeer_gov_uk"))

    inhoud = """
<style>
.bulk-log { max-height:200px; overflow-y:auto; background:var(--gray-50); border-radius:8px; padding:12px; font-size:0.85rem; margin-top:16px; }
</style>
<div class="page-title">UK overheidsregister importeren</div>
<div class="info-kaart" style="max-width:600px;">
    <p style="color:var(--gray-500);font-size:0.85rem;margin-bottom:16px;">
        Haalt het officiële Environment Agency-register van geregistreerde afvalvervoerders/-makelaars/-handelaars op (Engeland),
        filtert op Upper Tier + recycling-gerelateerde bedrijfsnamen (dus geen tuinmannen/loodgieters), en importeert max. 3000 nieuwe bedrijven.
        Kan enkele minuten duren door geocoding.
    </p>
    <div id="knopWrap">
        <button onclick="start()" style="padding:10px 20px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-weight:600;cursor:pointer;">Start import</button>
    </div>
    <div id="statusWrap" style="display:none;margin-top:16px;">
        <div id="voortgangTekst" style="font-size:0.85rem;color:var(--gray-600);">Bezig...</div>
    </div>
</div>
<script>
function start() {
    fetch("/importeer-gov-uk", {method:"POST"}).then(() => poll());
    document.getElementById("knopWrap").style.display = "none";
    document.getElementById("statusWrap").style.display = "block";
}
async function poll() {
    const res = await fetch("/api/gov-uk-import-status");
    const data = await res.json();
    document.getElementById("voortgangTekst").textContent = data.voortgang + (data.totaal_nieuw ? ` (${data.totaal_nieuw} nieuw tot nu toe)` : "");
    if (data.bezig) { setTimeout(poll, 3000); }
}
fetch("/api/gov-uk-import-status").then(r => r.json()).then(data => {
    if (data.bezig) {
        document.getElementById("knopWrap").style.display = "none";
        document.getElementById("statusWrap").style.display = "block";
        poll();
    }
});
</script>
    """
    pagina = render_simple_page("UK overheidsregister importeren", "zoeken", inhoud)
    return render_template_string(pagina)

@app.route("/api/gov-uk-import-status")
def gov_uk_import_status():
    return jsonify(GOV_UK_BULK_STATUS)

CH_CLEANUP_STATUS = {"bezig": False, "voortgang": "", "gecontroleerd": 0, "totaal": 0, "verwijderd": 0, "klaar": False, "fout": ""}

def _ch_cleanup_worker(gebruikersnaam):
    CH_CLEANUP_STATUS.update({"bezig": True, "klaar": False, "fout": "", "gecontroleerd": 0, "verwijderd": 0})
    try:
        if not COMPANIES_HOUSE_API_KEY:
            CH_CLEANUP_STATUS["fout"] = "Geen COMPANIES_HOUSE_API_KEY ingesteld op Railway."
            return

        uk_bedrijven = [b for b in ENF_BEDRIJVEN if b.get("land","").strip().lower() == "united kingdom"]
        CH_CLEANUP_STATUS["totaal"] = len(uk_bedrijven)
        te_verwijderen_namen = set()

        for i, b in enumerate(uk_bedrijven):
            if not is_ch_financieel_gezond(b["naam"]):
                te_verwijderen_namen.add((b["naam"], b.get("regio","")))
                CH_CLEANUP_STATUS["verwijderd"] += 1
            CH_CLEANUP_STATUS["gecontroleerd"] = i + 1
            if i % 20 == 0:
                CH_CLEANUP_STATUS["voortgang"] = f"{i+1}/{len(uk_bedrijven)} gecontroleerd, {CH_CLEANUP_STATUS['verwijderd']} failliet/ontbonden gevonden..."

        if te_verwijderen_namen:
            ENF_BEDRIJVEN[:] = [b for b in ENF_BEDRIJVEN if (b["naam"], b.get("regio","")) not in te_verwijderen_namen or b.get("land","").strip().lower() != "united kingdom"]
            bewaar_bedrijven()

        CH_CLEANUP_STATUS["voortgang"] = "Klaar!"

        if gebruikersnaam:
            alle_meldingen = laad_meldingen()
            alle_meldingen.append({
                "id": str(uuid.uuid4()),
                "tekst": f"UK-controle klaar! {CH_CLEANUP_STATUS['gecontroleerd']} bedrijven gecontroleerd bij Companies House, {CH_CLEANUP_STATUS['verwijderd']} failliete/ontbonden bedrijven verwijderd.",
                "bedrijf": "", "van": "Systeem", "voor_gebruiker": gebruikersnaam, "voor_team": "",
                "gelezen": False, "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
            })
            bewaar_meldingen(alle_meldingen)
    except Exception as e:
        CH_CLEANUP_STATUS["fout"] = str(e)
    finally:
        CH_CLEANUP_STATUS["bezig"] = False
        CH_CLEANUP_STATUS["klaar"] = True

@app.route("/controleer-uk-status", methods=["GET", "POST"])
def controleer_uk_status():
    _guard = vereist_admin_of_403()
    if _guard: return _guard
    if request.method == "POST":
        if not CH_CLEANUP_STATUS["bezig"]:
            gebruikersnaam = session.get("gebruikersnaam", "")
            thread = threading.Thread(target=_ch_cleanup_worker, args=(gebruikersnaam,), daemon=True)
            thread.start()
        return redirect(url_for("controleer_uk_status"))

    inhoud = """
<div class="page-title">UK-bedrijven controleren (Companies House)</div>
<div class="info-kaart" style="max-width:600px;">
    <p style="color:var(--gray-500);font-size:0.85rem;margin-bottom:16px;">
        Controleert al je bestaande UK-bedrijven bij Companies House en verwijdert bedrijven met status
        "dissolved", "liquidation", "administration" of vergelijkbaar. Kan lang duren bij veel UK-bedrijven
        (ca. 2 per seconde, dus 1000 bedrijven ≈ 8 minuten).
    </p>
    <div id="knopWrap">
        <button onclick="start()" style="padding:10px 20px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-weight:600;cursor:pointer;">Start controle</button>
    </div>
    <div id="statusWrap" style="display:none;margin-top:16px;">
        <div id="voortgangTekst" style="font-size:0.85rem;color:var(--gray-600);">Bezig...</div>
    </div>
</div>
<script>
function start() {
    fetch("/controleer-uk-status", {method:"POST"}).then(() => poll());
    document.getElementById("knopWrap").style.display = "none";
    document.getElementById("statusWrap").style.display = "block";
}
async function poll() {
    const res = await fetch("/api/ch-cleanup-status");
    const data = await res.json();
    let tekst = data.voortgang || "Bezig...";
    if (data.fout) tekst = "Fout: " + data.fout;
    document.getElementById("voortgangTekst").textContent = tekst;
    if (data.bezig) { setTimeout(poll, 3000); }
}
fetch("/api/ch-cleanup-status").then(r => r.json()).then(data => {
    if (data.bezig) {
        document.getElementById("knopWrap").style.display = "none";
        document.getElementById("statusWrap").style.display = "block";
        poll();
    }
});
</script>
    """
    pagina = render_simple_page("UK-bedrijven controleren", "zoeken", inhoud)
    return render_template_string(pagina)

@app.route("/api/ch-cleanup-status")
def ch_cleanup_status():
    return jsonify(CH_CLEANUP_STATUS)

@app.route("/debug-gov-uk-register")
def debug_gov_uk_register():
    _guard = vereist_admin_of_403()
    if _guard: return _guard
    import zipfile
    import io as io_module

    url = "https://environment.data.gov.uk/public-register/downloads/waste-carriers-brokers"
    info = f"URL: {url}\n\n"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (FTNext/1.0)"}, timeout=60)
        info += f"Status: {resp.status_code}\nContent-Type: {resp.headers.get('Content-Type')}\nGrootte: {len(resp.content)} bytes\n\n"

        if resp.status_code == 200:
            zip_bestand = zipfile.ZipFile(io_module.BytesIO(resp.content))
            info += f"Bestanden in de zip:\n"
            for naam in zip_bestand.namelist():
                info += f"  - {naam} ({zip_bestand.getinfo(naam).file_size} bytes)\n"
            info += "\n"

            csv_bestanden = [n for n in zip_bestand.namelist() if n.lower().endswith(".csv")]
            if csv_bestanden:
                eerste_csv = csv_bestanden[0]
                with zip_bestand.open(eerste_csv) as f:
                    inhoud = f.read().decode("utf-8", errors="replace")
                info += f"--- EERSTE 2000 TEKENS VAN {eerste_csv} ---\n\n"
                info += inhoud[:2000]
    except Exception as e:
        info += f"FOUT: {e}"

    from markupsafe import escape
    return f"<pre style='white-space:pre-wrap;font-size:12px;padding:20px;'>{escape(info)}</pre>"

@app.route("/debug-scrapmonster")
def debug_scrapmonster():
    _guard = vereist_admin_of_403()
    if _guard: return _guard
    land_naam = request.args.get("land", "Netherlands")
    slug = SCRAPMONSTER_LANDEN.get(land_naam, "netherlands")
    url = f"https://www.scrapmonster.com/scrap-yard/{slug}/"
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (FTNext/1.0)"}, timeout=30)
        info = f"URL: {url}\nStatus: {resp.status_code}\nContent-Length: {len(resp.text)}\n\n"
        info += f"Aantal keer '/scrap-yard/' in de HTML: {resp.text.count('/scrap-yard/')}\n"
        info += f"Aantal keer 'tel:' in de HTML: {resp.text.count('tel:')}\n\n"

        # Zoek de eerste individuele bedrijfslink (met numeriek ID erachter) en toon de omgeving
        m = re.search(r'/scrap-yard/[a-z0-9\-]+/\d+', resp.text)
        if m:
            start = max(0, m.start() - 400)
            eind = min(len(resp.text), m.start() + 1200)
            info += f"--- CONTEXT ROND EERSTE BEDRIJFSLINK (positie {m.start()}) ---\n\n"
            info += resp.text[start:eind]
        else:
            info += "--- GEEN patroon '/scrap-yard/<naam>/<cijfers>' gevonden. Eerste 2000 tekens: ---\n\n"
            info += resp.text[:2000]
    except Exception as e:
        info = f"FOUT bij ophalen: {e}"
    from markupsafe import escape
    return f"<pre style='white-space:pre-wrap;font-size:12px;padding:20px;'>{escape(info)}</pre>"

@app.route("/importeer-scrapmonster", methods=["GET", "POST"])
def importeer_scrapmonster():
    _guard = vereist_admin_of_403()
    if _guard: return _guard
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
    _guard = vereist_admin_of_403()
    if _guard: return _guard
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
        button { background: #0d5c62; color: white; border: none; cursor: pointer; font-weight: 600; }
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
            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
            <select name="land" required>
                {% for naam in landen %}<option value="{{ naam }}">{{ naam }}</option>{% endfor %}
            </select>
            <button type="submit">Importeren vanuit OpenStreetMap</button>
        </form>
        <a href="/importeer-osm-alle" style="display:block;text-align:center;margin-top:16px;font-size:13px;color:#0d5c62;">→ Of importeer in één keer álle landen op de achtergrond</a>
        <a href="/importeer-scrapmonster" style="display:block;text-align:center;margin-top:8px;font-size:13px;color:#0d5c62;">→ Of importeer schroothandels vanuit ScrapMonster.com</a>
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
        button { width: 100%; padding: 10px; background: #0d5c62; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 14px; margin-top:8px; }
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
            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
            <label><input type="radio" name="modus" value="normaal" checked> <b>Normaal</b> — zelfde naam + land + stad</label>
            <label><input type="radio" name="modus" value="streng"> <b>Streng</b> — alleen zelfde naam + land (negeert verschillen in stad-notatie, spaties, hoofdletters, leestekens)</label>
            <button type="submit">Nu opschonen</button>
        </form>
    </div>
</body>
</html>
'''

GEOCODE_AANVULLEN_HTML = '''
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>Ontbrekende coördinaten aanvullen</title>
    <style>
        body { font-family: -apple-system, sans-serif; background: #f1f5f9; padding: 40px; }
        .box { background: white; padding: 30px; border-radius: 12px; max-width: 480px; margin: 0 auto; box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        h1 { font-size: 18px; margin-bottom: 8px; }
        p { font-size: 13px; color: #64748b; margin-bottom: 16px; }
        button { width: 100%; padding: 10px; background: #0d5c62; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 14px; margin-top:8px; }
        .bericht { padding: 10px; border-radius: 6px; margin-bottom: 12px; font-size: 14px; }
        .succes { background: #f0fdf4; color: #16a34a; }
    </style>
</head>
<body>
    <div class="box">
        <h1>Ontbrekende coördinaten aanvullen</h1>
        <p>Bedrijven die al in het systeem staan zonder locatie (bv. via een oudere import) worden nu wel automatisch gegeocodeerd bij aanmaken — maar bestaande bedrijven zonder coördinaten profiteren daar niet met terugwerkende kracht van. Deze actie zoekt bedrijven met een land/stad maar zonder coördinaten, en vult die aan. Verwerkt maximaal {{ limiet }} per keer (i.v.m. de externe geocoding-dienst) — druk gerust nogmaals als er meer over zijn.</p>
        {% if bericht %}<div class="bericht succes">{{ bericht }}</div>{% endif %}
        <form method="POST">
            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
            <button type="submit">Nu aanvullen</button>
        </form>
    </div>
</body>
</html>
'''

@app.route("/geocode-aanvullen", methods=["GET", "POST"])
def geocode_aanvullen():
    """Vult coördinaten aan voor bedrijven die al in het systeem staan zonder
    lat/lon, maar wel een land en/of regio hebben (bv. via een oudere import
    van vóórdat nieuwe bedrijven automatisch gegeocodeerd werden). Verwerkt
    een beperkt aantal per keer om de request niet te lang te laten duren."""
    _guard = vereist_admin_of_403()
    if _guard: return _guard

    LIMIET = 50
    bericht = None
    if request.method == "POST":
        kandidaten = [b for b in ENF_BEDRIJVEN if (b.get("lat") is None or b.get("lon") is None) and (b.get("land") or b.get("regio"))]
        te_verwerken = kandidaten[:LIMIET]
        aantal_gelukt = 0
        for b in te_verwerken:
            geo = geocode_adres(b.get("regio",""), b.get("land",""))
            if geo:
                b["lat"] = geo["lat"]
                b["lon"] = geo["lon"]
                aantal_gelukt += 1
        if te_verwerken:
            bewaar_bedrijven()
        resterend = len(kandidaten) - len(te_verwerken)
        bericht = f"Klaar! {aantal_gelukt} van de {len(te_verwerken)} verwerkte bedrijven succesvol gegeocodeerd."
        if resterend > 0:
            bericht += f" Nog {resterend} over — druk nogmaals op de knop om verder te gaan."

    return render_template_string(GEOCODE_AANVULLEN_HTML, bericht=bericht, limiet=LIMIET)


def normaliseer_naam(naam):
    naam = str(naam or "").strip().lower()
    naam = re.sub(r"[.,]", "", naam)
    naam = re.sub(r"\s+", " ", naam)
    return naam

def volledigheid_score(item):
    score = sum(1 for veld in ("adres", "telefoon", "materialen", "volume", "certificeringen", "kwaliteiten", "contactpersoon", "brontype") if item.get(veld))
    if isinstance(item.get("materiaal_volumes"), dict) and item["materiaal_volumes"]:
        score += len(item["materiaal_volumes"])
    return score

def voeg_duplicaten_samen(winnaar, verliezer):
    """Vult lege velden van de winnaar aan met waarden van de verliezer, zodat er nooit data verloren gaat bij het opschonen."""
    for veld in ("adres", "telefoon", "materialen", "volume", "certificeringen", "kwaliteiten", "contactpersoon", "brontype", "klanttype", "url"):
        if not winnaar.get(veld) and verliezer.get(veld):
            winnaar[veld] = verliezer[veld]
    verliezer_volumes = verliezer.get("materiaal_volumes", {})
    if isinstance(verliezer_volumes, dict) and verliezer_volumes:
        winnaar.setdefault("materiaal_volumes", {})
        if not isinstance(winnaar["materiaal_volumes"], dict):
            winnaar["materiaal_volumes"] = {}
        for materiaal_naam, waarde in verliezer_volumes.items():
            winnaar["materiaal_volumes"].setdefault(materiaal_naam, waarde)
    return winnaar

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
                groepen[s] = voeg_duplicaten_samen(item, groepen[s])
            else:
                groepen[s] = voeg_duplicaten_samen(groepen[s], item)
    return [groepen[s] for s in volgorde], len(lijst) - len(volgorde)

def opschonen_bedrijven_en_fabrieken(modus="streng"):
    """Dedupliceert ENF_BEDRIJVEN en PAPIERFABRIEKEN in-place en slaat ze op. Geeft (aantal_bedrijven_verwijderd, aantal_fabrieken_verwijderd) terug."""
    nieuwe_bedrijven, dubbel_bedrijven = dedupliceer_lijst(ENF_BEDRIJVEN, "regio", modus)
    ENF_BEDRIJVEN[:] = nieuwe_bedrijven
    bewaar_bedrijven()

    nieuwe_fabrieken, dubbel_fabrieken = dedupliceer_lijst(PAPIERFABRIEKEN, "stad", modus)
    PAPIERFABRIEKEN[:] = nieuwe_fabrieken
    bewaar_papierfabrieken()

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
        button { width: 100%; padding: 10px; background: #0d5c62; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 14px; margin-bottom: 10px; }
        button.secundair { background: #fff; color: #0d5c62; border: 1px solid #0d5c62; }
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
            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
            <input type="hidden" name="actie" value="aanvullen">
            <button type="submit">Nu aanvullen</button>
        </form>
        <p style="margin-top:20px;">Heb je eerder de knop gebruikt en staat er nu te vaak "Papierfabriek"? Corrigeer dat hiermee:</p>
        <form method="POST">
            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
            <input type="hidden" name="actie" value="corrigeer">
            <button type="submit" class="secundair">Corrigeer verkeerd gegokte "Papierfabriek"-labels</button>
        </form>
        {% if telling_lijst %}
        <hr style="margin:20px 0;border:none;border-top:1px solid #e2e8f0;">
        <p style="font-weight:600;color:#334155;margin-bottom:8px;">Huidige verdeling:</p>
        <table style="width:100%;font-size:13px;">
            {% for type_naam, aantal in telling_lijst %}
            <tr><td style="padding:3px 0;color:#334155;">{{ type_naam }}</td><td style="padding:3px 0;text-align:right;color:#0d5c62;font-weight:600;">{{ aantal }}</td></tr>
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
    _guard = vereist_admin_of_403()
    if _guard: return _guard
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
            bewaar_bedrijven()
            bericht = f"Klaar! {aantal_gecorrigeerd} verkeerd gegokte 'Papierfabriek'-labels zijn gecorrigeerd."
        else:
            aantal_aangevuld = 0
            for b in ENF_BEDRIJVEN:
                if not b.get("brontype"):
                    nieuw_type = _bepaal_brontype_uit_materiaal(b.get("materialen", ""))
                    if nieuw_type:
                        b["brontype"] = nieuw_type
                        aantal_aangevuld += 1
            bewaar_bedrijven()
            bericht = f"Klaar! {aantal_aangevuld} bedrijven hebben nu een Bedrijfstype gekregen."

    telling = {}
    for b in ENF_BEDRIJVEN:
        t = b.get("brontype") or "(geen type)"
        telling[t] = telling.get(t, 0) + 1
    telling_lijst = sorted(telling.items(), key=lambda x: -x[1])

    return render_template_string(HERLABEL_HTML, bericht=bericht, telling_lijst=telling_lijst)

@app.route("/opschonen-dubbelen", methods=["GET", "POST"])
def opschonen_dubbelen():
    _guard = vereist_admin_of_403()
    if _guard: return _guard
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
                headers={"User-Agent": "FTNext/1.0"},
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
        gevonden = []
        if tags.get("craft") == "paper" or tags.get("recycling:paper") == "yes":
            gevonden.append("Paper")
        if tags.get("recycling:cardboard") == "yes" or tags.get("recycling:paper_packaging") == "yes":
            gevonden.append("Karton")
        if tags.get("shop") == "scrap_yard" or tags.get("recycling:scrap_metal") == "yes" or tags.get("recycling:metal") == "yes":
            gevonden.append("Metal")
        if tags.get("recycling:glass") == "yes" or tags.get("recycling:glass_bottles") == "yes":
            gevonden.append("Glass")
        if tags.get("recycling:plastic") == "yes" or tags.get("recycling:plastic_packaging") == "yes":
            gevonden.append("Plastic")
        return ", ".join(gevonden)

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

    bewaar_bedrijven()

    return aantal_nieuw, len(elementen)

@app.route("/importeer-osm", methods=["GET", "POST"])
def importeer_osm():
    _guard = vereist_admin_of_403()
    if _guard: return _guard
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
    _guard = vereist_admin_of_403()
    if _guard: return _guard
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
    _guard = vereist_admin_of_403()
    if _guard: return _guard
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

                bewaar_bedrijven()
                bewaar_papierfabrieken()

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
        opgeslagen_waarde = wachtwoorden.get(forwarder, "")
        _geldig = False
        if opgeslagen_waarde:
            if opgeslagen_waarde.startswith(("pbkdf2:", "scrypt:")):
                # Al correct gehasht
                _geldig = check_password_hash(opgeslagen_waarde, wachtwoord)
            else:
                # Nog platte tekst (oude, handmatig aangemaakte data) — dit is de
                # laatste keer dat dit onveilig wordt vergeleken: bij een geldig
                # wachtwoord wordt het meteen omgezet naar een hash, zodat het
                # bestand vanaf nu nooit meer leesbare wachtwoorden bevat.
                _geldig = (opgeslagen_waarde == wachtwoord)
                if _geldig:
                    wachtwoorden[forwarder] = generate_password_hash(wachtwoord)
                    bewaar_forwarder_wachtwoorden(wachtwoorden)
        if forwarder not in wachtwoorden or not _geldig:
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

                TRANSPORT_DATA.clear()
                TRANSPORT_DATA.update(laad_transport_data())
                TRANSPORT_DATA[forwarder] = records
                with open(datapad("transport_prijzen.json"), "w", encoding="utf-8") as f:
                    json.dump(TRANSPORT_DATA, f, ensure_ascii=False, indent=2)

                bericht = f"Gelukt! {len(records)} steden geimporteerd voor {forwarder}."
                succes = True
            except Exception as e:
                bericht = f"Er ging iets mis: {e}"

    return render_template_string(UPLOAD_HTML, bericht=bericht, succes=succes)





LOGIN_HTML = '''
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>Inloggen — FTNext</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: "Inter", -apple-system, sans-serif;
            background: radial-gradient(circle at 20% 10%, #eef6f6 0%, #f8fafc 45%, #f1f5f9 100%);
            min-height: 100vh; display: flex; align-items: center; justify-content: center; margin: 0;
            padding: 20px;
        }
        .box {
            background: #fff; padding: 44px 40px; border-radius: 20px; width: 100%; max-width: 360px;
            box-shadow: 0 24px 60px rgba(15,23,42,0.08), 0 2px 8px rgba(15,23,42,0.04);
            border: 1px solid #f1f5f9;
        }
        .logo { font-size: 1.4rem; font-weight: 800; color: #0f172a; letter-spacing: -0.5px; margin-bottom: 4px; }
        .logo em { color: #0d5c62; font-style: normal; }
        .sub { font-size: 0.82rem; color: #94a3b8; margin-bottom: 28px; }
        label { display: block; font-size: 0.75rem; font-weight: 600; color: #475569; margin-bottom: 6px; margin-top: 14px; }
        label:first-of-type { margin-top: 0; }
        input {
            width: 100%; padding: 11px 13px; border: 1px solid #e2e8f0; border-radius: 8px;
            font-size: 14px; font-family: inherit; outline: none; transition: all 0.15s ease;
        }
        input:focus { border-color: #3f9295; box-shadow: 0 0 0 3px rgba(251,146,60,0.15); }
        button {
            width: 100%; padding: 12px; background: linear-gradient(135deg, #14767b, #0d5c62); color: white;
            border: none; border-radius: 8px; font-size: 14px; font-weight: 700; font-family: inherit;
            cursor: pointer; margin-top: 22px; transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        button:hover { box-shadow: 0 8px 20px rgba(234,88,12,0.3); transform: translateY(-1px); }
        .fout { background: #fef2f2; color: #dc2626; font-size: 0.8rem; padding: 10px 12px; border-radius: 8px; margin-bottom: 16px; border: 1px solid #fecaca; }
    </style>
</head>
<body>
    <div class="box">
        <div class="logo">FT<em>Next</em></div>
        <div class="sub">Global Recycling Intelligence Platform</div>
        {% if fout %}<div class="fout">{{ fout }}</div>{% endif %}
        <form method="POST">
            <label>Gebruikersnaam</label>
            <input type="text" name="gebruikersnaam" placeholder="Gebruikersnaam of e-mailadres" required autofocus>
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
        ingevoerd = request.form.get("gebruikersnaam", "").strip()
        wachtwoord = request.form.get("wachtwoord", "")
        users = laad_users()

        # Ingevoerde waarde kan de gebruikersnaam zelf zijn, of het e-mailadres
        # dat bij Persoonlijke informatie is ingesteld — in dat laatste geval
        # herleiden we hier de echte gebruikersnaam, zodat rate-limiting en
        # sessie-opslag altijd op dezelfde, echte gebruiker werken (anders zou
        # iemand de blokkade kunnen omzeilen door af te wisselen tussen naam
        # en e-mail).
        gebruikersnaam = ingevoerd
        if ingevoerd not in users and ingevoerd:
            gevonden = next((naam for naam, gegevens in users.items()
                              if gegevens.get("email", "").strip().lower() == ingevoerd.lower()), None)
            if gevonden:
                gebruikersnaam = gevonden

        geblokkeerd, resterende_minuten = is_account_tijdelijk_geblokkeerd(gebruikersnaam)
        if geblokkeerd:
            fout = f"Te veel mislukte inlogpogingen. Probeer het over {resterende_minuten} minuten opnieuw."
        else:
            if gebruikersnaam in users and check_password_hash(users[gebruikersnaam]["wachtwoord"], wachtwoord):
                reset_mislukte_inlogpogingen(gebruikersnaam)
                session["ingelogd"] = True
                session["gebruikersnaam"] = gebruikersnaam
                session["team"] = users[gebruikersnaam].get("team", "")
                session["afdeling"] = users[gebruikersnaam].get("afdeling", "")
                session["rol"] = users[gebruikersnaam].get("rol", "")
                return redirect(url_for("zoeken.index"))
            else:
                registreer_mislukte_inlogpoging(gebruikersnaam)
                fout = "Onjuiste gebruikersnaam of wachtwoord."
    return render_template_string(LOGIN_HTML, fout=fout)



@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/wissel-weergave")
def wissel_weergave():
    """Laat een admin/directeur tijdelijk zien wat een specifieke afdeling ziet, zonder de
    eigen rechten te wijzigen. Alleen bevoorrechte gebruikers mogen dit gebruiken."""
    if not (is_huidige_gebruiker_admin() or session.get("rol", "") == "directeur"):
        return redirect(url_for("zoeken.index"))
    gekozen = request.args.get("afdeling", "alles")
    if gekozen == "alles" or gekozen in AFDELINGEN:
        session["weergave_als"] = gekozen
    terug_naar = request.referrer or url_for("zoeken.index")
    return redirect(terug_naar)

@app.route("/api/fotos", methods=["GET"])
def get_fotos():
    bedrijf = request.args.get("bedrijf", "")
    categorie = request.args.get("categorie", "")
    submap = request.args.get("submap", "")
    alle = laad_fotos().get(bedrijf, [])
    if categorie:
        alle = [f for f in alle if f.get("categorie", "Algemeen") == categorie and f.get("submap", "") == submap]
    return jsonify(alle)

@app.route("/api/fotos", methods=["POST"])
def upload_foto():
    bedrijf = request.form.get("bedrijf", "")
    bestand = request.files.get("foto")
    categorie = request.form.get("categorie", "Algemeen")
    submap = request.form.get("submap", "")

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
        "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
        "categorie": categorie,
        "submap": submap,
    })
    bewaar_fotos(alle)

    return jsonify({"ok": True, "bestandsnaam": bestandsnaam})

@app.route("/api/fotos", methods=["DELETE"])
def verwijder_foto():
    data = request.get_json()
    bedrijf = data.get("bedrijf", "")
    bestandsnaam = data.get("bestandsnaam", "")

    alle = laad_fotos()
    lijst = alle.get(bedrijf, [])
    doel = next((f for f in lijst if f.get("bestandsnaam") == bestandsnaam), None)
    if not doel:
        return jsonify({"error": "Foto niet gevonden"}), 404
    if doel.get("geupload_door") != session.get("gebruikersnaam", "") and not is_huidige_gebruiker_admin():
        return jsonify({"error": "Je kunt alleen je eigen foto's verwijderen."}), 403

    alle[bedrijf] = [f for f in lijst if f.get("bestandsnaam") != bestandsnaam]
    bewaar_fotos(alle)

    pad = os.path.join(FOTOS_MAP, bestandsnaam)
    if os.path.exists(pad):
        try:
            os.remove(pad)
        except Exception:
            pass

    return jsonify({"ok": True})


@app.route("/api/fotomappen", methods=["GET"])
def get_fotomappen():
    bedrijf = request.args.get("bedrijf", "")
    categorie = request.args.get("categorie", "")
    alle = laad_fotomappen().get(bedrijf, {})
    aangemaakte = alle.get(categorie, [])
    # Ook submappen meenemen die impliciet bestaan doordat er al foto's in staan
    foto_submappen = {f.get("submap","") for f in laad_fotos().get(bedrijf, []) if f.get("categorie","Algemeen") == categorie and f.get("submap","")}
    return jsonify(sorted(set(aangemaakte) | foto_submappen))

@app.route("/api/fotomappen", methods=["POST"])
def maak_fotomap():
    data = request.get_json()
    bedrijf = data.get("bedrijf", "")
    categorie = data.get("categorie", "")
    submap = data.get("submap", "").strip()
    if not bedrijf or not categorie or not submap:
        return jsonify({"error": "Bedrijf, categorie en mapnaam zijn verplicht"}), 400
    alle = laad_fotomappen()
    alle.setdefault(bedrijf, {}).setdefault(categorie, [])
    if submap not in alle[bedrijf][categorie]:
        alle[bedrijf][categorie].append(submap)
    bewaar_fotomappen(alle)
    return jsonify({"ok": True, "submap": submap})

from flask import send_from_directory

@app.route("/fotos_uploads/<bestandsnaam>")
def get_foto_bestand(bestandsnaam):
    return send_from_directory(FOTOS_MAP, bestandsnaam)
@app.route("/api/gebruikers", methods=["GET"])
def get_gebruikers():
    users = laad_users()
    lijst = [{"gebruikersnaam": naam, "team": info.get("team", "")} for naam, info in users.items()]
    return jsonify(lijst)











@app.route("/api/facturen", methods=["GET"])
def get_facturen():
    bedrijf = request.args.get("bedrijf", "")
    alle = laad_facturen()
    lijst = [f for f in alle if f.get("bedrijf") == bedrijf]
    lijst.sort(key=lambda f: f.get("vervaldatum", ""))
    for f in lijst:
        f["status"] = bepaal_factuur_status(f)
    return jsonify(lijst)

@app.route("/api/facturen", methods=["POST"])
def add_factuur():
    data = request.get_json()
    bedrijf = data.get("bedrijf", "")
    bedrag = data.get("bedrag", "").strip() if data.get("bedrag") else ""
    factuurdatum = data.get("factuurdatum", "").strip()
    vervaldatum = data.get("vervaldatum", "").strip()
    referentie = data.get("referentie", "").strip()
    omschrijving = data.get("omschrijving", "").strip()
    if not bedrijf or not bedrag or not vervaldatum:
        return jsonify({"error": "Bedrijf, bedrag en vervaldatum zijn verplicht"}), 400
    alle = laad_facturen()
    nieuwe = {
        "id": str(uuid.uuid4()), "bedrijf": bedrijf, "bedrag": bedrag,
        "factuurdatum": factuurdatum, "vervaldatum": vervaldatum,
        "referentie": referentie, "omschrijving": omschrijving,
        "betaalddatum": "", "gebruiker": session.get("gebruikersnaam", ""),
        "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
    }
    alle.append(nieuwe)
    bewaar_facturen(alle)
    nieuwe["status"] = bepaal_factuur_status(nieuwe)
    return jsonify(nieuwe)

@app.route("/api/facturen/<factuur_id>/betaald", methods=["POST"])
def markeer_factuur_betaald(factuur_id):
    alle = laad_facturen()
    gevonden = False
    for f in alle:
        if f.get("id") == factuur_id:
            f["betaalddatum"] = datetime.date.today().isoformat()
            gevonden = True
    if not gevonden:
        return jsonify({"error": "Factuur niet gevonden"}), 404
    bewaar_facturen(alle)
    return jsonify({"ok": True})

@app.route("/api/facturen", methods=["DELETE"])
def verwijder_factuur():
    data = request.get_json()
    factuur_id = data.get("id", "")
    alle = laad_facturen()
    if not any(f.get("id") == factuur_id for f in alle):
        return jsonify({"error": "Factuur niet gevonden"}), 404
    alle = [f for f in alle if f.get("id") != factuur_id]
    bewaar_facturen(alle)
    return jsonify({"ok": True})

@app.route("/api/documenten", methods=["GET"])
def get_documenten():
    bedrijf = request.args.get("bedrijf", "")
    alle = laad_documenten()
    return jsonify(alle.get(bedrijf, []))

@app.route("/api/documenten", methods=["POST"])
def upload_document():
    bedrijf = request.form.get("bedrijf", "")
    bestand = request.files.get("document")
    if not bedrijf or not bestand:
        return jsonify({"error": "Bedrijf en document zijn verplicht"}), 400

    origineel = bestand.filename or ""
    extensie = origineel.rsplit(".", 1)[-1].lower() if "." in origineel else ""
    if extensie not in DOCUMENT_EXTENSIES_TOEGESTAAN:
        return jsonify({"error": "Alleen PDF- en Word-bestanden zijn toegestaan (.pdf, .doc, .docx)"}), 400

    if not os.path.exists(DOCUMENTEN_MAP):
        os.makedirs(DOCUMENTEN_MAP)

    bestandsnaam = f"{uuid.uuid4()}.{extensie}"
    bestand.save(os.path.join(DOCUMENTEN_MAP, bestandsnaam))

    alle = laad_documenten()
    alle.setdefault(bedrijf, [])
    alle[bedrijf].append({
        "bestandsnaam": bestandsnaam,
        "originele_naam": origineel,
        "geupload_door": session.get("gebruikersnaam", ""),
        "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
    })
    bewaar_documenten(alle)
    return jsonify({"ok": True, "bestandsnaam": bestandsnaam})

@app.route("/api/documenten", methods=["DELETE"])
def verwijder_document():
    data = request.get_json()
    bedrijf = data.get("bedrijf", "")
    bestandsnaam = data.get("bestandsnaam", "")
    alle = laad_documenten()
    lijst = alle.get(bedrijf, [])
    doel = next((d for d in lijst if d.get("bestandsnaam") == bestandsnaam), None)
    if not doel:
        return jsonify({"error": "Document niet gevonden"}), 404
    if doel.get("geupload_door") != session.get("gebruikersnaam", "") and not is_huidige_gebruiker_admin():
        return jsonify({"error": "Je kunt alleen je eigen documenten verwijderen."}), 403
    alle[bedrijf] = [d for d in lijst if d.get("bestandsnaam") != bestandsnaam]
    bewaar_documenten(alle)
    pad = os.path.join(DOCUMENTEN_MAP, bestandsnaam)
    if os.path.exists(pad):
        try:
            os.remove(pad)
        except Exception:
            pass
    return jsonify({"ok": True})

@app.route("/documenten_uploads/<bestandsnaam>")
def get_document_bestand(bestandsnaam):
    alle = laad_documenten()
    originele_naam = bestandsnaam
    for lijst in alle.values():
        for d in lijst:
            if d.get("bestandsnaam") == bestandsnaam:
                originele_naam = d.get("originele_naam", bestandsnaam)
    from flask import send_from_directory
    return send_from_directory(DOCUMENTEN_MAP, bestandsnaam, as_attachment=True, download_name=originele_naam)






@app.route("/logistiek")
def logistiek_pagina():
    """Navigatie-hub: een kort overzicht van wat elke logistieke pagina doet,
    met een directe link. Draaide voorheen op het oude shipments.json-systeem,
    dat sinds Handelsorders/Transport Planning nergens meer gevuld wordt —
    vervangen door dit overzicht, zodat je in één oogopslag ziet wat waar
    hoort in plaats van zeven losse zijbalk-items te moeten onthouden."""
    _guard = vereist_afdeling_of_403("logistiek")
    if _guard: return _guard

    kaarten = [
        {"pagina_key": "logistiek_planning", "titel": "Planning (Inkoop / Verkoop / Scheepvaart)", "href": "/logistiek/planning",
         "beschrijving": "Wat nog ingepland moet worden — als tabbladen: vrachtwagen-inkoop, verkoop, en export per schip."},
        {"pagina_key": "logistieke_orders", "titel": "Orders logistiek", "href": "/logistiek/orders",
         "beschrijving": "Volgt de fysieke aflevering van vrachtwagen-vracht: van aankomst tot weging tot overdracht aan Finance."},
        {"pagina_key": "transport_planning", "titel": "Transport Planning", "href": "/transport-planning",
         "beschrijving": "Hier plan je een transport daadwerkelijk in — datums, kenteken of haven/forwarder — nadat je vanuit een planningspagina op 'Plan in' klikte."},
        {"pagina_key": "transport_overview", "titel": "Transport Overview", "href": "/transport-overview",
         "beschrijving": "Management-samenvatting over alle transporten: status-KPI's, vertragingen, en een overzicht per land."},
    ]
    kaarten = [k for k in kaarten if mag_pagina_zien(k["pagina_key"])]

    inhoud = """
<div class="page-title">Logistiek</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Overzicht van de logistieke pagina's — klik door naar waar je moet zijn.</p>

<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px;">
    {% for k in kaarten %}
    <a href="{{ k.href }}" style="display:block;background:#fff;border:1px solid var(--gray-200);border-radius:10px;padding:16px 18px;text-decoration:none;color:inherit;">
        <div style="font-size:14px;font-weight:700;color:var(--gray-800);margin-bottom:6px;">{{ k.titel }} →</div>
        <div style="font-size:12.5px;color:var(--gray-500);line-height:1.5;">{{ k.beschrijving }}</div>
    </a>
    {% endfor %}
</div>
    """
    pagina = render_simple_page("Logistiek", "logistiek", inhoud)
    return render_template_string(pagina, kaarten=kaarten)

@app.route("/logistiek/containers", methods=["GET", "POST"])
def containerbeheer_pagina():
    _guard = vereist_afdeling_of_403("logistiek")
    if _guard: return _guard

    if request.method == "POST":
        actie = request.form.get("actie", "")
        containers = laad_containers()

        if actie == "toevoegen":
            nieuw = {
                "id": str(uuid.uuid4()),
                "container_nummer": request.form.get("container_nummer", "").strip(),
                "type": request.form.get("type", "").strip(),
                "status": request.form.get("status", "Booking"),
                "gekoppelde_shipment_id": request.form.get("gekoppelde_shipment_id", "").strip(),
                "locatie": request.form.get("locatie", "").strip(),
                "gewicht": request.form.get("gewicht", "").strip(),
                "notitie": request.form.get("notitie", "").strip(),
                "land_herkomst": request.form.get("land_herkomst", "").strip(),
                "leverancier": request.form.get("leverancier", "").strip(),
                "laadlocatie": request.form.get("laadlocatie", "").strip(),
                "haven": request.form.get("haven", "").strip(),
                "reederij": request.form.get("reederij", "").strip(),
                "eta": request.form.get("eta", "").strip(),
                "etd": request.form.get("etd", "").strip(),
                "vessel": request.form.get("vessel", "").strip(),
                "bookingnummer": request.form.get("bookingnummer", "").strip(),
                "sealnummer": request.form.get("sealnummer", "").strip(),
                "materiaal": request.form.get("materiaal", "").strip(),
                "bestemming": request.form.get("bestemming", "").strip(),
                "fabriek": request.form.get("fabriek", "").strip(),
                "transporteur": request.form.get("transporteur", "").strip(),
                "gebruiker": session.get("gebruikersnaam", ""),
                "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
            }
            if nieuw["container_nummer"]:
                containers.append(nieuw)
                bewaar_containers(containers)

        elif actie == "status_wijzigen":
            container_id = request.form.get("container_id", "")
            nieuwe_status = request.form.get("nieuwe_status", "")
            for c in containers:
                if c["id"] == container_id:
                    c["status"] = nieuwe_status
            bewaar_containers(containers)

        elif actie == "verwijderen":
            container_id = request.form.get("container_id", "")
            doel = next((c for c in containers if c["id"] == container_id), None)
            if doel and (doel.get("gebruiker") == session.get("gebruikersnaam","") or is_huidige_gebruiker_admin()):
                containers = [c for c in containers if c["id"] != container_id]
                bewaar_containers(containers)

        return redirect(url_for("containerbeheer_pagina"))

    containers = laad_containers()
    filter_status_cont = request.args.get("filter_status", "")
    getoonde_containers = containers
    if filter_status_cont:
        getoonde_containers = [c for c in getoonde_containers if c.get("status") == filter_status_cont]
    getoonde_containers = sorted(getoonde_containers, key=lambda c: c.get("aangemaakt",""), reverse=True)

    # Shipment-referenties opzoeken voor koppeling-weergave (echte data, geen verzonnen koppeling)
    _shipments_lookup = {s["id"]: s for s in laad_shipments()}
    for c in getoonde_containers:
        gekoppeld = _shipments_lookup.get(c.get("gekoppelde_shipment_id", ""))
        c["shipment_referentie"] = gekoppeld.get("referentie", "") if gekoppeld else ""

    open_shipments_voor_koppeling = [s for s in laad_shipments() if s.get("status") not in ("Delivered", "Cancelled")]

    filter_land_cont = request.args.get("filter_land", "")
    if filter_land_cont:
        getoonde_containers = [c for c in getoonde_containers if c.get("land_herkomst") == filter_land_cont]

    _status_alle_cont = laad_status()
    _am_alle_cont = laad_accountmanagers()
    leverancier_namen_cont = sorted({b["naam"] for b in ENF_BEDRIJVEN if _status_alle_cont.get(b["naam"]) or _am_alle_cont.get(b["naam"])})
    fabriek_namen_cont = sorted({f["naam"] for f in toegewezen_klant_fabrieken()})
    landen_herkomst = sorted({c.get("land_herkomst","") for c in containers if c.get("land_herkomst")})

    per_land = []
    for land in landen_herkomst:
        containers_land = [c for c in containers if c.get("land_herkomst") == land]
        per_land.append({
            "land": land,
            "onderweg": len([c for c in containers_land if c.get("status") in ("Op zee", "Onderweg", "Transport gepland")]),
            "aangekomen": len([c for c in containers_land if c.get("status") in ("Aangekomen haven", "Douane", "Vrijgegeven")]),
            "afgerond": len([c for c in containers_land if c.get("status") in ("Geleverd", "Afgerond")]),
        })
    per_land.sort(key=lambda l: l["land"])

    inhoud = """
<style>
.log-tabel-rij { display:flex; align-items:center; padding:10px 16px; border-bottom:1px solid var(--gray-100); font-size:13px; }
.log-tabel-kop { display:flex; align-items:center; padding:10px 16px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); font-size:10px; letter-spacing:0.08em; text-transform:uppercase; color:#7d8792; }
</style>
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/logistiek" style="color:var(--gray-400);text-decoration:none;">Logistiek</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">Containerbeheer</span>
</div>
<div class="page-title">Containerbeheer</div>

<div class="info-kaart" style="max-width:560px;margin-bottom:20px;background:transparent;border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);border-radius:0;box-shadow:none;padding:16px 4px;">
    <div class="dg-kaart-titel">Container toevoegen</div>
    <form method="POST">
        <input type="hidden" name="actie" value="toevoegen">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
            <input type="text" name="container_nummer" placeholder="Containernummer (bv. MSKU1234567)" required style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
            <select name="type" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
                {% for t in container_types %}<option value="{{ t }}">{{ t }}</option>{% endfor %}
            </select>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
            <input type="text" name="land_herkomst" placeholder="Land van herkomst" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
            <input type="text" name="leverancier" placeholder="Leverancier" list="leveranciers_lijst_cont" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
            <datalist id="leveranciers_lijst_cont">{% for naam in leverancier_namen %}<option value="{{ naam }}">{% endfor %}</datalist>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
            <input type="text" name="laadlocatie" placeholder="Laadlocatie" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
            <input type="text" name="haven" placeholder="Haven" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
            <input type="text" name="reederij" placeholder="Reederij" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
            <input type="text" name="vessel" placeholder="Vessel" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
            <div><label style="font-size:10.5px;color:var(--gray-400);">ETD</label><input type="date" name="etd" style="width:100%;padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;box-sizing:border-box;font-family:inherit;"></div>
            <div><label style="font-size:10.5px;color:var(--gray-400);">ETA</label><input type="date" name="eta" style="width:100%;padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;box-sizing:border-box;font-family:inherit;"></div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
            <input type="text" name="bookingnummer" placeholder="Bookingnummer" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
            <input type="text" name="sealnummer" placeholder="Sealnummer" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
            <input type="text" name="materiaal" placeholder="Materiaal" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
            <input type="text" name="gewicht" placeholder="Gewicht (ton, optioneel)" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
            <input type="text" name="bestemming" placeholder="Bestemming" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
            <input type="text" name="fabriek" placeholder="Fabriek (indien bekend)" list="fabrieken_lijst_cont" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
            <datalist id="fabrieken_lijst_cont">{% for naam in fabriek_namen_cont %}<option value="{{ naam }}">{% endfor %}</datalist>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
            <input type="text" name="locatie" placeholder="Huidige locatie" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
            <input type="text" name="transporteur" placeholder="Transporteur" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
        </div>
        <select name="gekoppelde_shipment_id" style="width:100%;padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;margin-bottom:8px;box-sizing:border-box;">
            <option value="">Geen shipment gekoppeld</option>
            {% for s in open_shipments %}<option value="{{ s.id }}">{{ s.referentie or s.id[:8] }} — {{ s.materiaal }} ({{ s.origin_land }} → {{ s.destination_land }})</option>{% endfor %}
        </select>
        <input type="text" name="notitie" placeholder="Notitie (optioneel)" style="width:100%;padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;margin-bottom:8px;box-sizing:border-box;">
        <button type="submit" class="btn-nav btn-nav-primary" style="border:none;cursor:pointer;width:100%;">+ Toevoegen</button>
    </form>
</div>

<form method="GET" style="margin-bottom:16px;display:flex;gap:8px;">
    <select name="filter_status" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle statussen</option>
        {% for st in container_statussen %}<option value="{{ st }}" {% if filter_status_cont == st %}selected{% endif %}>{{ st }}</option>{% endfor %}
    </select>
    <select name="filter_land" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle landen</option>
        {% for land in landen_herkomst %}<option value="{{ land }}" {% if filter_land_cont == land %}selected{% endif %}>{{ land }}</option>{% endfor %}
    </select>
</form>

{% if per_land %}
<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Per land van herkomst</div>
<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px;">
    {% for l in per_land %}
    <a href="/logistiek/containers?filter_land={{ l.land|urlencode }}" style="text-decoration:none;background:transparent;border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);padding:14px 4px;min-width:180px;">
        <div style="font-size:12.5px;font-weight:700;color:var(--gray-800);margin-bottom:8px;">{{ l.land }}</div>
        <span style="display:inline-block;margin-right:12px;font-size:11.5px;color:var(--gray-500);">Onderweg: <b>{{ l.onderweg }}</b></span>
        <span style="display:inline-block;margin-right:12px;font-size:11.5px;color:var(--gray-500);">Aangekomen: <b>{{ l.aangekomen }}</b></span>
        <span style="display:inline-block;font-size:11.5px;color:var(--gray-500);">Afgerond: <b>{{ l.afgerond }}</b></span>
    </a>
    {% endfor %}
</div>
{% endif %}

{% if getoonde_containers %}
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);">
    <div class="log-tabel-kop">
        <span style="flex:1.1;">Containernummer</span>
        <span style="width:90px;">Herkomst</span>
        <span style="flex:1;">Leverancier</span>
        <span style="flex:1;">Materiaal</span>
        <span style="width:90px;">ETA</span>
        <span style="width:170px;">Status</span>
        <span style="width:40px;"></span>
    </div>
    {% for c in getoonde_containers %}
    <div class="log-tabel-rij">
        <span style="flex:1.1;font-weight:600;color:var(--gray-800);font-family:var(--font-mono);">{{ c.container_nummer }}</span>
        <span style="width:90px;color:var(--gray-500);">{{ c.land_herkomst or '—' }}</span>
        <span style="flex:1;color:var(--gray-600);">{{ c.leverancier or c.shipment_referentie or '—' }}</span>
        <span style="flex:1;color:var(--gray-600);">{{ c.materiaal or '—' }}</span>
        <span style="width:90px;color:var(--gray-600);">{{ c.eta or '—' }}</span>
        <span style="width:170px;">
            <form method="POST" style="margin:0;">
                <input type="hidden" name="actie" value="status_wijzigen">
                <input type="hidden" name="container_id" value="{{ c.id }}">
                <select name="nieuwe_status" onchange="this.form.submit()" style="font-size:11.5px;padding:3px 6px;border:1px solid var(--gray-200);border-radius:5px;">
                    {% for st in container_statussen %}<option value="{{ st }}" {% if c.status == st %}selected{% endif %}>{{ st }}</option>{% endfor %}
                    {% if c.status not in container_statussen %}<option value="{{ c.status }}" selected>{{ c.status }} (oud)</option>{% endif %}
                </select>
            </form>
        </span>
        <span style="width:40px;">
            <form method="POST" onsubmit="return confirm('Container verwijderen?');" style="margin:0;">
                <input type="hidden" name="actie" value="verwijderen">
                <input type="hidden" name="container_id" value="{{ c.id }}">
                <button type="submit" style="background:none;border:none;color:var(--gray-300);cursor:pointer;">✕</button>
            </form>
        </span>
    </div>
    {% endfor %}
</div>
<div style="padding:10px 4px;font-size:0.8rem;color:var(--gray-400);">{{ getoonde_containers|length }} containers</div>
{% else %}
<div class="lege-staat">Nog geen containers geregistreerd.</div>
{% endif %}
    """
    pagina = render_simple_page("Containerbeheer", "logistiek", inhoud)
    return render_template_string(pagina, getoonde_containers=getoonde_containers, filter_status_cont=filter_status_cont,
                                    container_types=CONTAINER_TYPES, container_statussen=CONTAINER_STATUSSEN,
                                    open_shipments=open_shipments_voor_koppeling, leverancier_namen=leverancier_namen_cont,
                                    fabriek_namen_cont=fabriek_namen_cont, landen_herkomst=landen_herkomst,
                                    filter_land_cont=filter_land_cont, per_land=per_land)

def _herstel_items_van_regels(regels):
    """Draait de 'gefactureerd'-markering van de onderliggende ladingen/
    transporten terug — nodig als een conceptfactuur wordt verwijderd, zodat
    die ladingen weer gewoon selecteerbaar zijn op Peute/Inkoop/Verkoop/Export
    (anders zouden ze voorgoed 'verdwenen' zijn zonder dat er ooit een echte
    factuur voor bestond). Regels van verschillende bronnen hebben elk hun
    eigen sleutel (logistieke_order_id, transport_id, of bron+item_id bij de
    gecombineerde Inkoop-regels) — dit handelt alle drie de vormen af."""
    lo_ids, tp_ids = set(), set()
    for r in regels:
        if "logistieke_order_id" in r:
            lo_ids.add(r["logistieke_order_id"])
        elif "transport_id" in r:
            tp_ids.add(r["transport_id"])
        elif r.get("bron") == "lo":
            lo_ids.add(r["item_id"])
        elif r.get("bron") == "tp":
            tp_ids.add(r["item_id"])

    if lo_ids:
        alle_orders = laad_logistieke_orders()
        for o in alle_orders:
            if o["id"] in lo_ids and o.get("status") == "Gefactureerd":
                o["status"] = "Klaar voor Finance"  # terug naar de stap vóór facturering
        bewaar_logistieke_orders(alle_orders)
    if tp_ids:
        alle_transport = laad_transport_planning()
        for t in alle_transport:
            if t["id"] in tp_ids:
                t["gefactureerd"] = False
        bewaar_transport_planning(alle_transport)

def _leverdatum_uit_regels(regels):
    """Bepaalt de leverings-/prestatiedatum voor op de factuur uit de datums
    van de losse regels — één datum als alles op dezelfde dag was, anders een
    'van t/m'-periode. Verplicht op een NL-factuur zodra dit afwijkt van de
    factuurdatum (wat bij een verzameling van meerdere ladingen bijna altijd
    het geval is)."""
    datums = sorted({r["datum"] for r in regels if r.get("datum")})
    if not datums:
        return ""
    if len(datums) == 1:
        return datums[0]
    return f"{datums[0]} t/m {datums[-1]}"

def _overzicht_factuur_inhoud():
    """Het algemene facturenoverzicht: KPI's, BTW-alerts, handmatig een factuur
    toevoegen, en de volledige lijst van alle facturen (ongeacht type/herkomst).
    Dit was de oorspronkelijke /facturen-pagina, nu een tabblad naast de
    specifiekere Inkoop/Verkoop/Export/Peute-tabbladen."""
    if request.method == "POST":
        actie = request.form.get("actie", "")
        alle_facturen = laad_facturen()
        if actie == "markeer_betaald":
            factuur_id = request.form.get("factuur_id", "")
            for f in alle_facturen:
                if f.get("id") == factuur_id:
                    f["betaalddatum"] = datetime.date.today().isoformat()
            bewaar_facturen(alle_facturen)
        elif actie == "verwijderen":
            factuur_id = request.form.get("factuur_id", "")
            factuur_te_verwijderen = next((f for f in alle_facturen if f.get("id") == factuur_id), None)
            # Alleen concepten mogen verwijderd worden (consistent met /facturen/<id>/verwijder-concept) —
            # een definitieve factuur moet gecrediteerd worden voor correctie, niet verwijderd.
            if factuur_te_verwijderen and factuur_te_verwijderen.get("workflow_status", "definitief") == "concept":
                _herstel_items_van_regels(factuur_te_verwijderen.get("regels", []))
                alle_facturen = [f for f in alle_facturen if f.get("id") != factuur_id]
                bewaar_facturen(alle_facturen)
        return redirect(url_for("facturen_pagina", **{k: v for k, v in request.args.items()}))

    vooringevuld_bedrijf = request.args.get("bedrijf", "")
    filter_status_fact = request.args.get("filter_status", "")
    vi_contract = request.args.get("contract_referentie", "").strip()
    vi_referentie = request.args.get("referentie", "").strip()
    vi_bedrag = request.args.get("bedrag", "").strip()
    vi_factuurdatum = request.args.get("factuurdatum", "").strip()
    vi_vervaldatum = request.args.get("vervaldatum", "").strip()

    alle_facturen = laad_facturen()
    for f in alle_facturen:
        f["status"] = bepaal_factuur_status(f)

    getoonde_facturen = alle_facturen
    if vooringevuld_bedrijf:
        getoonde_facturen = [f for f in getoonde_facturen if f.get("bedrijf") == vooringevuld_bedrijf]
    if filter_status_fact:
        getoonde_facturen = [f for f in getoonde_facturen if f.get("status") == filter_status_fact]
    getoonde_facturen.sort(key=lambda f: f.get("vervaldatum", ""))

    def _bedrag_getal(f):
        try:
            return float(str(f.get("bedrag", "0")).replace(",", "."))
        except (ValueError, TypeError):
            return 0.0

    openstaande_facturen = [f for f in alle_facturen if f.get("status") != "Betaald"]
    te_laat_facturen = [f for f in alle_facturen if f.get("status") == "Te laat"]
    totaal_openstaand = sum(_bedrag_getal(f) for f in openstaande_facturen)

    # --- Te verwerken betalingen: openstaand én binnen 7 dagen vervallend (of al te laat) —
    # dit is de "moet NU actie op"-lijst, anders dan de bredere 'openstaand'-KPI hierboven. ---
    _vandaag_fact = datetime.date.today()
    _binnenkort_grens = (_vandaag_fact + datetime.timedelta(days=7)).isoformat()
    te_verwerken_betalingen = sorted(
        [f for f in openstaande_facturen if f.get("vervaldatum","") <= _binnenkort_grens],
        key=lambda f: f.get("vervaldatum","")
    )
    for f in te_verwerken_betalingen:
        f["bedrag_weergave"] = "{:,.2f}".format(_bedrag_getal(f)).replace(",", "X").replace(".", ",").replace("X", ".")

    # --- BTW-alerts: ontbrekend of ongebruikelijk BTW%, plus eerstvolgende aangiftedeadline. ---
    STANDAARD_BTW_PERCENTAGES = {"0", "9", "21"}
    facturen_zonder_btw = [f for f in alle_facturen if not f.get("btw_percentage","").strip()]
    facturen_ongebruikelijk_btw = [f for f in alle_facturen if f.get("btw_percentage","").strip() and f.get("btw_percentage","").strip() not in STANDAARD_BTW_PERCENTAGES]

    def _volgende_btw_deadline():
        """Standaard NL kwartaal-BTW-deadlines: uiterlijk laatste dag van de maand ná het kwartaal."""
        jaar = _vandaag_fact.year
        deadlines = [
            datetime.date(jaar, 4, 30), datetime.date(jaar, 7, 31),
            datetime.date(jaar, 10, 31), datetime.date(jaar + 1, 1, 31),
        ]
        for d in deadlines:
            if d >= _vandaag_fact:
                return d
        return datetime.date(jaar + 1, 4, 30)

    btw_deadline = _volgende_btw_deadline()
    btw_deadline_dagen = (btw_deadline - _vandaag_fact).days

    _status_alle_fact = laad_status()
    _accountmanagers_alle_fact = laad_accountmanagers()
    alle_bedrijfsnamen_fact = sorted(set(_status_alle_fact.keys()) | set(_accountmanagers_alle_fact.keys()))[:500]

    inhoud = """
<style>
.fact-badge { font-size:10.5px; font-weight:700; padding:2px 9px; border-radius:10px; }
.fact-rij { display:flex; align-items:center; padding:0 var(--space-4); }
.fact-thead { padding-top:10px; padding-bottom:10px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); font-size:10px; letter-spacing:0.08em; text-transform:uppercase; color:#7d8792; }
.fact-row { padding-top:11px; padding-bottom:11px; border-bottom:1px solid var(--gray-100); font-size:12.5px; }
.fact-row:last-child { border-bottom:none; }
</style>
{% if aantal_klaar_voor_finance %}
<a href="/facturen/logistieke-orders" style="display:inline-flex;align-items:center;gap:6px;margin-bottom:16px;font-size:12.5px;font-weight:600;color:var(--brand-600);text-decoration:none;border:1px solid var(--gray-200);padding:7px 14px;border-radius:6px;">
    Logistieke orders klaar voor verwerking
    <span style="background:var(--brand-600);color:#fff;font-size:10.5px;font-weight:700;padding:1px 7px;border-radius:9px;">{{ aantal_klaar_voor_finance }}</span>
</a>
{% endif %}

<div class="kpi-mini" style="display:flex;gap:16px;margin-bottom:20px;">
    <div style="background:transparent;border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);padding:14px 4px;flex:1;">
        <div style="font-size:1.4rem;font-weight:800;color:var(--brand-600);">{{ openstaande_facturen|length }}</div>
        <div style="font-size:0.75rem;color:var(--gray-400);">Openstaand</div>
    </div>
    <div style="background:transparent;border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);padding:14px 4px;flex:1;">
        <div style="font-size:1.4rem;font-weight:800;color:var(--gray-800);">€{{ "{:,.0f}".format(totaal_openstaand).replace(",", ".") }}</div>
        <div style="font-size:0.75rem;color:var(--gray-400);">Totaal openstaand bedrag</div>
    </div>
    <div style="background:transparent;border:none;border-top:1px solid {{ '#fecaca' if te_laat_facturen else 'var(--gray-200)' }};border-bottom:1px solid {{ '#fecaca' if te_laat_facturen else 'var(--gray-200)' }};padding:14px 4px;flex:1;">
        <div style="font-size:1.4rem;font-weight:800;color:{{ '#dc2626' if te_laat_facturen else 'var(--gray-800)' }};">{{ te_laat_facturen|length }}</div>
        <div style="font-size:0.75rem;color:var(--gray-400);">Te laat</div>
    </div>
</div>

{% if te_verwerken_betalingen %}
<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Te verwerken betalingen (deze week vervallend of al te laat)</div>
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);margin-bottom:20px;">
    {% for f in te_verwerken_betalingen %}
    <div class="fact-rij fact-row">
        <span style="flex:1.4;">{{ f.bedrijf }}</span>
        <span style="flex:1.2;color:var(--gray-500);">{{ f.referentie or '—' }}</span>
        <span style="width:100px;text-align:right;font-family:var(--font-mono);">€{{ f.bedrag_weergave }}</span>
        <span style="width:100px;{% if f.status=='Te laat' %}color:#dc2626;font-weight:700;{% endif %}">{{ f.vervaldatum }}</span>
        <form method="POST" style="margin:0;">
            <input type="hidden" name="actie" value="markeer_betaald">
            <input type="hidden" name="factuur_id" value="{{ f.id }}">
            <button type="submit" style="font-size:11px;padding:4px 10px;background:var(--brand-600);color:#fff;border:none;border-radius:5px;cursor:pointer;font-weight:600;">Markeer betaald</button>
        </form>
    </div>
    {% endfor %}
</div>
{% endif %}

<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">BTW-alerts</div>
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);margin-bottom:20px;padding:12px 4px;font-size:12.5px;color:var(--gray-600);">
    <div style="margin-bottom:6px;">Eerstvolgende BTW-aangifte: <b>{{ btw_deadline.strftime("%d-%m-%Y") }}</b> ({{ btw_deadline_dagen }} dagen)</div>
    {% if facturen_zonder_btw %}<div style="margin-bottom:6px;color:#b45309;">{{ facturen_zonder_btw|length }} factu{{ "ur" if facturen_zonder_btw|length == 1 else "ren" }} zonder ingevuld BTW-percentage</div>{% endif %}
    {% if facturen_ongebruikelijk_btw %}<div style="color:#dc2626;">{{ facturen_ongebruikelijk_btw|length }} factu{{ "ur" if facturen_ongebruikelijk_btw|length == 1 else "ren" }} met een afwijkend BTW-percentage (niet 0/9/21%) — controleren</div>{% endif %}
    {% if not facturen_zonder_btw and not facturen_ongebruikelijk_btw %}<div style="color:var(--gray-400);">Geen BTW-aandachtspunten.</div>{% endif %}
</div>

<form method="GET" style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
    <input type="hidden" name="modus" value="overzicht">
    {% if vooringevuld_bedrijf %}<input type="hidden" name="bedrijf" value="{{ vooringevuld_bedrijf }}">{% endif %}
    <select name="filter_status" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle statussen</option>
        <option value="Open" {% if filter_status_fact == "Open" %}selected{% endif %}>Open</option>
        <option value="Te laat" {% if filter_status_fact == "Te laat" %}selected{% endif %}>Te laat</option>
        <option value="Betaald" {% if filter_status_fact == "Betaald" %}selected{% endif %}>Betaald</option>
    </select>
    {% if vooringevuld_bedrijf %}<a href="/facturen?modus=overzicht" style="font-size:12px;color:var(--gray-400);text-decoration:none;">Alle bedrijven tonen</a>{% endif %}
    <span style="font-size:12px;color:var(--gray-400);margin-left:auto;">{{ getoonde_facturen|length }} van {{ alle_facturen|length }}</span>
</form>

<a href="/facturen/nieuw{% if vooringevuld_bedrijf %}?bedrijf={{ vooringevuld_bedrijf|urlencode }}{% endif %}" style="display:inline-block;margin-bottom:20px;padding:9px 18px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-weight:700;text-decoration:none;font-size:13px;">+ Factuur toevoegen</a>

{% if getoonde_facturen %}
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);">
    <div class="fact-rij fact-thead">
        <span style="flex:1.4;">Bedrijf</span>
        <span style="flex:1.2;">Referentie</span>
        <span style="width:100px;text-align:right;">Bedrag</span>
        <span style="width:100px;">Vervaldatum</span>
        <span style="width:100px;">Status</span>
        <span style="width:140px;text-align:right;">Actie</span>
    </div>
    {% for f in getoonde_facturen %}
    <div class="fact-rij fact-row">
        <span style="flex:1.4;"><a href="/bedrijf/{{ f.bedrijf|urlencode }}" style="color:var(--gray-800);font-weight:600;text-decoration:none;">{{ f.bedrijf }}</a></span>
        <span style="flex:1.2;color:var(--gray-600);">
            {% if f.get('workflow_status') == 'concept' %}<span class="fact-badge" style="background:#fef3c7;color:#b45309;margin-right:4px;">Concept</span>{% endif %}
            {% if f.get('is_creditnota') %}<span class="fact-badge" style="background:#fef2f2;color:#dc2626;margin-right:4px;">Credit</span>{% endif %}
            <a href="/facturen/{{ f.id }}" style="color:var(--gray-600);text-decoration:none;">{{ f.factuurnummer or f.referentie|default('—', true) }}{% if f.get('regels') %} ({{ f.regels|length }}){% endif %}</a>
            {% if f.contract_referentie %}<br><a href="/handelsorders?zoekterm={{ f.contract_referentie|urlencode }}" style="font-size:10.5px;color:var(--brand-600);text-decoration:none;">↳ {{ f.contract_referentie }}</a>{% endif %}
        </span>
        <span style="width:100px;text-align:right;font-family:var(--font-mono);">€{{ f.bedrag }}</span>
        <span style="width:100px;color:var(--gray-500);">{{ f.vervaldatum }}</span>
        <span style="width:100px;">
            <span class="fact-badge" style="background:{{ '#f0fdf4' if f.status=='Betaald' else ('#fef2f2' if f.status=='Te laat' else '#eff6ff') }};color:{{ '#16a34a' if f.status=='Betaald' else ('#dc2626' if f.status=='Te laat' else '#1d4ed8') }};">{{ f.status }}</span>
        </span>
        <span style="width:140px;text-align:right;display:flex;justify-content:flex-end;gap:6px;">
            {% if f.get('workflow_status') != 'concept' and f.status != "Betaald" %}
            <form method="POST" style="margin:0;"><input type="hidden" name="actie" value="markeer_betaald"><input type="hidden" name="factuur_id" value="{{ f.id }}">
                <button type="submit" style="background:#f0fdf4;color:#16a34a;border:none;border-radius:5px;padding:4px 8px;cursor:pointer;font-size:11px;font-weight:700;">✓ Betaald</button>
            </form>
            {% endif %}
            {% if f.get('workflow_status') == 'concept' %}
            <form method="POST" style="margin:0;" onsubmit="return confirm('Dit concept verwijderen? De onderliggende ladingen/transporten worden weer vrijgegeven.');"><input type="hidden" name="actie" value="verwijderen"><input type="hidden" name="factuur_id" value="{{ f.id }}">
                <button type="submit" style="background:none;border:none;color:var(--gray-300);cursor:pointer;font-size:0.95rem;">✕</button>
            </form>
            {% endif %}
        </span>
    </div>
    {% endfor %}
</div>
{% else %}
<div class="lege-staat">{% if vooringevuld_bedrijf %}Nog geen facturen voor {{ vooringevuld_bedrijf }}.{% else %}Nog geen facturen toegevoegd.{% endif %}</div>
{% endif %}
    """
    return inhoud, dict(
        vooringevuld_bedrijf=vooringevuld_bedrijf, filter_status_fact=filter_status_fact,
        vi_contract=vi_contract, vi_referentie=vi_referentie, vi_bedrag=vi_bedrag,
        vi_factuurdatum=vi_factuurdatum, vi_vervaldatum=vi_vervaldatum,
        alle_facturen=alle_facturen, getoonde_facturen=getoonde_facturen,
        openstaande_facturen=openstaande_facturen, te_laat_facturen=te_laat_facturen,
        totaal_openstaand=totaal_openstaand, alle_bedrijfsnamen_fact=alle_bedrijfsnamen_fact,
        aantal_klaar_voor_finance=sum(1 for o in laad_logistieke_orders() if o.get("status") == "Klaar voor Finance"),
        te_verwerken_betalingen=te_verwerken_betalingen, facturen_zonder_btw=facturen_zonder_btw,
        facturen_ongebruikelijk_btw=facturen_ongebruikelijk_btw, btw_deadline=btw_deadline,
        btw_deadline_dagen=btw_deadline_dagen)


def _transport_planning_te_factureren(modus_filter=None, richting_filter=None):
    """Transport-planning-records die klaar zijn om te factureren: het
    transport is daadwerkelijk gebeurd (Geleverd/Afgerond), er is een contract
    gekoppeld, en het is nog niet eerder gefactureerd (apart 'gefactureerd'-
    veld — losstaand van de logistieke status, want dat is een ander soort
    voortgang). Optioneel filteren op transportmodus en/of richting
    (inkoop/verkoop, afgeleid van het gekoppelde handelsorder)."""
    alle_transport = laad_transport_planning()
    alle_handelsorders = {h["contractnummer"]: h for h in laad_handelsorders()}

    resultaat = []
    for t in alle_transport:
        if not t.get("contract_referentie") or t.get("gefactureerd"):
            continue
        if t.get("status") not in ("Geleverd", "Afgerond"):
            continue
        if modus_filter and t.get("transportmodus","") != modus_filter:
            continue
        contract = alle_handelsorders.get(t["contract_referentie"])
        richting = contract.get("order_type","") if contract else ""
        if richting_filter and richting != richting_filter:
            continue
        t = dict(t)
        t["_richting"] = richting
        t["_tegenpartij"] = t.get("leverancier","") if richting == "inkoop" else t.get("fabriek","")
        t["_prijs_per_ton"] = float(contract["prijs"]) if contract and contract.get("prijs") else None
        t["_valuta"] = contract.get("valuta", "EUR") if contract else "EUR"
        t["_ton"] = parse_ton_intern(t.get("hoeveelheid",""))
        t["_bedrag"] = round(t["_ton"] * t["_prijs_per_ton"], 2) if t["_prijs_per_ton"] is not None else None
        resultaat.append(t)
    return resultaat

def _groepeer_per_tegenpartij(items, tegenpartij_veld="_tegenpartij", datum_veld="aangemaakt"):
    """Groepeert een lijst van te-factureren items (van transport_planning of
    logistieke_orders) per tegenpartij, met totalen — gedeelde weergavelogica
    voor Export/Inkoop/Peute."""
    per_partij = {}
    for item in items:
        per_partij.setdefault(item.get(tegenpartij_veld,"Onbekend") or "Onbekend", []).append(item)
    for lijst in per_partij.values():
        lijst.sort(key=lambda i: i.get(datum_veld,""), reverse=True)
    return sorted(
        [{"tegenpartij": partij, "rijen": lijst, "aantal": len(lijst),
          "totaal_ton": round(sum(i["_ton"] for i in lijst), 3),
          "totaal_bedrag": round(sum(i["_bedrag"] for i in lijst if i["_bedrag"] is not None), 2)}
         for partij, lijst in per_partij.items()],
        key=lambda g: g["tegenpartij"]
    )

def _export_factuur_inhoud():
    """Export-tabblad: alles wat per schip gaat — inkoop (import) én verkoop
    (export) samen, net als het Scheepvaart-tabblad bij Planning. Afgeleverde
    transporten met een gekoppeld contract, nog niet gefactureerd."""
    items = _transport_planning_te_factureren(modus_filter="Schip")
    groepen = _groepeer_per_tegenpartij(items)

    inhoud = """
<p style="color:var(--gray-400);margin-top:0;margin-bottom:16px;font-size:0.85rem;">Afgeleverde scheepvaart-transporten met een gekoppeld contract, nog niet gefactureerd — inkoop (import) en verkoop (export) samen, per tegenpartij.</p>

<style>
.ef-groep { border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); margin-bottom:20px; }
.ef-groepkop { padding:12px 14px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); display:flex; align-items:center; gap:12px; font-size:12.5px; }
.ef-rij { padding:9px 14px; border-bottom:1px solid var(--gray-100); font-size:12.5px; display:flex; align-items:center; gap:12px; }
.ef-rij:last-child { border-bottom:none; }
.ef-richting-badge { font-size:9.5px; font-weight:700; padding:2px 7px; border-radius:4px; }
</style>

{% if groepen %}
{% for g in groepen %}
<form method="POST" action="/facturen/transport/genereer">
<input type="hidden" name="bron_modus" value="export">
<div class="ef-groep">
    <div class="ef-groepkop">
        <b style="flex:1;color:var(--gray-800);">{{ g.tegenpartij }}</b>
        <span style="color:var(--gray-400);">{{ g.aantal }} transport{{ 'en' if g.aantal != 1 else '' }} · {{ g.totaal_ton }} t open</span>
        <button type="submit" style="font-size:12px;font-weight:700;padding:6px 14px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;cursor:pointer;">Factuur aanmaken van geselecteerde →</button>
    </div>
    {% for t in g.rijen %}
    <div class="ef-rij">
        <input type="checkbox" name="transport_ids" value="{{ t.id }}" checked style="margin:0;">
        <span style="width:70px;">
            {% if t._richting == "inkoop" %}<span class="ef-richting-badge" style="background:#f0fdf4;color:#16a34a;">Inkoop</span>
            {% else %}<span class="ef-richting-badge" style="background:#fef3c7;color:#b45309;">Verkoop</span>{% endif %}
        </span>
        <span style="width:90px;color:var(--gray-500);">{{ t.aangemaakt[:10] if t.aangemaakt else '—' }}</span>
        <span style="width:130px;font-family:var(--font-mono);color:var(--gray-500);">{{ t.referentienummer or '—' }}</span>
        <span style="flex:1;color:var(--gray-600);">{{ t.materiaal }} — {{ t.kwaliteit }}</span>
        <span style="width:130px;color:var(--gray-500);">{{ t.contract_referentie }}</span>
        <span style="width:90px;text-align:right;font-family:var(--font-mono);color:var(--gray-700);">{{ t._ton }} t</span>
        {% if t._prijs_per_ton is not none %}
        <span style="width:90px;text-align:right;color:var(--gray-500);">{{ t._prijs_per_ton }}/t</span>
        <span style="width:100px;text-align:right;font-family:var(--font-mono);font-weight:700;color:var(--gray-800);">{{ "%.2f"|format(t._bedrag) }} {{ t._valuta }}</span>
        {% else %}
        <span style="width:190px;text-align:right;color:#dc2626;font-size:11px;">Geen prijs op het contract</span>
        {% endif %}
    </div>
    {% endfor %}
</div>
</form>
{% endfor %}
{% else %}
<div class="lege-staat">Niets te factureren — alle afgeleverde scheepvaart is al gefactureerd.</div>
{% endif %}
    """
    return inhoud, {"groepen": groepen}


@app.route("/facturen/transport/genereer", methods=["POST"])
def facturen_transport_genereer():
    """Maakt één factuur aan van geselecteerde transport_planning-records
    (Export- en Inkoop-per-schip-tabblad delen deze route) — zelfde patroon
    als /facturen/peute/genereer, maar met transport_planning als bron i.p.v.
    logistieke_orders (weegbrug). Alle geselecteerde records moeten dezelfde
    tegenpartij hebben (leverancier bij inkoop, fabriek bij verkoop)."""
    _guard = vereist_afdeling_of_403("facturen")
    if _guard: return _guard

    transport_ids = request.form.getlist("transport_ids")
    bron_modus = request.form.get("bron_modus", "export")
    if not transport_ids:
        return redirect(url_for("facturen_pagina", modus=bron_modus))

    alle_transport = laad_transport_planning()
    alle_handelsorders = {h["contractnummer"]: h for h in laad_handelsorders()}
    geselecteerd = [t for t in alle_transport if t["id"] in transport_ids]
    if not geselecteerd:
        return redirect(url_for("facturen_pagina", modus=bron_modus))

    def _tegenpartij_van(t):
        contract = alle_handelsorders.get(t.get("contract_referentie",""))
        richting = contract.get("order_type","") if contract else ""
        return (t.get("leverancier","") if richting == "inkoop" else t.get("fabriek","")), richting

    eerste_tegenpartij, _ = _tegenpartij_van(geselecteerd[0])
    geselecteerd = [t for t in geselecteerd if _tegenpartij_van(t)[0] == eerste_tegenpartij]  # veiligheid: alleen dezelfde tegenpartij

    regels = []
    totaal_bedrag = 0.0
    richting_van_factuur = ""
    for t in geselecteerd:
        contract = alle_handelsorders.get(t.get("contract_referentie",""))
        _, richting = _tegenpartij_van(t)
        richting_van_factuur = richting or richting_van_factuur
        prijs_per_ton = float(contract["prijs"]) if contract and contract.get("prijs") else 0.0
        valuta = contract.get("valuta", "EUR") if contract else "EUR"
        ton = parse_ton_intern(t.get("hoeveelheid",""))
        bedrag = round(ton * prijs_per_ton, 2)
        totaal_bedrag += bedrag
        regels.append({
            "transport_id": t["id"], "referentienummer": t.get("referentienummer",""),
            "datum": t.get("aangemaakt","")[:10] if t.get("aangemaakt") else "",
            "materiaal": t.get("materiaal",""), "kwaliteit": t.get("kwaliteit",""),
            "ton": ton, "prijs_per_ton": prijs_per_ton, "valuta": valuta, "bedrag": bedrag,
            "contractnummer": t.get("contract_referentie",""),
        })

    contractnummers = {r["contractnummer"] for r in regels}
    nu = datetime.datetime.now()
    prefix = "EXPORT" if bron_modus == "export" else "INKOOP-SCHIP"

    termijn_dagen = 30
    _termijn_ingesteld = leverancier_instelling_voor(eerste_tegenpartij).get("standaard_betalingstermijn","")
    if _termijn_ingesteld:
        try:
            termijn_dagen = int(_termijn_ingesteld)
        except (ValueError, TypeError):
            pass
    vervaldatum = (nu.date() + datetime.timedelta(days=termijn_dagen)).isoformat()

    alle_facturen = laad_facturen()
    factuur_type = "verkoop" if richting_van_factuur == "verkoop" else "inkoop"
    nieuwe_factuur = {
        "id": str(uuid.uuid4()),
        "factuurnummer": "", "workflow_status": "concept",
        "bedrijf": eerste_tegenpartij,
        "klant_gegevens": haal_factuurgegevens_bedrijf(eerste_tegenpartij),
        "type": factuur_type,
        "referentie": f"{prefix}-{nu.strftime('%Y%m%d')}-{len([f for f in alle_facturen if f.get('type')==factuur_type and f.get('aangemaakt','').startswith(nu.strftime('%d-%m-%Y'))]) + 1:03d}",
        "omschrijving": f"{len(regels)} transport{'en' if len(regels) != 1 else ''} — {', '.join(sorted(contractnummers))}",
        "regels": regels,
        "bedrag": str(round(totaal_bedrag, 2)),
        "btw_percentage": "21",  # standaard NL-BTW; wordt genegeerd als BTW verlegd van toepassing is
        "factuurdatum": nu.date().isoformat(),
        "leverdatum": _leverdatum_uit_regels(regels),
        "vervaldatum": vervaldatum,
        "betaalddatum": "",
        "contract_referentie": next(iter(contractnummers)) if len(contractnummers) == 1 else "",
        "gebruiker": session.get("gebruikersnaam", ""),
        "aangemaakt": nu.strftime("%d-%m-%Y %H:%M"),
    }
    alle_facturen.append(nieuwe_factuur)
    bewaar_facturen(alle_facturen)

    gefactureerde_ids = {r["transport_id"] for r in regels}
    for t in alle_transport:
        if t["id"] in gefactureerde_ids:
            t["gefactureerd"] = True
    bewaar_transport_planning(alle_transport)

    return redirect(url_for("facturen_pagina", modus="overzicht", bedrijf=eerste_tegenpartij))


def _verkoop_factuur_inhoud():
    """Verkoop-tabblad: ALLE uitgaande facturatie — vrachtwagen én schip
    samen, per klant/fabriek. Verkoop-transport loopt altijd via Transport
    Planning (nooit via de Weegbrug, die is alleen voor inkomende inkoop) —
    dus hier is er maar één bron, in tegenstelling tot Inkoop dat vrachtwagen
    (weegbrug) en schip (transport planning) moest combineren."""
    items = _transport_planning_te_factureren(richting_filter="verkoop")
    for t in items:
        t["_bron"] = "tp"
        t["_referentie"] = t.get("referentienummer","")
        t["_modus"] = t.get("transportmodus", "Vrachtwagen")
    groepen = _groepeer_per_tegenpartij(items)

    inhoud = """
<p style="color:var(--gray-400);margin-top:0;margin-bottom:16px;font-size:0.85rem;">Alle uitgaande facturatie — vrachtwagen én schip samen, per klant. Afgeleverde transporten met een gekoppeld verkoopcontract, nog niet gefactureerd.</p>

<style>
.vf-groep { border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); margin-bottom:20px; }
.vf-groepkop { padding:12px 14px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); display:flex; align-items:center; gap:12px; font-size:12.5px; }
.vf-rij { padding:9px 14px; border-bottom:1px solid var(--gray-100); font-size:12.5px; display:flex; align-items:center; gap:12px; }
.vf-rij:last-child { border-bottom:none; }
.vf-modus-badge { font-size:9.5px; font-weight:700; padding:2px 7px; border-radius:4px; }
</style>

{% if groepen %}
{% for g in groepen %}
<form method="POST" action="/facturen/verkoop/genereer">
<div class="vf-groep">
    <div class="vf-groepkop">
        <b style="flex:1;color:var(--gray-800);">{{ g.tegenpartij }}</b>
        <span style="color:var(--gray-400);">{{ g.aantal }} transport{{ 'en' if g.aantal != 1 else '' }} · {{ g.totaal_ton }} t open</span>
        <button type="submit" style="font-size:12px;font-weight:700;padding:6px 14px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;cursor:pointer;">Factuur aanmaken van geselecteerde →</button>
    </div>
    {% for t in g.rijen %}
    <div class="vf-rij">
        <input type="checkbox" name="transport_ids" value="{{ t.id }}" checked style="margin:0;">
        <span style="width:100px;">
            {% if t._modus == "Schip" %}<span class="vf-modus-badge" style="background:#eff6ff;color:#1d4ed8;">Schip</span>
            {% else %}<span class="vf-modus-badge" style="background:#f0fdf4;color:#16a34a;">Vrachtwagen</span>{% endif %}
        </span>
        <span style="width:90px;color:var(--gray-500);">{{ t.aangemaakt[:10] if t.aangemaakt else '—' }}</span>
        <span style="width:130px;font-family:var(--font-mono);color:var(--gray-500);">{{ t.referentienummer or '—' }}</span>
        <span style="flex:1;color:var(--gray-600);">{{ t.materiaal }} — {{ t.kwaliteit }}</span>
        <span style="width:130px;color:var(--gray-500);">{{ t.contract_referentie }}</span>
        <span style="width:90px;text-align:right;font-family:var(--font-mono);color:var(--gray-700);">{{ t._ton }} t</span>
        {% if t._prijs_per_ton is not none %}
        <span style="width:90px;text-align:right;color:var(--gray-500);">{{ t._prijs_per_ton }}/t</span>
        <span style="width:100px;text-align:right;font-family:var(--font-mono);font-weight:700;color:var(--gray-800);">{{ "%.2f"|format(t._bedrag) }} {{ t._valuta }}</span>
        {% else %}
        <span style="width:190px;text-align:right;color:#dc2626;font-size:11px;">Geen prijs op het contract</span>
        {% endif %}
    </div>
    {% endfor %}
</div>
</form>
{% endfor %}
{% else %}
<div class="lege-staat">Niets te factureren — alle verkoop is al gefactureerd.</div>
{% endif %}
    """
    return inhoud, {"groepen": groepen}


@app.route("/facturen/verkoop/genereer", methods=["POST"])
def facturen_verkoop_genereer():
    """Maakt één verkoopfactuur aan van geselecteerde transport_planning-
    records — zelfde patroon als /facturen/transport/genereer (Export), maar
    hier altijd verkoop-gericht en met 'VERKOOP-'-prefix op het factuurnummer.
    Alle geselecteerde records moeten dezelfde klant/fabriek hebben."""
    _guard = vereist_afdeling_of_403("facturen")
    if _guard: return _guard

    transport_ids = request.form.getlist("transport_ids")
    if not transport_ids:
        return redirect(url_for("facturen_pagina", modus="verkoop"))

    alle_transport = laad_transport_planning()
    alle_handelsorders = {h["contractnummer"]: h for h in laad_handelsorders()}
    geselecteerd = [t for t in alle_transport if t["id"] in transport_ids]
    if not geselecteerd:
        return redirect(url_for("facturen_pagina", modus="verkoop"))

    eerste_klant = geselecteerd[0].get("fabriek","")
    geselecteerd = [t for t in geselecteerd if t.get("fabriek","") == eerste_klant]  # veiligheid: alleen dezelfde klant

    regels = []
    totaal_bedrag = 0.0
    for t in geselecteerd:
        contract = alle_handelsorders.get(t.get("contract_referentie",""))
        prijs_per_ton = float(contract["prijs"]) if contract and contract.get("prijs") else 0.0
        valuta = contract.get("valuta", "EUR") if contract else "EUR"
        ton = parse_ton_intern(t.get("hoeveelheid",""))
        bedrag = round(ton * prijs_per_ton, 2)
        totaal_bedrag += bedrag
        regels.append({
            "transport_id": t["id"], "referentienummer": t.get("referentienummer",""),
            "datum": t.get("aangemaakt","")[:10] if t.get("aangemaakt") else "",
            "materiaal": t.get("materiaal",""), "kwaliteit": t.get("kwaliteit",""),
            "ton": ton, "prijs_per_ton": prijs_per_ton, "valuta": valuta, "bedrag": bedrag,
            "contractnummer": t.get("contract_referentie",""),
        })

    contractnummers = {r["contractnummer"] for r in regels}
    nu = datetime.datetime.now()

    termijn_dagen = 30
    _termijn_ingesteld = leverancier_instelling_voor(eerste_klant).get("standaard_betalingstermijn","")
    if _termijn_ingesteld:
        try:
            termijn_dagen = int(_termijn_ingesteld)
        except (ValueError, TypeError):
            pass
    vervaldatum = (nu.date() + datetime.timedelta(days=termijn_dagen)).isoformat()

    alle_facturen = laad_facturen()
    nieuwe_factuur = {
        "id": str(uuid.uuid4()),
        "factuurnummer": "", "workflow_status": "concept",
        "bedrijf": eerste_klant,
        "klant_gegevens": haal_factuurgegevens_bedrijf(eerste_klant),
        "type": "verkoop",
        "referentie": f"VERKOOP-{nu.strftime('%Y%m%d')}-{len([f for f in alle_facturen if f.get('type')=='verkoop' and f.get('aangemaakt','').startswith(nu.strftime('%d-%m-%Y'))]) + 1:03d}",
        "omschrijving": f"{len(regels)} transport{'en' if len(regels) != 1 else ''} — {', '.join(sorted(contractnummers))}",
        "regels": regels,
        "bedrag": str(round(totaal_bedrag, 2)),
        "btw_percentage": "21",  # standaard NL-BTW; wordt genegeerd als BTW verlegd van toepassing is
        "factuurdatum": nu.date().isoformat(),
        "leverdatum": _leverdatum_uit_regels(regels),
        "vervaldatum": vervaldatum,
        "betaalddatum": "",
        "contract_referentie": next(iter(contractnummers)) if len(contractnummers) == 1 else "",
        "gebruiker": session.get("gebruikersnaam", ""),
        "aangemaakt": nu.strftime("%d-%m-%Y %H:%M"),
    }
    alle_facturen.append(nieuwe_factuur)
    bewaar_facturen(alle_facturen)

    gefactureerde_ids = {r["transport_id"] for r in regels}
    for t in alle_transport:
        if t["id"] in gefactureerde_ids:
            t["gefactureerd"] = True
    bewaar_transport_planning(alle_transport)

    return redirect(url_for("facturen_pagina", modus="overzicht", bedrijf=eerste_klant))


def _eenvoudig_factuur_tabblad_inhoud(type_naam, type_label, uitleg):
    """Eenvoudige, gefilterde weergave van facturen met een bepaald 'type'-veld
    (inkoop/verkoop/export) — toont wat er al is, met een link naar het
    Overzicht-tabblad om er handmatig een toe te voegen. Minder uitgebreid dan
    Peute (die heeft de volledige 'selecteer wegingen -> genereer factuur'-flow),
    maar wel al bruikbaar en consistent qua stijl."""
    alle_facturen = [f for f in laad_facturen() if f.get("type") == type_naam]
    for f in alle_facturen:
        f["status"] = bepaal_factuur_status(f)
    alle_facturen.sort(key=lambda f: f.get("vervaldatum", ""))

    def _bedrag_getal(f):
        try:
            return float(str(f.get("bedrag", "0")).replace(",", "."))
        except (ValueError, TypeError):
            return 0.0
    totaal = sum(_bedrag_getal(f) for f in alle_facturen)

    inhoud = """
<p style="color:var(--gray-400);margin-top:0;margin-bottom:16px;font-size:0.85rem;">""" + uitleg + """</p>
<div style="display:flex;gap:16px;margin-bottom:20px;">
    <div style="flex:1;border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);padding:14px 4px;">
        <div style="font-size:1.4rem;font-weight:800;color:var(--gray-800);">{{ alle_facturen|length }}</div>
        <div style="font-size:0.75rem;color:var(--gray-400);">Facturen</div>
    </div>
    <div style="flex:1;border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);padding:14px 4px;">
        <div style="font-size:1.4rem;font-weight:800;color:var(--gray-800);">€{{ "{:,.0f}".format(totaal).replace(",", ".") }}</div>
        <div style="font-size:0.75rem;color:var(--gray-400);">Totaal</div>
    </div>
</div>
{% if alle_facturen %}
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);">
    {% for f in alle_facturen %}
    <div style="display:flex;align-items:center;padding:11px 4px;border-bottom:1px solid var(--gray-100);font-size:12.5px;">
        <span style="flex:1.4;"><a href="/bedrijf/{{ f.bedrijf|urlencode }}" style="color:var(--gray-800);font-weight:600;text-decoration:none;">{{ f.bedrijf }}</a></span>
        <span style="flex:1.2;color:var(--gray-600);">{{ f.referentie|default('—', true) }}</span>
        <span style="width:100px;text-align:right;font-family:var(--font-mono);">€{{ f.bedrag }}</span>
        <span style="width:100px;color:var(--gray-500);">{{ f.vervaldatum }}</span>
        <span style="width:90px;font-weight:700;color:{{ '#16a34a' if f.status=='Betaald' else ('#dc2626' if f.status=='Te laat' else '#1d4ed8') }};">{{ f.status }}</span>
    </div>
    {% endfor %}
</div>
{% else %}
<div class="lege-staat">Nog geen """ + type_label + """-facturen.</div>
{% endif %}
    """
    return inhoud, dict(alle_facturen=alle_facturen, totaal=totaal)


def _inkoop_factuur_inhoud():
    """Inkoop-tabblad: ALLE inkoop-facturatie, vrachtwagen (via de Weegbrug —
    hetzelfde als het Peute-tabblad) én schip samen, per leverancier. Een
    vrachtwagen-inkooplevering staat dus zowel hier als op Peute (net als bij
    Planning: richting-tabblad en modus-tabblad zijn twee lenzen op dezelfde
    onderliggende data). Checkbox-waarden krijgen een 'lo:'/'tp:'-prefix om
    bij het genereren te weten uit welke bron (logistieke_orders / transport_
    planning) een item komt, want die hebben elk hun eigen velden en hun eigen
    manier om 'al gefactureerd' te markeren."""
    alle_orders = laad_logistieke_orders()
    alle_handelsorders = {h["contractnummer"]: h for h in laad_handelsorders()}

    vrachtwagen_items = [
        o for o in alle_orders
        if o.get("contract_referentie") and o.get("status") not in ("Gefactureerd", "Afgerond")
    ]
    for o in vrachtwagen_items:
        contract = alle_handelsorders.get(o["contract_referentie"])
        o["_bron"] = "lo"
        o["_referentie"] = o.get("ordernummer","")
        o["_modus"] = "Vrachtwagen"
        o["_tegenpartij"] = o.get("leverancier","")
        o["_prijs_per_ton"] = float(contract["prijs"]) if contract and contract.get("prijs") else None
        o["_valuta"] = contract.get("valuta", "EUR") if contract else "EUR"
        o["_ton"] = parse_ton_intern(o.get("werkelijke_hoeveelheid", ""))
        o["_bedrag"] = round(o["_ton"] * o["_prijs_per_ton"], 2) if o["_prijs_per_ton"] is not None else None
        o["aangemaakt"] = o.get("datum","")

    transport_planning_items = _transport_planning_te_factureren(richting_filter="inkoop")
    for t in transport_planning_items:
        t["_bron"] = "tp"
        t["_referentie"] = t.get("referentienummer","")
        t["_modus"] = t.get("transportmodus", "Schip")

    alle_items = vrachtwagen_items + transport_planning_items
    groepen = _groepeer_per_tegenpartij(alle_items)

    inhoud = """
<p style="color:var(--gray-400);margin-top:0;margin-bottom:16px;font-size:0.85rem;">Alle inkoop-facturatie — vrachtwagen (Weegbrug) én schip samen, per leverancier. Nog niet gefactureerd.</p>

<style>
.if-groep { border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); margin-bottom:20px; }
.if-groepkop { padding:12px 14px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); display:flex; align-items:center; gap:12px; font-size:12.5px; }
.if-rij { padding:9px 14px; border-bottom:1px solid var(--gray-100); font-size:12.5px; display:flex; align-items:center; gap:12px; }
.if-rij:last-child { border-bottom:none; }
.if-modus-badge { font-size:9.5px; font-weight:700; padding:2px 7px; border-radius:4px; }
</style>

{% if groepen %}
{% for g in groepen %}
<form method="POST" action="/facturen/inkoop/genereer">
<div class="if-groep">
    <div class="if-groepkop">
        <b style="flex:1;color:var(--gray-800);">{{ g.tegenpartij }}</b>
        <span style="color:var(--gray-400);">{{ g.aantal }} lading{{ 'en' if g.aantal != 1 else '' }} · {{ g.totaal_ton }} t open</span>
        <button type="submit" style="font-size:12px;font-weight:700;padding:6px 14px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;cursor:pointer;">Factuur aanmaken van geselecteerde →</button>
    </div>
    {% for i in g.rijen %}
    <div class="if-rij">
        <input type="checkbox" name="item_ids" value="{{ i._bron }}:{{ i.id }}" checked style="margin:0;">
        <span style="width:100px;">
            {% if i._modus == "Schip" %}<span class="if-modus-badge" style="background:#eff6ff;color:#1d4ed8;">Schip</span>
            {% else %}<span class="if-modus-badge" style="background:#f0fdf4;color:#16a34a;">Vrachtwagen</span>{% endif %}
        </span>
        <span style="width:90px;color:var(--gray-500);">{{ i.aangemaakt[:10] if i.aangemaakt else '—' }}</span>
        <span style="width:130px;font-family:var(--font-mono);color:var(--gray-500);">{{ i._referentie or '—' }}</span>
        <span style="flex:1;color:var(--gray-600);">{{ i.materiaal }} — {{ i.kwaliteit }}</span>
        <span style="width:130px;color:var(--gray-500);">{{ i.contract_referentie }}</span>
        <span style="width:90px;text-align:right;font-family:var(--font-mono);color:var(--gray-700);">{{ i._ton }} t</span>
        {% if i._prijs_per_ton is not none %}
        <span style="width:90px;text-align:right;color:var(--gray-500);">{{ i._prijs_per_ton }}/t</span>
        <span style="width:100px;text-align:right;font-family:var(--font-mono);font-weight:700;color:var(--gray-800);">{{ "%.2f"|format(i._bedrag) }} {{ i._valuta }}</span>
        {% else %}
        <span style="width:190px;text-align:right;color:#dc2626;font-size:11px;">Geen prijs op het contract</span>
        {% endif %}
    </div>
    {% endfor %}
</div>
</form>
{% endfor %}
{% else %}
<div class="lege-staat">Niets te factureren — alle inkoop is al gefactureerd.</div>
{% endif %}
    """
    return inhoud, {"groepen": groepen}


@app.route("/facturen/inkoop/genereer", methods=["POST"])
def facturen_inkoop_genereer():
    """Maakt één inkoopfactuur aan van geselecteerde items — die kunnen van
    twee bronnen komen (vrachtwagen via logistieke_orders, schip via
    transport_planning), te onderscheiden aan de 'lo:'/'tp:'-prefix op elke
    checkbox-waarde. Beide brontypes hebben hun eigen velden en hun eigen
    manier om als 'gefactureerd' te markeren, dus die logica wordt hier
    per item apart afgehandeld voordat de gezamenlijke factuur wordt gebouwd."""
    _guard = vereist_afdeling_of_403("facturen")
    if _guard: return _guard

    item_ids = request.form.getlist("item_ids")
    if not item_ids:
        return redirect(url_for("facturen_pagina", modus="inkoop"))

    lo_ids = {i.split(":",1)[1] for i in item_ids if i.startswith("lo:")}
    tp_ids = {i.split(":",1)[1] for i in item_ids if i.startswith("tp:")}

    alle_orders = laad_logistieke_orders()
    alle_transport = laad_transport_planning()
    alle_handelsorders = {h["contractnummer"]: h for h in laad_handelsorders()}

    geselecteerde_orders = [o for o in alle_orders if o["id"] in lo_ids]
    geselecteerde_transport = [t for t in alle_transport if t["id"] in tp_ids]

    # Leverancier van het allereerste geselecteerde item bepaalt de factuur — veiligheid:
    # alleen items van diezelfde leverancier worden meegenomen, ongeacht bron.
    alle_geselecteerd = [("lo", o) for o in geselecteerde_orders] + [("tp", t) for t in geselecteerde_transport]
    if not alle_geselecteerd:
        return redirect(url_for("facturen_pagina", modus="inkoop"))
    eerste_leverancier = alle_geselecteerd[0][1].get("leverancier","")

    regels = []
    totaal_bedrag = 0.0
    lo_gefactureerd_ids = set()
    tp_gefactureerd_ids = set()

    for bron, item in alle_geselecteerd:
        if item.get("leverancier","") != eerste_leverancier:
            continue
        contract = alle_handelsorders.get(item.get("contract_referentie",""))
        prijs_per_ton = float(contract["prijs"]) if contract and contract.get("prijs") else 0.0
        valuta = contract.get("valuta", "EUR") if contract else "EUR"
        if bron == "lo":
            ton = parse_ton_intern(item.get("werkelijke_hoeveelheid",""))
            referentie = item.get("ordernummer","")
            datum = item.get("datum","")
            lo_gefactureerd_ids.add(item["id"])
        else:
            ton = parse_ton_intern(item.get("hoeveelheid",""))
            referentie = item.get("referentienummer","")
            datum = item.get("aangemaakt","")[:10] if item.get("aangemaakt") else ""
            tp_gefactureerd_ids.add(item["id"])
        bedrag = round(ton * prijs_per_ton, 2)
        totaal_bedrag += bedrag
        regels.append({
            "bron": bron, "item_id": item["id"], "referentienummer": referentie, "datum": datum,
            "materiaal": item.get("materiaal",""), "kwaliteit": item.get("kwaliteit",""),
            "ton": ton, "prijs_per_ton": prijs_per_ton, "valuta": valuta, "bedrag": bedrag,
            "contractnummer": item.get("contract_referentie",""),
        })

    if not regels:
        return redirect(url_for("facturen_pagina", modus="inkoop"))

    contractnummers = {r["contractnummer"] for r in regels}
    nu = datetime.datetime.now()

    termijn_dagen = 30
    _termijn_ingesteld = leverancier_instelling_voor(eerste_leverancier).get("standaard_betalingstermijn","")
    if _termijn_ingesteld:
        try:
            termijn_dagen = int(_termijn_ingesteld)
        except (ValueError, TypeError):
            pass
    vervaldatum = (nu.date() + datetime.timedelta(days=termijn_dagen)).isoformat()

    alle_facturen = laad_facturen()
    nieuwe_factuur = {
        "id": str(uuid.uuid4()),
        "factuurnummer": "", "workflow_status": "concept",
        "bedrijf": eerste_leverancier,
        "klant_gegevens": haal_factuurgegevens_bedrijf(eerste_leverancier),
        "type": "inkoop",
        "referentie": f"INKOOP-{nu.strftime('%Y%m%d')}-{len([f for f in alle_facturen if f.get('type')=='inkoop' and f.get('aangemaakt','').startswith(nu.strftime('%d-%m-%Y'))]) + 1:03d}",
        "omschrijving": f"{len(regels)} lading{'en' if len(regels) != 1 else ''} — {', '.join(sorted(contractnummers))}",
        "regels": regels,
        "bedrag": str(round(totaal_bedrag, 2)),
        "btw_percentage": "21",  # standaard NL-BTW; wordt genegeerd als BTW verlegd van toepassing is
        "factuurdatum": nu.date().isoformat(),
        "leverdatum": _leverdatum_uit_regels(regels),
        "vervaldatum": vervaldatum,
        "betaalddatum": "",
        "contract_referentie": next(iter(contractnummers)) if len(contractnummers) == 1 else "",
        "gebruiker": session.get("gebruikersnaam", ""),
        "aangemaakt": nu.strftime("%d-%m-%Y %H:%M"),
    }
    alle_facturen.append(nieuwe_factuur)
    bewaar_facturen(alle_facturen)

    if lo_gefactureerd_ids:
        for o in alle_orders:
            if o["id"] in lo_gefactureerd_ids:
                o["status"] = "Gefactureerd"
        bewaar_logistieke_orders(alle_orders)
    if tp_gefactureerd_ids:
        for t in alle_transport:
            if t["id"] in tp_gefactureerd_ids:
                t["gefactureerd"] = True
        bewaar_transport_planning(alle_transport)

    return redirect(url_for("facturen_pagina", modus="overzicht", bedrijf=eerste_leverancier))


def _peute_factuur_inhoud():
    """Wat er nog gefactureerd moet worden voor 'Peute' (alles wat op locatie
    binnenkomt via de Weegbrug): gewogen ladingen met een gekoppeld
    inkoopcontract, nog niet gefactureerd. Gegroepeerd per leverancier —
    typisch scenario: leverancier levert meerdere vrachtwagens per week,
    en aan het einde van de week vink je ze allemaal aan voor één factuur."""
    alle_orders = laad_logistieke_orders()
    alle_handelsorders = {h["contractnummer"]: h for h in laad_handelsorders()}

    te_factureren = [
        o for o in alle_orders
        if o.get("contract_referentie") and o.get("status") not in ("Gefactureerd", "Afgerond")
    ]

    for o in te_factureren:
        contract = alle_handelsorders.get(o["contract_referentie"])
        o["_prijs_per_ton"] = float(contract["prijs"]) if contract and contract.get("prijs") else None
        o["_valuta"] = contract.get("valuta", "EUR") if contract else "EUR"
        o["_ton"] = parse_ton_intern(o.get("werkelijke_hoeveelheid", ""))
        o["_bedrag"] = round(o["_ton"] * o["_prijs_per_ton"], 2) if o["_prijs_per_ton"] is not None else None

    per_leverancier = {}
    for o in te_factureren:
        per_leverancier.setdefault(o.get("leverancier","Onbekend"), []).append(o)
    for lijst in per_leverancier.values():
        lijst.sort(key=lambda o: o.get("datum",""), reverse=True)
    leverancier_groepen = sorted(
        [{"leverancier": lev, "orders": orders, "aantal": len(orders),
          "totaal_ton": round(sum(o["_ton"] for o in orders), 3),
          "totaal_bedrag": round(sum(o["_bedrag"] for o in orders if o["_bedrag"] is not None), 2)}
         for lev, orders in per_leverancier.items()],
        key=lambda g: g["leverancier"]
    )

    inhoud = """
<p style="color:var(--gray-400);margin-top:0;margin-bottom:16px;font-size:0.85rem;">Gewogen ladingen met een gekoppeld inkoopcontract, nog niet gefactureerd — per leverancier. Vink de ladingen aan die op één factuur moeten (bv. alle leveringen van deze week) en klik op 'Factuur aanmaken'.</p>

<style>
.pf-groep { border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); margin-bottom:20px; }
.pf-groepkop { padding:12px 14px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); display:flex; align-items:center; gap:12px; font-size:12.5px; }
.pf-rij { padding:9px 14px; border-bottom:1px solid var(--gray-100); font-size:12.5px; display:flex; align-items:center; gap:12px; }
.pf-rij:last-child { border-bottom:none; }
</style>

{% if leverancier_groepen %}
{% for g in leverancier_groepen %}
<form method="POST" action="/facturen/peute/genereer" class="pf-groep-form">
<div class="pf-groep">
    <div class="pf-groepkop">
        <b style="flex:1;color:var(--gray-800);">{{ g.leverancier }}</b>
        <span style="color:var(--gray-400);">{{ g.aantal }} lading{{ 'en' if g.aantal != 1 else '' }} · {{ g.totaal_ton }} t open</span>
        <button type="submit" style="font-size:12px;font-weight:700;padding:6px 14px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;cursor:pointer;">Factuur aanmaken van geselecteerde →</button>
    </div>
    {% for o in g.orders %}
    <div class="pf-rij">
        <input type="checkbox" name="order_ids" value="{{ o.id }}" checked style="margin:0;">
        <span style="width:90px;color:var(--gray-500);">{{ o.datum }}</span>
        <span style="width:120px;font-family:var(--font-mono);color:var(--gray-500);">{{ o.ordernummer }}</span>
        <span style="flex:1;color:var(--gray-600);">{{ o.materiaal }} — {{ o.kwaliteit }}</span>
        <span style="width:130px;color:var(--gray-500);">{{ o.contract_referentie }}</span>
        <span style="width:90px;text-align:right;font-family:var(--font-mono);color:var(--gray-700);">{{ o._ton }} t</span>
        {% if o._prijs_per_ton is not none %}
        <span style="width:90px;text-align:right;color:var(--gray-500);">{{ o._prijs_per_ton }}/t</span>
        <span style="width:100px;text-align:right;font-family:var(--font-mono);font-weight:700;color:var(--gray-800);">{{ "%.2f"|format(o._bedrag) }} {{ o._valuta }}</span>
        {% else %}
        <span style="width:190px;text-align:right;color:#dc2626;font-size:11px;">Geen prijs op het contract — bedrag onbekend</span>
        {% endif %}
    </div>
    {% endfor %}
</div>
</form>
{% endfor %}
{% else %}
<div class="lege-staat">Niets te factureren — alle gewogen, gekoppelde ladingen zijn al gefactureerd.</div>
{% endif %}
    """
    return inhoud, {"leverancier_groepen": leverancier_groepen}


@app.route("/facturen/peute/genereer", methods=["POST"])
def facturen_peute_genereer():
    """Maakt één factuur aan van de geselecteerde, gewogen ladingen — met een
    regel per lading (datum, ton, prijs, bedrag) en een totaalbedrag. Alle
    geselecteerde orders moeten van dezelfde leverancier zijn (een factuur
    gaat naar één partij); de leverancier wordt bepaald aan de hand van de
    eerste geselecteerde order."""
    _guard = vereist_afdeling_of_403("facturen")
    if _guard: return _guard

    order_ids = request.form.getlist("order_ids")
    if not order_ids:
        return redirect(url_for("facturen_pagina", modus="peute"))

    alle_orders = laad_logistieke_orders()
    alle_handelsorders = {h["contractnummer"]: h for h in laad_handelsorders()}
    geselecteerd = [o for o in alle_orders if o["id"] in order_ids]
    if not geselecteerd:
        return redirect(url_for("facturen_pagina", modus="peute"))

    leverancier = geselecteerd[0].get("leverancier", "")
    geselecteerd = [o for o in geselecteerd if o.get("leverancier") == leverancier]  # veiligheid: alleen dezelfde leverancier

    regels = []
    totaal_bedrag = 0.0
    for o in geselecteerd:
        contract = alle_handelsorders.get(o.get("contract_referentie",""))
        prijs_per_ton = float(contract["prijs"]) if contract and contract.get("prijs") else 0.0
        valuta = contract.get("valuta", "EUR") if contract else "EUR"
        ton = parse_ton_intern(o.get("werkelijke_hoeveelheid",""))
        bedrag = round(ton * prijs_per_ton, 2)
        totaal_bedrag += bedrag
        regels.append({
            "logistieke_order_id": o["id"], "ordernummer": o.get("ordernummer",""),
            "datum": o.get("datum",""), "materiaal": o.get("materiaal",""), "kwaliteit": o.get("kwaliteit",""),
            "ton": ton, "prijs_per_ton": prijs_per_ton, "valuta": valuta, "bedrag": bedrag,
            "contractnummer": o.get("contract_referentie",""),
        })

    contractnummers = {r["contractnummer"] for r in regels}
    nu = datetime.datetime.now()

    # Vervaldatum: standaard betalingstermijn van de leverancier indien ingesteld, anders 30 dagen.
    termijn_dagen = 30
    _termijn_ingesteld = leverancier_instelling_voor(leverancier).get("standaard_betalingstermijn","")
    if _termijn_ingesteld:
        try:
            termijn_dagen = int(_termijn_ingesteld)
        except (ValueError, TypeError):
            pass
    vervaldatum = (nu.date() + datetime.timedelta(days=termijn_dagen)).isoformat()

    alle_facturen = laad_facturen()
    nieuwe_factuur = {
        "id": str(uuid.uuid4()),
        "factuurnummer": "", "workflow_status": "concept",
        "bedrijf": leverancier,
        "klant_gegevens": haal_factuurgegevens_bedrijf(leverancier),
        "type": "peute",
        "referentie": f"PEUTE-{nu.strftime('%Y%m%d')}-{len([f for f in alle_facturen if f.get('type')=='peute' and f.get('aangemaakt','').startswith(nu.strftime('%d-%m-%Y'))]) + 1:03d}",
        "omschrijving": f"{len(regels)} lading{'en' if len(regels) != 1 else ''} — {', '.join(sorted(contractnummers))}",
        "regels": regels,
        "bedrag": str(round(totaal_bedrag, 2)),
        "btw_percentage": "21",  # standaard NL-BTW; wordt genegeerd als BTW verlegd van toepassing is
        "factuurdatum": nu.date().isoformat(),
        "leverdatum": _leverdatum_uit_regels(regels),
        "vervaldatum": vervaldatum,
        "betaalddatum": "",
        "contract_referentie": next(iter(contractnummers)) if len(contractnummers) == 1 else "",
        "gebruiker": session.get("gebruikersnaam", ""),
        "aangemaakt": nu.strftime("%d-%m-%Y %H:%M"),
    }
    alle_facturen.append(nieuwe_factuur)
    bewaar_facturen(alle_facturen)

    for o in alle_orders:
        if o["id"] in [r["logistieke_order_id"] for r in regels]:
            o["status"] = "Gefactureerd"
    bewaar_logistieke_orders(alle_orders)

    return redirect(url_for("facturen_pagina", modus="overzicht", bedrijf=leverancier))


@app.route("/facturen/nieuw", methods=["GET", "POST"])
def facturen_nieuw():
    """Handmatig een factuur toevoegen — een eigen, aparte pagina (i.p.v. een
    formulier ingeklemd tussen de KPI's en de factuurlijst op het Overzicht-
    tabblad) voor overzichtelijkheid. Bereikbaar met een vooringevulde
    leverancier/klant via ?bedrijf=... (bv. vanaf de Leveranciers/Klanten-
    pagina, een contract, of het bedrijfsprofiel)."""
    _guard = vereist_afdeling_of_403("facturen")
    if _guard: return _guard

    if request.method == "POST":
        bedrijf_naam = request.form.get("bedrijf", "").strip()
        alle_facturen_voor_nummer = laad_facturen()
        nieuwe_factuur = {
            "id": str(uuid.uuid4()),
            "factuurnummer": "", "workflow_status": "concept",
            "bedrijf": bedrijf_naam,
            "klant_gegevens": haal_factuurgegevens_bedrijf(bedrijf_naam),
            "referentie": request.form.get("referentie", "").strip(),
            "omschrijving": request.form.get("omschrijving", "").strip(),
            "bedrag": request.form.get("bedrag", "").strip(),
            "btw_percentage": request.form.get("btw_percentage", "").strip(),
            "factuurdatum": request.form.get("factuurdatum", "").strip() or datetime.date.today().isoformat(),
            "leverdatum": request.form.get("leverdatum", "").strip(),
            "vervaldatum": request.form.get("vervaldatum", "").strip(),
            "betaalddatum": "",
            "contract_referentie": request.form.get("contract_referentie", "").strip(),
            "incoterm": request.form.get("incoterm", "").strip(),
            "gebruiker": session.get("gebruikersnaam", ""),
            "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
        }
        if nieuwe_factuur["bedrijf"] and nieuwe_factuur["bedrag"] and nieuwe_factuur["vervaldatum"]:
            alle_facturen_voor_nummer.append(nieuwe_factuur)
            bewaar_facturen(alle_facturen_voor_nummer)
            return redirect(url_for("factuur_detail", factuur_id=nieuwe_factuur["id"]))
        # Verplichte velden ontbreken -> terug naar het formulier, met wat al was ingevuld behouden
        return redirect(url_for("facturen_nieuw", bedrijf=nieuwe_factuur["bedrijf"],
                                  referentie=nieuwe_factuur["referentie"], bedrag=nieuwe_factuur["bedrag"],
                                  factuurdatum=nieuwe_factuur["factuurdatum"], vervaldatum=nieuwe_factuur["vervaldatum"],
                                  contract_referentie=nieuwe_factuur["contract_referentie"]))

    vooringevuld_bedrijf = request.args.get("bedrijf", "")
    vi_contract = request.args.get("contract_referentie", "").strip()
    vi_referentie = request.args.get("referentie", "").strip()
    vi_bedrag = request.args.get("bedrag", "").strip()
    vi_factuurdatum = request.args.get("factuurdatum", "").strip()
    vi_leverdatum = request.args.get("leverdatum", "").strip()
    vi_vervaldatum = request.args.get("vervaldatum", "").strip()
    vi_incoterm = request.args.get("incoterm", "").strip()

    _status_alle_fact = laad_status()
    _accountmanagers_alle_fact = laad_accountmanagers()
    alle_bedrijfsnamen_fact = sorted(set(_status_alle_fact.keys()) | set(_accountmanagers_alle_fact.keys()))[:500]

    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/facturen" style="color:var(--gray-400);text-decoration:none;">Facturen</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">Nieuwe factuur</span>
</div>
<div class="page-title">Factuur toevoegen</div>

<div style="background:#fff;border:1px solid var(--gray-200);border-radius:10px;padding:20px 22px;max-width:600px;">
    {% if vi_contract %}
    <div style="background:#eff6ff;color:#1d4ed8;padding:10px 14px;border-radius:8px;margin-bottom:16px;font-size:12.5px;">
        Wordt gekoppeld aan contract <b>{{ vi_contract }}</b>.
    </div>
    {% endif %}
    <form method="POST">
        <input type="hidden" name="contract_referentie" value="{{ vi_contract }}">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Bedrijf</label>
        <input type="text" name="bedrijf" placeholder="Bedrijfsnaam" value="{{ vooringevuld_bedrijf }}" list="bedrijvenLijstFacturen" required style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-bottom:14px;margin-top:4px;box-sizing:border-box;">
        <datalist id="bedrijvenLijstFacturen">{% for naam in alle_bedrijfsnamen_fact %}<option value="{{ naam }}">{% endfor %}</datalist>

        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Referentie / omschrijving</label>
        <input type="text" name="referentie" placeholder="Referentie / omschrijving" value="{{ vi_referentie }}" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-bottom:14px;margin-top:4px;box-sizing:border-box;">

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;">
            <div>
                <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Bedrag (€)</label>
                <input type="text" name="bedrag" placeholder="Bedrag (€)" value="{{ vi_bedrag }}" required style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-top:4px;box-sizing:border-box;">
            </div>
            <div>
                <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">BTW %</label>
                <select name="btw_percentage" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-top:4px;box-sizing:border-box;">
                    <option value="">BTW %</option>
                    <option value="0">0%</option>
                    <option value="9">9%</option>
                    <option value="21">21%</option>
                </select>
            </div>
            <div>
                <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Factuurdatum</label>
                <input type="date" name="factuurdatum" value="{{ vi_factuurdatum }}" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-top:4px;box-sizing:border-box;">
            </div>
            <div>
                <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Leveringsdatum (indien anders)</label>
                <input type="date" name="leverdatum" value="{{ vi_leverdatum }}" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-top:4px;box-sizing:border-box;">
            </div>
            <div>
                <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Vervaldatum</label>
                <input type="date" name="vervaldatum" value="{{ vi_vervaldatum }}" required style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-top:4px;box-sizing:border-box;">
            </div>
            <div>
                <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Incoterm (bij internationaal)</label>
                <input type="text" name="incoterm" placeholder="bv. FCA, CIF, DAP" value="{{ vi_incoterm }}" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-top:4px;box-sizing:border-box;">
            </div>
        </div>
        <div style="margin-top:20px;display:flex;gap:8px;">
            <button type="submit" style="padding:9px 20px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-weight:700;cursor:pointer;font-size:13px;">+ Factuur toevoegen</button>
            <a href="/facturen" style="padding:9px 20px;color:var(--gray-400);text-decoration:none;font-size:13px;">Annuleren</a>
        </div>
    </form>
</div>
    """
    pagina = render_simple_page("Factuur toevoegen", "facturen", inhoud)
    return render_template_string(pagina, vooringevuld_bedrijf=vooringevuld_bedrijf, vi_contract=vi_contract,
                                    vi_referentie=vi_referentie, vi_bedrag=vi_bedrag, vi_factuurdatum=vi_factuurdatum,
                                    vi_leverdatum=vi_leverdatum, vi_incoterm=vi_incoterm,
                                    vi_vervaldatum=vi_vervaldatum, alle_bedrijfsnamen_fact=alle_bedrijfsnamen_fact)


@app.route("/facturen", methods=["GET", "POST"])
def facturen_pagina():
    """Facturen als tabbladen: Overzicht (alle facturen, KPI's, BTW-alerts,
    handmatig toevoegen — de oorspronkelijke pagina), Inkoop, Verkoop, Export
    (alles wat geëxporteerd wordt) en Peute (alles wat op locatie binnenkomt,
    via de Weegbrug). Peute heeft de volledige 'selecteer gewogen ladingen met
    gekoppeld contract -> genereer één factuur'-flow; de andere tabbladen
    tonen voorlopig wat er al is, met de bestaande 'handmatig toevoegen' op
    Overzicht als gemeenschappelijke ingang."""
    _guard = vereist_afdeling_of_403("facturen")
    if _guard: return _guard

    modus = request.args.get("modus", "overzicht")
    if modus not in ("overzicht", "inkoop", "verkoop", "export", "peute"):
        modus = "overzicht"

    if modus == "overzicht":
        _resultaat = _overzicht_factuur_inhoud()
        if isinstance(_resultaat, Response):
            return _resultaat  # POST-verwerking (markeer_betaald/verwijderen/toevoegen) deed al een redirect
        _tab_inhoud, _tab_context = _resultaat
    elif modus == "inkoop":
        _tab_inhoud, _tab_context = _inkoop_factuur_inhoud()
    elif modus == "verkoop":
        _tab_inhoud, _tab_context = _verkoop_factuur_inhoud()
    elif modus == "export":
        _tab_inhoud, _tab_context = _export_factuur_inhoud()
    else:
        _tab_inhoud, _tab_context = _peute_factuur_inhoud()

    _tabbladen = [("overzicht", "Overzicht"), ("inkoop", "Inkoop"), ("verkoop", "Verkoop"), ("export", "Export"), ("peute", "Peute")]
    _tabbladen_html = "".join(
        f'<a href="/facturen?modus={sleutel}" style="padding:8px 16px;font-size:12.5px;font-weight:700;text-decoration:none;border-bottom:2px solid {"var(--brand-600)" if sleutel == modus else "transparent"};color:{"var(--brand-600)" if sleutel == modus else "var(--gray-400)"};">{titel}</a>'
        for sleutel, titel in _tabbladen
    )

    inhoud = f"""
<div class="page-title">Facturen</div>
<div style="display:flex;gap:4px;border-bottom:1px solid var(--gray-200);margin-bottom:16px;">
    {_tabbladen_html}
</div>
{_tab_inhoud}
    """
    pagina = render_simple_page("Facturen", "facturen", inhoud)
    return render_template_string(pagina, **_tab_context)


def _genereer_factuur_pdf(factuur):
    """Bouwt een volledige, wettelijk correcte NL-factuur als PDF: eigen
    bedrijfsgegevens (afzender), klantgegevens (incl. BTW-nummer bij EU B2B),
    factuurgegevens (nummer/datum/leverdatum/vervaldatum), regels met
    omschrijving/aantal/prijs/subtotaal, en de BTW-uitsplitsing (of 'BTW
    verlegd' met toelichting). Internationale velden (incoterm, EORI) alleen
    getoond als ze zijn ingevuld — een binnenlandse factuur wordt er niet
    onnodig mee volgestouwd."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT

    eigen = laad_eigen_bedrijfsgegevens()
    klant = factuur.get("klant_gegevens") or {"naam": factuur.get("bedrijf",""), "adres":"", "postcode":"", "stad":"", "land":"", "kvk_nummer":"", "vat_nummer":""}
    bedragen = bereken_factuur_bedragen(factuur)
    regels = factuur.get("regels", [])

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=18*mm, bottomMargin=18*mm, leftMargin=20*mm, rightMargin=20*mm)
    stijlen = getSampleStyleSheet()
    titel_stijl = ParagraphStyle("FactuurTitel", parent=stijlen["Title"], fontSize=20, textColor=colors.HexColor("#0d5c62"))
    label_stijl = ParagraphStyle("Label", parent=stijlen["Normal"], fontSize=8.5, textColor=colors.HexColor("#64748b"))
    klein_stijl = ParagraphStyle("Klein", parent=stijlen["Normal"], fontSize=8.5, textColor=colors.HexColor("#64748b"), leading=12)
    normaal_stijl = stijlen["Normal"]
    rechts_stijl = ParagraphStyle("Rechts", parent=stijlen["Normal"], alignment=TA_RIGHT)

    elementen = []

    # --- Header: eigen bedrijfsgegevens (afzender) links, klant rechts ---
    eigen_adresregel = f"{eigen.get('adres','')}<br/>{eigen.get('postcode','')} {eigen.get('stad','')}<br/>{eigen.get('land','')}"
    eigen_blok = [
        Paragraph(f"<b>{eigen.get('naam','') or '—'}</b>", normaal_stijl),
        Paragraph(eigen_adresregel, klein_stijl),
        Spacer(1, 4),
        Paragraph(f"KvK: {eigen.get('kvk_nummer','') or '—'}", klein_stijl),
        Paragraph(f"BTW-id: {eigen.get('btw_nummer','') or '—'}", klein_stijl),
        Paragraph(f"IBAN: {eigen.get('iban','') or '—'}{' · BIC: ' + eigen['bic'] if eigen.get('bic') else ''}", klein_stijl),
    ]
    klant_adresregel = f"{klant.get('adres','') or '—'}<br/>{klant.get('postcode','')} {klant.get('stad','')}<br/>{klant.get('land','')}"
    klant_blok = [
        Paragraph("<b>Factuur aan</b>", label_stijl),
        Paragraph(f"<b>{klant.get('naam','') or '—'}</b>", normaal_stijl),
        Paragraph(klant_adresregel, klein_stijl),
    ]
    if klant.get("kvk_nummer"):
        klant_blok.append(Paragraph(f"KvK: {klant['kvk_nummer']}", klein_stijl))
    if klant.get("vat_nummer"):
        klant_blok.append(Paragraph(f"BTW-nummer: {klant['vat_nummer']}", klein_stijl))

    header_tabel = Table([[eigen_blok, klant_blok]], colWidths=[85*mm, 75*mm])
    header_tabel.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP")]))
    elementen.append(header_tabel)
    elementen.append(Spacer(1, 22))

    # --- Titel + factuurgegevens ---
    is_concept = factuur.get("workflow_status", "definitief") == "concept"
    is_credit = factuur.get("is_creditnota", False)
    titel_tekst = "Creditfactuur" if is_credit else "Factuur"
    if is_concept:
        titel_tekst += " — CONCEPT (nog niet definitief)"
    elementen.append(Paragraph(titel_tekst, titel_stijl))
    elementen.append(Spacer(1, 8))

    def factuurgegevens_rij(label, waarde):
        return [Paragraph(label, label_stijl), Paragraph(str(waarde) if waarde else "—", normaal_stijl)]

    factuurgegevens = [
        factuurgegevens_rij("Conceptreferentie (nog geen definitief factuurnummer)" if is_concept else "Factuurnummer",
                              factuur.get("referentie","") if is_concept else factuur.get("factuurnummer","")),
        factuurgegevens_rij("Factuurdatum", factuur.get("factuurdatum","")),
    ]
    if is_credit:
        factuurgegevens.append(factuurgegevens_rij("Creditfactuur bij factuurnummer", factuur.get("credit_van_factuurnummer","")))
    if factuur.get("leverdatum") and factuur.get("leverdatum") != factuur.get("factuurdatum"):
        factuurgegevens.append(factuurgegevens_rij("Leverings-/prestatiedatum", factuur["leverdatum"]))
    factuurgegevens.append(factuurgegevens_rij("Uiterste betaaldatum", factuur.get("vervaldatum","")))
    if factuur.get("incoterm"):
        factuurgegevens.append(factuurgegevens_rij("Incoterm", factuur["incoterm"]))
    if eigen.get("eori_nummer") and bedragen["btw_verlegd"]:
        factuurgegevens.append(factuurgegevens_rij("EORI-nummer", eigen["eori_nummer"]))

    fg_tabel = Table(factuurgegevens, colWidths=[55*mm, 105*mm])
    fg_tabel.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"), ("BOTTOMPADDING", (0,0), (-1,-1), 4), ("TOPPADDING", (0,0), (-1,-1), 4),
    ]))
    elementen.append(fg_tabel)
    elementen.append(Spacer(1, 20))

    # --- Regels ---
    if regels:
        kop = [Paragraph("Datum", label_stijl), Paragraph("Omschrijving", label_stijl),
               Paragraph("Aantal (t)", label_stijl), Paragraph("Prijs/t", label_stijl),
               Paragraph("Bedrag", label_stijl)]
        regelrijen = [kop]
        for r in regels:
            omschrijving = f"{r.get('materiaal','')} — {r.get('kwaliteit','')}" if r.get("kwaliteit") else r.get("materiaal","")
            if r.get("contractnummer"):
                omschrijving += f"<br/><font size=7 color='#94a3b8'>{r['contractnummer']}</font>"
            try:
                bedrag_tekst = f"{float(r.get('bedrag', 0)):.2f}"
            except (ValueError, TypeError):
                bedrag_tekst = str(r.get("bedrag", ""))
            regelrijen.append([
                Paragraph(r.get("datum","") or "—", normaal_stijl),
                Paragraph(omschrijving, normaal_stijl),
                Paragraph(f"{r.get('ton','')}", rechts_stijl),
                Paragraph(f"{r.get('prijs_per_ton','')} {r.get('valuta','')}", rechts_stijl),
                Paragraph(bedrag_tekst, rechts_stijl),
            ])
        regeltabel = Table(regelrijen, colWidths=[22*mm, 68*mm, 22*mm, 28*mm, 28*mm])
        regeltabel.setStyle(TableStyle([
            ("LINEBELOW", (0,0), (-1,0), 0.8, colors.HexColor("#0d5c62")),
            ("LINEBELOW", (0,1), (-1,-1), 0.4, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
            ("VALIGN", (0,0), (-1,-1), "TOP"),
        ]))
        elementen.append(regeltabel)
    else:
        # Handmatige factuur zonder regels: één omschrijvingsregel met het totaalbedrag.
        enkele_rij = [[Paragraph("Omschrijving", label_stijl), Paragraph("Bedrag", label_stijl)],
                       [Paragraph(factuur.get("omschrijving") or factuur.get("referentie") or "—", normaal_stijl),
                        Paragraph(f"{bedragen['subtotaal']:.2f}", rechts_stijl)]]
        enkele_tabel = Table(enkele_rij, colWidths=[130*mm, 40*mm])
        enkele_tabel.setStyle(TableStyle([
            ("LINEBELOW", (0,0), (-1,0), 0.8, colors.HexColor("#0d5c62")),
            ("LINEBELOW", (0,1), (-1,-1), 0.4, colors.HexColor("#e2e8f0")),
            ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ]))
        elementen.append(enkele_tabel)

    elementen.append(Spacer(1, 14))

    # --- Totalen: subtotaal excl. BTW, BTW-bedrag (of 'BTW verlegd'), totaal incl. BTW ---
    valuta = regels[0].get("valuta", "EUR") if regels else "EUR"
    totalen_rijen = [[Paragraph("Subtotaal (excl. BTW)", normaal_stijl), Paragraph(f"{valuta} {bedragen['subtotaal']:.2f}", rechts_stijl)]]
    if bedragen["btw_verlegd"]:
        totalen_rijen.append([Paragraph("BTW verlegd", normaal_stijl), Paragraph("€ 0,00", rechts_stijl)])
    else:
        totalen_rijen.append([Paragraph(f"BTW ({bedragen['btw_percentage']:.0f}%)", normaal_stijl), Paragraph(f"{valuta} {bedragen['btw_bedrag']:.2f}", rechts_stijl)])
    totalen_rijen.append([Paragraph("<b>Totaal (incl. BTW)</b>", normaal_stijl), Paragraph(f"<b>{valuta} {bedragen['totaal']:.2f}</b>", rechts_stijl)])

    totalen_tabel = Table(totalen_rijen, colWidths=[150*mm, 20*mm])
    totalen_tabel.setStyle(TableStyle([
        ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LINEABOVE", (0,-1), (-1,-1), 0.8, colors.HexColor("#0d5c62")),
    ]))
    elementen.append(totalen_tabel)

    if bedragen["btw_verlegd"]:
        elementen.append(Spacer(1, 10))
        elementen.append(Paragraph(bedragen["btw_verlegd_uitleg"], klein_stijl))

    elementen.append(Spacer(1, 24))
    elementen.append(Paragraph(
        f"Gelieve het totaalbedrag vóór {factuur.get('vervaldatum','') or 'de uiterste betaaldatum'} over te maken naar "
        f"IBAN {eigen.get('iban','') or '—'} onder vermelding van factuurnummer {factuur.get('factuurnummer','')}.",
        klein_stijl
    ))

    doc.build(elementen)
    buffer.seek(0)
    return buffer.read()


@app.route("/facturen/<factuur_id>/pdf")
def factuur_pdf(factuur_id):
    _guard = vereist_afdeling_of_403("facturen")
    if _guard: return _guard

    alle_facturen = laad_facturen()
    factuur = next((f for f in alle_facturen if f.get("id") == factuur_id), None)
    if not factuur:
        pagina = render_simple_page("Niet gevonden", "facturen", '<div class="page-title">Factuur niet gevonden</div><div class="lege-staat">Deze factuur bestaat niet (meer). <a href="/facturen">Terug naar Facturen</a></div>')
        return render_template_string(pagina), 404

    pdf_bytes = _genereer_factuur_pdf(factuur)
    bestandsnaam = factuur.get("factuurnummer") or factuur.get("referentie") or factuur_id
    return Response(pdf_bytes, mimetype="application/pdf",
                     headers={"Content-Disposition": f'inline; filename="factuur_{bestandsnaam}.pdf"'})


@app.route("/facturen/<factuur_id>/definitief-maken", methods=["POST"])
def factuur_definitief_maken(factuur_id):
    """Concept -> Definitief: kent nu pas het echte, doorlopende
    factuurnummer toe (dat mag wettelijk geen gaten hebben, dus pas toekennen
    zodra een factuur ook echt de deur uitgaat, niet al bij het concept — een
    verwijderd concept zou anders een gat in de reeks achterlaten). Dit is
    tegelijk het moment van 'verzenden' naar de leverancier/klant."""
    _guard = vereist_afdeling_of_403("facturen")
    if _guard: return _guard

    alle_facturen = laad_facturen()
    factuur = next((f for f in alle_facturen if f.get("id") == factuur_id), None)
    if not factuur or factuur.get("workflow_status") != "concept":
        return redirect(url_for("factuur_detail", factuur_id=factuur_id))

    factuur["factuurnummer"] = genereer_factuurnummer(alle_facturen)
    factuur["workflow_status"] = "definitief"
    factuur["definitief_op"] = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
    factuur["definitief_door"] = session.get("gebruikersnaam", "")
    bewaar_facturen(alle_facturen)
    return redirect(url_for("factuur_detail", factuur_id=factuur_id))


@app.route("/facturen/<factuur_id>/verwijder-concept", methods=["POST"])
def factuur_verwijder_concept(factuur_id):
    """Verwijdert een conceptfactuur (alleen conceptfacturen — een definitieve
    factuur mag niet zomaar verdwijnen, wettelijk vereist een creditfactuur
    voor correctie). Draait de 'gefactureerd'-markering van de onderliggende
    ladingen/transporten terug, zodat die weer gewoon selecteerbaar zijn."""
    _guard = vereist_afdeling_of_403("facturen")
    if _guard: return _guard

    alle_facturen = laad_facturen()
    factuur = next((f for f in alle_facturen if f.get("id") == factuur_id), None)
    if not factuur or factuur.get("workflow_status") != "concept":
        return redirect(url_for("factuur_detail", factuur_id=factuur_id))

    _herstel_items_van_regels(factuur.get("regels", []))
    alle_facturen = [f for f in alle_facturen if f.get("id") != factuur_id]
    bewaar_facturen(alle_facturen)
    return redirect(url_for("facturen_pagina", modus="overzicht"))


@app.route("/facturen/<factuur_id>/boekhouding", methods=["POST"])
def factuur_naar_boekhouding(factuur_id):
    """Markeert een definitieve factuur als verstuurd naar het
    boekhoudpakket — losstaand van het versturen naar de leverancier/klant
    zelf (dat gebeurt al bij het definitief maken). Zoals elders in het
    systeem: de boekhoudkoppeling zelf is nog niet actief, dit legt wel al
    het moment en wie het deed vast, klaar voor als die koppeling er is."""
    _guard = vereist_afdeling_of_403("facturen")
    if _guard: return _guard

    alle_facturen = laad_facturen()
    factuur = next((f for f in alle_facturen if f.get("id") == factuur_id), None)
    if not factuur or factuur.get("workflow_status") != "definitief":
        return redirect(url_for("factuur_detail", factuur_id=factuur_id))

    factuur["verstuurd_naar_boekhouding_op"] = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
    factuur["verstuurd_naar_boekhouding_door"] = session.get("gebruikersnaam", "")
    bewaar_facturen(alle_facturen)
    return redirect(url_for("factuur_detail", factuur_id=factuur_id))


@app.route("/facturen/<factuur_id>/crediteren", methods=["POST"])
def factuur_crediteren(factuur_id):
    """Maakt een creditfactuur aan voor een definitieve factuur — zelfde
    bedragen maar negatief, als concept (moet ook eerst akkoord/definitief
    doorlopen). Alleen mogelijk voor een definitieve, niet-credit factuur die
    nog niet eerder gecrediteerd is (anders zou je per ongeluk twee keer
    kunnen crediteren)."""
    _guard = vereist_afdeling_of_403("facturen")
    if _guard: return _guard

    alle_facturen = laad_facturen()
    origineel = next((f for f in alle_facturen if f.get("id") == factuur_id), None)
    if not origineel or origineel.get("workflow_status") != "definitief" or origineel.get("is_creditnota"):
        return redirect(url_for("factuur_detail", factuur_id=factuur_id))
    if any(f.get("credit_van_factuur_id") == factuur_id for f in alle_facturen):
        return redirect(url_for("factuur_detail", factuur_id=factuur_id))  # al gecrediteerd

    nu = datetime.datetime.now()
    negatieve_regels = []
    for r in origineel.get("regels", []):
        r_neg = dict(r)
        r_neg["ton"] = -r_neg.get("ton", 0)
        r_neg["bedrag"] = -r_neg.get("bedrag", 0)
        negatieve_regels.append(r_neg)

    creditnota = {
        "id": str(uuid.uuid4()),
        "factuurnummer": "", "workflow_status": "concept",
        "bedrijf": origineel["bedrijf"],
        "klant_gegevens": origineel.get("klant_gegevens", {}),
        "type": origineel.get("type", ""),
        "is_creditnota": True,
        "credit_van_factuur_id": factuur_id,
        "credit_van_factuurnummer": origineel.get("factuurnummer", ""),
        "referentie": f"CREDIT-{origineel.get('factuurnummer','')}",
        "omschrijving": f"Creditfactuur voor {origineel.get('factuurnummer','')}",
        "regels": negatieve_regels,
        "bedrag": str(-round(float(origineel.get("bedrag", 0)), 2)),
        "btw_percentage": origineel.get("btw_percentage", "21"),
        "factuurdatum": nu.date().isoformat(),
        "leverdatum": origineel.get("leverdatum", ""),
        "vervaldatum": nu.date().isoformat(),  # creditfacturen hebben geen betaaltermijn nodig
        "betaalddatum": "",
        "contract_referentie": origineel.get("contract_referentie", ""),
        "gebruiker": session.get("gebruikersnaam", ""),
        "aangemaakt": nu.strftime("%d-%m-%Y %H:%M"),
    }
    alle_facturen.append(creditnota)
    bewaar_facturen(alle_facturen)
    return redirect(url_for("factuur_detail", factuur_id=creditnota["id"]))


@app.route("/facturen/<factuur_id>")
def factuur_detail(factuur_id):
    """Detailweergave van één factuur — voor door de app zelf gegenereerde
    facturen (Peute/Inkoop/Verkoop/Export) toont dit de regels waaruit hij is
    opgebouwd (datum, materiaal, ton, prijs, bedrag per lading/transport) en
    het totaalbedrag onderaan. Voor handmatig toegevoegde facturen (geen
    regels) toont het gewoon de basisgegevens."""
    _guard = vereist_afdeling_of_403("facturen")
    if _guard: return _guard

    alle_facturen = laad_facturen()
    factuur = next((f for f in alle_facturen if f.get("id") == factuur_id), None)
    if not factuur:
        pagina = render_simple_page("Niet gevonden", "facturen", '<div class="page-title">Factuur niet gevonden</div><div class="lege-staat">Deze factuur bestaat niet (meer). <a href="/facturen">Terug naar Facturen</a></div>')
        return render_template_string(pagina), 404

    factuur["status"] = bepaal_factuur_status(factuur)
    regels = factuur.get("regels", [])
    bedragen = bereken_factuur_bedragen(factuur)
    klant = factuur.get("klant_gegevens") or {}
    valuta_weergave = regels[0].get("valuta", "EUR") if regels else "EUR"
    workflow_status = factuur.get("workflow_status", "definitief")  # oudere facturen (van vóór dit systeem) tellen als al-definitief
    heeft_creditnota = any(f.get("credit_van_factuur_id") == factuur_id for f in alle_facturen)

    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/facturen" style="color:var(--gray-400);text-decoration:none;">Facturen</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">{{ factuur.factuurnummer or factuur.referentie or factuur.id }}</span>
</div>
<div class="page-title">{{ factuur.bedrijf }} <span style="font-size:0.55em;font-weight:600;color:var(--gray-400);">{{ factuur.factuurnummer }}</span></div>

<div style="margin-bottom:16px;">
    {% if workflow_status == "concept" %}
    <span style="display:inline-block;font-size:11px;font-weight:700;padding:4px 12px;border-radius:5px;background:#fef3c7;color:#b45309;text-transform:uppercase;letter-spacing:0.04em;">Concept — nog niet definitief</span>
    {% else %}
    <span style="display:inline-block;font-size:11px;font-weight:700;padding:4px 12px;border-radius:5px;background:#f0fdf4;color:#16a34a;text-transform:uppercase;letter-spacing:0.04em;">Definitief{% if factuur.definitief_op %} · verzonden {{ factuur.definitief_op }}{% endif %}</span>
    {% endif %}
    {% if factuur.is_creditnota %}
    <span style="display:inline-block;font-size:11px;font-weight:700;padding:4px 12px;border-radius:5px;background:#fef2f2;color:#dc2626;text-transform:uppercase;letter-spacing:0.04em;margin-left:6px;">Creditfactuur — bij {{ factuur.credit_van_factuurnummer }}</span>
    {% endif %}
    {% if heeft_creditnota %}
    <span style="display:inline-block;font-size:11px;font-weight:700;padding:4px 12px;border-radius:5px;background:var(--gray-100);color:var(--gray-500);margin-left:6px;">Gecrediteerd</span>
    {% endif %}
</div>

<div style="display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap;">
    <div style="flex:1;min-width:140px;border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);padding:14px 4px;">
        <div style="font-size:1.3rem;font-weight:800;color:var(--gray-800);">{{ valuta_weergave }} {{ "{:,.2f}".format(bedragen.totaal).replace(",", "X").replace(".", ",").replace("X", ".") }}</div>
        <div style="font-size:0.75rem;color:var(--gray-400);">Totaal (incl. BTW)</div>
    </div>
    <div style="flex:1;min-width:140px;border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);padding:14px 4px;">
        <div style="font-size:1.3rem;font-weight:800;color:{{ '#16a34a' if factuur.status=='Betaald' else ('#dc2626' if factuur.status=='Te laat' else 'var(--gray-800)') }};">{{ factuur.status }}</div>
        <div style="font-size:0.75rem;color:var(--gray-400);">Status</div>
    </div>
    <div style="flex:1;min-width:140px;border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);padding:14px 4px;">
        <div style="font-size:1.3rem;font-weight:800;color:var(--gray-800);">{{ factuur.vervaldatum or '—' }}</div>
        <div style="font-size:0.75rem;color:var(--gray-400);">Uiterste betaaldatum</div>
    </div>
    {% if regels %}
    <div style="flex:1;min-width:140px;border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);padding:14px 4px;">
        <div style="font-size:1.3rem;font-weight:800;color:var(--gray-800);">{{ regels|length }}</div>
        <div style="font-size:0.75rem;color:var(--gray-400);">{{ 'Ladingen' if factuur.type == 'peute' else 'Regels' }}</div>
    </div>
    {% endif %}
</div>

<div style="display:flex;gap:24px;margin-bottom:24px;flex-wrap:wrap;">
    <div style="flex:1;min-width:220px;font-size:12.5px;color:var(--gray-600);">
        <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;">Factuurgegevens</div>
        <b>Factuurnummer:</b> {{ factuur.factuurnummer or '—' }}<br>
        <b>Factuurdatum:</b> {{ factuur.factuurdatum or '—' }}<br>
        {% if factuur.leverdatum and factuur.leverdatum != factuur.factuurdatum %}<b>Leverdatum:</b> {{ factuur.leverdatum }}<br>{% endif %}
        {% if factuur.incoterm %}<b>Incoterm:</b> {{ factuur.incoterm }}<br>{% endif %}
        <b>Referentie:</b> {{ factuur.referentie or '—' }}
        {% if factuur.omschrijving %} · {{ factuur.omschrijving }}{% endif %}
        {% if factuur.contract_referentie %} · <a href="/handelsorders?zoekterm={{ factuur.contract_referentie|urlencode }}" style="color:var(--brand-600);text-decoration:none;">↳ {{ factuur.contract_referentie }}</a>{% endif %}<br>
        <b>Aangemaakt door:</b> {{ factuur.gebruiker or '—' }} op {{ factuur.aangemaakt or '—' }}
    </div>
    {% if klant.adres %}
    <div style="flex:1;min-width:220px;font-size:12.5px;color:var(--gray-600);">
        <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:6px;">Klantgegevens (op moment van facturering)</div>
        <b>{{ factuur.bedrijf }}</b><br>
        {{ klant.adres }}<br>
        {{ klant.postcode }} {{ klant.stad }}<br>
        {{ klant.land }}<br>
        {% if klant.kvk_nummer %}KvK: {{ klant.kvk_nummer }}<br>{% endif %}
        {% if klant.vat_nummer %}BTW-nummer: {{ klant.vat_nummer }}{% endif %}
    </div>
    {% endif %}
</div>

{% if regels %}
<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Regels</div>
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);margin-bottom:12px;">
    <div style="display:flex;align-items:center;padding:9px 4px;background:var(--gray-50);border-bottom:1px solid var(--gray-200);font-size:10px;text-transform:uppercase;letter-spacing:0.06em;color:#7d8792;">
        <span style="width:90px;">Datum</span>
        <span style="width:130px;">Referentie</span>
        <span style="flex:1;">Materiaal</span>
        <span style="width:130px;">Contract</span>
        <span style="width:90px;text-align:right;">Ton</span>
        <span style="width:90px;text-align:right;">Prijs/ton</span>
        <span style="width:110px;text-align:right;">Bedrag</span>
    </div>
    {% for r in regels %}
    <div style="display:flex;align-items:center;padding:9px 4px;border-bottom:1px solid var(--gray-100);font-size:12.5px;">
        <span style="width:90px;color:var(--gray-500);">{{ r.datum or '—' }}</span>
        <span style="width:130px;font-family:var(--font-mono);color:var(--gray-500);">{{ r.ordernummer or r.referentienummer or '—' }}</span>
        <span style="flex:1;color:var(--gray-600);">{{ r.materiaal }}{% if r.kwaliteit %} — {{ r.kwaliteit }}{% endif %}</span>
        <span style="width:130px;color:var(--gray-500);">{{ r.contractnummer or '—' }}</span>
        <span style="width:90px;text-align:right;font-family:var(--font-mono);color:var(--gray-700);">{{ r.ton }} t</span>
        <span style="width:90px;text-align:right;color:var(--gray-500);">{{ r.prijs_per_ton }} {{ r.valuta }}</span>
        <span style="width:110px;text-align:right;font-family:var(--font-mono);font-weight:700;color:var(--gray-800);">{{ "%.2f"|format(r.bedrag) }} {{ r.valuta }}</span>
    </div>
    {% endfor %}
</div>
{% endif %}

<div style="max-width:340px;margin-left:auto;margin-bottom:20px;font-size:12.5px;">
    <div style="display:flex;justify-content:space-between;padding:6px 4px;color:var(--gray-600);">
        <span>Subtotaal (excl. BTW)</span><span style="font-family:var(--font-mono);">{{ valuta_weergave }} {{ "%.2f"|format(bedragen.subtotaal) }}</span>
    </div>
    {% if bedragen.btw_verlegd %}
    <div style="display:flex;justify-content:space-between;padding:6px 4px;color:var(--gray-600);">
        <span>BTW verlegd</span><span style="font-family:var(--font-mono);">{{ valuta_weergave }} 0.00</span>
    </div>
    {% else %}
    <div style="display:flex;justify-content:space-between;padding:6px 4px;color:var(--gray-600);">
        <span>BTW ({{ bedragen.btw_percentage|round|int }}%)</span><span style="font-family:var(--font-mono);">{{ valuta_weergave }} {{ "%.2f"|format(bedragen.btw_bedrag) }}</span>
    </div>
    {% endif %}
    <div style="display:flex;justify-content:space-between;padding:8px 4px;border-top:1px solid var(--gray-800);font-weight:800;color:var(--gray-800);">
        <span>Totaal (incl. BTW)</span><span style="font-family:var(--font-mono);">{{ valuta_weergave }} {{ "%.2f"|format(bedragen.totaal) }}</span>
    </div>
    {% if bedragen.btw_verlegd %}
    <div style="font-size:11px;color:var(--gray-400);margin-top:6px;">{{ bedragen.btw_verlegd_uitleg }}</div>
    {% endif %}
</div>

<div style="display:flex;gap:8px;flex-wrap:wrap;">
    <a href="/facturen/{{ factuur.id }}/pdf" target="_blank" style="font-size:12.5px;font-weight:700;padding:8px 16px;background:var(--brand-600);color:#fff;border-radius:6px;text-decoration:none;">PDF downloaden</a>

    {% if workflow_status == "concept" %}
    <form method="POST" action="/facturen/{{ factuur.id }}/definitief-maken" style="margin:0;" onsubmit="return confirm('Definitief maken kent het echte factuurnummer toe en kan niet ongedaan worden gemaakt. Dit is ook het moment waarop de factuur naar {{ factuur.bedrijf }} wordt verstuurd. Doorgaan?');">
        <button type="submit" style="font-size:12.5px;font-weight:700;padding:8px 16px;background:#16a34a;color:#fff;border:none;border-radius:6px;cursor:pointer;">✓ Akkoord — definitief maken &amp; versturen</button>
    </form>
    <form method="POST" action="/facturen/{{ factuur.id }}/verwijder-concept" style="margin:0;" onsubmit="return confirm('Dit concept verwijderen? De onderliggende ladingen/transporten worden weer vrijgegeven voor facturering.');">
        <button type="submit" style="font-size:12.5px;font-weight:600;padding:8px 16px;background:none;border:1px solid var(--gray-200);border-radius:6px;color:#dc2626;cursor:pointer;">Concept verwijderen</button>
    </form>
    {% else %}
        {% if factuur.status != "Betaald" %}
        <form method="POST" action="/facturen" style="margin:0;">
            <input type="hidden" name="actie" value="markeer_betaald">
            <input type="hidden" name="factuur_id" value="{{ factuur.id }}">
            <button type="submit" style="font-size:12.5px;font-weight:700;padding:8px 16px;background:#f0fdf4;color:#16a34a;border:none;border-radius:6px;cursor:pointer;">✓ Markeer betaald</button>
        </form>
        {% endif %}
        {% if factuur.verstuurd_naar_boekhouding_op %}
        <span style="font-size:12.5px;color:var(--gray-400);padding:8px 4px;">Naar boekhouding: {{ factuur.verstuurd_naar_boekhouding_op }}</span>
        {% else %}
        <form method="POST" action="/facturen/{{ factuur.id }}/boekhouding" style="margin:0;">
            <button type="submit" style="font-size:12.5px;font-weight:600;padding:8px 16px;background:none;border:1px solid var(--gray-200);border-radius:6px;color:var(--gray-600);cursor:pointer;">Naar boekhoudpakket versturen</button>
        </form>
        {% endif %}
        {% if not factuur.is_creditnota and not heeft_creditnota %}
        <form method="POST" action="/facturen/{{ factuur.id }}/crediteren" style="margin:0;" onsubmit="return confirm('Een creditfactuur aanmaken voor {{ factuur.factuurnummer }}? Deze moet zelf ook weer akkoord/definitief gemaakt worden.');">
            <button type="submit" style="font-size:12.5px;font-weight:600;padding:8px 16px;background:none;border:1px solid var(--gray-200);border-radius:6px;color:#dc2626;cursor:pointer;">Crediteren</button>
        </form>
        {% endif %}
    {% endif %}
    <a href="/bedrijf/{{ factuur.bedrijf|urlencode }}" style="font-size:12.5px;font-weight:600;padding:8px 16px;border:1px solid var(--gray-200);border-radius:6px;color:var(--gray-600);text-decoration:none;">Naar bedrijfsprofiel</a>
</div>
    """
    pagina = render_simple_page(factuur.get("factuurnummer") or factuur.get("referentie") or "Factuur", "facturen", inhoud)
    return render_template_string(pagina, factuur=factuur, regels=regels, bedragen=bedragen, klant=klant,
                                    valuta_weergave=valuta_weergave, workflow_status=workflow_status, heeft_creditnota=heeft_creditnota)

@app.route("/facturen/logistieke-orders", methods=["GET", "POST"])
def facturen_logistieke_orders():
    _guard = vereist_afdeling_of_403("logistieke_orders_finance")
    if _guard: return _guard

    if request.method == "POST":
        order_id = request.form.get("order_id", "")
        nieuwe_status = request.form.get("nieuwe_status", "")
        orders = laad_logistieke_orders()
        order = next((o for o in orders if o["id"] == order_id), None)
        if order and nieuwe_status in ("Gefactureerd", "Afgerond"):
            order["status"] = nieuwe_status
            bewaar_logistieke_orders(orders)
        return redirect(url_for("facturen_logistieke_orders"))

    alle_orders = laad_logistieke_orders()
    weegrecords = {r["id"]: r for r in laad_weegbrug()}
    documenten = laad_documenten()

    klaar_voor_finance = [o for o in alle_orders if o.get("status") == "Klaar voor Finance"]
    in_behandeling = [o for o in alle_orders if o.get("status") == "Gefactureerd"]
    financieel_afgerond = [o for o in alle_orders if o.get("status") == "Afgerond"]

    def _weegbon_link(order):
        weegrecord = weegrecords.get(order.get("gekoppeld_weegbrug_id", ""))
        return weegrecord["id"] if weegrecord and weegrecord.get("status") == "Compleet" else None

    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/facturen" style="color:var(--gray-400);text-decoration:none;">Facturen</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">Logistieke orders</span>
</div>
<div class="page-title">Logistieke orders — Finance-verwerking</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Orders die logistiek heeft vrijgegeven, met alle gegevens die Finance nodig heeft voor de (inkoop)factuur.</p>

<style>
.flo-sectie { border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); margin-bottom:18px; }
.flo-kop { padding:12px 16px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); font-size:12.5px; font-weight:700; color:var(--gray-700); display:flex; justify-content:space-between; }
.flo-rij { padding:10px 16px; border-bottom:1px solid var(--gray-100); font-size:12.5px; display:flex; align-items:center; gap:16px; }
</style>

<div class="flo-sectie">
    <div class="flo-kop"><span>Klaar voor Finance</span><span>{{ klaar_voor_finance|length }}</span></div>
    {% for o in klaar_voor_finance %}
    <div class="flo-rij">
        <span style="width:120px;font-family:var(--font-mono);color:var(--gray-500);"><a href="/logistiek/orders/{{ o.id }}" style="color:var(--brand-600);text-decoration:none;font-weight:600;">{{ o.ordernummer }}</a></span>
        <span style="flex:1;color:var(--gray-700);">{{ o.leverancier or '—' }}</span>
        <span style="width:100px;color:var(--gray-600);">{{ o.materiaal or '—' }}</span>
        <span style="width:90px;text-align:right;font-family:var(--font-mono);color:var(--gray-600);">{{ o.werkelijke_hoeveelheid or '—' }}{% if o.werkelijke_hoeveelheid %} ton{% endif %}</span>
        <span style="width:110px;">
            {% set wb_id = weegbon_links[o.id] %}
            {% if wb_id %}<a href="/weegbrug/weegbon/{{ wb_id }}" target="_blank" style="color:var(--brand-600);text-decoration:none;font-size:11.5px;font-weight:600;">Weegbon →</a>{% else %}<span style="color:var(--gray-300);font-size:11.5px;">geen weegbon</span>{% endif %}
        </span>
        <form method="POST" style="margin:0;">
            <input type="hidden" name="order_id" value="{{ o.id }}">
            <input type="hidden" name="nieuwe_status" value="Gefactureerd">
            <button type="submit" style="font-size:11px;padding:4px 10px;background:var(--brand-600);color:#fff;border:none;border-radius:5px;cursor:pointer;font-weight:600;">In behandeling nemen</button>
        </form>
    </div>
    {% else %}
    <div class="flo-rij" style="color:var(--gray-300);">Niets klaar voor verwerking.</div>
    {% endfor %}
</div>

<div class="flo-sectie">
    <div class="flo-kop"><span>In behandeling bij Finance</span><span>{{ in_behandeling|length }}</span></div>
    {% for o in in_behandeling %}
    <div class="flo-rij">
        <span style="width:120px;font-family:var(--font-mono);color:var(--gray-500);"><a href="/logistiek/orders/{{ o.id }}" style="color:var(--brand-600);text-decoration:none;font-weight:600;">{{ o.ordernummer }}</a></span>
        <span style="flex:1;color:var(--gray-700);">{{ o.leverancier or '—' }}</span>
        <span style="width:90px;text-align:right;font-family:var(--font-mono);color:var(--gray-600);">{{ o.werkelijke_hoeveelheid or '—' }}{% if o.werkelijke_hoeveelheid %} ton{% endif %}</span>
        <form method="POST" style="margin:0;margin-left:auto;">
            <input type="hidden" name="order_id" value="{{ o.id }}">
            <input type="hidden" name="nieuwe_status" value="Afgerond">
            <button type="submit" style="font-size:11px;padding:4px 10px;background:var(--gray-700);color:#fff;border:none;border-radius:5px;cursor:pointer;font-weight:600;">Markeer financieel afgerond</button>
        </form>
    </div>
    {% else %}
    <div class="flo-rij" style="color:var(--gray-300);">Niets in behandeling.</div>
    {% endfor %}
</div>

<div class="flo-sectie">
    <div class="flo-kop" style="color:var(--gray-400);"><span>Financieel afgerond</span><span>{{ financieel_afgerond|length }}</span></div>
    {% for o in financieel_afgerond[:10] %}
    <div class="flo-rij" style="color:var(--gray-500);">
        <span style="width:120px;font-family:var(--font-mono);"><a href="/logistiek/orders/{{ o.id }}" style="color:var(--gray-500);text-decoration:none;">{{ o.ordernummer }}</a></span>
        <span style="flex:1;">{{ o.leverancier or '—' }}</span>
        <span style="color:var(--gray-400);">{{ o.werkelijke_hoeveelheid or '—' }}{% if o.werkelijke_hoeveelheid %} ton{% endif %}</span>
    </div>
    {% else %}
    <div class="flo-rij" style="color:var(--gray-300);">Nog niets afgerond.</div>
    {% endfor %}
</div>
    """
    pagina = render_simple_page("Logistieke orders", "facturen", inhoud)
    weegbon_links = {o["id"]: _weegbon_link(o) for o in alle_orders}
    return render_template_string(pagina, klaar_voor_finance=klaar_voor_finance, in_behandeling=in_behandeling,
                                    financieel_afgerond=financieel_afgerond, weegbon_links=weegbon_links)



import string

def genereer_wachtwoord():
    tekens = string.ascii_letters + string.digits
    return "".join(secrets.choice(tekens) for _ in range(10))

def _bereken_contractvergelijking_financieel():
    """Herbruikbaar voor zowel de Financiële Inzichten-pagina als de CSV-export
    ervan. Vervangt het oude, losse contracten.json/shipments.json-systeem door
    alle Definitieve Handelsorders (inkoop én verkoop), met geleverd/uitgeleverd
    volume via logistieke_orders (vrachtwagen) en transport_planning (schip) —
    zelfde principe als Contractvoortgang bij Commerciële Inzichten."""
    def _geleverd_op_contract(contractnummer):
        _via_orders = sum(
            parse_ton_intern(o.get("werkelijke_hoeveelheid",""))
            for o in laad_logistieke_orders()
            if o.get("contract_referentie") == contractnummer and o.get("status") in ("Weegbon compleet", "Afhandeling", "Klaar voor Finance", "Gefactureerd", "Afgerond")
        )
        _via_transport = sum(
            parse_hoeveelheid_getal(t.get("hoeveelheid",""))
            for t in laad_transport_planning()
            if t.get("contract_referentie") == contractnummer and t.get("status") != "Geannuleerd"
        )
        return round(_via_orders + _via_transport, 3)

    contract_vergelijking = []
    for h in laad_handelsorders():
        if h.get("status") != "Definitief":
            continue
        try:
            contract_vol = float(str(h.get("hoeveelheid_mt","0")).replace(",",""))
        except (ValueError, TypeError):
            contract_vol = 0.0
        werkelijk_vol = _geleverd_op_contract(h["contractnummer"])
        contract_vergelijking.append({
            "referentie": h.get("contractnummer",""), "tegenpartij": h.get("tegenpartij_naam",""), "materiaal": h.get("materiaal",""),
            "order_type": "Inkoop" if h.get("order_type") == "inkoop" else "Verkoop",
            "contract_volume": round(contract_vol,1), "werkelijk_volume": round(werkelijk_vol,1),
            "verschil": round(werkelijk_vol - contract_vol, 1),
        })
    return contract_vergelijking

@app.route("/inzichten/financieel/export/contractvergelijking")
def export_contractvergelijking_csv():
    """CSV-export van Contractvolume vs. werkelijk volume op Financiële Inzichten."""
    _guard = vereist_afdeling_of_403("inzichten_financieel")
    if _guard: return _guard

    contract_vergelijking = _bereken_contractvergelijking_financieel()
    output = io.StringIO()
    schrijver = csv.writer(output, delimiter=";")
    schrijver.writerow(["Contractnummer", "Type", "Tegenpartij", "Materiaal", "Contractvolume (MT)", "Werkelijk volume (MT)", "Verschil (MT)"])
    for c in contract_vergelijking:
        schrijver.writerow([c["referentie"], c["order_type"], c["tegenpartij"], c["materiaal"], c["contract_volume"], c["werkelijk_volume"], c["verschil"]])
    return Response(output.getvalue(), mimetype="text/csv",
                     headers={"Content-Disposition": "attachment; filename=contractvergelijking.csv"})

@app.route("/inzichten/financieel")
def financiele_inzichten():
    """Financiële Inzichten — alleen met echt berekenbare data. Bewust NIET gebouwd:
    'Claims' en 'Credit notes' (geen datamodel hiervoor aanwezig), en 'Winst komende
    30 dagen' (zelfde marge-datagat als bij Commerciële Inzichten — geen gekoppelde
    inkoopprijs). 'Contractvolume vs. werkelijke waarde' toont bewust volume, geen
    euro's — dit is een volume-controle (klopt de levering met het contract), geen
    winst/margecijfer; die horen bij Commerciële Inzichten."""
    _guard = vereist_afdeling_of_403("inzichten_financieel")
    if _guard: return _guard

    alle_facturen = laad_facturen()
    for f in alle_facturen:
        f["status"] = bepaal_factuur_status(f)

    def _bedrag_getal(f):
        try:
            return float(str(f.get("bedrag", "0")).replace(",", "."))
        except (ValueError, TypeError):
            return 0.0

    openstaande_facturen = [f for f in alle_facturen if f.get("status") != "Betaald"]
    te_laat_facturen = [f for f in alle_facturen if f.get("status") == "Te laat"]
    totaal_openstaand = sum(_bedrag_getal(f) for f in openstaande_facturen)
    totaal_te_laat = sum(_bedrag_getal(f) for f in te_laat_facturen)

    # --- Gemiddelde betalingstermijn: (betaalddatum - factuurdatum), alleen betaalde facturen met beide data ---
    betalingstermijnen = []
    for f in alle_facturen:
        if f.get("betaalddatum") and f.get("factuurdatum"):
            try:
                fd = datetime.date.fromisoformat(f["factuurdatum"])
                bd = datetime.date.fromisoformat(f["betaalddatum"])
                betalingstermijnen.append((bd - fd).days)
            except (ValueError, TypeError):
                pass
    gem_betalingstermijn = round(sum(betalingstermijnen) / len(betalingstermijnen), 1) if betalingstermijnen else None

    # --- Verwachte cashflow: openstaande facturen geprojecteerd op vervaldatum, komende 4 weken ---
    _vandaag = datetime.date.today()
    cashflow_weken = []
    for i in range(4):
        week_start = _vandaag + datetime.timedelta(days=i*7)
        week_eind = week_start + datetime.timedelta(days=6)
        bedrag_week = sum(_bedrag_getal(f) for f in openstaande_facturen if f.get("vervaldatum","") and week_start.isoformat() <= f["vervaldatum"] <= week_eind.isoformat())
        cashflow_weken.append({"label": f"{week_start.strftime('%d-%m')} t/m {week_eind.strftime('%d-%m')}", "bedrag": round(bedrag_week, 2)})
    max_cashflow_week = max([w["bedrag"] for w in cashflow_weken], default=1) or 1

    # --- Nog te factureren orders: logistieke orders 'Klaar voor Finance', nog niet Gefactureerd ---
    alle_logistieke_orders = laad_logistieke_orders()
    nog_te_factureren = [o for o in alle_logistieke_orders if o.get("status") == "Klaar voor Finance"]

    # --- Contractvolume vs. werkelijk geleverd volume (LET OP: volume, geen
    # waarde — zie docstring) — herbruikt dezelfde functie als de CSV-export,
    # zodat scherm en export nooit uit de pas lopen. ---
    contract_vergelijking = _bereken_contractvergelijking_financieel()

    inhoud = """
<div class="page-title">Financiële Inzichten</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Rapportages voor Finance — facturen, cashflow, nog te factureren.</p>

<style>
.fi-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:14px; margin-bottom:24px; }
.fi-kaart { background:transparent; border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); padding:16px 4px; }
.fi-getal { font-size:1.5rem; font-weight:800; color:var(--gray-800); }
.fi-label { font-size:0.72rem; color:var(--gray-400); text-transform:uppercase; letter-spacing:0.6px; margin-top:4px; font-weight:600; }
.fi-sectie { border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); margin-bottom:24px; }
.fi-kop { padding:12px 16px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); font-size:12.5px; font-weight:700; color:var(--gray-700); }
.fi-rij { display:flex; align-items:center; padding:9px 16px; border-bottom:1px solid var(--gray-100); font-size:12.5px; }
</style>

<div class="fi-grid">
    <div class="fi-kaart"><div class="fi-getal">{{ openstaande_facturen|length }}</div><div class="fi-label">Openstaande facturen</div></div>
    <div class="fi-kaart" style="{% if te_laat_facturen %}border-color:#fecaca;{% endif %}"><div class="fi-getal" style="{% if te_laat_facturen %}color:#dc2626;{% endif %}">{{ te_laat_facturen|length }}</div><div class="fi-label">Overdue (te laat)</div></div>
    <div class="fi-kaart"><div class="fi-getal">€{{ "{:,.0f}".format(totaal_openstaand).replace(",", ".") }}</div><div class="fi-label">Totaal openstaand</div></div>
    <div class="fi-kaart"><div class="fi-getal">{% if gem_betalingstermijn %}{{ gem_betalingstermijn }}{% else %}—{% endif %}</div><div class="fi-label">Gem. betalingstermijn (dagen)</div></div>
    <div class="fi-kaart"><div class="fi-getal">{{ nog_te_factureren|length }}</div><div class="fi-label">Nog te factureren orders</div></div>
</div>

<div class="fi-sectie">
    <div class="fi-kop">Verwachte cashflow (komende 4 weken, o.b.v. vervaldatum openstaande facturen)</div>
    {% for w in cashflow_weken %}
    <div class="fi-rij">
        <span style="width:160px;color:var(--gray-500);">{{ w.label }}</span>
        <div style="flex:1;background:var(--gray-100);border-radius:4px;height:16px;overflow:hidden;margin-right:10px;">
            <div style="background:var(--brand-600);height:100%;width:{{ (w.bedrag/max_cashflow_week*100)|round(1) }}%;"></div>
        </div>
        <span style="width:100px;text-align:right;font-family:var(--font-mono);color:var(--gray-700);">€{{ "{:,.0f}".format(w.bedrag).replace(",", ".") }}</span>
    </div>
    {% endfor %}
</div>

<div class="fi-sectie">
    <div class="fi-kop">Nog te factureren orders</div>
    {% for o in nog_te_factureren %}
    <div class="fi-rij"><a href="/logistiek/orders/{{ o.id }}" style="flex:1;color:var(--brand-600);text-decoration:none;font-weight:600;">{{ o.ordernummer }}</a><span style="color:var(--gray-500);">{{ o.leverancier or '—' }}</span><span style="width:100px;text-align:right;color:var(--gray-600);">{{ o.werkelijke_hoeveelheid or '—' }}{% if o.werkelijke_hoeveelheid %} ton{% endif %}</span></div>
    {% else %}
    <div class="fi-rij" style="color:var(--gray-300);">Niets openstaand.</div>
    {% endfor %}
</div>

<div class="fi-sectie">
    <div class="fi-kop" style="display:flex;justify-content:space-between;align-items:center;">
        <span>Contractvolume vs. werkelijk geleverd volume <span style="font-weight:400;color:var(--gray-400);">(volume, niet gekoppeld aan winst/marge)</span></span>
        <a href="/inzichten/financieel/export/contractvergelijking" style="font-size:11px;font-weight:600;color:var(--brand-600);text-decoration:none;">↓ CSV</a>
    </div>
    {% if contract_vergelijking %}
    <div style="height:200px;margin:10px 0;">
        <canvas id="contractChart"></canvas>
    </div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
    <script>
    (function() {
        var labels = {{ contract_vergelijking[:15]|map(attribute='referentie')|list|tojson }};
        var contractData = {{ contract_vergelijking[:15]|map(attribute='contract_volume')|list|tojson }};
        var werkelijkData = {{ contract_vergelijking[:15]|map(attribute='werkelijk_volume')|list|tojson }};
        var ctx = document.getElementById('contractChart');
        if (ctx && window.Chart) {
            new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [
                        { label: 'Contract (t)', data: contractData, backgroundColor: '#94a3b8' },
                        { label: 'Werkelijk (t)', data: werkelijkData, backgroundColor: '#0d5c62' }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: true, labels: { font: { size: 10.5 } } } },
                    scales: {
                        y: { beginAtZero: true, ticks: { font: { size: 10.5 } } },
                        x: { ticks: { font: { size: 9.5 } } }
                    }
                }
            });
        }
    })();
    </script>
    {% if contract_vergelijking|length > 15 %}<div style="font-size:10.5px;color:var(--gray-300);margin-bottom:6px;">Grafiek toont de eerste 15 van {{ contract_vergelijking|length }} — de volledige lijst staat eronder en in de export.</div>{% endif %}
    {% endif %}
    {% for c in contract_vergelijking %}
    <div class="fi-rij">
        <span style="flex:1;color:var(--gray-700);">{{ c.referentie }} — {{ c.tegenpartij }} ({{ c.materiaal }}, {{ c.order_type }})</span>
        <span style="width:110px;text-align:right;color:var(--gray-500);">Contract: {{ c.contract_volume }}t</span>
        <span style="width:110px;text-align:right;color:var(--gray-500);">Werkelijk: {{ c.werkelijk_volume }}t</span>
        <span style="width:100px;text-align:right;font-weight:700;color:{{ '#16a34a' if c.verschil >= 0 else '#dc2626' }};">{{ '+' if c.verschil >= 0 else '' }}{{ c.verschil }}t</span>
    </div>
    {% else %}
    <div class="fi-rij" style="color:var(--gray-300);">Geen contracten geregistreerd.</div>
    {% endfor %}
</div>
    """
    pagina = render_simple_page("Financiële Inzichten", "inzichten_financieel", inhoud)
    return render_template_string(pagina, openstaande_facturen=openstaande_facturen, te_laat_facturen=te_laat_facturen,
                                    totaal_openstaand=totaal_openstaand, gem_betalingstermijn=gem_betalingstermijn,
                                    cashflow_weken=cashflow_weken, max_cashflow_week=max_cashflow_week,
                                    nog_te_factureren=nog_te_factureren, contract_vergelijking=contract_vergelijking)


@app.route("/organisatie-beheer", methods=["GET", "POST"])
def organisatie_beheer():
    """Beheerpagina voor de organisatiestructuur: Afdelingen (Papier, Plastic,
    Backoffice, ...), elk met een lijst Teams (bv. Papier -> UK, Spanje, Italie,
    Duitsland). Dit is puur organisatorisch (groepering/filtering, en het
    'team'-veld van een gebruiker) — een ANDER concept dan de vaste toegangsrol
    (accountmanager/backoffice/logistiek/weegbrug/finance), die bepaalt welke
    pagina's iemand mag zien en apart blijft bij het aanmaken van een gebruiker."""
    if not is_huidige_gebruiker_admin():
        pagina = render_simple_page("Geen toegang", "instellingen", '<div class="page-title">Geen toegang</div><div class="lege-staat">Alleen admins kunnen de organisatiestructuur beheren.</div>')
        return render_template_string(pagina), 403

    if request.method == "POST":
        structuur = laad_organisatiestructuur()
        actie = request.form.get("actie", "")
        if actie == "afdeling_toevoegen":
            naam = request.form.get("afdeling_naam", "").strip()
            if naam and naam not in structuur:
                structuur[naam] = []
                bewaar_organisatiestructuur(structuur)
        elif actie == "afdeling_verwijderen":
            naam = request.form.get("afdeling_naam", "").strip()
            if naam in structuur:
                del structuur[naam]
                bewaar_organisatiestructuur(structuur)
        elif actie == "team_toevoegen":
            afdeling_naam = request.form.get("afdeling_naam", "").strip()
            team_naam = request.form.get("team_naam", "").strip()
            if afdeling_naam in structuur and team_naam and team_naam not in structuur[afdeling_naam]:
                structuur[afdeling_naam].append(team_naam)
                bewaar_organisatiestructuur(structuur)
        elif actie == "team_verwijderen":
            afdeling_naam = request.form.get("afdeling_naam", "").strip()
            team_naam = request.form.get("team_naam", "").strip()
            if afdeling_naam in structuur and team_naam in structuur[afdeling_naam]:
                structuur[afdeling_naam].remove(team_naam)
                bewaar_organisatiestructuur(structuur)
        elif actie == "lid_toevoegen_aan_team":
            afdeling_naam = request.form.get("afdeling_naam", "").strip()
            team_naam = request.form.get("team_naam", "").strip()
            gebruikersnaam_lid = request.form.get("gebruikersnaam_lid", "").strip()
            users = laad_users()
            if gebruikersnaam_lid in users and afdeling_naam in structuur and team_naam in structuur[afdeling_naam]:
                users[gebruikersnaam_lid]["org_afdeling"] = afdeling_naam
                users[gebruikersnaam_lid]["team"] = team_naam
                bewaar_users(users)
        elif actie == "lid_verwijderen_uit_team":
            gebruikersnaam_lid = request.form.get("gebruikersnaam_lid", "").strip()
            users = laad_users()
            if gebruikersnaam_lid in users:
                users[gebruikersnaam_lid]["org_afdeling"] = ""
                users[gebruikersnaam_lid]["team"] = ""
                bewaar_users(users)
        return redirect(url_for("organisatie_beheer"))

    structuur = laad_organisatiestructuur()
    alle_users = laad_users()
    # Per afdeling+team: welke bestaande gebruikers zitten daar al, en welke
    # gebruikers zijn nog niet aan een team gekoppeld (bruikbaar voor de
    # keuzelijst "toevoegen" — iemand kan maar in één team tegelijk zitten).
    leden_per_team = {}
    for gebruikersnaam_u, info_u in alle_users.items():
        sleutel = (info_u.get("org_afdeling",""), info_u.get("team",""))
        if sleutel[0] and sleutel[1]:
            leden_per_team.setdefault(sleutel, []).append(gebruikersnaam_u)

    inhoud = """
<div class="page-title">Afdelingen & Teams</div>
<a href="/gebruikers-beheer" style="display:inline-block;margin-bottom:16px;font-size:12.5px;font-weight:600;color:var(--brand-600);text-decoration:none;">← Gebruikers beheren</a>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Organisatorische indeling — wie hoort bij welk team. Los van de toegangsrol (die regel je bij Gebruikers beheren).</p>

<div style="max-width:520px;margin-bottom:24px;">
    <form method="POST" style="display:flex;gap:8px;">
        <input type="hidden" name="actie" value="afdeling_toevoegen">
        <input type="text" name="afdeling_naam" placeholder="Nieuwe afdeling (bv. Papier, Plastic, Backoffice)" required style="flex:1;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
        <button type="submit" style="padding:8px 16px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">+ Afdeling</button>
    </form>
</div>

{% for afdeling_naam, teams in structuur.items() %}
<div style="border:none;border-top:2px solid var(--gray-800);padding-top:10px;margin-bottom:24px;max-width:600px;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
        <div style="font-weight:800;color:var(--gray-800);font-size:14px;">{{ afdeling_naam }}</div>
        <form method="POST" onsubmit="return confirm('Afdeling {{ afdeling_naam }} verwijderen? Bestaande gebruikers behouden hun huidige team-waarde, maar die is dan niet meer aan een afdeling gekoppeld.');" style="margin:0;">
            <input type="hidden" name="actie" value="afdeling_verwijderen">
            <input type="hidden" name="afdeling_naam" value="{{ afdeling_naam }}">
            <button type="submit" style="background:none;border:none;color:var(--gray-300);cursor:pointer;font-size:12px;">Verwijderen</button>
        </form>
    </div>
    {% for team_naam in teams %}
    <div style="padding:8px 0;border-bottom:1px solid var(--gray-100);">
        <div style="display:flex;align-items:center;font-size:12.5px;margin-bottom:6px;">
            <span style="flex:1;font-weight:700;color:var(--gray-700);">{{ team_naam }}</span>
            <form method="POST" style="margin:0;">
                <input type="hidden" name="actie" value="team_verwijderen">
                <input type="hidden" name="afdeling_naam" value="{{ afdeling_naam }}">
                <input type="hidden" name="team_naam" value="{{ team_naam }}">
                <button type="submit" style="background:none;border:none;color:var(--gray-300);cursor:pointer;font-size:11px;">✕ team verwijderen</button>
            </form>
        </div>
        {% for lid in leden_per_team.get((afdeling_naam, team_naam), []) %}
        <div style="display:flex;align-items:center;padding:3px 0 3px 10px;font-size:12px;color:var(--gray-600);">
            <span style="flex:1;">{{ lid }}</span>
            <form method="POST" style="margin:0;">
                <input type="hidden" name="actie" value="lid_verwijderen_uit_team">
                <input type="hidden" name="gebruikersnaam_lid" value="{{ lid }}">
                <button type="submit" style="background:none;border:none;color:var(--gray-300);cursor:pointer;font-size:10.5px;">verwijderen uit team</button>
            </form>
        </div>
        {% else %}
        <div style="padding:3px 0 3px 10px;font-size:11.5px;color:var(--gray-300);">Nog geen leden.</div>
        {% endfor %}
        <form method="POST" style="display:flex;gap:6px;margin-top:6px;padding-left:10px;">
            <input type="hidden" name="actie" value="lid_toevoegen_aan_team">
            <input type="hidden" name="afdeling_naam" value="{{ afdeling_naam }}">
            <input type="hidden" name="team_naam" value="{{ team_naam }}">
            <select name="gebruikersnaam_lid" required style="flex:1;padding:5px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:11.5px;font-family:inherit;">
                <option value="">Bestaande gebruiker kiezen...</option>
                {% for gnaam in alle_users.keys() %}<option value="{{ gnaam }}">{{ gnaam }}{% if alle_users[gnaam].get('team') %} (nu: {{ alle_users[gnaam].team }}){% endif %}</option>{% endfor %}
            </select>
            <button type="submit" style="padding:5px 12px;background:#fff;color:var(--gray-700);border:1px solid var(--gray-200);border-radius:6px;font-size:11px;font-weight:600;cursor:pointer;">+ Lid</button>
        </form>
    </div>
    {% else %}
    <div style="font-size:11.5px;color:var(--gray-300);padding:5px 0;">Nog geen teams.</div>
    {% endfor %}
    <form method="POST" style="display:flex;gap:6px;margin-top:8px;">
        <input type="hidden" name="actie" value="team_toevoegen">
        <input type="hidden" name="afdeling_naam" value="{{ afdeling_naam }}">
        <input type="text" name="team_naam" placeholder="Nieuw team (bv. UK, Spanje...)" style="flex:1;padding:6px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:12px;font-family:inherit;">
        <button type="submit" style="padding:6px 12px;background:#fff;color:var(--gray-700);border:1px solid var(--gray-200);border-radius:6px;font-size:11.5px;font-weight:600;cursor:pointer;">+ Team</button>
    </form>
</div>
{% else %}
<div class="lege-staat">Nog geen afdelingen. Begin hierboven met de eerste.</div>
{% endfor %}
    """
    pagina = render_simple_page("Afdelingen & Teams", "instellingen", inhoud)
    return render_template_string(pagina, structuur=structuur, alle_users=alle_users, leden_per_team=leden_per_team)

@app.route("/instellingen/layout", methods=["GET", "POST"])
def layout_instellingen():
    """Persoonlijke zijbalk-volgorde en -zichtbaarheid, per gebruiker. Bewust
    omhoog/omlaag-knoppen i.p.v. drag-and-drop: die werken altijd, ook zonder
    JavaScript, en zijn betrouwbaarder te testen."""
    gebruikersnaam = session.get("gebruikersnaam", "")
    alle_voorkeuren = laad_layout_voorkeuren()
    mijn_voorkeur = alle_voorkeuren.setdefault(gebruikersnaam, {})

    if request.method == "POST":
        actie = request.form.get("actie", "")
        _effectief_voor_post = effectieve_layout_voorkeur(gebruikersnaam)
        zichtbare_keys = [item[0] for item in ZIJBALK_ITEMS if mag_pagina_zien(item[0])]
        huidige_volgorde = _effectief_voor_post.get("sidebar_volgorde") or zichtbare_keys
        # Nieuwe/nog-niet-opgeslagen items altijd aan het einde toevoegen, zodat
        # de omhoog/omlaag-knoppen op een volledige, actuele lijst werken.
        for k in zichtbare_keys:
            if k not in huidige_volgorde:
                huidige_volgorde.append(k)
        huidige_volgorde = [k for k in huidige_volgorde if k in zichtbare_keys]
        verborgen = set(_effectief_voor_post.get("sidebar_verborgen", []))

        if actie == "omhoog":
            key = request.form.get("key", "")
            if key in huidige_volgorde:
                i = huidige_volgorde.index(key)
                if i > 0:
                    huidige_volgorde[i-1], huidige_volgorde[i] = huidige_volgorde[i], huidige_volgorde[i-1]
        elif actie == "omlaag":
            key = request.form.get("key", "")
            if key in huidige_volgorde:
                i = huidige_volgorde.index(key)
                if i < len(huidige_volgorde) - 1:
                    huidige_volgorde[i+1], huidige_volgorde[i] = huidige_volgorde[i], huidige_volgorde[i+1]
        elif actie == "toggle_zichtbaar":
            key = request.form.get("key", "")
            if key in verborgen:
                verborgen.discard(key)
            else:
                verborgen.add(key)
        elif actie == "standaard_herstellen":
            huidige_volgorde = []
            verborgen = set()

        mijn_voorkeur["sidebar_volgorde"] = huidige_volgorde
        mijn_voorkeur["sidebar_verborgen"] = list(verborgen)

        # Dashboard-widgets: zelfde principe, eigen sleutels binnen dezelfde voorkeur.
        widget_keys = list(DASHBOARD_WIDGET_LABELS.keys())
        widget_volgorde = mijn_voorkeur.get("dashboard_widget_volgorde") or widget_keys
        for k in widget_keys:
            if k not in widget_volgorde:
                widget_volgorde.append(k)
        widget_volgorde = [k for k in widget_volgorde if k in widget_keys]
        widget_verborgen = set(mijn_voorkeur.get("dashboard_widget_verborgen", []))

        if actie == "widget_omhoog":
            key = request.form.get("key", "")
            if key in widget_volgorde:
                i = widget_volgorde.index(key)
                if i > 0:
                    widget_volgorde[i-1], widget_volgorde[i] = widget_volgorde[i], widget_volgorde[i-1]
        elif actie == "widget_omlaag":
            key = request.form.get("key", "")
            if key in widget_volgorde:
                i = widget_volgorde.index(key)
                if i < len(widget_volgorde) - 1:
                    widget_volgorde[i+1], widget_volgorde[i] = widget_volgorde[i], widget_volgorde[i+1]
        elif actie == "widget_toggle_zichtbaar":
            key = request.form.get("key", "")
            if key in widget_verborgen:
                widget_verborgen.discard(key)
            else:
                widget_verborgen.add(key)
        elif actie == "widget_standaard_herstellen":
            widget_volgorde = []
            widget_verborgen = set()

        mijn_voorkeur["dashboard_widget_volgorde"] = widget_volgorde
        mijn_voorkeur["dashboard_widget_verborgen"] = list(widget_verborgen)
        alle_voorkeuren[gebruikersnaam] = mijn_voorkeur
        bewaar_layout_voorkeuren(alle_voorkeuren)
        return redirect(url_for("layout_instellingen"))

    _effectief_voor_weergave = effectieve_layout_voorkeur(gebruikersnaam)
    zichtbare_items = [item for item in ZIJBALK_ITEMS if mag_pagina_zien(item[0])]
    volgorde = _effectief_voor_weergave.get("sidebar_volgorde", [])
    zichtbare_items = _sorteer_op_voorkeur(zichtbare_items, volgorde)
    verborgen_set = set(_effectief_voor_weergave.get("sidebar_verborgen", []))

    widget_items = list(DASHBOARD_WIDGET_LABELS.items())
    widget_volgorde_getoond = mijn_voorkeur.get("dashboard_widget_volgorde", [])
    if widget_volgorde_getoond:
        _widget_volgorde_index = {s: i for i, s in enumerate(widget_volgorde_getoond)}
        widget_items = sorted(widget_items, key=lambda item: _widget_volgorde_index.get(item[0], len(widget_volgorde_getoond)))
    widget_verborgen_set = set(mijn_voorkeur.get("dashboard_widget_verborgen", []))

    inhoud = """
<div class="page-title">Mijn zijbalk</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Zet de volgorde die voor jou het handigst werkt, en verberg wat je niet gebruikt.</p>

<div style="border:none;border-top:1px solid var(--gray-200);max-width:420px;">
    {% for key, href, icoon, label in zichtbare_items %}
    <div style="display:flex;align-items:center;gap:8px;padding:8px 4px;border-bottom:1px solid var(--gray-100);font-size:13px;{% if key in verborgen_set %}opacity:0.4;{% endif %}">
        <span style="flex:1;color:var(--gray-700);">{{ label }}</span>
        <form method="POST" style="margin:0;display:inline;">
            <input type="hidden" name="actie" value="toggle_zichtbaar">
            <input type="hidden" name="key" value="{{ key }}">
            <button type="submit" style="background:none;border:none;color:var(--gray-400);cursor:pointer;font-size:11px;padding:2px 6px;" title="{{ 'Weer tonen' if key in verborgen_set else 'Verbergen' }}">{{ '👁' if key in verborgen_set else '—' }}</button>
        </form>
        <form method="POST" style="margin:0;display:inline;">
            <input type="hidden" name="actie" value="omhoog">
            <input type="hidden" name="key" value="{{ key }}">
            <button type="submit" style="background:none;border:none;color:var(--gray-400);cursor:pointer;font-size:13px;padding:2px 6px;" title="Omhoog">↑</button>
        </form>
        <form method="POST" style="margin:0;display:inline;">
            <input type="hidden" name="actie" value="omlaag">
            <input type="hidden" name="key" value="{{ key }}">
            <button type="submit" style="background:none;border:none;color:var(--gray-400);cursor:pointer;font-size:13px;padding:2px 6px;" title="Omlaag">↓</button>
        </form>
    </div>
    {% endfor %}
</div>
<form method="POST" style="margin-top:16px;">
    <input type="hidden" name="actie" value="standaard_herstellen">
    <button type="submit" style="padding:7px 14px;background:#fff;color:var(--gray-500);border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;cursor:pointer;">Standaardvolgorde herstellen</button>
</form>

<div class="page-title" style="margin-top:36px;font-size:1.1rem;">Mijn Dashboard</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Volgorde en zichtbaarheid van de blokken op je Dashboard (alleen van toepassing op het commerciële dashboard).</p>
<div style="border:none;border-top:1px solid var(--gray-200);max-width:420px;">
    {% for key, label in widget_items %}
    <div style="display:flex;align-items:center;gap:8px;padding:8px 4px;border-bottom:1px solid var(--gray-100);font-size:13px;{% if key in widget_verborgen_set %}opacity:0.4;{% endif %}">
        <span style="flex:1;color:var(--gray-700);">{{ label }}</span>
        <form method="POST" style="margin:0;display:inline;">
            <input type="hidden" name="actie" value="widget_toggle_zichtbaar">
            <input type="hidden" name="key" value="{{ key }}">
            <button type="submit" style="background:none;border:none;color:var(--gray-400);cursor:pointer;font-size:11px;padding:2px 6px;" title="{{ 'Weer tonen' if key in widget_verborgen_set else 'Verbergen' }}">{{ '👁' if key in widget_verborgen_set else '—' }}</button>
        </form>
        <form method="POST" style="margin:0;display:inline;">
            <input type="hidden" name="actie" value="widget_omhoog">
            <input type="hidden" name="key" value="{{ key }}">
            <button type="submit" style="background:none;border:none;color:var(--gray-400);cursor:pointer;font-size:13px;padding:2px 6px;" title="Omhoog">↑</button>
        </form>
        <form method="POST" style="margin:0;display:inline;">
            <input type="hidden" name="actie" value="widget_omlaag">
            <input type="hidden" name="key" value="{{ key }}">
            <button type="submit" style="background:none;border:none;color:var(--gray-400);cursor:pointer;font-size:13px;padding:2px 6px;" title="Omlaag">↓</button>
        </form>
    </div>
    {% endfor %}
</div>
<form method="POST" style="margin-top:16px;">
    <input type="hidden" name="actie" value="widget_standaard_herstellen">
    <button type="submit" style="padding:7px 14px;background:#fff;color:var(--gray-500);border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;cursor:pointer;">Standaardvolgorde herstellen</button>
</form>
    """
    pagina = render_simple_page("Mijn zijbalk", "instellingen", inhoud)
    return render_template_string(pagina, zichtbare_items=zichtbare_items, verborgen_set=verborgen_set,
                                    widget_items=widget_items, widget_verborgen_set=widget_verborgen_set)

@app.route("/gebruikers-beheer", methods=["GET", "POST"])
def gebruikers_beheer():
    if not is_huidige_gebruiker_admin():
        pagina = render_simple_page("Geen toegang", "instellingen", '<div class="page-title">Geen toegang</div><div class="lege-staat">Alleen admins kunnen gebruikers beheren. Vraag een admin om je rechten aan te passen.</div>')
        return render_template_string(pagina), 403

    bericht = None
    nieuw_wachtwoord = None
    if request.method == "POST":
        actie = request.form.get("actie", "toevoegen")
        if actie == "toevoegen":
            nieuwe_naam = request.form.get("gebruikersnaam", "").strip()
            team = request.form.get("team", "").strip()
            org_afdeling_nieuw = request.form.get("org_afdeling", "").strip()
            is_admin_nieuw = request.form.get("is_admin") == "on"
            afdeling_nieuw = request.form.get("afdeling", "")
            rol_nieuw = request.form.get("rol", "medewerker")
            users = laad_users()
            if not nieuwe_naam:
                bericht = "Gebruikersnaam is verplicht."
            elif nieuwe_naam in users:
                bericht = f"'{nieuwe_naam}' bestaat al."
            else:
                nieuw_wachtwoord = genereer_wachtwoord()
                users[nieuwe_naam] = {
                    "wachtwoord": generate_password_hash(nieuw_wachtwoord), "team": team,
                    "org_afdeling": org_afdeling_nieuw, "is_admin": is_admin_nieuw,
                    "afdeling": afdeling_nieuw if afdeling_nieuw in AFDELINGEN else "",
                    "rol": rol_nieuw if rol_nieuw in ROLLEN else "medewerker",
                }
                bewaar_users(users)
                bericht = f"'{nieuwe_naam}' toegevoegd!"
        elif actie == "verwijderen":
            te_verwijderen = request.form.get("gebruikersnaam", "")
            users = laad_users()
            if te_verwijderen == session.get("gebruikersnaam"):
                bericht = "Je kunt jezelf niet verwijderen."
            elif te_verwijderen in users:
                del users[te_verwijderen]
                bewaar_users(users)
                bericht = f"'{te_verwijderen}' verwijderd."
        elif actie == "toggle_admin":
            doelnaam = request.form.get("gebruikersnaam", "")
            users = laad_users()
            if doelnaam == session.get("gebruikersnaam"):
                bericht = "Je kunt je eigen adminrechten niet aanpassen."
            elif doelnaam in users:
                huidige = users[doelnaam].get("is_admin", True)
                users[doelnaam]["is_admin"] = not huidige
                bewaar_users(users)
                bericht = f"'{doelnaam}' is nu {'wel' if not huidige else 'geen'} admin."
        elif actie == "wijzig_afdeling_rol":
            doelnaam = request.form.get("gebruikersnaam", "")
            nieuwe_afdeling = request.form.get("afdeling", "")
            nieuwe_rol = request.form.get("rol", "")
            nieuwe_org_afdeling = request.form.get("org_afdeling", "")
            nieuw_team = request.form.get("team", "").strip()
            users = laad_users()
            if doelnaam in users:
                if nieuwe_afdeling in AFDELINGEN or nieuwe_afdeling == "":
                    users[doelnaam]["afdeling"] = nieuwe_afdeling
                if nieuwe_rol in ROLLEN:
                    users[doelnaam]["rol"] = nieuwe_rol
                users[doelnaam]["org_afdeling"] = nieuwe_org_afdeling
                users[doelnaam]["team"] = nieuw_team
                bewaar_users(users)
                bericht = f"Afdeling/rol van '{doelnaam}' bijgewerkt."

    users = laad_users()
    inhoud = """
    <div class="page-title">Gebruikers beheren</div>
    <a href="/organisatie-beheer" style="display:inline-block;margin-bottom:16px;font-size:12.5px;font-weight:600;color:var(--brand-600);text-decoration:none;">Afdelingen &amp; Teams beheren →</a>
    {% if bericht %}<div style="background:{{ '#f0fdf4' if nieuw_wachtwoord or 'verwijderd' in bericht or 'nu' in bericht else '#fef2f2' }};color:{{ '#16a34a' if nieuw_wachtwoord or 'verwijderd' in bericht or 'nu' in bericht else '#dc2626' }};padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:14px;">{{ bericht }}
        {% if nieuw_wachtwoord %}<br><b>Wachtwoord: <code style="background:#fff;padding:3px 8px;border-radius:4px;">{{ nieuw_wachtwoord }}</code></b><br><span style="font-size:12px;">Bewaar dit nu — dit wordt niet nogmaals getoond. Geef het handmatig door aan de gebruiker.</span>{% endif %}
    </div>{% endif %}

    <div class="info-kaart" style="max-width:420px;margin-bottom:20px;">
        <div class="dg-kaart-titel">Nieuwe gebruiker toevoegen</div>
        <form method="POST">
            <input type="hidden" name="actie" value="toevoegen">
            <input type="text" name="gebruikersnaam" placeholder="Gebruikersnaam (bv. leander)" required style="width:100%;padding:8px 10px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;margin-bottom:10px;box-sizing:border-box;font-family:inherit;">
            <select name="org_afdeling" id="org_afdeling_select" onchange="verversOrgTeams()" style="width:100%;padding:8px 10px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;margin-bottom:10px;box-sizing:border-box;font-family:inherit;">
                <option value="">Geen organisatie-afdeling</option>
                {% for a in organisatiestructuur.keys() %}<option value="{{ a }}">{{ a }}</option>{% endfor %}
            </select>
            <select name="team" id="org_team_select" style="width:100%;padding:8px 10px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;margin-bottom:10px;box-sizing:border-box;font-family:inherit;">
                <option value="">Geen team</option>
            </select>
            <select name="afdeling" style="width:100%;padding:8px 10px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;margin-bottom:10px;box-sizing:border-box;font-family:inherit;">
                <option value="">Geen toegangsrol</option>
                {% for a in afdelingen %}<option value="{{ a }}">{{ afdeling_labels[a] }}</option>{% endfor %}
            </select>
            <select name="rol" style="width:100%;padding:8px 10px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;margin-bottom:10px;box-sizing:border-box;font-family:inherit;">
                {% for r in rollen %}<option value="{{ r }}" {% if r == 'medewerker' %}selected{% endif %}>{{ rol_labels[r] }}</option>{% endfor %}
            </select>
            <label style="display:flex;align-items:center;gap:6px;font-size:13px;color:var(--gray-600);margin-bottom:12px;">
                <input type="checkbox" name="is_admin"> Admin (mag ook gebruikers beheren)
            </label>
            <button type="submit" class="btn-nav btn-nav-primary" style="border:none;cursor:pointer;width:100%;">+ Toevoegen (wachtwoord wordt automatisch gegenereerd)</button>
        </form>
    </div>

    <div class="info-kaart" style="max-width:420px;">
        <div class="dg-kaart-titel">Huidige gebruikers ({{ users|length }})</div>
        {% for naam, info in users.items() %}
        <div style="padding:10px 0;border-bottom:1px solid var(--gray-100);">
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div>
                    <b style="color:var(--gray-800);">{{ naam }}</b>
                    <span style="color:var(--gray-400);font-size:12px;"> · {{ info.team or "geen team" }}</span>
                    {% if info.get("is_admin", True) %}<span style="background:var(--brand-50);color:var(--brand-600);font-size:11px;font-weight:700;padding:2px 6px;border-radius:4px;margin-left:6px;">ADMIN</span>{% endif %}
                    {% if info.get("afdeling") %}<span style="background:var(--gray-100);color:var(--gray-600);font-size:11px;font-weight:600;padding:2px 6px;border-radius:4px;margin-left:6px;">{{ afdeling_labels.get(info.afdeling, info.afdeling) }}</span>{% endif %}
                    {% if info.get("rol") %}<span style="background:var(--gray-100);color:var(--gray-600);font-size:11px;font-weight:600;padding:2px 6px;border-radius:4px;margin-left:4px;">{{ rol_labels.get(info.rol, info.rol) }}</span>{% endif %}
                </div>
                {% if naam != gebruikersnaam %}
                <div style="display:flex;gap:10px;align-items:center;">
                    <form method="POST" style="margin:0;">
                        <input type="hidden" name="actie" value="toggle_admin">
                        <input type="hidden" name="gebruikersnaam" value="{{ naam }}">
                        <button type="submit" style="background:none;border:1px solid var(--gray-200);border-radius:6px;padding:3px 8px;color:var(--gray-500);cursor:pointer;font-size:11px;">{{ "Admin intrekken" if info.get("is_admin", True) else "Maak admin" }}</button>
                    </form>
                    <form method="POST" onsubmit="return confirm('{{ naam }} verwijderen?');" style="margin:0;">
                        <input type="hidden" name="actie" value="verwijderen">
                        <input type="hidden" name="gebruikersnaam" value="{{ naam }}">
                        <button type="submit" style="background:none;border:none;color:var(--gray-300);cursor:pointer;font-size:0.9rem;">✕</button>
                    </form>
                </div>
                {% endif %}
            </div>
            <form method="POST" style="display:flex;gap:6px;margin-top:6px;flex-wrap:wrap;">
                <input type="hidden" name="actie" value="wijzig_afdeling_rol">
                <input type="hidden" name="gebruikersnaam" value="{{ naam }}">
                <select name="org_afdeling" onchange="verversOrgTeamsVoorRij(this)" style="font-size:11px;padding:3px 6px;border:1px solid var(--gray-200);border-radius:5px;">
                    <option value="">Geen org.-afdeling</option>
                    {% for a in organisatiestructuur.keys() %}<option value="{{ a }}" {% if info.get("org_afdeling") == a %}selected{% endif %}>{{ a }}</option>{% endfor %}
                </select>
                <select name="team" onchange="this.form.submit()" style="font-size:11px;padding:3px 6px;border:1px solid var(--gray-200);border-radius:5px;">
                    <option value="">Geen team</option>
                    {% for t in organisatiestructuur.get(info.get("org_afdeling",""), []) %}<option value="{{ t }}" {% if info.get("team") == t %}selected{% endif %}>{{ t }}</option>{% endfor %}
                </select>
                <select name="afdeling" onchange="this.form.submit()" style="font-size:11px;padding:3px 6px;border:1px solid var(--gray-200);border-radius:5px;">
                    <option value="">Geen toegangsrol</option>
                    {% for a in afdelingen %}<option value="{{ a }}" {% if info.get("afdeling") == a %}selected{% endif %}>{{ afdeling_labels[a] }}</option>{% endfor %}
                </select>
                <select name="rol" onchange="this.form.submit()" style="font-size:11px;padding:3px 6px;border:1px solid var(--gray-200);border-radius:5px;">
                    {% for r in rollen %}<option value="{{ r }}" {% if info.get("rol") == r %}selected{% endif %}>{{ rol_labels[r] }}</option>{% endfor %}
                </select>
            </form>
        </div>
        {% endfor %}
    </div>
    <script>
    var ORGANISATIESTRUCTUUR = {{ organisatiestructuur_json|safe }};
    function verversOrgTeamsVoorRij(afdelingSelect) {
        var teamSelect = afdelingSelect.parentElement.querySelector('select[name="team"]');
        var teams = ORGANISATIESTRUCTUUR[afdelingSelect.value] || [];
        teamSelect.innerHTML = '<option value="">Geen team</option>';
        teams.forEach(function(t) {
            var optie = document.createElement("option");
            optie.value = t;
            optie.textContent = t;
            teamSelect.appendChild(optie);
        });
        afdelingSelect.form.submit();
    }
    function verversOrgTeams() {
        var afdelingSelect = document.getElementById("org_afdeling_select");
        var teamSelect = document.getElementById("org_team_select");
        if (!afdelingSelect || !teamSelect) return;
        var teams = ORGANISATIESTRUCTUUR[afdelingSelect.value] || [];
        teamSelect.innerHTML = '<option value="">Geen team</option>';
        teams.forEach(function(t) {
            var optie = document.createElement("option");
            optie.value = t;
            optie.textContent = t;
            teamSelect.appendChild(optie);
        });
    }
    </script>
    """
    pagina = render_simple_page("Gebruikers beheren", "instellingen", inhoud)
    return render_template_string(pagina, users=users, bericht=bericht, nieuw_wachtwoord=nieuw_wachtwoord,
                                    afdelingen=AFDELINGEN, afdeling_labels=AFDELING_LABELS, rollen=ROLLEN, rol_labels=ROL_LABELS,
                                    organisatiestructuur=laad_organisatiestructuur(), organisatiestructuur_json=json.dumps(laad_organisatiestructuur()))

@app.route("/instellingen/eigen-bedrijfsgegevens", methods=["GET", "POST"])
def instellingen_eigen_bedrijfsgegevens():
    """Peute's eigen bedrijfsgegevens — worden als afzender op elke
    gegenereerde factuur gebruikt (verplicht voor een geldige NL-factuur:
    bedrijfsnaam, adres, KvK, BTW-id, IBAN)."""
    _guard = vereist_admin_of_403()
    if _guard: return _guard

    if request.method == "POST":
        gegevens = {
            "naam": request.form.get("naam", "").strip(),
            "adres": request.form.get("adres", "").strip(),
            "postcode": request.form.get("postcode", "").strip(),
            "stad": request.form.get("stad", "").strip(),
            "land": request.form.get("land", "Nederland").strip(),
            "kvk_nummer": request.form.get("kvk_nummer", "").strip(),
            "btw_nummer": request.form.get("btw_nummer", "").strip(),
            "iban": request.form.get("iban", "").strip(),
            "bic": request.form.get("bic", "").strip(),
            "eori_nummer": request.form.get("eori_nummer", "").strip(),
        }
        bewaar_eigen_bedrijfsgegevens(gegevens)
        return redirect(url_for("instellingen_eigen_bedrijfsgegevens", opgeslagen="1"))

    waarden = laad_eigen_bedrijfsgegevens()
    opgeslagen = request.args.get("opgeslagen") == "1"
    ontbrekende_velden = [label for veld, label in [
        ("naam","Bedrijfsnaam"), ("adres","Adres"), ("kvk_nummer","KvK-nummer"),
        ("btw_nummer","BTW-nummer"), ("iban","IBAN"),
    ] if not waarden.get(veld)]

    inhoud = """
<div class="page-title">Eigen bedrijfsgegevens</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:16px;font-size:0.85rem;">Deze gegevens verschijnen als afzender op elke factuur die het systeem genereert — verplicht voor een geldige Nederlandse factuur.</p>

{% if opgeslagen %}<div style="background:#f0fdf4;color:#16a34a;padding:10px 14px;border-radius:8px;margin-bottom:16px;font-size:12.5px;">Opgeslagen.</div>{% endif %}
{% if ontbrekende_velden %}
<div style="background:#fef3c7;color:#b45309;padding:10px 14px;border-radius:8px;margin-bottom:16px;font-size:12.5px;">
    Nog niet compleet — ontbreekt: {{ ontbrekende_velden|join(', ') }}. Facturen kunnen wel al gegenereerd worden, maar zijn dan niet volledig conform de wettelijke eisen.
</div>
{% endif %}

<div style="background:#fff;border:1px solid var(--gray-200);border-radius:10px;padding:20px 22px;max-width:600px;">
    <form method="POST">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Bedrijfsnaam *</label>
        <input type="text" name="naam" value="{{ waarden.naam }}" required style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-bottom:14px;margin-top:4px;box-sizing:border-box;">

        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Adres *</label>
        <input type="text" name="adres" value="{{ waarden.adres }}" required style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-bottom:14px;margin-top:4px;box-sizing:border-box;">

        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin-bottom:14px;">
            <div>
                <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Postcode</label>
                <input type="text" name="postcode" value="{{ waarden.postcode }}" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-top:4px;box-sizing:border-box;">
            </div>
            <div>
                <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Stad</label>
                <input type="text" name="stad" value="{{ waarden.stad }}" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-top:4px;box-sizing:border-box;">
            </div>
            <div>
                <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Land</label>
                <input type="text" name="land" value="{{ waarden.land }}" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-top:4px;box-sizing:border-box;">
            </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px;">
            <div>
                <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">KvK-nummer *</label>
                <input type="text" name="kvk_nummer" value="{{ waarden.kvk_nummer }}" required style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-top:4px;box-sizing:border-box;">
            </div>
            <div>
                <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">BTW-identificatienummer *</label>
                <input type="text" name="btw_nummer" value="{{ waarden.btw_nummer }}" required placeholder="NL000000000B00" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-top:4px;box-sizing:border-box;">
            </div>
        </div>

        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;margin-bottom:6px;">
            <div>
                <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">IBAN *</label>
                <input type="text" name="iban" value="{{ waarden.iban }}" required style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-top:4px;box-sizing:border-box;">
            </div>
            <div>
                <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">BIC</label>
                <input type="text" name="bic" value="{{ waarden.bic }}" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-top:4px;box-sizing:border-box;">
            </div>
            <div>
                <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">EORI-nummer</label>
                <input type="text" name="eori_nummer" value="{{ waarden.eori_nummer }}" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-top:4px;box-sizing:border-box;">
            </div>
        </div>
        <div style="font-size:11px;color:var(--gray-400);margin-bottom:16px;">EORI alleen nodig bij internationale handel buiten de EU.</div>

        <button type="submit" style="padding:9px 20px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-weight:700;cursor:pointer;font-size:13px;">Opslaan</button>
    </form>
</div>
    """
    pagina = render_simple_page("Eigen bedrijfsgegevens", "instellingen", inhoud)
    return render_template_string(pagina, waarden=waarden, opgeslagen=opgeslagen, ontbrekende_velden=ontbrekende_velden)


def _persoonlijke_informatie_inhoud():
    """Eigen profiel: weergavenaam (los van de inlognaam), e-mailadres en een
    profielfoto. De weergavenaam wordt gebruikt in de zijbalk; e-mailadres en
    profielfoto zijn voor nu puur informatief (nog niet elders in de app
    gebruikt, bijvoorbeeld voor toewijzingen of meldingen)."""
    gebruikersnaam = session.get("gebruikersnaam", "")
    users = laad_users()
    eigen_gegevens = users.get(gebruikersnaam, {})
    opgeslagen = request.args.get("opgeslagen") == "1"
    wachtwoord_gewijzigd = request.args.get("wachtwoord_gewijzigd") == "1"
    wachtwoord_fout = request.args.get("wachtwoord_fout", "")
    WACHTWOORD_FOUTMELDINGEN = {
        "wachtwoord_onjuist": "Je huidige wachtwoord klopt niet.",
        "wachtwoord_te_kort": "Nieuw wachtwoord moet minstens 6 tekens zijn.",
        "wachtwoord_komt_niet_overeen": "De bevestiging komt niet overeen met het nieuwe wachtwoord.",
    }

    inhoud = """
    <div class="page-title">Persoonlijke informatie</div>
    {% if opgeslagen %}<div style="background:#f0fdf4;color:#16a34a;padding:10px 14px;border-radius:8px;margin-bottom:16px;font-size:12.5px;max-width:420px;">Opgeslagen.</div>{% endif %}

    <style>
        .profielfoto-cirkel { position:relative; width:64px; height:64px; flex-shrink:0; }
        .profielfoto-cirkel img, .profielfoto-cirkel .profielfoto-initialen { width:64px; height:64px; border-radius:50%; object-fit:cover; display:flex; align-items:center; justify-content:center; font-weight:800; font-size:19px; background:var(--brand-600); color:#fff; }
        .profielfoto-plus { position:absolute; bottom:-2px; right:-2px; width:22px; height:22px; border-radius:50%; background:var(--brand-600); color:#fff; border:2px solid #fff; display:flex; align-items:center; justify-content:center; font-size:14px; font-weight:800; cursor:pointer; line-height:1; }
        .profielfoto-label { cursor:pointer; display:block; }
    </style>

    <div class="info-kaart" style="max-width:420px;margin-bottom:16px;">
        <form method="POST" enctype="multipart/form-data">
            <div style="display:flex;align-items:center;gap:14px;margin-bottom:20px;">
                <label class="profielfoto-label" title="Profielfoto wijzigen">
                    <div class="profielfoto-cirkel">
                        <img id="profielfotoPreview" src="{% if eigen_gegevens.profielfoto %}/fotos_uploads/{{ eigen_gegevens.profielfoto }}{% endif %}" style="{% if not eigen_gegevens.profielfoto %}display:none;{% endif %}">
                        <div id="profielfotoInitialen" class="profielfoto-initialen" style="{% if eigen_gegevens.profielfoto %}display:none;{% endif %}">{{ (eigen_gegevens.weergavenaam or gebruikersnaam)[:2]|upper }}</div>
                        <div class="profielfoto-plus">+</div>
                    </div>
                    <input type="file" name="profielfoto" accept="image/*" style="display:none;" onchange="profielfotoWijzigen(this)">
                </label>
                <div>
                    <div style="font-weight:700;color:var(--gray-800);">{{ eigen_gegevens.weergavenaam or gebruikersnaam }}</div>
                    <div style="font-size:11.5px;color:var(--gray-400);">Inlognaam: {{ gebruikersnaam }}</div>
                </div>
            </div>

            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Naam (zichtbaar in de app)</label>
            <input type="text" name="weergavenaam" value="{{ eigen_gegevens.weergavenaam or '' }}" placeholder="{{ gebruikersnaam }}" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-bottom:14px;margin-top:4px;box-sizing:border-box;">

            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">E-mailadres</label>
            <input type="email" name="email" value="{{ eigen_gegevens.email or '' }}" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-bottom:18px;margin-top:4px;box-sizing:border-box;">

            <button type="submit" style="padding:9px 20px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-weight:700;cursor:pointer;font-size:13px;">Opslaan</button>
        </form>
    </div>

    <div class="info-kaart" style="max-width:420px;">
        <div class="drawer-row"><span class="drawer-row-label">Team</span><span class="drawer-row-value">{{ team or "—" }}</span></div>
        <div class="drawer-row"><span class="drawer-row-label">Afdeling</span><span class="drawer-row-value">{{ AFDELING_LABELS.get(eigen_gegevens.get("afdeling",""), eigen_gegevens.get("afdeling","") or "—") }}</span></div>
        <hr class="drawer-divider">
        <a href="/logout" class="btn-nav btn-nav-primary" style="display:inline-block;">Uitloggen</a>
    </div>

    <div class="info-kaart" style="max-width:420px;margin-top:16px;">
        <div class="dg-kaart-titel">Wachtwoord wijzigen</div>
        {% if wachtwoord_gewijzigd %}<div style="background:#f0fdf4;color:#16a34a;padding:9px 12px;border-radius:7px;margin-bottom:12px;font-size:12px;">Wachtwoord gewijzigd.</div>{% endif %}
        {% if wachtwoord_fout %}<div style="background:#fef2f2;color:#dc2626;padding:9px 12px;border-radius:7px;margin-bottom:12px;font-size:12px;">{{ wachtwoord_foutmeldingen.get(wachtwoord_fout, "Er ging iets mis.") }}</div>{% endif %}
        <form method="POST" action="/instellingen/wachtwoord">
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Huidig wachtwoord</label>
            <input type="password" name="huidig_wachtwoord" required style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-bottom:12px;margin-top:4px;box-sizing:border-box;">
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Nieuw wachtwoord</label>
            <input type="password" name="nieuw_wachtwoord" required minlength="6" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-bottom:12px;margin-top:4px;box-sizing:border-box;">
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Nieuw wachtwoord bevestigen</label>
            <input type="password" name="nieuw_wachtwoord_bevestig" required minlength="6" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-bottom:16px;margin-top:4px;box-sizing:border-box;">
            <button type="submit" style="padding:9px 20px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-weight:700;cursor:pointer;font-size:13px;">Wachtwoord wijzigen</button>
        </form>
    </div>

    <script>
    function profielfotoWijzigen(input) {
        if (!input.files || !input.files[0]) return;
        var reader = new FileReader();
        reader.onload = function(e) {
            var img = document.getElementById("profielfotoPreview");
            img.src = e.target.result;
            img.style.display = "block";
            document.getElementById("profielfotoInitialen").style.display = "none";
        };
        reader.readAsDataURL(input.files[0]);
    }
    </script>
    """
    return inhoud, dict(gebruikersnaam=gebruikersnaam, eigen_gegevens=eigen_gegevens, opgeslagen=opgeslagen,
                          team=session.get("team",""), AFDELING_LABELS=AFDELING_LABELS,
                          wachtwoord_gewijzigd=wachtwoord_gewijzigd, wachtwoord_fout=wachtwoord_fout,
                          wachtwoord_foutmeldingen=WACHTWOORD_FOUTMELDINGEN)


def _beheer_inhoud():
    """De bestaande admin-links, nu als klikbare kaart-tegels gegroepeerd in
    logische categorieën — zelfde grid-patroon als de /logistiek-hubpagina,
    i.p.v. tekstlinks onder elkaar. Zelfde links als voorheen."""
    categorieen = [
        ("Data importeren", [
            {"titel": "Excel-import", "href": "/importeer", "beschrijving": "Bedrijven in bulk toevoegen vanuit een Excel-bestand."},
            {"titel": "OpenStreetMap-import", "href": "/importeer-osm", "beschrijving": "Bedrijven zoeken en toevoegen via OpenStreetMap."},
            {"titel": "ScrapMonster-import", "href": "/importeer-scrapmonster", "beschrijving": "Schroothandels importeren vanuit ScrapMonster."},
            {"titel": "UK overheidsregister-import", "href": "/importeer-gov-uk", "beschrijving": "Britse bedrijven importeren via het overheidsregister."},
        ]),
        ("Data-onderhoud", [
            {"titel": "Dubbele bedrijven opschonen", "href": "/opschonen-dubbelen", "beschrijving": "Vindt en verwijdert dubbel ingevoerde bedrijven."},
            {"titel": "Ontbrekende coördinaten aanvullen", "href": "/geocode-aanvullen", "beschrijving": "Geocodeert bedrijven zonder lat/lon, 50 per keer."},
            {"titel": "Bedrijfstypes aanvullen", "href": "/herlabel-brontype", "beschrijving": "Vult ontbrekende bedrijfstype-labels aan."},
            {"titel": "UK-bedrijven controleren", "href": "/controleer-uk-status", "beschrijving": "Controleert Britse bedrijven bij Companies House."},
            {"titel": "Live data downloaden", "href": "/export-data", "beschrijving": "Backup of synchronisatie van alle live data."},
        ]),
        ("Gebruikers & instellingen", [
            {"titel": "Gebruikers beheren", "href": "/gebruikers-beheer", "beschrijving": "Accounts toevoegen, verwijderen en rechten instellen."},
            {"titel": "Materialen beheren", "href": "/materialen-beheer", "beschrijving": "Het materialen- en kwaliteitenoverzicht bijwerken."},
            {"titel": "Commerciële instellingen", "href": "/instellingen/commercieel", "beschrijving": "Incoterms, betalingstermijnen, valuta, POD, bedrijfseenheden."},
            {"titel": "Eigen bedrijfsgegevens", "href": "/instellingen/eigen-bedrijfsgegevens", "beschrijving": "KvK, BTW en IBAN voor op facturen."},
        ]),
    ]

    inhoud = """
    <div class="page-title">Beheer</div>
    <p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Alleen zichtbaar voor beheerders.</p>

    {% for categorie_titel, kaarten in categorieen %}
    <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">{{ categorie_titel }}</div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin-bottom:24px;">
        {% for k in kaarten %}
        <a href="{{ k.href }}" style="display:block;background:#fff;border:1px solid var(--gray-200);border-radius:10px;padding:16px 18px;text-decoration:none;color:inherit;">
            <div style="font-size:13.5px;font-weight:700;color:var(--gray-800);margin-bottom:6px;">{{ k.titel }} →</div>
            <div style="font-size:12px;color:var(--gray-500);line-height:1.5;">{{ k.beschrijving }}</div>
        </a>
        {% endfor %}
    </div>
    {% endfor %}

    <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Bedrijfslogo (op de weegbon)</div>
    <div class="info-kaart" style="max-width:440px;">
        {% if logo_instelling.bestandsnaam %}
        <img src="/bedrijfslogo/{{ logo_instelling.bestandsnaam }}" style="max-width:160px;max-height:60px;margin-bottom:10px;display:block;">
        {% else %}
        <div style="font-size:12.5px;color:var(--gray-400);margin-bottom:10px;">Nog geen logo geüpload.</div>
        {% endif %}
        <form method="POST" action="/instellingen/logo" enctype="multipart/form-data">
            <input type="file" name="logo" accept="image/*" style="font-size:12px;margin-bottom:8px;display:block;">
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Positie op de weegbon</label>
            <select name="positie" style="width:100%;padding:6px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-bottom:10px;margin-top:2px;">
                {% for p in logo_posities %}<option value="{{ p }}" {% if logo_instelling.positie == p %}selected{% endif %}>{{ p|capitalize }}</option>{% endfor %}
            </select>
            <button type="submit" style="padding:7px 16px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:12.5px;font-weight:700;cursor:pointer;">Opslaan</button>
        </form>
    </div>
    """
    return inhoud, dict(categorieen=categorieen, logo_instelling=laad_bedrijfslogo_instelling(), logo_posities=LOGO_POSITIES)


@app.route("/instellingen/wachtwoord", methods=["POST"])
def instellingen_wachtwoord_wijzigen():
    """Eigen wachtwoord wijzigen — vereist het huidige wachtwoord ter
    verificatie (niet zomaar overschrijfbaar door iemand die al bij een
    ingelogde sessie kan, en beschermt tegen een fout-getypt nieuw
    wachtwoord door een verplichte bevestiging)."""
    gebruikersnaam = session.get("gebruikersnaam", "")
    huidig_wachtwoord = request.form.get("huidig_wachtwoord", "")
    nieuw_wachtwoord = request.form.get("nieuw_wachtwoord", "")
    nieuw_wachtwoord_bevestig = request.form.get("nieuw_wachtwoord_bevestig", "")

    users = laad_users()
    fout = ""
    if gebruikersnaam not in users or not check_password_hash(users[gebruikersnaam]["wachtwoord"], huidig_wachtwoord):
        fout = "wachtwoord_onjuist"
    elif len(nieuw_wachtwoord) < 6:
        fout = "wachtwoord_te_kort"
    elif nieuw_wachtwoord != nieuw_wachtwoord_bevestig:
        fout = "wachtwoord_komt_niet_overeen"
    else:
        users[gebruikersnaam]["wachtwoord"] = generate_password_hash(nieuw_wachtwoord)
        bewaar_users(users)
        return redirect(url_for("instellingen", modus="profiel", wachtwoord_gewijzigd="1"))

    return redirect(url_for("instellingen", modus="profiel", wachtwoord_fout=fout))


@app.route("/instellingen", methods=["GET", "POST"])
def instellingen():
    _guard = vereist_afdeling_of_403("instellingen")
    if _guard: return _guard

    is_admin = is_huidige_gebruiker_admin()
    modus = request.args.get("modus", "profiel")
    if modus == "beheer" and not is_admin:
        modus = "profiel"

    if request.method == "POST" and modus == "profiel":
        gebruikersnaam = session.get("gebruikersnaam", "")
        users = laad_users()
        if gebruikersnaam in users:
            users[gebruikersnaam]["weergavenaam"] = request.form.get("weergavenaam", "").strip()
            users[gebruikersnaam]["email"] = request.form.get("email", "").strip()
            bestand = request.files.get("profielfoto")
            if bestand and bestand.filename:
                extensie = bestand.filename.rsplit(".", 1)[-1].lower() if "." in bestand.filename else ""
                if extensie in ("jpg", "jpeg", "png", "gif", "webp"):
                    if not os.path.exists(FOTOS_MAP):
                        os.makedirs(FOTOS_MAP)
                    nieuwe_bestandsnaam = f"profiel_{uuid.uuid4()}.{extensie}"
                    bestand.save(os.path.join(FOTOS_MAP, nieuwe_bestandsnaam))
                    users[gebruikersnaam]["profielfoto"] = nieuwe_bestandsnaam
            bewaar_users(users)
        return redirect(url_for("instellingen", modus="profiel", opgeslagen="1"))

    if modus == "beheer":
        _tab_inhoud, _tab_context = _beheer_inhoud()
    else:
        _tab_inhoud, _tab_context = _persoonlijke_informatie_inhoud()

    _tabbladen = [("profiel", "Persoonlijke informatie")]
    if is_admin:
        _tabbladen.append(("beheer", "Beheer"))
    _tabbladen_html = "".join(
        f'<a href="/instellingen?modus={sleutel}" style="padding:8px 16px;font-size:12.5px;font-weight:700;text-decoration:none;border-bottom:2px solid {"var(--brand-600)" if sleutel == modus else "transparent"};color:{"var(--brand-600)" if sleutel == modus else "var(--gray-400)"};">{titel}</a>'
        for sleutel, titel in _tabbladen
    )

    inhoud = f"""
    <div style="display:flex;gap:4px;border-bottom:1px solid var(--gray-200);margin-bottom:20px;">
        {_tabbladen_html}
    </div>
    {_tab_inhoud}
    """
    pagina = render_simple_page("Instellingen", "instellingen", inhoud)
    return render_template_string(pagina, **_tab_context)

@app.route("/instellingen/logo", methods=["POST"])
def instellingen_logo_upload():
    if not is_huidige_gebruiker_admin():
        return redirect(url_for("instellingen"))
    instelling = laad_bedrijfslogo_instelling()
    bestand = request.files.get("logo")
    if bestand and bestand.filename:
        _, extensie = os.path.splitext(bestand.filename)
        if extensie.lower() in (".png", ".jpg", ".jpeg", ".svg", ".gif"):
            if not os.path.exists(LOGO_MAP):
                os.makedirs(LOGO_MAP)
            nieuwe_bestandsnaam = f"logo{extensie.lower()}"
            bestand.save(os.path.join(LOGO_MAP, nieuwe_bestandsnaam))
            instelling["bestandsnaam"] = nieuwe_bestandsnaam
    instelling["positie"] = request.form.get("positie", "links") if request.form.get("positie") in LOGO_POSITIES else instelling.get("positie", "links")
    bewaar_bedrijfslogo_instelling(instelling)
    return redirect(url_for("instellingen"))

@app.route("/bedrijfslogo/<bestandsnaam>")
def bedrijfslogo_bestand(bestandsnaam):
    from flask import send_from_directory
    return send_from_directory(LOGO_MAP, bestandsnaam)





FOUTPAGINA_HTML = '''
<!DOCTYPE html>
<html lang="nl">
<head>
    <meta charset="UTF-8">
    <title>{{ titel }} — FTNext</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: "Inter", -apple-system, sans-serif;
            background: radial-gradient(circle at 20% 10%, #eef6f6 0%, #f8fafc 45%, #f1f5f9 100%);
            min-height: 100vh; display: flex; align-items: center; justify-content: center; margin: 0; padding: 20px;
        }
        .box { text-align: center; max-width: 420px; }
        .code { font-size: 4.5rem; font-weight: 900; color: #0d5c62; letter-spacing: -3px; line-height: 1; margin-bottom: 12px; }
        h1 { font-size: 1.3rem; font-weight: 800; color: #0f172a; margin-bottom: 8px; }
        p { color: #64748b; font-size: 0.9rem; margin-bottom: 24px; }
        a { display: inline-block; padding: 11px 22px; background: linear-gradient(135deg, #14767b, #0d5c62); color: #fff;
            border-radius: 8px; text-decoration: none; font-weight: 700; font-size: 0.85rem; }
        a:hover { box-shadow: 0 8px 20px rgba(234,88,12,0.3); }
    </style>
</head>
<body>
    <div class="box">
        <div class="code">{{ code }}</div>
        <h1>{{ titel }}</h1>
        <p>{{ boodschap }}</p>
        <a href="/">← Terug naar FTNext</a>
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