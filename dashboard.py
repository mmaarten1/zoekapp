"""
dashboard.py — Blueprint voor de Dashboard- en Inzichten-modules.

Bevat: /dashboard (KPI's, ingekocht per maand, sales-pipeline, team-
prestaties, topklanten, "vraagt om aandacht") en /inzichten (landen-/
materiaalverdeling). Gebruikt dagelijkse snapshots voor groeicijfers.

Registratie in app.py met: app.register_blueprint(dashboard_bp)
"""
import json
import datetime
import io
import csv
from flask import Blueprint, session, render_template_string, request, Response

from core import (
    datapad, laad_status, laad_shipments, laad_voorraad, laad_orders,
    laad_accountmanagers, laad_users, laad_notities, laad_marktprijzen,
    laad_transport_data, laad_cert_vervaldatums, _cert_sleutel, laad_meldingen,
    parse_hoeveelheid_getal, bereken_afstand_km, bepaal_shipment_flow_type,
    shipment_hoeveelheid, render_simple_page, ENF_BEDRIJVEN, LANDEN,
    effectieve_afdeling, laad_weegbrug, laad_logistieke_orders, laad_transport_planning,
    laad_containers, vereist_afdeling_of_403, laad_handelsorders, laad_facturen, bepaal_factuur_status,
    laad_layout_voorkeuren,
)

dashboard_bp = Blueprint("dashboard", __name__)

DASHBOARD_WIDGET_LABELS = {
    "inkoop_pipeline": "Ingekocht per maand & Sales pipeline",
    "kwaliteit_team_aandacht": "Inkoop per kwaliteit, Team-prestatie & Vraagt om aandacht",
    "progressie_klanten": "Progressie, Topklanten, Klanten zonder contact & Recent gekoppeld",
    "concept_orders": "Eigen orders die actie nodig hebben",
    "leads_prijzen": "Nieuwe leads, Marktprijzen & Transportkosten",
}

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

def _logistiek_dashboard():
    """Aparte, logistiek-gerichte dashboard-inhoud — geen omzet/marge/klant-KPI's, alleen wat
    voor Logistiek/Weegbrug relevant is. Hergebruikt bestaande databronnen, geen nieuwe."""
    alle_weegrecords = laad_weegbrug()
    alle_orders = laad_logistieke_orders()
    alle_transporten = laad_transport_planning()
    alle_containers = laad_containers()

    _vandaag = datetime.date.today().isoformat()
    kpi_op_locatie = len([r for r in alle_weegrecords if r.get("status") == "Ingewogen"])
    kpi_wacht_afhandeling = len([o for o in alle_orders if o.get("status") in ("Weegbon compleet", "Afhandeling")])
    kpi_wacht_contractkeuze = len([o for o in alle_orders if o.get("status") == "Weegbon compleet" and not o.get("contract_referentie")])
    kpi_klaar_finance = len([o for o in alle_orders if o.get("status") == "Klaar voor Finance"])
    kpi_transport_gepland = len([t for t in alle_transporten if t.get("status") not in ("Te plannen",)])
    kpi_transport_onderweg = len([t for t in alle_transporten if t.get("status") == "Onderweg"])
    _vertraagd_check = lambda t: t.get("laaddatum","") and t["laaddatum"] < _vandaag and t.get("status") in ("Te plannen", "Transport aangevraagd", "Transporteur toegewezen", "Bevestigd")
    kpi_transport_vertraagd = len([t for t in alle_transporten if _vertraagd_check(t)])
    kpi_containers_onderweg = len([c for c in alle_containers if c.get("status") in ("Op zee", "Onderweg", "Transport gepland")])

    recente_weegrecords = sorted(alle_weegrecords, key=lambda r: r.get("aangemaakt",""), reverse=True)[:8]

    inhoud = """
<div class="page-title">Dashboard — Logistiek</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Overzicht specifiek voor Logistiek/Weegbrug — geen omzet- of margecijfers.</p>

<style>
.ld-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:14px; margin-bottom:24px; }
.ld-kaart { background:transparent; border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); padding:16px 4px; }
.ld-getal { font-size:1.7rem; font-weight:800; color:var(--brand-700); }
.ld-label { font-size:0.72rem; color:var(--gray-400); text-transform:uppercase; letter-spacing:0.8px; margin-top:4px; font-weight:600; }
.ld-tabel-kop { display:flex; align-items:center; padding:10px 16px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); font-size:10px; letter-spacing:0.08em; text-transform:uppercase; color:#7d8792; }
.ld-tabel-rij { display:flex; align-items:center; padding:9px 16px; border-bottom:1px solid var(--gray-100); font-size:12.5px; }
</style>

<div class="ld-grid">
    <div class="ld-kaart"><div class="ld-getal">{{ kpi_op_locatie }}</div><div class="ld-label">Nu op locatie (weegbrug)</div></div>
    <div class="ld-kaart"><div class="ld-getal">{{ kpi_wacht_afhandeling }}</div><div class="ld-label">Wacht op afhandeling</div></div>
    <div class="ld-kaart" style="{% if kpi_wacht_contractkeuze %}border-color:#fecaca;{% endif %}"><div class="ld-getal" style="{% if kpi_wacht_contractkeuze %}color:#dc2626;{% endif %}">{{ kpi_wacht_contractkeuze }}</div><div class="ld-label">Wacht op contractkeuze</div></div>
    <div class="ld-kaart"><div class="ld-getal">{{ kpi_klaar_finance }}</div><div class="ld-label">Klaar voor Finance</div></div>
    <div class="ld-kaart"><div class="ld-getal">{{ kpi_transport_onderweg }}</div><div class="ld-label">Transporten onderweg</div></div>
    <div class="ld-kaart" style="{% if kpi_transport_vertraagd %}border-color:#fecaca;{% endif %}"><div class="ld-getal" style="{% if kpi_transport_vertraagd %}color:#dc2626;{% endif %}">{{ kpi_transport_vertraagd }}</div><div class="ld-label">Transporten vertraagd</div></div>
    <div class="ld-kaart"><div class="ld-getal">{{ kpi_containers_onderweg }}</div><div class="ld-label">Containers onderweg</div></div>
</div>

<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:24px;">
    <a href="/live-operations" style="font-size:12.5px;font-weight:600;color:var(--brand-600);text-decoration:none;border:1px solid var(--gray-200);padding:7px 14px;border-radius:6px;">Live Operations →</a>
    <a href="/logistiek/afhandeling" style="font-size:12.5px;font-weight:600;color:var(--brand-600);text-decoration:none;border:1px solid var(--gray-200);padding:7px 14px;border-radius:6px;">Afhandeling →</a>
    <a href="/transport-overview" style="font-size:12.5px;font-weight:600;color:var(--brand-600);text-decoration:none;border:1px solid var(--gray-200);padding:7px 14px;border-radius:6px;">Transport Overview →</a>
</div>

{% if recente_weegrecords %}
<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Recente weegrecords</div>
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);">
    <div class="ld-tabel-kop">
        <span style="width:110px;">Weegnummer</span>
        <span style="width:100px;">Kenteken</span>
        <span style="flex:1;">Leverancier</span>
        <span style="width:160px;">Status</span>
    </div>
    {% for r in recente_weegrecords %}
    <div class="ld-tabel-rij">
        <span style="width:110px;font-family:var(--font-mono);color:var(--gray-500);">{{ r.weegnummer }}</span>
        <span style="width:100px;font-weight:600;color:var(--gray-800);">{{ r.kenteken }}</span>
        <span style="flex:1;color:var(--gray-600);">{{ r.leverancier or '—' }}</span>
        <span style="width:160px;color:var(--gray-600);font-size:11.5px;">{{ r.status }}</span>
    </div>
    {% endfor %}
</div>
{% endif %}
    """
    pagina = render_simple_page("Dashboard", "dashboard", inhoud)
    return render_template_string(pagina, kpi_op_locatie=kpi_op_locatie, kpi_wacht_afhandeling=kpi_wacht_afhandeling,
                                    kpi_wacht_contractkeuze=kpi_wacht_contractkeuze,
                                    kpi_klaar_finance=kpi_klaar_finance, kpi_transport_gepland=kpi_transport_gepland,
                                    kpi_transport_onderweg=kpi_transport_onderweg, kpi_transport_vertraagd=kpi_transport_vertraagd,
                                    kpi_containers_onderweg=kpi_containers_onderweg, recente_weegrecords=recente_weegrecords)

def _backoffice_finance_dashboard():
    """Eenvoudig, apart dashboard voor Backoffice/Finance — bewust klein gehouden en
    alleen met echt beschikbare data; wordt later verder ingevuld. Zonder deze
    aparte functie vielen deze afdelingen terug op het commerciële dashboard
    (persoonlijk per accountmanager), wat voor hen altijd leeg/nul zou zijn."""
    huidige_gebruiker = session.get("gebruikersnaam", "")
    _huidig_uur = datetime.datetime.now().hour
    if _huidig_uur < 12:
        groet_woord = "Goedemorgen"
    elif _huidig_uur < 18:
        groet_woord = "Goedemiddag"
    else:
        groet_woord = "Goedenavond"

    alle_facturen = laad_facturen()
    for _f in alle_facturen:
        _f["status"] = bepaal_factuur_status(_f)
    openstaande_facturen = [f for f in alle_facturen if f.get("status") != "Betaald"]
    te_laat_facturen = [f for f in alle_facturen if f.get("status") == "Te laat"]

    def _bedrag_getal(f):
        try:
            return float(str(f.get("bedrag", "0")).replace(",", "."))
        except (ValueError, TypeError):
            return 0.0
    totaal_openstaand = sum(_bedrag_getal(f) for f in openstaande_facturen)

    alle_logistieke_orders_bf = laad_logistieke_orders()
    klaar_voor_finance = [o for o in alle_logistieke_orders_bf if o.get("status") == "Klaar voor Finance"]
    wacht_op_afhandeling = [o for o in alle_logistieke_orders_bf if o.get("status") in ("Weegbon compleet", "Afhandeling")]

    _vandaag_bf = datetime.date.today()
    _vervaldatums_bf = laad_cert_vervaldatums()
    aantal_cert_verlopen_bf = 0
    for b in ENF_BEDRIJVEN:
        for c in [x.strip() for x in b.get("certificeringen", "").split(",") if x.strip()]:
            geldig_tot = _vervaldatums_bf.get(_cert_sleutel(b["naam"], c), "")
            if geldig_tot:
                try:
                    if datetime.datetime.strptime(geldig_tot, "%Y-%m-%d").date() < _vandaag_bf:
                        aantal_cert_verlopen_bf += 1
                except (ValueError, TypeError):
                    pass

    recent_gekoppeld_bf = sorted(
        [o for o in alle_logistieke_orders_bf if o.get("contract_referentie")],
        key=lambda o: o.get("aangemaakt",""), reverse=True
    )[:6]

    inhoud = """
<div class="page-title">{{ groet_woord }}, {{ gebruikersnaam or "daar" }}</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Overzicht voor Backoffice/Finance.</p>

<style>
.bf-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:14px; margin-bottom:24px; }
.bf-kaart { background:transparent; border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); padding:16px 4px; }
.bf-getal { font-size:1.6rem; font-weight:800; color:var(--gray-800); }
.bf-label { font-size:0.72rem; color:var(--gray-400); text-transform:uppercase; letter-spacing:0.6px; margin-top:4px; font-weight:600; }
.bf-tabel-rij { display:flex; align-items:center; padding:9px 4px; border-bottom:1px solid var(--gray-100); font-size:12.5px; text-decoration:none; color:inherit; }
</style>

<div class="bf-grid">
    <div class="bf-kaart"><div class="bf-getal">{{ openstaande_facturen|length }}</div><div class="bf-label">Openstaande facturen</div></div>
    <div class="bf-kaart" style="{% if te_laat_facturen %}border-color:#fecaca;{% endif %}"><div class="bf-getal" style="{% if te_laat_facturen %}color:#dc2626;{% endif %}">{{ te_laat_facturen|length }}</div><div class="bf-label">Te laat</div></div>
    <div class="bf-kaart"><div class="bf-getal">€{{ "{:,.0f}".format(totaal_openstaand).replace(",", ".") }}</div><div class="bf-label">Totaal openstaand</div></div>
    <div class="bf-kaart"><div class="bf-getal">{{ klaar_voor_finance|length }}</div><div class="bf-label">Klaar voor Finance</div></div>
    <div class="bf-kaart"><div class="bf-getal">{{ wacht_op_afhandeling|length }}</div><div class="bf-label">Wacht op afhandeling</div></div>
    <div class="bf-kaart"><div class="bf-getal">{{ aantal_cert_verlopen_bf }}</div><div class="bf-label">Certificeringen verlopen</div></div>
</div>

<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:24px;">
    <a href="/facturen" style="font-size:12.5px;font-weight:600;color:var(--brand-600);text-decoration:none;border:1px solid var(--gray-200);padding:7px 14px;border-radius:6px;">Facturen →</a>
    <a href="/logistiek/afhandeling" style="font-size:12.5px;font-weight:600;color:var(--brand-600);text-decoration:none;border:1px solid var(--gray-200);padding:7px 14px;border-radius:6px;">Afhandeling →</a>
    <a href="/certificeringen" style="font-size:12.5px;font-weight:600;color:var(--brand-600);text-decoration:none;border:1px solid var(--gray-200);padding:7px 14px;border-radius:6px;">Certificeringen →</a>
</div>

<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Recent gekoppeld aan contract</div>
{% if recent_gekoppeld_bf %}
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);">
    {% for o in recent_gekoppeld_bf %}
    <a href="/logistiek/orders/{{ o.id }}" class="bf-tabel-rij">
        <span style="flex:1;font-weight:600;color:var(--gray-800);">{{ o.leverancier }}</span>
        <span style="flex:1;color:var(--gray-500);">{{ o.contract_referentie }} — {{ o.materiaal }}</span>
        <span style="width:90px;text-align:right;color:var(--gray-600);">{{ o.werkelijke_hoeveelheid or '—' }}{% if o.werkelijke_hoeveelheid %} t{% endif %}</span>
    </a>
    {% endfor %}
</div>
{% else %}
<div class="lege-staat">Nog geen leveringen aan een contract gekoppeld.</div>
{% endif %}
    """
    pagina = render_simple_page("Dashboard", "dashboard", inhoud)
    return render_template_string(pagina, groet_woord=groet_woord, gebruikersnaam=huidige_gebruiker,
                                    openstaande_facturen=openstaande_facturen, te_laat_facturen=te_laat_facturen,
                                    totaal_openstaand=totaal_openstaand, klaar_voor_finance=klaar_voor_finance,
                                    wacht_op_afhandeling=wacht_op_afhandeling, aantal_cert_verlopen_bf=aantal_cert_verlopen_bf,
                                    recent_gekoppeld_bf=recent_gekoppeld_bf)

@dashboard_bp.route("/dashboard")
def dashboard():
    if effectieve_afdeling() in ("logistiek", "weegbrug"):
        return _logistiek_dashboard()
    if effectieve_afdeling() in ("backoffice", "finance"):
        return _backoffice_finance_dashboard()

    huidige_gebruiker = session.get("gebruikersnaam", "")
    _huidig_uur = datetime.datetime.now().hour
    if _huidig_uur < 12:
        groet_woord = "Goedemorgen"
    elif _huidig_uur < 18:
        groet_woord = "Goedemiddag"
    else:
        groet_woord = "Goedenavond"

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

    # ---------- Alles hieronder gepersonaliseerd naar de ingelogde accountmanager ----------
    accountmanagers_alle_dash = laad_accountmanagers()
    mijn_bedrijven_lijst = [b for b in ENF_BEDRIJVEN if accountmanagers_alle_dash.get(b["naam"]) == huidige_gebruiker]
    alle_handelsorders_dash = laad_handelsorders()

    def _handelsorder_datum(h):
        try:
            return datetime.datetime.strptime(h.get("aangemaakt",""), "%d-%m-%Y %H:%M").date()
        except (ValueError, TypeError):
            return None

    def _marge_getal(h):
        try:
            return float(str(h.get("berekende_marge","0")).replace(",","."))
        except (ValueError, TypeError):
            return 0.0

    mijn_inkoop_definitief = [h for h in alle_handelsorders_dash if h.get("order_type")=="inkoop" and h.get("status")=="Definitief" and h.get("aangemaakt_door")==huidige_gebruiker]
    mijn_verkoop_definitief = [h for h in alle_handelsorders_dash if h.get("order_type")=="verkoop" and h.get("status")=="Definitief" and h.get("aangemaakt_door")==huidige_gebruiker]
    mijn_concept_orders = [h for h in alle_handelsorders_dash if h.get("status")=="Concept" and h.get("aangemaakt_door")==huidige_gebruiker]

    # KPI: eigen klanten (was: 'Bedrijven in database', bedrijfsbreed)
    eigen_klanten_aantal = sum(1 for b in mijn_bedrijven_lijst if status_alle.get(b["naam"]) == "klant")

    # KPI: gedekt volume -> persoonlijk ingekocht volume deze maand
    _deze_maand_sleutel_kpi = (datetime.date.today().year, datetime.date.today().month)
    gedekt_volume_maand = sum(
        parse_hoeveelheid_getal(h.get("hoeveelheid_mt",""))
        for h in mijn_inkoop_definitief
        if _handelsorder_datum(h) and (_handelsorder_datum(h).year, _handelsorder_datum(h).month) == _deze_maand_sleutel_kpi
    )

    # KPI: actieve leads -> eigen leads (potentie/in_proces), gekoppeld als accountmanager
    eigen_actieve_leads = sum(1 for b in mijn_bedrijven_lijst if status_alle.get(b["naam"]) in ("potentie", "in_proces"))

    # KPI: geplande orders -> eigen openstaande (Concept) handelsorders
    geplande_orders_aantal = len(mijn_concept_orders)

    # KPI: omzet (gewonnen) -> som van eigen marges uit inkoop, dit jaar
    _dit_jaar_kpi = datetime.date.today().year
    mijn_inkoop_dit_jaar = [h for h in mijn_inkoop_definitief if _handelsorder_datum(h) and _handelsorder_datum(h).year == _dit_jaar_kpi]
    omzet_totaal = sum(_marge_getal(h) for h in mijn_inkoop_dit_jaar if h.get("berekende_marge"))

    # KPI: ton verkocht -> alles wat je zelf hebt verkocht
    ton_verkocht_totaal = sum(parse_hoeveelheid_getal(h.get("hoeveelheid_mt","")) for h in mijn_verkoop_definitief)

    # KPI: verwachte omzet -> hernoemd naar gemiddelde marge per ton (dit jaar, eigen inkoop)
    mijn_inkoop_met_marge = [h for h in mijn_inkoop_dit_jaar if h.get("berekende_marge") and h.get("hoeveelheid_mt")]
    _totaal_marge_gem = sum(_marge_getal(h) for h in mijn_inkoop_met_marge)
    _totaal_ton_gem = sum(parse_hoeveelheid_getal(h.get("hoeveelheid_mt","")) for h in mijn_inkoop_met_marge)
    gemiddelde_marge_per_ton = round(_totaal_marge_gem / _totaal_ton_gem, 2) if _totaal_ton_gem > 0 else 0

    # KPI: lopende orders -> hernoemd naar openstaande (te laat) facturen van eigen klanten
    alle_facturen_dash = laad_facturen()
    for _f in alle_facturen_dash:
        _f["status"] = bepaal_factuur_status(_f)
    lopende_orders_aantal = len([f for f in alle_facturen_dash if f.get("status")=="Te laat" and accountmanagers_alle_dash.get(f.get("bedrijf",""))==huidige_gebruiker])

    # ---------- Ingekocht per maand (persoonlijk, uit eigen Handelsorders) ----------
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
    for h in mijn_inkoop_definitief:
        _d = _handelsorder_datum(h)
        if not _d:
            continue
        sleutel = (_d.year, _d.month)
        if sleutel in inkoop_per_maand:
            inkoop_per_maand[sleutel] += parse_hoeveelheid_getal(h.get("hoeveelheid_mt",""))
    inkoop_serie = [inkoop_per_maand[s] for s in maand_sleutels]
    max_inkoop_maand = max(inkoop_serie) if any(inkoop_serie) else 1

    # ---------- Inkoop per kwaliteit (persoonlijk, uit eigen Handelsorders) ----------
    inkoop_per_kwaliteit = {}
    for h in mijn_inkoop_definitief:
        naam = f"{h.get('materiaal','')} — {h.get('kwaliteit','')}" if h.get("kwaliteit") else h.get("materiaal","")
        if not naam:
            continue
        inkoop_per_kwaliteit[naam] = inkoop_per_kwaliteit.get(naam, 0.0) + parse_hoeveelheid_getal(h.get("hoeveelheid_mt",""))
    inkoop_kwaliteit_lijst = sorted(inkoop_per_kwaliteit.items(), key=lambda x: -x[1])[:8]
    max_inkoop_kwaliteit = max([a for _, a in inkoop_kwaliteit_lijst], default=1) or 1

    # ---------- Orders (oude, eenvoudige orders.json — nog gebruikt door Team-prestatie hieronder) ----------
    orders_alle_dash = laad_orders()
    _vandaag_dash = datetime.date.today()

    def _prijs_getal(o):
        try:
            return float(str(o.get("prijs", "")).replace(",", "").replace("€", "").strip())
        except (ValueError, TypeError):
            return 0.0

    # ---------- Sales pipeline -> per bedrijfseenheid (team), dan per persoon: ingekochte hoeveelheid ----------
    _pipeline_per_team = {}
    for h in alle_handelsorders_dash:
        if h.get("order_type") != "inkoop" or h.get("status") != "Definitief":
            continue
        _team = h.get("bedrijfseenheid","") or "Niet ingedeeld"
        _persoon = h.get("aangemaakt_door","") or "Onbekend"
        _hoeveelheid = parse_hoeveelheid_getal(h.get("hoeveelheid_mt",""))
        _pipeline_per_team.setdefault(_team, {})
        _pipeline_per_team[_team][_persoon] = _pipeline_per_team[_team].get(_persoon, 0.0) + _hoeveelheid
    pipeline_tellingen = []
    for _team, _personen in _pipeline_per_team.items():
        _personen_lijst = sorted([{"naam": p, "hoeveelheid": round(h,1)} for p, h in _personen.items()], key=lambda x: -x["hoeveelheid"])
        pipeline_tellingen.append({"team": _team, "personen": _personen_lijst, "totaal": round(sum(_personen.values()),1)})
    pipeline_tellingen.sort(key=lambda t: -t["totaal"])
    max_pipeline = max([t["totaal"] for t in pipeline_tellingen], default=1) or 1

    # ---------- Team-prestatie (echte data) ----------
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

    # ---------- Progressie met bedrijven (status-funnel, gepersonaliseerd) ----------
    progressie_funnel = [
        {"label": "Nieuwe leads", "aantal": sum(1 for b in mijn_bedrijven_lijst if not status_alle.get(b["naam"]))},
        {"label": "Potentie", "aantal": sum(1 for b in mijn_bedrijven_lijst if status_alle.get(b["naam"]) == "potentie")},
        {"label": "In proces", "aantal": sum(1 for b in mijn_bedrijven_lijst if status_alle.get(b["naam"]) == "in_proces")},
        {"label": "Klant", "aantal": eigen_klanten_aantal},
    ]
    max_funnel = max([f["aantal"] for f in progressie_funnel], default=1) or 1

    # ---------- Topklanten & klanten zonder recent contact (gepersonaliseerd) ----------
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

    klanten_dash = [b for b in mijn_bedrijven_lijst if status_alle.get(b["naam"]) == "klant"]
    topklanten = sorted(klanten_dash, key=lambda b: -parse_hoeveelheid_getal(b.get("volume", "")))[:5]
    klanten_zonder_contact = []
    for b in klanten_dash:
        dagen = _laatste_contact_dagen(b["naam"])
        if dagen is None or dagen > 30:
            klanten_zonder_contact.append({"naam": b["naam"], "dagen": dagen})
    klanten_zonder_contact.sort(key=lambda x: (x["dagen"] is not None, -(x["dagen"] or 0)))
    klanten_zonder_contact = klanten_zonder_contact[:5]

    nieuwe_leads_lijst = sorted(
        [b for b in mijn_bedrijven_lijst if not status_alle.get(b["naam"])],
        key=lambda b: -parse_hoeveelheid_getal(b.get("volume", ""))
    )[:5]

    # ---------- Marktprijzen & transportkosten (echte data, samengevat) ----------
    marktprijzen_alle = laad_marktprijzen()
    marktprijzen_recent = sorted(marktprijzen_alle, key=lambda p: p.get("datum", ""), reverse=True)[:5]

    transport_data_dash = laad_transport_data()
    aantal_forwarders = len(transport_data_dash)
    aantal_transport_steden = sum(len(v) for v in transport_data_dash.values())

    # ---------- Vraagt om aandacht (grotendeels gepersonaliseerd; 'leads zonder
    # accountmanager' blijft bewust bedrijfsbreed, want die hebben per definitie
    # nog geen eigenaar) ----------
    leads_zonder_am_dash = [b for b in ENF_BEDRIJVEN if not accountmanagers_alle_dash.get(b["naam"])]
    leads_zonder_am_groot = sum(1 for b in leads_zonder_am_dash if parse_hoeveelheid_getal(b.get("volume", "")) > 10000)
    bedrijven_zonder_kwaliteiten = sum(1 for b in mijn_bedrijven_lijst if b.get("materialen") and not b.get("kwaliteiten"))

    _vervaldatums_dash = laad_cert_vervaldatums()
    aantal_cert_verlopen = 0
    for b in mijn_bedrijven_lijst:
        for c in [x.strip() for x in b.get("certificeringen", "").split(",") if x.strip()]:
            geldig_tot = _vervaldatums_dash.get(_cert_sleutel(b["naam"], c), "")
            if geldig_tot:
                try:
                    if datetime.datetime.strptime(geldig_tot, "%Y-%m-%d").date() < _vandaag_dash:
                        aantal_cert_verlopen += 1
                except (ValueError, TypeError):
                    pass

    # Orders over datum -> eigen Concept-handelsorders waarvan de einddatum al voorbij is
    orders_verlopen = 0
    for h in mijn_concept_orders:
        if h.get("einddatum"):
            try:
                if datetime.datetime.strptime(h["einddatum"], "%Y-%m-%d").date() < _vandaag_dash:
                    orders_verlopen += 1
            except (ValueError, TypeError):
                pass

    aandacht_items = []
    if leads_zonder_am_dash:
        sub = f"waarvan {leads_zonder_am_groot} boven 10.000 t/j" if leads_zonder_am_groot else ""
        aandacht_items.append({"titel": f"{len(leads_zonder_am_dash)} leads zonder accountmanager", "sub": sub, "url": "/?accountmanager="})
    if bedrijven_zonder_kwaliteiten:
        aandacht_items.append({"titel": f"{bedrijven_zonder_kwaliteiten} eigen bedrijven zonder kwaliteiten", "sub": "blokkeert matching met fabrieken", "url": "/"})
    if aantal_cert_verlopen:
        aandacht_items.append({"titel": f"{aantal_cert_verlopen} certificeringen verlopen (eigen bedrijven)", "sub": "controle nodig", "url": "/certificeringen"})
    if orders_verlopen:
        aandacht_items.append({"titel": f"{orders_verlopen} eigen orders over de einddatum", "sub": "nog niet definitief gemaakt", "url": "/handelsorders"})

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

    DASHBOARD_WIDGETS = {
        "inkoop_pipeline": '''
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
        <div class="db-sectie-titel">Sales pipeline <small>ingekocht per team, per persoon</small></div>
        {% for t in pipeline_tellingen %}
        <div style="margin-bottom:10px;">
            <div style="font-size:11.5px;font-weight:700;color:var(--gray-700);margin-bottom:3px;">{{ t.team }} — {{ t.totaal }} t</div>
            {% for p in t.personen %}
            <div class="db-hbar-rij" style="margin-left:8px;">
                <span class="db-hbar-naam" style="font-size:11px;">{{ p.naam }}</span>
                <span class="db-hbar-track"><span class="db-hbar-fill" style="width:{{ (p.hoeveelheid/max_pipeline*100)|round(1) }}%;"></span></span>
                <span class="db-hbar-getal">{{ p.hoeveelheid }} t</span>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="db-leeg">Nog geen ingekochte, definitieve orders.</div>
        {% endfor %}
    </div>
</div>
''',
        "kwaliteit_team_aandacht": '''
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
''',
        "progressie_klanten": '''
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
    <div class="db-kol">
        <div class="db-sectie-titel">Recent gekoppeld aan contract</div>
        {% for o in recent_gekoppelde_contracten %}
        <a class="db-lijst-item" href="/logistiek/orders/{{ o.id }}">
            <span><span class="db-lijst-naam">{{ o.leverancier }}</span><br><span class="db-lijst-sub">{{ o.contract_referentie }} — {{ o.materiaal }}</span></span>
            <span class="db-lijst-getal">{{ o.werkelijke_hoeveelheid or '—' }}{% if o.werkelijke_hoeveelheid %} t{% endif %}</span>
        </a>
        {% else %}
        <div class="db-leeg">Nog geen leveringen aan een contract gekoppeld.</div>
        {% endfor %}
    </div>
</div>
''',
        "concept_orders": '''
<div class="db-rij">
    <div class="db-kol">
        <div class="db-sectie-titel">Eigen orders die actie nodig hebben <small>nog concept</small></div>
        {% for h in mijn_concept_orders %}
        <a class="db-lijst-item" href="/handelsorders/{{ h.id }}">
            <span><span class="db-lijst-naam">{{ h.tegenpartij_naam }}</span><br><span class="db-lijst-sub">{{ h.contractnummer }} — {{ "Inkoop" if h.order_type == "inkoop" else "Verkoop" }}</span></span>
            <span class="db-lijst-getal">{{ h.hoeveelheid_mt or '—' }}{% if h.hoeveelheid_mt %} t{% endif %}</span>
        </a>
        {% else %}
        <div class="db-leeg">Geen openstaande concept-orders.</div>
        {% endfor %}
    </div>
</div>
''',
        "leads_prijzen": '''
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
''',
    }
    _widget_voorkeur = laad_layout_voorkeuren().get(session.get("gebruikersnaam",""), {})
    _widget_volgorde = _widget_voorkeur.get("dashboard_widget_volgorde", [])
    _widget_verborgen = set(_widget_voorkeur.get("dashboard_widget_verborgen", []))
    _widget_sleutels = list(DASHBOARD_WIDGETS.keys())
    if _widget_volgorde:
        _volgorde_index = {s: i for i, s in enumerate(_widget_volgorde)}
        _widget_sleutels = sorted(_widget_sleutels, key=lambda s: _volgorde_index.get(s, len(_widget_volgorde)))
    widgets_html = "".join(DASHBOARD_WIDGETS[s] for s in _widget_sleutels if s not in _widget_verborgen)

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
        <div class="db-groet">{{ groet_woord }}, {{ gebruikersnaam_dash or "daar" }}</div>
        <div class="db-substaat">Stand van zaken, week {{ huidige_week }} · bijgewerkt vanochtend {{ bijgewerkt_tijd }}</div>
    </div>
    <div class="db-acties">
        <a href="/dashboard" class="db-btn">Deze maand</a>
        <a href="/export-csv" class="db-btn db-btn-primair">Rapport delen</a>
    </div>
</div>

<div class="db-kpi-rij">
    <div class="db-kpi">
        <div class="db-kpi-label">Eigen klanten</div>
        <div class="db-kpi-getal">{{ "{:,}".format(eigen_klanten_aantal).replace(",", ".") }}</div>
        <div class="db-kpi-sub">gekoppeld als accountmanager</div>
    </div>
    <div class="db-kpi">
        <div class="db-kpi-label">Gedekt volume</div>
        <div class="db-kpi-getal">{{ volume_totaal_label }}</div>
        <div class="db-kpi-sub">persoonlijk ingekocht deze maand</div>
    </div>
    <div class="db-kpi">
        <div class="db-kpi-label">Actieve leads</div>
        <div class="db-kpi-getal">{{ eigen_actieve_leads }}</div>
        <div class="db-kpi-sub">eigen leads, gekoppeld als accountmanager</div>
    </div>
    <div class="db-kpi">
        <div class="db-kpi-label">Geplande orders</div>
        <div class="db-kpi-getal">{{ geplande_orders_aantal }}</div>
        <div class="db-kpi-sub">eigen orders, nog concept</div>
    </div>
</div>
<div class="db-kpi-rij">
    <div class="db-kpi">
        <div class="db-kpi-label">Omzet (marge, dit jaar)</div>
        <div class="db-kpi-getal">€{{ "{:,.0f}".format(omzet_totaal).replace(",", ".") }}</div>
        <div class="db-kpi-sub">eigen marge uit inkoop</div>
    </div>
    <div class="db-kpi">
        <div class="db-kpi-label">Ton verkocht</div>
        <div class="db-kpi-getal">{{ "{:,.0f}".format(ton_verkocht_totaal).replace(",", ".") }}</div>
        <div class="db-kpi-sub">eigen, definitieve verkooporders</div>
    </div>
    <div class="db-kpi">
        <div class="db-kpi-label">Gem. marge per ton</div>
        <div class="db-kpi-getal">€{{ "{:,.2f}".format(gemiddelde_marge_per_ton).replace(",", ".") }}</div>
        <div class="db-kpi-sub">gemiddeld dit jaar, eigen inkoop</div>
    </div>
    <div class="db-kpi">
        <div class="db-kpi-label">Openstaande facturen</div>
        <div class="db-kpi-getal">{{ lopende_orders_aantal }}</div>
        <div class="db-kpi-sub">te laat, bij eigen klanten</div>
    </div>
</div>

WIDGETS_HIER

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
    inhoud = inhoud.replace("WIDGETS_HIER", widgets_html)
    pagina = render_simple_page("Dashboard", "dashboard", inhoud)

    if gedekt_volume_maand >= 1_000_000:
        volume_totaal_label = f"{gedekt_volume_maand/1_000_000:.1f} Mt".replace(".", ",")
    elif gedekt_volume_maand >= 1000:
        volume_totaal_label = f"{gedekt_volume_maand/1000:.1f}k t".replace(".", ",")
    else:
        volume_totaal_label = f"{gedekt_volume_maand:.0f} t"

    # --- Recent gekoppelde contracten: laatste logistieke orders die aan een
    # inkoopcontract gekoppeld zijn (via Live Operaties/Weegbrug) — noodzakelijk om
    # vanuit het commerciële Dashboard te kunnen zien wat er al binnengekomen is. ---
    recent_gekoppelde_contracten = sorted(
        [o for o in laad_logistieke_orders() if o.get("contract_referentie")],
        key=lambda o: o.get("aangemaakt",""), reverse=True
    )[:6]

    return render_template_string(pagina,
        gebruikersnaam_dash=gebruikersnaam_dash, groet_woord=groet_woord,
        huidige_week=_vandaag_dash.isocalendar()[1],
        bijgewerkt_tijd=datetime.datetime.now().strftime("%H:%M"),
        totaal=len(ENF_BEDRIJVEN), groei_pct=groei_pct, groei_periode=groei_periode,
        volume_totaal_label=volume_totaal_label, eigen_klanten_aantal=eigen_klanten_aantal,
        eigen_actieve_leads=eigen_actieve_leads, leads_zonder_am_dash=leads_zonder_am_dash,
        geplande_orders_aantal=geplande_orders_aantal,
        omzet_totaal=omzet_totaal, ton_verkocht_totaal=ton_verkocht_totaal,
        gemiddelde_marge_per_ton=gemiddelde_marge_per_ton, lopende_orders_aantal=lopende_orders_aantal,
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
        activiteit=activiteit, recent_gekoppelde_contracten=recent_gekoppelde_contracten,
        mijn_concept_orders=mijn_concept_orders)

def _bereken_contractvoortgang_inzichten(gekozen_materiaal, gekozen_land):
    """Herbruikbaar voor zowel de Commerciële Inzichten-pagina als de CSV-export
    ervan — zodat beide altijd exact dezelfde cijfers tonen. Gebaseerd op
    Handelsorders (de actuele, actieve databron), niet het oude orders.json."""
    _bedrijf_land_lookup = {b["naam"]: b.get("land","") for b in ENF_BEDRIJVEN}

    def _geleverd_op_contract(contractnummer):
        return round(sum(
            parse_hoeveelheid_getal(o.get("werkelijke_hoeveelheid",""))
            for o in laad_logistieke_orders()
            if o.get("contract_referentie") == contractnummer and o.get("status") in ("Weegbon compleet", "Afhandeling", "Klaar voor Finance", "Gefactureerd", "Afgerond")
        ), 3)

    contractvoortgang_lijst = []
    for h in laad_handelsorders():
        if h.get("order_type") == "inkoop" and h.get("materiaal","") == gekozen_materiaal and h.get("status") == "Definitief" and _bedrijf_land_lookup.get(h.get("tegenpartij_naam",""), "") == gekozen_land:
            try:
                totaal = float(str(h.get("hoeveelheid_mt","0")).replace(",",""))
            except (ValueError, TypeError):
                totaal = 0.0
            geleverd = _geleverd_op_contract(h["contractnummer"])
            contractvoortgang_lijst.append({
                "contractnummer": h["contractnummer"], "leverancier": h.get("tegenpartij_naam",""), "kwaliteit": h.get("kwaliteit",""),
                "totaal": round(totaal,1), "geleverd": geleverd, "resterend": round(totaal-geleverd,1),
            })
    contractvoortgang_lijst.sort(key=lambda c: -c["resterend"])
    return contractvoortgang_lijst

@dashboard_bp.route("/inzichten/export/contractvoortgang")
def export_contractvoortgang_csv():
    """CSV-export van de Contractvoortgang-tabel op Commerciële Inzichten —
    exact dezelfde cijfers als op het scherm, want dezelfde berekeningsfunctie."""
    _guard = vereist_afdeling_of_403("inzichten")
    if _guard: return _guard

    gekozen_materiaal = request.args.get("materiaal", "")
    gekozen_land = request.args.get("land", "")
    contractvoortgang_lijst = _bereken_contractvoortgang_inzichten(gekozen_materiaal, gekozen_land)

    output = io.StringIO()
    schrijver = csv.writer(output, delimiter=";")
    schrijver.writerow(["Contractnummer", "Leverancier", "Kwaliteit", "Totaal (MT)", "Geleverd (MT)", "Resterend (MT)"])
    for c in contractvoortgang_lijst:
        schrijver.writerow([c["contractnummer"], c["leverancier"], c["kwaliteit"], c["totaal"], c["geleverd"], c["resterend"]])

    return Response(output.getvalue(), mimetype="text/csv",
                     headers={"Content-Disposition": f"attachment; filename=contractvoortgang_{gekozen_materiaal}_{gekozen_land}.csv"})

@dashboard_bp.route("/inzichten")
def inzichten():
    """Commerciële Inzichten: rapportages op materiaal+land, alleen met echt
    berekenbare data. Marge-onderdelen zijn bewust weggelaten — daarvoor
    ontbreekt een gekoppelde inkoopprijs (zie afspraak met gebruiker)."""
    _guard = vereist_afdeling_of_403("inzichten")
    if _guard: return _guard

    LANDEN_KEUZE = ["United Kingdom", "Spain", "France", "Germany", "Netherlands"]
    LAND_LABELS = {"United Kingdom": "UK", "Spain": "Spanje", "France": "Frankrijk", "Germany": "Duitsland", "Netherlands": "Nederland"}

    alle_orders = laad_orders()
    materiaal_opties = sorted({o.get("materiaal","").strip() for o in alle_orders if o.get("materiaal","").strip()})
    gekozen_materiaal = request.args.get("materiaal", "")
    gekozen_land = request.args.get("land", "")

    resultaat_html = ""
    if gekozen_materiaal and gekozen_land:
        _bedrijf_land_lookup = {b["naam"]: b.get("land","") for b in ENF_BEDRIJVEN}

        def _order_getal(o):
            try:
                return float(str(o.get("prijs","0")).replace(",",".").replace("€",""))
            except (ValueError, TypeError):
                return 0.0

        def _order_hoeveelheid(o):
            return parse_hoeveelheid_getal(o.get("hoeveelheid",""))

        gefilterde_orders = [
            o for o in alle_orders
            if o.get("materiaal","").strip() == gekozen_materiaal
            and _bedrijf_land_lookup.get(o.get("bedrijf",""), "") == gekozen_land
        ]
        gewonnen_orders = [o for o in gefilterde_orders if o.get("status") == "Gewonnen"]

        # --- Omzet deze maand vs. vorige maand ---
        _vandaag = datetime.date.today()
        _deze_maand_key = (_vandaag.year, _vandaag.month)
        _vorige_maand_datum = (_vandaag.replace(day=1) - datetime.timedelta(days=1))
        _vorige_maand_key = (_vorige_maand_datum.year, _vorige_maand_datum.month)

        def _maand_key(datum_str):
            try:
                d = datetime.date.fromisoformat(datum_str)
                return (d.year, d.month)
            except (ValueError, TypeError):
                return None

        omzet_deze_maand = sum(_order_getal(o) for o in gewonnen_orders if _maand_key(o.get("datum","")) == _deze_maand_key)
        omzet_vorige_maand = sum(_order_getal(o) for o in gewonnen_orders if _maand_key(o.get("datum","")) == _vorige_maand_key)
        omzet_verschil_pct = round((omzet_deze_maand - omzet_vorige_maand) / omzet_vorige_maand * 100, 1) if omzet_vorige_maand > 0 else None

        # --- Gemiddelde verkoopprijs per ton ---
        totaal_omzet_gewonnen = sum(_order_getal(o) for o in gewonnen_orders)
        totaal_volume_gewonnen = sum(_order_hoeveelheid(o) for o in gewonnen_orders)
        gem_verkoopprijs_per_ton = round(totaal_omzet_gewonnen / totaal_volume_gewonnen, 2) if totaal_volume_gewonnen > 0 else None

        # --- Volumeontwikkeling per maand (laatste 6 maanden) ---
        _maand_labels = []
        _maand_sleutels = []
        _cursor = _vandaag.replace(day=1)
        for _ in range(6):
            _maand_sleutels.append((_cursor.year, _cursor.month))
            _maand_labels.append(_cursor.strftime("%b %Y"))
            _cursor = (_cursor - datetime.timedelta(days=1)).replace(day=1)
        _maand_sleutels.reverse()
        _maand_labels.reverse()
        volume_per_maand = []
        for sleutel, label in zip(_maand_sleutels, _maand_labels):
            vol = sum(_order_hoeveelheid(o) for o in gewonnen_orders if _maand_key(o.get("datum","")) == sleutel)
            volume_per_maand.append({"label": label, "volume": round(vol, 1)})
        max_volume_maand = max([v["volume"] for v in volume_per_maand], default=1) or 1

        # --- Prijsontwikkeling per materiaal (uit marktprijzen, niet land-specifiek) ---
        alle_marktprijzen = laad_marktprijzen()
        prijspunten_materiaal = sorted(
            [p for p in alle_marktprijzen if p.get("materiaal","") == gekozen_materiaal],
            key=lambda p: p.get("datum","")
        )[-12:]

        # --- Gemiddeld laadgewicht per leverancier (weegbrug, materiaal+land-gefilterd) ---
        alle_weegrecords = laad_weegbrug()
        weegrecords_gefilterd = [
            r for r in alle_weegrecords
            if r.get("materiaal","").strip() == gekozen_materiaal
            and _bedrijf_land_lookup.get(r.get("leverancier",""), "") == gekozen_land
            and r.get("netto_gewicht")
        ]
        per_leverancier = {}
        for r in weegrecords_gefilterd:
            lev = r.get("leverancier","Onbekend")
            per_leverancier.setdefault(lev, []).append(float(r["netto_gewicht"]))
        gem_laadgewicht_per_leverancier = sorted(
            [{"leverancier": lev, "gemiddeld": round(sum(gewichten)/len(gewichten), 0), "aantal": len(gewichten)} for lev, gewichten in per_leverancier.items()],
            key=lambda x: -x["gemiddeld"]
        )

        # --- Contractvoortgang: goedgekeurde inkoopcontracten voor dit materiaal, bij
        # leveranciers in het gekozen land — met geleverd/resterend tonnage. Dit maakt
        # zichtbaar wat er via Live Operaties/Weegbrug al daadwerkelijk gekoppeld is,
        # rechtstreeks vanuit de commerciële kant. Herbruikt dezelfde functie als de
        # CSV-export, zodat scherm en export nooit uit de pas kunnen lopen. ---
        contractvoortgang_lijst = _bereken_contractvoortgang_inzichten(gekozen_materiaal, gekozen_land)

        resultaat_html = render_template_string("""
<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Omzet</div>
<div class="ci-grid" style="margin-bottom:24px;">
    <div class="ci-kaart">
        <div class="ci-getal">€{{ "{:,.0f}".format(omzet_deze_maand).replace(",", ".") }}</div>
        <div class="ci-label">Omzet deze maand</div>
        {% if omzet_verschil_pct is not none %}<div style="font-size:11.5px;color:{{ '#16a34a' if omzet_verschil_pct >= 0 else '#dc2626' }};margin-top:4px;">{{ '+' if omzet_verschil_pct >= 0 else '' }}{{ omzet_verschil_pct }}% t.o.v. vorige maand</div>{% endif %}
    </div>
    <div class="ci-kaart">
        <div class="ci-getal">€{{ "{:,.0f}".format(omzet_vorige_maand).replace(",", ".") }}</div>
        <div class="ci-label">Omzet vorige maand</div>
    </div>
    <div class="ci-kaart">
        <div class="ci-getal">{% if gem_verkoopprijs_per_ton %}€{{ gem_verkoopprijs_per_ton }}{% else %}—{% endif %}</div>
        <div class="ci-label">Gem. verkoopprijs per ton (gewonnen)</div>
    </div>
</div>

<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Volumeontwikkeling per maand</div>
<div style="margin-bottom:24px;">
    {% for v in volume_per_maand %}
    <div style="display:flex;align-items:center;gap:10px;padding:6px 0;">
        <span style="width:80px;font-size:11.5px;color:var(--gray-500);">{{ v.label }}</span>
        <div style="flex:1;background:var(--gray-100);border-radius:4px;height:16px;overflow:hidden;">
            <div style="background:var(--brand-600);height:100%;width:{{ (v.volume/max_volume_maand*100)|round(1) }}%;"></div>
        </div>
        <span style="width:70px;text-align:right;font-size:11.5px;color:var(--gray-600);font-family:var(--font-mono);">{{ v.volume }} t</span>
    </div>
    {% endfor %}
</div>

<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Prijsontwikkeling {{ gekozen_materiaal }} (marktprijzen)</div>
{% if prijspunten_materiaal %}
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);margin-bottom:24px;">
    {% for p in prijspunten_materiaal %}
    <div style="display:flex;padding:7px 4px;border-bottom:1px solid var(--gray-100);font-size:12.5px;">
        <span style="width:110px;color:var(--gray-500);">{{ p.datum }}</span>
        <span style="color:var(--gray-700);font-weight:600;">€{{ p.prijs_per_ton }} / ton</span>
        <span style="margin-left:10px;color:var(--gray-400);">{{ p.bron or '' }}</span>
    </div>
    {% endfor %}
</div>
{% else %}
<div class="lege-staat" style="margin-bottom:24px;">Nog geen marktprijspunten voor {{ gekozen_materiaal }}.</div>
{% endif %}

<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Gemiddeld laadgewicht per leverancier</div>
{% if gem_laadgewicht_per_leverancier %}
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);">
    {% for l in gem_laadgewicht_per_leverancier %}
    <div style="display:flex;padding:7px 4px;border-bottom:1px solid var(--gray-100);font-size:12.5px;">
        <span style="flex:1;color:var(--gray-700);">{{ l.leverancier }}</span>
        <span style="width:120px;text-align:right;font-family:var(--font-mono);color:var(--gray-600);">{{ "{:,.0f}".format(l.gemiddeld) }} kg</span>
        <span style="width:80px;text-align:right;color:var(--gray-400);">{{ l.aantal }}x</span>
    </div>
    {% endfor %}
</div>
{% else %}
<div class="lege-staat">Geen weegrecords voor deze combinatie.</div>
{% endif %}

<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
    <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;">Contractvoortgang (goedgekeurde inkoopcontracten)</div>
    <a href="/inzichten/export/contractvoortgang?materiaal={{ gekozen_materiaal|urlencode }}&land={{ gekozen_land|urlencode }}" style="font-size:11.5px;font-weight:600;color:var(--brand-600);text-decoration:none;">↓ CSV exporteren</a>
</div>
{% if contractvoortgang_lijst %}
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);">
    {% for c in contractvoortgang_lijst %}
    <div style="display:flex;align-items:center;padding:8px 4px;border-bottom:1px solid var(--gray-100);font-size:12.5px;">
        <span style="flex:1.3;font-family:var(--font-mono);color:var(--gray-500);">{{ c.contractnummer }}</span>
        <span style="flex:1;color:var(--gray-700);">{{ c.leverancier }} — {{ c.kwaliteit }}</span>
        <span style="width:110px;text-align:right;color:var(--gray-500);">{{ c.geleverd }} / {{ c.totaal }} MT</span>
        <span style="width:110px;text-align:right;font-weight:700;color:{{ '#dc2626' if c.resterend > 0 else '#16a34a' }};">{{ c.resterend }} MT open</span>
    </div>
    {% endfor %}
</div>
{% else %}
<div class="lege-staat">Geen goedgekeurde inkoopcontracten voor deze combinatie.</div>
{% endif %}
        """, omzet_deze_maand=omzet_deze_maand, omzet_vorige_maand=omzet_vorige_maand,
             omzet_verschil_pct=omzet_verschil_pct, gem_verkoopprijs_per_ton=gem_verkoopprijs_per_ton,
             volume_per_maand=volume_per_maand, max_volume_maand=max_volume_maand,
             prijspunten_materiaal=prijspunten_materiaal, gekozen_materiaal=gekozen_materiaal, gekozen_land=gekozen_land,
             gem_laadgewicht_per_leverancier=gem_laadgewicht_per_leverancier,
             contractvoortgang_lijst=contractvoortgang_lijst)

    inhoud = """
<div class="page-title">Commerciële Inzichten</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Kies materiaal en land om rapportages te zien.</p>

<style>
.ci-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; }
.ci-kaart { background:transparent; border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); padding:16px 4px; }
.ci-getal { font-size:1.5rem; font-weight:800; color:var(--gray-800); }
.ci-label { font-size:0.72rem; color:var(--gray-400); text-transform:uppercase; letter-spacing:0.6px; margin-top:4px; font-weight:600; }
</style>

<form method="GET" style="display:flex;gap:10px;margin-bottom:24px;flex-wrap:wrap;">
    <select name="materiaal" required style="padding:8px 12px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
        <option value="">Materiaal kiezen...</option>
        {% for m in materiaal_opties %}<option value="{{ m }}" {% if gekozen_materiaal == m %}selected{% endif %}>{{ m }}</option>{% endfor %}
    </select>
    <select name="land" required style="padding:8px 12px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
        <option value="">Land kiezen...</option>
        {% for land in landen_keuze %}<option value="{{ land }}" {% if gekozen_land == land %}selected{% endif %}>{{ land_labels[land] }}</option>{% endfor %}
    </select>
    <button type="submit" style="padding:8px 18px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">Tonen</button>
</form>

{% if not gekozen_materiaal or not gekozen_land %}
<div class="lege-staat">Kies hierboven een materiaal én land om de commerciële inzichten te zien.</div>
{% else %}
""" + resultaat_html + """
{% endif %}
    """
    pagina = render_simple_page("Inzichten", "inzichten", inhoud)
    return render_template_string(pagina, materiaal_opties=materiaal_opties, landen_keuze=LANDEN_KEUZE,
                                    land_labels=LAND_LABELS, gekozen_materiaal=gekozen_materiaal, gekozen_land=gekozen_land)