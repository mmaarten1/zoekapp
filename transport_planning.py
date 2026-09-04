"""
transport_planning.py — Blueprint voor Transport Planning (uitgaande logistiek).

Peute -> fabrieken in Europa. Los van de inkomende keten (Weegbrug/
Logistieke Orders) — dit is een planning-vooraf-flow, geen registratie-bij-
aankomst-flow. Per fabriek een eigen overzicht van geplande/lopende/
afgeronde transporten.

Registratie in app.py met: app.register_blueprint(transport_planning_bp)
"""
import uuid
import re
import datetime
from flask import Blueprint, request, session, redirect, url_for, render_template_string, jsonify

from core import (
    laad_transport_planning, bewaar_transport_planning, genereer_transport_referentie,
    TRANSPORT_PLANNING_STATUSSEN, PAPIERFABRIEKEN, ENF_BEDRIJVEN, is_huidige_gebruiker_admin,
    toegewezen_klant_fabrieken, laad_pod_havens, laad_handelsorders, parse_hoeveelheid_getal,
    vereist_afdeling_of_403, render_simple_page, TRANSPORT_DATA,
    vind_transport_tarieven_dichtbij, laad_documenten, leverancier_instelling_voor,
)

transport_planning_bp = Blueprint("transport_planning", __name__)


@transport_planning_bp.route("/transport-planning")
def transport_planning_pagina():
    _guard = vereist_afdeling_of_403("transport_planning")
    if _guard: return _guard

    alle_transporten = laad_transport_planning()

    # Vrachtwagen- en zeevaart-afdelingen zijn twee aparte teams binnen Peute die
    # elk alleen hun eigen modus inplannen — logistiek (en admins) blijven alles
    # zien. Geen aparte pagina's, gewoon een filter op basis van de ingelogde
    # gebruiker's afdeling.
    _eigen_afdeling = session.get("afdeling", "")
    if not is_huidige_gebruiker_admin():
        if _eigen_afdeling == "transport_vrachtwagen":
            alle_transporten = [t for t in alle_transporten if t.get("transportmodus", "Vrachtwagen") != "Schip"]
        elif _eigen_afdeling == "transport_zeevaart":
            alle_transporten = [t for t in alle_transporten if t.get("transportmodus", "Vrachtwagen") == "Schip"]

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
    fabriek_namen = sorted({b["naam"] for b in toegewezen_klant_fabrieken()})
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
{% if aangemaakt %}
<div style="background:#f0fdf4;color:#16a34a;padding:10px 14px;border-radius:8px;margin-bottom:16px;font-size:12.5px;">
    {{ aangemaakt }} trucks aangemaakt en klaargezet als 'Te plannen'.
</div>
{% endif %}
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
                                    filter_fabriek=filter_fabriek, filter_status=filter_status,
                                    aangemaakt=request.args.get("aangemaakt", ""))

@transport_planning_bp.route("/transport-planning/nieuw", methods=["GET", "POST"])
def transport_planning_nieuw():
    _guard = vereist_afdeling_of_403("transport_planning")
    if _guard: return _guard

    if request.method == "POST":
        transporten = laad_transport_planning()
        nu = datetime.datetime.now()
        _modus = request.form.get("transportmodus", "Vrachtwagen").strip()

        _gedeelde_velden = {
            "transportmodus": _modus,
            "leverancier": request.form.get("leverancier_tp", "").strip(),
            "fabriek": request.form.get("fabriek", "").strip(),
            "laadlocatie": request.form.get("laadlocatie", "Alblasserdam").strip(),
            "loslocatie": request.form.get("loslocatie", "").strip(),
            "haven": request.form.get("haven", "").strip(),
            "forwarder": request.form.get("forwarder", "").strip(),
            "vervoerder": request.form.get("vervoerder", "").strip(),
            "laaddatum": request.form.get("laaddatum", "").strip(),
            "laadtijd": request.form.get("laadtijd", "").strip(),
            "losdatum": request.form.get("losdatum", "").strip(),
            "lostijd": request.form.get("lostijd", "").strip(),
            "transporteur": request.form.get("transporteur", "").strip(),
            "transporttarief": request.form.get("transporttarief", "").strip(),
            "status": "Te plannen",
            "opmerkingen": request.form.get("opmerkingen", "").strip(),
            "contract_referentie": request.form.get("contract_referentie", "").strip(),
            "aangemaakt_door": session.get("gebruikersnaam", ""),
            "aangemaakt": nu.strftime("%d-%m-%Y %H:%M"),
        }

        # Combi: dit contract wordt samen met (een) ander(e) contract(en) in
        # dezelfde vrachtwagen/container geladen (kleine order, truck vol
        # maken) — allemaal gekoppeld via een gedeelde combi_groep_id.
        _combi_ruw = request.form.get("combi_contracten", "").strip()
        _combi_contracten = [c.strip() for c in _combi_ruw.split(",") if c.strip()]
        _combi_groep_id = str(uuid.uuid4()) if _combi_contracten else ""
        _gedeelde_velden["combi_groep_id"] = _combi_groep_id
        _gedeelde_velden["combi_gekoppelde_contracten"] = _combi_contracten

        nieuwe_records = []
        if _modus == "Schip":
            # Schip: één record, zoals voorheen — geen aparte truck-rijen.
            nieuw = dict(_gedeelde_velden)
            nieuw["id"] = str(uuid.uuid4())
            nieuw["referentienummer"] = genereer_transport_referentie(transporten)
            nieuw["materiaal"] = request.form.get("materiaal", "").strip()
            nieuw["hoeveelheid"] = request.form.get("hoeveelheid", "").strip()
            nieuw["kenteken"] = ""
            nieuwe_records.append(nieuw)
        else:
            # Vrachtwagen: één record PER TRUCK-RIJ (materiaal_1/hoeveelheid_1/
            # kenteken_1, materiaal_2/..., enz.) — elke truck heeft een eigen
            # kenteken en status die onafhankelijk bijgehouden moeten worden.
            # Verzamel ALLE aanwezige indices i.p.v. een while-lus die stopt bij
            # het eerste ontbrekende nummer: als de gebruiker een middelste rij
            # verwijdert (bv. rij 1 weg, rij 2 en 3 blijven staan), ontstaat een
            # gat in de nummering — een while-lus vanaf i=1 zou dan meteen
            # stoppen en rij 2/3 nooit verwerken.
            _rij_indices = set()
            for _veldnaam in request.form:
                _match = re.match(r"^materiaal_(\d+)$|^hoeveelheid_(\d+)$|^kenteken_(\d+)$", _veldnaam)
                if _match:
                    _rij_indices.add(int(next(g for g in _match.groups() if g)))
            for i in sorted(_rij_indices):
                _materiaal_i = request.form.get(f"materiaal_{i}", "").strip()
                _hoeveelheid_i = request.form.get(f"hoeveelheid_{i}", "").strip()
                _kenteken_i = request.form.get(f"kenteken_{i}", "").strip()
                if _materiaal_i or _hoeveelheid_i:
                    nieuw = dict(_gedeelde_velden)
                    nieuw["id"] = str(uuid.uuid4())
                    nieuw["referentienummer"] = genereer_transport_referentie(transporten + nieuwe_records)
                    nieuw["materiaal"] = _materiaal_i
                    nieuw["hoeveelheid"] = _hoeveelheid_i
                    nieuw["kenteken"] = _kenteken_i
                    nieuwe_records.append(nieuw)
            if not nieuwe_records:
                # Vangnet: geen enkele truck-rij ingevuld -> toch één (lege) record aanmaken,
                # zodat de gebruiker niet met een onverklaarde 'niks gebeurde er'-actie blijft zitten.
                nieuw = dict(_gedeelde_velden)
                nieuw["id"] = str(uuid.uuid4())
                nieuw["referentienummer"] = genereer_transport_referentie(transporten)
                nieuw["materiaal"] = request.form.get("materiaal", "").strip()
                nieuw["hoeveelheid"] = request.form.get("hoeveelheid", "").strip()
                nieuw["kenteken"] = ""
                nieuwe_records.append(nieuw)

        transporten.extend(nieuwe_records)
        bewaar_transport_planning(transporten)
        if len(nieuwe_records) == 1:
            return redirect(url_for("transport_planning.transport_planning_detail", transport_id=nieuwe_records[0]["id"]))
        return redirect(url_for("transport_planning.transport_planning_pagina", aangemaakt=len(nieuwe_records)))

    fabriek_namen = sorted({b["naam"] for b in toegewezen_klant_fabrieken()})
    fabriek_steden = {b["naam"]: b.get("stad","") for b in toegewezen_klant_fabrieken()}
    leverancier_namen_tp = sorted({b["naam"] for b in ENF_BEDRIJVEN})
    _vi_leverancier = request.args.get("leverancier", "").strip()
    _vi_materiaal = request.args.get("materiaal", "").strip()
    _vi_hoeveelheid = request.args.get("hoeveelheid", "").strip()
    _vi_contract = request.args.get("contract_referentie", "").strip()
    _vi_fabriek = request.args.get("fabriek", "").strip()

    # Vanuit een contract geopend: haven, laadlocatie en transportmodus komen
    # automatisch uit het Handelsorder over — vervangbaar, want soms verandert
    # de situatie (andere haven, andere lading).
    _vi_haven = ""
    _vi_transportmodus = ""
    if _vi_contract:
        _gekoppeld_contract = next((h for h in laad_handelsorders() if h.get("contractnummer") == _vi_contract), None)
        if _gekoppeld_contract:
            _vi_haven = _gekoppeld_contract.get("pod_haven", "")
            _vi_transportmodus = _gekoppeld_contract.get("transportmodus", "")
            if _gekoppeld_contract.get("afhaal_locatienaam"):
                request_laadlocatie_override = _gekoppeld_contract["afhaal_locatienaam"]
            else:
                request_laadlocatie_override = "Alblasserdam"
        else:
            request_laadlocatie_override = "Alblasserdam"
    else:
        request_laadlocatie_override = "Alblasserdam"

    # Zonder contract: de eigen afdeling (vrachtwagen/zeevaart) bepaalt een
    # logische standaardkeuze — blijft gewoon aanpasbaar.
    if not _vi_transportmodus:
        if session.get("afdeling") == "transport_zeevaart":
            _vi_transportmodus = "Schip"
        else:
            _vi_transportmodus = "Vrachtwagen"

    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/transport-planning" style="color:var(--gray-400);text-decoration:none;">Transport Planning</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">Nieuw</span>
</div>
<div class="page-title">Transport plannen</div>
{% if vi_contract %}
<div style="background:#eff6ff;color:#1d4ed8;padding:10px 14px;border-radius:8px;margin-bottom:16px;font-size:12.5px;">
    Wordt gekoppeld aan contract <b>{{ vi_contract }}</b>{% if vi_leverancier %} (leverancier: {{ vi_leverancier }}){% endif %}.
</div>
{% endif %}

<form method="POST" style="max-width:680px;">
    <input type="hidden" name="contract_referentie" value="{{ vi_contract }}">
    <div style="margin-bottom:10px;">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Transportmodus</label>
        <select name="transportmodus" id="transportmodus_select" onchange="wisselTransportmodus()" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
            <option value="Vrachtwagen" {% if vi_transportmodus == "Vrachtwagen" %}selected{% endif %}>Vrachtwagen</option>
            <option value="Schip" {% if vi_transportmodus == "Schip" %}selected{% endif %}>Schip (zeevaart)</option>
        </select>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Leverancier (bij ophalen)</label>
            <input type="text" name="leverancier_tp" id="leverancier_tp_veld" value="{{ vi_leverancier }}" list="leveranciers_tp_lijst" onchange="zoekAfhaallocaties(this.value)" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
            <datalist id="leveranciers_tp_lijst">{% for naam in leverancier_namen_tp %}<option value="{{ naam }}">{% endfor %}</datalist>
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Fabriek</label>
            <input type="text" name="fabriek" value="{{ vi_fabriek }}" list="fabrieken_lijst" onchange="vulLoslocatieIn(this.value); toonTariefSuggestie(this.value);" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
            <datalist id="fabrieken_lijst">{% for naam in fabriek_namen %}<option value="{{ naam }}">{% endfor %}</datalist>
            <div id="tarief_suggestie" style="margin-top:6px;font-size:11.5px;"></div>
        </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Laadlocatie</label>
            <input type="text" name="laadlocatie" id="laadlocatie_veld" value="{{ vi_laadlocatie }}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
            <div id="afhaallocaties_suggestie" style="margin-top:6px;font-size:11.5px;"></div>
        </div>
        <div id="loslocatie_veld">
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Loslocatie</label>
            <input type="text" name="loslocatie" id="loslocatie_invoer" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
    </div>

    <div id="zeevaart_velden" style="display:none;">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
            <div>
                <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Haven (POD)</label>
                <input type="text" name="haven" value="{{ vi_haven }}" list="pod_havens_lijst" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
                <datalist id="pod_havens_lijst">{% for h in pod_havens %}<option value="{{ h }}">{% endfor %}</datalist>
            </div>
            <div>
                <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Forwarder</label>
                <input type="text" name="forwarder" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
            </div>
        </div>
        <div style="margin-bottom:10px;">
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Vervoerder (rederij, bv. MSC, Cosco)</label>
            <input type="text" name="vervoerder" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
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
    <div id="schip_materiaal_velden" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Materiaal</label>
            <input type="text" name="materiaal" value="{{ vi_materiaal }}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Hoeveelheid (ton)</label>
            <input type="text" name="hoeveelheid" value="{{ vi_hoeveelheid }}" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
    </div>

    <div id="vrachtwagen_truckrijen" style="margin-bottom:10px;">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;display:block;margin-bottom:6px;">Trucks (materiaal, hoeveelheid, kenteken — per truck een rij)</label>
        {% if vi_hoeveelheid %}
        <div id="truck_suggestie" style="font-size:11.5px;color:var(--gray-400);margin-bottom:8px;"></div>
        {% endif %}
        <div id="truckrijen_container"></div>
        <button type="button" onclick="voegTruckrijToe()" style="font-size:12px;padding:6px 12px;border:1px solid var(--gray-200);border-radius:6px;background:#fff;cursor:pointer;color:var(--brand-600);font-weight:600;">+ Truck toevoegen</button>
    </div>

    <div style="margin-bottom:10px;">
        <label style="font-size:12.5px;color:var(--gray-600);">
            <input type="checkbox" id="combi_checkbox" onchange="document.getElementById('combi_veld').style.display=this.checked?'block':'none';" style="margin-right:6px;">
            Combi — dit gaat samen met (een) ander(e) contract(en) in dezelfde truck/container
        </label>
        <div id="combi_veld" style="display:none;margin-top:8px;">
            <input type="text" name="combi_contracten" placeholder="Ander contractnummer (of meerdere, gescheiden door een komma)" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
            <div style="font-size:11px;color:var(--gray-400);margin-top:4px;">Deze contracten worden aan elkaar gekoppeld als 'samen geladen' — handig bij een kleine order die de vrachtwagen/container mee vol maakt.</div>
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
    <div style="margin-bottom:16px;">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Opmerkingen</label>
        <textarea name="opmerkingen" rows="2" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;"></textarea>
    </div>
    <button type="submit" style="padding:9px 20px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">Transport aanmaken</button>
    <a href="/transport-planning" style="margin-left:10px;font-size:12.5px;color:var(--gray-400);text-decoration:none;">Annuleren</a>
</form>

<script>
function wisselTransportmodus() {
    var modus = document.getElementById("transportmodus_select").value;
    var isSchip = (modus === "Schip");
    document.getElementById("zeevaart_velden").style.display = isSchip ? "block" : "none";
    document.getElementById("schip_materiaal_velden").style.display = isSchip ? "grid" : "none";
    document.getElementById("vrachtwagen_truckrijen").style.display = isSchip ? "none" : "block";
    document.getElementById("loslocatie_veld").style.display = isSchip ? "none" : "block";
}
wisselTransportmodus();
var TRUCK_CAPACITEIT = 25;  // ton per vrachtwagen — gebruikt voor het automatisch voorstellen van het aantal trucks/rijen
var truckrijTeller = 0;
function escapeVoorHtmlAttribuut(tekst) {
    return String(tekst).replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
function voegTruckrijToe(materiaalWaarde, hoeveelheidWaarde) {
    truckrijTeller++;
    var i = truckrijTeller;
    var materiaal = materiaalWaarde !== undefined ? materiaalWaarde : (document.querySelector('[name="materiaal_1"]') ? document.querySelector('[name="materiaal_1"]').value : {{ vi_materiaal|tojson }});
    var hoeveelheid = hoeveelheidWaarde !== undefined ? hoeveelheidWaarde : TRUCK_CAPACITEIT;
    var rij = document.createElement("div");
    rij.id = "truckrij_" + i;
    rij.style.cssText = "display:grid;grid-template-columns:1fr 90px 130px 30px;gap:8px;margin-bottom:6px;align-items:center;";
    rij.innerHTML =
        '<input type="text" name="materiaal_' + i + '" value="' + escapeVoorHtmlAttribuut(materiaal) + '" placeholder="Materiaal" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;box-sizing:border-box;font-family:inherit;">' +
        '<input type="text" name="hoeveelheid_' + i + '" value="' + escapeVoorHtmlAttribuut(hoeveelheid) + '" placeholder="Ton" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;box-sizing:border-box;font-family:inherit;">' +
        '<input type="text" name="kenteken_' + i + '" placeholder="Kenteken" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;box-sizing:border-box;text-transform:uppercase;font-family:inherit;">' +
        '<button type="button" style="background:none;border:none;color:var(--gray-300);cursor:pointer;font-size:16px;">×</button>';
    rij.querySelector("button").onclick = function() { rij.remove(); };  // programmatisch ingesteld, geen geneste onclick-string nodig
    document.getElementById("truckrijen_container").appendChild(rij);
}
{% if vi_hoeveelheid %}
(function() {
    var totaal = parseFloat("{{ vi_hoeveelheid }}".replace(",","."));
    if (!totaal || totaal <= 0) { voegTruckrijToe(); return; }
    var aantalTrucks = Math.max(1, Math.ceil(totaal / TRUCK_CAPACITEIT));
    document.getElementById("truck_suggestie").innerHTML =
        totaal + " t totaal ÷ " + TRUCK_CAPACITEIT + " t per truck ≈ <b>" + aantalTrucks + " truck" + (aantalTrucks != 1 ? "s" : "") + "</b> — hieronder alvast ingevuld, pas gerust aan of voeg meer toe.";
    var resterend = totaal;
    for (var i = 0; i < aantalTrucks; i++) {
        var ladingDezeRij = Math.min(TRUCK_CAPACITEIT, Math.round(resterend * 10) / 10);
        voegTruckrijToe({{ vi_materiaal|tojson }}, ladingDezeRij);
        resterend -= ladingDezeRij;
    }
})();
{% else %}
voegTruckrijToe();
{% endif %}
var FABRIEK_STEDEN = {{ fabriek_steden|tojson }};
function vulLoslocatieIn(fabriekNaam) {
    var veld = document.getElementById("loslocatie_invoer");
    if (!fabriekNaam || veld.value.trim()) return;  // niet overschrijven als de gebruiker al iets typte
    var stad = FABRIEK_STEDEN[fabriekNaam];
    if (stad) veld.value = stad;
}
async function zoekAfhaallocaties(leverancierNaam) {
    var doel = document.getElementById("afhaallocaties_suggestie");
    if (!leverancierNaam) { doel.innerHTML = ""; return; }
    doel.innerHTML = '<span style="color:var(--gray-300);">Bekende locaties zoeken...</span>';
    try {
        const res = await fetch("/api/afhaallocaties-leverancier?leverancier=" + encodeURIComponent(leverancierNaam));
        const locaties = await res.json();
        if (!locaties.length) { doel.innerHTML = ""; return; }
        var laadlocatieVeld = document.getElementById("laadlocatie_veld");
        if (locaties.length === 1) {
            // Precies één bekende locatie -> automatisch invullen, blijft aanpasbaar
            laadlocatieVeld.value = (locaties[0].naam || locaties[0].stad) + ", " + locaties[0].adres;
            doel.innerHTML = '<span style="color:var(--gray-400);">Automatisch ingevuld op basis van de bekende afhaallocatie.</span>';
        } else {
            // Meerdere bekende locaties -> keuzeknoppen tonen (programmatisch opgebouwd,
            // geen geneste onclick-string nodig, dus geen quote-escape-risico)
            doel.innerHTML = '';
            var label_span = document.createElement("span");
            label_span.style.color = "var(--gray-500);";
            label_span.textContent = "Meerdere bekende locaties: ";
            doel.appendChild(label_span);
            locaties.forEach(function(loc) {
                var label = (loc.naam || loc.stad) + " (" + loc.adres + ")";
                var knop = document.createElement("button");
                knop.type = "button";
                knop.textContent = label;
                knop.style.cssText = "font-size:11px;padding:3px 8px;margin:2px;border:1px solid var(--gray-200);border-radius:5px;background:#fff;cursor:pointer;";
                knop.onclick = function() { laadlocatieVeld.value = label; };
                doel.appendChild(knop);
            });
        }
    } catch (e) { doel.innerHTML = ""; }
}
if (document.getElementById("leverancier_tp_veld").value) {
    zoekAfhaallocaties(document.getElementById("leverancier_tp_veld").value);
}
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
    return render_template_string(pagina, fabriek_namen=fabriek_namen, vi_leverancier=_vi_leverancier,
                                    vi_materiaal=_vi_materiaal, vi_hoeveelheid=_vi_hoeveelheid,
                                    vi_contract=_vi_contract, vi_fabriek=_vi_fabriek,
                                    vi_haven=_vi_haven, vi_transportmodus=_vi_transportmodus,
                                    vi_laadlocatie=request_laadlocatie_override, pod_havens=laad_pod_havens(),
                                    fabriek_steden=fabriek_steden, leverancier_namen_tp=leverancier_namen_tp)

@transport_planning_bp.route("/transport-planning/<transport_id>/koppel-verkoop", methods=["POST"])
def transport_planning_koppel_verkoop(transport_id):
    """Een schip-transport koppelen aan het verkoopcontract waar de lading
    voor bestemd is — de bestemming van deze inkoop. Leeg gekozen ontkoppelt."""
    _guard = vereist_afdeling_of_403("transport_planning")
    if _guard: return _guard

    transporten = laad_transport_planning()
    transport = next((t for t in transporten if t["id"] == transport_id), None)
    if transport:
        transport["verkoopcontract_referentie"] = request.form.get("verkoopcontract", "").strip()
        bewaar_transport_planning(transporten)
    return redirect(url_for("transport_planning.transport_planning_detail", transport_id=transport_id))

def _verkoopcontract_opties_voor_transport(transport):
    """Alle open (resterend > 0), Definitieve verkoop-Handelsorders — de beste
    materiaal-match voor dit transport bovenaan. Materiaal staat op een
    transport als gecombineerde 'Categorie — Kwaliteit'-string, dus dit is een
    zachte sortering, geen harde filter (anders sluit je te snel iets uit)."""
    _alle_transporten_vc = laad_transport_planning()

    def _gepland_verkoop(contractnummer):
        return round(sum(
            parse_hoeveelheid_getal(t.get("hoeveelheid",""))
            for t in _alle_transporten_vc
            if t.get("contract_referentie") == contractnummer and t.get("status") != "Geannuleerd"
        ), 3)

    opties = []
    for h in laad_handelsorders():
        if h.get("order_type") != "verkoop" or h.get("status") != "Definitief":
            continue
        try:
            totaal = float(str(h.get("hoeveelheid_mt","0")).replace(",",""))
        except (ValueError, TypeError):
            totaal = 0.0
        resterend = round(totaal - _gepland_verkoop(h["contractnummer"]), 1)
        if resterend <= 0:
            continue
        _materiaal_match = bool(transport.get("materiaal")) and h.get("materiaal","") in transport.get("materiaal","")
        opties.append({
            "contractnummer": h["contractnummer"], "tegenpartij_naam": h.get("tegenpartij_naam",""),
            "resterend": resterend, "_match": _materiaal_match,
        })
    opties.sort(key=lambda o: (not o["_match"], o["contractnummer"]))
    return opties

@transport_planning_bp.route("/transport-planning/<transport_id>")
def transport_planning_detail(transport_id):
    _guard = vereist_afdeling_of_403("transport_planning")
    if _guard: return _guard

    transporten = laad_transport_planning()
    transport = next((t for t in transporten if t["id"] == transport_id), None)
    if not transport:
        pagina = render_simple_page("Niet gevonden", "transport_planning", '<div class="page-title">Transport niet gevonden</div><div class="lege-staat">Dit transport bestaat niet (meer). <a href="/transport-planning">Terug naar Transport Planning</a></div>')
        return render_template_string(pagina), 404

    verkoopcontract_opties = []
    verkoopcontract_gekoppeld = None
    if transport.get("transportmodus") == "Schip":
        if transport.get("verkoopcontract_referentie"):
            verkoopcontract_gekoppeld = next((h for h in laad_handelsorders() if h.get("contractnummer") == transport["verkoopcontract_referentie"]), None)
        else:
            verkoopcontract_opties = _verkoopcontract_opties_voor_transport(transport)

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

    {% if transport.combi_gekoppelde_contracten %}
    <div style="background:#fef3c7;color:#b45309;padding:10px 14px;border-radius:8px;margin-bottom:16px;font-size:12.5px;">
        <b>Combi-lading</b> — wordt samen geladen met: {{ transport.combi_gekoppelde_contracten|join(', ') }}
    </div>
    {% endif %}
    <div style="background:var(--gray-50);border-radius:8px;padding:14px 16px;font-size:12.5px;color:var(--gray-600);">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
            <div><b>Transportmodus:</b> {{ transport.transportmodus or 'Vrachtwagen' }}</div>
            <div><b>Laadlocatie:</b> {{ transport.laadlocatie or '—' }}</div>
            {% if transport.transportmodus == "Schip" %}
            <div><b>Haven (POD):</b> {{ transport.haven or '—' }}</div>
            <div><b>Forwarder:</b> {{ transport.forwarder or '—' }}</div>
            <div><b>Vervoerder:</b> {{ transport.vervoerder or '—' }}</div>
            {% else %}
            <div><b>Loslocatie:</b> {{ transport.loslocatie or '—' }}</div>
            {% endif %}
            <div><b>Laaddatum:</b> {{ transport.laaddatum or '—' }} {{ transport.laadtijd }}</div>
            <div><b>Losdatum:</b> {{ transport.losdatum or '—' }} {{ transport.lostijd }}</div>
            <div><b>Materiaal:</b> {{ transport.materiaal or '—' }}</div>
            <div><b>Hoeveelheid:</b> {{ transport.hoeveelheid or '—' }}{% if transport.hoeveelheid %} ton{% endif %}</div>
            <div><b>Transporteur:</b> {{ transport.transporteur or '—' }}</div>
            {% if transport.transportmodus != "Schip" %}
            <div><b>Kenteken:</b> {{ transport.kenteken or '—' }}</div>
            <div><b>Chauffeur:</b> {{ transport.chauffeur or '—' }}</div>
            {% endif %}
            <div><b>Transporttarief:</b> {% if transport.transporttarief %}€{{ transport.transporttarief }}{% else %}—{% endif %}</div>
        </div>
        {% if transport.opmerkingen %}<div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--gray-200);"><b>Opmerkingen:</b> {{ transport.opmerkingen }}</div>{% endif %}
    </div>

    {% if transport.transportmodus == "Schip" %}
    <div style="background:transparent;border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);padding:16px 4px;margin-top:16px;">
        <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Verkoopcontract (bestemming)</div>
        {% if transport.verkoopcontract_referentie %}
        <div style="font-size:13px;color:var(--gray-700);">
            <a href="/handelsorders/{{ verkoopcontract_gekoppeld.id }}" style="font-weight:700;color:var(--brand-600);text-decoration:none;">{{ transport.verkoopcontract_referentie }}</a>
            {% if verkoopcontract_gekoppeld %} — {{ verkoopcontract_gekoppeld.tegenpartij_naam }}{% endif %}
        </div>
        <form method="POST" action="/transport-planning/{{ transport.id }}/koppel-verkoop" style="margin-top:8px;">
            <input type="hidden" name="verkoopcontract" value="">
            <button type="submit" style="font-size:11.5px;color:var(--gray-400);background:none;border:none;cursor:pointer;padding:0;">Ontkoppelen</button>
        </form>
        {% else %}
        <form method="POST" action="/transport-planning/{{ transport.id }}/koppel-verkoop">
            <select name="verkoopcontract" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;margin-bottom:8px;">
                <option value="">— kies een verkoopcontract —</option>
                {% for v in verkoopcontract_opties %}<option value="{{ v.contractnummer }}">{{ v.contractnummer }} — {{ v.tegenpartij_naam }} ({{ v.resterend }}t open)</option>{% endfor %}
            </select>
            <button type="submit" style="padding:7px 14px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:12.5px;font-weight:700;cursor:pointer;">Koppelen</button>
        </form>
        {% if not verkoopcontract_opties %}<div style="font-size:11.5px;color:var(--gray-300);margin-top:6px;">Geen open verkoopcontracten gevonden voor {{ transport.materiaal or 'dit materiaal' }}.</div>{% endif %}
        {% endif %}
    </div>
    {% endif %}
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
    return render_template_string(pagina, transport=transport, statussen=TRANSPORT_PLANNING_STATUSSEN,
                                    verkoopcontract_opties=verkoopcontract_opties, verkoopcontract_gekoppeld=verkoopcontract_gekoppeld)

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

@transport_planning_bp.route("/api/afhaallocaties-leverancier")
def api_afhaallocaties_leverancier():
    """Geeft de opgeslagen afhaallocaties van een leverancier terug — gebruikt
    bij het inplannen om automatisch een laadlocatie voor te stellen (en een
    keuze te bieden als er meerdere zijn), in plaats van steeds handmatig
    hetzelfde adres te moeten intikken."""
    _guard = vereist_afdeling_of_403("transport_planning")
    if _guard: return _guard
    leverancier_naam = request.args.get("leverancier", "").strip()
    if not leverancier_naam:
        return jsonify([])
    return jsonify(leverancier_instelling_voor(leverancier_naam).get("afhaallocaties", []))

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