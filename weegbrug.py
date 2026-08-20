"""
weegbrug.py — Blueprint voor de Weegbrug-module (Logistiek, Fase 1 + verfijning).

Ontworpen voor snel, foutloos in- en uitwegen met zo min mogelijk handelingen:
1. Weegopdracht (leverancier + materiaal + kwaliteit — alle drie verplicht en
   uit bestaande, beheerde lijsten gekozen, nooit vrije tekst, zodat er nooit
   een tikfout de koppeling met de boekhouding kan verstoren).
2. Inwegen (bruto gewicht — handmatig of via de weegbrug-knop, nu nog niet
   technisch gekoppeld maar wel al als optie aanwezig voor later).
3. Uitwegen (tarra gewicht — zelfde principe).

Handmatige invoer wordt intern gemarkeerd (herkomst_bruto/herkomst_tarra),
maar NOOIT op de weegbon getoond — puur voor eigen administratie.

Statussen: Opdracht -> Ingewogen -> Compleet (of Probleem bij een
gewichtsafwijking), plus Geannuleerd. Geen emoji-iconen — bewust zakelijk en
rustig gehouden, met alleen een kleurpunt en een korte statustekst.

Registratie in app.py met: app.register_blueprint(weegbrug_bp)
"""
import uuid
import datetime
import os
import io
import json
from flask import Blueprint, request, session, redirect, url_for, render_template_string, Response

from core import (
    laad_weegbrug, bewaar_weegbrug, genereer_weegnummer, WEEGBRUG_STATUS_BADGES,
    laad_accountmanagers, laad_status, laad_materiaal_taxonomie, ENF_BEDRIJVEN,
    is_huidige_gebruiker_admin, vereist_afdeling_of_403, render_simple_page,
    parse_hoeveelheid_getal, laad_logistieke_orders, bewaar_logistieke_orders,
    DOCUMENTEN_MAP, laad_documenten, bewaar_documenten, laad_bedrijfslogo_instelling, LOGO_MAP,
    laad_meldingen, bewaar_meldingen,
)

weegbrug_bp = Blueprint("weegbrug", __name__)

def _echte_leveranciers():
    """Zelfde definitie als de Leveranciers-pagina: alleen bedrijven met een
    toegekende status OF accountmanager — dus daadwerkelijk erkende leveranciers,
    niet de volledige, ongefilterde bedrijvendatabase."""
    status_alle = laad_status()
    am_alle = laad_accountmanagers()
    return sorted({b["naam"] for b in ENF_BEDRIJVEN if status_alle.get(b["naam"]) or am_alle.get(b["naam"])})

def _bepaal_netto_en_status(record):
    """Berekent netto gewicht en detecteert logische afwijkingen (bruto/tarra onmogelijk)."""
    bruto = parse_hoeveelheid_getal(record.get("bruto_gewicht", ""))
    tarra = parse_hoeveelheid_getal(record.get("tarra_gewicht", ""))
    if not record.get("tarra_gewicht"):
        return "", "Ingewogen"
    netto = round(bruto - tarra, 2)
    if tarra <= 0 or bruto <= 0 or tarra >= bruto or netto <= 0:
        return str(netto), "Probleem"
    return str(netto), "Compleet"


@weegbrug_bp.route("/weegbrug")
def weegbrug_pagina():
    _guard = vereist_afdeling_of_403("weegbrug")
    if _guard: return _guard

    alle_records = laad_weegbrug()
    filter_status = request.args.get("filter_status", "")
    filter_kenteken = request.args.get("kenteken", "").strip().lower()

    getoonde = alle_records
    if filter_status:
        getoonde = [r for r in getoonde if r.get("status") == filter_status]
    if filter_kenteken:
        getoonde = [r for r in getoonde if filter_kenteken in r.get("kenteken","").lower()]
    getoonde = sorted(getoonde, key=lambda r: r.get("aangemaakt",""), reverse=True)

    voertuigen_op_locatie = [r for r in alle_records if r.get("status") == "Ingewogen"]
    opdrachten_klaar_voor_wegen = [r for r in alle_records if r.get("status") == "Opdracht"]
    _vandaag_log = datetime.date.today().isoformat()
    kpi_vandaag = [r for r in alle_records if r.get("aangemaakt","").startswith(datetime.date.today().strftime("%d-%m-%Y"))]
    kpi_compleet_vandaag = [r for r in kpi_vandaag if r.get("status") == "Compleet"]
    kpi_probleem = [r for r in alle_records if r.get("status") == "Probleem"]

    inhoud = """
<div class="page-title">Weegbrug</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">In- en uitwegen van vrachtwagens.</p>

<style>
.wb-tabel-kop { display:flex; align-items:center; padding:10px 16px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); font-size:10px; letter-spacing:0.08em; text-transform:uppercase; color:#7d8792; }
.wb-tabel-rij { display:flex; align-items:center; padding:11px 16px; border-bottom:1px solid var(--gray-100); font-size:12.5px; text-decoration:none; color:inherit; cursor:pointer; }
.wb-tabel-rij:hover { background:var(--gray-50); }
.dg-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; }
.dg-kaart { background:transparent; border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); padding:16px 4px; }
.dg-getal { font-size:1.7rem; font-weight:800; color:var(--brand-700); }
.dg-label { font-size:0.72rem; color:var(--gray-400); text-transform:uppercase; letter-spacing:0.8px; margin-top:4px; font-weight:600; }
.wb-statuspunt { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }
@media (max-width:768px) { .dg-grid { grid-template-columns:repeat(2,1fr); } }
</style>

<div class="dg-grid" style="margin-bottom:24px;">
    <div class="dg-kaart"><div class="dg-getal">{{ voertuigen_op_locatie|length }}</div><div class="dg-label">Nu op locatie</div></div>
    <div class="dg-kaart"><div class="dg-getal">{{ opdrachten_klaar_voor_wegen|length }}</div><div class="dg-label">Klaar om in te wegen</div></div>
    <div class="dg-kaart"><div class="dg-getal">{{ kpi_vandaag|length }}</div><div class="dg-label">Vandaag</div></div>
    <div class="dg-kaart"><div class="dg-getal">{{ kpi_compleet_vandaag|length }}</div><div class="dg-label">Compleet vandaag</div></div>
    <div class="dg-kaart"><div class="dg-getal" style="{% if kpi_probleem %}color:#dc2626;{% endif %}">{{ kpi_probleem|length }}</div><div class="dg-label">Afwijkingen</div></div>
</div>

<a href="/weegbrug/opdracht" style="display:inline-block;margin-bottom:20px;font-size:12.5px;font-weight:700;color:#fff;background:var(--brand-600);text-decoration:none;padding:9px 18px;border-radius:6px;">Nieuwe weegopdracht</a>

{% if voertuigen_op_locatie or opdrachten_klaar_voor_wegen %}
<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Actie vereist</div>
<div style="display:flex;flex-direction:column;gap:6px;margin-bottom:24px;">
    {% for r in opdrachten_klaar_voor_wegen %}
    <a href="/weegbrug/inwegen/{{ r.id }}" style="display:flex;align-items:center;gap:14px;background:transparent;border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);padding:10px 4px;text-decoration:none;color:inherit;">
        <span style="font-weight:700;color:var(--gray-800);font-family:var(--font-mono);width:100px;">{{ r.kenteken or "—" }}</span>
        <span style="color:var(--gray-600);flex:1;">{{ r.leverancier or '—' }} — {{ r.materiaal or '—' }}</span>
        <span style="color:var(--gray-400);font-size:11.5px;">{{ r.weegnummer }}</span>
        <span style="color:var(--brand-600);font-weight:700;font-size:12px;">Inwegen</span>
    </a>
    {% endfor %}
    {% for r in voertuigen_op_locatie %}
    <a href="/weegbrug/uitwegen/{{ r.id }}" style="display:flex;align-items:center;gap:14px;background:transparent;border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);padding:10px 4px;text-decoration:none;color:inherit;">
        <span style="font-weight:700;color:var(--gray-800);font-family:var(--font-mono);width:100px;">{{ r.kenteken }}</span>
        <span style="color:var(--gray-600);flex:1;">{{ r.leverancier or '—' }} — {{ r.materiaal or '—' }}</span>
        <span style="color:var(--gray-400);font-size:11.5px;">{{ r.weegnummer }}</span>
        <span style="color:var(--brand-600);font-weight:700;font-size:12px;">Uitwegen</span>
    </a>
    {% endfor %}
</div>
{% endif %}

<form method="GET" style="display:flex;gap:8px;margin-bottom:16px;">
    <select name="filter_status" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle statussen</option>
        {% for st in statussen %}<option value="{{ st }}" {% if filter_status == st %}selected{% endif %}>{{ badges[st].kort }}</option>{% endfor %}
    </select>
    <input type="text" name="kenteken" value="{{ filter_kenteken }}" placeholder="Zoek op kenteken" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
    <button type="submit" style="padding:7px 14px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;background:#fff;cursor:pointer;">Filteren</button>
</form>

{% if getoonde %}
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);">
    <div class="wb-tabel-kop">
        <span style="width:110px;">Weegnummer</span>
        <span style="width:100px;">Kenteken</span>
        <span style="flex:1;">Leverancier</span>
        <span style="flex:1;">Materiaal</span>
        <span style="width:130px;text-align:right;">Netto</span>
        <span style="width:140px;">Status</span>
        <span style="width:110px;"></span>
    </div>
    {% for r in getoonde %}
    <div class="wb-tabel-rij" style="cursor:default;">
        <a href="/weegbrug/{{ r.id }}" style="display:contents;color:inherit;text-decoration:none;">
        <span style="width:110px;font-family:var(--font-mono);color:var(--gray-500);">{{ r.weegnummer }}</span>
        <span style="width:100px;font-weight:700;color:var(--gray-800);">{{ r.kenteken or "—" }}</span>
        <span style="flex:1;color:var(--gray-600);">{{ r.leverancier or '—' }}</span>
        <span style="flex:1;color:var(--gray-600);">{{ r.materiaal or '—' }}</span>
        <span style="width:130px;text-align:right;font-family:var(--font-mono);color:var(--gray-600);">
            {% if r.netto_gewicht %}{{ "{:,.0f}".format(r.netto_gewicht|float).replace(",", ".") }} kg{% else %}—{% endif %}
        </span>
        <span style="width:140px;">
            <span class="wb-statuspunt" style="background:{{ badges[r.status].kleur }};"></span>
            <span style="font-size:12px;font-weight:600;color:var(--gray-700);">{{ badges[r.status].kort }}</span>
        </span>
        </a>
        <span style="width:110px;">
            {% if r.status == "Opdracht" %}<a href="/weegbrug/inwegen/{{ r.id }}" style="font-size:11px;color:var(--brand-600);text-decoration:none;font-weight:600;">Inwegen</a>
            {% elif r.status == "Ingewogen" %}<a href="/weegbrug/uitwegen/{{ r.id }}" style="font-size:11px;color:var(--brand-600);text-decoration:none;font-weight:600;">Uitwegen</a>
            {% elif r.status == "Compleet" %}<a href="/weegbrug/weegbon/{{ r.id }}" target="_blank" style="font-size:11px;color:var(--brand-600);text-decoration:none;font-weight:600;">Weegbon</a>{% endif %}
            <form method="POST" action="/weegbrug/verwijderen" onsubmit="return confirm('Deze weging definitief verwijderen? Dit kan niet ongedaan gemaakt worden.');" style="display:inline;margin:0;margin-left:6px;">
                <input type="hidden" name="record_id" value="{{ r.id }}">
                <button type="submit" style="background:none;border:none;color:var(--gray-300);cursor:pointer;font-size:11px;" title="Verwijderen">Verwijderen</button>
            </form>
        </span>
    </div>
    {% endfor %}
</div>
<div style="padding:10px 4px;font-size:0.8rem;color:var(--gray-400);">{{ getoonde|length }} weegrecords</div>
{% else %}
<div class="lege-staat">Nog geen weegrecords.</div>
{% endif %}
    """
    pagina = render_simple_page("Weegbrug", "weegbrug", inhoud)
    return render_template_string(pagina, getoonde=getoonde, statussen=list(WEEGBRUG_STATUS_BADGES.keys()),
                                    badges=WEEGBRUG_STATUS_BADGES, filter_status=filter_status, filter_kenteken=filter_kenteken,
                                    voertuigen_op_locatie=voertuigen_op_locatie, opdrachten_klaar_voor_wegen=opdrachten_klaar_voor_wegen,
                                    kpi_vandaag=kpi_vandaag, kpi_compleet_vandaag=kpi_compleet_vandaag, kpi_probleem=kpi_probleem)

@weegbrug_bp.route("/weegbrug/opdracht", methods=["GET", "POST"])
def weegbrug_opdracht():
    """Stap 1: weegopdracht aanmaken. Leverancier, materiaal en kwaliteit zijn
    alle drie verplicht en komen uit bestaande, beheerde lijsten (nooit vrije
    tekst) — dit voorkomt tikfouten die de koppeling met de boekhouding
    zouden kunnen verstoren. Bruto gewicht komt pas in stap 2 (inwegen)."""
    _guard = vereist_afdeling_of_403("weegbrug")
    if _guard: return _guard

    leverancier_namen = _echte_leveranciers()
    taxonomie = laad_materiaal_taxonomie()
    materiaal_namen = sorted(taxonomie.keys())

    if request.method == "POST":
        records = laad_weegbrug()
        nu = datetime.datetime.now()
        leverancier = request.form.get("leverancier", "").strip()
        materiaal = request.form.get("materiaal", "").strip()
        kwaliteit = request.form.get("kwaliteit", "").strip()
        kwaliteiten_bij_materiaal = taxonomie.get(materiaal, [])

        fout = None
        if leverancier not in leverancier_namen:
            fout = "Kies een bestaande leverancier uit de lijst. Nieuwe leverancier? Vraag Backoffice om deze eerst aan te maken."
        elif not materiaal:
            fout = "Materiaal is verplicht."
        elif not kwaliteit or kwaliteit not in kwaliteiten_bij_materiaal:
            fout = "Kies een geldige kwaliteit die bij het gekozen materiaal hoort."

        if fout:
            inhoud = _opdracht_formulier_html()
            pagina = render_simple_page("Weegopdracht", "weegbrug", inhoud)
            return render_template_string(pagina, fout=fout, leverancier_namen=leverancier_namen,
                                            materiaal_namen=materiaal_namen, taxonomie_json=json.dumps(taxonomie))

        nieuw = {
            "id": str(uuid.uuid4()),
            "weegnummer": genereer_weegnummer(records),
            "kenteken": request.form.get("kenteken", "").strip().upper(),
            "herkenningsbron": "handmatig",
            "leverancier": leverancier,
            "chauffeur": request.form.get("chauffeur", "").strip(),
            "transporteur": request.form.get("transporteur", "").strip(),
            "ordernummer": request.form.get("ordernummer", "").strip(),
            "materiaal": materiaal,
            "kwaliteit": kwaliteit,
            "herkomst": request.form.get("herkomst", "").strip(),
            "bestemming": request.form.get("bestemming", "").strip(),
            "referentienummer_leverancier": request.form.get("referentienummer_leverancier", "").strip(),
            "opmerkingen": request.form.get("opmerkingen", "").strip(),
            "bruto_gewicht": "", "bruto_herkomst": "", "inweegmoment": "", "weegbrugmedewerker_in": "",
            "tarra_gewicht": "", "tarra_herkomst": "", "uitweegmoment": "", "weegbrugmedewerker_uit": "",
            "netto_gewicht": "",
            "status": "Opdracht",
            "aangemaakt_door": session.get("gebruikersnaam", ""),
            "aangemaakt": nu.strftime("%d-%m-%Y %H:%M"),
        }
        records.append(nieuw)
        bewaar_weegbrug(records)
        return redirect(url_for("weegbrug.weegbrug_inwegen", record_id=nieuw["id"]))

    inhoud = _opdracht_formulier_html()
    pagina = render_simple_page("Weegopdracht", "weegbrug", inhoud)
    return render_template_string(pagina, fout=None, leverancier_namen=leverancier_namen,
                                    materiaal_namen=materiaal_namen, taxonomie_json=json.dumps(taxonomie))

def _opdracht_formulier_html():
    return """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/weegbrug" style="color:var(--gray-400);text-decoration:none;">Weegbrug</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">Weegopdracht</span>
</div>
<div class="page-title">Nieuwe weegopdracht</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Stap 1 van 2 — leverancier, materiaal en kwaliteit. Het gewicht volgt in de volgende stap.</p>

{% if fout %}<div style="background:#fef2f2;color:#dc2626;padding:10px 14px;border-radius:8px;font-size:13px;margin-bottom:16px;">{{ fout }}</div>{% endif %}

<form method="POST" style="max-width:640px;">
    <div style="margin-bottom:12px;">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Leverancier *</label>
        <input type="text" name="leverancier" list="leveranciers_datalist" required autocomplete="off" placeholder="Begin te typen..." style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        <datalist id="leveranciers_datalist">{% for naam in leverancier_namen %}<option value="{{ naam }}">{% endfor %}</datalist>
        <div style="font-size:10.5px;color:var(--gray-300);margin-top:2px;">Alleen bestaande, erkende leveranciers. Nieuwe leverancier? Vraag Backoffice.</div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px;">
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Materiaal *</label>
            <input type="text" name="materiaal" id="materiaal_input" list="materiaal_datalist" required autocomplete="off" placeholder="Begin te typen..." oninput="verversKwaliteiten()" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
            <datalist id="materiaal_datalist">{% for m in materiaal_namen %}<option value="{{ m }}">{% endfor %}</datalist>
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Kwaliteit *</label>
            <input type="text" name="kwaliteit" id="kwaliteit_input" list="kwaliteit_datalist" required autocomplete="off" placeholder="Kies eerst materiaal..." style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
            <datalist id="kwaliteit_datalist"></datalist>
        </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px;">
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Kenteken</label>
            <input type="text" name="kenteken" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;text-transform:uppercase;font-family:inherit;">
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Ordernummer</label>
            <input type="text" name="ordernummer" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px;">
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Chauffeur</label>
            <input type="text" name="chauffeur" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Transporteur</label>
            <input type="text" name="transporteur" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px;">
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Herkomst</label>
            <input type="text" name="herkomst" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Bestemming</label>
            <input type="text" name="bestemming" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
    </div>
    <div style="margin-bottom:12px;">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Referentienummer leverancier</label>
        <input type="text" name="referentienummer_leverancier" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
    </div>
    <div style="margin-bottom:18px;">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Opmerkingen</label>
        <textarea name="opmerkingen" rows="2" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;"></textarea>
    </div>
    <button type="submit" style="padding:10px 22px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">Verder naar inwegen</button>
    <a href="/weegbrug" style="margin-left:10px;font-size:12.5px;color:var(--gray-400);text-decoration:none;">Annuleren</a>
</form>

<script>
var TAXONOMIE = {{ taxonomie_json|safe }};
function verversKwaliteiten() {
    var materiaal = document.getElementById("materiaal_input").value;
    var kwaliteitDatalist = document.getElementById("kwaliteit_datalist");
    var kwaliteitInput = document.getElementById("kwaliteit_input");
    var kwaliteiten = TAXONOMIE[materiaal] || [];
    kwaliteitDatalist.innerHTML = "";
    kwaliteiten.forEach(function(k) {
        var optie = document.createElement("option");
        optie.value = k;
        kwaliteitDatalist.appendChild(optie);
    });
    kwaliteitInput.placeholder = kwaliteiten.length ? "Begin te typen..." : "Kies eerst een geldig materiaal...";
}
</script>
    """

@weegbrug_bp.route("/weegbrug/inwegen/<record_id>", methods=["GET", "POST"])
def weegbrug_inwegen(record_id):
    """Stap 2: bruto gewicht invoeren voor een bestaande weegopdracht. Handmatig
    óf (later) via de weegbrug-knop — beide opties staan al klaar, de
    weegbrug-koppeling is nu nog niet technisch aangesloten."""
    _guard = vereist_afdeling_of_403("weegbrug")
    if _guard: return _guard

    records = laad_weegbrug()
    record = next((r for r in records if r["id"] == record_id), None)
    if not record:
        pagina = render_simple_page("Niet gevonden", "weegbrug", '<div class="page-title">Weegopdracht niet gevonden</div><div class="lege-staat">Deze weegopdracht bestaat niet (meer). <a href="/weegbrug">Terug naar Weegbrug</a></div>')
        return render_template_string(pagina), 404

    if request.method == "POST":
        record["kenteken"] = request.form.get("kenteken", record.get("kenteken","")).strip().upper() or record.get("kenteken","")
        record["bruto_gewicht"] = request.form.get("bruto_gewicht", "").strip()
        record["bruto_herkomst"] = request.form.get("herkomst_bron", "handmatig")
        record["inweegmoment"] = datetime.datetime.now().isoformat(timespec="seconds")
        record["weegbrugmedewerker_in"] = session.get("gebruikersnaam", "")
        record["status"] = "Ingewogen"
        bewaar_weegbrug(records)

        # Melding naar de accountmanager die aan deze leverancier gekoppeld is: hun
        # vrachtwagen is nu binnengekomen en wordt afgehandeld.
        if record.get("leverancier"):
            toegewezen_am = laad_accountmanagers().get(record["leverancier"], "")
            if toegewezen_am and toegewezen_am != session.get("gebruikersnaam", ""):
                alle_meldingen = laad_meldingen()
                alle_meldingen.append({
                    "id": str(uuid.uuid4()),
                    "tekst": f"Vrachtwagen binnengekomen bij de weegbrug voor {record['leverancier']} (jouw leverancier) — {record.get('materiaal','')} {record.get('kwaliteit','')}, kenteken {record['kenteken']}.",
                    "bedrijf": record["leverancier"], "van": session.get("gebruikersnaam", ""),
                    "voor_gebruiker": toegewezen_am, "voor_team": "",
                    "gelezen": False, "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
                })
                bewaar_meldingen(alle_meldingen)

        return redirect(url_for("weegbrug.weegbrug_pagina"))

    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/weegbrug" style="color:var(--gray-400);text-decoration:none;">Weegbrug</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">Inwegen</span>
</div>
<div class="page-title">Inwegen — {{ record.weegnummer }}</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Stap 2 van 2.</p>

<div style="background:var(--gray-50);border-radius:8px;padding:14px 16px;margin-bottom:20px;font-size:12.5px;color:var(--gray-600);max-width:480px;">
    <div><b>Leverancier:</b> {{ record.leverancier }}</div>
    <div><b>Materiaal:</b> {{ record.materiaal }} — {{ record.kwaliteit }}</div>
</div>

<form method="POST" style="max-width:400px;">
    {% if not record.kenteken %}
    <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Kenteken</label>
    <input type="text" name="kenteken" style="width:100%;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;text-transform:uppercase;margin-bottom:16px;font-family:inherit;">
    {% endif %}
    <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Bruto gewicht (kg) *</label>
    <div style="display:flex;gap:8px;margin-bottom:16px;">
        <input type="text" name="bruto_gewicht" id="bruto_veld" required autofocus style="flex:1;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        <button type="button" onclick="alert('De koppeling met de weegbrug is nog niet actief. Vul het gewicht voorlopig handmatig in.'); document.getElementById('herkomst_veld').value='weegbrug';" style="padding:9px 14px;border:1px solid var(--gray-200);border-radius:6px;font-size:12px;background:#fff;color:var(--gray-500);cursor:pointer;white-space:nowrap;">Ophalen van weegbrug</button>
    </div>
    <input type="hidden" name="herkomst_bron" id="herkomst_veld" value="handmatig">
    <button type="submit" style="padding:10px 22px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">Inwegen registreren</button>
    <a href="/weegbrug" style="margin-left:10px;font-size:12.5px;color:var(--gray-400);text-decoration:none;">Annuleren</a>
</form>
    """
    pagina = render_simple_page("Inwegen", "weegbrug", inhoud)
    return render_template_string(pagina, record=record)

@weegbrug_bp.route("/weegbrug/uitwegen/<record_id>", methods=["GET", "POST"])
def weegbrug_uitwegen(record_id):
    _guard = vereist_afdeling_of_403("weegbrug")
    if _guard: return _guard

    records = laad_weegbrug()
    record = next((r for r in records if r["id"] == record_id), None)
    if not record:
        pagina = render_simple_page("Niet gevonden", "weegbrug", '<div class="page-title">Weegrecord niet gevonden</div><div class="lege-staat">Dit weegrecord bestaat niet (meer). <a href="/weegbrug">Terug naar Weegbrug</a></div>')
        return render_template_string(pagina), 404

    if request.method == "POST":
        record["tarra_gewicht"] = request.form.get("tarra_gewicht", "").strip()
        record["tarra_herkomst"] = request.form.get("herkomst_bron", "handmatig")
        record["uitweegmoment"] = datetime.datetime.now().isoformat(timespec="seconds")
        record["weegbrugmedewerker_uit"] = session.get("gebruikersnaam", "")
        netto, status = _bepaal_netto_en_status(record)
        record["netto_gewicht"] = netto
        record["status"] = status
        bewaar_weegbrug(records)

        if record.get("ordernummer"):
            orders = laad_logistieke_orders()
            gekoppelde_order = next((o for o in orders if o.get("ordernummer") == record["ordernummer"]), None)
            if gekoppelde_order and status == "Compleet":
                gekoppelde_order["werkelijke_hoeveelheid"] = str(round(float(netto) / 1000, 3)) if netto else gekoppelde_order.get("werkelijke_hoeveelheid","")
                gekoppelde_order["status"] = "Weegbon compleet"
                bewaar_logistieke_orders(orders)

        if status == "Compleet":
            pdf_bytes = _genereer_weegbon_pdf(record)
            _bewaar_weegbon_bij_document(record, pdf_bytes)

        return redirect(url_for("weegbrug.weegbrug_pagina"))

    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/weegbrug" style="color:var(--gray-400);text-decoration:none;">Weegbrug</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">Uitwegen</span>
</div>
<div class="page-title">Uitwegen — {{ record.weegnummer }}</div>

<div style="background:var(--gray-50);border-radius:8px;padding:14px 16px;margin-bottom:20px;font-size:12.5px;color:var(--gray-600);max-width:480px;">
    <div><b>Kenteken:</b> {{ record.kenteken }}</div>
    <div><b>Leverancier:</b> {{ record.leverancier or '—' }}</div>
    <div><b>Bruto gewicht:</b> {{ record.bruto_gewicht }} kg</div>
</div>

<form method="POST" style="max-width:400px;">
    <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Tarra gewicht (kg, leeggewicht bij vertrek) *</label>
    <div style="display:flex;gap:8px;margin-bottom:16px;">
        <input type="text" name="tarra_gewicht" required autofocus style="flex:1;padding:9px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        <button type="button" onclick="alert('De koppeling met de weegbrug is nog niet actief. Vul het gewicht voorlopig handmatig in.'); document.getElementById('herkomst_veld_uit').value='weegbrug';" style="padding:9px 14px;border:1px solid var(--gray-200);border-radius:6px;font-size:12px;background:#fff;color:var(--gray-500);cursor:pointer;white-space:nowrap;">Ophalen van weegbrug</button>
    </div>
    <input type="hidden" name="herkomst_bron" id="herkomst_veld_uit" value="handmatig">
    <button type="submit" style="padding:10px 22px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">Uitwegen registreren</button>
    <a href="/weegbrug" style="margin-left:10px;font-size:12.5px;color:var(--gray-400);text-decoration:none;">Annuleren</a>
</form>
    """
    pagina = render_simple_page("Uitwegen", "weegbrug", inhoud)
    return render_template_string(pagina, record=record)

@weegbrug_bp.route("/weegbrug/<record_id>")
def weegbrug_detail(record_id):
    """Detailpagina: alle info van een weegrecord op één plek, bereikbaar door
    op een rij in het overzicht te klikken."""
    _guard = vereist_afdeling_of_403("weegbrug")
    if _guard: return _guard

    records = laad_weegbrug()
    record = next((r for r in records if r["id"] == record_id), None)
    if not record:
        pagina = render_simple_page("Niet gevonden", "weegbrug", '<div class="page-title">Weegrecord niet gevonden</div><div class="lege-staat">Dit weegrecord bestaat niet (meer). <a href="/weegbrug">Terug naar Weegbrug</a></div>')
        return render_template_string(pagina), 404

    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/weegbrug" style="color:var(--gray-400);text-decoration:none;">Weegbrug</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">{{ record.weegnummer }}</span>
</div>
<div class="page-title">{{ record.weegnummer }}</div>
<div style="margin-bottom:16px;">
    <span class="wb-statuspunt" style="display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px;background:{{ badge.kleur }};"></span>
    <span style="font-size:13px;font-weight:600;color:var(--gray-700);">{{ badge.label }}</span>
</div>

<div style="display:flex;gap:24px;flex-wrap:wrap;">
<div style="flex:1;min-width:320px;">
    <div style="background:var(--gray-50);border-radius:8px;padding:16px 18px;font-size:12.5px;color:var(--gray-600);">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <div><b>Kenteken:</b> {{ record.kenteken or '—' }}</div>
            <div><b>Leverancier:</b> {{ record.leverancier or '—' }}</div>
            <div><b>Materiaal:</b> {{ record.materiaal or '—' }}</div>
            <div><b>Kwaliteit:</b> {{ record.kwaliteit or '—' }}</div>
            <div><b>Chauffeur:</b> {{ record.chauffeur or '—' }}</div>
            <div><b>Transporteur:</b> {{ record.transporteur or '—' }}</div>
            <div><b>Ordernummer:</b> {{ record.ordernummer or '—' }}</div>
            <div><b>Ref. leverancier:</b> {{ record.referentienummer_leverancier or '—' }}</div>
            <div><b>Herkomst:</b> {{ record.herkomst or '—' }}</div>
            <div><b>Bestemming:</b> {{ record.bestemming or '—' }}</div>
        </div>
        {% if record.opmerkingen %}<div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--gray-200);"><b>Opmerkingen:</b> {{ record.opmerkingen }}</div>{% endif %}
    </div>
</div>

<div style="flex:1;min-width:280px;">
    <div style="background:var(--gray-50);border-radius:8px;padding:16px 18px;font-size:12.5px;color:var(--gray-600);">
        <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Weging</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <div><b>Bruto:</b> {{ record.bruto_gewicht or '—' }}{% if record.bruto_gewicht %} kg{% endif %}</div>
            <div><b>Tarra:</b> {{ record.tarra_gewicht or '—' }}{% if record.tarra_gewicht %} kg{% endif %}</div>
            <div><b>Netto:</b> {% if record.netto_gewicht %}{{ "{:,.0f}".format(record.netto_gewicht|float).replace(",", ".") }} kg{% else %}—{% endif %}</div>
            <div><b>Netto (ton):</b> {% if record.netto_gewicht %}{{ "%.3f"|format(record.netto_gewicht|float / 1000) }} t{% else %}—{% endif %}</div>
            <div><b>Ingewogen door:</b> {{ record.weegbrugmedewerker_in or '—' }}</div>
            <div><b>Uitgewogen door:</b> {{ record.weegbrugmedewerker_uit or '—' }}</div>
        </div>
        {% if record.status == "Compleet" %}<div style="margin-top:10px;"><a href="/weegbrug/weegbon/{{ record.id }}" target="_blank" style="color:var(--brand-600);text-decoration:none;font-weight:600;">Weegbon bekijken (PDF) →</a></div>{% endif %}
    </div>
</div>
</div>

<div style="margin-top:20px;display:flex;gap:10px;align-items:center;">
    {% if record.status == "Opdracht" %}
    <a href="/weegbrug/inwegen/{{ record.id }}" style="padding:9px 18px;background:var(--brand-600);color:#fff;text-decoration:none;border-radius:6px;font-size:13px;font-weight:700;">Inwegen</a>
    {% elif record.status == "Ingewogen" %}
    <a href="/weegbrug/uitwegen/{{ record.id }}" style="padding:9px 18px;background:var(--brand-600);color:#fff;text-decoration:none;border-radius:6px;font-size:13px;font-weight:700;">Uitwegen</a>
    {% endif %}
    {% if record.status in ("Opdracht", "Ingewogen") %}
    <form method="POST" action="/weegbrug/annuleren" onsubmit="return confirm('Deze weegopdracht annuleren?');" style="margin:0;">
        <input type="hidden" name="record_id" value="{{ record.id }}">
        <button type="submit" style="padding:9px 16px;background:#fff;color:var(--gray-500);border:1px solid var(--gray-200);border-radius:6px;font-size:13px;cursor:pointer;">Annuleren</button>
    </form>
    {% endif %}
    <form method="POST" action="/weegbrug/verwijderen" onsubmit="return confirm('Deze weging definitief verwijderen? Dit kan niet ongedaan gemaakt worden.');" style="margin:0;">
        <input type="hidden" name="record_id" value="{{ record.id }}">
        <button type="submit" style="padding:9px 16px;background:#fff;color:#dc2626;border:1px solid #fecaca;border-radius:6px;font-size:13px;cursor:pointer;">Verwijderen</button>
    </form>
</div>
    """
    pagina = render_simple_page(record["weegnummer"], "weegbrug", inhoud)
    return render_template_string(pagina, record=record, badge=WEEGBRUG_STATUS_BADGES.get(record["status"], {}))

def _genereer_weegbon_pdf(record):
    """Bouwt de weegbon als PDF-bytes met reportlab. Geeft alleen echte, ingevoerde data
    weer — de handmatig/weegbrug-herkomst van een gewicht komt hier NOOIT op te staan,
    dat is puur interne administratie."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm, leftMargin=20*mm, rightMargin=20*mm)
    stijlen = getSampleStyleSheet()
    titel_stijl = ParagraphStyle("WeegbonTitel", parent=stijlen["Title"], fontSize=18, textColor=colors.HexColor("#0d5c62"))
    label_stijl = ParagraphStyle("Label", parent=stijlen["Normal"], fontSize=9, textColor=colors.HexColor("#64748b"))

    elementen = []

    logo_instelling = laad_bedrijfslogo_instelling()
    if logo_instelling.get("bestandsnaam"):
        logo_pad = os.path.join(LOGO_MAP, logo_instelling["bestandsnaam"])
        if os.path.exists(logo_pad):
            try:
                from PIL import Image as PILImage
                with PILImage.open(logo_pad) as test_img:
                    test_img.verify()  # Valideert het bestand nu meteen, i.p.v. pas tijdens doc.build()
                logo_img = Image(logo_pad, width=45*mm, height=18*mm, kind="proportional")
                positie = logo_instelling.get("positie", "links")
                logo_img.hAlign = {"links": "LEFT", "midden": "CENTER", "rechts": "RIGHT"}.get(positie, "LEFT")
                elementen.append(logo_img)
                elementen.append(Spacer(1, 10))
            except Exception:
                pass  # Ongeldig of beschadigd logo-bestand: weegbon gewoon zonder logo genereren

    elementen.append(Paragraph("Weegbon", titel_stijl))
    elementen.append(Paragraph(f"Weegnummer: <b>{record['weegnummer']}</b>", stijlen["Normal"]))
    elementen.append(Spacer(1, 14))

    def rij(label, waarde):
        return [Paragraph(label, label_stijl), Paragraph(str(waarde) if waarde else "—", stijlen["Normal"])]

    netto_kg = record.get("netto_gewicht", "")
    netto_ton = f"{float(netto_kg)/1000:.3f} ton" if netto_kg else "—"

    data = [
        rij("Datum/tijd inwegen", record.get("aangemaakt", "")),
        rij("Datum/tijd uitwegen", record.get("uitweegmoment", "").replace("T", " ") if record.get("uitweegmoment") else ""),
        rij("Kenteken", record.get("kenteken", "")),
        rij("Leverancier", record.get("leverancier", "")),
        rij("Transporteur", record.get("transporteur", "")),
        rij("Chauffeur", record.get("chauffeur", "")),
        rij("Ordernummer", record.get("ordernummer", "")),
        rij("Materiaal", record.get("materiaal", "")),
        rij("Kwaliteit/product", record.get("kwaliteit", "")),
        rij("Herkomst", record.get("herkomst", "")),
        rij("Bestemming", record.get("bestemming", "")),
        rij("Referentienummer leverancier", record.get("referentienummer_leverancier", "")),
        rij("Bruto gewicht", f"{record.get('bruto_gewicht','')} kg" if record.get("bruto_gewicht") else ""),
        rij("Tarra gewicht", f"{record.get('tarra_gewicht','')} kg" if record.get("tarra_gewicht") else ""),
        rij("Netto gewicht", f"{netto_kg} kg  /  {netto_ton}" if netto_kg else ""),
        rij("Weegbrugmedewerker (in)", record.get("weegbrugmedewerker_in", "")),
        rij("Weegbrugmedewerker (uit)", record.get("weegbrugmedewerker_uit", "")),
    ]
    if record.get("opmerkingen"):
        data.append(rij("Opmerkingen", record["opmerkingen"]))

    tabel = Table(data, colWidths=[55*mm, 105*mm])
    tabel.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("LINEBELOW", (0,0), (-1,-2), 0.4, colors.HexColor("#e2e8f0")),
    ]))
    elementen.append(tabel)
    elementen.append(Spacer(1, 20))
    elementen.append(Paragraph(f"Netto gewicht = bruto gewicht - tarra gewicht = {netto_kg} kg ({netto_ton})" if netto_kg else "", stijlen["Normal"]))

    doc.build(elementen)
    buffer.seek(0)
    return buffer.read()

def _bewaar_weegbon_bij_document(record, pdf_bytes):
    """Slaat de weegbon-PDF op via het bestaande documentensysteem, gekoppeld aan het ordernummer als bekend."""
    if not record.get("ordernummer"):
        return
    if not os.path.exists(DOCUMENTEN_MAP):
        os.makedirs(DOCUMENTEN_MAP)
    bestandsnaam = f"{uuid.uuid4()}.pdf"
    with open(os.path.join(DOCUMENTEN_MAP, bestandsnaam), "wb") as f:
        f.write(pdf_bytes)
    alle = laad_documenten()
    alle.setdefault(record["ordernummer"], [])
    al_opgeslagen = any(d.get("originele_naam","").startswith(f"Weegbon_{record['weegnummer']}") for d in alle[record["ordernummer"]])
    if not al_opgeslagen:
        alle[record["ordernummer"]].append({
            "bestandsnaam": bestandsnaam,
            "originele_naam": f"Weegbon_{record['weegnummer']}.pdf",
            "geupload_door": "systeem (automatisch bij uitwegen)",
            "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
        })
        bewaar_documenten(alle)

@weegbrug_bp.route("/weegbrug/weegbon/<record_id>")
def weegbrug_weegbon(record_id):
    _guard = vereist_afdeling_of_403("weegbrug")
    if _guard: return _guard

    records = laad_weegbrug()
    record = next((r for r in records if r["id"] == record_id), None)
    if not record or record.get("status") != "Compleet":
        pagina = render_simple_page("Weegbon niet beschikbaar", "weegbrug", '<div class="page-title">Weegbon nog niet beschikbaar</div><div class="lege-staat">Deze weegbon kan pas gegenereerd worden zodra het voertuig volledig in- én uitgewogen is. <a href="/weegbrug">Terug naar Weegbrug</a></div>')
        return render_template_string(pagina), 404

    pdf_bytes = _genereer_weegbon_pdf(record)
    return Response(pdf_bytes, mimetype="application/pdf",
                     headers={"Content-Disposition": f'inline; filename="weegbon_{record["weegnummer"]}.pdf"'})

@weegbrug_bp.route("/weegbrug/annuleren", methods=["POST"])
def weegbrug_annuleren():
    _guard = vereist_afdeling_of_403("weegbrug")
    if _guard: return _guard
    record_id = request.form.get("record_id", "")
    records = laad_weegbrug()
    record = next((r for r in records if r["id"] == record_id), None)
    if record and (record.get("weegbrugmedewerker_in") == session.get("gebruikersnaam","") or record.get("aangemaakt_door") == session.get("gebruikersnaam","") or is_huidige_gebruiker_admin()):
        record["status"] = "Geannuleerd"
        bewaar_weegbrug(records)
    return redirect(url_for("weegbrug.weegbrug_pagina"))

@weegbrug_bp.route("/weegbrug/verwijderen", methods=["POST"])
def weegbrug_verwijderen():
    _guard = vereist_afdeling_of_403("weegbrug")
    if _guard: return _guard
    record_id = request.form.get("record_id", "")
    records = laad_weegbrug()
    record = next((r for r in records if r["id"] == record_id), None)
    if record and (record.get("weegbrugmedewerker_in") == session.get("gebruikersnaam","") or record.get("aangemaakt_door") == session.get("gebruikersnaam","") or is_huidige_gebruiker_admin()):
        if record.get("ordernummer"):
            orders = laad_logistieke_orders()
            gekoppelde_order = next((o for o in orders if o.get("ordernummer") == record["ordernummer"]), None)
            if gekoppelde_order and gekoppelde_order.get("gekoppeld_weegbrug_id") == record_id:
                gekoppelde_order["gekoppeld_weegbrug_id"] = ""
                bewaar_logistieke_orders(orders)
        records = [r for r in records if r["id"] != record_id]
        bewaar_weegbrug(records)
    return redirect(url_for("weegbrug.weegbrug_pagina"))