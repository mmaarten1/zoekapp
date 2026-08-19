"""
transport_planning.py — Blueprint voor Transport Planning (uitgaande logistiek).

Peute -> fabrieken in Europa. Los van de inkomende keten (Weegbrug/
Logistieke Orders) — dit is een planning-vooraf-flow, geen registratie-bij-
aankomst-flow. Per fabriek een eigen overzicht van geplande/lopende/
afgeronde transporten.

Registratie in app.py met: app.register_blueprint(transport_planning_bp)
"""
import uuid
import datetime
from flask import Blueprint, request, session, redirect, url_for, render_template_string, jsonify

from core import (
    laad_transport_planning, bewaar_transport_planning, genereer_transport_referentie,
    TRANSPORT_PLANNING_STATUSSEN, PAPIERFABRIEKEN, is_huidige_gebruiker_admin,
    vereist_afdeling_of_403, render_simple_page, TRANSPORT_DATA,
    vind_transport_tarieven_dichtbij, laad_documenten,
)

transport_planning_bp = Blueprint("transport_planning", __name__)


@transport_planning_bp.route("/transport-planning")
def transport_planning_pagina():
    _guard = vereist_afdeling_of_403("transport_planning")
    if _guard: return _guard

    alle_transporten = laad_transport_planning()
    filter_fabriek = request.args.get("fabriek", "")
    filter_status = request.args.get("filter_status", "")

    getoond = alle_transporten
    if filter_fabriek:
        getoond = [t for t in getoond if t.get("fabriek") == filter_fabriek]
    if filter_status:
        getoond = [t for t in getoond if t.get("status") == filter_status]
    getoond = sorted(getoond, key=lambda t: t.get("laaddatum",""), reverse=True)

    # --- Per-fabriek overzicht, exact zoals gevraagd: geplande vrachten, nog te
    # plannen, vandaag geladen, onderweg, aangekomen, afgeleverd, problemen ---
    _vandaag = datetime.date.today().isoformat()
    fabriek_namen = sorted({b["naam"] for b in PAPIERFABRIEKEN})
    per_fabriek = []
    for naam in fabriek_namen:
        transporten_fabriek = [t for t in alle_transporten if t.get("fabriek") == naam]
        if not transporten_fabriek:
            continue
        per_fabriek.append({
            "naam": naam,
            "totaal": len(transporten_fabriek),
            "te_plannen": len([t for t in transporten_fabriek if t.get("status") == "Te plannen"]),
            "vandaag_geladen": len([t for t in transporten_fabriek if t.get("status") == "Geladen" and t.get("laaddatum") == _vandaag]),
            "onderweg": len([t for t in transporten_fabriek if t.get("status") == "Onderweg"]),
            "geleverd": len([t for t in transporten_fabriek if t.get("status") in ("Geleverd","Afgerond")]),
        })
    per_fabriek.sort(key=lambda f: f["totaal"], reverse=True)

    inhoud = """
<div class="page-title">Transport Planning</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Uitgaande transporten naar fabrieken in Europa.</p>

<style>
.tp-fabriek-kaart { background:transparent; border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); padding:14px 4px; min-width:200px; }
.tp-fabriek-naam { font-size:12.5px; font-weight:700; color:var(--gray-800); margin-bottom:8px; }
.tp-fabriek-statje { display:inline-block; margin-right:12px; font-size:11.5px; color:var(--gray-500); }
.tp-tabel-kop { display:flex; align-items:center; padding:10px 16px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); font-size:10px; letter-spacing:0.08em; text-transform:uppercase; color:#7d8792; }
.tp-tabel-rij { display:flex; align-items:center; padding:10px 16px; border-bottom:1px solid var(--gray-100); font-size:12.5px; }
</style>

{% if per_fabriek %}
<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Per fabriek</div>
<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px;">
    {% for f in per_fabriek %}
    <a href="/transport-planning?fabriek={{ f.naam|urlencode }}" class="tp-fabriek-kaart" style="text-decoration:none;">
        <div class="tp-fabriek-naam">{{ f.naam }}</div>
        <span class="tp-fabriek-statje">Totaal: <b>{{ f.totaal }}</b></span>
        <span class="tp-fabriek-statje">Te plannen: <b>{{ f.te_plannen }}</b></span>
        <span class="tp-fabriek-statje">Onderweg: <b>{{ f.onderweg }}</b></span>
        <span class="tp-fabriek-statje">Geleverd: <b>{{ f.geleverd }}</b></span>
    </a>
    {% endfor %}
</div>
{% endif %}

<a href="/transport-planning/nieuw" style="display:inline-block;margin-bottom:20px;font-size:12.5px;font-weight:700;color:#fff;background:var(--brand-600);text-decoration:none;padding:8px 16px;border-radius:6px;">+ Transport plannen</a>

<form method="GET" style="display:flex;gap:8px;margin-bottom:16px;">
    <select name="fabriek" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle fabrieken</option>
        {% for naam in fabriek_namen %}<option value="{{ naam }}" {% if filter_fabriek == naam %}selected{% endif %}>{{ naam }}</option>{% endfor %}
    </select>
    <select name="filter_status" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle statussen</option>
        {% for st in statussen %}<option value="{{ st }}" {% if filter_status == st %}selected{% endif %}>{{ st }}</option>{% endfor %}
    </select>
</form>

{% if getoond %}
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);">
    <div class="tp-tabel-kop">
        <span style="width:120px;">Referentie</span>
        <span style="flex:1;">Fabriek</span>
        <span style="width:100px;">Laaddatum</span>
        <span style="flex:1;">Materiaal</span>
        <span style="width:80px;text-align:right;">Ton</span>
        <span style="width:100px;">Trucks</span>
        <span style="width:160px;">Status</span>
    </div>
    {% for t in getoond %}
    <div class="tp-tabel-rij">
        <span style="width:120px;font-family:var(--font-mono);color:var(--gray-500);"><a href="/transport-planning/{{ t.id }}" style="color:var(--brand-600);text-decoration:none;font-weight:600;">{{ t.referentienummer }}</a></span>
        <span style="flex:1;color:var(--gray-700);">{{ t.fabriek or '—' }}</span>
        <span style="width:100px;color:var(--gray-600);">{{ t.laaddatum or '—' }}</span>
        <span style="flex:1;color:var(--gray-600);">{{ t.materiaal or '—' }}</span>
        <span style="width:80px;text-align:right;font-family:var(--font-mono);color:var(--gray-600);">{{ t.hoeveelheid or '—' }}</span>
        <span style="width:100px;color:var(--gray-600);">{{ t.aantal_trucks or '—' }}</span>
        <span style="width:160px;font-size:11.5px;font-weight:600;color:var(--gray-600);">{{ t.status }}</span>
    </div>
    {% endfor %}
</div>
<div style="padding:10px 4px;font-size:0.8rem;color:var(--gray-400);">{{ getoond|length }} transporten</div>
{% else %}
<div class="lege-staat">Nog geen transporten gepland.</div>
{% endif %}
    """
    pagina = render_simple_page("Transport Planning", "transport_planning", inhoud)
    return render_template_string(pagina, getoond=getoond, statussen=TRANSPORT_PLANNING_STATUSSEN,
                                    per_fabriek=per_fabriek, fabriek_namen=fabriek_namen,
                                    filter_fabriek=filter_fabriek, filter_status=filter_status)

@transport_planning_bp.route("/transport-planning/nieuw", methods=["GET", "POST"])
def transport_planning_nieuw():
    _guard = vereist_afdeling_of_403("transport_planning")
    if _guard: return _guard

    if request.method == "POST":
        transporten = laad_transport_planning()
        nu = datetime.datetime.now()
        nieuw = {
            "id": str(uuid.uuid4()),
            "referentienummer": genereer_transport_referentie(transporten),
            "fabriek": request.form.get("fabriek", "").strip(),
            "laadlocatie": request.form.get("laadlocatie", "Alblasserdam").strip(),
            "loslocatie": request.form.get("loslocatie", "").strip(),
            "laaddatum": request.form.get("laaddatum", "").strip(),
            "laadtijd": request.form.get("laadtijd", "").strip(),
            "losdatum": request.form.get("losdatum", "").strip(),
            "lostijd": request.form.get("lostijd", "").strip(),
            "materiaal": request.form.get("materiaal", "").strip(),
            "hoeveelheid": request.form.get("hoeveelheid", "").strip(),
            "aantal_trucks": request.form.get("aantal_trucks", "").strip(),
            "transporteur": request.form.get("transporteur", "").strip(),
            "kenteken": request.form.get("kenteken", "").strip(),
            "chauffeur": request.form.get("chauffeur", "").strip(),
            "transporttarief": request.form.get("transporttarief", "").strip(),
            "status": "Te plannen",
            "opmerkingen": request.form.get("opmerkingen", "").strip(),
            "aangemaakt_door": session.get("gebruikersnaam", ""),
            "aangemaakt": nu.strftime("%d-%m-%Y %H:%M"),
        }
        transporten.append(nieuw)
        bewaar_transport_planning(transporten)
        return redirect(url_for("transport_planning.transport_planning_detail", transport_id=nieuw["id"]))

    fabriek_namen = sorted({b["naam"] for b in PAPIERFABRIEKEN})
    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/transport-planning" style="color:var(--gray-400);text-decoration:none;">Transport Planning</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">Nieuw</span>
</div>
<div class="page-title">Transport plannen</div>

<form method="POST" style="max-width:680px;">
    <div style="margin-bottom:10px;">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Fabriek</label>
        <input type="text" name="fabriek" list="fabrieken_lijst" onblur="toonTariefSuggestie(this.value)" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        <datalist id="fabrieken_lijst">{% for naam in fabriek_namen %}<option value="{{ naam }}">{% endfor %}</datalist>
        <div id="tarief_suggestie" style="margin-top:6px;font-size:11.5px;"></div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Laadlocatie</label>
            <input type="text" name="laadlocatie" value="Alblasserdam" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Loslocatie</label>
            <input type="text" name="loslocatie" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:10px;margin-bottom:10px;">
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Laaddatum</label>
            <input type="date" name="laaddatum" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Laadtijd</label>
            <input type="time" name="laadtijd" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Losdatum</label>
            <input type="date" name="losdatum" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Lostijd</label>
            <input type="time" name="lostijd" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:10px;">
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Materiaal</label>
            <input type="text" name="materiaal" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Hoeveelheid (ton)</label>
            <input type="text" name="hoeveelheid" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Aantal trucks</label>
            <input type="text" name="aantal_trucks" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Transporteur</label>
            <input type="text" name="transporteur" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Transporttarief (€)</label>
            <input type="text" name="transporttarief" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Kenteken (indien bekend)</label>
            <input type="text" name="kenteken" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;text-transform:uppercase;font-family:inherit;">
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Chauffeur (indien bekend)</label>
            <input type="text" name="chauffeur" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
    </div>
    <div style="margin-bottom:16px;">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Opmerkingen</label>
        <textarea name="opmerkingen" rows="2" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;"></textarea>
    </div>
    <button type="submit" style="padding:9px 20px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">Transport aanmaken</button>
    <a href="/transport-planning" style="margin-left:10px;font-size:12.5px;color:var(--gray-400);text-decoration:none;">Annuleren</a>
</form>

<script>
async function toonTariefSuggestie(fabriekNaam) {
    var doel = document.getElementById("tarief_suggestie");
    if (!fabriekNaam) { doel.innerHTML = ""; return; }
    doel.innerHTML = '<span style="color:var(--gray-300);">Tarieven zoeken...</span>';
    try {
        const res = await fetch("/api/transport-tarieven-fabriek?fabriek=" + encodeURIComponent(fabriekNaam));
        const data = await res.json();
        const forwarders = Object.keys(data);
        if (!forwarders.length) { doel.innerHTML = '<span style="color:var(--gray-300);">Geen bekende tarieven in de buurt van deze fabriek.</span>'; return; }
        doel.innerHTML = '<span style="color:var(--gray-500);">Beschikbare tarieven in de buurt: </span>' + forwarders.map(function(fw) {
            var info = data[fw];
            var tariefTekst = Object.entries(info.tarieven).map(function(kv) { return kv[0] + ": " + kv[1]; }).join(", ");
            return '<b style="color:var(--gray-800);">' + fw + '</b> (' + info.stad + ', ' + info.afstand + ' km) — ' + tariefTekst;
        }).join(' &nbsp;|&nbsp; ');
    } catch (e) { doel.innerHTML = ""; }
}
</script>
    """
    pagina = render_simple_page("Transport plannen", "transport_planning", inhoud)
    return render_template_string(pagina, fabriek_namen=fabriek_namen)

@transport_planning_bp.route("/transport-planning/<transport_id>")
def transport_planning_detail(transport_id):
    _guard = vereist_afdeling_of_403("transport_planning")
    if _guard: return _guard

    transporten = laad_transport_planning()
    transport = next((t for t in transporten if t["id"] == transport_id), None)
    if not transport:
        pagina = render_simple_page("Niet gevonden", "transport_planning", '<div class="page-title">Transport niet gevonden</div><div class="lege-staat">Dit transport bestaat niet (meer). <a href="/transport-planning">Terug naar Transport Planning</a></div>')
        return render_template_string(pagina), 404

    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/transport-planning" style="color:var(--gray-400);text-decoration:none;">Transport Planning</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">{{ transport.referentienummer }}</span>
</div>
<div class="page-title">{{ transport.referentienummer }} — {{ transport.fabriek or 'Geen fabriek' }}</div>

<div style="display:flex;gap:24px;flex-wrap:wrap;">
<div style="flex:1;min-width:340px;">
    <div style="background:transparent;border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);padding:16px 4px;margin-bottom:16px;">
        <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Status</div>
        <form method="POST" action="/transport-planning/{{ transport.id }}/status">
            <select name="nieuwe_status" onchange="this.form.submit()" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-weight:600;">
                {% for st in statussen %}<option value="{{ st }}" {% if transport.status == st %}selected{% endif %}>{{ st }}</option>{% endfor %}
            </select>
        </form>
    </div>

    <div style="background:var(--gray-50);border-radius:8px;padding:14px 16px;font-size:12.5px;color:var(--gray-600);">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
            <div><b>Laadlocatie:</b> {{ transport.laadlocatie or '—' }}</div>
            <div><b>Loslocatie:</b> {{ transport.loslocatie or '—' }}</div>
            <div><b>Laaddatum:</b> {{ transport.laaddatum or '—' }} {{ transport.laadtijd }}</div>
            <div><b>Losdatum:</b> {{ transport.losdatum or '—' }} {{ transport.lostijd }}</div>
            <div><b>Materiaal:</b> {{ transport.materiaal or '—' }}</div>
            <div><b>Hoeveelheid:</b> {{ transport.hoeveelheid or '—' }}{% if transport.hoeveelheid %} ton{% endif %}</div>
            <div><b>Aantal trucks:</b> {{ transport.aantal_trucks or '—' }}</div>
            <div><b>Transporteur:</b> {{ transport.transporteur or '—' }}</div>
            <div><b>Kenteken:</b> {{ transport.kenteken or '—' }}</div>
            <div><b>Chauffeur:</b> {{ transport.chauffeur or '—' }}</div>
            <div><b>Transporttarief:</b> {% if transport.transporttarief %}€{{ transport.transporttarief }}{% else %}—{% endif %}</div>
        </div>
        {% if transport.opmerkingen %}<div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--gray-200);"><b>Opmerkingen:</b> {{ transport.opmerkingen }}</div>{% endif %}
    </div>
</div>

<div style="flex:1;min-width:300px;">
    <div style="background:transparent;border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);padding:16px 4px;">
        <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Documenten (CMR, POD, etc.)</div>
        <div id="docslijst" style="margin-bottom:8px;font-size:12.5px;color:var(--gray-400);">Laden...</div>
        <input type="file" id="docupload" accept=".pdf,.doc,.docx" style="font-size:12px;">
        <button type="button" onclick="uploadTransportDoc()" style="font-size:11.5px;padding:4px 10px;background:var(--brand-600);color:#fff;border:none;border-radius:5px;cursor:pointer;margin-left:6px;">Uploaden</button>
    </div>
</div>
</div>

<script>
var TRANSPORTREF = "{{ transport.referentienummer }}";
async function laadTransportDocs() {
    var lijstDiv = document.getElementById("docslijst");
    try {
        const res = await fetch("/api/documenten?bedrijf=" + encodeURIComponent(TRANSPORTREF));
        const docs = await res.json();
        if (!docs.length) { lijstDiv.innerHTML = "Nog geen documenten geüpload."; return; }
        lijstDiv.innerHTML = docs.map(function(d) {
            return '<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;">' +
                '<a href="/documenten_uploads/' + encodeURIComponent(d.bestandsnaam) + '" target="_blank" style="color:var(--brand-600);text-decoration:none;">' + d.originele_naam + '</a>' +
                '<span style="font-size:11px;color:var(--gray-300);">' + d.timestamp + '</span></div>';
        }).join("");
    } catch (e) { lijstDiv.innerHTML = "Kon documenten niet laden."; }
}
async function uploadTransportDoc() {
    var input = document.getElementById("docupload");
    if (!input.files.length) { alert("Kies eerst een bestand."); return; }
    var form = new FormData();
    form.append("bedrijf", TRANSPORTREF);
    form.append("document", input.files[0]);
    const res = await fetch("/api/documenten", {method: "POST", body: form});
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    input.value = "";
    laadTransportDocs();
}
laadTransportDocs();
</script>
    """
    pagina = render_simple_page(transport["referentienummer"], "transport_planning", inhoud)
    return render_template_string(pagina, transport=transport, statussen=TRANSPORT_PLANNING_STATUSSEN)

@transport_planning_bp.route("/transport-planning/<transport_id>/status", methods=["POST"])
def transport_planning_status(transport_id):
    _guard = vereist_afdeling_of_403("transport_planning")
    if _guard: return _guard

    transporten = laad_transport_planning()
    transport = next((t for t in transporten if t["id"] == transport_id), None)
    nieuwe_status = request.form.get("nieuwe_status", "")
    if transport and nieuwe_status in TRANSPORT_PLANNING_STATUSSEN:
        transport["status"] = nieuwe_status
        bewaar_transport_planning(transporten)
    return redirect(url_for("transport_planning.transport_planning_detail", transport_id=transport_id))

@transport_planning_bp.route("/transport-rates")
def transport_rates_pagina():
    _guard = vereist_afdeling_of_403("transport_rates")
    if _guard: return _guard

    filter_forwarder = request.args.get("forwarder", "")
    forwarder_namen = sorted(TRANSPORT_DATA.keys())

    inhoud = """
<div class="page-title">Transport Rates</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">
    Tarieven zoals geüpload door transporteurs zelf via de forwarder-portal.
    {% if not forwarder_namen %}Nog geen tarieven geüpload.{% endif %}
</p>

<style>
.tr-tabel-kop { display:flex; align-items:center; padding:10px 16px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); font-size:10px; letter-spacing:0.08em; text-transform:uppercase; color:#7d8792; }
.tr-tabel-rij { display:flex; align-items:flex-start; padding:10px 16px; border-bottom:1px solid var(--gray-100); font-size:12.5px; }
</style>

{% if forwarder_namen %}
<form method="GET" style="margin-bottom:16px;">
    <select name="forwarder" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Kies een transporteur</option>
        {% for naam in forwarder_namen %}<option value="{{ naam }}" {% if filter_forwarder == naam %}selected{% endif %}>{{ naam }}</option>{% endfor %}
    </select>
</form>

{% if filter_forwarder %}
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);">
    <div class="tr-tabel-kop">
        <span style="width:160px;">Stad</span>
        <span style="flex:1;">Tarieven</span>
    </div>
    {% for record in steden_van_forwarder %}
    <div class="tr-tabel-rij">
        <span style="width:160px;font-weight:600;color:var(--gray-800);">{{ record.stad }}</span>
        <span style="flex:1;color:var(--gray-600);">
            {% for kolom, waarde in record.tarieven.items() %}<span style="display:inline-block;margin-right:14px;">{{ kolom }}: <b style="color:var(--gray-800);">{{ waarde }}</b></span>{% endfor %}
        </span>
    </div>
    {% endfor %}
</div>
<div style="padding:10px 4px;font-size:0.8rem;color:var(--gray-400);">{{ steden_van_forwarder|length }} steden</div>
{% else %}
<div class="lege-staat">Kies hierboven een transporteur om de tarieven te bekijken.</div>
{% endif %}
{% else %}
<div class="lege-staat">Nog geen tarieven geüpload. Transporteurs kunnen dit zelf doen via <a href="/forwarder-upload" style="color:var(--brand-600);">de forwarder-portal</a>.</div>
{% endif %}
    """
    steden_van_forwarder = TRANSPORT_DATA.get(filter_forwarder, []) if filter_forwarder else []
    pagina = render_simple_page("Transport Rates", "transport_rates", inhoud)
    return render_template_string(pagina, forwarder_namen=forwarder_namen, filter_forwarder=filter_forwarder,
                                    steden_van_forwarder=steden_van_forwarder)

@transport_planning_bp.route("/api/transport-tarieven-fabriek")
def api_transport_tarieven_fabriek():
    _guard = vereist_afdeling_of_403("transport_planning")
    if _guard: return _guard
    fabriek_naam = request.args.get("fabriek", "").strip()
    fabriek = next((f for f in PAPIERFABRIEKEN if f["naam"] == fabriek_naam), None)
    if not fabriek or not fabriek.get("lat") or not fabriek.get("lon"):
        return jsonify({})
    return jsonify(vind_transport_tarieven_dichtbij(fabriek["lat"], fabriek["lon"]))

@transport_planning_bp.route("/transport-overview")
def transport_overview_pagina():
    _guard = vereist_afdeling_of_403("transport_overview")
    if _guard: return _guard

    alle_transporten = laad_transport_planning()
    alle_documenten = laad_documenten()
    fabriek_land_lookup = {f["naam"]: f.get("land", "") for f in PAPIERFABRIEKEN}
    _vandaag = datetime.date.today().isoformat()

    def is_vertraagd(t):
        return t.get("laaddatum","") and t["laaddatum"] < _vandaag and t.get("status") in ("Te plannen", "Transport aangevraagd", "Transporteur toegewezen", "Bevestigd")

    # --- Control tower-KPI's, exact zoals gevraagd ---
    kpi_gepland = [t for t in alle_transporten if t.get("status") not in ("Te plannen",)]
    kpi_nog_te_plannen = [t for t in alle_transporten if t.get("status") == "Te plannen"]
    kpi_onderweg = [t for t in alle_transporten if t.get("status") == "Onderweg"]
    kpi_vertraagd = [t for t in alle_transporten if is_vertraagd(t)]
    kpi_geleverd = [t for t in alle_transporten if t.get("status") in ("Geleverd", "Afgerond")]
    kpi_ontbrekende_docs = [t for t in alle_transporten if t.get("status") != "Te plannen" and not alle_documenten.get(t.get("referentienummer",""), [])]

    # --- Per land/regio (sectie 10): aantal, volume, gem. kosten, transporteurs, openstaand/gepland ---
    landen = sorted({fabriek_land_lookup.get(t.get("fabriek",""), "") for t in alle_transporten if fabriek_land_lookup.get(t.get("fabriek",""))})
    per_land = []
    for land in landen:
        transporten_land = [t for t in alle_transporten if fabriek_land_lookup.get(t.get("fabriek","")) == land]
        volumes = [float(t["hoeveelheid"]) for t in transporten_land if t.get("hoeveelheid") and t["hoeveelheid"].replace(".","",1).replace(",","").isdigit()]
        kosten = [float(t["transporttarief"]) for t in transporten_land if t.get("transporttarief") and t["transporttarief"].replace(".","",1).replace(",","").isdigit()]
        per_land.append({
            "land": land,
            "aantal": len(transporten_land),
            "volume": round(sum(volumes), 1) if volumes else 0,
            "gem_kosten": round(sum(kosten)/len(kosten), 2) if kosten else None,
            "transporteurs": len({t.get("transporteur","") for t in transporten_land if t.get("transporteur")}),
            "openstaand": len([t for t in transporten_land if t.get("status") not in ("Geleverd","Afgerond")]),
            "gepland": len([t for t in transporten_land if t.get("status") not in ("Te plannen",)]),
        })
    per_land.sort(key=lambda l: l["aantal"], reverse=True)

    inhoud = """
<div class="page-title">Transport Overview</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Control tower voor alle uitgaande transporten.</p>

<style>
.tov-statustabel { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:24px; }
.tov-kaart { background:transparent; border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); padding:14px 4px; }
.tov-getal { font-size:1.5rem; font-weight:800; color:var(--gray-800); }
.tov-label { font-size:0.7rem; color:var(--gray-400); text-transform:uppercase; letter-spacing:0.6px; margin-top:2px; font-weight:600; }
.tov-tabel-kop { display:flex; align-items:center; padding:10px 16px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); font-size:10px; letter-spacing:0.08em; text-transform:uppercase; color:#7d8792; }
.tov-tabel-rij { display:flex; align-items:center; padding:10px 16px; border-bottom:1px solid var(--gray-100); font-size:12.5px; }
</style>

<div class="tov-statustabel">
    <div class="tov-kaart"><div class="tov-getal">{{ kpi_gepland|length }}</div><div class="tov-label">Gepland</div></div>
    <div class="tov-kaart"><div class="tov-getal">{{ kpi_nog_te_plannen|length }}</div><div class="tov-label">Nog te plannen</div></div>
    <div class="tov-kaart"><div class="tov-getal">{{ kpi_onderweg|length }}</div><div class="tov-label">Onderweg</div></div>
    <div class="tov-kaart" style="{% if kpi_vertraagd %}border-color:#fecaca;{% endif %}"><div class="tov-getal" style="{% if kpi_vertraagd %}color:#dc2626;{% endif %}">{{ kpi_vertraagd|length }}</div><div class="tov-label">Vertraagd</div></div>
    <div class="tov-kaart"><div class="tov-getal">{{ kpi_geleverd|length }}</div><div class="tov-label">Geleverd</div></div>
    <div class="tov-kaart"><div class="tov-getal">{{ kpi_ontbrekende_docs|length }}</div><div class="tov-label">Ontbrekende documenten</div></div>
</div>

{% if kpi_vertraagd %}
<div style="font-size:11px;font-weight:700;color:#dc2626;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Vertraagde transporten</div>
<div style="border:none;border-top:2px solid #fecaca;border-bottom:2px solid #fecaca;margin-bottom:24px;">
    {% for t in kpi_vertraagd %}
    <div class="tov-tabel-rij"><a href="/transport-planning/{{ t.id }}" style="color:var(--brand-600);text-decoration:none;font-weight:600;width:120px;">{{ t.referentienummer }}</a><span style="flex:1;">{{ t.fabriek }}</span><span style="color:#dc2626;">Laaddatum {{ t.laaddatum }} verstreken, nog niet geladen</span></div>
    {% endfor %}
</div>
{% endif %}

{% if per_land %}
<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Per land/regio</div>
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);margin-bottom:24px;">
    <div class="tov-tabel-kop">
        <span style="flex:1;">Land</span>
        <span style="width:70px;text-align:right;">Aantal</span>
        <span style="width:90px;text-align:right;">Volume (ton)</span>
        <span style="width:110px;text-align:right;">Gem. kosten</span>
        <span style="width:100px;text-align:right;">Transporteurs</span>
        <span style="width:90px;text-align:right;">Openstaand</span>
    </div>
    {% for l in per_land %}
    <div class="tov-tabel-rij">
        <span style="flex:1;font-weight:600;color:var(--gray-800);"><a href="/transport-planning?fabriek=" style="color:inherit;text-decoration:none;">{{ l.land }}</a></span>
        <span style="width:70px;text-align:right;color:var(--gray-600);">{{ l.aantal }}</span>
        <span style="width:90px;text-align:right;color:var(--gray-600);">{{ l.volume }}</span>
        <span style="width:110px;text-align:right;color:var(--gray-600);">{% if l.gem_kosten %}€{{ l.gem_kosten }}{% else %}—{% endif %}</span>
        <span style="width:100px;text-align:right;color:var(--gray-600);">{{ l.transporteurs }}</span>
        <span style="width:90px;text-align:right;color:var(--gray-600);">{{ l.openstaand }}</span>
    </div>
    {% endfor %}
</div>
{% else %}
<div class="lege-staat">Nog geen transporten met een gekoppelde fabriek (land onbekend).</div>
{% endif %}
    """
    pagina = render_simple_page("Transport Overview", "transport_overview", inhoud)
    return render_template_string(pagina, kpi_gepland=kpi_gepland, kpi_nog_te_plannen=kpi_nog_te_plannen,
                                    kpi_onderweg=kpi_onderweg, kpi_vertraagd=kpi_vertraagd, kpi_geleverd=kpi_geleverd,
                                    kpi_ontbrekende_docs=kpi_ontbrekende_docs, per_land=per_land)