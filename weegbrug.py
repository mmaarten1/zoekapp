"""
weegbrug.py — Blueprint voor de Weegbrug-module (Logistiek, Fase 1).

Losstaande, gerichte module voor het in- en uitwegen van vrachtwagens.
Bewust een eigen afdeling ("weegbrug"), los van de bredere Logistiek-
afdeling — een weegbrugmedewerker heeft alleen dit scherm nodig.

Kenteken wordt nu handmatig ingevoerd. Het "herkenningsbron"-veld
(handmatig/camera) ligt al klaar zodat een toekomstige ANPR-camera-
koppeling hier gewoon op kan aansluiten zonder het datamodel te wijzigen
— zo'n koppeling zou simpelweg dezelfde /weegbrug/inwegen-actie aanroepen
met herkenningsbron="camera" i.p.v. een nieuw systeem nodig te hebben.

Registratie in app.py met: app.register_blueprint(weegbrug_bp)
"""
import uuid
import datetime
from flask import Blueprint, request, session, redirect, url_for, render_template_string

from core import (
    laad_weegbrug, bewaar_weegbrug, genereer_weegnummer, WEEGBRUG_STATUS_BADGES,
    laad_accountmanagers, ENF_BEDRIJVEN, is_huidige_gebruiker_admin,
    vereist_afdeling_of_403, render_simple_page, parse_hoeveelheid_getal,
)

weegbrug_bp = Blueprint("weegbrug", __name__)


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
    kpi_vandaag = [r for r in alle_records if r.get("inweegmoment","").startswith(datetime.date.today().isoformat())]
    kpi_compleet_vandaag = [r for r in kpi_vandaag if r.get("status") == "Compleet"]
    kpi_probleem = [r for r in alle_records if r.get("status") == "Probleem"]
    kpi_wacht_op_koppeling = [r for r in alle_records if r.get("status") in ("Ingewogen","Compleet") and not r.get("ordernummer","").strip()]

    leverancier_namen = sorted({b["naam"] for b in ENF_BEDRIJVEN})

    inhoud = """
<div class="page-title">Weegbrug</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">In- en uitwegen van vrachtwagens, realtime overzicht wie er op locatie is.</p>

<div class="dg-grid" style="margin-bottom:20px;">
    <div class="dg-kaart"><div class="dg-icoon">🚛</div><div class="dg-getal">{{ voertuigen_op_locatie|length }}</div><div class="dg-label">Nu op locatie</div></div>
    <div class="dg-kaart"><div class="dg-icoon">📋</div><div class="dg-getal">{{ kpi_vandaag|length }}</div><div class="dg-label">Ingewogen vandaag</div></div>
    <div class="dg-kaart"><div class="dg-icoon">✅</div><div class="dg-getal">{{ kpi_compleet_vandaag|length }}</div><div class="dg-label">Compleet vandaag</div></div>
    <div class="dg-kaart"><div class="dg-icoon">🔴</div><div class="dg-getal">{{ kpi_probleem|length }}</div><div class="dg-label">Afwijkingen</div></div>
    <div class="dg-kaart"><div class="dg-icoon">🔵</div><div class="dg-getal">{{ kpi_wacht_op_koppeling|length }}</div><div class="dg-label">Wacht op orderkoppeling</div></div>
</div>

<a href="/weegbrug/inwegen" style="display:inline-block;margin-bottom:20px;font-size:12.5px;font-weight:700;color:#fff;background:var(--brand-600);text-decoration:none;padding:8px 16px;border-radius:6px;">+ Nieuw voertuig inwegen</a>

<form method="GET" style="display:flex;gap:8px;margin-bottom:16px;">
    <select name="filter_status" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle statussen</option>
        {% for st in statussen %}<option value="{{ st }}" {% if filter_status == st %}selected{% endif %}>{{ badges[st].bol }} {{ badges[st].label }}</option>{% endfor %}
    </select>
    <input type="text" name="kenteken" value="{{ filter_kenteken }}" placeholder="Zoek op kenteken" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
    <button type="submit" style="padding:7px 14px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;background:#fff;cursor:pointer;">Filteren</button>
</form>

<style>
.wb-tabel-kop { display:flex; align-items:center; padding:10px 16px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); font-size:10px; letter-spacing:0.08em; text-transform:uppercase; color:#7d8792; }
.wb-tabel-rij { display:flex; align-items:center; padding:10px 16px; border-bottom:1px solid var(--gray-100); font-size:12.5px; }
.dg-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; }
.dg-kaart { background:#fff; border:1px solid var(--gray-200); border-radius:12px; padding:16px 18px; }
.dg-icoon { font-size:1.2rem; margin-bottom:6px; }
.dg-getal { font-size:1.7rem; font-weight:800; color:var(--brand-700); }
.dg-label { font-size:0.72rem; color:var(--gray-400); text-transform:uppercase; letter-spacing:0.8px; margin-top:4px; font-weight:600; }
@media (max-width:768px) { .dg-grid { grid-template-columns:repeat(2,1fr); } }
</style>

{% if getoonde %}
<div style="border:1px solid var(--gray-200);border-radius:var(--radius-md);overflow:hidden;">
    <div class="wb-tabel-kop">
        <span style="width:110px;">Weegnummer</span>
        <span style="width:100px;">Kenteken</span>
        <span style="flex:1;">Leverancier</span>
        <span style="flex:1;">Materiaal</span>
        <span style="width:130px;text-align:right;">Netto</span>
        <span style="width:160px;">Status</span>
        <span style="width:90px;"></span>
    </div>
    {% for r in getoonde %}
    <div class="wb-tabel-rij">
        <span style="width:110px;font-family:var(--font-mono);color:var(--gray-500);">{{ r.weegnummer }}</span>
        <span style="width:100px;font-weight:700;color:var(--gray-800);">{{ r.kenteken }}</span>
        <span style="flex:1;color:var(--gray-600);">{{ r.leverancier or '—' }}{% if not r.ordernummer %} <span title="Nog geen order gekoppeld" style="font-size:11px;">🔵</span>{% endif %}</span>
        <span style="flex:1;color:var(--gray-600);">{{ r.materiaal or '—' }}</span>
        <span style="width:130px;text-align:right;font-family:var(--font-mono);color:var(--gray-600);">
            {% if r.netto_gewicht %}{{ "{:,.0f}".format(r.netto_gewicht|float) }} kg<br><span style="color:var(--gray-400);font-size:11px;">{{ "{:,.3f}".format(r.netto_gewicht|float / 1000) }} ton</span>{% else %}—{% endif %}
        </span>
        <span style="width:160px;">
            <span style="color:{{ badges[r.status].kleur }};font-size:11.5px;font-weight:700;">{{ badges[r.status].bol }} {{ badges[r.status].label }}</span>
        </span>
        <span style="width:90px;">
            {% if r.status == "Ingewogen" %}
            <a href="/weegbrug/uitwegen/{{ r.id }}" style="font-size:11px;color:var(--brand-600);text-decoration:none;font-weight:600;">Uitwegen →</a>
            <form method="POST" action="/weegbrug/annuleren" onsubmit="return confirm('Weegrecord annuleren?');" style="display:inline;margin:0;margin-left:6px;">
                <input type="hidden" name="record_id" value="{{ r.id }}">
                <button type="submit" style="background:none;border:none;color:var(--gray-300);cursor:pointer;font-size:11px;" title="Annuleren">✕</button>
            </form>
            {% endif %}
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
                                    voertuigen_op_locatie=voertuigen_op_locatie, kpi_vandaag=kpi_vandaag,
                                    kpi_compleet_vandaag=kpi_compleet_vandaag, kpi_probleem=kpi_probleem,
                                    kpi_wacht_op_koppeling=kpi_wacht_op_koppeling, leverancier_namen=leverancier_namen)

@weegbrug_bp.route("/weegbrug/inwegen", methods=["GET", "POST"])
def weegbrug_inwegen():
    _guard = vereist_afdeling_of_403("weegbrug")
    if _guard: return _guard

    if request.method == "POST":
        records = laad_weegbrug()
        nu = datetime.datetime.now()
        nieuw = {
            "id": str(uuid.uuid4()),
            "weegnummer": genereer_weegnummer(records),
            "kenteken": request.form.get("kenteken", "").strip().upper(),
            "herkenningsbron": "handmatig",
            "leverancier": request.form.get("leverancier", "").strip(),
            "chauffeur": request.form.get("chauffeur", "").strip(),
            "transporteur": request.form.get("transporteur", "").strip(),
            "ordernummer": request.form.get("ordernummer", "").strip(),
            "materiaal": request.form.get("materiaal", "").strip(),
            "kwaliteit": request.form.get("kwaliteit", "").strip(),
            "herkomst": request.form.get("herkomst", "").strip(),
            "bestemming": request.form.get("bestemming", "").strip(),
            "referentienummer_leverancier": request.form.get("referentienummer_leverancier", "").strip(),
            "opmerkingen": request.form.get("opmerkingen", "").strip(),
            "bruto_gewicht": request.form.get("bruto_gewicht", "").strip(),
            "inweegmoment": nu.isoformat(timespec="seconds"),
            "weegbrugmedewerker_in": session.get("gebruikersnaam", ""),
            "tarra_gewicht": "",
            "uitweegmoment": "",
            "weegbrugmedewerker_uit": "",
            "netto_gewicht": "",
            "status": "Ingewogen",
            "aangemaakt": nu.strftime("%d-%m-%Y %H:%M"),
        }
        if not nieuw["kenteken"] or not nieuw["bruto_gewicht"]:
            fout = "Kenteken en bruto gewicht zijn verplicht."
            leverancier_namen = sorted({b["naam"] for b in ENF_BEDRIJVEN})
            inhoud = _inwegen_formulier_html()
            pagina = render_simple_page("Inwegen", "weegbrug", inhoud)
            return render_template_string(pagina, fout=fout, leverancier_namen=leverancier_namen, vooringevuld={})
        records.append(nieuw)
        bewaar_weegbrug(records)
        return redirect(url_for("weegbrug.weegbrug_pagina"))

    leverancier_namen = sorted({b["naam"] for b in ENF_BEDRIJVEN})
    inhoud = _inwegen_formulier_html()
    pagina = render_simple_page("Inwegen", "weegbrug", inhoud)
    return render_template_string(pagina, fout=None, leverancier_namen=leverancier_namen, vooringevuld={})

def _inwegen_formulier_html():
    return """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/weegbrug" style="color:var(--gray-400);text-decoration:none;">Weegbrug</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">Inwegen</span>
</div>
<div class="page-title">Vrachtwagen inwegen</div>

{% if fout %}<div style="background:#fef2f2;color:#dc2626;padding:10px 14px;border-radius:8px;font-size:13px;margin-bottom:16px;">{{ fout }}</div>{% endif %}

<form method="POST" style="max-width:640px;">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Kenteken *</label>
            <input type="text" name="kenteken" required style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;text-transform:uppercase;font-family:inherit;">
            <div style="font-size:10.5px;color:var(--gray-300);margin-top:2px;">Handmatig — automatische herkenning volgt later</div>
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Bruto gewicht (kg) *</label>
            <input type="text" name="bruto_gewicht" required style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Leverancier</label>
            <input type="text" name="leverancier" list="leveranciers_lijst" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
            <datalist id="leveranciers_lijst">{% for naam in leverancier_namen %}<option value="{{ naam }}">{% endfor %}</datalist>
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Transporteur</label>
            <input type="text" name="transporteur" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Chauffeur</label>
            <input type="text" name="chauffeur" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Ordernummer</label>
            <input type="text" name="ordernummer" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
            <div style="font-size:10.5px;color:var(--gray-300);margin-top:2px;">Optioneel — kan later gekoppeld worden</div>
        </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Materiaal</label>
            <input type="text" name="materiaal" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Kwaliteit/product</label>
            <input type="text" name="kwaliteit" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Herkomst</label>
            <input type="text" name="herkomst" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Bestemming</label>
            <input type="text" name="bestemming" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
    </div>
    <div style="margin-bottom:10px;">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Referentienummer leverancier</label>
        <input type="text" name="referentienummer_leverancier" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
    </div>
    <div style="margin-bottom:16px;">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Opmerkingen</label>
        <textarea name="opmerkingen" rows="2" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;"></textarea>
    </div>
    <button type="submit" style="padding:9px 20px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">Inwegen registreren</button>
    <a href="/weegbrug" style="margin-left:10px;font-size:12.5px;color:var(--gray-400);text-decoration:none;">Annuleren</a>
</form>
    """

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
        record["uitweegmoment"] = datetime.datetime.now().isoformat(timespec="seconds")
        record["weegbrugmedewerker_uit"] = session.get("gebruikersnaam", "")
        netto, status = _bepaal_netto_en_status(record)
        record["netto_gewicht"] = netto
        record["status"] = status
        bewaar_weegbrug(records)
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
    <div><b>Ingewogen:</b> {{ record.weegbrugmedewerker_in }} op {{ record.aangemaakt }}</div>
</div>

<form method="POST" style="max-width:400px;">
    <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Tarra gewicht (kg, leeggewicht bij vertrek) *</label>
    <input type="text" name="tarra_gewicht" required autofocus style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;margin-bottom:16px;font-family:inherit;">
    <button type="submit" style="padding:9px 20px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">Uitwegen registreren</button>
    <a href="/weegbrug" style="margin-left:10px;font-size:12.5px;color:var(--gray-400);text-decoration:none;">Annuleren</a>
</form>
    """
    pagina = render_simple_page("Uitwegen", "weegbrug", inhoud)
    return render_template_string(pagina, record=record)

@weegbrug_bp.route("/weegbrug/annuleren", methods=["POST"])
def weegbrug_annuleren():
    _guard = vereist_afdeling_of_403("weegbrug")
    if _guard: return _guard
    record_id = request.form.get("record_id", "")
    records = laad_weegbrug()
    record = next((r for r in records if r["id"] == record_id), None)
    if record and (record.get("weegbrugmedewerker_in") == session.get("gebruikersnaam","") or is_huidige_gebruiker_admin()):
        record["status"] = "Geannuleerd"
        bewaar_weegbrug(records)
    return redirect(url_for("weegbrug.weegbrug_pagina"))