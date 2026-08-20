"""
commercieel_instellingen.py — Beheerpagina voor de commerciële instellingen
die de nieuwe Inkoop-/Verkooporder-module gebruikt: Incoterms,
Betalingstermijnen, Valuta, POD-havens en Bedrijfseenheden.

Alle vijf zijn eenvoudige, beheerbare lijsten — zelfde toevoegen/verwijderen-
patroon als de bestaande Materialen-beheer-pagina.

Registratie in app.py met: app.register_blueprint(commercieel_instellingen_bp)
"""
from flask import Blueprint, request, session, redirect, url_for, render_template_string

from core import (
    laad_incoterms, bewaar_incoterms, laad_betalingstermijnen, bewaar_betalingstermijnen,
    laad_valuta, bewaar_valuta, laad_pod_havens, bewaar_pod_havens,
    laad_bedrijfseenheden, bewaar_bedrijfseenheden, vereist_admin_of_403, render_simple_page,
)

commercieel_instellingen_bp = Blueprint("commercieel_instellingen", __name__)

_LIJST_CONFIG = {
    "incoterms": {"laad": laad_incoterms, "bewaar": bewaar_incoterms, "titel": "Incoterms", "voorbeeld": "bv. FOB, CIF, DAP..."},
    "betalingstermijnen": {"laad": laad_betalingstermijnen, "bewaar": bewaar_betalingstermijnen, "titel": "Betalingstermijnen", "voorbeeld": "bv. 30 dagen, Vooruitbetaling..."},
    "valuta": {"laad": laad_valuta, "bewaar": bewaar_valuta, "titel": "Valuta", "voorbeeld": "bv. EUR, USD, GBP..."},
    "pod_havens": {"laad": laad_pod_havens, "bewaar": bewaar_pod_havens, "titel": "POD — Port of Discharge (loshavens)", "voorbeeld": "bv. Rotterdam, Felixstowe, Shanghai..."},
    "bedrijfseenheden": {"laad": laad_bedrijfseenheden, "bewaar": bewaar_bedrijfseenheden, "titel": "Bedrijfseenheden", "voorbeeld": "bv. Papier, Plastic, Spanje, Portugal, UK..."},
}

@commercieel_instellingen_bp.route("/instellingen/commercieel", methods=["GET", "POST"])
def commerciele_instellingen_pagina():
    _guard = vereist_admin_of_403()
    if _guard: return _guard

    bericht = None
    if request.method == "POST":
        actie = request.form.get("actie", "")
        lijst_naam = request.form.get("lijst", "")
        config = _LIJST_CONFIG.get(lijst_naam)
        if config:
            huidige_lijst = config["laad"]()
            if actie == "toevoegen":
                waarde = request.form.get("waarde", "").strip()
                if not waarde:
                    bericht = "Vul een waarde in."
                elif waarde in huidige_lijst:
                    bericht = f"'{waarde}' staat al in de lijst."
                else:
                    huidige_lijst.append(waarde)
                    config["bewaar"](huidige_lijst)
                    bericht = f"'{waarde}' toegevoegd aan {config['titel']}."
            elif actie == "verwijderen":
                waarde = request.form.get("waarde", "")
                if waarde in huidige_lijst:
                    huidige_lijst.remove(waarde)
                    config["bewaar"](huidige_lijst)
                    bericht = f"'{waarde}' verwijderd uit {config['titel']}."

    inhoud = """
<div class="page-title">Commerciële instellingen</div>
<p style="color:var(--gray-400);font-size:0.85rem;margin-top:0;margin-bottom:20px;max-width:600px;">
    Deze lijsten worden gebruikt bij het aanmaken van inkoop- en verkooporders. Pas je hier iets aan, dan zie je dat direct terug in die formulieren.
</p>
{% if bericht %}<div style="background:#f0fdf4;color:#16a34a;padding:10px 16px;border-radius:8px;margin-bottom:20px;font-size:14px;max-width:600px;">{{ bericht }}</div>{% endif %}

<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:20px;">
    {% for sleutel, config in lijst_config.items() %}
    <div>
        <div style="font-size:12.5px;font-weight:700;color:var(--gray-700);margin-bottom:8px;">{{ config.titel }}</div>
        <form method="POST" style="display:flex;gap:6px;margin-bottom:10px;">
            <input type="hidden" name="actie" value="toevoegen">
            <input type="hidden" name="lijst" value="{{ sleutel }}">
            <input type="text" name="waarde" placeholder="{{ config.voorbeeld }}" required style="flex:1;padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
            <button type="submit" style="padding:7px 12px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;">+ Toevoegen</button>
        </form>
        <div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);">
            {% for item in config.laad() %}
            <div style="display:flex;justify-content:space-between;align-items:center;padding:7px 4px;border-bottom:1px solid var(--gray-100);font-size:12.5px;">
                <span style="color:var(--gray-700);">{{ item }}</span>
                <form method="POST" onsubmit="return confirm('{{ item }} verwijderen?');" style="margin:0;">
                    <input type="hidden" name="actie" value="verwijderen">
                    <input type="hidden" name="lijst" value="{{ sleutel }}">
                    <input type="hidden" name="waarde" value="{{ item }}">
                    <button type="submit" style="background:none;border:none;color:var(--gray-300);cursor:pointer;font-size:12px;">✕</button>
                </form>
            </div>
            {% else %}
            <div style="padding:10px 4px;color:var(--gray-300);font-size:12px;">Nog niets toegevoegd.</div>
            {% endfor %}
        </div>
    </div>
    {% endfor %}
</div>
    """
    pagina = render_simple_page("Commerciële instellingen", "instellingen", inhoud)
    return render_template_string(pagina, bericht=bericht, lijst_config=_LIJST_CONFIG)