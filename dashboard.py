"""
dashboard.py — Blueprint voor de Dashboard- en Inzichten-modules.

Bevat: /dashboard (KPI's, ingekocht per maand, sales-pipeline, team-
prestaties, topklanten, "vraagt om aandacht") en /inzichten (landen-/
materiaalverdeling). Gebruikt dagelijkse snapshots voor groeicijfers.

Registratie in app.py met: app.register_blueprint(dashboard_bp)
"""
import json
import datetime
from flask import Blueprint, session, render_template_string

from core import (
    datapad, laad_status, laad_shipments, laad_voorraad, laad_orders,
    laad_accountmanagers, laad_users, laad_notities, laad_marktprijzen,
    laad_transport_data, laad_cert_vervaldatums, _cert_sleutel, laad_meldingen,
    parse_hoeveelheid_getal, bereken_afstand_km, bepaal_shipment_flow_type,
    shipment_hoeveelheid, render_simple_page, ENF_BEDRIJVEN, LANDEN,
    effectieve_afdeling, laad_weegbrug, laad_logistieke_orders, laad_transport_planning,
    laad_containers,
)

dashboard_bp = Blueprint("dashboard", __name__)

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
                                    kpi_klaar_finance=kpi_klaar_finance, kpi_transport_gepland=kpi_transport_gepland,
                                    kpi_transport_onderweg=kpi_transport_onderweg, kpi_transport_vertraagd=kpi_transport_vertraagd,
                                    kpi_containers_onderweg=kpi_containers_onderweg, recente_weegrecords=recente_weegrecords)

@dashboard_bp.route("/dashboard")
def dashboard():
    if effectieve_afdeling() in ("logistiek", "weegbrug"):
        return _logistiek_dashboard()

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
@dashboard_bp.route("/inzichten")
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