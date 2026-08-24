"""
handelsorders.py — Het nieuwe, professionele Inkoop-/Verkooporder-systeem.

LET OP: dit is een NIEUWE, aparte module — niet een vervanging van het
bestaande, eenvoudige orders.json/orders.py-systeem. Dat oude systeem zit
diep verweven in het Dashboard, bedrijfsprofiel-pagina's en Logistieke
Inzichten; dat blijft dus ongewijzigd bestaan naast dit hier.

Workflow: Nieuwe order -> keuze Inkoop/Verkoop -> volledig formulier ->
opslaan als Concept -> op de detailpagina kiezen: Wijzigen (blijft Concept)
of Goedkeuren en versturen (wordt Definitief — PDF gegenereerd, en de
infrastructuur staat klaar voor e-mail-naar-leverancier en boekhoudkoppeling,
al zijn beide nog niet daadwerkelijk aangesloten).

Registratie in app.py met: app.register_blueprint(handelsorders_bp)
"""
import uuid
import datetime
import re
import io
from flask import Blueprint, request, session, redirect, url_for, render_template_string, Response, jsonify

from core import (
    laad_handelsorders, bewaar_handelsorders, genereer_contractnummer, HANDELSORDER_STATUSSEN,
    TRANSPORTMODI, ENF_BEDRIJVEN, PAPIERFABRIEKEN, laad_status, laad_accountmanagers,
    laad_materiaal_taxonomie, laad_incoterms, laad_betalingstermijnen, laad_valuta, laad_pod_havens,
    laad_bedrijfseenheden, laad_leverancier_instellingen, leverancier_instelling_voor,
    genereer_supplier_reference, is_huidige_gebruiker_admin, vereist_afdeling_of_403, render_simple_page,
    parse_hoeveelheid_getal, AFDELINGEN, AFDELING_LABELS, haal_live_wisselkoers, laad_facturen,
    bepaal_factuur_status, laad_marktprijzen, bewaar_marktprijzen,
)

handelsorders_bp = Blueprint("handelsorders", __name__)

def _echte_relaties():
    """Zelfde definitie als Leveranciers/Klanten: alleen bedrijven met een toegekende status
    of accountmanager. Gebruikt voor zowel leverancier- als klant-keuze in het formulier."""
    status_alle = laad_status()
    am_alle = laad_accountmanagers()
    return sorted({b["naam"] for b in ENF_BEDRIJVEN if status_alle.get(b["naam"]) or am_alle.get(b["naam"])})

def _klant_namen():
    """Klanten = fabrieken waaraan verkocht wordt (PAPIERFABRIEKEN)."""
    return sorted({f["naam"] for f in PAPIERFABRIEKEN})

def _getal(waarde):
    try:
        return float(str(waarde).replace(",", "."))
    except (ValueError, TypeError):
        return 0.0

def _bereken_marge_intern(order):
    """Berekent kostprijs/winst volledig in euro. Gebruikt de wisselkoersen die bij
    het AANMAKEN van de order zijn vastgelegd (wisselkoers_vastgelegd) — die worden
    nooit opnieuw opgehaald, ook niet bij bewerken of definitief maken, zodat de
    koers nooit onder je berekening verandert. Deze cijfers (kostprijs, winst) zijn
    puur intern en komen nooit op het contract dat naar de leverancier gaat.

    PERN (alleen UK-markt): een exportsubsidie die we ontvangen, dus die gaat van
    de inkoopprijs af vóórdat de rest van de berekening begint. PERN is altijd in
    pond en wordt met de eigen, apart vastgelegde pond-koers naar euro omgerekend —
    ook als de inkoopprijs zelf in een andere valuta staat."""
    koersen = order.get("wisselkoers_vastgelegd", {}) or {}
    inkoopprijs_eur = _getal(order.get("prijs")) * koersen.get("inkoop", 1.0)
    pern_eur = _getal(order.get("pern_gbp")) * koersen.get("pern", 1.0)
    effectieve_inkoopprijs_eur = inkoopprijs_eur - pern_eur
    verkoopprijs_eur = _getal(order.get("berekende_verkoopprijs")) * koersen.get("verkoop", 1.0)
    transportkosten_eur = _getal(order.get("berekende_transportkosten")) * koersen.get("transport", 1.0)
    laadgewicht = _getal(order.get("gemiddeld_laadgewicht"))
    extra_kosten = _getal(order.get("extra_kosten_per_mt"))
    hoeveelheid = _getal(order.get("hoeveelheid_mt"))

    transportkosten_per_mt_eur = round(transportkosten_eur / laadgewicht, 2) if laadgewicht > 0 else 0.0
    kostprijs_eur = round(effectieve_inkoopprijs_eur + transportkosten_per_mt_eur + extra_kosten, 2)
    winst_per_mt_eur = round(verkoopprijs_eur - kostprijs_eur, 2)
    winst_totaal_eur = round(winst_per_mt_eur * hoeveelheid, 2)
    return {
        "pern_eur": round(pern_eur, 2),
        "effectieve_inkoopprijs_eur": round(effectieve_inkoopprijs_eur, 2),
        "transportkosten_per_mt_eur": transportkosten_per_mt_eur,
        "kostprijs_eur": kostprijs_eur,
        "winst_per_mt_eur": winst_per_mt_eur,
        "winst_totaal_eur": winst_totaal_eur,
    }

def _vergrendel_wisselkoersen(order_form):
    """Haalt bij het AANMAKEN van een inkooporder eenmalig de live wisselkoersen op
    voor inkoop-, verkoop-, transport- en pond-valuta (voor PERN), en legt ze vast.
    Wordt nooit opnieuw aangeroepen bij bewerken — dat is precies het punt."""
    inkoop_valuta = order_form.get("valuta", "EUR")
    verkoop_valuta = order_form.get("verkoopprijs_valuta", "EUR") or inkoop_valuta
    transport_valuta = order_form.get("transportkosten_valuta", "EUR") or inkoop_valuta
    koers_inkoop, _ = haal_live_wisselkoers(inkoop_valuta, "EUR")
    koers_verkoop, _ = haal_live_wisselkoers(verkoop_valuta, "EUR")
    koers_transport, _ = haal_live_wisselkoers(transport_valuta, "EUR")
    koers_pern, _ = haal_live_wisselkoers("GBP", "EUR")
    return {"inkoop": koers_inkoop, "verkoop": koers_verkoop, "transport": koers_transport, "pern": koers_pern}


@handelsorders_bp.route("/handelsorders")
def handelsorders_pagina():
    _guard = vereist_afdeling_of_403("handelsorders")
    if _guard: return _guard

    alle_orders = laad_handelsorders()
    filter_type = request.args.get("type", "")
    filter_status = request.args.get("status", "")
    zoekterm = request.args.get("zoekterm", "").strip().lower()

    getoond = alle_orders
    if filter_type:
        getoond = [o for o in getoond if o.get("order_type") == filter_type]
    if filter_status:
        getoond = [o for o in getoond if o.get("status") == filter_status]
    if zoekterm:
        getoond = [o for o in getoond if zoekterm in o.get("contractnummer","").lower() or zoekterm in o.get("tegenpartij_naam","").lower()]
    getoond = sorted(getoond, key=lambda o: o.get("aangemaakt",""), reverse=True)

    kpi_concept = len([o for o in alle_orders if o.get("status") == "Concept"])
    kpi_definitief = len([o for o in alle_orders if o.get("status") == "Definitief"])
    kpi_inkoop = len([o for o in alle_orders if o.get("order_type") == "inkoop"])
    kpi_verkoop = len([o for o in alle_orders if o.get("order_type") == "verkoop"])

    inhoud = """
<div class="page-title">Handelsorders</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Inkoop- en verkoopcontracten.</p>

<style>
.ho-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; margin-bottom:24px; }
.ho-kaart { background:transparent; border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); padding:16px 4px; }
.ho-getal { font-size:1.6rem; font-weight:800; color:var(--gray-800); }
.ho-label { font-size:0.72rem; color:var(--gray-400); text-transform:uppercase; letter-spacing:0.6px; margin-top:4px; font-weight:600; }
.ho-tabel-kop { display:flex; align-items:center; padding:10px 16px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); font-size:10px; letter-spacing:0.08em; text-transform:uppercase; color:#7d8792; }
.ho-tabel-rij { display:flex; align-items:center; padding:10px 16px; border-bottom:1px solid var(--gray-100); font-size:12.5px; text-decoration:none; color:inherit; }
.ho-tabel-rij:hover { background:var(--gray-50); }
.ho-badge { font-size:10.5px; font-weight:700; padding:2px 8px; border-radius:4px; }
</style>

<div class="ho-grid">
    <div class="ho-kaart"><div class="ho-getal">{{ kpi_concept }}</div><div class="ho-label">Concept</div></div>
    <div class="ho-kaart"><div class="ho-getal">{{ kpi_definitief }}</div><div class="ho-label">Definitief</div></div>
    <div class="ho-kaart"><div class="ho-getal">{{ kpi_inkoop }}</div><div class="ho-label">Inkooporders</div></div>
    <div class="ho-kaart"><div class="ho-getal">{{ kpi_verkoop }}</div><div class="ho-label">Verkooporders</div></div>
</div>

<a href="/handelsorders/nieuw" style="display:inline-block;margin-bottom:20px;font-size:12.5px;font-weight:700;color:#fff;background:var(--brand-600);text-decoration:none;padding:9px 18px;border-radius:6px;">+ Nieuwe order</a>

<form method="GET" style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;">
    <select name="type" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle typen</option>
        <option value="inkoop" {% if filter_type == "inkoop" %}selected{% endif %}>Inkoop</option>
        <option value="verkoop" {% if filter_type == "verkoop" %}selected{% endif %}>Verkoop</option>
    </select>
    <select name="status" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle statussen</option>
        {% for st in statussen %}<option value="{{ st }}" {% if filter_status == st %}selected{% endif %}>{{ st }}</option>{% endfor %}
    </select>
    <input type="text" name="zoekterm" value="{{ zoekterm }}" placeholder="Zoek op contractnummer of naam" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;width:240px;">
    <button type="submit" style="padding:7px 14px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;background:#fff;cursor:pointer;">Filteren</button>
</form>

{% if getoond %}
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);">
    <div class="ho-tabel-kop">
        <span style="width:150px;">Contractnummer</span>
        <span style="width:70px;">Type</span>
        <span style="flex:1;">Naam</span>
        <span style="flex:1;">Materiaal</span>
        <span style="width:90px;text-align:right;">Hoeveelheid</span>
        <span style="width:100px;">Status</span>
    </div>
    {% for o in getoond %}
    <a href="/handelsorders/{{ o.id }}" class="ho-tabel-rij">
        <span style="width:150px;font-family:var(--font-mono);color:var(--gray-500);">{{ o.contractnummer }}</span>
        <span style="width:70px;">
            {% if o.order_type == "inkoop" %}<span class="ho-badge" style="background:#eff6ff;color:#1d4ed8;">Inkoop</span>
            {% else %}<span class="ho-badge" style="background:#f0fdf4;color:#16a34a;">Verkoop</span>{% endif %}
        </span>
        <span style="flex:1;color:var(--gray-700);font-weight:600;">{{ o.tegenpartij_naam or '—' }}</span>
        <span style="flex:1;color:var(--gray-600);">{{ o.materiaal or '—' }}{% if o.kwaliteit %} — {{ o.kwaliteit }}{% endif %}</span>
        <span style="width:90px;text-align:right;font-family:var(--font-mono);color:var(--gray-600);">{{ o.hoeveelheid_mt or '—' }}{% if o.hoeveelheid_mt %} MT{% endif %}</span>
        <span style="width:100px;">
            {% if o.status == "Definitief" %}<span class="ho-badge" style="background:#f0fdf4;color:#16a34a;">Definitief</span>
            {% else %}<span class="ho-badge" style="background:var(--gray-100);color:var(--gray-500);">Concept</span>{% endif %}
        </span>
    </a>
    {% endfor %}
</div>
<div style="padding:10px 4px;font-size:0.8rem;color:var(--gray-400);">{{ getoond|length }} orders</div>
{% else %}
<div class="lege-staat">Nog geen handelsorders. Maak je eerste order aan.</div>
{% endif %}
    """
    pagina = render_simple_page("Handelsorders", "handelsorders", inhoud)
    return render_template_string(pagina, getoond=getoond, statussen=HANDELSORDER_STATUSSEN,
                                    filter_type=filter_type, filter_status=filter_status, zoekterm=zoekterm,
                                    kpi_concept=kpi_concept, kpi_definitief=kpi_definitief,
                                    kpi_inkoop=kpi_inkoop, kpi_verkoop=kpi_verkoop)

@handelsorders_bp.route("/handelsorders/nieuw")
def handelsorders_nieuw_keuze():
    _guard = vereist_afdeling_of_403("handelsorders")
    if _guard: return _guard

    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/handelsorders" style="color:var(--gray-400);text-decoration:none;">Handelsorders</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">Nieuw</span>
</div>
<div class="page-title">Nieuwe order</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:24px;font-size:0.85rem;">Kies het type order.</p>

<div style="display:flex;gap:16px;flex-wrap:wrap;max-width:640px;">
    <a href="/handelsorders/nieuw/inkoop" style="flex:1;min-width:260px;text-decoration:none;display:block;border:none;border-top:2px solid var(--gray-200);border-bottom:2px solid var(--gray-200);padding:24px 20px;">
        <div style="font-size:15px;font-weight:800;color:var(--gray-800);margin-bottom:6px;">Inkooporder</div>
        <div style="font-size:12.5px;color:var(--gray-500);">Materiaal inkopen bij een leverancier.</div>
    </a>
    <a href="/handelsorders/nieuw/verkoop" style="flex:1;min-width:260px;text-decoration:none;display:block;border:none;border-top:2px solid var(--gray-200);border-bottom:2px solid var(--gray-200);padding:24px 20px;">
        <div style="font-size:15px;font-weight:800;color:var(--gray-800);margin-bottom:6px;">Verkooporder</div>
        <div style="font-size:12.5px;color:var(--gray-500);">Materiaal verkopen aan een klant.</div>
    </a>
</div>
    """
    pagina = render_simple_page("Nieuwe order", "handelsorders", inhoud)
    return render_template_string(pagina)

@handelsorders_bp.route("/api/leverancier-info")
def api_leverancier_info():
    """Voor het auto-invullen bij het kiezen van een leverancier: afhaallocaties en
    standaard betalingstermijn, plus een live-gegenereerd voorbeeld van het
    volgende supplier-referentienummer (zonder de teller al op te hogen)."""
    _guard = vereist_afdeling_of_403("handelsorders")
    if _guard: return _guard
    naam = request.args.get("naam", "").strip()
    instelling = leverancier_instelling_voor(naam)
    return jsonify({
        "afhaallocaties": instelling.get("afhaallocaties", []),
        "standaard_betalingstermijn": instelling.get("standaard_betalingstermijn", ""),
    })

@handelsorders_bp.route("/handelsorders/nieuw/inkoop", methods=["GET", "POST"])
def handelsorders_nieuw_inkoop():
    _guard = vereist_afdeling_of_403("handelsorders")
    if _guard: return _guard

    if request.method == "POST":
        orders = laad_handelsorders()
        nu = datetime.datetime.now()
        leverancier = request.form.get("leverancier", "").strip()
        nieuw = {
            "id": str(uuid.uuid4()),
            "order_type": "inkoop",
            "contractnummer": genereer_contractnummer(orders, "inkoop"),
            "tegenpartij_naam": leverancier,
            "bedrijfseenheid": request.form.get("bedrijfseenheid", "").strip(),
            "datum_aangemaakt": request.form.get("datum_aangemaakt", "") or nu.date().isoformat(),
            "incoterm": request.form.get("incoterm", "").strip(),
            "betalingstermijn": request.form.get("betalingstermijn", "").strip(),
            "materiaal": request.form.get("materiaal", "").strip(),
            "kwaliteit": request.form.get("kwaliteit", "").strip(),
            "supplier_reference": genereer_supplier_reference(leverancier) if leverancier else "",
            "startdatum": request.form.get("startdatum", "") or nu.date().isoformat(),
            "einddatum": request.form.get("einddatum", "").strip(),
            "valuta": request.form.get("valuta", "").strip(),
            "hoeveelheid_mt": request.form.get("hoeveelheid_mt", "").strip(),
            "prijs": request.form.get("prijs", "").strip(),
            "afhaal_locatienaam": request.form.get("afhaal_locatienaam", "").strip(),
            "afhaal_adres": request.form.get("afhaal_adres", "").strip(),
            "afhaal_postcode": request.form.get("afhaal_postcode", "").strip(),
            "afhaal_stad": request.form.get("afhaal_stad", "").strip(),
            "afhaal_land": request.form.get("afhaal_land", "").strip(),
            "transportmodus": request.form.get("transportmodus", "").strip(),
            "berekende_verkoopprijs": request.form.get("berekende_verkoopprijs", "").strip(),
            "verkoopprijs_valuta": request.form.get("verkoopprijs_valuta", "").strip(),
            "berekende_transportkosten": request.form.get("berekende_transportkosten", "").strip(),
            "transportkosten_valuta": request.form.get("transportkosten_valuta", "").strip(),
            "gemiddeld_laadgewicht": request.form.get("gemiddeld_laadgewicht", "").strip(),
            "extra_kosten_per_mt": request.form.get("extra_kosten_per_mt", "").strip(),
            "pern_gbp": request.form.get("pern_gbp", "").strip(),
            "klant": request.form.get("klant", "").strip(),
            "pod_haven": request.form.get("pod_haven", "").strip(),
            "opmerkingen": request.form.get("opmerkingen", "").strip(),
            "afdeling_notities": {a: request.form.get(f"notitie_{a}", "").strip() for a in AFDELINGEN},
            "status": "Concept",
            "aangemaakt_door": session.get("gebruikersnaam", ""),
            "aangemaakt": nu.strftime("%d-%m-%Y %H:%M"),
        }
        # Wisselkoersen NU vastleggen (eenmalig, bij aanmaken) — worden nooit meer
        # opnieuw opgehaald, ook niet bij bewerken of definitief maken.
        nieuw["wisselkoers_vastgelegd"] = _vergrendel_wisselkoersen(request.form)
        marge_resultaat = _bereken_marge_intern(nieuw)
        nieuw["pern_eur"] = marge_resultaat["pern_eur"]
        nieuw["effectieve_inkoopprijs_eur"] = marge_resultaat["effectieve_inkoopprijs_eur"]
        nieuw["kostprijs_eur"] = marge_resultaat["kostprijs_eur"]
        nieuw["winst_per_mt_eur"] = marge_resultaat["winst_per_mt_eur"]
        nieuw["winst_totaal_eur"] = marge_resultaat["winst_totaal_eur"]
        nieuw["transportkosten_per_mt_eur"] = marge_resultaat["transportkosten_per_mt_eur"]
        # berekende_marge blijft bestaan (nu gevuld met de echte winst_totaal_eur) zodat
        # Dashboard/Inzichten/Leveranciers-pagina, die dit veld al gebruiken, automatisch
        # de correcte, volledige berekening tonen zonder dat die code aangepast hoeft te worden.
        nieuw["berekende_marge"] = str(marge_resultaat["winst_totaal_eur"])
        orders.append(nieuw)
        bewaar_handelsorders(orders)
        return redirect(url_for("handelsorders.handelsorder_detail", order_id=nieuw["id"]))

    inhoud = _inkoop_formulier_html()
    pagina = render_simple_page("Nieuwe inkooporder", "handelsorders", inhoud)
    return render_template_string(pagina, **_formulier_context())

def _formulier_context():
    return dict(
        leverancier_namen=_echte_relaties(), klant_namen=_klant_namen(),
        bedrijfseenheden=laad_bedrijfseenheden(), incoterms=laad_incoterms(),
        betalingstermijnen=laad_betalingstermijnen(), materiaal_namen=sorted(laad_materiaal_taxonomie().keys()),
        taxonomie_json=__import__("json").dumps(laad_materiaal_taxonomie()),
        valuta_lijst=laad_valuta(), pod_havens=laad_pod_havens(),
        transportmodi=TRANSPORTMODI, afdelingen=AFDELINGEN, afdeling_labels=AFDELING_LABELS,
        vandaag=datetime.date.today().isoformat(),
    )

def _inkoop_formulier_html():
    return """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/handelsorders" style="color:var(--gray-400);text-decoration:none;">Handelsorders</a> &nbsp;/&nbsp; <a href="/handelsorders/nieuw" style="color:var(--gray-400);text-decoration:none;">Nieuw</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">Inkoop</span>
</div>
<div class="page-title">Nieuwe inkooporder</div>

<form method="POST" style="max-width:720px;">
<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin:20px 0 10px 0;">Basisinformatie</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Leverancier *</label>
        <input type="text" name="leverancier" id="leverancier_input" list="leveranciers_datalist" required autocomplete="off" oninput="laadLeverancierInfo()" value="{{ leverancier|default('') }}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        <datalist id="leveranciers_datalist">{% for naam in leverancier_namen %}<option value="{{ naam }}">{% endfor %}</datalist>
    </div>
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Bedrijfseenheid</label>
        <select name="bedrijfseenheid" id="bedrijfseenheid_select" onchange="toonPernIndienUK()" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
            <option value="">— kies —</option>
            {% for be in bedrijfseenheden %}<option value="{{ be }}" {% if bedrijfseenheid == be %}selected{% endif %}>{{ be }}</option>{% endfor %}
        </select>
    </div>
</div>
<div style="margin-bottom:16px;max-width:240px;">
    <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Datum aangemaakt</label>
    <input type="date" name="datum_aangemaakt" value="{{ vandaag }}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;">
</div>

<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin:20px 0 10px 0;">Deal informatie</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Incoterm</label>
        <select name="incoterm" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
            <option value="">— kies —</option>
            {% for i in incoterms %}<option value="{{ i }}" {% if incoterm == i %}selected{% endif %}>{{ i }}</option>{% endfor %}
        </select>
    </div>
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Betalingstermijn</label>
        <select name="betalingstermijn" id="betalingstermijn_select" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
            <option value="">— kies —</option>
            {% for b in betalingstermijnen %}<option value="{{ b }}" {% if betalingstermijn == b %}selected{% endif %}>{{ b }}</option>{% endfor %}
        </select>
    </div>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Materiaal *</label>
        <input type="text" name="materiaal" id="materiaal_input" list="materiaal_datalist" required autocomplete="off" oninput="verversKwaliteiten()" value="{{ materiaal|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        <datalist id="materiaal_datalist">{% for m in materiaal_namen %}<option value="{{ m }}">{% endfor %}</datalist>
    </div>
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Kwaliteit *</label>
        <input type="text" name="kwaliteit" id="kwaliteit_input" list="kwaliteit_datalist" required autocomplete="off" placeholder="Kies eerst materiaal..." value="{{ kwaliteit|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        <datalist id="kwaliteit_datalist"></datalist>
    </div>
</div>
<div style="font-size:11px;color:var(--gray-300);margin-bottom:16px;">Suppliers Reference wordt automatisch gegenereerd na opslaan.</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Startdatum order</label>
        <input type="date" name="startdatum" value="{{ vandaag }}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;">
    </div>
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Einddatum order</label>
        <input type="date" name="einddatum" value="{{ einddatum|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;">
    </div>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:16px;">
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Valuta</label>
        <select name="valuta" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
            {% for v in valuta_lijst %}<option value="{{ v }}" {% if valuta == v %}selected{% endif %}>{{ v }}</option>{% endfor %}
        </select>
    </div>
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Hoeveelheid (MT)</label>
        <input type="text" name="hoeveelheid_mt" value="{{ hoeveelheid_mt|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
    </div>
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Inkoopprijs (per MT)</label>
        <input type="text" name="prijs" value="{{ prijs|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
    </div>
</div>

<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin:20px 0 10px 0;">Afhaallocatie</div>
<div id="afhaal_keuze_blok" style="margin-bottom:10px;display:none;">
    <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Kies locatie</label>
    <select id="afhaal_locatie_select" onchange="vulAfhaallocatieIn()" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;"></select>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
    <input type="text" name="afhaal_locatienaam" id="afhaal_locatienaam" placeholder="Locatienaam" value="{{ afhaal_locatienaam|default('')}}" style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
    <input type="text" name="afhaal_adres" id="afhaal_adres" placeholder="Adres" value="{{ afhaal_adres|default('')}}" style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
</div>
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:16px;">
    <input type="text" name="afhaal_postcode" id="afhaal_postcode" placeholder="Postcode" value="{{ afhaal_postcode|default('')}}" style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
    <input type="text" name="afhaal_stad" id="afhaal_stad" placeholder="Stad" value="{{ afhaal_stad|default('')}}" style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
    <input type="text" name="afhaal_land" id="afhaal_land" placeholder="Land" value="{{ afhaal_land|default('')}}" style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
</div>

<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin:20px 0 10px 0;">Transport</div>
<div style="display:flex;gap:12px;margin-bottom:16px;">
    {% for modus in transportmodi %}
    <label style="flex:1;border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);padding:14px 16px;cursor:pointer;display:block;">
        <input type="radio" name="transportmodus" value="{{ modus }}" {% if transportmodus == modus or (not transportmodus and loop.first) %}checked{% endif %} style="margin-right:8px;">
        <span style="font-weight:700;color:var(--gray-800);font-size:13px;">{{ modus }}</span>
        <div style="font-size:11.5px;color:var(--gray-400);margin-top:4px;margin-left:22px;">{% if modus == "Schip" %}Voor lange afstand / intercontinentaal{% else %}Voor korte tot middellange afstand{% endif %}</div>
    </label>
    {% endfor %}
</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px;">
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Klant (doorverkocht aan)</label>
        <input type="text" name="klant" list="klanten_datalist" autocomplete="off" value="{{ klant|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        <datalist id="klanten_datalist">{% for naam in klant_namen %}<option value="{{ naam }}">{% endfor %}</datalist>
    </div>
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">POD (loshaven)</label>
        <input type="text" name="pod_haven" list="pod_havens_datalist" autocomplete="off" value="{{ pod_haven|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        <datalist id="pod_havens_datalist">{% for h in pod_havens %}<option value="{{ h }}">{% endfor %}</datalist>
    </div>
</div>

<div style="margin:24px 0 14px 0;padding:12px 14px;background:#fef2f2;border-radius:8px;">
    <div style="font-size:11px;font-weight:800;color:#b91c1c;text-transform:uppercase;letter-spacing:0.06em;">Intern — dit ziet de leverancier nooit</div>
    <div style="font-size:11.5px;color:#991b1b;margin-top:2px;">Deze cijfers verschijnen nooit op het contract of in de mail naar de leverancier. Puur voor de eigen margeberekening.</div>
</div>
<div id="pern_blok" style="display:none;margin-bottom:10px;max-width:260px;">
    <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">PERN (£, alleen UK-markt)</label>
    <input type="text" name="pern_gbp" value="{{ pern_gbp|default('')}}" placeholder="Schommelt dagelijk, zelf invullen" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
    <div style="font-size:10.5px;color:var(--gray-300);margin-top:2px;">Gaat van de inkoopprijs af (we ontvangen dit).</div>
</div>
<div style="display:grid;grid-template-columns:2fr 1fr;gap:10px;margin-bottom:10px;">
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Verkoopprijs (per MT)</label>
        <input type="text" name="berekende_verkoopprijs" value="{{ berekende_verkoopprijs|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
    </div>
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Valuta</label>
        <select name="verkoopprijs_valuta" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
            {% for v in valuta_lijst %}<option value="{{ v }}" {% if verkoopprijs_valuta == v %}selected{% endif %}>{{ v }}</option>{% endfor %}
        </select>
    </div>
</div>
<div style="display:grid;grid-template-columns:2fr 1fr;gap:10px;margin-bottom:10px;">
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Transportkosten (totaal)</label>
        <input type="text" name="berekende_transportkosten" value="{{ berekende_transportkosten|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
    </div>
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Valuta</label>
        <select name="transportkosten_valuta" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
            {% for v in valuta_lijst %}<option value="{{ v }}" {% if transportkosten_valuta == v %}selected{% endif %}>{{ v }}</option>{% endfor %}
        </select>
    </div>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px;">
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Gemiddeld laadgewicht (per rit, in MT)</label>
        <input type="text" name="gemiddeld_laadgewicht" value="{{ gemiddeld_laadgewicht|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        <div style="font-size:10.5px;color:var(--gray-300);margin-top:2px;">Voor: transportkosten ÷ laadgewicht = transportkosten per MT</div>
    </div>
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Extra kosten per MT (€)</label>
        <input type="text" name="extra_kosten_per_mt" value="{{ extra_kosten_per_mt|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
    </div>
</div>
<div style="font-size:11px;color:var(--gray-300);margin-bottom:16px;">Kostprijs en winst (per MT en totaal) worden automatisch in euro berekend na opslaan — met de live wisselkoers van dit moment, die daarna vastligt voor deze order.</div>

<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin:20px 0 10px 0;">Opmerkingen</div>
<div style="margin-bottom:16px;">
    <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Order remarks</label>
    <textarea name="opmerkingen" rows="2" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">{{ opmerkingen|default('') }}</textarea>
</div>
<div style="margin-bottom:20px;">
    <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Notities per afdeling</label>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:6px;">
        {% for a in afdelingen %}
        <div>
            <label style="font-size:10.5px;color:var(--gray-400);">{{ afdeling_labels.get(a, a) }}</label>
            <input type="text" name="notitie_{{ a }}" value="{{ afdeling_notities.get(a, '') if afdeling_notities else '' }}" style="width:100%;padding:6px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;box-sizing:border-box;font-family:inherit;">
        </div>
        {% endfor %}
    </div>
</div>

<button type="submit" style="padding:10px 24px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">Opslaan als concept</button>
<a href="/handelsorders" style="margin-left:10px;font-size:12.5px;color:var(--gray-400);text-decoration:none;">Annuleren</a>
</form>

<script>
var TAXONOMIE = {{ taxonomie_json|safe }};
function toonPernIndienUK() {
    var select = document.getElementById("bedrijfseenheid_select");
    var pernBlok = document.getElementById("pern_blok");
    if (select && pernBlok) {
        pernBlok.style.display = (select.value === "UK") ? "block" : "none";
    }
}
document.addEventListener("DOMContentLoaded", toonPernIndienUK);
function verversKwaliteiten() {
    var materiaal = document.getElementById("materiaal_input").value;
    var kwaliteitDatalist = document.getElementById("kwaliteit_datalist");
    var kwaliteiten = TAXONOMIE[materiaal] || [];
    kwaliteitDatalist.innerHTML = "";
    kwaliteiten.forEach(function(k) {
        var optie = document.createElement("option");
        optie.value = k;
        kwaliteitDatalist.appendChild(optie);
    });
}
var HUIDIGE_LOCATIES = [];
async function laadLeverancierInfo() {
    var naam = document.getElementById("leverancier_input").value;
    if (!naam) return;
    try {
        const res = await fetch("/api/leverancier-info?naam=" + encodeURIComponent(naam));
        const data = await res.json();
        HUIDIGE_LOCATIES = data.afhaallocaties || [];
        if (data.standaard_betalingstermijn) {
            document.getElementById("betalingstermijn_select").value = data.standaard_betalingstermijn;
        }
        var keuzeBlok = document.getElementById("afhaal_keuze_blok");
        var select = document.getElementById("afhaal_locatie_select");
        if (HUIDIGE_LOCATIES.length === 1) {
            keuzeBlok.style.display = "none";
            _vulLocatieVelden(HUIDIGE_LOCATIES[0]);
        } else if (HUIDIGE_LOCATIES.length > 1) {
            keuzeBlok.style.display = "block";
            select.innerHTML = '<option value="">— kies locatie —</option>';
            HUIDIGE_LOCATIES.forEach(function(loc, i) {
                var optie = document.createElement("option");
                optie.value = i;
                optie.textContent = (loc.naam || loc.stad) + " — " + loc.stad;
                select.appendChild(optie);
            });
        } else {
            keuzeBlok.style.display = "none";
        }
    } catch (e) {}
}
function vulAfhaallocatieIn() {
    var index = document.getElementById("afhaal_locatie_select").value;
    if (index === "") return;
    _vulLocatieVelden(HUIDIGE_LOCATIES[parseInt(index)]);
}
function _vulLocatieVelden(loc) {
    document.getElementById("afhaal_locatienaam").value = loc.naam || "";
    document.getElementById("afhaal_adres").value = loc.adres || "";
    document.getElementById("afhaal_postcode").value = loc.postcode || "";
    document.getElementById("afhaal_stad").value = loc.stad || "";
    document.getElementById("afhaal_land").value = loc.land || "";
}
(function() {
    var formGewijzigd = false;
    var formulier = document.querySelector("form");
    if (formulier) {
        formulier.addEventListener("input", function() { formGewijzigd = true; });
        formulier.addEventListener("change", function() { formGewijzigd = true; });
        formulier.addEventListener("submit", function() { formGewijzigd = false; });
    }
    window.addEventListener("beforeunload", function(e) {
        if (formGewijzigd) { e.preventDefault(); e.returnValue = ""; }
    });
})();
</script>
    """

@handelsorders_bp.route("/handelsorders/nieuw/verkoop", methods=["GET", "POST"])
def handelsorders_nieuw_verkoop():
    _guard = vereist_afdeling_of_403("handelsorders")
    if _guard: return _guard

    if request.method == "POST":
        orders = laad_handelsorders()
        nu = datetime.datetime.now()
        nieuw = {
            "id": str(uuid.uuid4()),
            "order_type": "verkoop",
            "contractnummer": genereer_contractnummer(orders, "verkoop"),
            "tegenpartij_naam": request.form.get("klant", "").strip(),
            "bedrijfseenheid": request.form.get("bedrijfseenheid", "").strip(),
            "datum_aangemaakt": request.form.get("datum_aangemaakt", "") or nu.date().isoformat(),
            "incoterm": request.form.get("incoterm", "").strip(),
            "betalingstermijn": request.form.get("betalingstermijn", "").strip(),
            "materiaal": request.form.get("materiaal", "").strip(),
            "kwaliteit": request.form.get("kwaliteit", "").strip(),
            "startdatum": request.form.get("startdatum", "") or nu.date().isoformat(),
            "einddatum": request.form.get("einddatum", "").strip(),
            "valuta": request.form.get("valuta", "").strip(),
            "hoeveelheid_mt": request.form.get("hoeveelheid_mt", "").strip(),
            "prijs": request.form.get("prijs", "").strip(),
            "lever_adres": request.form.get("lever_adres", "").strip(),
            "lever_postcode": request.form.get("lever_postcode", "").strip(),
            "lever_stad": request.form.get("lever_stad", "").strip(),
            "lever_land": request.form.get("lever_land", "").strip(),
            "transportmodus": request.form.get("transportmodus", "").strip(),
            "leverancier": request.form.get("leverancier", "").strip(),
            "pod_haven": request.form.get("pod_haven", "").strip(),
            "opmerkingen": request.form.get("opmerkingen", "").strip(),
            "afdeling_notities": {a: request.form.get(f"notitie_{a}", "").strip() for a in AFDELINGEN},
            "status": "Concept",
            "aangemaakt_door": session.get("gebruikersnaam", ""),
            "aangemaakt": nu.strftime("%d-%m-%Y %H:%M"),
        }
        orders.append(nieuw)
        bewaar_handelsorders(orders)
        return redirect(url_for("handelsorders.handelsorder_detail", order_id=nieuw["id"]))

    inhoud = _verkoop_formulier_html()
    pagina = render_simple_page("Nieuwe verkooporder", "handelsorders", inhoud)
    return render_template_string(pagina, **_formulier_context())

def _verkoop_formulier_html():
    return """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/handelsorders" style="color:var(--gray-400);text-decoration:none;">Handelsorders</a> &nbsp;/&nbsp; <a href="/handelsorders/nieuw" style="color:var(--gray-400);text-decoration:none;">Nieuw</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">Verkoop</span>
</div>
<div class="page-title">Nieuwe verkooporder</div>

<form method="POST" style="max-width:720px;">
<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin:20px 0 10px 0;">Basisinformatie</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Klant *</label>
        <input type="text" name="klant" list="klanten_datalist" required autocomplete="off" value="{{ klant|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        <datalist id="klanten_datalist">{% for naam in klant_namen %}<option value="{{ naam }}">{% endfor %}</datalist>
    </div>
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Bedrijfseenheid</label>
        <select name="bedrijfseenheid" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
            <option value="">— kies —</option>
            {% for be in bedrijfseenheden %}<option value="{{ be }}" {% if bedrijfseenheid == be %}selected{% endif %}>{{ be }}</option>{% endfor %}
        </select>
    </div>
</div>
<div style="margin-bottom:16px;max-width:240px;">
    <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Datum aangemaakt</label>
    <input type="date" name="datum_aangemaakt" value="{{ vandaag }}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;">
</div>

<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin:20px 0 10px 0;">Deal informatie</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Incoterm</label>
        <select name="incoterm" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
            <option value="">— kies —</option>
            {% for i in incoterms %}<option value="{{ i }}" {% if incoterm == i %}selected{% endif %}>{{ i }}</option>{% endfor %}
        </select>
    </div>
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Betalingstermijn</label>
        <select name="betalingstermijn" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
            <option value="">— kies —</option>
            {% for b in betalingstermijnen %}<option value="{{ b }}" {% if betalingstermijn == b %}selected{% endif %}>{{ b }}</option>{% endfor %}
        </select>
    </div>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px;">
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Materiaal *</label>
        <input type="text" name="materiaal" id="materiaal_input" list="materiaal_datalist" required autocomplete="off" oninput="verversKwaliteiten()" value="{{ materiaal|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        <datalist id="materiaal_datalist">{% for m in materiaal_namen %}<option value="{{ m }}">{% endfor %}</datalist>
    </div>
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Kwaliteit *</label>
        <input type="text" name="kwaliteit" id="kwaliteit_input" list="kwaliteit_datalist" required autocomplete="off" placeholder="Kies eerst materiaal..." value="{{ kwaliteit|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        <datalist id="kwaliteit_datalist"></datalist>
    </div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Startdatum order</label>
        <input type="date" name="startdatum" value="{{ vandaag }}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;">
    </div>
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Einddatum order</label>
        <input type="date" name="einddatum" value="{{ einddatum|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;">
    </div>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:16px;">
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Valuta</label>
        <select name="valuta" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
            {% for v in valuta_lijst %}<option value="{{ v }}" {% if valuta == v %}selected{% endif %}>{{ v }}</option>{% endfor %}
        </select>
    </div>
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Hoeveelheid (MT)</label>
        <input type="text" name="hoeveelheid_mt" value="{{ hoeveelheid_mt|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
    </div>
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Verkoopprijs (per MT)</label>
        <input type="text" name="prijs" value="{{ prijs|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
    </div>
</div>

<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin:20px 0 10px 0;">Leverlocatie</div>
<div style="margin-bottom:10px;">
    <input type="text" name="lever_adres" placeholder="Adres" value="{{ lever_adres|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
</div>
<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:16px;">
    <input type="text" name="lever_postcode" placeholder="Postcode" value="{{ lever_postcode|default('')}}" style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
    <input type="text" name="lever_stad" placeholder="Stad" value="{{ lever_stad|default('')}}" style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
    <input type="text" name="lever_land" placeholder="Land" value="{{ lever_land|default('')}}" style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
</div>

<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin:20px 0 10px 0;">Transport &amp; herkomst</div>
<div style="display:flex;gap:12px;margin-bottom:16px;">
    {% for modus in transportmodi %}
    <label style="flex:1;border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);padding:14px 16px;cursor:pointer;display:block;">
        <input type="radio" name="transportmodus" value="{{ modus }}" {% if transportmodus == modus or (not transportmodus and loop.first) %}checked{% endif %} style="margin-right:8px;">
        <span style="font-weight:700;color:var(--gray-800);font-size:13px;">{{ modus }}</span>
        <div style="font-size:11.5px;color:var(--gray-400);margin-top:4px;margin-left:22px;">{% if modus == "Schip" %}Voor lange afstand / intercontinentaal{% else %}Voor korte tot middellange afstand{% endif %}</div>
    </label>
    {% endfor %}
</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px;">
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Leverancier (herkomst materiaal, indien bekend)</label>
        <input type="text" name="leverancier" list="leveranciers_datalist" autocomplete="off" value="{{ leverancier|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        <datalist id="leveranciers_datalist">{% for naam in leverancier_namen %}<option value="{{ naam }}">{% endfor %}</datalist>
    </div>
    <div>
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">POD (loshaven)</label>
        <input type="text" name="pod_haven" list="pod_havens_datalist" autocomplete="off" value="{{ pod_haven|default('')}}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        <datalist id="pod_havens_datalist">{% for h in pod_havens %}<option value="{{ h }}">{% endfor %}</datalist>
    </div>
</div>

<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin:20px 0 10px 0;">Opmerkingen</div>
<div style="margin-bottom:16px;">
    <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Order remarks</label>
    <textarea name="opmerkingen" rows="2" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">{{ opmerkingen|default('') }}</textarea>
</div>
<div style="margin-bottom:20px;">
    <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Notities per afdeling</label>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:6px;">
        {% for a in afdelingen %}
        <div>
            <label style="font-size:10.5px;color:var(--gray-400);">{{ afdeling_labels.get(a, a) }}</label>
            <input type="text" name="notitie_{{ a }}" value="{{ afdeling_notities.get(a, '') if afdeling_notities else '' }}" style="width:100%;padding:6px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;box-sizing:border-box;font-family:inherit;">
        </div>
        {% endfor %}
    </div>
</div>

<button type="submit" style="padding:10px 24px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">Opslaan als concept</button>
<a href="/handelsorders" style="margin-left:10px;font-size:12.5px;color:var(--gray-400);text-decoration:none;">Annuleren</a>
</form>

<script>
var TAXONOMIE = {{ taxonomie_json|safe }};
function verversKwaliteiten() {
    var materiaal = document.getElementById("materiaal_input").value;
    var kwaliteitDatalist = document.getElementById("kwaliteit_datalist");
    var kwaliteiten = TAXONOMIE[materiaal] || [];
    kwaliteitDatalist.innerHTML = "";
    kwaliteiten.forEach(function(k) {
        var optie = document.createElement("option");
        optie.value = k;
        kwaliteitDatalist.appendChild(optie);
    });
}
(function() {
    var formGewijzigd = false;
    var formulier = document.querySelector("form");
    if (formulier) {
        formulier.addEventListener("input", function() { formGewijzigd = true; });
        formulier.addEventListener("change", function() { formGewijzigd = true; });
        formulier.addEventListener("submit", function() { formGewijzigd = false; });
    }
    window.addEventListener("beforeunload", function(e) {
        if (formGewijzigd) { e.preventDefault(); e.returnValue = ""; }
    });
})();
</script>
    """

@handelsorders_bp.route("/handelsorders/<order_id>/notitie", methods=["POST"])
def handelsorder_notitie_toevoegen(order_id):
    """Voegt een tijdgestempelde notitie toe aan het doorlopende activiteitenlog van
    een order — los van de vaste afdeling_notities-velden (die maar één waarde per
    afdeling hebben en alleen bij aanmaken/bewerken ingevuld worden). Dit hier is
    een groeiende lijst, zodat iedereen die met de order te maken krijgt een
    kanttekening kan achterlaten, ook nadat de order al Definitief is."""
    _guard = vereist_afdeling_of_403("handelsorders")
    if _guard: return _guard

    orders = laad_handelsorders()
    order = next((o for o in orders if o["id"] == order_id), None)
    if order:
        tekst = request.form.get("notitie_tekst", "").strip()
        if tekst:
            order.setdefault("activiteitenlog", []).append({
                "tekst": tekst,
                "gebruiker": session.get("gebruikersnaam", ""),
                "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
            })
            bewaar_handelsorders(orders)
    return redirect(url_for("handelsorders.handelsorder_detail", order_id=order_id))

@handelsorders_bp.route("/handelsorders/<order_id>")
def handelsorder_detail(order_id):
    _guard = vereist_afdeling_of_403("handelsorders")
    if _guard: return _guard

    orders = laad_handelsorders()
    order = next((o for o in orders if o["id"] == order_id), None)
    if not order:
        pagina = render_simple_page("Niet gevonden", "handelsorders", '<div class="page-title">Order niet gevonden</div><div class="lege-staat">Deze order bestaat niet (meer). <a href="/handelsorders">Terug naar Handelsorders</a></div>')
        return render_template_string(pagina), 404

    # Voor definitieve verkooporders: check of er al een factuur aan dit contract
    # gekoppeld is (voorkomt dubbel factureren), en bereken de voorinvulling voor
    # het geval er nog geen is.
    bestaande_factuur = None
    factuur_vervaldatum_voorstel = ""
    factuur_bedrag_voorstel = ""
    if order.get("order_type") == "verkoop" and order.get("status") == "Definitief":
        bestaande_factuur = next((f for f in laad_facturen() if f.get("contract_referentie") == order["contractnummer"]), None)
        if bestaande_factuur:
            bestaande_factuur["status"] = bepaal_factuur_status(bestaande_factuur)
        if not bestaande_factuur:
            try:
                factuur_bedrag_voorstel = str(round(_getal(order.get("prijs")) * _getal(order.get("hoeveelheid_mt")), 2))
            except (ValueError, TypeError):
                factuur_bedrag_voorstel = ""
            _betalingstermijn_dagen = None
            _match = re.search(r"(\d+)\s*dagen", order.get("betalingstermijn","") or "")
            if _match:
                _betalingstermijn_dagen = int(_match.group(1))
            if _betalingstermijn_dagen is not None:
                factuur_vervaldatum_voorstel = (datetime.date.today() + datetime.timedelta(days=_betalingstermijn_dagen)).isoformat()

    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/handelsorders" style="color:var(--gray-400);text-decoration:none;">Handelsorders</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">{{ order.contractnummer }}</span>
</div>
<div class="page-title">{{ order.contractnummer }}</div>
<div style="margin-bottom:20px;">
    {% if order.status == "Definitief" %}<span style="font-size:12.5px;font-weight:700;color:#16a34a;">Definitief</span>
    {% else %}<span style="font-size:12.5px;font-weight:700;color:var(--gray-500);">Concept</span>{% endif %}
    <span style="color:var(--gray-300);margin:0 8px;">·</span>
    <span style="font-size:12.5px;color:var(--gray-500);">{{ "Inkoop" if order.order_type == "inkoop" else "Verkoop" }}</span>
</div>

<div style="background:var(--gray-50);border-radius:8px;padding:18px 20px;font-size:12.5px;color:var(--gray-600);max-width:720px;margin-bottom:20px;">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
        <div><b>{{ "Leverancier" if order.order_type == "inkoop" else "Klant" }}:</b> {{ order.tegenpartij_naam or '—' }}</div>
        <div><b>Bedrijfseenheid:</b> {{ order.bedrijfseenheid or '—' }}</div>
        <div><b>Materiaal:</b> {{ order.materiaal or '—' }} — {{ order.kwaliteit or '—' }}</div>
        <div><b>Incoterm:</b> {{ order.incoterm or '—' }}</div>
        <div><b>Betalingstermijn:</b> {{ order.betalingstermijn or '—' }}</div>
        {% if order.order_type == "inkoop" %}<div><b>Supplier Reference:</b> {{ order.supplier_reference or '—' }}</div>{% endif %}
        <div><b>Startdatum:</b> {{ order.startdatum or '—' }}</div>
        <div><b>Einddatum:</b> {{ order.einddatum or '—' }}</div>
        <div><b>Hoeveelheid:</b> {{ order.hoeveelheid_mt or '—' }}{% if order.hoeveelheid_mt %} MT{% endif %}</div>
        <div><b>Prijs:</b> {% if order.prijs %}{{ order.valuta }} {{ order.prijs }} / MT{% else %}—{% endif %}</div>
        <div><b>Transportmodus:</b> {{ order.transportmodus or '—' }}</div>
        <div><b>POD:</b> {{ order.pod_haven or '—' }}</div>
        {% if order.order_type == "inkoop" %}
        <div><b>Klant (doorverkocht aan):</b> {{ order.klant or '—' }}</div>
        {% else %}
        <div><b>Leverancier (herkomst):</b> {{ order.leverancier or '—' }}</div>
        {% endif %}
    </div>
    {% if order.order_type == "inkoop" and order.afhaal_adres %}
    <div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--gray-200);"><b>Afhaallocatie:</b> {{ order.afhaal_locatienaam }} — {{ order.afhaal_adres }}, {{ order.afhaal_postcode }} {{ order.afhaal_stad }}, {{ order.afhaal_land }}</div>
    {% elif order.order_type == "verkoop" and order.lever_adres %}
    <div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--gray-200);"><b>Leverlocatie:</b> {{ order.lever_adres }}, {{ order.lever_postcode }} {{ order.lever_stad }}, {{ order.lever_land }}</div>
    {% endif %}
    {% if order.opmerkingen %}<div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--gray-200);"><b>Opmerkingen:</b> {{ order.opmerkingen }}</div>{% endif %}
    {% set notities_ingevuld = order.afdeling_notities.items()|selectattr('1')|list %}
    {% if notities_ingevuld %}
    <div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--gray-200);">
        <b>Notities per afdeling:</b>
        {% for afd, notitie in notities_ingevuld %}<div style="margin-top:4px;">— {{ afdeling_labels.get(afd, afd) }}: {{ notitie }}</div>{% endfor %}
    </div>
    {% endif %}
</div>

{% if order.order_type == "inkoop" %}
<div style="background:#fef2f2;border-radius:8px;padding:14px 20px;font-size:12.5px;color:#7f1d1d;max-width:720px;margin-bottom:20px;">
    <div style="font-size:11px;font-weight:800;color:#b91c1c;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Intern — nooit naar de leverancier</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
        {% if order.bedrijfseenheid == "UK" %}
        <div><b>PERN (£):</b> {{ order.pern_gbp or '—' }}</div>
        <div><b>PERN in €:</b> {% if order.pern_eur %}€{{ order.pern_eur }}{% else %}—{% endif %}</div>
        <div><b>Inkoopprijs na PERN (€):</b> {% if order.effectieve_inkoopprijs_eur is not none %}€{{ order.effectieve_inkoopprijs_eur }}{% else %}—{% endif %}</div>
        {% endif %}
        <div><b>Verkoopprijs:</b> {% if order.berekende_verkoopprijs %}{{ order.verkoopprijs_valuta }} {{ order.berekende_verkoopprijs }}/MT{% else %}—{% endif %}</div>
        <div><b>Transportkosten (totaal):</b> {% if order.berekende_transportkosten %}{{ order.transportkosten_valuta }} {{ order.berekende_transportkosten }}{% else %}—{% endif %}</div>
        <div><b>Gem. laadgewicht:</b> {{ order.gemiddeld_laadgewicht or '—' }}{% if order.gemiddeld_laadgewicht %} MT{% endif %}</div>
        <div><b>Transportkosten per MT:</b> {% if order.transportkosten_per_mt_eur %}€{{ order.transportkosten_per_mt_eur }}{% else %}—{% endif %}</div>
        <div><b>Extra kosten per MT:</b> {% if order.extra_kosten_per_mt %}€{{ order.extra_kosten_per_mt }}{% else %}—{% endif %}</div>
        <div><b>Kostprijs (per MT):</b> {% if order.kostprijs_eur is not none %}€{{ order.kostprijs_eur }}{% else %}—{% endif %}</div>
        <div><b>Winst per MT:</b> {% if order.winst_per_mt_eur is not none %}€{{ order.winst_per_mt_eur }}{% else %}—{% endif %}</div>
        <div><b>Winst totaal (order):</b> {% if order.winst_totaal_eur is not none %}€{{ order.winst_totaal_eur }}{% else %}—{% endif %}</div>
    </div>
    {% if order.wisselkoers_vastgelegd %}
    <div style="margin-top:10px;padding-top:10px;border-top:1px solid #fecaca;font-size:11px;color:#991b1b;">
        Wisselkoersen vastgelegd bij aanmaken (blijven ongewijzigd): inkoop 1 {{ order.valuta }} = €{{ "%.4f"|format(order.wisselkoers_vastgelegd.inkoop) }},
        verkoop 1 {{ order.verkoopprijs_valuta }} = €{{ "%.4f"|format(order.wisselkoers_vastgelegd.verkoop) }},
        transport 1 {{ order.transportkosten_valuta }} = €{{ "%.4f"|format(order.wisselkoers_vastgelegd.transport) }}
    </div>
    {% endif %}
</div>
{% endif %}

<div style="display:flex;gap:10px;align-items:center;">
    {% if order.status == "Concept" %}
    <a href="/handelsorders/{{ order.id }}/bewerken" style="padding:9px 18px;background:#fff;color:var(--gray-700);border:1px solid var(--gray-200);text-decoration:none;border-radius:6px;font-size:13px;font-weight:700;">Wijzigen</a>
    <form method="POST" action="/handelsorders/{{ order.id }}/goedkeuren" onsubmit="return confirm('Order goedkeuren en versturen? Dit maakt de order definitief en kan niet ongedaan gemaakt worden.');" style="margin:0;">
        <button type="submit" style="padding:9px 18px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">Goedkeuren en versturen</button>
    </form>
    {% else %}
    <a href="/handelsorders/{{ order.id }}/pdf" target="_blank" style="padding:9px 18px;background:var(--brand-600);color:#fff;text-decoration:none;border-radius:6px;font-size:13px;font-weight:700;">Contract downloaden (PDF)</a>
    <span style="font-size:11.5px;color:var(--gray-400);">Verstuurd naar {{ order.tegenpartij_naam }} · boekhoudkoppeling: infrastructuur gereed, nog niet actief</span>
    {% if order.order_type == "verkoop" %}
        {% if bestaande_factuur %}
        <a href="/facturen?bedrijf={{ order.tegenpartij_naam|urlencode }}" style="padding:9px 18px;background:#fff;color:var(--gray-700);border:1px solid var(--gray-200);text-decoration:none;border-radius:6px;font-size:13px;font-weight:700;">Factuur bekijken ({{ bestaande_factuur.status }})</a>
        {% else %}
        <a href="/facturen?bedrijf={{ order.tegenpartij_naam|urlencode }}&contract_referentie={{ order.contractnummer|urlencode }}&referentie={{ order.contractnummer|urlencode }}&bedrag={{ factuur_bedrag_voorstel }}&vervaldatum={{ factuur_vervaldatum_voorstel }}" style="padding:9px 18px;background:#fff;color:var(--gray-700);border:1px solid var(--gray-200);text-decoration:none;border-radius:6px;font-size:13px;font-weight:700;">Factuur aanmaken →</a>
        {% endif %}
    {% endif %}
    {% endif %}
</div>

<div style="margin-top:28px;max-width:720px;">
    <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Activiteitenlog</div>
    {% if order.activiteitenlog %}
    <div style="border:none;border-top:1px solid var(--gray-200);margin-bottom:14px;">
        {% for regel in order.activiteitenlog|reverse %}
        <div style="padding:10px 0;border-bottom:1px solid var(--gray-100);font-size:12.5px;color:var(--gray-700);">
            {{ regel.tekst }}
            <div style="font-size:11px;color:var(--gray-400);margin-top:2px;">{{ regel.gebruiker }} · {{ regel.aangemaakt }}</div>
        </div>
        {% endfor %}
    </div>
    {% else %}
    <div style="font-size:12px;color:var(--gray-300);margin-bottom:14px;">Nog geen notities toegevoegd.</div>
    {% endif %}
    <form method="POST" action="/handelsorders/{{ order.id }}/notitie">
        <textarea name="notitie_tekst" rows="2" placeholder="Notitie toevoegen (bv. vraag, update, bijzonderheid)..." required style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;margin-bottom:8px;"></textarea>
        <button type="submit" style="padding:7px 16px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:12.5px;font-weight:700;cursor:pointer;">Notitie toevoegen</button>
    </form>
</div>
    """
    pagina = render_simple_page(order["contractnummer"], "handelsorders", inhoud)
    return render_template_string(pagina, order=order, afdeling_labels=AFDELING_LABELS,
                                    bestaande_factuur=bestaande_factuur,
                                    factuur_bedrag_voorstel=factuur_bedrag_voorstel,
                                    factuur_vervaldatum_voorstel=factuur_vervaldatum_voorstel)

@handelsorders_bp.route("/handelsorders/<order_id>/bewerken", methods=["GET", "POST"])
def handelsorder_bewerken(order_id):
    _guard = vereist_afdeling_of_403("handelsorders")
    if _guard: return _guard

    orders = laad_handelsorders()
    order = next((o for o in orders if o["id"] == order_id), None)
    if not order:
        pagina = render_simple_page("Niet gevonden", "handelsorders", '<div class="page-title">Order niet gevonden</div><div class="lege-staat">Deze order bestaat niet (meer). <a href="/handelsorders">Terug</a></div>')
        return render_template_string(pagina), 404
    if order["status"] != "Concept":
        return redirect(url_for("handelsorders.handelsorder_detail", order_id=order_id))

    velden = ["bedrijfseenheid", "datum_aangemaakt", "incoterm", "betalingstermijn", "materiaal", "kwaliteit",
              "startdatum", "einddatum", "valuta", "hoeveelheid_mt", "prijs", "transportmodus", "pod_haven", "opmerkingen"]
    if order["order_type"] == "inkoop":
        velden += ["afhaal_locatienaam", "afhaal_adres", "afhaal_postcode", "afhaal_stad", "afhaal_land",
                   "berekende_verkoopprijs", "verkoopprijs_valuta", "berekende_transportkosten", "transportkosten_valuta",
                   "gemiddeld_laadgewicht", "extra_kosten_per_mt", "pern_gbp", "klant"]
    else:
        velden += ["lever_adres", "lever_postcode", "lever_stad", "lever_land", "leverancier"]

    if request.method == "POST":
        for veld in velden:
            order[veld] = request.form.get(veld, "").strip()
        if order["order_type"] == "inkoop":
            nieuwe_leverancier = request.form.get("leverancier", "").strip()
            if nieuwe_leverancier and nieuwe_leverancier != order.get("tegenpartij_naam"):
                order["tegenpartij_naam"] = nieuwe_leverancier
        else:
            nieuwe_klant = request.form.get("klant", "").strip()
            if nieuwe_klant and nieuwe_klant != order.get("tegenpartij_naam"):
                order["tegenpartij_naam"] = nieuwe_klant
        order["afdeling_notities"] = {a: request.form.get(f"notitie_{a}", "").strip() for a in AFDELINGEN}
        # Marge herberekenen met de gewijzigde velden — maar met de wisselkoersen die
        # al bij het aanmaken zijn vastgelegd. Die worden hier NOOIT opnieuw opgehaald.
        if order["order_type"] == "inkoop":
            marge_resultaat = _bereken_marge_intern(order)
            order["pern_eur"] = marge_resultaat["pern_eur"]
            order["effectieve_inkoopprijs_eur"] = marge_resultaat["effectieve_inkoopprijs_eur"]
            order["kostprijs_eur"] = marge_resultaat["kostprijs_eur"]
            order["winst_per_mt_eur"] = marge_resultaat["winst_per_mt_eur"]
            order["winst_totaal_eur"] = marge_resultaat["winst_totaal_eur"]
            order["transportkosten_per_mt_eur"] = marge_resultaat["transportkosten_per_mt_eur"]
            order["berekende_marge"] = str(marge_resultaat["winst_totaal_eur"])
        bewaar_handelsorders(orders)
        return redirect(url_for("handelsorders.handelsorder_detail", order_id=order_id))

    if order["order_type"] == "inkoop":
        inhoud = _inkoop_formulier_html().replace('action=""', "").replace(
            '<form method="POST"', f'<form method="POST" action="/handelsorders/{order_id}/bewerken"'
        )
        titel = "Inkooporder wijzigen"
    else:
        inhoud = _verkoop_formulier_html().replace(
            '<form method="POST"', f'<form method="POST" action="/handelsorders/{order_id}/bewerken"'
        )
        titel = "Verkooporder wijzigen"
    pagina = render_simple_page(titel, "handelsorders", inhoud)
    context = _formulier_context()
    context.update(order)
    if order["order_type"] == "inkoop":
        context["leverancier"] = order.get("tegenpartij_naam", "")
    else:
        context["klant"] = order.get("tegenpartij_naam", "")
    return render_template_string(pagina, **context)

def _stuur_naar_boekhoudpakket(order):
    """Placeholder voor de boekhoudkoppeling. Nu nog geen daadwerkelijke verbinding,
    maar deze functie is het vaste aanknopingspunt: zodra er credentials/API-details
    voor het boekhoudpakket zijn, hoeft alleen déze functie ingevuld te worden — de
    rest van de workflow (wanneer het aangeroepen wordt, met welke data) staat al klaar."""
    return {"verstuurd": False, "reden": "Boekhoudkoppeling nog niet actief."}

def _stuur_contractmail_naar_tegenpartij(order, pdf_bytes):
    """Placeholder voor het automatisch e-mailen van de orderbevestiging naar de
    leverancier/klant. Nu nog geen daadwerkelijke verbinding, maar dit is het vaste
    aanknopingspunt voor zodra er een e-mailaccount/SMTP-koppeling beschikbaar is."""
    return {"verstuurd": False, "reden": "E-mailkoppeling nog niet actief."}

def _log_marktprijs_bij_definitief(order):
    """Legt automatisch een marktprijspunt vast zodra een order definitief wordt —
    zelfde principe als het oude orders.json-systeem deed bij 'Gewonnen', nu voor
    het huidige, actieve Handelsorders-systeem. Prijs wordt altijd in euro
    vastgelegd: voor inkoop via de al-vastgelegde wisselkoers (nooit opnieuw
    opgehaald), voor verkoop via een live koers op het moment van definitief maken
    (verkooporders leggen geen koers vooraf vast, dus die is er nog niet)."""
    if not order.get("materiaal") or not order.get("prijs"):
        return
    try:
        _prijs = float(str(order["prijs"]).replace(",", "."))
    except (ValueError, TypeError):
        return
    if _prijs <= 0:
        return
    _valuta = order.get("valuta", "EUR")
    if order.get("order_type") == "inkoop":
        _koers = (order.get("wisselkoers_vastgelegd") or {}).get("inkoop", 1.0)
    else:
        _koers, _ = haal_live_wisselkoers(_valuta, "EUR") if _valuta != "EUR" else (1.0, True)
    _prijs_eur = round(_prijs * _koers, 2)

    _marktprijzen = laad_marktprijzen()
    _marktprijzen.append({
        "id": str(uuid.uuid4()), "materiaal": order["materiaal"],
        "prijs_per_ton": _prijs_eur, "bron": "handelsorder",
        "bedrijf": order.get("tegenpartij_naam", ""), "order_id": order["id"],
        "notitie": f"{order.get('contractnummer','')} ({order.get('kwaliteit','')})" if order.get("kwaliteit") else order.get("contractnummer",""),
        "gebruiker": session.get("gebruikersnaam", ""),
        "datum": datetime.date.today().isoformat(),
        "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
    })
    bewaar_marktprijzen(_marktprijzen)

@handelsorders_bp.route("/handelsorders/<order_id>/goedkeuren", methods=["POST"])
def handelsorder_goedkeuren(order_id):
    _guard = vereist_afdeling_of_403("handelsorders")
    if _guard: return _guard

    orders = laad_handelsorders()
    order = next((o for o in orders if o["id"] == order_id), None)
    if order and order["status"] == "Concept":
        order["status"] = "Definitief"
        order["goedgekeurd_door"] = session.get("gebruikersnaam", "")
        order["goedgekeurd_op"] = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
        bewaar_handelsorders(orders)

        pdf_bytes = _genereer_contract_pdf(order)
        order["boekhoud_resultaat"] = _stuur_naar_boekhoudpakket(order)
        order["email_resultaat"] = _stuur_contractmail_naar_tegenpartij(order, pdf_bytes)
        bewaar_handelsorders(orders)

        _log_marktprijs_bij_definitief(order)

    return redirect(url_for("handelsorders.handelsorder_detail", order_id=order_id))

def _genereer_contract_pdf(order):
    """Bouwt het contract/de orderbevestiging als PDF."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm, leftMargin=20*mm, rightMargin=20*mm)
    stijlen = getSampleStyleSheet()
    titel_stijl = ParagraphStyle("ContractTitel", parent=stijlen["Title"], fontSize=18, textColor=colors.HexColor("#0d5c62"))
    label_stijl = ParagraphStyle("Label", parent=stijlen["Normal"], fontSize=9, textColor=colors.HexColor("#64748b"))

    elementen = [
        Paragraph("Inkoopcontract" if order["order_type"] == "inkoop" else "Verkoopcontract", titel_stijl),
        Paragraph(f"Contractnummer: <b>{order['contractnummer']}</b>", stijlen["Normal"]),
        Spacer(1, 14),
    ]

    def rij(label, waarde):
        return [Paragraph(label, label_stijl), Paragraph(str(waarde) if waarde else "—", stijlen["Normal"])]

    tegenpartij_label = "Leverancier" if order["order_type"] == "inkoop" else "Klant"
    data = [
        rij(tegenpartij_label, order.get("tegenpartij_naam", "")),
        rij("Bedrijfseenheid", order.get("bedrijfseenheid", "")),
        rij("Materiaal", f"{order.get('materiaal','')} — {order.get('kwaliteit','')}"),
        rij("Incoterm", order.get("incoterm", "")),
        rij("Betalingstermijn", order.get("betalingstermijn", "")),
        rij("Startdatum", order.get("startdatum", "")),
        rij("Einddatum", order.get("einddatum", "")),
        rij("Hoeveelheid", f"{order.get('hoeveelheid_mt','')} MT" if order.get("hoeveelheid_mt") else ""),
        rij("Prijs", f"{order.get('valuta','')} {order.get('prijs','')} / MT" if order.get("prijs") else ""),
        rij("Transportmodus", order.get("transportmodus", "")),
        rij("POD", order.get("pod_haven", "")),
    ]
    if order["order_type"] == "inkoop":
        data.append(rij("Afhaallocatie", f"{order.get('afhaal_adres','')}, {order.get('afhaal_postcode','')} {order.get('afhaal_stad','')}, {order.get('afhaal_land','')}" if order.get("afhaal_adres") else ""))
    else:
        data.append(rij("Leverlocatie", f"{order.get('lever_adres','')}, {order.get('lever_postcode','')} {order.get('lever_stad','')}, {order.get('lever_land','')}" if order.get("lever_adres") else ""))
    if order.get("opmerkingen"):
        data.append(rij("Opmerkingen", order["opmerkingen"]))

    tabel = Table(data, colWidths=[50*mm, 110*mm])
    tabel.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("LINEBELOW", (0,0), (-1,-2), 0.4, colors.HexColor("#e2e8f0")),
    ]))
    elementen.append(tabel)

    doc.build(elementen)
    buffer.seek(0)
    return buffer.read()

@handelsorders_bp.route("/handelsorders/<order_id>/pdf")
def handelsorder_pdf(order_id):
    _guard = vereist_afdeling_of_403("handelsorders")
    if _guard: return _guard

    orders = laad_handelsorders()
    order = next((o for o in orders if o["id"] == order_id), None)
    if not order or order["status"] != "Definitief":
        pagina = render_simple_page("PDF niet beschikbaar", "handelsorders", '<div class="page-title">Contract nog niet beschikbaar</div><div class="lege-staat">Het contract kan pas gedownload worden zodra de order goedgekeurd en verstuurd is. <a href="/handelsorders">Terug</a></div>')
        return render_template_string(pagina), 404

    pdf_bytes = _genereer_contract_pdf(order)
    return Response(pdf_bytes, mimetype="application/pdf",
                     headers={"Content-Disposition": f'inline; filename="contract_{order["contractnummer"]}.pdf"'})