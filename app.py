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
    TRANSPORT_DATA, vind_transport_tarieven_dichtbij, ORDER_KLEUREN, SHIPMENT_STATUSSEN,
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



HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FTNext — Global Recycling Intelligence</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<style>
.marker-cluster-small { background-color: rgba(179,217,218,0.7); }
.marker-cluster-small div { background-color: rgba(63,146,149,0.85); color: #fff; }
.marker-cluster-medium { background-color: rgba(63,146,149,0.6); }
.marker-cluster-medium div { background-color: rgba(20,118,123,0.9); color: #fff; }
.marker-cluster-large { background-color: rgba(10,74,79,0.6); }
.marker-cluster-large div { background-color: rgba(10,74,79,0.95); color: #fff; }
.marker-cluster div { font-weight: 700; font-family: 'Libre Franklin', -apple-system, sans-serif; }
</style>
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
        .tag-orange { background: var(--orange-50); color: var(--orange-600); border: 1px solid #b3d9da; }
        .tag-purple { background: #f5f3ff; color: #7c3aed; border: 1px solid #ddd6fe; }

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
        .page-title { font-size: 24px; font-weight: 600; letter-spacing: -0.025em; color: var(--gray-900); margin: 0 0 5px; }
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
    <a href="/" class="sidebar-logo"><span class="sidebar-mark">FT</span><em>Next</em></a>
    <nav class="sidebar-nav">
        <a href="/" class="sidebar-link active"><span class="icoon">ZK</span> Zoeken</a>
        <a href="/wereldkaart" class="sidebar-link"><span class="icoon">WM</span> World Map</a>
        <a href="/dashboard" class="sidebar-link"><span class="icoon">DB</span> Dashboard</a>
        <a href="/inzichten" class="sidebar-link"><span class="icoon">IZ</span> Inzichten</a>
        <a href="/materialen" class="sidebar-link"><span class="icoon">MT</span> Materials</a>
        <a href="/klanten" class="sidebar-link"><span class="icoon">KL</span> Klanten</a>
        <a href="/leveranciers" class="sidebar-link"><span class="icoon">LV</span> Leveranciers</a>
        <a href="/certificeringen" class="sidebar-link"><span class="icoon">CF</span> Certifications</a>
        <a href="/contacten" class="sidebar-link"><span class="icoon">CT</span> Contacten</a>
        <a href="/orders" class="sidebar-link" style="display:flex;align-items:center;"><span class="icoon">OR</span> Orders{% if aantal_open_orders %}<span style="background:var(--brand-600);color:#fff;font-size:10px;font-weight:700;padding:1px 6px;border-radius:9px;margin-left:auto;">{{ aantal_open_orders }}</span>{% endif %}</a>
        <a href="/logistiek" class="sidebar-link"><span class="icoon">LG</span> Logistiek</a>
        <a href="/facturen" class="sidebar-link"><span class="icoon">FA</span> Facturen</a>
        <a href="/marktprijzen" class="sidebar-link"><span class="icoon">MP</span> Marktprijzen</a>
        <a href="/voorraad" class="sidebar-link"><span class="icoon">VR</span> Voorraad</a>
        <a href="/notities-overzicht" class="sidebar-link"><span class="icoon">NT</span> Notities</a>
        <a href="/instellingen" class="sidebar-link"><span class="icoon">IN</span> Instellingen</a>
    </nav>
    <div class="sidebar-me">
        <span class="sidebar-avatar">{{ (session.get('gebruikersnaam','??')[:2])|upper }}</span>
        <div style="min-width:0;">
            <div class="sidebar-me-naam">{{ session.get('gebruikersnaam','Gast') }}</div>
            <div class="sidebar-me-rol">{{ session.get('team','') or 'Teamlid' }}</div>
        </div>
        <a class="sidebar-me-uit" href="/logout" title="Uitloggen">⏻</a>
    </div>
</aside>
<script>
function toggleMobielMenu() {
    document.getElementById("mobielSidebar").classList.toggle("open");
    document.getElementById("mobielOverlay").classList.toggle("open");
}
</script>

<div class="content-wrapper">

<!-- ZOEKBALK -->
<section class="search-bar-section">
    <div class="hero-content" style="display:flex;align-items:center;gap:14px;">
        <form method="POST" id="searchForm" style="flex:1;">
            <div class="search-container">
                <div class="search-row">
                    <input class="search-input" name="zoekterm" placeholder="Bedrijf, contactpersoon of stad..." value="{{ zoekterm }}">
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
        <button onclick="toonMeldingen()" style="background:none;border:none;cursor:pointer;font-size:13px;font-weight:600;color:var(--gray-500);white-space:nowrap;flex:none;padding:8px 4px;font-family:inherit;display:inline-flex;align-items:center;gap:5px;">
            <span style="white-space:nowrap;">Meldingen</span><span id="meldingBadge" style="display:none;background:var(--brand-600);color:#fff;font-size:11px;font-weight:700;border-radius:9px;padding:1px 7px;white-space:nowrap;"></span>
        </button>

    </div>
</section>

<!-- MAIN -->
<div class="main">

    {% if bedrijven %}
    <!-- FILTERS -->
    <form method="POST" id="filterForm" style="flex:0 0 0;width:0;margin:0;padding:0;overflow:visible;">
        <input type="hidden" name="zoekterm" value="{{ zoekterm }}">
        <input type="hidden" name="land" value="{{ land }}">
        <input type="hidden" name="regio" value="{{ regio }}">
        <aside class="filters-panel" id="filtersPaneel" style="display:none;">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3);">
                <div class="filters-title" style="margin-bottom:0;display:flex;align-items:center;gap:8px;">
                    🎚️ Filters
                    {% if actieve_filter_count > 0 %}<span style="background:var(--brand-600);color:#fff;font-size:11px;font-weight:700;padding:1px 7px;border-radius:10px;">{{ actieve_filter_count }}</span>{% endif %}
                </div>
                <div style="display:flex;align-items:center;gap:10px;">
                    {% if actieve_filter_count > 0 %}<a href="/" style="font-size:var(--text-xs);color:var(--gray-400);text-decoration:none;font-weight:600;">Wis alles</a>{% endif %}
                    <button type="button" onclick="toggleFiltersPaneel()" style="background:none;border:none;color:var(--gray-400);cursor:pointer;font-size:1.1rem;line-height:1;padding:0;">✕</button>
                </div>
            </div>

            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:var(--space-2);">Bedrijfsprofiel</div>

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

            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin:var(--space-4) 0 var(--space-2);">Materiaal</div>

            <div class="filter-group">
                <label class="filter-label">Material</label>
                <select class="filter-select" name="materiaal">
                    <option value="">All materials</option>
                    {% for cat_naam in materiaal_categorieen %}
                    <option value="{{ cat_naam }}" {% if materiaal == cat_naam %}selected{% endif %}>{{ cat_naam }}</option>
                    {% endfor %}
                </select>
            </div>

            <div class="filter-group">
                <label class="filter-label">Min. volume van dit materiaal (t/j)</label>
                <input type="number" class="filter-select" name="materiaal_min_volume" value="{{ materiaal_min_volume }}" placeholder="bv. 1000" min="0">
            </div>

            <div class="filter-group">
                <label class="filter-label">Kwaliteiten</label>
                <input type="text" class="filter-select" name="kwaliteiten" value="{{ kwaliteiten }}" placeholder="bv. OCC, HDPE...">
            </div>

            <div class="filter-group">
                <label class="filter-label">Annual Volume</label>
                <select class="filter-select" name="volume_filter">
                    <option value="">Any volume</option>
                    <option value="small" {% if volume_filter == "small" %}selected{% endif %}>Under 1,000 t/y</option>
                    <option value="medium" {% if volume_filter == "medium" %}selected{% endif %}>1,000 – 10,000 t/y</option>
                    <option value="large" {% if volume_filter == "large" %}selected{% endif %}>Over 10,000 t/y</option>
                </select>
            </div>

            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin:var(--space-4) 0 var(--space-2);">Team</div>

            <div class="filter-group">
                <label class="filter-label">Accountmanager</label>
                <select class="filter-select" name="accountmanager">
                    <option value="">Alle bedrijven</option>
                    <option value="__mij__" {% if accountmanager == "__mij__" %}selected{% endif %}>🙋 Alleen mijn bedrijven</option>
                    {% for gebruikersnaam in alle_gebruikersnamen %}
                    <option value="{{ gebruikersnaam }}" {% if accountmanager == gebruikersnaam %}selected{% endif %}>{{ gebruikersnaam }}</option>
                    {% endfor %}
                </select>
            </div>

            <hr class="filter-divider">
            <button type="submit" class="btn-apply">Filters toepassen</button>
        </aside>
    </form>

    <!-- RESULTS -->
    <div class="results-panel">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px;flex-wrap:wrap;gap:12px;padding-left:20px;">
            <div>
                <div style="font-size:28px;font-weight:600;letter-spacing:-0.02em;color:var(--gray-900);">
                    {% if materiaal %}{{ materiaal }}bedrijven{% if land %} in {{ land }}{% endif %}{% elif land %}Bedrijven in {{ land }}{% else %}Alle bedrijven{% endif %}
                </div>
            </div>
            <div style="display:flex;gap:22px;">
                <div><div style="font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Resultaten</div><div style="font-size:28px;font-weight:700;color:var(--gray-800);font-family:var(--font-mono);">{{ totaal_gevonden }}</div></div>
                <div><div style="font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Landen</div><div style="font-size:28px;font-weight:700;color:var(--gray-800);font-family:var(--font-mono);">{{ landen_in_resultaat }}</div></div>
                {% if volume_totaal_resultaat %}<div><div style="font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Volume</div><div style="font-size:28px;font-weight:700;color:var(--gray-800);font-family:var(--font-mono);">{{ volume_totaal_resultaat }}</div></div>{% endif %}
            </div>
        </div>

        <div style="display:flex;flex-wrap:wrap;align-items:center;gap:7px;margin-bottom:14px;">
            {% for af in actieve_filters_lijst %}
            <a href="{{ af.url }}" style="display:inline-flex;align-items:center;gap:5px;background:var(--brand-600);color:#fff;border-radius:14px;padding:4px 11px;font-size:12px;font-weight:600;text-decoration:none;">
                {{ af.label }}<span style="font-weight:800;opacity:0.8;">✕</span>
            </a>
            {% endfor %}
            <button type="button" onclick="toggleFiltersPaneel()" style="font-size:12px;font-weight:600;color:var(--gray-500);background:#fff;border:1px solid var(--gray-200);border-radius:14px;padding:4px 11px;cursor:pointer;font-family:inherit;">+ filter</button>
            {% if actieve_filters_lijst %}<a href="/" style="font-size:12px;color:var(--gray-300);text-decoration:none;margin-left:4px;">Wis alles</a>{% endif %}
        </div>
        <!-- MAP + TABEL: één doorlopend blok -->
        <div class="kaart-tabel-blok">
            <div class="map-panel" style="position:relative;">
                <div id="kaart"></div>
                {% if legenda_tellingen.recyclingcentrum or legenda_tellingen.inzamelaar or legenda_tellingen.papierfabriek %}
                <div style="position:absolute;left:12px;bottom:12px;z-index:400;background:#fff;border:1px solid var(--gray-200);border-radius:8px;padding:8px 14px;display:flex;gap:16px;align-items:center;box-shadow:var(--shadow-sm);font-size:12px;">
                    {% if legenda_tellingen.recyclingcentrum %}<span style="display:flex;align-items:center;gap:6px;"><span style="width:9px;height:9px;border-radius:50%;background:#0d5c62;display:inline-block;"></span>Recyclingcentra <b>{{ legenda_tellingen.recyclingcentrum }}</b></span>{% endif %}
                    {% if legenda_tellingen.inzamelaar %}<span style="display:flex;align-items:center;gap:6px;"><span style="width:9px;height:9px;border-radius:50%;background:#3f9295;display:inline-block;"></span>Inzamelaars <b>{{ legenda_tellingen.inzamelaar }}</b></span>{% endif %}
                    {% if legenda_tellingen.papierfabriek %}<span style="display:flex;align-items:center;gap:6px;"><span style="width:9px;height:9px;border-radius:50%;background:#d97706;display:inline-block;"></span>Papierfabrieken <b>{{ legenda_tellingen.papierfabriek }}</b></span>{% endif %}
                </div>
                {% endif %}
            </div>

            <div class="results-list" id="resultatenLijst">
                <div class="data-thead">
                    <span style="width:26px;"></span>
                    <span style="flex:1.5;" data-sort="naam">Bedrijf</span>
                    <span style="flex:1;" data-sort="brontype">Bedrijfstype</span>
                <span style="flex:1.2;" data-sort="materialen">Materialen</span>
                <span style="flex:1.2;" data-sort="kwaliteiten">Kwaliteiten</span>
                <span style="flex:1;" data-sort="klanttype">Klanttype</span>
                <span style="width:90px;text-align:right;" data-sort="volume">Volume t/j</span>
                <span style="width:110px;" data-sort="accountmanager">Accountmgr.</span>
                <span style="width:90px;text-align:right;" data-sort="laatst_contact">Contact</span>
                <span style="width:28px;"></span>
            </div>
            {% for bedrijf in bedrijven %}
            <a class="data-row"
                href="#"
                data-naam="{{ bedrijf.naam|e }}" data-brontype="{{ bedrijf.brontype|default('',true)|e }}"
                data-materialen="{{ bedrijf.materialen|default('',true)|e }}" data-kwaliteiten="{{ bedrijf.kwaliteiten|default('',true)|e }}"
                data-klanttype="{{ bedrijf.klanttype|default('',true)|e }}" data-volume="{{ bedrijf.volume|default('',true)|e }}"
                data-accountmanager="{{ bedrijf.accountmanager|default('',true)|e }}"
                data-laatst_contact="{{ bedrijf.laatst_contact|default('',true)|e }}"
                data-lat="{{ bedrijf.lat or '' }}" data-lon="{{ bedrijf.lon or '' }}"
                onclick="event.preventDefault(); openDrawer('{{ bedrijf.naam|replace("'","&#39;") }}', '{{ bedrijf.regio }}', '{{ bedrijf.land }}', '{{ bedrijf.url }}', '{{ bedrijf.klanttype }}', '{{ bedrijf.materialen }}', '{{ bedrijf.volume }}', {{ bedrijf.lat }}, {{ bedrijf.lon }}, '{{ bedrijf.adres|default("", true)|replace("'","&#39;") }}', '{{ bedrijf.telefoon|default("", true) }}', '{{ bedrijf.certificeringen|default("", true)|replace("'","&#39;") }}', '{{ bedrijf.contactpersoon|default("", true)|replace("'","&#39;") }}', '{{ bedrijf.kwaliteiten|default("", true)|replace("'","&#39;") }}', '{{ bedrijf.brontype|default("", true)|replace("'","&#39;") }}')">
                <span style="width:26px;"><span class="star-btn {% if bedrijf.naam in opgeslagen_namen %}opgeslagen{% endif %}" onclick="event.stopPropagation(); toggleOpslaan(event, '{{ bedrijf.naam|replace("'","\\'") }}', this)">{% if bedrijf.naam in opgeslagen_namen %}★{% else %}☆{% endif %}</span></span>
                <span style="flex:1.5;font-weight:600;color:var(--gray-800);">{{ bedrijf.naam }}{% if bedrijf.adres or bedrijf.telefoon %} <span class="verificatie-badge" style="font-size:0.6rem;">✓</span>{% endif %}<br><span style="font-weight:400;font-size:11px;color:var(--gray-400);">{{ bedrijf.regio }}, {{ bedrijf.land }}</span></span>
                <span style="flex:1;" class="zacht">{{ bedrijf.brontype|default('—',true) }}</span>
                <span style="flex:1.2;" class="zacht">{{ bedrijf.materialen|default('—',true) }}</span>
                <span style="flex:1.2;" class="zacht">{{ bedrijf.kwaliteiten|default('—',true) }}</span>
                <span style="flex:1;" class="zacht">{{ bedrijf.klanttype|default('—',true) }}</span>
                <span style="width:90px;text-align:right;" class="num">{{ bedrijf.volume|default('—',true) }}</span>
                <span style="width:110px;" class="zacht">{{ bedrijf.accountmanager|default('—',true) }}</span>
                <span style="width:90px;text-align:right;font-size:11px;" class="zacht">{{ bedrijf.laatst_contact|default('—',true) }}</span>
                <span style="width:28px;text-align:center;color:var(--gray-300);">›</span>
            </a>
            {% endfor %}
        </div>
        <div class="results-header">
            <div class="results-count">
                <strong id="inBeeldTeller">{{ bedrijven|length }}</strong> bedrijven in kaartbeeld · <strong>{{ bedrijven|length }}</strong> van <strong>{{ totaal_gevonden }}</strong>
                {% if totaal_paginas > 1 %}<span style="color:var(--gray-300);"> · pagina {{ pagina }}/{{ totaal_paginas }}</span>{% endif %}
                <span style="color:var(--gray-300);font-size:11px;"> · zoom of sleep de kaart om te filteren</span>
            </div>
            <a href="/export-csv?{{ export_query }}" style="font-size:12px;font-weight:600;color:var(--brand-600);text-decoration:none;">⬇ Export to CSV</a>
        </div>
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
    <div style="margin-bottom:10px;padding-bottom:10px;border-bottom:1px solid #f1f5f9;">
        <label style="font-size:11px;color:#94a3b8;display:block;margin-bottom:4px;">Kwaliteiten die deze fabriek aanneemt</label>
        <input type="text" id="fabriekKwaliteitenInput" placeholder="bv. OCC, Mixed Paper..." onblur="wijzigFabriekKwaliteiten()" style="width:100%;padding:6px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
    </div>
    <div id="fabriekAnalyseLijst"></div>
</div>
<div id="meldingenPaneel" style="display:none;position:fixed;top:60px;right:20px;width:340px;max-height:400px;overflow-y:auto;background:white;border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,0.15);z-index:9998;padding:12px;">
    <div style="font-weight:700;margin-bottom:8px;">Meldingen</div>
    <div id="meldingenLijst"></div>
    <a href="/meldingen-overzicht" style="display:block;text-align:center;margin-top:10px;font-size:12px;color:var(--brand-600);text-decoration:none;font-weight:600;">Alle meldingen bekijken →</a>
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

function toggleFiltersPaneel() {
    var paneel = document.getElementById("filtersPaneel");
    var isOpen = paneel.style.display === "block";
    if (isOpen) {
        paneel.style.display = "none";
        return;
    }
    var knop = event.currentTarget;
    var rect = knop.getBoundingClientRect();
    paneel.style.position = "fixed";
    paneel.style.top = (rect.bottom + 8) + "px";
    paneel.style.left = rect.left + "px";
    paneel.style.zIndex = "9999";
    paneel.style.display = "block";
}
document.addEventListener("click", function(e) {
    var paneel = document.getElementById("filtersPaneel");
    if (!paneel || paneel.style.display === "none") return;
    if (paneel.contains(e.target)) return;
    if (e.target.closest && e.target.closest("[onclick='toggleFiltersPaneel()']")) return;
    paneel.style.display = "none";
});

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
var kaartCategorieKleuren = {"recyclingcentrum": "#0d5c62", "inzamelaar": "#3f9295", "papierfabriek": "#d97706", "overig": "#94a3b8"};
{% for b in bedrijven %}
L.marker([{{ b.lat }}, {{ b.lon }}], {icon: L.divIcon({
    html: '<div style="width:16px;height:16px;border-radius:50%;background:' + kaartCategorieKleuren["{{ b.kaart_categorie }}"] + ';border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,0.35);"></div>',
    className: '', iconSize: [16,16], iconAnchor: [8,8]
})})
    .bindPopup("<b>{{ b.naam|replace('"','') }}</b><br><small>{{ b.regio }}, {{ b.land }}</small>")
    .on("click", function(){ openDrawer("{{ b.naam|replace("'","&#39;") }}","{{ b.regio }}","{{ b.land }}","{{ b.url }}","{{ b.klanttype }}","{{ b.materialen }}","{{ b.volume }}",{{ b.lat }},{{ b.lon }},"{{ b.adres|default('', true)|replace("'","&#39;") }}","{{ b.telefoon|default('', true) }}","{{ b.certificeringen|default('', true)|replace("'","&#39;") }}","{{ b.contactpersoon|default('', true)|replace("'","&#39;") }}","{{ b.kwaliteiten|default('', true)|replace("'","&#39;") }}","{{ b.brontype|default('', true)|replace("'","&#39;") }}"); })
    .addTo(clusterGroep);
{% endfor %}
kaart.addLayer(clusterGroep);
var fabriekIcon = L.divIcon({
    html: '<div style="background:#0d5c62;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:16px;box-shadow:0 2px 8px rgba(0,0,0,0.3);border:2px solid white;">🏭</div>',
    className: '',
    iconSize: [32, 32],
    iconAnchor: [16, 16]
});
{% for f in papierfabrieken %}{% if f.lat and f.lon %}
L.marker([{{ f.lat }}, {{ f.lon }}], {icon: fabriekIcon})
    .addTo(kaart)
.bindPopup('<b>🏭 {{ f.naam }}</b><br><small>{{ f.stad }}, {{ f.land }}</small><br><small>{{ f.materialen }}</small><br><a href="/bedrijf/{{ f.naam|urlencode }}" style="display:inline-block;margin-top:6px;padding:4px 10px;background:#0d5c62;color:white;border-radius:6px;font-size:12px;text-decoration:none;">Bekijk profiel →</a> <button data-fabriek="{{ f.naam }}" onclick="toonFabriekAnalyse(this.dataset.fabriek)" style="margin-top:6px;padding:4px 10px;background:#fff;color:#0d5c62;border:1px solid #0d5c62;border-radius:6px;cursor:pointer;font-size:12px;">Toon leveranciers</button>');
{% endif %}{% endfor %}

// Kaart↔tabel-koppeling: zoomen/slepen van de kaart filtert live welke rijen zichtbaar zijn
var kaartTabelRijen = Array.prototype.slice.call(document.querySelectorAll("#resultatenLijst .data-row"));
function syncKaartMetTabel() {
    var bounds = kaart.getBounds();
    var teller = 0;
    kaartTabelRijen.forEach(function (rij) {
        var lat = parseFloat(rij.dataset.lat), lon = parseFloat(rij.dataset.lon);
        if (isNaN(lat) || isNaN(lon)) { rij.style.display = "none"; return; }
        var zichtbaar = bounds.contains([lat, lon]);
        rij.style.display = zichtbaar ? "" : "none";
        if (zichtbaar) teller++;
    });
    var tellerEl = document.getElementById("inBeeldTeller");
    if (tellerEl) tellerEl.textContent = teller;
}
kaart.on("moveend zoomend", syncKaartMetTabel);
kaart.whenReady(function () { setTimeout(syncKaartMetTabel, 300); });
{% endif %}

(function () {
    var lijst = document.getElementById("resultatenLijst");
    if (!lijst) return;
    var koppen = lijst.querySelectorAll(".data-thead [data-sort]");
    var richting = "desc", sleutel = null;
    var getal = function (v) { return parseFloat((v || "").replace(/[^\d,.-]/g, "").replace(/\./g, "").replace(",", ".")) || 0; };

    koppen.forEach(function (kop) {
        kop.addEventListener("click", function () {
            var k = kop.dataset.sort;
            richting = (sleutel === k && richting === "desc") ? "asc" : "desc";
            sleutel = k;
            koppen.forEach(function (x) { x.textContent = x.textContent.replace(/ [\u2191\u2193]$/, ""); });
            kop.textContent += richting === "desc" ? " \u2193" : " \u2191";

            var rijen = Array.prototype.slice.call(lijst.querySelectorAll(".data-row")).filter(function (r) { return r.dataset && r.dataset[k] !== undefined; });
            rijen.sort(function (a, b) {
                var va = a.dataset[k] || "", vb = b.dataset[k] || "";
                var numeriek = /^[\d.,\s-]+$/.test(va) && /^[\d.,\s-]+$/.test(vb) && va !== "";
                var r = numeriek ? getal(va) - getal(vb) : va.localeCompare(vb, "nl");
                return richting === "asc" ? r : -r;
            });
            rijen.forEach(function (r) { lijst.appendChild(r); });
        });
    });
})();

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
        <div class="drawer-row"><span class="drawer-row-label">Accountmanager</span><span class="drawer-row-value" id="accountmanagerWaarde">—</span></div>
        <div class="drawer-row"><span class="drawer-row-label">Customer Type</span><span class="drawer-row-value">${klanttype || "—"}</span></div>
        ${window.currentDrawerData && window.currentDrawerData.brontype ? `<div class="drawer-row"><span class="drawer-row-label">Type</span><span class="drawer-row-value">${window.currentDrawerData.brontype}</span></div>` : ""}
        <div class="drawer-row"><span class="drawer-row-label">Materials</span><span class="drawer-row-value">${materialen || "—"}</span></div>
        ${window.currentDrawerData && window.currentDrawerData.kwaliteiten ? `<div class="drawer-row"><span class="drawer-row-label">Kwaliteiten</span><span class="drawer-row-value">${window.currentDrawerData.kwaliteiten}</span></div>` : ""}
        <div class="drawer-row"><span class="drawer-row-label">Annual Volume</span><span class="drawer-row-value">${volume ? volume + " t/y" : "—"}</span></div>
        ${window.currentDrawerData && window.currentDrawerData.contactpersoon ? `<div class="drawer-row"><span class="drawer-row-label">Contactpersoon</span><span class="drawer-row-value">${window.currentDrawerData.contactpersoon}</span></div>` : ""}
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
        <div id="notitiesLijst" style="margin-bottom:14px;"></div>
        <textarea id="notitieInput" placeholder="Schrijf een notitie..." style="width:100%;min-height:56px;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-family:inherit;font-size:13px;color:var(--gray-700);resize:vertical;box-sizing:border-box;"></textarea>
        <div style="display:flex;align-items:center;gap:16px;margin-top:10px;">
            <label style="font-size:12.5px;color:var(--gray-600);display:flex;align-items:center;gap:5px;cursor:pointer;"><input type="radio" name="notitieType" value="team" checked> Team</label>
            <label style="font-size:12.5px;color:var(--gray-600);display:flex;align-items:center;gap:5px;cursor:pointer;"><input type="radio" name="notitieType" value="prive"> Privé</label>
            <button onclick="voegNotitieToe()" style="margin-left:auto;padding:6px 16px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12.5px;font-weight:600;">Toevoegen</button>
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

function openDrawer(naam, regio, land, url, klanttype, materialen, volume, lat, lon, adres, telefoon, certificeringen, contactpersoon, kwaliteiten, brontype) {
    window.currentDrawerData = {naam: naam, land: land, regio: regio, klanttype: klanttype, materialen: materialen, volume: volume, lat: lat, lon: lon, adres: adres || "", telefoon: telefoon || "", certificeringen: certificeringen || "", contactpersoon: contactpersoon || "", kwaliteiten: kwaliteiten || "", brontype: brontype || ""};
    {% if bedrijven %}kaart.flyTo([lat,lon], 12);{% endif %}
    document.getElementById("drawerName").textContent = naam;
    document.getElementById("drawerLoc").innerHTML = "📍 " + regio + ", " + land + ' · <a href="/bedrijf/' + encodeURIComponent(naam) + '" style="color:var(--brand-600);font-weight:600;text-decoration:none;">Volledig profiel →</a>';
    document.getElementById("drawerBody").innerHTML = bouwDrawerBody(klanttype, materialen, volume, `<div style="color:var(--gray-400);font-size:var(--text-sm);">⏳ Loading details...</div>`, "");
    document.getElementById("overlay").style.display = "block";
    document.getElementById("drawer").classList.add("open");
    laadNotities();
    laadTransport();
    laadStatus();
    laadAccountmanager();
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
            laadAccountmanager();
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
            const badgeAchtergrond = n.type === "team" ? "var(--brand-50)" : "var(--gray-100)";
            const badgeKleur = n.type === "team" ? "var(--brand-600)" : "var(--gray-500)";
            const badge = n.type === "team" ? "Team" : "Privé";
            html += `
                <div style="padding:10px 0;border-bottom:1px solid var(--gray-100);font-size:13px;">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
                        <div style="color:var(--gray-700);">${n.tekst}</div>
                        <button onclick="verwijderNotitieDrawer('${n.id}')" title="Verwijderen" style="background:none;border:none;color:var(--gray-300);cursor:pointer;font-size:12px;flex-shrink:0;">✕</button>
                    </div>
                    <div style="margin-top:5px;display:flex;align-items:center;gap:7px;">
                        <span style="font-size:10px;font-weight:700;padding:1px 8px;border-radius:8px;background:${badgeAchtergrond};color:${badgeKleur};">${badge}</span>
                        <span style="color:var(--gray-400);font-size:11px;">${n.timestamp}</span>
                    </div>
                </div>`;
        });
        lijstDiv.innerHTML = html;
    } catch (err) {
        lijstDiv.innerHTML = "<p style='font-size:13px;color:#ef4444;'>Kon notities niet laden.</p>";
    }
}

async function verwijderNotitieDrawer(id) {
    if (!confirm("Deze notitie verwijderen?")) return;
    const bedrijf = window.currentDrawerData.naam;
    const res = await fetch("/api/notities", {method:"DELETE", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: bedrijf, id: id})});
    const data = await res.json();
    if (data.error) { alert(data.error); } else { laadNotities(); }
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

async function laadAccountmanager() {
    const bedrijf = window.currentDrawerData.naam;
    const el = document.getElementById("accountmanagerWaarde");
    if (!el) return;
    try {
        const res = await fetch("/api/accountmanager?bedrijf=" + encodeURIComponent(bedrijf));
        const data = await res.json();
        el.textContent = data.accountmanager ? ("👤 " + data.accountmanager) : "Niet toegewezen";
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

    var knop = event.currentTarget;
    var rect = knop.getBoundingClientRect();
    paneel.style.top = (rect.bottom + 8) + "px";
    paneel.style.right = (window.innerWidth - rect.right) + "px";
    paneel.style.left = "auto";

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
    window.huidigeFabriekNaam = fabriekNaam;
    const paneel = document.getElementById("fabriekAnalysePaneel");
    const titel = document.getElementById("fabriekAnalyseTitel");
    const lijstDiv = document.getElementById("fabriekAnalyseLijst");
    paneel.style.display = "block";
    titel.innerText = "🏭 " + fabriekNaam;
    lijstDiv.innerHTML = "<p style='font-size:13px;color:#94a3b8;'>Laden...</p>";

    try {
        const kwalRes = await fetch("/api/fabriek-kwaliteiten?fabriek=" + encodeURIComponent(fabriekNaam));
        const kwalData = await kwalRes.json();
        document.getElementById("fabriekKwaliteitenInput").value = kwalData.kwaliteiten || "";

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
                        <span style="font-weight:700;color:#0d5c62;">${r.afstand_km} km</span>
                    </div>
                    ${r.gedeelde_kwaliteiten ? `<div style="margin-top:4px;"><span style="background:#dcfce7;color:#16a34a;padding:2px 8px;border-radius:4px;font-size:11px;">✓ ${r.gedeelde_kwaliteiten}</span></div>` : ""}
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

async function wijzigFabriekKwaliteiten() {
    const input = document.getElementById("fabriekKwaliteitenInput");
    if (!window.huidigeFabriekNaam) return;
    await fetch("/api/fabriek-kwaliteiten", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({fabriek: window.huidigeFabriekNaam, waarde: input.value})});
    toonFabriekAnalyse(window.huidigeFabriekNaam);
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
    accountmanager = request.args.get("accountmanager", "")
    kwaliteiten = request.args.get("kwaliteiten", "")
    volume_filter = request.args.get("volume_filter", "")
    materiaal_min_volume = request.args.get("materiaal_min_volume", "")

    bedrijven = ENF_BEDRIJVEN
    if zoekterm:  bedrijven = [b for b in bedrijven if zoekterm in b["naam"].lower() or zoekterm in b.get("contactpersoon","").lower() or zoekterm in b.get("regio","").lower()]
    if land:      bedrijven = [b for b in bedrijven if b.get("land","").strip().lower() == land.strip().lower()]
    if regio:     bedrijven = [b for b in bedrijven if b.get("regio","").strip().lower() == regio.strip().lower()]
    if klanttype: bedrijven = [b for b in bedrijven if klanttype.strip().lower() in b.get("klanttype","").lower()]
    if materiaal: bedrijven = [b for b in bedrijven if materiaal.strip().lower() in b.get("materialen","").lower()]
    if materiaal and materiaal_min_volume:
        bedrijven = [b for b in bedrijven if voldoet_aan_materiaal_min_volume(b, materiaal, materiaal_min_volume)]
    if brontype:  bedrijven = [b for b in bedrijven if b.get("brontype","").strip().lower() == brontype.strip().lower()]
    if kwaliteiten: bedrijven = [b for b in bedrijven if kwaliteiten.strip().lower() in b.get("kwaliteiten","").lower()]
    if volume_filter:
        def _volume_getal_csv(b):
            try:
                return float(str(b.get("volume","")).replace(",", "").strip())
            except (ValueError, TypeError):
                return None
        if volume_filter == "small":
            bedrijven = [b for b in bedrijven if (v := _volume_getal_csv(b)) is not None and v < 1000]
        elif volume_filter == "medium":
            bedrijven = [b for b in bedrijven if (v := _volume_getal_csv(b)) is not None and 1000 <= v <= 10000]
        elif volume_filter == "large":
            bedrijven = [b for b in bedrijven if (v := _volume_getal_csv(b)) is not None and v > 10000]
    if accountmanager:
        accountmanagers_alle = laad_accountmanagers()
        gezocht_am = session.get("gebruikersnaam", "") if accountmanager == "__mij__" else accountmanager
        bedrijven = [b for b in bedrijven if accountmanagers_alle.get(b["naam"], "") == gezocht_am]

    output = io.StringIO()
    schrijver = csv.writer(output)
    schrijver.writerow(["Naam", "Land", "Stad/Regio", "Bedrijfstype", "Materialen", "Kwaliteiten", "Klanttype", "Volume (t/jaar)",
                         "Volume per materiaal", "Adres", "Telefoonnummer", "Contactpersoon", "Accountmanager", "Certificeringen"])
    accountmanagers_export = laad_accountmanagers()
    for b in bedrijven:
        volumes_dict = b.get("materiaal_volumes", {})
        volumes_tekst = ", ".join(f"{k}: {v}" for k, v in volumes_dict.items()) if isinstance(volumes_dict, dict) else ""
        schrijver.writerow([
            b.get("naam",""), b.get("land",""), b.get("regio",""), b.get("brontype",""),
            b.get("materialen",""), b.get("kwaliteiten",""), b.get("klanttype",""), b.get("volume",""),
            volumes_tekst, b.get("adres",""), b.get("telefoon",""), b.get("contactpersoon",""),
            accountmanagers_export.get(b.get("naam",""), ""), b.get("certificeringen",""),
        ])

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=recyclefind_export.csv"}
    )

@app.route("/export-data")
def export_data():
    _guard = vereist_admin_of_403()
    if _guard: return _guard
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
    fabriek_kwaliteiten = [k.strip().lower() for k in fabriek.get("kwaliteiten", "").split(",") if k.strip()]

    resultaten = []
    for b in ENF_BEDRIJVEN:
        if "lat" not in b or "lon" not in b:
            continue
        bedrijf_materialen = [m.strip().lower() for m in b.get("materialen", "").split(",")]
        gedeeld = [m for m in fabriek_materialen if m in bedrijf_materialen]
        if not gedeeld:
            continue
        bedrijf_kwaliteiten = [k.strip().lower() for k in b.get("kwaliteiten", "").split(",") if k.strip()]
        gedeelde_kwaliteiten = [k for k in fabriek_kwaliteiten if k in bedrijf_kwaliteiten]
        afstand = bereken_afstand_km(fabriek["lat"], fabriek["lon"], b["lat"], b["lon"])
        resultaten.append({
            "naam": b["naam"],
            "land": b["land"],
            "regio": b["regio"],
            "materialen": b.get("materialen", ""),
            "gedeelde_materialen": ", ".join(gedeeld),
            "gedeelde_kwaliteiten": ", ".join(gedeelde_kwaliteiten),
            "afstand_km": round(afstand, 1)
        })

    resultaten.sort(key=lambda x: (0 if x["gedeelde_kwaliteiten"] else 1, x["afstand_km"]))
    return jsonify(resultaten[:25])
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


@app.route("/details")
def details():
    url = request.args.get("url", "")
    if not url or "enfpaper" not in url:
        return jsonify({})
    return jsonify(haal_bedrijf_details(url))

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

@app.route("/api/accountmanager", methods=["GET"])
def get_accountmanager():
    bedrijf = request.args.get("bedrijf", "")
    alle = laad_accountmanagers()
    return jsonify({"accountmanager": alle.get(bedrijf, "")})

@app.route("/api/accountmanager", methods=["POST"])
def set_accountmanager():
    data = request.get_json()
    bedrijf = data.get("bedrijf", "")
    nieuwe_am = data.get("accountmanager", "")
    if not bedrijf:
        return jsonify({"error": "Bedrijf is verplicht"}), 400
    alle = laad_accountmanagers()
    oude_am = alle.get(bedrijf, "")
    if nieuwe_am:
        alle[bedrijf] = nieuwe_am
    else:
        alle.pop(bedrijf, None)
    bewaar_accountmanagers(alle)

    huidige_gebruikersnaam = session.get("gebruikersnaam", "")
    if nieuwe_am and nieuwe_am != oude_am and nieuwe_am != huidige_gebruikersnaam:
        alle_meldingen = laad_meldingen()
        alle_meldingen.append({
            "id": str(uuid.uuid4()),
            "tekst": f"{huidige_gebruikersnaam} heeft jou toegewezen als accountmanager voor {bedrijf}.",
            "bedrijf": bedrijf, "van": huidige_gebruikersnaam,
            "voor_gebruiker": nieuwe_am, "voor_team": "",
            "gelezen": False, "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
        })
        bewaar_meldingen(alle_meldingen)

    return jsonify({"accountmanager": nieuwe_am})

BEWERKBARE_BEDRIJFSVELDEN = {"brontype", "klanttype", "materialen", "contactpersoon", "volume", "adres", "telefoon", "kwaliteiten", "certificeringen", "betalingstermijn", "bankgegevens", "vat_nummer", "email_logistiek", "email_finance", "email_sales",
                              "email_algemeen", "kvk_nummer", "postcode", "stad", "bank_naam", "begunstigde", "bank_adres", "iban_eur", "iban_usd", "iban_gbp", "swift_bic",
                              "factuur_email", "factuur_contactpersoon", "vragen_betalingen_email", "sales_facturatie_email", "overige_informatie"}

@app.route("/api/bedrijf-veld", methods=["POST"])
def set_bedrijf_veld():
    data = request.get_json()
    bedrijf_naam = data.get("bedrijf", "")
    veld = data.get("veld", "")
    waarde = data.get("waarde", "")
    if not bedrijf_naam or veld not in BEWERKBARE_BEDRIJFSVELDEN:
        return jsonify({"error": "Ongeldig bedrijf of veld"}), 400
    for b in ENF_BEDRIJVEN:
        if b["naam"] == bedrijf_naam:
            b[veld] = waarde
            bewaar_bedrijven()
            if veld == "contactpersoon" and waarde:
                sync_contactpersoon_naar_contacten(bedrijf_naam, waarde, email=b.get("email_algemeen",""), telefoon=b.get("telefoon",""), gebruiker=session.get("gebruikersnaam",""))
            return jsonify({"veld": veld, "waarde": waarde})
    for f_item in PAPIERFABRIEKEN:
        if f_item["naam"] == bedrijf_naam:
            f_item[veld] = waarde
            bewaar_papierfabrieken()
            if veld == "contactpersoon" and waarde:
                sync_contactpersoon_naar_contacten(bedrijf_naam, waarde, email=f_item.get("email_algemeen",""), telefoon=f_item.get("telefoon",""), gebruiker=session.get("gebruikersnaam",""))
            return jsonify({"veld": veld, "waarde": waarde})
    return jsonify({"error": "Bedrijf niet gevonden"}), 404

@app.route("/api/materiaal-volume", methods=["POST"])
def set_materiaal_volume():
    data = request.get_json()
    bedrijf_naam = data.get("bedrijf", "")
    materiaal = data.get("materiaal", "").strip()
    volume = data.get("volume", "").strip()
    if not bedrijf_naam or not materiaal:
        return jsonify({"error": "Bedrijf en materiaal zijn verplicht"}), 400
    for b in ENF_BEDRIJVEN:
        if b["naam"] == bedrijf_naam:
            volumes = b.get("materiaal_volumes", {})
            if not isinstance(volumes, dict):
                volumes = {}
            if volume:
                volumes[materiaal] = volume
            else:
                volumes.pop(materiaal, None)
            b["materiaal_volumes"] = volumes
            bewaar_bedrijven()
            return jsonify({"materiaal": materiaal, "volume": volume})
    for f_item in PAPIERFABRIEKEN:
        if f_item["naam"] == bedrijf_naam:
            volumes = f_item.get("materiaal_volumes", {})
            if not isinstance(volumes, dict):
                volumes = {}
            if volume:
                volumes[materiaal] = volume
            else:
                volumes.pop(materiaal, None)
            f_item["materiaal_volumes"] = volumes
            bewaar_papierfabrieken()
            return jsonify({"materiaal": materiaal, "volume": volume})
    return jsonify({"error": "Bedrijf niet gevonden"}), 404

@app.route("/api/fabriek-kwaliteiten", methods=["GET"])
def get_fabriek_kwaliteiten():
    naam = request.args.get("fabriek", "")
    fabriek = next((f for f in PAPIERFABRIEKEN if f["naam"] == naam), None)
    return jsonify({"kwaliteiten": fabriek.get("kwaliteiten", "") if fabriek else ""})

@app.route("/api/fabriek-kwaliteiten", methods=["POST"])
def set_fabriek_kwaliteiten():
    data = request.get_json()
    naam = data.get("fabriek", "")
    waarde = data.get("waarde", "")
    for f in PAPIERFABRIEKEN:
        if f["naam"] == naam:
            f["kwaliteiten"] = waarde
            bewaar_papierfabrieken()
            return jsonify({"kwaliteiten": waarde})
    return jsonify({"error": "Fabriek niet gevonden"}), 404


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

    huidige_gebruikersnaam = session.get("gebruikersnaam", "")
    toegewezen_am = laad_accountmanagers().get(bedrijf, "")
    if toegewezen_am and toegewezen_am != huidige_gebruikersnaam and nieuwe_status:
        status_labels = {"klant": "Klant", "potentie": "Potentie", "in_proces": "In Proces", "geen_interesse": "Geen Interesse"}
        alle_meldingen = laad_meldingen()
        alle_meldingen.append({
            "id": str(uuid.uuid4()),
            "tekst": f"{huidige_gebruikersnaam} heeft de status van {bedrijf} (jouw bedrijf) gewijzigd naar \"{status_labels.get(nieuwe_status, nieuwe_status)}\".",
            "bedrijf": bedrijf, "van": huidige_gebruikersnaam,
            "voor_gebruiker": toegewezen_am, "voor_team": "",
            "gelezen": False, "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
        })
        bewaar_meldingen(alle_meldingen)

    return jsonify({"status": nieuwe_status})
@app.route("/api/company-analysis", methods=["POST"])
def company_analysis():
    from ai_filter import analyseer_uitrusting

    data = request.get_json()
    resultaat = analyseer_uitrusting(data)

    return jsonify(resultaat)

PAGINA_GROOTTE = 200

@app.route("/", methods=["GET", "POST"])
def index():
    zoekterm = land = regio = klanttype = materiaal = brontype = accountmanager = kwaliteiten = volume_filter = materiaal_min_volume = ""
    pagina = 1

    if request.method == "POST":
        zoekterm = request.form.get("zoekterm", "").lower()
        land     = request.form.get("land", "")
        regio    = request.form.get("regio", "")
        klanttype = request.form.get("klanttype", "")
        materiaal = request.form.get("materiaal", "")
        brontype  = request.form.get("brontype", "")
        accountmanager = request.form.get("accountmanager", "")
        kwaliteiten = request.form.get("kwaliteiten", "")
        volume_filter = request.form.get("volume_filter", "")
        materiaal_min_volume = request.form.get("materiaal_min_volume", "")
        pagina    = request.form.get("pagina", "1")
    else:
        zoekterm = request.args.get("zoekterm", "").lower()
        land     = request.args.get("land", "")
        regio    = request.args.get("regio", "")
        klanttype = request.args.get("klanttype", "")
        materiaal = request.args.get("materiaal", "")
        brontype  = request.args.get("brontype", "")
        accountmanager = request.args.get("accountmanager", "")
        kwaliteiten = request.args.get("kwaliteiten", "")
        volume_filter = request.args.get("volume_filter", "")
        materiaal_min_volume = request.args.get("materiaal_min_volume", "")
        pagina    = request.args.get("pagina", "1")

    try:
        pagina = max(1, int(pagina))
    except (TypeError, ValueError):
        pagina = 1

    bedrijven = ENF_BEDRIJVEN
    if zoekterm:  bedrijven = [b for b in bedrijven if zoekterm in b["naam"].lower() or zoekterm in b.get("contactpersoon","").lower() or zoekterm in b.get("regio","").lower()]
    if land:      bedrijven = [b for b in bedrijven if b.get("land","").strip().lower() == land.strip().lower()]
    if regio:     bedrijven = [b for b in bedrijven if b.get("regio","").strip().lower() == regio.strip().lower()]
    if klanttype: bedrijven = [b for b in bedrijven if klanttype.strip().lower() in b.get("klanttype","").lower()]
    if materiaal: bedrijven = [b for b in bedrijven if materiaal.strip().lower() in b.get("materialen","").lower()]
    if materiaal and materiaal_min_volume:
        bedrijven = [b for b in bedrijven if voldoet_aan_materiaal_min_volume(b, materiaal, materiaal_min_volume)]
    if brontype:  bedrijven = [b for b in bedrijven if b.get("brontype","").strip().lower() == brontype.strip().lower()]
    if kwaliteiten: bedrijven = [b for b in bedrijven if kwaliteiten.strip().lower() in b.get("kwaliteiten","").lower()]
    if volume_filter:
        def _volume_getal(b):
            try:
                return float(str(b.get("volume","")).replace(",", "").strip())
            except (ValueError, TypeError):
                return None
        if volume_filter == "small":
            bedrijven = [b for b in bedrijven if (v := _volume_getal(b)) is not None and v < 1000]
        elif volume_filter == "medium":
            bedrijven = [b for b in bedrijven if (v := _volume_getal(b)) is not None and 1000 <= v <= 10000]
        elif volume_filter == "large":
            bedrijven = [b for b in bedrijven if (v := _volume_getal(b)) is not None and v > 10000]
    if accountmanager:
        accountmanagers_alle = laad_accountmanagers()
        gezocht_am = session.get("gebruikersnaam", "") if accountmanager == "__mij__" else accountmanager
        bedrijven = [b for b in bedrijven if accountmanagers_alle.get(b["naam"], "") == gezocht_am]

    totaal_gevonden = len(bedrijven)

    landen_in_resultaat = len({b.get("land","") for b in bedrijven if b.get("land")})
    _volume_som = sum(parse_hoeveelheid_getal(b.get("volume","")) for b in bedrijven)
    if _volume_som >= 1_000_000:
        volume_totaal_resultaat = f"{_volume_som/1_000_000:.1f} Mt"
    elif _volume_som >= 1000:
        volume_totaal_resultaat = f"{_volume_som/1000:.0f}k t"
    elif _volume_som > 0:
        volume_totaal_resultaat = f"{_volume_som:.0f} t"
    else:
        volume_totaal_resultaat = ""

    er_is_gefilterd = bool(zoekterm or land or regio or klanttype or materiaal or brontype or accountmanager or kwaliteiten or volume_filter)
    totaal_paginas = max(1, (totaal_gevonden + PAGINA_GROOTTE - 1) // PAGINA_GROOTTE)
    pagina = min(pagina, totaal_paginas)
    start = (pagina - 1) * PAGINA_GROOTTE
    bedrijven = bedrijven[start:start + PAGINA_GROOTTE]
    opgeslagen_namen = set(laad_opgeslagen())

    _am_lookup = laad_accountmanagers()
    _alle_notities_index = laad_notities()
    _vandaag_index = datetime.date.today()
    for b in bedrijven:
        b["accountmanager"] = _am_lookup.get(b["naam"], "")

        b["laatst_contact"] = ""
        notities_van_bedrijf = _alle_notities_index.get(b["naam"], [])
        laatste_datum = None
        for n in notities_van_bedrijf:
            try:
                dt = datetime.datetime.strptime(n.get("timestamp",""), "%d-%m-%Y %H:%M").date()
                if laatste_datum is None or dt > laatste_datum:
                    laatste_datum = dt
            except (ValueError, TypeError):
                continue
        if laatste_datum:
            dagen_geleden = (_vandaag_index - laatste_datum).days
            if dagen_geleden <= 0:
                b["laatst_contact"] = "Vandaag"
            elif dagen_geleden == 1:
                b["laatst_contact"] = "Gisteren"
            else:
                b["laatst_contact"] = f"{dagen_geleden} dagen"

    # Brontype-categorie bepalen voor kaartkleur + legenda (op basis van wat al bekend is, niks verzonnen)
    def _kaart_categorie(brontype_tekst):
        t = (brontype_tekst or "").strip().lower()
        if "papierfabriek" in t:
            return "papierfabriek"
        if "recyclingcentrum" in t:
            return "recyclingcentrum"
        if "inzamelaar" in t:
            return "inzamelaar"
        return "overig"
    for b in bedrijven:
        b["kaart_categorie"] = _kaart_categorie(b.get("brontype",""))
    _legenda_tellingen = {"recyclingcentrum": 0, "inzamelaar": 0, "papierfabriek": 0, "overig": 0}
    for b in bedrijven:
        _legenda_tellingen[b["kaart_categorie"]] += 1

    _volume_labels = {"small": "Volume: <1.000 t/j", "medium": "Volume: 1.000-10.000 t/j", "large": "Volume: >10.000 t/j"}
    _accountmanager_label = "Accountmanager: Mijn bedrijven" if accountmanager == "__mij__" else (f"Accountmanager: {accountmanager}" if accountmanager else "")
    _alle_filter_velden = [
        ("klanttype", klanttype, f"Customer Type: {klanttype}"),
        ("brontype", brontype, f"Bedrijfstype: {brontype}"),
        ("materiaal", materiaal, f"Materiaal: {materiaal}"),
        ("materiaal_min_volume", materiaal_min_volume, f"Min. volume {materiaal}: {materiaal_min_volume} t/j" if materiaal_min_volume else ""),
        ("kwaliteiten", kwaliteiten, f"Kwaliteiten: {kwaliteiten}"),
        ("volume_filter", volume_filter, _volume_labels.get(volume_filter, "")),
        ("accountmanager", accountmanager, _accountmanager_label),
    ]
    actieve_filter_count = sum(1 for _, waarde, _ in _alle_filter_velden if waarde)

    def _maak_filter_url_zonder(uit_te_sluiten_key):
        params = {"zoekterm": zoekterm, "land": land, "regio": regio, "klanttype": klanttype,
                   "materiaal": materiaal, "brontype": brontype, "accountmanager": accountmanager,
                   "kwaliteiten": kwaliteiten, "volume_filter": volume_filter, "materiaal_min_volume": materiaal_min_volume}
        params[uit_te_sluiten_key] = ""
        params = {k: v for k, v in params.items() if v}
        return "/?" + "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())

    actieve_filters_lijst = [
        {"label": label, "url": _maak_filter_url_zonder(key)}
        for key, waarde, label in _alle_filter_velden if waarde
    ]

    def maak_pagina_url(p):
        params = {"zoekterm": zoekterm, "land": land, "regio": regio, "klanttype": klanttype,
                   "materiaal": materiaal, "brontype": brontype, "accountmanager": accountmanager,
                   "kwaliteiten": kwaliteiten, "volume_filter": volume_filter, "materiaal_min_volume": materiaal_min_volume, "pagina": p}
        params = {k: v for k, v in params.items() if v}
        return "/?" + "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())

    export_params = {"zoekterm": zoekterm, "land": land, "regio": regio, "klanttype": klanttype,
                      "materiaal": materiaal, "brontype": brontype, "accountmanager": accountmanager,
                      "kwaliteiten": kwaliteiten, "volume_filter": volume_filter, "materiaal_min_volume": materiaal_min_volume}
    export_params = {k: v for k, v in export_params.items() if v}
    export_query = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in export_params.items())

    return render_template_string(HTML,
        bedrijven=bedrijven, zoekterm=zoekterm, land=land, regio=regio,
        klanttype=klanttype, materiaal=materiaal, brontype=brontype, accountmanager=accountmanager,
        kwaliteiten=kwaliteiten, volume_filter=volume_filter, materiaal_min_volume=materiaal_min_volume,
        totaal=len(ENF_BEDRIJVEN), landen=LANDEN,
        totaal_gevonden=totaal_gevonden, regio_per_land=REGIO_PER_LAND,
        landen_in_resultaat=landen_in_resultaat, volume_totaal_resultaat=volume_totaal_resultaat,
        legenda_tellingen=_legenda_tellingen,
        papierfabrieken=PAPIERFABRIEKEN, opgeslagen_namen=opgeslagen_namen,
        er_is_gefilterd=er_is_gefilterd, pagina=pagina, totaal_paginas=totaal_paginas,
        maak_pagina_url=maak_pagina_url, export_query=export_query,
        alle_gebruikersnamen=sorted(laad_users().keys()),
        actieve_filter_count=actieve_filter_count, actieve_filters_lijst=actieve_filters_lijst,
        materiaal_categorieen=sorted(laad_materiaal_taxonomie().keys()),
        aantal_open_orders=sum(1 for o in laad_orders() if o.get("status") in ("Open", "Onderhandeling")))

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

    # ---------- Ingekocht per maand (echte data: inbound shipments) ----------
    vandaag_maand = datetime.date.today().replace(day=1)
    maand_labels = []
    maand_sleutels = []
    cursor = vandaag_maand
    for _ in range(12):
        maand_sleutels.append((cursor.year, cursor.month))
        maand_labels.append(cursor.strftime("%b").lower())
        if cursor.month == 1:
            cursor = cursor.replace(year=cursor.year - 1, month=12)
        else:
            cursor = cursor.replace(month=cursor.month - 1)
    maand_sleutels.reverse()
    maand_labels.reverse()
    inkoop_per_maand = {sleutel: 0.0 for sleutel in maand_sleutels}
    alle_shipments_dash = laad_shipments()
    for s in alle_shipments_dash:
        if s.get("status") == "Cancelled" or not s.get("datum"):
            continue
        if bepaal_shipment_flow_type(s) != "inbound":
            continue
        try:
            dt = datetime.datetime.strptime(s["datum"], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        sleutel = (dt.year, dt.month)
        if sleutel in inkoop_per_maand:
            inkoop_per_maand[sleutel] += shipment_hoeveelheid(s)
    inkoop_serie = [inkoop_per_maand[s] for s in maand_sleutels]
    max_inkoop_maand = max(inkoop_serie) if any(inkoop_serie) else 1

    # ---------- Inkoop per kwaliteit (echte data: goedgekeurde inbound-transacties) ----------
    inkoop_per_kwaliteit = {}
    for t in laad_voorraad():
        if t.get("type") not in ("in", "inbound"):
            continue
        if t.get("keuringsstatus", "goedgekeurd") != "goedgekeurd":
            continue
        naam = t.get("materiaal", "")
        if not naam:
            continue
        inkoop_per_kwaliteit[naam] = inkoop_per_kwaliteit.get(naam, 0.0) + parse_hoeveelheid_getal(t.get("hoeveelheid", ""))
    inkoop_kwaliteit_lijst = sorted(inkoop_per_kwaliteit.items(), key=lambda x: -x[1])[:8]
    max_inkoop_kwaliteit = max([a for _, a in inkoop_kwaliteit_lijst], default=1) or 1

    # ---------- Orders / sales (echte data) ----------
    orders_alle_dash = laad_orders()
    verkoop_orders_dash = [o for o in orders_alle_dash if o.get("ordertype", "verkoop") != "inkoop"]
    gewonnen_verkoop_dash = [o for o in verkoop_orders_dash if o.get("status") == "Gewonnen"]
    open_of_onderhandeling_dash = [o for o in orders_alle_dash if o.get("status") in ("Open", "Onderhandeling")]

    def _prijs_getal(o):
        try:
            return float(str(o.get("prijs", "")).replace(",", "").replace("€", "").strip())
        except (ValueError, TypeError):
            return 0.0

    omzet_totaal = sum(_prijs_getal(o) for o in gewonnen_verkoop_dash)
    ton_verkocht_totaal = sum(parse_hoeveelheid_getal(o.get("hoeveelheid", "")) for o in gewonnen_verkoop_dash)
    verwachte_omzet = sum(_prijs_getal(o) for o in verkoop_orders_dash if o.get("status") in ("Open", "Onderhandeling"))
    lopende_orders_aantal = len(open_of_onderhandeling_dash)

    _vandaag_dash = datetime.date.today()
    geplande_orders_lijst = []
    for o in open_of_onderhandeling_dash:
        if not o.get("verwachte_datum"):
            continue
        try:
            d = datetime.datetime.strptime(o["verwachte_datum"], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue
        if d >= _vandaag_dash:
            geplande_orders_lijst.append(o)
    geplande_orders_aantal = len(geplande_orders_lijst)

    # Sales pipeline: verdeling van alle orders over de statussen
    pipeline_tellingen = []
    for st in ("Open", "Onderhandeling", "Gewonnen", "Verloren"):
        aantal = sum(1 for o in orders_alle_dash if o.get("status") == st)
        pipeline_tellingen.append({"status": st, "aantal": aantal})
    max_pipeline = max([p["aantal"] for p in pipeline_tellingen], default=1) or 1

    # ---------- Team-prestatie (echte data) ----------
    accountmanagers_alle_dash = laad_accountmanagers()
    _teamnamen_dash = sorted(set(laad_users().keys()) | set(accountmanagers_alle_dash.values()) | {o.get("verantwoordelijke", "") for o in orders_alle_dash if o.get("verantwoordelijke")})
    team_prestaties_dash = []
    for naam in _teamnamen_dash:
        if not naam:
            continue
        aantal_bedrijven_am = sum(1 for am in accountmanagers_alle_dash.values() if am == naam)
        orders_van_am = [o for o in orders_alle_dash if o.get("verantwoordelijke") == naam]
        waarde_am = sum(_prijs_getal(o) for o in orders_van_am if o.get("status") == "Gewonnen")
        if aantal_bedrijven_am == 0 and not orders_van_am:
            continue
        team_prestaties_dash.append({"naam": naam, "bedrijven": aantal_bedrijven_am, "orders": len(orders_van_am), "waarde": waarde_am})
    team_prestaties_dash.sort(key=lambda t: -t["waarde"])
    team_prestaties_dash = team_prestaties_dash[:6]
    max_team_waarde = max([t["waarde"] for t in team_prestaties_dash], default=1) or 1

    # ---------- Progressie met bedrijven (status-funnel, echte data) ----------
    progressie_funnel = [
        {"label": "Nieuwe leads", "aantal": len(ENF_BEDRIJVEN) - status_totaal + max(0, status_totaal - (aantal_klant + aantal_potentie + aantal_proces + aantal_geen))},
        {"label": "Potentie", "aantal": aantal_potentie},
        {"label": "In proces", "aantal": aantal_proces},
        {"label": "Klant", "aantal": aantal_klant},
    ]
    # Nieuwe leads = bedrijven zonder enige status
    progressie_funnel[0]["aantal"] = sum(1 for b in ENF_BEDRIJVEN if not status_alle.get(b["naam"]))
    max_funnel = max([f["aantal"] for f in progressie_funnel], default=1) or 1

    # ---------- Topklanten & klanten zonder recent contact (echte data) ----------
    _notities_alle_dash = laad_notities()

    def _laatste_contact_dagen(naam_bedrijf):
        notities_van = _notities_alle_dash.get(naam_bedrijf, [])
        laatste = None
        for n in notities_van:
            try:
                dt = datetime.datetime.strptime(n.get("timestamp", ""), "%d-%m-%Y %H:%M").date()
                if laatste is None or dt > laatste:
                    laatste = dt
            except (ValueError, TypeError):
                continue
        if laatste is None:
            return None
        return (_vandaag_dash - laatste).days

    klanten_dash = [b for b in ENF_BEDRIJVEN if status_alle.get(b["naam"]) == "klant"]
    topklanten = sorted(klanten_dash, key=lambda b: -parse_hoeveelheid_getal(b.get("volume", "")))[:5]
    klanten_zonder_contact = []
    for b in klanten_dash:
        dagen = _laatste_contact_dagen(b["naam"])
        if dagen is None or dagen > 30:
            klanten_zonder_contact.append({"naam": b["naam"], "dagen": dagen})
    klanten_zonder_contact.sort(key=lambda x: (x["dagen"] is not None, -(x["dagen"] or 0)))
    klanten_zonder_contact = klanten_zonder_contact[:5]

    nieuwe_leads_lijst = sorted(
        [b for b in ENF_BEDRIJVEN if not status_alle.get(b["naam"])],
        key=lambda b: -parse_hoeveelheid_getal(b.get("volume", ""))
    )[:5]

    # ---------- Marktprijzen & transportkosten (echte data, samengevat) ----------
    marktprijzen_alle = laad_marktprijzen()
    marktprijzen_recent = sorted(marktprijzen_alle, key=lambda p: p.get("datum", ""), reverse=True)[:5]

    transport_data_dash = laad_transport_data()
    aantal_forwarders = len(transport_data_dash)
    aantal_transport_steden = sum(len(v) for v in transport_data_dash.values())

    # ---------- Vraagt om aandacht ----------
    leads_zonder_am_dash = [b for b in ENF_BEDRIJVEN if not accountmanagers_alle_dash.get(b["naam"])]
    leads_zonder_am_groot = sum(1 for b in leads_zonder_am_dash if parse_hoeveelheid_getal(b.get("volume", "")) > 10000)
    bedrijven_zonder_kwaliteiten = sum(1 for b in ENF_BEDRIJVEN if b.get("materialen") and not b.get("kwaliteiten"))

    _vervaldatums_dash = laad_cert_vervaldatums()
    aantal_cert_verlopen = 0
    for b in ENF_BEDRIJVEN:
        for c in [x.strip() for x in b.get("certificeringen", "").split(",") if x.strip()]:
            geldig_tot = _vervaldatums_dash.get(_cert_sleutel(b["naam"], c), "")
            if geldig_tot:
                try:
                    if datetime.datetime.strptime(geldig_tot, "%Y-%m-%d").date() < _vandaag_dash:
                        aantal_cert_verlopen += 1
                except (ValueError, TypeError):
                    pass

    orders_verlopen = 0
    for o in open_of_onderhandeling_dash:
        if o.get("verwachte_datum"):
            try:
                if datetime.datetime.strptime(o["verwachte_datum"], "%Y-%m-%d").date() < _vandaag_dash:
                    orders_verlopen += 1
            except (ValueError, TypeError):
                pass

    aandacht_items = []
    if leads_zonder_am_dash:
        sub = f"waarvan {leads_zonder_am_groot} boven 10.000 t/j" if leads_zonder_am_groot else ""
        aandacht_items.append({"titel": f"{len(leads_zonder_am_dash)} leads zonder accountmanager", "sub": sub, "url": "/?accountmanager="})
    if bedrijven_zonder_kwaliteiten:
        aandacht_items.append({"titel": f"{bedrijven_zonder_kwaliteiten} bedrijven zonder kwaliteiten", "sub": "blokkeert matching met fabrieken", "url": "/"})
    if aantal_cert_verlopen:
        aandacht_items.append({"titel": f"{aantal_cert_verlopen} certificeringen verlopen", "sub": "controle nodig", "url": "/certificeringen"})
    if orders_verlopen:
        aandacht_items.append({"titel": f"{orders_verlopen} orders over de verwachte datum", "sub": "nog niet afgerond", "url": "/orders"})

    # ---------- Activiteit van het team ----------
    activiteit = []
    for bedrijf_naam, lijst in _notities_alle_dash.items():
        for n in lijst:
            if n.get("type") != "team":
                continue
            activiteit.append({
                "gebruiker": n.get("gebruikersnaam", "?"), "tekst": "Notitie toegevoegd", "sub": bedrijf_naam,
                "tijd_sorteer": n.get("timestamp", ""),
            })
    for m in laad_meldingen():
        if m.get("van"):
            activiteit.append({
                "gebruiker": m["van"], "tekst": m.get("tekst", "")[:60], "sub": m.get("bedrijf", ""),
                "tijd_sorteer": m.get("timestamp", ""),
            })
    activiteit.sort(key=lambda x: x["tijd_sorteer"], reverse=True)
    activiteit = activiteit[:6]

    volume_klant = 0.0
    for b in ENF_BEDRIJVEN:
        if status_alle.get(b["naam"]) == "klant":
            volume_klant += parse_hoeveelheid_getal(b.get("volume", ""))

    gebruikersnaam_dash = session.get("gebruikersnaam", "")

    # ---------- Placeholders: metrics zonder datamodel — nooit fabriceren, altijd eerlijk "—" ----------
    placeholders = [
        {"label": "Marge", "sub": "kostprijs-veld ontbreekt nog"},
        {"label": "Marge per ton", "sub": "kostprijs-veld ontbreekt nog"},
        {"label": "Target / voortgang", "sub": "geen targets ingesteld"},
        {"label": "Openstaande betalingen", "sub": "geen betaalstatus op orders"},
        {"label": "Betalingsachterstanden", "sub": "geen vervaldatum op facturen"},
        {"label": "Openstaande offertes", "sub": "geen offerte-stadium"},
        {"label": "Openstaande claims", "sub": "geen claims-model"},
        {"label": "Taken voor vandaag", "sub": "geen takenlijst"},
        {"label": "Follow-ups", "sub": "geen follow-up-systeem"},
    ]

    inhoud = """
<style>
.db-topbar { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:24px; }
.db-groet { font-size:1.5rem; font-weight:700; color:var(--gray-900); }
.db-substaat { font-size:0.82rem; color:var(--gray-400); margin-top:2px; }
.db-acties { display:flex; gap:8px; }
.db-btn { font-size:0.8rem; font-weight:600; padding:8px 16px; border-radius:6px; text-decoration:none; cursor:pointer; border:1px solid var(--gray-200); background:#fff; color:var(--gray-700); }
.db-btn-primair { background:var(--brand-600); color:#fff; border-color:var(--brand-600); }

.db-kpi-rij { display:grid; grid-template-columns:repeat(4,1fr); border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); margin-bottom:8px; }
.db-kpi { padding:18px 22px; border-right:1px solid var(--gray-200); }
.db-kpi:last-child { border-right:none; }
.db-kpi-label { font-size:0.68rem; font-weight:700; letter-spacing:0.06em; text-transform:uppercase; color:var(--gray-400); margin-bottom:8px; }
.db-kpi-getal { font-size:28px; font-weight:700; color:var(--gray-900); letter-spacing:-0.02em; }
.db-kpi-sub { font-size:0.76rem; color:var(--gray-400); margin-top:4px; }
.db-kpi-rij + .db-kpi-rij { border-top:none; margin-bottom:28px; }

.db-rij { display:flex; gap:28px; margin-bottom:28px; align-items:flex-start; }
.db-kol { flex:1; min-width:0; }
.db-sectie-titel { font-size:0.95rem; font-weight:600; color:var(--gray-900); margin-bottom:18px; display:flex; justify-content:space-between; align-items:baseline; }
.db-sectie-titel small { font-size:0.72rem; font-weight:500; color:var(--gray-400); }

.db-bars { display:flex; align-items:flex-end; gap:10px; height:150px; padding-top:8px; }
.db-bar-kol { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:flex-end; height:100%; }
.db-bar { width:100%; max-width:34px; background:var(--brand-600); border-radius:3px 3px 0 0; }
.db-bar-label { font-size:0.68rem; color:var(--gray-400); margin-top:8px; }

.db-hbar-rij { display:flex; align-items:center; gap:10px; padding:9px 0; border-bottom:1px solid var(--gray-100); font-size:0.82rem; }
.db-hbar-rij:last-child { border-bottom:none; }
.db-hbar-naam { width:120px; flex-shrink:0; color:var(--gray-700); }
.db-hbar-track { flex:1; height:7px; background:var(--gray-100); border-radius:4px; overflow:hidden; }
.db-hbar-fill { height:100%; background:var(--brand-600); border-radius:4px; }
.db-hbar-getal { width:64px; text-align:right; color:var(--gray-500); font-family:var(--font-mono); font-size:0.78rem; }

.db-att-item { display:flex; gap:10px; align-items:flex-start; padding:11px 0; border-bottom:1px solid var(--gray-100); text-decoration:none; }
.db-att-item:last-child { border-bottom:none; }
.db-att-dot { width:6px; height:6px; border-radius:50%; background:var(--brand-600); margin-top:6px; flex-shrink:0; }
.db-att-titel { font-size:0.82rem; font-weight:600; color:var(--gray-900); }
.db-att-sub { font-size:0.74rem; color:var(--gray-400); margin-top:2px; }

.db-act-item { padding:9px 0; border-bottom:1px solid var(--gray-100); font-size:0.8rem; display:flex; gap:8px; }
.db-act-item:last-child { border-bottom:none; }
.db-act-naam { font-weight:600; color:var(--gray-900); flex-shrink:0; }
.db-act-tekst { color:var(--gray-600); }
.db-act-sub { color:var(--gray-400); display:block; font-size:0.74rem; margin-top:1px; }

.db-lijst-item { padding:9px 0; border-bottom:1px solid var(--gray-100); font-size:0.82rem; display:flex; justify-content:space-between; gap:8px; text-decoration:none; color:inherit; }
.db-lijst-item:last-child { border-bottom:none; }
.db-lijst-naam { color:var(--gray-800); font-weight:600; }
.db-lijst-sub { color:var(--gray-400); font-size:0.74rem; }
.db-lijst-getal { color:var(--gray-500); font-family:var(--font-mono); font-size:0.78rem; white-space:nowrap; }

.db-leeg { color:var(--gray-400); font-size:0.82rem; padding:8px 0; }

.db-ph-titel { font-size:0.95rem; font-weight:600; color:var(--gray-900); margin-bottom:4px; }
.db-ph-sub { font-size:0.78rem; color:var(--gray-400); margin-bottom:16px; }
.db-ph-grid { display:grid; grid-template-columns:repeat(3,1fr); border-top:1px solid var(--gray-200); border-left:1px solid var(--gray-200); margin-bottom:28px; }
.db-ph-tegel { padding:16px 18px; border-right:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); }
.db-ph-tegel-label { font-size:0.72rem; font-weight:700; text-transform:uppercase; letter-spacing:0.05em; color:var(--gray-400); margin-bottom:6px; }
.db-ph-tegel-waarde { font-size:20px; font-weight:700; color:var(--gray-300); }
.db-ph-tegel-sub { font-size:0.7rem; color:var(--gray-300); margin-top:3px; }
</style>

<div class="db-topbar">
    <div>
        <div class="db-groet">Goedemorgen, {{ gebruikersnaam_dash or "daar" }}</div>
        <div class="db-substaat">Stand van zaken, week {{ huidige_week }} · bijgewerkt vanochtend {{ bijgewerkt_tijd }}</div>
    </div>
    <div class="db-acties">
        <a href="/dashboard" class="db-btn">Deze maand</a>
        <a href="/export-csv" class="db-btn db-btn-primair">Rapport delen</a>
    </div>
</div>

<div class="db-kpi-rij">
    <div class="db-kpi">
        <div class="db-kpi-label">Bedrijven in database</div>
        <div class="db-kpi-getal">{{ "{:,}".format(totaal).replace(",", ".") }}</div>
        <div class="db-kpi-sub">{% if groei_pct is not none %}{{ '+' if groei_pct >= 0 else '' }}{{ groei_pct }}% sinds {{ groei_periode }}{% else %}nog geen groeicijfer{% endif %}</div>
    </div>
    <div class="db-kpi">
        <div class="db-kpi-label">Gedekt volume</div>
        <div class="db-kpi-getal">{{ volume_totaal_label }}</div>
        <div class="db-kpi-sub">per jaar, opgegeven</div>
    </div>
    <div class="db-kpi">
        <div class="db-kpi-label">Actieve leads</div>
        <div class="db-kpi-getal">{{ status_totaal_leads }}</div>
        <div class="db-kpi-sub">{{ leads_zonder_am_dash|length }} zonder accountmanager</div>
    </div>
    <div class="db-kpi">
        <div class="db-kpi-label">Geplande orders</div>
        <div class="db-kpi-getal">{{ geplande_orders_aantal }}</div>
        <div class="db-kpi-sub">met een verwachte datum</div>
    </div>
</div>
<div class="db-kpi-rij">
    <div class="db-kpi">
        <div class="db-kpi-label">Omzet (gewonnen)</div>
        <div class="db-kpi-getal">€{{ "{:,.0f}".format(omzet_totaal).replace(",", ".") }}</div>
        <div class="db-kpi-sub">uit gewonnen verkooporders</div>
    </div>
    <div class="db-kpi">
        <div class="db-kpi-label">Ton verkocht</div>
        <div class="db-kpi-getal">{{ "{:,.0f}".format(ton_verkocht_totaal).replace(",", ".") }}</div>
        <div class="db-kpi-sub">uit gewonnen verkooporders</div>
    </div>
    <div class="db-kpi">
        <div class="db-kpi-label">Verwachte omzet</div>
        <div class="db-kpi-getal">€{{ "{:,.0f}".format(verwachte_omzet).replace(",", ".") }}</div>
        <div class="db-kpi-sub">open + onderhandeling</div>
    </div>
    <div class="db-kpi">
        <div class="db-kpi-label">Lopende orders</div>
        <div class="db-kpi-getal">{{ lopende_orders_aantal }}</div>
        <div class="db-kpi-sub">open of in onderhandeling</div>
    </div>
</div>

<div class="db-rij">
    <div class="db-kol" style="flex:1.6;">
        <div class="db-sectie-titel">Ingekocht per maand <small>ton, laatste 12 maanden</small></div>
        {% if inkoop_serie and inkoop_serie|sum > 0 %}
        <div class="db-bars">
            {% for label in maand_labels %}
            <div class="db-bar-kol">
                <div class="db-bar" style="height:{{ ((inkoop_serie[loop.index0] / max_inkoop_maand * 100)|round(1)) if max_inkoop_maand else 0 }}%;"></div>
                <div class="db-bar-label">{{ label }}</div>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="db-leeg">Nog geen inkoop-shipments om een trend te tonen.</div>
        {% endif %}
    </div>
    <div class="db-kol">
        <div class="db-sectie-titel">Sales pipeline</div>
        {% for p in pipeline_tellingen %}
        <div class="db-hbar-rij">
            <span class="db-hbar-naam">{{ p.status }}</span>
            <span class="db-hbar-track"><span class="db-hbar-fill" style="width:{{ (p.aantal/max_pipeline*100)|round(1) }}%;"></span></span>
            <span class="db-hbar-getal">{{ p.aantal }}</span>
        </div>
        {% endfor %}
    </div>
</div>

<div class="db-rij">
    <div class="db-kol">
        <div class="db-sectie-titel">Inkoop per kwaliteit <small>ton, goedgekeurd</small></div>
        {% for k in inkoop_kwaliteit_lijst %}
        <div class="db-hbar-rij">
            <span class="db-hbar-naam">{{ k[0] }}</span>
            <span class="db-hbar-track"><span class="db-hbar-fill" style="width:{{ (k[1]/max_inkoop_kwaliteit*100)|round(1) }}%;"></span></span>
            <span class="db-hbar-getal">{{ "{:,.0f}".format(k[1]).replace(",", ".") }}t</span>
        </div>
        {% else %}
        <div class="db-leeg">Nog geen goedgekeurde inkoop.</div>
        {% endfor %}
    </div>
    <div class="db-kol">
        <div class="db-sectie-titel">Team-prestatie</div>
        {% for t in team_prestaties_dash %}
        <div class="db-hbar-rij">
            <span class="db-hbar-naam">{{ t.naam }}</span>
            <span class="db-hbar-track"><span class="db-hbar-fill" style="width:{{ (t.waarde/max_team_waarde*100)|round(1) }}%;"></span></span>
            <span class="db-hbar-getal">€{{ "{:,.0f}".format(t.waarde).replace(",", ".") }}</span>
        </div>
        {% else %}
        <div class="db-leeg">Nog geen accountmanagers of orders toegewezen.</div>
        {% endfor %}
    </div>
    <div class="db-kol">
        <div class="db-sectie-titel">Vraagt om aandacht</div>
        {% if aandacht_items %}
        {% for a in aandacht_items %}
        <a class="db-att-item" href="{{ a.url }}">
            <span class="db-att-dot"></span>
            <span><span class="db-att-titel">{{ a.titel }}</span>{% if a.sub %}<br><span class="db-att-sub">{{ a.sub }}</span>{% endif %}</span>
        </a>
        {% endfor %}
        {% else %}
        <div class="db-leeg">Niets dat aandacht vraagt.</div>
        {% endif %}
    </div>
</div>

<div class="db-rij">
    <div class="db-kol">
        <div class="db-sectie-titel">Progressie met bedrijven</div>
        {% for f in progressie_funnel %}
        <div class="db-hbar-rij">
            <span class="db-hbar-naam">{{ f.label }}</span>
            <span class="db-hbar-track"><span class="db-hbar-fill" style="width:{{ (f.aantal/max_funnel*100)|round(1) }}%;"></span></span>
            <span class="db-hbar-getal">{{ f.aantal }}</span>
        </div>
        {% endfor %}
    </div>
    <div class="db-kol">
        <div class="db-sectie-titel">Topklanten</div>
        {% for b in topklanten %}
        <a class="db-lijst-item" href="/bedrijf/{{ b.naam|urlencode }}">
            <span><span class="db-lijst-naam">{{ b.naam }}</span><br><span class="db-lijst-sub">{{ b.land }}</span></span>
            <span class="db-lijst-getal">{{ b.volume }} t/j</span>
        </a>
        {% else %}
        <div class="db-leeg">Nog geen klanten.</div>
        {% endfor %}
    </div>
    <div class="db-kol">
        <div class="db-sectie-titel">Klanten zonder recent contact <small>&gt;30 dagen</small></div>
        {% for k in klanten_zonder_contact %}
        <a class="db-lijst-item" href="/bedrijf/{{ k.naam|urlencode }}">
            <span class="db-lijst-naam">{{ k.naam }}</span>
            <span class="db-lijst-getal">{% if k.dagen is not none %}{{ k.dagen }} dagen{% else %}nooit contact{% endif %}</span>
        </a>
        {% else %}
        <div class="db-leeg">Alle klanten recent gesproken.</div>
        {% endfor %}
    </div>
</div>

<div class="db-rij">
    <div class="db-kol">
        <div class="db-sectie-titel">Nieuwe leads</div>
        {% for b in nieuwe_leads_lijst %}
        <a class="db-lijst-item" href="/bedrijf/{{ b.naam|urlencode }}">
            <span><span class="db-lijst-naam">{{ b.naam }}</span><br><span class="db-lijst-sub">{{ b.land }}</span></span>
            <span class="db-lijst-getal">{{ b.volume|default("—", true) }} t/j</span>
        </a>
        {% else %}
        <div class="db-leeg">Geen nieuwe leads zonder status.</div>
        {% endfor %}
    </div>
    <div class="db-kol">
        <div class="db-sectie-titel">Marktprijzen</div>
        {% for p in marktprijzen_recent %}
        <div class="db-lijst-item">
            <span class="db-lijst-naam">{{ p.materiaal }}</span>
            <span class="db-lijst-getal">€{{ "{:,.2f}".format(p.prijs_per_ton) }}/t</span>
        </div>
        {% else %}
        <div class="db-leeg">Nog geen marktprijzen ingevoerd.</div>
        {% endfor %}
    </div>
    <div class="db-kol">
        <div class="db-sectie-titel">Transportkosten</div>
        {% if aantal_forwarders %}
        <div class="db-lijst-item"><span class="db-lijst-naam">Forwarders</span><span class="db-lijst-getal">{{ aantal_forwarders }}</span></div>
        <div class="db-lijst-item"><span class="db-lijst-naam">Steden gedekt</span><span class="db-lijst-getal">{{ aantal_transport_steden }}</span></div>
        {% else %}
        <div class="db-leeg">Nog geen transportprijzen geimporteerd.</div>
        {% endif %}
    </div>
</div>

<div class="db-ph-titel">Nog te koppelen</div>
<div class="db-ph-sub">Deze onderdelen staan klaar in het dashboard maar hebben nog geen datamodel — geen verzonnen cijfers, wel alvast de plek.</div>
<div class="db-ph-grid">
    {% for p in placeholders %}
    <div class="db-ph-tegel">
        <div class="db-ph-tegel-label">{{ p.label }}</div>
        <div class="db-ph-tegel-waarde">—</div>
        <div class="db-ph-tegel-sub">{{ p.sub }}</div>
    </div>
    {% endfor %}
</div>

<div class="db-sectie-titel">Activiteit van het team</div>
{% if activiteit %}
{% for a in activiteit %}
<div class="db-act-item">
    <span class="db-act-naam">{{ a.gebruiker }}</span>
    <span class="db-act-tekst">{{ a.tekst }}<span class="db-act-sub">{{ a.sub }}</span></span>
</div>
{% endfor %}
{% else %}
<div class="db-leeg">Nog geen teamactiviteit.</div>
{% endif %}
    """
    pagina = render_simple_page("Dashboard", "dashboard", inhoud)

    _volume_som_dash = sum(parse_hoeveelheid_getal(b.get("volume","")) for b in ENF_BEDRIJVEN)
    if _volume_som_dash >= 1_000_000:
        volume_totaal_label = f"{_volume_som_dash/1_000_000:.1f} Mt".replace(".", ",")
    elif _volume_som_dash >= 1000:
        volume_totaal_label = f"{_volume_som_dash/1000:.1f}k t".replace(".", ",")
    else:
        volume_totaal_label = f"{_volume_som_dash:.0f} t"

    return render_template_string(pagina,
        gebruikersnaam_dash=gebruikersnaam_dash,
        huidige_week=_vandaag_dash.isocalendar()[1],
        bijgewerkt_tijd=datetime.datetime.now().strftime("%H:%M"),
        totaal=len(ENF_BEDRIJVEN), groei_pct=groei_pct, groei_periode=groei_periode,
        volume_totaal_label=volume_totaal_label,
        status_totaal_leads=len(ENF_BEDRIJVEN), leads_zonder_am_dash=leads_zonder_am_dash,
        geplande_orders_aantal=geplande_orders_aantal,
        omzet_totaal=omzet_totaal, ton_verkocht_totaal=ton_verkocht_totaal,
        verwachte_omzet=verwachte_omzet, lopende_orders_aantal=lopende_orders_aantal,
        maand_labels=maand_labels, inkoop_serie=inkoop_serie, max_inkoop_maand=max_inkoop_maand,
        pipeline_tellingen=pipeline_tellingen, max_pipeline=max_pipeline,
        inkoop_kwaliteit_lijst=inkoop_kwaliteit_lijst, max_inkoop_kwaliteit=max_inkoop_kwaliteit,
        team_prestaties_dash=team_prestaties_dash, max_team_waarde=max_team_waarde,
        aandacht_items=aandacht_items,
        progressie_funnel=progressie_funnel, max_funnel=max_funnel,
        topklanten=topklanten, klanten_zonder_contact=klanten_zonder_contact,
        nieuwe_leads_lijst=nieuwe_leads_lijst,
        marktprijzen_recent=marktprijzen_recent,
        aantal_forwarders=aantal_forwarders, aantal_transport_steden=aantal_transport_steden,
        placeholders=placeholders,
        activiteit=activiteit)
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

@app.route("/logistiek")
def logistiek_pagina():
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

    inhoud = """
<style>
.log-tabel-rij { display:flex; align-items:center; padding:10px 16px; border-bottom:1px solid var(--gray-100); font-size:13px; }
.log-tabel-kop { display:flex; align-items:center; padding:10px 16px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); font-size:10px; letter-spacing:0.08em; text-transform:uppercase; color:#7d8792; }
.log-badge { font-size:10px; font-weight:700; padding:2px 7px; border-radius:4px; }
</style>
<div class="page-title">Logistiek</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">
    {% if vooringevuld_bedrijf %}Shipments voor <b style="color:var(--gray-700);">{{ vooringevuld_bedrijf }}</b> — <a href="/logistiek" style="color:var(--brand-600);">alles tonen</a>
    {% else %}Alle actieve shipments (inbound, outbound en direct flow){% endif %}
</p>

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
<div style="border:1px solid var(--gray-200);border-radius:var(--radius-md);overflow:hidden;">
    <div class="log-tabel-kop">
        <span style="width:100px;">Datum</span>
        <span style="flex:1.6;">Route</span>
        <span style="flex:1;">Materiaal</span>
        <span style="width:110px;text-align:right;">Ton</span>
        <span style="width:90px;">Type</span>
        <span style="width:120px;">Status</span>
    </div>
    {% for s in getoonde_shipments_log %}
    <div class="log-tabel-rij">
        <span style="width:100px;color:var(--gray-500);">{{ s.datum }}</span>
        <span style="flex:1.6;color:var(--gray-800);font-weight:600;">{{ s.origin_land }}{% if s.origin_leverancier %} ({{ s.origin_leverancier }}){% endif %} → {{ s.destination_land }}{% if s.destination_naam %} ({{ s.destination_naam }}){% endif %}</span>
        <span style="flex:1;color:var(--gray-600);">{{ s.materiaal }}</span>
        <span style="width:110px;text-align:right;font-family:var(--font-mono);color:var(--gray-600);">{{ s.gepland_hoeveelheid }}{% if s.werkelijk_hoeveelheid %} / {{ s.werkelijk_hoeveelheid }}{% endif %}</span>
        <span style="width:90px;">
            <span class="log-badge" style="background:{{ '#eff6ff' if s.flow_type=='inbound' else ('#fef2f2' if s.flow_type=='outbound' else '#f5f3ff') }};color:{{ '#1d4ed8' if s.flow_type=='inbound' else ('#dc2626' if s.flow_type=='outbound' else '#7c3aed') }};">{{ s.flow_type|upper }}</span>
        </span>
        <span style="width:120px;color:var(--gray-600);">{{ s.status }}</span>
    </div>
    {% endfor %}
</div>
{% else %}
<div class="lege-staat">{% if vooringevuld_bedrijf %}Geen shipments gevonden voor {{ vooringevuld_bedrijf }}.{% else %}Geen shipments gevonden voor deze filters.{% endif %}</div>
{% endif %}
    """
    pagina = render_simple_page("Logistiek", "logistiek", inhoud)
    return render_template_string(pagina,
        vooringevuld_bedrijf=vooringevuld_bedrijf,
        getoonde_shipments_log=getoonde_shipments_log, actieve_shipments_log=actieve_shipments_log,
        filter_flow_type=filter_flow_type, filter_status_log=filter_status_log, filter_materiaal_log=filter_materiaal_log,
        shipment_statussen=SHIPMENT_STATUSSEN, shipment_materialen_log=shipment_materialen_log)

@app.route("/facturen", methods=["GET", "POST"])
def facturen_pagina():
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

<div class="kpi-mini" style="display:flex;gap:16px;margin-bottom:20px;">
    <div style="background:#fff;border:1px solid var(--gray-200);border-radius:10px;padding:14px 18px;flex:1;">
        <div style="font-size:1.4rem;font-weight:800;color:var(--brand-600);">{{ openstaande_facturen|length }}</div>
        <div style="font-size:0.75rem;color:var(--gray-400);">Openstaand</div>
    </div>
    <div style="background:#fff;border:1px solid var(--gray-200);border-radius:10px;padding:14px 18px;flex:1;">
        <div style="font-size:1.4rem;font-weight:800;color:var(--gray-800);">€{{ "{:,.0f}".format(totaal_openstaand).replace(",", ".") }}</div>
        <div style="font-size:0.75rem;color:var(--gray-400);">Totaal openstaand bedrag</div>
    </div>
    <div style="background:#fff;border:1px solid {{ '#fecaca' if te_laat_facturen else 'var(--gray-200)' }};border-radius:10px;padding:14px 18px;flex:1;">
        <div style="font-size:1.4rem;font-weight:800;color:{{ '#dc2626' if te_laat_facturen else 'var(--gray-800)' }};">{{ te_laat_facturen|length }}</div>
        <div style="font-size:0.75rem;color:var(--gray-400);">Te laat</div>
    </div>
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
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;">
            <input type="text" name="bedrag" placeholder="Bedrag (€)" required style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
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
        totaal_openstaand=totaal_openstaand, alle_bedrijfsnamen_fact=alle_bedrijfsnamen_fact)



import secrets
import string

def genereer_wachtwoord():
    tekens = string.ascii_letters + string.digits
    return "".join(secrets.choice(tekens) for _ in range(10))


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
            users = laad_users()
            if not nieuwe_naam:
                bericht = "Gebruikersnaam is verplicht."
            elif nieuwe_naam in users:
                bericht = f"'{nieuwe_naam}' bestaat al."
            else:
                nieuw_wachtwoord = genereer_wachtwoord()
                users[nieuwe_naam] = {"wachtwoord": generate_password_hash(nieuw_wachtwoord), "team": team, "is_admin": is_admin_nieuw}
                with open(USERS_FILE, "w", encoding="utf-8") as f:
                    json.dump(users, f, ensure_ascii=False, indent=2)
                bericht = f"'{nieuwe_naam}' toegevoegd!"
        elif actie == "verwijderen":
            te_verwijderen = request.form.get("gebruikersnaam", "")
            users = laad_users()
            if te_verwijderen == session.get("gebruikersnaam"):
                bericht = "Je kunt jezelf niet verwijderen."
            elif te_verwijderen in users:
                del users[te_verwijderen]
                with open(USERS_FILE, "w", encoding="utf-8") as f:
                    json.dump(users, f, ensure_ascii=False, indent=2)
                bericht = f"'{te_verwijderen}' verwijderd."
        elif actie == "toggle_admin":
            doelnaam = request.form.get("gebruikersnaam", "")
            users = laad_users()
            if doelnaam == session.get("gebruikersnaam"):
                bericht = "Je kunt je eigen adminrechten niet aanpassen."
            elif doelnaam in users:
                huidige = users[doelnaam].get("is_admin", True)
                users[doelnaam]["is_admin"] = not huidige
                with open(USERS_FILE, "w", encoding="utf-8") as f:
                    json.dump(users, f, ensure_ascii=False, indent=2)
                bericht = f"'{doelnaam}' is nu {'wel' if not huidige else 'geen'} admin."

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
            <label style="display:flex;align-items:center;gap:6px;font-size:13px;color:var(--gray-600);margin-bottom:12px;">
                <input type="checkbox" name="is_admin"> Admin (mag ook gebruikers beheren)
            </label>
            <button type="submit" class="btn-nav btn-nav-primary" style="border:none;cursor:pointer;width:100%;">+ Toevoegen (wachtwoord wordt automatisch gegenereerd)</button>
        </form>
    </div>

    <div class="info-kaart" style="max-width:420px;">
        <div class="dg-kaart-titel">Huidige gebruikers ({{ users|length }})</div>
        {% for naam, info in users.items() %}
        <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--gray-100);">
            <div>
                <b style="color:var(--gray-800);">{{ naam }}</b>
                <span style="color:var(--gray-400);font-size:12px;"> · {{ info.team or "geen team" }}</span>
                {% if info.get("is_admin", True) %}<span style="background:var(--brand-50);color:var(--brand-600);font-size:11px;font-weight:700;padding:2px 6px;border-radius:4px;margin-left:6px;">ADMIN</span>{% endif %}
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
        {% endfor %}
    </div>
    """
    pagina = render_simple_page("Gebruikers beheren", "instellingen", inhoud)
    return render_template_string(pagina, users=users, bericht=bericht, nieuw_wachtwoord=nieuw_wachtwoord)

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
    {% endif %}
    """
    pagina = render_simple_page("Instellingen", "instellingen", inhoud)
    return render_template_string(pagina, gebruikersnaam=session.get("gebruikersnaam",""), team=session.get("team",""), is_admin=is_huidige_gebruiker_admin())


@app.route("/fabriek/<naam>")
def fabriek_detail(naam):
    return redirect(url_for("bedrijf_profiel", naam=naam))


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
        <div class="wk-legenda"><span class="stip" style="background:#0d5c62;"></span> Geen status</div>
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
<style>
.marker-cluster-small { background-color: rgba(179,217,218,0.7); }
.marker-cluster-small div { background-color: rgba(63,146,149,0.85); color: #fff; }
.marker-cluster-medium { background-color: rgba(63,146,149,0.6); }
.marker-cluster-medium div { background-color: rgba(20,118,123,0.9); color: #fff; }
.marker-cluster-large { background-color: rgba(10,74,79,0.6); }
.marker-cluster-large div { background-color: rgba(10,74,79,0.95); color: #fff; }
.marker-cluster div { font-weight: 700; font-family: 'Libre Franklin', -apple-system, sans-serif; }
</style>
<script>
var ALLE_BEDRIJVEN_WK = {{ kaart_data|tojson }};
var wkKaart = L.map("wereldKaart").setView([30, 10], 2);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {attribution:"© OpenStreetMap"}).addTo(wkKaart);
var wkKleur = {"klant":"#22c55e","potentie":"#f59e0b","in_proces":"#3b82f6","geen_interesse":"#6b7280","":"#0d5c62"};
var wkCluster = null;

function wkFilter() {
    var land = document.getElementById("wkLand").value;
    var mat = document.getElementById("wkMateriaal").value;
    var status = document.getElementById("wkStatus").value;

    if (wkCluster) wkKaart.removeLayer(wkCluster);
    wkCluster = L.markerClusterGroup({
        iconCreateFunction: function(cluster) {
            return L.divIcon({
                html: '<div style="background:#0d5c62;color:#fff;width:34px;height:34px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12px;border:2px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,0.25);">' + cluster.getChildCount() + '</div>',
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
        popup += '<br><a href="/bedrijf/' + encodeURIComponent(b.naam) + '" style="color:#0d5c62;font-weight:600;">Bekijk profiel →</a>';
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
    is_fabriek_profiel = False
    if not bedrijf:
        _fabriek_bron = next((f for f in PAPIERFABRIEKEN if f["naam"] == naam), None)
        if _fabriek_bron:
            is_fabriek_profiel = True
            bedrijf = dict(_fabriek_bron)
            bedrijf.setdefault("regio", bedrijf.get("stad", ""))
            bedrijf.setdefault("brontype", "Papierfabriek")
    if not bedrijf:
        inhoud = '<div class="page-title">Niet gevonden</div><div class="lege-staat">Dit bedrijf bestaat niet (meer).</div>'
        pagina = render_simple_page("Niet gevonden", "zoeken", inhoud)
        return render_template_string(pagina), 404

    status_alle = laad_status()
    status = status_alle.get(bedrijf["naam"], "")
    opgeslagen = bedrijf["naam"] in set(laad_opgeslagen())
    geverifieerd = bool(bedrijf.get("adres") or bedrijf.get("telefoon"))

    inhoud = """
{% if is_fabriek_profiel %}<input type="hidden" id="isFabriekProfiel" value="1">{% endif %}
<div class="bedrijfsprofiel-inhoud">
<style>
.profiel-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:24px; }
.veld-label { font-size:10px; letter-spacing:0.08em; text-transform:uppercase; color:var(--gray-400); margin-bottom:3px; }
.klik-bewerken-veld {
    width:100%; border:1px solid transparent; background:transparent; padding:3px 6px; margin-left:-6px;
    font-size:13px; font-family:inherit; color:var(--gray-800); border-radius:5px; box-sizing:border-box; cursor:text;
}
.klik-bewerken-veld:hover { background:var(--gray-50); border-color:var(--gray-100); }
.klik-bewerken-veld:focus { background:#fff; border-color:var(--brand-300); outline:none; box-shadow:0 0 0 2px rgba(20,118,123,0.12); cursor:auto; }
select.klik-bewerken-veld { cursor:pointer; }
.profiel-naam { font-size:1.6rem; font-weight:800; color:var(--gray-900); letter-spacing:-0.5px; }
.profiel-loc { color:var(--gray-400); font-size:0.9rem; margin-top:4px; }
.profiel-grid { display:grid; grid-template-columns:1.3fr 1fr; gap:20px; align-items:start; }
@media (max-width:900px) { .profiel-grid { grid-template-columns:1fr; } }
.bedrijfsprofiel-inhoud .info-kaart {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0 0 16px 0;
    border-bottom: 1px solid var(--gray-200);
    margin-bottom: 16px !important;
    box-shadow: none;
}
.bedrijfsprofiel-inhoud .info-kaart:last-child { border-bottom: none; }
.bedrijfsprofiel-inhoud .profiel-grid > div .info-kaart:last-child { margin-bottom: 0 !important; }
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

<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/" style="color:var(--gray-400);text-decoration:none;">Zoeken</a> &nbsp;/&nbsp; {{ bedrijf.land }} &nbsp;/&nbsp; <span style="color:var(--gray-600);">{{ bedrijf.naam }}</span>
</div>
<div class="profiel-header">
    <div class="profiel-naam">{{ bedrijf.naam }}{% if geverifieerd %}<span class="verificatie-badge" style="margin-left:10px;">✓ Geverifieerd</span>{% endif %}</div>
    <div style="display:flex;align-items:center;gap:8px;">
        <span class="star-btn {% if opgeslagen %}opgeslagen{% endif %}" id="profielSterBtn" onclick="toggleOpslaanProfiel(this)" style="font-size:1.3rem;margin-right:4px;">{% if opgeslagen %}★{% else %}☆{% endif %}</span>
        <a href="#notitiesSectie" onclick="document.getElementById('nieuweNotitieTekst').focus();" style="font-size:13px;font-weight:600;color:var(--gray-600);border:1px solid var(--gray-200);padding:8px 14px;border-radius:6px;text-decoration:none;">Notitie</a>
        <a href="/export-csv?zoekterm={{ bedrijf.naam|urlencode }}" style="font-size:13px;font-weight:600;color:var(--gray-600);border:1px solid var(--gray-200);padding:8px 14px;border-radius:6px;text-decoration:none;">Export</a>
        <a href="/orders?bedrijf={{ bedrijf.naam|urlencode }}" style="font-size:13px;font-weight:600;color:#fff;background:var(--brand-600);padding:8px 14px;border-radius:6px;text-decoration:none;">Order aanmaken</a>
    </div>
</div>
<div style="display:flex;align-items:center;gap:10px;margin-top:-14px;margin-bottom:20px;font-size:13px;color:var(--gray-500);">
    {% if bedrijf.brontype %}<span style="background:var(--brand-600);color:#fff;font-size:11.5px;font-weight:600;padding:4px 10px;border-radius:5px;">{{ bedrijf.brontype }}</span>{% endif %}
    <span>{{ bedrijf.regio }}, {{ bedrijf.land }}</span>
</div>

{% if is_fabriek_profiel %}
<div style="display:flex;border:1px solid var(--gray-200);border-radius:var(--radius-md);margin-bottom:20px;overflow:hidden;">
    <div style="flex:1;padding:14px 20px;border-right:1px solid var(--gray-100);">
        <div style="font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Volume totaal</div>
        <div style="font-size:1.2rem;font-weight:700;color:var(--gray-800);">{{ bedrijf.volume|default('—',true) }}</div>
        <div style="font-size:11px;color:var(--gray-400);">t/jaar{% if bedrijf.materiaal_volumes %}, {{ bedrijf.materiaal_volumes|length }} materialen{% endif %}</div>
    </div>
    <div style="flex:1;padding:14px 20px;border-right:1px solid var(--gray-100);">
        <div style="font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Open orders</div>
        <div style="font-size:1.2rem;font-weight:700;color:var(--gray-800);">{{ open_orders_aantal }}</div>
        <div style="font-size:11px;color:var(--gray-400);">{% if open_orders_ton %}{{ open_orders_ton }} t deze periode{% else %}&nbsp;{% endif %}</div>
    </div>
    <div style="flex:1;padding:14px 20px;border-right:1px solid var(--gray-100);">
        <div style="font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Laatste contact</div>
        <div style="font-size:1.2rem;font-weight:700;color:var(--gray-800);">{{ laatst_contact_profiel|default('—',true) }}</div>
        <div style="font-size:11px;color:var(--gray-400);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ bedrijf.accountmanager|default('',true) }}{% if bedrijf.telefoon %}, telefoon{% endif %}</div>
    </div>
    <div style="flex:1;padding:14px 20px;">
        <div style="font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Afstand tot Alblasserdam</div>
        <div style="font-size:1.2rem;font-weight:700;color:var(--gray-800);">{% if afstand_alblasserdam %}{{ afstand_alblasserdam }} km{% else %}—{% endif %}</div>
        <div style="font-size:11px;color:var(--gray-400);">{{ bedrijf.regio }}, {{ bedrijf.land }}</div>
    </div>
</div>
{% else %}
<div style="display:flex;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);margin-bottom:20px;">
    <div style="flex:1;padding:14px 20px;border-right:1px solid var(--gray-200);">
        <div style="font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Volume totaal</div>
        <div style="font-size:1.2rem;font-weight:700;color:var(--gray-800);">{{ bedrijf.volume|default('—',true) }}</div>
        <div style="font-size:11px;color:var(--gray-400);">t/jaar{% if bedrijf.materiaal_volumes %}, {{ bedrijf.materiaal_volumes|length }} materialen{% endif %}</div>
    </div>
    <div style="flex:1;padding:14px 20px;border-right:1px solid var(--gray-200);">
        <div style="font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Open orders</div>
        <a href="/logistiek?bedrijf={{ bedrijf.naam|urlencode }}" style="text-decoration:none;">
            <div style="font-size:1.2rem;font-weight:700;color:var(--brand-600);">{{ open_orders_aantal }} →</div>
        </a>
        <div style="font-size:11px;color:var(--gray-400);">{% if open_orders_ton %}{{ open_orders_ton }} t deze periode{% else %}&nbsp;{% endif %}</div>
    </div>
    <div style="flex:1;padding:14px 20px;border-right:1px solid var(--gray-200);">
        <div style="font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Laatste contact</div>
        <div style="font-size:1.2rem;font-weight:700;color:var(--gray-800);">{{ laatst_contact_profiel|default('—',true) }}</div>
        <div style="font-size:11px;color:var(--gray-400);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ bedrijf.accountmanager|default('',true) }}{% if bedrijf.telefoon %}, telefoon{% endif %}</div>
    </div>
    <div style="flex:1;padding:14px 20px;">
        <div style="font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Afstand tot Alblasserdam</div>
        <div style="font-size:1.2rem;font-weight:700;color:var(--gray-800);">{% if afstand_alblasserdam %}{{ afstand_alblasserdam }} km{% else %}—{% endif %}</div>
        <div style="font-size:11px;color:var(--gray-400);">{{ bedrijf.regio }}, {{ bedrijf.land }}</div>
    </div>
</div>
{% endif %}

{% if materialen_volume_lijst %}
<div class="info-kaart" style="margin-bottom:16px;">
    <div class="dg-kaart-titel" style="color:var(--gray-400);margin-bottom:12px;">Materialen en volume</div>
    <div style="display:flex;font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:var(--gray-400);padding-bottom:8px;border-bottom:1px solid var(--gray-100);">
        <span style="flex:1.4;">Materiaal</span>
        <span style="width:100px;text-align:right;">T/jaar</span>
        <span style="width:160px;padding-left:16px;">Aandeel</span>
    </div>
    {% for m in materialen_volume_lijst %}
    <div style="display:flex;align-items:center;padding:10px 0;border-bottom:1px solid var(--gray-50);font-size:13px;">
        <span style="flex:1.4;font-weight:600;color:var(--gray-800);">{{ m.naam }}</span>
        <span style="width:100px;text-align:right;font-family:var(--font-mono);">{{ "{:,.0f}".format(m.volume) }}</span>
        <span style="width:160px;padding-left:16px;display:flex;align-items:center;gap:8px;">
            <span style="flex:1;height:5px;background:var(--gray-100);border-radius:5px;overflow:hidden;"><span style="display:block;height:100%;background:var(--brand-600);width:{{ m.aandeel }}%;"></span></span>
            <span style="font-size:11px;color:var(--gray-400);width:32px;text-align:right;">{{ m.aandeel }}%</span>
        </span>
    </div>
    {% endfor %}
</div>
{% endif %}

{% if inkoop_voortgang_lijst %}
<div class="info-kaart" style="margin-bottom:16px;">
    <div class="dg-kaart-titel" style="color:var(--gray-400);margin-bottom:12px;">Inkoop dit jaar t.o.v. jaarvolume</div>
    <div style="display:flex;font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:var(--gray-400);padding-bottom:8px;border-bottom:1px solid var(--gray-100);">
        <span style="flex:1.2;">Materiaal</span>
        <span style="width:90px;text-align:right;">Beschikbaar</span>
        <span style="width:90px;text-align:right;">Ingekocht</span>
        <span style="width:90px;text-align:right;">Nog te leveren</span>
        <span style="width:130px;padding-left:16px;">Voortgang</span>
    </div>
    {% for i in inkoop_voortgang_lijst %}
    <div style="padding:10px 0;border-bottom:1px solid var(--gray-50);font-size:13px;">
        <div style="display:flex;align-items:center;">
            <span style="flex:1.2;font-weight:600;color:var(--gray-800);">{{ i.naam }}</span>
            <span style="width:90px;text-align:right;font-family:var(--font-mono);">{{ "{:,.0f}".format(i.beschikbaar_jaar) }}t</span>
            <span style="width:90px;text-align:right;font-family:var(--font-mono);color:var(--brand-600);">{{ "{:,.0f}".format(i.ingekocht_dit_jaar) }}t</span>
            <span style="width:90px;text-align:right;font-family:var(--font-mono);color:{{ '#d97706' if i.nog_te_leveren else 'var(--gray-400)' }};">{{ "{:,.0f}".format(i.nog_te_leveren) }}t</span>
            <span style="width:130px;padding-left:16px;display:flex;align-items:center;gap:8px;">
                <span style="flex:1;height:5px;background:var(--gray-100);border-radius:5px;overflow:hidden;"><span style="display:block;height:100%;background:var(--brand-600);width:{{ i.pct_ingekocht }}%;"></span></span>
                <span style="font-size:11px;color:var(--gray-400);width:32px;text-align:right;">{{ i.pct_ingekocht }}%</span>
            </span>
        </div>
        <div style="font-size:11px;color:var(--gray-400);margin-top:3px;">nog {{ "{:,.0f}".format(i.restant_jaarvolume) }}t beschikbaar dit jaar</div>
    </div>
    {% endfor %}
</div>
{% endif %}


{% if recente_orders_profiel %}
<div class="info-kaart" style="margin-bottom:16px;">
    <div class="dg-kaart-titel" style="color:var(--gray-400);margin-bottom:12px;">Recente orders</div>
    <div style="display:flex;font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:var(--gray-400);padding-bottom:8px;border-bottom:1px solid var(--gray-100);">
        <span style="width:90px;">Referentie</span>
        <span style="flex:1;">Materiaal</span>
        <span style="width:110px;">Datum</span>
        <span style="width:80px;text-align:right;">Besteld</span>
        <span style="width:100px;text-align:right;">Status</span>
    </div>
    {% for o in recente_orders_profiel %}
    <div style="padding:9px 0;border-bottom:1px solid var(--gray-50);font-size:13px;">
        <div style="display:flex;align-items:center;">
            <span style="width:90px;color:var(--gray-400);font-family:var(--font-mono);font-size:11.5px;">{{ o.referentie }}</span>
            <span style="flex:1;font-weight:600;color:var(--gray-800);">{{ o.materiaal }}</span>
            <span style="width:110px;color:var(--gray-400);">{{ o.datum }}</span>
            <span style="width:80px;text-align:right;font-family:var(--font-mono);">{{ o.hoeveelheid }}</span>
            <span style="width:100px;text-align:right;font-weight:600;color:{{ '#16a34a' if o.status == 'Gewonnen' else ('#dc2626' if o.status == 'Verloren' else 'var(--brand-600)') }};">{{ o.status }}</span>
        </div>
        {% if o.heeft_levering_data %}
        <div style="display:flex;align-items:center;gap:10px;margin-top:6px;padding-left:90px;">
            <span style="flex:1;height:5px;background:var(--gray-100);border-radius:5px;overflow:hidden;"><span style="display:block;height:100%;background:{{ '#16a34a' if o.openstaand_order == 0 else 'var(--brand-600)' }};width:{{ o.geleverd_pct }}%;"></span></span>
            <span style="font-size:11px;color:var(--gray-400);white-space:nowrap;">{{ "{:,.0f}".format(o.geleverd_order) }}t geleverd{% if o.openstaand_order > 0 %} · {{ "{:,.0f}".format(o.openstaand_order) }}t openstaand{% endif %}</span>
        </div>
        {% endif %}
    </div>
    {% endfor %}
    <a href="/orders?bedrijf={{ bedrijf.naam|urlencode }}" style="display:block;margin-top:10px;font-size:0.78rem;color:var(--brand-600);text-decoration:none;font-weight:600;">+ Order toevoegen voor {{ bedrijf.naam }} →</a>
</div>
{% endif %}

<div class="profiel-grid">
    <div>
        <div class="info-kaart" style="margin-bottom:16px;">
    <div class="dg-kaart-titel" style="color:var(--gray-400);">Bedrijfsgegevens</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px 24px;">
        <div>
            <div class="veld-label">Status</div>
            <select id="statusSelect" onchange="wijzigStatusProfiel()" class="klik-bewerken-veld">
                <option value="" {% if not status %}selected{% endif %}>Geen status</option>
                <option value="klant" {% if status=='klant' %}selected{% endif %}>🟢 Klant</option>
                <option value="potentie" {% if status=='potentie' %}selected{% endif %}>🟡 Potentie</option>
                <option value="in_proces" {% if status=='in_proces' %}selected{% endif %}>🔵 In Proces</option>
                <option value="geen_interesse" {% if status=='geen_interesse' %}selected{% endif %}>⚪ Geen Interesse</option>
            </select>
        </div>
        <div>
            <div class="veld-label">Accountmanager</div>
            <select id="accountmanagerSelect" onchange="wijzigAccountmanagerProfiel()" class="klik-bewerken-veld">
                <option value="" {% if not accountmanager %}selected{% endif %}>Niet toegewezen</option>
                {% for gebruikersnaam in alle_gebruikersnamen %}
                <option value="{{ gebruikersnaam }}" {% if accountmanager == gebruikersnaam %}selected{% endif %}>{{ gebruikersnaam }}</option>
                {% endfor %}
            </select>
        </div>
        <div>
            <div class="veld-label">Bedrijfstype</div>
            <input type="text" value="{{ bedrijf.brontype or '' }}" data-veld="brontype" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld">
        </div>
        <div>
            <div class="veld-label">Klanttype</div>
            <input type="text" value="{{ bedrijf.klanttype or '' }}" data-veld="klanttype" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld">
        </div>
        <div>
            <div class="veld-label">Certificering</div>
            <input type="text" value="{{ bedrijf.certificeringen or '' }}" data-veld="certificeringen" onblur="wijzigBedrijfVeld(this)" placeholder="bv. ISO 9001, FSC..." class="klik-bewerken-veld">
        </div>
        <div>
            <div class="veld-label">Contactpersoon</div>
            <input type="text" value="{{ bedrijf.contactpersoon or '' }}" data-veld="contactpersoon" onblur="wijzigBedrijfVeld(this)" placeholder="Naam invullen..." class="klik-bewerken-veld">
        </div>
        <div>
            <div class="veld-label">Adres</div>
            <input type="text" value="{{ bedrijf.adres or '' }}" data-veld="adres" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld">
        </div>
        <div>
            <div class="veld-label">Telefoon</div>
            <input type="text" value="{{ bedrijf.telefoon or '' }}" data-veld="telefoon" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld">
        </div>
        <div>
            <div class="veld-label">Betalingstermijn</div>
            <input type="text" value="{{ bedrijf.betalingstermijn or '' }}" data-veld="betalingstermijn" onblur="wijzigBedrijfVeld(this)" placeholder="bv. 30 dagen" class="klik-bewerken-veld">
        </div>
    </div>
    <div style="margin-top:10px;font-size:13px;">
        <span id="echteWebsiteWrap" style="display:none;">🌐 <a id="echteWebsiteLink" href="#" target="_blank" style="color:var(--brand-600);font-weight:600;text-decoration:none;"></a></span>
    </div>
    <div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--gray-100);">
        <button type="button" onclick="toggleMeerInfo()" id="meerInfoToggleBtn" style="font-size:12px;font-weight:600;color:var(--brand-600);background:none;border:none;cursor:pointer;padding:0;">+ Meer informatie (bank, VAT, contact per afdeling)</button>
        <div id="meerInfoPaneel" style="display:none;margin-top:12px;">
            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:8px;">Algemeen</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px 24px;margin-bottom:16px;">
                <div><div class="veld-label">Postcode</div><input type="text" value="{{ bedrijf.postcode or '' }}" data-veld="postcode" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">Stad</div><input type="text" value="{{ bedrijf.stad or bedrijf.regio or '' }}" data-veld="stad" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">Algemeen e-mailadres</div><input type="text" value="{{ bedrijf.email_algemeen or '' }}" data-veld="email_algemeen" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">KvK-nummer</div><input type="text" value="{{ bedrijf.kvk_nummer or '' }}" data-veld="kvk_nummer" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
            </div>

            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:8px;">Financieel</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px 24px;margin-bottom:16px;">
                <div><div class="veld-label">Naam bank</div><input type="text" value="{{ bedrijf.bank_naam or '' }}" data-veld="bank_naam" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">Begunstigde</div><input type="text" value="{{ bedrijf.begunstigde or '' }}" data-veld="begunstigde" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">Bankadres</div><input type="text" value="{{ bedrijf.bank_adres or '' }}" data-veld="bank_adres" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">SWIFT / BIC-code</div><input type="text" value="{{ bedrijf.swift_bic or '' }}" data-veld="swift_bic" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">IBAN (EUR)</div><input type="text" value="{{ bedrijf.iban_eur or '' }}" data-veld="iban_eur" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">IBAN (USD)</div><input type="text" value="{{ bedrijf.iban_usd or '' }}" data-veld="iban_usd" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">IBAN (GBP)</div><input type="text" value="{{ bedrijf.iban_gbp or '' }}" data-veld="iban_gbp" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">VAT / BTW-nummer</div><input type="text" value="{{ bedrijf.vat_nummer or '' }}" data-veld="vat_nummer" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">Bankgegevens (overig)</div><input type="text" value="{{ bedrijf.bankgegevens or '' }}" data-veld="bankgegevens" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
            </div>

            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:8px;">Facturatie</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px 24px;margin-bottom:16px;">
                <div><div class="veld-label">E-mail voor facturatie</div><input type="text" value="{{ bedrijf.factuur_email or '' }}" data-veld="factuur_email" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">Contactpersoon facturatie</div><input type="text" value="{{ bedrijf.factuur_contactpersoon or '' }}" data-veld="factuur_contactpersoon" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">E-mail vragen over betalingen</div><input type="text" value="{{ bedrijf.vragen_betalingen_email or '' }}" data-veld="vragen_betalingen_email" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">E-mail sales-facturatie</div><input type="text" value="{{ bedrijf.sales_facturatie_email or '' }}" data-veld="sales_facturatie_email" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
            </div>

            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:8px;">Contact per afdeling</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px 24px;margin-bottom:16px;">
                <div><div class="veld-label">E-mail logistiek</div><input type="text" value="{{ bedrijf.email_logistiek or '' }}" data-veld="email_logistiek" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">E-mail finance</div><input type="text" value="{{ bedrijf.email_finance or '' }}" data-veld="email_finance" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">E-mail sales</div><input type="text" value="{{ bedrijf.email_sales or '' }}" data-veld="email_sales" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
            </div>

            {% if bedrijf.overige_contacten %}
            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:8px;">Overige contacten</div>
            <table style="width:100%;border-collapse:collapse;margin-bottom:16px;font-size:12.5px;">
                <thead><tr style="text-align:left;color:var(--gray-400);font-size:10px;text-transform:uppercase;border-bottom:1px solid var(--gray-100);">
                    <th style="padding:4px 6px;">Afdeling</th><th style="padding:4px 6px;">Naam</th><th style="padding:4px 6px;">E-mail</th><th style="padding:4px 6px;">Telefoon</th><th style="padding:4px 6px;">Functie</th>
                </tr></thead>
                <tbody>
                {% for c in bedrijf.overige_contacten %}
                <tr style="border-bottom:1px solid var(--gray-50);">
                    <td style="padding:6px;color:var(--gray-700);">{{ c.afdeling|default('—',true) }}</td>
                    <td style="padding:6px;color:var(--gray-800);font-weight:600;">{{ c.naam|default('—',true) }}</td>
                    <td style="padding:6px;color:var(--gray-600);">{{ c.email|default('—',true) }}</td>
                    <td style="padding:6px;color:var(--gray-600);">{{ c.telefoon|default('—',true) }}</td>
                    <td style="padding:6px;color:var(--gray-600);">{{ c.functie|default('—',true) }}</td>
                </tr>
                {% endfor %}
                </tbody>
            </table>
            {% endif %}

            {% if bedrijf.depot_adressen %}
            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:8px;">Depot-adressen</div>
            <table style="width:100%;border-collapse:collapse;margin-bottom:16px;font-size:12.5px;">
                <thead><tr style="text-align:left;color:var(--gray-400);font-size:10px;text-transform:uppercase;border-bottom:1px solid var(--gray-100);">
                    <th style="padding:4px 6px;">Naam</th><th style="padding:4px 6px;">Adres</th><th style="padding:4px 6px;">Telefoon</th><th style="padding:4px 6px;">E-mail</th><th style="padding:4px 6px;">Openingsuren</th><th style="padding:4px 6px;">Overig</th>
                </tr></thead>
                <tbody>
                {% for d in bedrijf.depot_adressen %}
                <tr style="border-bottom:1px solid var(--gray-50);">
                    <td style="padding:6px;color:var(--gray-800);font-weight:600;">{{ d.naam|default('—',true) }}</td>
                    <td style="padding:6px;color:var(--gray-600);">{{ d.adres|default('—',true) }}</td>
                    <td style="padding:6px;color:var(--gray-600);">{{ d.telefoon|default('—',true) }}</td>
                    <td style="padding:6px;color:var(--gray-600);">{{ d.email|default('—',true) }}</td>
                    <td style="padding:6px;color:var(--gray-600);">{{ d.openingsuren|default('—',true) }}</td>
                    <td style="padding:6px;color:var(--gray-600);">{{ d.overig|default('—',true) }}</td>
                </tr>
                {% endfor %}
                </tbody>
            </table>
            {% endif %}

            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:8px;">Overig</div>
            <div class="veld-label">Overige informatie</div>
            <textarea data-veld="overige_informatie" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld" style="min-height:56px;resize:vertical;">{{ bedrijf.overige_informatie or '' }}</textarea>
        </div>
    </div>
</div>

<div class="info-kaart" style="margin-bottom:16px;">
    <div style="display:flex;justify-content:space-between;align-items:center;">
        <div class="dg-kaart-titel" style="color:var(--gray-400);margin-bottom:0;">Materialen &amp; Kwaliteiten</div>
        <button type="button" onclick="toggleMaterialenBewerken()" id="materialenToggleBtn" style="font-size:12px;font-weight:600;color:var(--brand-600);background:none;border:none;cursor:pointer;">Bewerken</button>
    </div>
    <div id="materialenBewerkenPaneel" style="display:none;margin-top:12px;">
            {% set gekozen_materialen = (bedrijf.materialen or "").split(",") | map("trim") | list %}
            {% set gekozen_kwaliteiten = (bedrijf.kwaliteiten or "").split(",") | map("trim") | list %}
            {% for categorie, kwaliteiten_lijst in materiaal_taxonomie.items() %}
            <div style="padding:8px 0;border-bottom:1px solid var(--gray-50);">
                <label style="display:flex;align-items:center;gap:8px;font-weight:600;font-size:13px;color:var(--gray-700);cursor:pointer;">
                    <input type="checkbox" class="materiaal-checkbox" data-categorie="{{ categorie }}" {% if categorie in gekozen_materialen %}checked{% endif %} onchange="wijzigMateriaalCheckbox()">
                    {{ categorie }}
                </label>
                {% if kwaliteiten_lijst %}
                <div style="margin-left:24px;margin-top:6px;display:flex;flex-wrap:wrap;gap:10px;">
                    {% for kw in kwaliteiten_lijst %}
                    <label style="display:flex;align-items:center;gap:5px;font-size:12px;color:var(--gray-500);cursor:pointer;">
                        <input type="checkbox" class="kwaliteit-checkbox" data-categorie="{{ categorie }}" value="{{ kw }}" {% if kw in gekozen_kwaliteiten %}checked{% endif %} onchange="wijzigKwaliteitCheckbox()">
                        {{ kw }}
                    </label>
                    {% endfor %}
                </div>
                {% endif %}
            </div>
            {% else %}
            <div style="font-size:0.8rem;color:var(--gray-300);">Nog geen materialen gedefinieerd. Ga naar Instellingen → Materialen beheren (admin).</div>
            {% endfor %}
    <div id="volumeRijenContainer"></div>
    </div>
</div>

{% if not is_fabriek_profiel %}
<div class="info-kaart" style="margin-bottom:16px;">
    <div class="dg-kaart-titel" style="color:var(--gray-400);margin-bottom:4px;">Financieel</div>
    <a href="/facturen?bedrijf={{ bedrijf.naam|urlencode }}" id="facturenSamenvattingLink" style="display:block;text-decoration:none;padding:4px 0;">
        <div id="facturenSamenvatting" style="font-size:1.2rem;font-weight:700;color:var(--brand-600);">Laden...</div>
        <div style="font-size:11px;color:var(--gray-400);margin-top:2px;">Bekijk alle facturen →</div>
    </a>
</div>

<div class="info-kaart" style="margin-bottom:16px;">
    <div class="dg-kaart-titel" style="color:var(--gray-400);">Documenten</div>
    <div id="documentenLijst" style="margin-bottom:10px;"></div>
    <label style="display:inline-block;padding:6px 12px;background:var(--gray-100);color:var(--gray-700);border-radius:6px;cursor:pointer;font-size:12.5px;font-weight:600;">
        📄 Document uploaden (PDF/Word)
        <input type="file" id="documentInput" accept=".pdf,.doc,.docx" onchange="uploadDocumentProfiel()" style="display:none;">
    </label>
</div>
{% endif %}

        {% if bedrijf_shipments %}
        <div class="info-kaart" style="margin-bottom:16px;">
            <div class="dg-kaart-titel" style="color:var(--gray-400);">Shipments</div>
                {% for s in bedrijf_shipments %}
                <div class="dg-activiteit-item">
                    {{ s.referentie or s.id[:8] }} · {{ s.materiaal }} · {{ s.origin_land }} → {{ s.destination_land }}
                    <span style="color:{{ '#16a34a' if s.status in ('Delivered','Received') else 'var(--gray-500)' }};font-weight:700;"> · {{ s.status }}</span>
                    <small>{{ s.datum }}{% if s.werkelijk_hoeveelheid %} · {{ s.werkelijk_hoeveelheid }} ton (gewogen){% elif s.gepland_hoeveelheid %} · {{ s.gepland_hoeveelheid }} ton (gepland){% endif %}</small>
                </div>
                {% endfor %}
            <a href="/voorraad" style="display:block;margin-top:8px;font-size:0.78rem;color:var(--brand-600);text-decoration:none;font-weight:600;">Naar Voorraad →</a>
        </div>
        {% endif %}

        <div class="info-kaart" style="margin-bottom:16px;">
            <div class="dg-kaart-titel" style="color:var(--gray-400);">Foto's</div>
            <div id="fotoCategorieTabs" style="display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap;"></div>
            <div id="fotoBreadcrumb" style="font-size:0.78rem;color:var(--gray-400);margin-bottom:10px;"></div>
            <div id="fotoMappenGrid" style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;"></div>
            <div id="fotoGrid" style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;"></div>
            <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;">
                <input type="text" id="nieuweMapNaam" placeholder="Nieuwe map (bv. kwaliteit A)..." style="flex:1;padding:6px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;font-family:inherit;">
                <button onclick="maakFotoSubmapProfiel()" style="padding:6px 12px;background:var(--gray-100);color:var(--gray-700);border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;">+ Map</button>
            </div>
            <label style="display:inline-block;padding:6px 12px;background:var(--brand-600);color:#fff;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;">
                📷 Foto uploaden
                <input type="file" id="fotoInputProfiel" accept="image/*" onchange="uploadFotoProfiel()" style="display:none;">
            </label>
        </div>
    </div>

    <div>
        <div class="info-kaart">
            <div id="profielKaart" style="height:200px;border-radius:10px;overflow:hidden;"></div>
        </div>

        {% if fabrieken_gedeelde_kwaliteiten %}
        <div class="info-kaart" style="margin-top:16px;">
            <div class="dg-kaart-titel" style="color:var(--gray-400);">{{ matchpoel_label }}</div>
            {% for f in fabrieken_gedeelde_kwaliteiten %}
            <a href="/bedrijf/{{ f.naam|urlencode }}" style="display:block;padding:10px 0;border-bottom:1px solid var(--gray-50);text-decoration:none;color:inherit;">
                <div style="display:flex;justify-content:space-between;align-items:baseline;">
                    <b style="font-size:13px;color:var(--gray-800);">{{ f.naam }}</b>
                    {% if f.afstand %}<span style="font-size:11.5px;color:var(--brand-600);font-family:var(--font-mono);">{{ f.afstand }} km</span>{% endif %}
                </div>
                <div style="font-size:11.5px;color:var(--gray-400);margin-top:2px;">{{ f.regio }}, {{ f.land }} · match op {{ f.gedeelde_kwaliteiten }}</div>
            </a>
            {% endfor %}
        </div>
        {% endif %}

        {% if is_fabriek_profiel %}
        <div class="info-kaart" style="margin-top:16px;">
            <div class="dg-kaart-titel" style="color:var(--gray-400);">Leveranciers die leveren</div>
            {% if actieve_leveranciers %}
            {% for l in actieve_leveranciers %}
            <a href="/bedrijf/{{ l.naam|urlencode }}" style="display:block;padding:10px 0;border-bottom:1px solid var(--gray-50);text-decoration:none;color:inherit;">
                <div style="display:flex;justify-content:space-between;align-items:baseline;">
                    <b style="font-size:13px;color:var(--gray-800);">{{ l.naam }}</b>
                    {% if l.totaal_volume %}<span style="font-size:11.5px;color:var(--brand-600);font-family:var(--font-mono);">{{ "{:,.0f}".format(l.totaal_volume) }} t</span>{% endif %}
                </div>
                <div style="font-size:11.5px;color:var(--gray-400);margin-top:2px;">{{ l.land }} · {{ l.aantal_shipments }} shipment{{ 's' if l.aantal_shipments != 1 else '' }}{% if l.laatste_datum %} · laatst {{ l.laatste_datum }}{% endif %}</div>
            </a>
            {% endfor %}
            {% else %}
            <div style="font-size:13px;color:var(--gray-400);">Nog geen leveranties geregistreerd (via Voorraad-shipments).</div>
            {% endif %}
        </div>
        {% else %}
        <div class="info-kaart" style="margin-top:16px;">
            <div class="dg-kaart-titel" style="color:var(--gray-400);">Waar het naartoe gaat</div>
            {% if bestemmingen_lijst %}
            {% for b in bestemmingen_lijst %}
            <div style="padding:10px 0;border-bottom:1px solid var(--gray-50);">
                <div style="display:flex;justify-content:space-between;align-items:baseline;">
                    <b style="font-size:13px;color:var(--gray-800);">{{ b.naam or "Onbekende bestemming" }}{% if b.naam and b.land %}, {% endif %}{{ b.land }}</b>
                    {% if b.totaal_volume %}<span style="font-size:11.5px;color:var(--brand-600);font-family:var(--font-mono);">{{ "{:,.0f}".format(b.totaal_volume) }} t</span>{% endif %}
                </div>
                <div style="font-size:11.5px;color:var(--gray-400);margin-top:2px;">{{ b.aantal_shipments }} shipment{{ 's' if b.aantal_shipments != 1 else '' }}{% if b.laatste_datum %} · laatst {{ b.laatste_datum }}{% endif %}</div>
            </div>
            {% endfor %}
            {% else %}
            <div style="font-size:13px;color:var(--gray-400);">Nog geen vervolg-bestemmingen bekend — koppel een vervolg-shipment via Logistiek zodra dit materiaal wordt doorverscheept.</div>
            {% endif %}
        </div>
        {% endif %}

        <div class="info-kaart" style="margin-top:16px;">
            <div class="dg-kaart-titel" style="color:var(--gray-400);">Notities</div>
            <div id="notitiesLijst" style="margin-bottom:14px;"></div>
            <textarea id="notitieInput" placeholder="Schrijf een notitie..." style="width:100%;min-height:56px;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-family:inherit;font-size:13px;color:var(--gray-700);resize:vertical;box-sizing:border-box;"></textarea>
            <div style="display:flex;align-items:center;gap:16px;margin-top:10px;">
                <label style="font-size:12.5px;color:var(--gray-600);display:flex;align-items:center;gap:5px;cursor:pointer;"><input type="radio" name="notitieType" value="team" checked> Team</label>
                <label style="font-size:12.5px;color:var(--gray-600);display:flex;align-items:center;gap:5px;cursor:pointer;"><input type="radio" name="notitieType" value="prive"> Privé</label>
                <button onclick="voegNotitieToeProfiel()" style="margin-left:auto;padding:6px 16px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12.5px;font-weight:600;">Toevoegen</button>
            </div>
        </div>
    </div>
</div>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
var BEDRIJF_NAAM = {{ (bedrijf.naam or "")|tojson }};
var HUIDIGE_GEBRUIKER = {{ (gebruikersnaam or "")|tojson }};
var MATERIAAL_TAXONOMIE = {{ materiaal_taxonomie|tojson }};
var BEDRIJF_MATERIAAL_VOLUMES = {{ (bedrijf.get('materiaal_volumes', {}))|tojson }};
var BEDRIJF_URL = {{ (bedrijf.url or "")|tojson }};
var pKaart = L.map("profielKaart", {zoomControl:true}).setView([{{ bedrijf.lat or 20 }}, {{ bedrijf.lon or 0 }}], {{ 12 if bedrijf.lat else 2 }});
L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {attribution:"© OpenStreetMap, © CARTO", subdomains:"abcd", maxZoom:19}).addTo(pKaart);
{% if bedrijf.lat and bedrijf.lon %}
L.marker([{{ bedrijf.lat }}, {{ bedrijf.lon }}]).addTo(pKaart).bindPopup({{ bedrijf.naam|tojson }});
{% endif %}

function vulContact(data) {
    var telInput = document.querySelector('[data-veld="telefoon"]');
    var adrInput = document.querySelector('[data-veld="adres"]');
    if (telInput && !telInput.value && data.telefoon) telInput.value = data.telefoon;
    if (adrInput && !adrInput.value && data.adres) adrInput.value = data.adres;
    if (data.website) {
        var wrap = document.getElementById("echteWebsiteWrap");
        var link = document.getElementById("echteWebsiteLink");
        if (wrap && link) {
            link.href = data.website;
            link.textContent = data.website.replace("https://", "").replace("http://", "").split("/")[0];
            wrap.style.display = "inline";
        }
    }
}

if (BEDRIJF_URL) {
    fetch("/details?url=" + encodeURIComponent(BEDRIJF_URL)).then(r => r.json()).then(vulContact);
} else {
    vulContact({});
}

function toggleMeerInfo() {
    var paneel = document.getElementById("meerInfoPaneel");
    var knop = document.getElementById("meerInfoToggleBtn");
    var isOpen = paneel.style.display !== "none";
    paneel.style.display = isOpen ? "none" : "block";
    knop.textContent = isOpen ? "+ Meer informatie (bank, VAT, contact per afdeling)" : "− Meer informatie verbergen";
}

async function laadNotities() {
    const res = await fetch("/api/notities?bedrijf=" + encodeURIComponent(BEDRIJF_NAAM));
    const notities = await res.json();
    const div = document.getElementById("notitiesLijst");
    if (notities.length === 0) { div.innerHTML = "<p style='font-size:13px;color:var(--gray-400);'>Nog geen notities.</p>"; return; }
    let html = "";
    notities.forEach(n => {
        const badgeAchtergrond = n.type === "team" ? "var(--brand-50)" : "var(--gray-100)";
        const badgeKleur = n.type === "team" ? "var(--brand-600)" : "var(--gray-500)";
        const badge = n.type === "team" ? "Team" : "Privé";
        html += `<div style="padding:10px 0;border-bottom:1px solid var(--gray-100);font-size:13px;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
                <div style="color:var(--gray-700);">${n.tekst}</div>
                <button onclick="verwijderNotitieProfiel('${n.id}')" title="Verwijderen" style="background:none;border:none;color:var(--gray-300);cursor:pointer;font-size:12px;flex-shrink:0;">✕</button>
            </div>
            <div style="margin-top:5px;display:flex;align-items:center;gap:7px;">
                <span style="font-size:10px;font-weight:700;padding:1px 8px;border-radius:8px;background:${badgeAchtergrond};color:${badgeKleur};">${badge}</span>
                <span style="color:var(--gray-400);font-size:11px;">${n.timestamp}</span>
            </div>
        </div>`;
    });
    div.innerHTML = html;
}
async function verwijderNotitieProfiel(id) {
    if (!confirm("Deze notitie verwijderen?")) return;
    const res = await fetch("/api/notities", {method:"DELETE", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, id: id})});
    const data = await res.json();
    if (data.error) { alert(data.error); } else { laadNotities(); }
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
async function wijzigAccountmanagerProfiel() {
    const select = document.getElementById("accountmanagerSelect");
    await fetch("/api/accountmanager", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, accountmanager: select.value})});
}
async function wijzigBedrijfVeld(input) {
    const veld = input.dataset.veld;
    const origineel = input.dataset.origineel !== undefined ? input.dataset.origineel : input.defaultValue;
    if (input.value === origineel) return;
    input.style.opacity = "0.5";
    try {
        await fetch("/api/bedrijf-veld", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, veld: veld, waarde: input.value})});
        input.dataset.origineel = input.value;
    } finally {
        input.style.opacity = "1";
    }
}
async function wijzigMateriaalCheckbox() {
    const aangevinkt = Array.from(document.querySelectorAll(".materiaal-checkbox:checked")).map(el => el.dataset.categorie);
    herbouwVolumeRijen();
    await fetch("/api/bedrijf-veld", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, veld: "materialen", waarde: aangevinkt.join(", ")})});
}
async function wijzigKwaliteitCheckbox() {
    const aangevinkt = Array.from(document.querySelectorAll(".kwaliteit-checkbox:checked")).map(el => el.value);
    herbouwVolumeRijen();
    await fetch("/api/bedrijf-veld", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, veld: "kwaliteiten", waarde: aangevinkt.join(", ")})});
}
async function wijzigMateriaalVolume(input) {
    const materiaal = input.dataset.materiaal;
    const origineel = input.dataset.origineel !== undefined ? input.dataset.origineel : input.defaultValue;
    if (input.value === origineel) return;
    BEDRIJF_MATERIAAL_VOLUMES[materiaal] = input.value;
    input.style.opacity = "0.5";
    try {
        await fetch("/api/materiaal-volume", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, materiaal: materiaal, volume: input.value})});
        input.dataset.origineel = input.value;
    } finally {
        input.style.opacity = "1";
    }
}
function toggleMaterialenBewerken() {
    var paneel = document.getElementById("materialenBewerkenPaneel");
    var knop = document.getElementById("materialenToggleBtn");
    var isOpen = paneel.style.display !== "none";
    paneel.style.display = isOpen ? "none" : "block";
    knop.textContent = isOpen ? "Bewerken" : "Sluiten";
}

function herbouwVolumeRijen() {
    const container = document.getElementById("volumeRijenContainer");
    if (!container) return;
    const aangevinkteMaterialen = Array.from(document.querySelectorAll(".materiaal-checkbox:checked")).map(el => el.dataset.categorie);
    const aangevinkteKwaliteiten = Array.from(document.querySelectorAll(".kwaliteit-checkbox:checked")).map(el => ({categorie: el.dataset.categorie, naam: el.value}));

    let regels = [];
    aangevinkteMaterialen.forEach(cat => {
        const kwaliteitenOnderCat = aangevinkteKwaliteiten.filter(k => k.categorie === cat);
        if (kwaliteitenOnderCat.length > 0) {
            kwaliteitenOnderCat.forEach(k => regels.push(k.naam));
        } else {
            regels.push(cat);
        }
    });

    if (regels.length === 0) {
        container.innerHTML = "";
        return;
    }

    let html = '<div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin:10px 0 8px;">Volume per kwaliteit (t/jaar)</div>';
    regels.forEach(naam => {
        const waarde = BEDRIJF_MATERIAAL_VOLUMES[naam] || "";
        const veiligeNaam = naam.replace(/"/g, "&quot;");
        html += `<div class="drawer-row">
            <span class="drawer-row-label">${naam}</span>
            <span class="drawer-row-value">
                <input type="text" value="${waarde}" data-materiaal="${veiligeNaam}" onblur="wijzigMateriaalVolume(this)" placeholder="0" style="width:90px;padding:4px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;text-align:right;font-family:inherit;">
            </span>
        </div>`;
    });
    container.innerHTML = html;
}
async function toggleOpslaanProfiel(el) {
    const res = await fetch("/api/opgeslagen", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({naam: BEDRIJF_NAAM})});
    const data = await res.json();
    el.textContent = data.opgeslagen ? "★" : "☆";
    el.classList.toggle("opgeslagen", data.opgeslagen);
}
laadNotities();

async function laadFacturen() {
    const samenvattingDiv = document.getElementById("facturenSamenvatting");
    if (!samenvattingDiv) return;
    samenvattingDiv.textContent = "Laden...";
    try {
        const res = await fetch("/api/facturen?bedrijf=" + encodeURIComponent(BEDRIJF_NAAM));
        const facturen = await res.json();
        const openstaand = facturen.filter(f => f.status !== "Betaald");
        const teLaat = facturen.filter(f => f.status === "Te laat");
        const totaalOpenstaand = openstaand.reduce((som, f) => som + (parseFloat(String(f.bedrag).replace(",", ".")) || 0), 0);
        if (facturen.length === 0) {
            samenvattingDiv.textContent = "0";
        } else {
            samenvattingDiv.innerHTML = `${openstaand.length}<span style="font-size:0.7rem;font-weight:600;color:var(--gray-300);"> openstaand</span>`;
            const subDiv = samenvattingDiv.parentElement.querySelector("div:last-child");
            if (subDiv) subDiv.textContent = `€${totaalOpenstaand.toLocaleString("nl-NL", {maximumFractionDigits:0})} · ${teLaat.length} te laat — Bekijk alle facturen →`;
        }
    } catch (err) {
        samenvattingDiv.textContent = "—";
    }
}

async function laadDocumentenProfiel() {
    const lijstDiv = document.getElementById("documentenLijst");
    if (!lijstDiv) return;
    lijstDiv.innerHTML = "<p style='font-size:13px;color:#94a3b8;'>Laden...</p>";
    try {
        const res = await fetch("/api/documenten?bedrijf=" + encodeURIComponent(BEDRIJF_NAAM));
        const documenten = await res.json();
        if (documenten.length === 0) {
            lijstDiv.innerHTML = "<p style='font-size:13px;color:#94a3b8;'>Nog geen documenten geupload.</p>";
            return;
        }
        let html = "";
        documenten.forEach(d => {
            html += `
                <div style="display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid #f1f5f9;font-size:13px;">
                    <span style="color:#1e293b;">📄 ${d.originele_naam}<br><small style="color:#94a3b8;">${d.timestamp} · ${d.geupload_door}</small></span>
                    <span style="display:flex;gap:8px;align-items:center;">
                        <a href="/documenten_uploads/${d.bestandsnaam}" style="font-size:11.5px;font-weight:600;color:var(--brand-600);text-decoration:none;">Download</a>
                        <button onclick="verwijderDocumentProfiel('${d.bestandsnaam}')" title="Verwijderen" style="background:none;border:none;color:#cbd5e1;cursor:pointer;font-size:12px;">✕</button>
                    </span>
                </div>`;
        });
        lijstDiv.innerHTML = html;
    } catch (err) {
        lijstDiv.innerHTML = "<p style='font-size:13px;color:#ef4444;'>Kon documenten niet laden.</p>";
    }
}

async function uploadDocumentProfiel() {
    const input = document.getElementById("documentInput");
    const bestand = input.files[0];
    if (!bestand) return;
    const formData = new FormData();
    formData.append("bedrijf", BEDRIJF_NAAM);
    formData.append("document", bestand);
    const res = await fetch("/api/documenten", {method: "POST", body: formData});
    const data = await res.json();
    if (data.error) { alert(data.error); } else { laadDocumentenProfiel(); }
    input.value = "";
}

async function verwijderDocumentProfiel(bestandsnaam) {
    if (!confirm("Dit document verwijderen?")) return;
    const res = await fetch("/api/documenten", {method: "DELETE", headers: {"Content-Type": "application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, bestandsnaam: bestandsnaam})});
    const data = await res.json();
    if (data.error) { alert(data.error); } else { laadDocumentenProfiel(); }
}

if (!document.getElementById("isFabriekProfiel")) {
    laadFacturen();
    laadDocumentenProfiel();
}

const FOTO_STAAT = {categorie: "Algemeen", submap: ""};
const FOTO_CATEGORIEEN_LIJST = {{ (["Algemeen"] + materiaal_categorieen_lijst)|tojson }};

function initFotoBrowser() {
    const tabsDiv = document.getElementById("fotoCategorieTabs");
    if (!tabsDiv) return;
    tabsDiv.innerHTML = FOTO_CATEGORIEEN_LIJST.map(c =>
        `<button onclick="wisselFotoCategorieProfiel('${c}')" data-cat="${c}" style="padding:5px 12px;border-radius:6px;border:1px solid #e2e8f0;background:${c === FOTO_STAAT.categorie ? 'var(--brand-600)' : '#fff'};color:${c === FOTO_STAAT.categorie ? '#fff' : 'var(--gray-600)'};cursor:pointer;font-size:12px;font-weight:600;">${c}</button>`
    ).join("");
    laadFotoBrowser();
}

function wisselFotoCategorieProfiel(cat) {
    FOTO_STAAT.categorie = cat;
    FOTO_STAAT.submap = "";
    initFotoBrowser();
}

function openFotoSubmapProfiel(naam) {
    FOTO_STAAT.submap = naam;
    laadFotoBrowser();
}

function gaNaarFotoRootProfiel() {
    FOTO_STAAT.submap = "";
    laadFotoBrowser();
}

async function laadFotoBrowser() {
    const breadcrumb = document.getElementById("fotoBreadcrumb");
    const mappenGrid = document.getElementById("fotoMappenGrid");
    const fotoGrid = document.getElementById("fotoGrid");
    if (!breadcrumb) return;

    breadcrumb.innerHTML = FOTO_STAAT.submap
        ? `<a href="#" onclick="gaNaarFotoRootProfiel();return false;" style="color:var(--brand-600);text-decoration:none;">${FOTO_STAAT.categorie}</a> / ${FOTO_STAAT.submap}`
        : FOTO_STAAT.categorie;

    if (!FOTO_STAAT.submap) {
        const res = await fetch("/api/fotomappen?bedrijf=" + encodeURIComponent(BEDRIJF_NAAM) + "&categorie=" + encodeURIComponent(FOTO_STAAT.categorie));
        const mappen = await res.json();
        mappenGrid.innerHTML = mappen.map(m =>
            `<div onclick="openFotoSubmapProfiel('${m.replace(/'/g,"&#39;")}')" style="padding:8px 12px;background:var(--gray-50);border:1px solid #e2e8f0;border-radius:8px;cursor:pointer;font-size:12px;font-weight:600;color:var(--gray-700);">📁 ${m}</div>`
        ).join("");
    } else {
        mappenGrid.innerHTML = "";
    }

    const res2 = await fetch("/api/fotos?bedrijf=" + encodeURIComponent(BEDRIJF_NAAM) + "&categorie=" + encodeURIComponent(FOTO_STAAT.categorie) + "&submap=" + encodeURIComponent(FOTO_STAAT.submap));
    const fotos = await res2.json();
    fotoGrid.innerHTML = fotos.map(f =>
        `<div style="position:relative;width:70px;height:70px;">
            <img src="/fotos_uploads/${f.bestandsnaam}" style="width:70px;height:70px;object-fit:cover;border-radius:6px;border:1px solid #e2e8f0;cursor:pointer;" onclick="window.open('/fotos_uploads/${f.bestandsnaam}','_blank')" title="Door ${f.geupload_door} op ${f.timestamp}">
            <button onclick="verwijderFotoProfiel('${f.bestandsnaam}')" title="Verwijderen" style="position:absolute;top:-6px;right:-6px;width:18px;height:18px;border-radius:50%;background:#ef4444;color:#fff;border:2px solid #fff;cursor:pointer;font-size:10px;line-height:1;padding:0;">✕</button>
        </div>`
    ).join("") || `<div style="font-size:0.78rem;color:var(--gray-300);">Nog geen foto's hier.</div>`;
}

async function verwijderFotoProfiel(bestandsnaam) {
    if (!confirm("Deze foto verwijderen?")) return;
    const res = await fetch("/api/fotos", {method:"DELETE", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, bestandsnaam: bestandsnaam})});
    const data = await res.json();
    if (data.error) { alert(data.error); } else { laadFotoBrowser(); }
}

async function maakFotoSubmapProfiel() {
    const input = document.getElementById("nieuweMapNaam");
    const naam = input.value.trim();
    if (!naam) return;
    await fetch("/api/fotomappen", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, categorie: FOTO_STAAT.categorie, submap: naam})});
    input.value = "";
    laadFotoBrowser();
}

async function uploadFotoProfiel() {
    const input = document.getElementById("fotoInputProfiel");
    const bestand = input.files[0];
    if (!bestand) return;
    const formData = new FormData();
    formData.append("bedrijf", BEDRIJF_NAAM);
    formData.append("categorie", FOTO_STAAT.categorie);
    formData.append("submap", FOTO_STAAT.submap);
    formData.append("foto", bestand);
    const res = await fetch("/api/fotos", {method:"POST", body: formData});
    const data = await res.json();
    if (data.error) { alert(data.error); } else { laadFotoBrowser(); }
    input.value = "";
}

initFotoBrowser();
herbouwVolumeRijen();
</script>
</div>
    """

    # --- Open orders + laatste contact (echte data, dezelfde logica als op de zoekpagina) ---
    _orders_alle_profiel = laad_orders()
    _orders_van_bedrijf = [o for o in _orders_alle_profiel if o.get("bedrijf","") == bedrijf["naam"]]
    open_orders_lijst = [o for o in _orders_van_bedrijf if o.get("status") in ("Open", "Onderhandeling")]
    open_orders_aantal = len(open_orders_lijst)
    open_orders_ton = round(sum(parse_hoeveelheid_getal(o.get("hoeveelheid","")) for o in open_orders_lijst))
    open_orders_ton = f"{open_orders_ton:,.0f}" if open_orders_ton else ""

    _notities_alle_profiel = laad_notities()
    laatst_contact_profiel = ""
    _laatste_datum_profiel = None
    for n in _notities_alle_profiel.get(bedrijf["naam"], []):
        try:
            dt = datetime.datetime.strptime(n.get("timestamp",""), "%d-%m-%Y %H:%M").date()
            if _laatste_datum_profiel is None or dt > _laatste_datum_profiel:
                _laatste_datum_profiel = dt
        except (ValueError, TypeError):
            continue
    if _laatste_datum_profiel:
        _dagen_geleden_profiel = (datetime.date.today() - _laatste_datum_profiel).days
        if _dagen_geleden_profiel <= 0:
            laatst_contact_profiel = "Vandaag"
        elif _dagen_geleden_profiel == 1:
            laatst_contact_profiel = "Gisteren"
        else:
            laatst_contact_profiel = f"{_dagen_geleden_profiel} dagen"

    # --- Afstand tot Alblasserdam (haversine, echte berekening) ---
    def _haversine_km(lat1, lon1, lat2, lon2):
        import math
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * 2 * math.asin(math.sqrt(a))
    ALBLASSERDAM_LAT, ALBLASSERDAM_LON = 51.868, 4.663
    afstand_alblasserdam = None
    if bedrijf.get("lat") and bedrijf.get("lon"):
        afstand_alblasserdam = round(_haversine_km(ALBLASSERDAM_LAT, ALBLASSERDAM_LON, bedrijf["lat"], bedrijf["lon"]))

    # --- Materialen en volume (echte data uit materiaal_volumes) ---
    materialen_volume_lijst = []
    _volumes_dict = bedrijf.get("materiaal_volumes", {})
    if isinstance(_volumes_dict, dict) and _volumes_dict:
        _totaal_volume = sum(parse_hoeveelheid_getal(v) for v in _volumes_dict.values())
        for mat_naam, waarde in sorted(_volumes_dict.items(), key=lambda x: -parse_hoeveelheid_getal(x[1])):
            vol = parse_hoeveelheid_getal(waarde)
            materialen_volume_lijst.append({"naam": mat_naam, "volume": vol, "aandeel": round(vol / _totaal_volume * 100) if _totaal_volume else 0})

    # --- Inkoop-voortgang dit jaar vs. jaarlijks beschikbaar volume (alleen leveranciers, echte shipment-data) ---
    inkoop_voortgang_lijst = []
    if not is_fabriek_profiel and isinstance(_volumes_dict, dict) and _volumes_dict:
        _huidig_jaar = datetime.date.today().year
        _ontvangen_statussen = ("Weighed", "Received", "Delivered")
        _gepland_statussen = ("Planned", "Confirmed", "Loading", "Loaded", "In Transit", "Arrived")
        for mat_naam, waarde in _volumes_dict.items():
            beschikbaar_jaar = parse_hoeveelheid_getal(waarde)
            if beschikbaar_jaar <= 0:
                continue
            ingekocht_dit_jaar = 0.0
            nog_te_leveren = 0.0
            for s in laad_shipments():
                if s.get("origin_leverancier", "").strip().lower() != bedrijf["naam"].strip().lower():
                    continue
                if s.get("materiaal", "") != mat_naam:
                    continue
                if not s.get("datum"):
                    continue
                try:
                    jaar_shipment = datetime.datetime.strptime(s["datum"], "%Y-%m-%d").date().year
                except (ValueError, TypeError):
                    continue
                if jaar_shipment != _huidig_jaar:
                    continue
                if s.get("status") in _ontvangen_statussen:
                    ingekocht_dit_jaar += shipment_hoeveelheid(s)
                elif s.get("status") in _gepland_statussen:
                    nog_te_leveren += shipment_hoeveelheid(s)
            restant_jaarvolume = max(0.0, beschikbaar_jaar - ingekocht_dit_jaar)
            inkoop_voortgang_lijst.append({
                "naam": mat_naam, "beschikbaar_jaar": beschikbaar_jaar,
                "ingekocht_dit_jaar": ingekocht_dit_jaar, "nog_te_leveren": nog_te_leveren,
                "restant_jaarvolume": restant_jaarvolume,
                "pct_ingekocht": round(min(100, ingekocht_dit_jaar / beschikbaar_jaar * 100)) if beschikbaar_jaar else 0,
            })
        inkoop_voortgang_lijst.sort(key=lambda x: -x["beschikbaar_jaar"])

    # --- Recente orders (echte data, laatste 5) + geleverd/openstaand obv gekoppelde shipments ---
    _alle_shipments_profiel = laad_shipments()
    recente_orders_profiel = []
    for o in sorted(_orders_van_bedrijf, key=lambda x: x.get("aangemaakt",""), reverse=True)[:5]:
        _order_ref = f"Order-{o['id'][:8]}"
        _gekoppelde_shipments = [s for s in _alle_shipments_profiel if s.get("referentie","") == _order_ref]
        _totaal_order = parse_hoeveelheid_getal(o.get("hoeveelheid",""))
        _geleverd_order = sum(parse_hoeveelheid_getal(s.get("werkelijk_hoeveelheid","")) for s in _gekoppelde_shipments if s.get("werkelijk_hoeveelheid"))
        _openstaand_order = max(0, _totaal_order - _geleverd_order) if _totaal_order else 0
        recente_orders_profiel.append({
            "referentie": f"ORD-{o['id'][:4].upper()}", "materiaal": o.get("materiaal","—"),
            "datum": o.get("verwachte_datum","") or o.get("aangemaakt","").split(" ")[0],
            "hoeveelheid": o.get("hoeveelheid",""), "status": o.get("status",""),
            "totaal_order": _totaal_order, "geleverd_order": _geleverd_order, "openstaand_order": _openstaand_order,
            "geleverd_pct": round(_geleverd_order / _totaal_order * 100) if _totaal_order else 0,
            "heeft_levering_data": bool(_gekoppelde_shipments and _totaal_order),
        })

    # --- Fabrieken met gedeelde kwaliteiten (echte data: overlap in kwaliteiten, gesorteerd op afstand) ---
    fabrieken_gedeelde_kwaliteiten = []
    _matchpoel = PAPIERFABRIEKEN if not is_fabriek_profiel else ENF_BEDRIJVEN
    matchpoel_label = "Fabrieken met gedeelde kwaliteiten" if not is_fabriek_profiel else "Leveranciers met gedeelde kwaliteiten"
    _eigen_kwaliteiten = set(k.strip().lower() for k in (bedrijf.get("kwaliteiten","") or "").split(",") if k.strip())
    if _eigen_kwaliteiten:
        for ander in _matchpoel:
            if ander["naam"] == bedrijf["naam"] or not ander.get("kwaliteiten"):
                continue
            _andere_kwaliteiten = set(k.strip().lower() for k in ander["kwaliteiten"].split(",") if k.strip())
            _gedeeld = _eigen_kwaliteiten & _andere_kwaliteiten
            if _gedeeld:
                _afstand = None
                if bedrijf.get("lat") and bedrijf.get("lon") and ander.get("lat") and ander.get("lon"):
                    _afstand = round(_haversine_km(bedrijf["lat"], bedrijf["lon"], ander["lat"], ander["lon"]))
                fabrieken_gedeelde_kwaliteiten.append({
                    "naam": ander["naam"], "regio": ander.get("regio", ander.get("stad","")), "land": ander.get("land",""),
                    "afstand": _afstand, "gedeelde_kwaliteiten": ", ".join(sorted(_gedeeld, key=str.lower))[:60],
                    "_sorteer_afstand": _afstand if _afstand is not None else 999999,
                })
        fabrieken_gedeelde_kwaliteiten.sort(key=lambda x: x["_sorteer_afstand"])
        fabrieken_gedeelde_kwaliteiten = fabrieken_gedeelde_kwaliteiten[:5]

    pagina = render_simple_page(bedrijf["naam"], "zoeken", inhoud)
    _bedrijf_naam_laag = bedrijf["naam"].strip().lower()
    _bedrijf_shipments = sorted(
        [s for s in laad_shipments() if _bedrijf_naam_laag in (s.get("origin_leverancier","").strip().lower(), s.get("destination_naam","").strip().lower())],
        key=lambda s: s.get("datum",""), reverse=True
    )

    # --- Echte leveranciers die aan dit bedrijf leveren (uit shipment-geschiedenis, geen matching-gok) ---
    _leveren_aan_dict = {}
    for s in laad_shipments():
        if s.get("destination_naam","").strip().lower() != _bedrijf_naam_laag:
            continue
        _lev_naam = s.get("origin_leverancier","").strip()
        if not _lev_naam:
            continue
        if _lev_naam not in _leveren_aan_dict:
            _leveren_aan_dict[_lev_naam] = {"naam": _lev_naam, "land": s.get("origin_land",""), "aantal_shipments": 0, "totaal_volume": 0.0, "laatste_datum": ""}
        _entry = _leveren_aan_dict[_lev_naam]
        _entry["aantal_shipments"] += 1
        _entry["totaal_volume"] += parse_hoeveelheid_getal(s.get("werkelijk_hoeveelheid") or s.get("gepland_hoeveelheid") or "")
        if s.get("datum","") > _entry["laatste_datum"]:
            _entry["laatste_datum"] = s.get("datum","")
    actieve_leveranciers = sorted(_leveren_aan_dict.values(), key=lambda x: -x["totaal_volume"])

    # --- Voor leveranciers: waar hun materiaal uiteindelijk naartoe gaat (via gekoppelde vervolg-shipments) ---
    bestemmingen_lijst = []
    if not is_fabriek_profiel:
        _inbound_ids_van_leverancier = {
            s.get("id") for s in laad_shipments()
            if s.get("origin_leverancier", "").strip().lower() == _bedrijf_naam_laag
        }
        _bestemmingen_dict = {}
        for s in laad_shipments():
            if s.get("gekoppelde_shipment_id") not in _inbound_ids_van_leverancier:
                continue
            sleutel = (s.get("destination_land", ""), s.get("destination_naam", ""))
            if sleutel not in _bestemmingen_dict:
                _bestemmingen_dict[sleutel] = {
                    "land": s.get("destination_land", ""), "naam": s.get("destination_naam", ""),
                    "aantal_shipments": 0, "totaal_volume": 0.0, "laatste_datum": "",
                }
            _entry2 = _bestemmingen_dict[sleutel]
            _entry2["aantal_shipments"] += 1
            _entry2["totaal_volume"] += shipment_hoeveelheid(s)
            if s.get("datum", "") > _entry2["laatste_datum"]:
                _entry2["laatste_datum"] = s.get("datum", "")
        bestemmingen_lijst = sorted(_bestemmingen_dict.values(), key=lambda x: -x["totaal_volume"])

    return render_template_string(pagina, bedrijf=bedrijf, status=status, opgeslagen=opgeslagen, geverifieerd=geverifieerd,
                                    is_fabriek_profiel=is_fabriek_profiel,
                                    open_orders_aantal=open_orders_aantal, open_orders_ton=open_orders_ton,
                                    laatst_contact_profiel=laatst_contact_profiel, afstand_alblasserdam=afstand_alblasserdam,
                                    materialen_volume_lijst=materialen_volume_lijst, inkoop_voortgang_lijst=inkoop_voortgang_lijst,
                                    recente_orders_profiel=recente_orders_profiel,
                                    actieve_leveranciers=actieve_leveranciers, bestemmingen_lijst=bestemmingen_lijst,
                                    fabrieken_gedeelde_kwaliteiten=fabrieken_gedeelde_kwaliteiten, matchpoel_label=matchpoel_label,
                                    bedrijf_orders=[o for o in laad_orders() if o.get("bedrijf","").strip().lower() == bedrijf["naam"].strip().lower()],
                                    orderkleuren=ORDER_KLEUREN,
                                    accountmanager=laad_accountmanagers().get(bedrijf["naam"], ""),
                                    alle_gebruikersnamen=sorted(laad_users().keys()),
                                    gebruikersnaam=session.get("gebruikersnaam", ""),
                                    bedrijf_shipments=_bedrijf_shipments,
                                    materiaal_categorieen_lijst=[k.strip() for k in (bedrijf.get("kwaliteiten","") or "").split(",") if k.strip()],
                                    materiaal_taxonomie=laad_materiaal_taxonomie())

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