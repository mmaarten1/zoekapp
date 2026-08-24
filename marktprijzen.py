"""
marktprijzen.py — Blueprint voor de Marktprijzen-module.

Eerste echte Blueprint van de modularisatie. Bevat de /marktprijzen-route
(prijspunten per materiaal bekijken, toevoegen, verwijderen).

Registratie in app.py met: app.register_blueprint(marktprijzen_bp)
"""
import uuid
import datetime
from flask import Blueprint, request, session, redirect, url_for, render_template_string

from core import (
    laad_marktprijzen, bewaar_marktprijzen, laad_status, laad_accountmanagers,
    laad_materiaal_taxonomie, render_simple_page, is_huidige_gebruiker_admin, vereist_afdeling_of_403,
)

marktprijzen_bp = Blueprint("marktprijzen", __name__)

@marktprijzen_bp.route("/marktprijzen", methods=["GET", "POST"])
def marktprijzen_pagina():
    _guard = vereist_afdeling_of_403("marktprijzen")
    if _guard: return _guard
    if request.method == "POST":
        actie = request.form.get("actie", "")
        prijzen = laad_marktprijzen()

        if actie == "toevoegen":
            nieuw = {
                "id": str(uuid.uuid4()),
                "materiaal": request.form.get("materiaal", "").strip(),
                "prijs_per_ton": request.form.get("prijs_per_ton", "").strip(),
                "bron": request.form.get("bron", "handmatig"),
                "bedrijf": request.form.get("bedrijf", "").strip(),
                "notitie": request.form.get("notitie", "").strip(),
                "gebruiker": session.get("gebruikersnaam", ""),
                "datum": request.form.get("datum", "") or datetime.date.today().isoformat(),
                "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
            }
            try:
                nieuw["prijs_per_ton"] = float(str(nieuw["prijs_per_ton"]).replace(",", "."))
            except (ValueError, TypeError):
                nieuw["prijs_per_ton"] = 0
            if nieuw["materiaal"] and nieuw["prijs_per_ton"] > 0:
                prijzen.append(nieuw)
                bewaar_marktprijzen(prijzen)

        elif actie == "verwijderen":
            prijs_id = request.form.get("prijs_id", "")
            doel = next((p for p in prijzen if p["id"] == prijs_id), None)
            if doel and (doel.get("gebruiker") == session.get("gebruikersnaam","") or is_huidige_gebruiker_admin()):
                prijzen = [p for p in prijzen if p["id"] != prijs_id]
                bewaar_marktprijzen(prijzen)

        return redirect(url_for("marktprijzen.marktprijzen_pagina"))

    alle_prijzen = laad_marktprijzen()
    alle_prijzen.sort(key=lambda p: p.get("datum",""))

    per_materiaal = {}
    for p in alle_prijzen:
        per_materiaal.setdefault(p["materiaal"], []).append(p)

    materiaal_overzicht = []
    for naam, punten in per_materiaal.items():
        punten_gesorteerd = sorted(punten, key=lambda p: p.get("datum",""))
        laatste = punten_gesorteerd[-1]
        vorige = punten_gesorteerd[-2] if len(punten_gesorteerd) >= 2 else None
        trend = None
        if vorige:
            if laatste["prijs_per_ton"] > vorige["prijs_per_ton"]:
                trend = "up"
            elif laatste["prijs_per_ton"] < vorige["prijs_per_ton"]:
                trend = "down"
            else:
                trend = "gelijk"
        materiaal_overzicht.append({
            "naam": naam, "laatste_prijs": laatste["prijs_per_ton"], "laatste_datum": laatste["datum"],
            "trend": trend, "aantal_punten": len(punten_gesorteerd),
            "historie": punten_gesorteerd[-20:],
        })
    materiaal_overzicht.sort(key=lambda m: m["naam"])

    filter_materiaal_prijs = request.args.get("filter_materiaal", "")
    getoonde_prijzen = sorted(alle_prijzen, key=lambda p: p.get("aangemaakt",""), reverse=True)
    if filter_materiaal_prijs:
        getoonde_prijzen = [p for p in getoonde_prijzen if p["materiaal"] == filter_materiaal_prijs]

    _status_alle_mp = laad_status()
    _accountmanagers_alle_mp = laad_accountmanagers()
    alle_bedrijfsnamen_mp = sorted(set(_status_alle_mp.keys()) | set(_accountmanagers_alle_mp.keys()))[:500]

    inhoud = """
<style>
.mp-kaart { background:#fff; border:1px solid var(--gray-200); border-radius:10px; padding:16px 18px; }
.mp-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(210px,1fr)); gap:14px; margin-bottom:24px; }
.mp-prijs { font-size:1.4rem; font-weight:800; color:var(--gray-800); }
.mp-trend-up { color:#16a34a; }
.mp-trend-down { color:#dc2626; }
.mp-trend-gelijk { color:var(--gray-400); }
.mp-rij { display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid var(--gray-50); font-size:12.5px; }
.form-voorraad input, .form-voorraad select, .form-voorraad textarea { width:100%; padding:8px 10px; border:1px solid var(--gray-200); border-radius:6px; font-size:13px; margin-bottom:10px; font-family:inherit; box-sizing:border-box; }
</style>
<div class="page-title">Marktprijzen</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Prijs per ton, per materiaal/kwaliteit. Wordt automatisch aangevuld zodra je een order op "Gewonnen" zet.</p>

<div class="mp-grid">
    {% for m in materiaal_overzicht %}
    <div class="mp-kaart">
        <div class="mp-prijs">€{{ "{:,.2f}".format(m.laatste_prijs) }}<span style="font-size:0.7rem;font-weight:600;color:var(--gray-300);"> /ton</span>
            {% if m.trend == "up" %}<span class="mp-trend-up">▲</span>{% elif m.trend == "down" %}<span class="mp-trend-down">▼</span>{% elif m.trend == "gelijk" %}<span class="mp-trend-gelijk">▬</span>{% endif %}
        </div>
        <div style="font-size:0.82rem;color:var(--gray-500);margin-top:2px;">{{ m.naam }}</div>
        <div style="font-size:0.72rem;color:var(--gray-300);margin-top:4px;">{{ m.laatste_datum }} · {{ m.aantal_punten }} prijspunt{{ "en" if m.aantal_punten != 1 else "" }}</div>
    </div>
    {% else %}
    <div class="lege-staat">Nog geen marktprijzen. Voeg er handmatig een toe, of win een order met prijs + hoeveelheid.</div>
    {% endfor %}
</div>

<div class="mp-kaart" style="max-width:520px;margin-bottom:20px;">
    <div class="dg-kaart-titel">Prijspunt toevoegen</div>
    <form method="POST" class="form-voorraad">
        <input type="hidden" name="actie" value="toevoegen">
        <div class="form-rij-2" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <select name="materiaal" required>
                <option value="">Materiaal kiezen...</option>
                {% for categorie, kwaliteiten_lijst in materiaal_taxonomie.items() %}
                <optgroup label="{{ categorie }}">
                    <option value="{{ categorie }}">{{ categorie }} (algemeen)</option>
                    {% for kw in kwaliteiten_lijst %}<option value="{{ kw }}">{{ kw }}</option>{% endfor %}
                </optgroup>
                {% endfor %}
            </select>
            <input type="text" name="prijs_per_ton" placeholder="Prijs per ton (€)" required>
        </div>
        <div class="form-rij-2" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <select name="bron">
                <option value="handmatig">Handmatig ingevoerd</option>
                <option value="marktbericht">Marktbericht</option>
                <option value="leverancier_offerte">Leverancier offerte</option>
                <option value="klant_offerte">Klant offerte</option>
            </select>
            <input type="date" name="datum" value="{{ vandaag }}">
        </div>
        <input type="text" name="bedrijf" placeholder="Bedrijf (optioneel)" list="bedrijvenLijstMarktprijzen">
        <datalist id="bedrijvenLijstMarktprijzen">
            {% for naam in alle_bedrijfsnamen_mp %}<option value="{{ naam }}">{% endfor %}
        </datalist>
        <textarea name="notitie" placeholder="Notitie (optioneel)" rows="2"></textarea>
        <button type="submit" class="btn-nav btn-nav-primary" style="border:none;cursor:pointer;width:100%;">+ Prijspunt toevoegen</button>
    </form>
</div>

<form method="GET" style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
    <select name="filter_materiaal" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle materialen</option>
        {% for m in materiaal_overzicht %}<option value="{{ m.naam }}" {% if filter_materiaal_prijs == m.naam %}selected{% endif %}>{{ m.naam }}</option>{% endfor %}
    </select>
    {% if filter_materiaal_prijs %}<a href="/marktprijzen" style="font-size:12px;color:var(--gray-400);text-decoration:none;">Wis filter</a>{% endif %}
    <span style="font-size:12px;color:var(--gray-400);margin-left:auto;">{{ getoonde_prijzen|length }} prijspunten</span>
</form>

<div class="mp-kaart">
    {% for p in getoonde_prijzen %}
    <div class="mp-rij">
        <div>
            <b>{{ p.materiaal }}</b> · €{{ "{:,.2f}".format(p.prijs_per_ton) }}/ton
            {% if p.bedrijf %} · {{ p.bedrijf }}{% endif %}
            {% if p.bron == "order" %} · <span style="color:var(--brand-600);">📦 uit order</span>{% endif %}
            {% if p.bron == "handelsorder" %} · <a href="/handelsorders/{{ p.order_id }}" style="color:var(--brand-600);text-decoration:none;">📦 uit handelsorder</a>{% endif %}
            <br><small style="color:var(--gray-400);">{{ p.datum }} · {{ p.gebruiker }}{% if p.notitie %} · {{ p.notitie }}{% endif %}</small>
        </div>
        <form method="POST" onsubmit="return confirm('Prijspunt verwijderen?');" style="margin:0;">
            <input type="hidden" name="actie" value="verwijderen">
            <input type="hidden" name="prijs_id" value="{{ p.id }}">
            <button type="submit" style="background:none;border:none;color:var(--gray-300);cursor:pointer;font-size:1rem;">✕</button>
        </form>
    </div>
    {% else %}
    <div class="lege-staat">Geen prijspunten gevonden.</div>
    {% endfor %}
</div>
    """
    pagina = render_simple_page("Marktprijzen", "marktprijzen", inhoud)
    return render_template_string(pagina, materiaal_overzicht=materiaal_overzicht, getoonde_prijzen=getoonde_prijzen,
                                    filter_materiaal_prijs=filter_materiaal_prijs, materiaal_taxonomie=laad_materiaal_taxonomie(),
                                    alle_bedrijfsnamen_mp=alle_bedrijfsnamen_mp, vandaag=datetime.date.today().isoformat())