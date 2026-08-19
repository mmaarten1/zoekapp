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

from core import (
    datapad, laad_users, laad_accountmanagers, bewaar_accountmanagers,
    laad_status, bewaar_status, laad_voorraadmomenten, bewaar_voorraadmomenten,
    laad_shipments, bewaar_shipments, laad_cert_vervaldatums, bewaar_cert_vervaldatums,
    _cert_sleutel, laad_contactpersonen, bewaar_contactpersonen, sync_contactpersoon_naar_contacten,
    laad_facturen, bewaar_facturen, bepaal_factuur_status, laad_documenten,
    bewaar_documenten, laad_uitnodigingen, bewaar_uitnodigingen, laad_marktprijzen,
    bewaar_marktprijzen, laad_contracten, bewaar_contracten, laad_voorraad,
    bewaar_voorraad, laad_orders, bewaar_orders, laad_meldingen,
    bewaar_meldingen, laad_materiaal_taxonomie, bewaar_materiaal_taxonomie, laad_fotos,
    bewaar_fotos, laad_fotomappen, bewaar_fotomappen, laad_notities,
    bewaar_notities, get_user_id, laad_geocode_cache, bewaar_geocode_cache,
    parse_hoeveelheid_getal, bereken_voorraad_status, voldoet_aan_materiaal_min_volume, bereken_afstand_km,
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
    PAGINA_HOOFD, sidebar_html, render_simple_page, is_huidige_gebruiker_admin, vereist_admin_of_403,
    ENF_BEDRIJVEN, PAPIERFABRIEKEN, bewaar_bedrijven, bewaar_papierfabrieken,
    TRANSPORT_DATA, vind_transport_tarieven_dichtbij, ORDER_KLEUREN, SHIPMENT_STATUSSEN, LANDEN,
    bewaar_users, AFDELINGEN, AFDELING_LABELS, ROLLEN, ROL_LABELS,
    mag_pagina_zien, vereist_afdeling_of_403, PAGINA_AFDELINGEN,
    laad_containers, bewaar_containers, CONTAINER_TYPES, CONTAINER_STATUSSEN,
    laad_logistieke_orders, bewaar_logistieke_orders, laad_weegbrug, laad_documenten,
    laad_bedrijfslogo_instelling, bewaar_bedrijfslogo_instelling, LOGO_MAP, LOGO_POSITIES,
)

from bs4 import BeautifulSoup

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "verander-dit-later-in-iets-geheims")

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

from orders import orders_bp
app.register_blueprint(orders_bp)

from voorraad import voorraad_bp
app.register_blueprint(voorraad_bp)

from dashboard import dashboard_bp
app.register_blueprint(dashboard_bp)

from zoeken import zoeken_bp
app.register_blueprint(zoeken_bp)

from weegbrug import weegbrug_bp
app.register_blueprint(weegbrug_bp)

from logistieke_orders import logistieke_orders_bp
app.register_blueprint(logistieke_orders_bp)

from transport_planning import transport_planning_bp
app.register_blueprint(transport_planning_bp)

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

            ENF_BEDRIJVEN.append({
                "naam": naam, "land": land_naam, "regio": stad,
                "materialen": "Metal", "klanttype": "", "volume": "", "url": "",
                "lat": None, "lon": None,
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

                nieuwe_bedrijven_tmp.append({
                    "naam": naam, "land": "United Kingdom", "regio": stad,
                    "materialen": gegokt_materiaal, "klanttype": "", "volume": "", "url": "",
                    "lat": None, "lon": None,
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
            session["afdeling"] = users[gebruikersnaam].get("afdeling", "")
            session["rol"] = users[gebruikersnaam].get("rol", "")
            return redirect(url_for("zoeken.index"))
        else:
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
    _guard = vereist_afdeling_of_403("logistiek")
    if _guard: return _guard
    vooringevuld_bedrijf = request.args.get("bedrijf", "")

    alle_shipments_log = laad_shipments()
    for s in alle_shipments_log:
        s["flow_type"] = bepaal_shipment_flow_type(s)
    actieve_shipments_log = [s for s in alle_shipments_log if s.get("status") != "Cancelled"]

    if vooringevuld_bedrijf:
        _naam_laag = vooringevuld_bedrijf.strip().lower()
        actieve_shipments_log = [
            s for s in actieve_shipments_log
            if s.get("origin_leverancier", "").strip().lower() == _naam_laag
            or s.get("destination_naam", "").strip().lower() == _naam_laag
        ]

    filter_flow_type = request.args.get("filter_flow_type", "")
    filter_status_log = request.args.get("filter_status", "")
    filter_materiaal_log = request.args.get("filter_materiaal", "")
    getoonde_shipments_log = actieve_shipments_log
    if filter_flow_type:
        getoonde_shipments_log = [s for s in getoonde_shipments_log if s.get("flow_type") == filter_flow_type]
    if filter_status_log:
        getoonde_shipments_log = [s for s in getoonde_shipments_log if s.get("status") == filter_status_log]
    if filter_materiaal_log:
        getoonde_shipments_log = [s for s in getoonde_shipments_log if s.get("materiaal") == filter_materiaal_log]
    getoonde_shipments_log = sorted(getoonde_shipments_log, key=lambda s: s.get("datum", ""), reverse=True)

    shipment_materialen_log = sorted({s.get("materiaal", "") for s in actieve_shipments_log if s.get("materiaal")})

    # --- Logistiek-dashboard-KPI's (alleen echte, berekende data — geen chauffeursplanning: geen datamodel daarvoor) ---
    _vandaag_log = datetime.date.today().isoformat()
    kpi_ritten_vandaag = [s for s in actieve_shipments_log if s.get("datum","") == _vandaag_log]
    kpi_actieve_ritten = [s for s in actieve_shipments_log if s.get("status") in ("Loading", "Loaded", "In Transit", "Arrived")]
    _alle_containers_log = laad_containers()
    kpi_te_laden_containers = [c for c in _alle_containers_log if c.get("status") == "Leeg"]
    kpi_recente_wegingen = sorted(
        [s for s in actieve_shipments_log if s.get("status") in ("Weighed", "Received") and s.get("weegbon_nummer")],
        key=lambda s: s.get("datum",""), reverse=True
    )[:5]
    _shipments_met_kosten = [s for s in actieve_shipments_log if s.get("transportkosten")]
    kpi_totale_kosten = sum(parse_hoeveelheid_getal(s["transportkosten"]) for s in _shipments_met_kosten)
    kpi_kosten_aantal = len(_shipments_met_kosten)

    inhoud = """
<div class="dg-grid" style="margin-bottom:20px;">
    <div class="dg-kaart"><div class="dg-icoon">🚚</div><div class="dg-getal">{{ kpi_ritten_vandaag|length }}</div><div class="dg-label">Ritten vandaag</div></div>
    <div class="dg-kaart"><div class="dg-icoon">📍</div><div class="dg-getal">{{ kpi_actieve_ritten|length }}</div><div class="dg-label">Actief onderweg/laden</div></div>
    <div class="dg-kaart"><div class="dg-icoon">📦</div><div class="dg-getal">{{ kpi_te_laden_containers|length }}</div><div class="dg-label">Containers te laden</div></div>
    <div class="dg-kaart"><div class="dg-icoon">⚖️</div><div class="dg-getal">{{ kpi_recente_wegingen|length }}</div><div class="dg-label">Recente wegingen</div></div>
    <div class="dg-kaart"><div class="dg-icoon">💶</div><div class="dg-getal" style="font-size:1.3rem;">{{ "€{:,.0f}".format(kpi_totale_kosten) }}</div><div class="dg-label">Transportkosten ({{ kpi_kosten_aantal }} ritten)</div></div>
</div>
<style>
.log-tabel-rij { display:flex; align-items:center; padding:10px 16px; border-bottom:1px solid var(--gray-100); font-size:13px; }
.log-tabel-kop { display:flex; align-items:center; padding:10px 16px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); font-size:10px; letter-spacing:0.08em; text-transform:uppercase; color:#7d8792; }
.log-badge { font-size:10px; font-weight:700; padding:2px 7px; border-radius:4px; }
.dg-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:14px; }
.dg-kaart { background:transparent; border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); border-radius:0; padding:16px 4px; }
.dg-icoon { font-size:1.2rem; margin-bottom:6px; }
.dg-getal { font-size:1.7rem; font-weight:800; color:var(--brand-700); }
.dg-label { font-size:0.72rem; color:var(--gray-400); text-transform:uppercase; letter-spacing:0.8px; margin-top:4px; font-weight:600; }
@media (max-width:768px) { .dg-grid { grid-template-columns:repeat(2,1fr); } }
</style>
<div class="page-title">Logistiek</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:12px;font-size:0.85rem;">
    {% if vooringevuld_bedrijf %}Shipments voor <b style="color:var(--gray-700);">{{ vooringevuld_bedrijf }}</b> — <a href="/logistiek" style="color:var(--brand-600);">alles tonen</a>
    {% else %}Alle actieve shipments (inbound, outbound en direct flow){% endif %}
</p>
<a href="/logistiek/containers" style="display:inline-block;margin-bottom:20px;font-size:12.5px;font-weight:600;color:var(--brand-600);text-decoration:none;border:1px solid var(--gray-200);padding:6px 12px;border-radius:6px;">📦 Containerbeheer →</a>

<form method="GET" style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
    {% if vooringevuld_bedrijf %}<input type="hidden" name="bedrijf" value="{{ vooringevuld_bedrijf }}">{% endif %}
    <select name="filter_flow_type" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle types</option>
        <option value="inbound" {% if filter_flow_type == "inbound" %}selected{% endif %}>Inbound</option>
        <option value="outbound" {% if filter_flow_type == "outbound" %}selected{% endif %}>Outbound</option>
        <option value="direct" {% if filter_flow_type == "direct" %}selected{% endif %}>Direct</option>
    </select>
    <select name="filter_status" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle statussen</option>
        {% for st in shipment_statussen %}<option value="{{ st }}" {% if filter_status_log == st %}selected{% endif %}>{{ st }}</option>{% endfor %}
    </select>
    <select name="filter_materiaal" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle materialen</option>
        {% for m in shipment_materialen_log %}<option value="{{ m }}" {% if filter_materiaal_log == m %}selected{% endif %}>{{ m }}</option>{% endfor %}
    </select>
    <span style="font-size:12px;color:var(--gray-400);margin-left:auto;">{{ getoonde_shipments_log|length }} van {{ actieve_shipments_log|length }}</span>
</form>

{% if getoonde_shipments_log %}
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);">
    <div class="log-tabel-kop">
        <span style="width:100px;">Datum</span>
        <span style="flex:1.6;">Route</span>
        <span style="flex:1;">Materiaal</span>
        <span style="width:110px;text-align:right;">Ton</span>
        <span style="width:90px;">Type</span>
        <span style="width:120px;">Status</span>
        <span style="width:100px;text-align:right;">Kosten</span>
        <span style="width:80px;"></span>
    </div>
    {% for s in getoonde_shipments_log %}
    <div class="log-tabel-rij" style="flex-wrap:wrap;">
        <span style="width:100px;color:var(--gray-500);">{{ s.datum }}</span>
        <span style="flex:1.6;color:var(--gray-800);font-weight:600;">{{ s.origin_land }}{% if s.origin_leverancier %} ({{ s.origin_leverancier }}){% endif %} → {{ s.destination_land }}{% if s.destination_naam %} ({{ s.destination_naam }}){% endif %}</span>
        <span style="flex:1;color:var(--gray-600);">{{ s.materiaal }}</span>
        <span style="width:110px;text-align:right;font-family:var(--font-mono);color:var(--gray-600);">{{ s.gepland_hoeveelheid }}{% if s.werkelijk_hoeveelheid %} / {{ s.werkelijk_hoeveelheid }}{% endif %}</span>
        <span style="width:90px;">
            <span class="log-badge" style="background:{{ '#eff6ff' if s.flow_type=='inbound' else ('#fef2f2' if s.flow_type=='outbound' else '#f5f3ff') }};color:{{ '#1d4ed8' if s.flow_type=='inbound' else ('#dc2626' if s.flow_type=='outbound' else '#7c3aed') }};">{{ s.flow_type|upper }}</span>
        </span>
        <span style="width:120px;color:var(--gray-600);">{{ s.status }}</span>
        <span style="width:100px;">
            <form method="POST" action="/voorraad/shipments" style="margin:0;display:flex;align-items:center;gap:2px;">
                <input type="hidden" name="actie" value="kosten_bijwerken">
                <input type="hidden" name="shipment_id" value="{{ s.id }}">
                <input type="hidden" name="terug_naar" value="logistiek">
                <span style="font-size:11px;color:var(--gray-400);">€</span>
                <input type="text" name="transportkosten" value="{{ s.transportkosten|default('',true) }}" onblur="this.form.submit()" placeholder="0" style="width:60px;padding:3px 4px;border:1px solid var(--gray-200);border-radius:4px;font-size:11.5px;text-align:right;font-family:inherit;">
            </form>
        </span>
        <span style="width:80px;">
            <button type="button" onclick="toggleShipmentDocs('{{ s.id }}')" style="background:none;border:1px solid var(--gray-200);border-radius:5px;padding:3px 8px;font-size:11px;color:var(--gray-500);cursor:pointer;">📎 Docs</button>
        </span>
        <div id="docs-{{ s.id }}" style="display:none;width:100%;margin-top:10px;padding:12px;background:var(--gray-50);border-radius:6px;">
            <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">CMR / Annex / exportdocumenten</div>
            <div id="docslijst-{{ s.id }}" style="margin-bottom:8px;font-size:12.5px;color:var(--gray-400);">Laden...</div>
            <input type="file" id="docupload-{{ s.id }}" accept=".pdf,.doc,.docx" style="font-size:12px;">
            <button type="button" onclick="uploadShipmentDoc('{{ s.id }}')" style="font-size:11.5px;padding:4px 10px;background:var(--brand-600);color:#fff;border:none;border-radius:5px;cursor:pointer;margin-left:6px;">Uploaden</button>
        </div>
    </div>
    {% endfor %}
</div>
<script>
function toggleShipmentDocs(shipmentId) {
    var paneel = document.getElementById("docs-" + shipmentId);
    var wordtGeopend = paneel.style.display === "none";
    paneel.style.display = wordtGeopend ? "block" : "none";
    if (wordtGeopend) laadShipmentDocs(shipmentId);
}
async function laadShipmentDocs(shipmentId) {
    var lijstDiv = document.getElementById("docslijst-" + shipmentId);
    try {
        const res = await fetch("/api/documenten?bedrijf=" + encodeURIComponent(shipmentId));
        const docs = await res.json();
        if (!docs.length) { lijstDiv.innerHTML = "Nog geen documenten geüpload."; return; }
        lijstDiv.innerHTML = docs.map(function(d) {
            return '<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;">' +
                '<a href="/documenten_uploads/' + encodeURIComponent(d.bestandsnaam) + '" target="_blank" style="color:var(--brand-600);text-decoration:none;">' + d.originele_naam + '</a>' +
                '<span style="font-size:11px;color:var(--gray-300);">' + d.timestamp + ' · ' + d.geupload_door + '</span></div>';
        }).join("");
    } catch (e) { lijstDiv.innerHTML = "Kon documenten niet laden."; }
}
async function uploadShipmentDoc(shipmentId) {
    var input = document.getElementById("docupload-" + shipmentId);
    if (!input.files.length) { alert("Kies eerst een bestand."); return; }
    var form = new FormData();
    form.append("bedrijf", shipmentId);
    form.append("document", input.files[0]);
    const res = await fetch("/api/documenten", {method: "POST", body: form});
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    input.value = "";
    laadShipmentDocs(shipmentId);
}
</script>
{% else %}
<div class="lege-staat">{% if vooringevuld_bedrijf %}Geen shipments gevonden voor {{ vooringevuld_bedrijf }}.{% else %}Geen shipments gevonden voor deze filters.{% endif %}</div>
{% endif %}
    """
    pagina = render_simple_page("Logistiek", "logistiek", inhoud)
    return render_template_string(pagina,
        vooringevuld_bedrijf=vooringevuld_bedrijf,
        getoonde_shipments_log=getoonde_shipments_log, actieve_shipments_log=actieve_shipments_log,
        filter_flow_type=filter_flow_type, filter_status_log=filter_status_log, filter_materiaal_log=filter_materiaal_log,
        shipment_statussen=SHIPMENT_STATUSSEN, shipment_materialen_log=shipment_materialen_log,
        kpi_ritten_vandaag=kpi_ritten_vandaag, kpi_actieve_ritten=kpi_actieve_ritten,
        kpi_te_laden_containers=kpi_te_laden_containers, kpi_recente_wegingen=kpi_recente_wegingen,
        kpi_totale_kosten=kpi_totale_kosten, kpi_kosten_aantal=kpi_kosten_aantal)

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

    leverancier_namen_cont = sorted({b["naam"] for b in ENF_BEDRIJVEN})
    fabriek_namen_cont = sorted({b["naam"] for b in PAPIERFABRIEKEN})
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

@app.route("/facturen", methods=["GET", "POST"])
def facturen_pagina():
    _guard = vereist_afdeling_of_403("facturen")
    if _guard: return _guard
    if request.method == "POST":
        actie = request.form.get("actie", "")
        alle_facturen = laad_facturen()
        if actie == "toevoegen":
            nieuwe_factuur = {
                "id": str(uuid.uuid4()),
                "bedrijf": request.form.get("bedrijf", "").strip(),
                "referentie": request.form.get("referentie", "").strip(),
                "omschrijving": request.form.get("omschrijving", "").strip(),
                "bedrag": request.form.get("bedrag", "").strip(),
                "btw_percentage": request.form.get("btw_percentage", "").strip(),
                "factuurdatum": request.form.get("factuurdatum", "").strip(),
                "vervaldatum": request.form.get("vervaldatum", "").strip(),
                "betaalddatum": "",
                "gebruiker": session.get("gebruikersnaam", ""),
                "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
            }
            if nieuwe_factuur["bedrijf"] and nieuwe_factuur["bedrag"] and nieuwe_factuur["vervaldatum"]:
                alle_facturen.append(nieuwe_factuur)
                bewaar_facturen(alle_facturen)
        elif actie == "markeer_betaald":
            factuur_id = request.form.get("factuur_id", "")
            for f in alle_facturen:
                if f.get("id") == factuur_id:
                    f["betaalddatum"] = datetime.date.today().isoformat()
            bewaar_facturen(alle_facturen)
        elif actie == "verwijderen":
            factuur_id = request.form.get("factuur_id", "")
            alle_facturen = [f for f in alle_facturen if f.get("id") != factuur_id]
            bewaar_facturen(alle_facturen)
        return redirect(url_for("facturen_pagina", **{k: v for k, v in request.args.items()}))

    vooringevuld_bedrijf = request.args.get("bedrijf", "")
    filter_status_fact = request.args.get("filter_status", "")

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
<div class="page-title">Facturen</div>
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
    {% if vooringevuld_bedrijf %}<input type="hidden" name="bedrijf" value="{{ vooringevuld_bedrijf }}">{% endif %}
    <select name="filter_status" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle statussen</option>
        <option value="Open" {% if filter_status_fact == "Open" %}selected{% endif %}>Open</option>
        <option value="Te laat" {% if filter_status_fact == "Te laat" %}selected{% endif %}>Te laat</option>
        <option value="Betaald" {% if filter_status_fact == "Betaald" %}selected{% endif %}>Betaald</option>
    </select>
    {% if vooringevuld_bedrijf %}<a href="/facturen" style="font-size:12px;color:var(--gray-400);text-decoration:none;">Alle bedrijven tonen</a>{% endif %}
    <span style="font-size:12px;color:var(--gray-400);margin-left:auto;">{{ getoonde_facturen|length }} van {{ alle_facturen|length }}</span>
</form>

<div style="background:#fff;border:1px solid var(--gray-200);border-radius:10px;padding:16px 18px;max-width:600px;margin-bottom:20px;">
    <div class="dg-kaart-titel" style="margin-bottom:10px;">Factuur toevoegen</div>
    <form method="POST">
        <input type="hidden" name="actie" value="toevoegen">
        <input type="text" name="bedrijf" placeholder="Bedrijfsnaam" value="{{ vooringevuld_bedrijf }}" list="bedrijvenLijstFacturen" required style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-bottom:10px;box-sizing:border-box;">
        <datalist id="bedrijvenLijstFacturen">{% for naam in alle_bedrijfsnamen_fact %}<option value="{{ naam }}">{% endfor %}</datalist>
        <input type="text" name="referentie" placeholder="Referentie / omschrijving" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-bottom:10px;box-sizing:border-box;">
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:10px;">
            <input type="text" name="bedrag" placeholder="Bedrag (€)" required style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
            <select name="btw_percentage" style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
                <option value="">BTW %</option>
                <option value="0">0%</option>
                <option value="9">9%</option>
                <option value="21">21%</option>
            </select>
            <input type="date" name="factuurdatum" title="Factuurdatum" style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
            <input type="date" name="vervaldatum" title="Vervaldatum" required style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
        </div>
        <button type="submit" style="margin-top:10px;padding:8px 16px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-weight:600;cursor:pointer;font-size:13px;">+ Factuur toevoegen</button>
    </form>
</div>

{% if getoonde_facturen %}
<div style="border:1px solid var(--gray-200);border-radius:var(--radius-md);overflow:hidden;">
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
        <span style="flex:1.2;color:var(--gray-600);">{{ f.referentie|default('—', true) }}</span>
        <span style="width:100px;text-align:right;font-family:var(--font-mono);">€{{ f.bedrag }}</span>
        <span style="width:100px;color:var(--gray-500);">{{ f.vervaldatum }}</span>
        <span style="width:100px;">
            <span class="fact-badge" style="background:{{ '#f0fdf4' if f.status=='Betaald' else ('#fef2f2' if f.status=='Te laat' else '#eff6ff') }};color:{{ '#16a34a' if f.status=='Betaald' else ('#dc2626' if f.status=='Te laat' else '#1d4ed8') }};">{{ f.status }}</span>
        </span>
        <span style="width:140px;text-align:right;display:flex;justify-content:flex-end;gap:6px;">
            {% if f.status != "Betaald" %}
            <form method="POST" style="margin:0;"><input type="hidden" name="actie" value="markeer_betaald"><input type="hidden" name="factuur_id" value="{{ f.id }}">
                <button type="submit" style="background:#f0fdf4;color:#16a34a;border:none;border-radius:5px;padding:4px 8px;cursor:pointer;font-size:11px;font-weight:700;">✓ Betaald</button>
            </form>
            {% endif %}
            <form method="POST" style="margin:0;" onsubmit="return confirm('Factuur verwijderen?');"><input type="hidden" name="actie" value="verwijderen"><input type="hidden" name="factuur_id" value="{{ f.id }}">
                <button type="submit" style="background:none;border:none;color:var(--gray-300);cursor:pointer;font-size:0.95rem;">✕</button>
            </form>
        </span>
    </div>
    {% endfor %}
</div>
{% else %}
<div class="lege-staat">{% if vooringevuld_bedrijf %}Nog geen facturen voor {{ vooringevuld_bedrijf }}.{% else %}Nog geen facturen toegevoegd.{% endif %}</div>
{% endif %}
    """
    pagina = render_simple_page("Facturen", "facturen", inhoud)
    return render_template_string(pagina,
        vooringevuld_bedrijf=vooringevuld_bedrijf, filter_status_fact=filter_status_fact,
        alle_facturen=alle_facturen, getoonde_facturen=getoonde_facturen,
        openstaande_facturen=openstaande_facturen, te_laat_facturen=te_laat_facturen,
        totaal_openstaand=totaal_openstaand, alle_bedrijfsnamen_fact=alle_bedrijfsnamen_fact,
        aantal_klaar_voor_finance=sum(1 for o in laad_logistieke_orders() if o.get("status") == "Klaar voor Finance"),
        te_verwerken_betalingen=te_verwerken_betalingen, facturen_zonder_btw=facturen_zonder_btw,
        facturen_ongebruikelijk_btw=facturen_ongebruikelijk_btw, btw_deadline=btw_deadline,
        btw_deadline_dagen=btw_deadline_dagen)

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



import secrets
import string

def genereer_wachtwoord():
    tekens = string.ascii_letters + string.digits
    return "".join(secrets.choice(tekens) for _ in range(10))

@app.route("/inzichten/financieel")
def financiele_inzichten():
    """Financiële Inzichten — alleen met echt berekenbare data. Bewust NIET gebouwd:
    'Claims' en 'Credit notes' (geen datamodel hiervoor aanwezig), en 'Winst komende
    30 dagen' (zelfde marge-datagat als bij Commerciële Inzichten — geen gekoppelde
    inkoopprijs). Voor 'contractwaarde vs. werkelijke waarde' bestaat alleen een
    contractVOLUME-veld (geen contractprijs), dus dat is hier volume, geen euro's."""
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

    # --- Contractvolume vs. werkelijk geleverd volume (LET OP: volume, geen waarde — zie docstring) ---
    alle_contracten = laad_contracten()
    alle_shipments = laad_shipments()
    contract_vergelijking = []
    for c in alle_contracten:
        try:
            contract_vol = float(str(c.get("contract_volume","0")).replace(",",""))
        except (ValueError, TypeError):
            contract_vol = 0
        werkelijk_vol = sum(
            parse_hoeveelheid_getal(s.get("werkelijk_hoeveelheid","")) for s in alle_shipments
            if s.get("materiaal","") == c.get("materiaal","") and (s.get("origin_leverancier","") == c.get("tegenpartij","") or s.get("destination_naam","") == c.get("tegenpartij",""))
        )
        contract_vergelijking.append({
            "referentie": c.get("referentie",""), "tegenpartij": c.get("tegenpartij",""), "materiaal": c.get("materiaal",""),
            "contract_volume": round(contract_vol,1), "werkelijk_volume": round(werkelijk_vol,1),
            "verschil": round(werkelijk_vol - contract_vol, 1),
        })

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
    <div class="fi-kop">Contractvolume vs. werkelijk geleverd volume <span style="font-weight:400;color:var(--gray-400);">(volume, geen euro's — contracten hebben geen prijsveld)</span></div>
    {% for c in contract_vergelijking %}
    <div class="fi-rij">
        <span style="flex:1;color:var(--gray-700);">{{ c.referentie }} — {{ c.tegenpartij }} ({{ c.materiaal }})</span>
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
                    "wachtwoord": generate_password_hash(nieuw_wachtwoord), "team": team, "is_admin": is_admin_nieuw,
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
            users = laad_users()
            if doelnaam in users:
                if nieuwe_afdeling in AFDELINGEN or nieuwe_afdeling == "":
                    users[doelnaam]["afdeling"] = nieuwe_afdeling
                if nieuwe_rol in ROLLEN:
                    users[doelnaam]["rol"] = nieuwe_rol
                bewaar_users(users)
                bericht = f"Afdeling/rol van '{doelnaam}' bijgewerkt."

    users = laad_users()
    inhoud = """
    <div class="page-title">Gebruikers beheren</div>
    {% if bericht %}<div style="background:{{ '#f0fdf4' if nieuw_wachtwoord or 'verwijderd' in bericht or 'nu' in bericht else '#fef2f2' }};color:{{ '#16a34a' if nieuw_wachtwoord or 'verwijderd' in bericht or 'nu' in bericht else '#dc2626' }};padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:14px;">{{ bericht }}
        {% if nieuw_wachtwoord %}<br><b>Wachtwoord: <code style="background:#fff;padding:3px 8px;border-radius:4px;">{{ nieuw_wachtwoord }}</code></b><br><span style="font-size:12px;">Bewaar dit nu — dit wordt niet nogmaals getoond. Geef het handmatig door aan de gebruiker.</span>{% endif %}
    </div>{% endif %}

    <div class="info-kaart" style="max-width:420px;margin-bottom:20px;">
        <div class="dg-kaart-titel">Nieuwe gebruiker toevoegen</div>
        <form method="POST">
            <input type="hidden" name="actie" value="toevoegen">
            <input type="text" name="gebruikersnaam" placeholder="Gebruikersnaam (bv. leander)" required style="width:100%;padding:8px 10px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;margin-bottom:10px;box-sizing:border-box;font-family:inherit;">
            <input type="text" name="team" placeholder="Team (bv. papier-nl)" style="width:100%;padding:8px 10px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;margin-bottom:10px;box-sizing:border-box;font-family:inherit;">
            <select name="afdeling" style="width:100%;padding:8px 10px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;margin-bottom:10px;box-sizing:border-box;font-family:inherit;">
                <option value="">Geen afdeling</option>
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
            <form method="POST" style="display:flex;gap:6px;margin-top:6px;">
                <input type="hidden" name="actie" value="wijzig_afdeling_rol">
                <input type="hidden" name="gebruikersnaam" value="{{ naam }}">
                <select name="afdeling" onchange="this.form.submit()" style="font-size:11px;padding:3px 6px;border:1px solid var(--gray-200);border-radius:5px;">
                    <option value="">Geen afdeling</option>
                    {% for a in afdelingen %}<option value="{{ a }}" {% if info.get("afdeling") == a %}selected{% endif %}>{{ afdeling_labels[a] }}</option>{% endfor %}
                </select>
                <select name="rol" onchange="this.form.submit()" style="font-size:11px;padding:3px 6px;border:1px solid var(--gray-200);border-radius:5px;">
                    {% for r in rollen %}<option value="{{ r }}" {% if info.get("rol") == r %}selected{% endif %}>{{ rol_labels[r] }}</option>{% endfor %}
                </select>
            </form>
        </div>
        {% endfor %}
    </div>
    """
    pagina = render_simple_page("Gebruikers beheren", "instellingen", inhoud)
    return render_template_string(pagina, users=users, bericht=bericht, nieuw_wachtwoord=nieuw_wachtwoord,
                                    afdelingen=AFDELINGEN, afdeling_labels=AFDELING_LABELS, rollen=ROLLEN, rol_labels=ROL_LABELS)

@app.route("/instellingen")
def instellingen():
    _guard = vereist_afdeling_of_403("instellingen")
    if _guard: return _guard
    inhoud = """
    <div class="page-title">Instellingen</div>
    <div class="info-kaart" style="max-width:400px;margin-bottom:16px;">
        <div class="drawer-row"><span class="drawer-row-label">Ingelogd als</span><span class="drawer-row-value">{{ gebruikersnaam }}</span></div>
        <div class="drawer-row"><span class="drawer-row-label">Team</span><span class="drawer-row-value">{{ team or "—" }}</span></div>
        <hr class="drawer-divider">
        <a href="/logout" class="btn-nav btn-nav-primary" style="display:inline-block;">Uitloggen</a>
    </div>
    {% if is_admin %}
    <div class="info-kaart" style="max-width:400px;">
        <div class="dg-kaart-titel">Beheer <span style="font-size:10px;font-weight:700;color:var(--gray-400);background:var(--gray-100);padding:2px 6px;border-radius:4px;">ADMIN</span></div>
        <a href="/importeer" style="display:block;margin-bottom:8px;color:var(--brand-600);font-weight:600;text-decoration:none;">→ Excel-import</a>
        <a href="/importeer-osm" style="display:block;margin-bottom:8px;color:var(--brand-600);font-weight:600;text-decoration:none;">→ OpenStreetMap-import</a>
        <a href="/opschonen-dubbelen" style="display:block;margin-bottom:8px;color:var(--brand-600);font-weight:600;text-decoration:none;">→ Dubbele bedrijven opschonen</a>
        <a href="/herlabel-brontype" style="display:block;margin-bottom:8px;color:var(--brand-600);font-weight:600;text-decoration:none;">→ Bedrijfstypes aanvullen</a>
        <a href="/importeer-scrapmonster" style="display:block;margin-bottom:8px;color:var(--brand-600);font-weight:600;text-decoration:none;">→ ScrapMonster-import (schroothandels)</a>
        <a href="/importeer-gov-uk" style="display:block;margin-bottom:8px;color:var(--brand-600);font-weight:600;text-decoration:none;">→ UK overheidsregister-import</a>
        <a href="/controleer-uk-status" style="display:block;margin-bottom:8px;color:var(--brand-600);font-weight:600;text-decoration:none;">→ UK-bedrijven controleren (Companies House)</a>
        <a href="/export-data" style="display:block;margin-bottom:8px;color:var(--brand-600);font-weight:600;text-decoration:none;">→ Live data downloaden (backup/synchroniseren)</a>
        <a href="/gebruikers-beheer" style="display:block;margin-bottom:8px;color:var(--brand-600);font-weight:600;text-decoration:none;">→ Gebruikers beheren</a>
        <a href="/materialen-beheer" style="display:block;color:var(--brand-600);font-weight:600;text-decoration:none;">→ Materialen beheren</a>
    </div>
    <div class="info-kaart" style="max-width:400px;margin-top:16px;">
        <div class="dg-kaart-titel">Bedrijfslogo (op de weegbon)</div>
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
    {% endif %}
    """
    pagina = render_simple_page("Instellingen", "instellingen", inhoud)
    return render_template_string(pagina, gebruikersnaam=session.get("gebruikersnaam",""), team=session.get("team",""),
                                    is_admin=is_huidige_gebruiker_admin(), logo_instelling=laad_bedrijfslogo_instelling(),
                                    logo_posities=LOGO_POSITIES)

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