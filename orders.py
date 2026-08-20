"""
orders.py — Blueprint voor de Orders-module.

Bevat: /orders (GET/POST — orders bekijken, toevoegen, status wijzigen,
verwijderen) en /export-orders-csv.

Registratie in app.py met: app.register_blueprint(orders_bp)
"""
import uuid
import datetime
from flask import Blueprint, request, session, redirect, url_for, render_template_string

from core import (
    laad_orders, bewaar_orders, laad_accountmanagers, laad_meldingen, bewaar_meldingen,
    laad_marktprijzen, bewaar_marktprijzen, parse_hoeveelheid_getal, laad_shipments,
    laad_status, laad_materiaal_taxonomie, render_simple_page,
    ORDER_STATUSSEN, ORDER_KLEUREN, vereist_afdeling_of_403, laad_handelsorders,
)

orders_bp = Blueprint("orders", __name__)

@orders_bp.route("/export-orders-csv")
def export_orders_csv():
    _guard = vereist_afdeling_of_403("orders")
    if _guard: return _guard
    import csv, io
    filter_status = request.args.get("filter_status", "")
    filter_materiaal = request.args.get("filter_materiaal", "")
    filter_verantwoordelijke = request.args.get("filter_verantwoordelijke", "")

    orders = laad_orders()
    if filter_status:
        orders = [o for o in orders if o.get("status") == filter_status]
    if filter_materiaal:
        orders = [o for o in orders if o.get("materiaal") == filter_materiaal]
    if filter_verantwoordelijke:
        orders = [o for o in orders if o.get("verantwoordelijke") == filter_verantwoordelijke]

    output = io.StringIO()
    schrijver = csv.writer(output)
    schrijver.writerow(["Bedrijf", "Materiaal", "Hoeveelheid", "Prijs", "Status", "Verantwoordelijke", "Verwachte datum", "Notitie", "Aangemaakt"])
    for o in orders:
        schrijver.writerow([o.get("bedrijf",""), o.get("materiaal",""), o.get("hoeveelheid",""), o.get("prijs",""),
                             o.get("status",""), o.get("verantwoordelijke",""), o.get("verwachte_datum",""),
                             o.get("notitie",""), o.get("aangemaakt","")])

    from flask import Response
    return Response(output.getvalue(), mimetype="text/csv",
                     headers={"Content-Disposition": "attachment; filename=orders_export.csv"})


@orders_bp.route("/orders", methods=["GET", "POST"])
def orders_pagina():
    _guard = vereist_afdeling_of_403("orders")
    if _guard: return _guard
    if request.method == "POST":
        actie = request.form.get("actie", "")
        alle_orders = laad_orders()

        if actie == "toevoegen":
            nieuwe_order = {
                "id": str(uuid.uuid4()),
                "bedrijf": request.form.get("bedrijf", "").strip(),
                "ordertype": request.form.get("ordertype", "verkoop"),
                "materiaal": request.form.get("materiaal", "").strip(),
                "hoeveelheid": request.form.get("hoeveelheid", "").strip(),
                "prijs": request.form.get("prijs", "").strip(),
                "status": request.form.get("status", "Open"),
                "verantwoordelijke": session.get("gebruikersnaam", ""),
                "verwachte_datum": request.form.get("verwachte_datum", "").strip(),
                "bestemming": request.form.get("bestemming", "").strip(),
                "transportmiddel": request.form.get("transportmiddel", "").strip(),
                "notitie": request.form.get("notitie", "").strip(),
                "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
            }
            if nieuwe_order["bedrijf"]:
                alle_orders.append(nieuwe_order)
                bewaar_orders(alle_orders)

                toegewezen_am = laad_accountmanagers().get(nieuwe_order["bedrijf"], "")
                if toegewezen_am and toegewezen_am != nieuwe_order["verantwoordelijke"]:
                    alle_meldingen = laad_meldingen()
                    alle_meldingen.append({
                        "id": str(uuid.uuid4()),
                        "tekst": f"{nieuwe_order['verantwoordelijke']} heeft een order aangemaakt voor {nieuwe_order['bedrijf']} (jouw bedrijf) — {nieuwe_order.get('materiaal','') or 'geen materiaal'}{', €' + nieuwe_order['prijs'] if nieuwe_order.get('prijs') else ''}.",
                        "bedrijf": nieuwe_order["bedrijf"], "van": nieuwe_order["verantwoordelijke"],
                        "voor_gebruiker": toegewezen_am, "voor_team": "",
                        "gelezen": False, "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
                    })
                    bewaar_meldingen(alle_meldingen)

        elif actie == "status_wijzigen":
            order_id = request.form.get("order_id", "")
            nieuwe_status = request.form.get("nieuwe_status", "")
            gewijzigde_order = None
            for o in alle_orders:
                if o["id"] == order_id:
                    o["status"] = nieuwe_status
                    gewijzigde_order = o
            bewaar_orders(alle_orders)

            if gewijzigde_order and nieuwe_status == "Gewonnen":
                huidige_gebruikersnaam = session.get("gebruikersnaam", "")

                # Automatisch een marktprijspunt loggen: prijs/hoeveelheid = €/ton, waardevolle marktdata
                if gewijzigde_order.get("materiaal") and gewijzigde_order.get("prijs"):
                    _hoeveelheid_ton = parse_hoeveelheid_getal(gewijzigde_order.get("hoeveelheid", ""))
                    try:
                        _prijs_totaal = float(str(gewijzigde_order["prijs"]).replace(",", "").replace("€", "").strip())
                    except (ValueError, TypeError):
                        _prijs_totaal = 0
                    if _hoeveelheid_ton > 0 and _prijs_totaal > 0:
                        _marktprijzen = laad_marktprijzen()
                        _prijs_per_ton = round(_prijs_totaal / _hoeveelheid_ton, 2)
                        _marktprijzen.append({
                            "id": str(uuid.uuid4()), "materiaal": gewijzigde_order["materiaal"],
                            "prijs_per_ton": _prijs_per_ton, "bron": "order",
                            "bedrijf": gewijzigde_order.get("bedrijf", ""), "order_id": gewijzigde_order["id"],
                            "notitie": "", "gebruiker": huidige_gebruikersnaam,
                            "datum": datetime.date.today().isoformat(),
                            "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
                        })
                        bewaar_marktprijzen(_marktprijzen)

                toegewezen_am = laad_accountmanagers().get(gewijzigde_order["bedrijf"], "")
                if toegewezen_am and toegewezen_am != huidige_gebruikersnaam:
                    alle_meldingen = laad_meldingen()
                    prijs_tekst = f" (€{gewijzigde_order['prijs']})" if gewijzigde_order.get("prijs") else ""
                    alle_meldingen.append({
                        "id": str(uuid.uuid4()),
                        "tekst": f"🎉 Order gewonnen! {huidige_gebruikersnaam} heeft een order voor {gewijzigde_order['bedrijf']} (jouw bedrijf) op 'Gewonnen' gezet{prijs_tekst}.",
                        "bedrijf": gewijzigde_order["bedrijf"], "van": huidige_gebruikersnaam,
                        "voor_gebruiker": toegewezen_am, "voor_team": "",
                        "gelezen": False, "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
                    })
                    bewaar_meldingen(alle_meldingen)

        elif actie == "verwijderen":
            order_id = request.form.get("order_id", "")
            alle_orders = [o for o in alle_orders if o["id"] != order_id]
            bewaar_orders(alle_orders)

        return redirect(url_for("orders.orders_pagina"))

    alle_orders = laad_orders()
    alle_orders.sort(key=lambda o: o.get("aangemaakt", ""), reverse=True)

    # Koppel elke order aan een reeds aangemaakte shipment (via "Uitboeken"/"Inboeken"), zodat je niet per ongeluk dubbel boekt
    _alle_shipments_lookup = laad_shipments()
    for o in alle_orders:
        gekoppelde_ref = f"Order-{o['id'][:8]}"
        gekoppelde_shipment = next((s for s in _alle_shipments_lookup if s.get("referentie") == gekoppelde_ref), None)
        o["gekoppelde_shipment"] = gekoppelde_shipment

    open_waarde = sum(float(o["prijs"]) for o in alle_orders if o["status"] in ("Open", "Onderhandeling") and o.get("prijs", "").replace(".","",1).isdigit())
    gewonnen_waarde = sum(float(o["prijs"]) for o in alle_orders if o["status"] == "Gewonnen" and o.get("prijs", "").replace(".","",1).isdigit())
    _vandaag_kpi = datetime.date.today()
    aantal_verlopen = 0
    for o in alle_orders:
        if o.get("status") in ("Open", "Onderhandeling") and o.get("verwachte_datum"):
            try:
                if datetime.datetime.strptime(o["verwachte_datum"], "%Y-%m-%d").date() < _vandaag_kpi:
                    aantal_verlopen += 1
            except (ValueError, TypeError):
                pass
    vooringevuld_bedrijf = request.args.get("bedrijf", "")

    _status_alle = laad_status()
    _accountmanagers_alle = laad_accountmanagers()
    alle_bedrijfsnamen = sorted(set(_status_alle.keys()) | set(_accountmanagers_alle.keys()))[:500]

    filter_status = request.args.get("filter_status", "")
    filter_materiaal = request.args.get("filter_materiaal", "")
    filter_verantwoordelijke = request.args.get("filter_verantwoordelijke", "")
    getoonde_orders = alle_orders
    if filter_status:
        getoonde_orders = [o for o in getoonde_orders if o.get("status") == filter_status]
    if filter_materiaal:
        getoonde_orders = [o for o in getoonde_orders if o.get("materiaal") == filter_materiaal]
    if filter_verantwoordelijke:
        getoonde_orders = [o for o in getoonde_orders if o.get("verantwoordelijke") == filter_verantwoordelijke]

    alle_materialen_in_orders = sorted({o.get("materiaal") for o in alle_orders if o.get("materiaal")})
    alle_verantwoordelijken = sorted({o.get("verantwoordelijke") for o in alle_orders if o.get("verantwoordelijke")})

    _vandaag = datetime.date.today()
    for o in getoonde_orders:
        o["is_verlopen"] = False
        if o.get("status") in ("Open", "Onderhandeling") and o.get("verwachte_datum"):
            try:
                verwachte_datum_obj = datetime.datetime.strptime(o["verwachte_datum"], "%Y-%m-%d").date()
                o["is_verlopen"] = verwachte_datum_obj < _vandaag
            except (ValueError, TypeError):
                pass

    # --- Gecombineerd overzicht: pipeline-orders (dit bestand) + Handelsorders
    # (het nieuwe inkoop/verkoop-contractsysteem) samen, met twee indelingen. ---
    alle_handelsorders = laad_handelsorders()
    gecombineerde_lijst = []
    for o in alle_orders:
        gecombineerde_lijst.append({
            "bron": "pipeline", "id": o["id"], "naam": o.get("bedrijf",""), "materiaal": o.get("materiaal",""),
            "status": o.get("status",""), "verantwoordelijke": o.get("verantwoordelijke",""),
            "bedrijfseenheid": "", "link": "/orders",
        })
    for o in alle_handelsorders:
        gecombineerde_lijst.append({
            "bron": "handelsorder", "id": o["id"], "naam": o.get("tegenpartij_naam",""), "materiaal": o.get("materiaal",""),
            "status": o.get("status",""), "verantwoordelijke": o.get("aangemaakt_door",""),
            "bedrijfseenheid": o.get("bedrijfseenheid","") or "Niet ingedeeld", "link": f"/handelsorders/{o['id']}",
        })

    per_accountmanager = {}
    for o in gecombineerde_lijst:
        sleutel = o["verantwoordelijke"] or "Onbekend"
        per_accountmanager.setdefault(sleutel, []).append(o)
    per_bedrijfseenheid = {}
    for o in gecombineerde_lijst:
        sleutel = o["bedrijfseenheid"] or "Niet ingedeeld"
        per_bedrijfseenheid.setdefault(sleutel, []).append(o)

    kpi_totaal_gecombineerd = len(gecombineerde_lijst)
    kpi_handelsorders_definitief = len([o for o in alle_handelsorders if o.get("status") == "Definitief"])
    kpi_handelsorders_concept = len([o for o in alle_handelsorders if o.get("status") == "Concept"])

    inhoud = """
<style>
.order-kaart { background:#fff; border:1px solid var(--gray-200); border-radius:12px; padding:16px 18px; margin-bottom:10px; }
.order-top { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; }
.order-bedrijf { font-weight:700; color:var(--gray-800); font-size:0.95rem; }
.order-details { font-size:0.8rem; color:var(--gray-500); margin-top:4px; }
.order-status-select { font-size:0.75rem; font-weight:700; padding:4px 8px; border-radius:6px; border:none; cursor:pointer; }
.form-nieuw-order { background:#fff; border:1px solid var(--gray-200); border-radius:12px; padding:18px; margin-bottom:20px; }
.form-nieuw-order input, .form-nieuw-order select, .form-nieuw-order textarea { width:100%; padding:8px 10px; border:1px solid var(--gray-200); border-radius:6px; font-size:13px; margin-bottom:10px; font-family:inherit; box-sizing:border-box; }
.form-rij-2 { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
.kpi-mini { display:flex; gap:16px; margin-bottom:20px; }
.kpi-mini div { background:#fff; border:1px solid var(--gray-200); border-radius:10px; padding:14px 18px; flex:1; }
.kpi-mini .getal { font-size:1.4rem; font-weight:800; color:var(--brand-600); }
.kpi-mini .label { font-size:0.75rem; color:var(--gray-400); }
</style>
<div class="page-title">Orders</div>

<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Overzicht — alle orders</div>
<style>
.oo-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; margin-bottom:20px; }
.oo-kaart { background:transparent; border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); padding:14px 4px; }
.oo-getal { font-size:1.5rem; font-weight:800; color:var(--gray-800); }
.oo-label { font-size:0.72rem; color:var(--gray-400); text-transform:uppercase; letter-spacing:0.6px; margin-top:4px; font-weight:600; }
.oo-tabs { display:flex; gap:4px; margin-bottom:12px; }
.oo-tab { padding:6px 14px; font-size:12px; font-weight:600; color:var(--gray-400); cursor:pointer; border:none; background:none; border-bottom:2px solid transparent; }
.oo-tab.actief { color:var(--brand-600); border-bottom-color:var(--brand-600); }
.oo-groep-kop { font-size:12.5px; font-weight:700; color:var(--gray-700); padding:8px 4px; background:var(--gray-50); }
.oo-rij { display:flex; align-items:center; padding:8px 4px; border-bottom:1px solid var(--gray-100); font-size:12px; text-decoration:none; color:inherit; }
</style>

<div class="oo-grid">
    <div class="oo-kaart"><div class="oo-getal">{{ kpi_totaal_gecombineerd }}</div><div class="oo-label">Totaal orders (beide systemen)</div></div>
    <div class="oo-kaart"><div class="oo-getal">{{ kpi_handelsorders_concept }}</div><div class="oo-label">Handelsorders — concept</div></div>
    <div class="oo-kaart"><div class="oo-getal">{{ kpi_handelsorders_definitief }}</div><div class="oo-label">Handelsorders — definitief</div></div>
</div>

<a href="/handelsorders/nieuw" style="display:inline-block;margin-bottom:20px;font-size:12.5px;font-weight:700;color:#fff;background:var(--brand-600);text-decoration:none;padding:9px 18px;border-radius:6px;">+ Nieuwe order</a>

<div class="oo-tabs">
    <button type="button" class="oo-tab actief" onclick="wisselIndeling('am')" id="tab_am">Per accountmanager</button>
    <button type="button" class="oo-tab" onclick="wisselIndeling('be')" id="tab_be">Per bedrijfseenheid</button>
</div>

<div id="indeling_am" style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);margin-bottom:32px;">
    {% for groep, items in per_accountmanager.items() %}
    <div class="oo-groep-kop">{{ groep }} ({{ items|length }})</div>
    {% for o in items %}
    <a href="{{ o.link }}" class="oo-rij">
        <span style="flex:1;font-weight:600;color:var(--gray-800);">{{ o.naam or '—' }}</span>
        <span style="flex:1;color:var(--gray-500);">{{ o.materiaal or '—' }}</span>
        <span style="width:90px;color:var(--gray-400);">{{ "Handelsorder" if o.bron == "handelsorder" else "Pipeline" }}</span>
        <span style="width:100px;color:var(--gray-600);">{{ o.status }}</span>
    </a>
    {% endfor %}
    {% endfor %}
</div>

<div id="indeling_be" style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);margin-bottom:32px;display:none;">
    {% for groep, items in per_bedrijfseenheid.items() %}
    <div class="oo-groep-kop">{{ groep }} ({{ items|length }})</div>
    {% for o in items %}
    <a href="{{ o.link }}" class="oo-rij">
        <span style="flex:1;font-weight:600;color:var(--gray-800);">{{ o.naam or '—' }}</span>
        <span style="flex:1;color:var(--gray-500);">{{ o.materiaal or '—' }}</span>
        <span style="width:90px;color:var(--gray-400);">{{ "Handelsorder" if o.bron == "handelsorder" else "Pipeline" }}</span>
        <span style="width:100px;color:var(--gray-600);">{{ o.status }}</span>
    </a>
    {% endfor %}
    {% endfor %}
</div>

<script>
function wisselIndeling(welke) {
    document.getElementById("indeling_am").style.display = welke === "am" ? "block" : "none";
    document.getElementById("indeling_be").style.display = welke === "be" ? "block" : "none";
    document.getElementById("tab_am").classList.toggle("actief", welke === "am");
    document.getElementById("tab_be").classList.toggle("actief", welke === "be");
}
</script>

<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Pipeline-orders (los, kort proces)</div>

<div class="kpi-mini">
    <div><div class="getal">€{{ "{:,.0f}".format(open_waarde) }}</div><div class="label">Openstaande waarde</div></div>
    <div><div class="getal">€{{ "{:,.0f}".format(gewonnen_waarde) }}</div><div class="label">Gewonnen (totaal)</div></div>
    <div><div class="getal">{{ alle_orders|length }}</div><div class="label">Totaal orders</div></div>
    {% if aantal_verlopen > 0 %}<div style="border-color:#fecaca;"><div class="getal" style="color:#dc2626;">{{ aantal_verlopen }}</div><div class="label">⚠ Verlopen</div></div>{% endif %}
</div>

<form method="GET" style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
    <a href="/orders?filter_verantwoordelijke={{ gebruikersnaam }}" style="padding:6px 12px;border-radius:6px;font-size:12.5px;font-weight:600;text-decoration:none;{% if filter_verantwoordelijke == gebruikersnaam %}background:var(--brand-600);color:#fff;{% else %}background:var(--brand-50);color:var(--brand-700);{% endif %}">🙋 Mijn orders</a>
    <select name="filter_status" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle statussen</option>
        {% for s in statussen %}<option value="{{ s }}" {% if filter_status == s %}selected{% endif %}>{{ s }}</option>{% endfor %}
    </select>
    <select name="filter_materiaal" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle materialen</option>
        {% for m in alle_materialen_in_orders %}<option value="{{ m }}" {% if filter_materiaal == m %}selected{% endif %}>{{ m }}</option>{% endfor %}
    </select>
    <select name="filter_verantwoordelijke" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Iedereen</option>
        {% for v in alle_verantwoordelijken %}<option value="{{ v }}" {% if filter_verantwoordelijke == v %}selected{% endif %}>{{ v }}</option>{% endfor %}
    </select>
    {% if filter_status or filter_materiaal or filter_verantwoordelijke %}<a href="/orders" style="font-size:12px;color:var(--gray-400);text-decoration:none;">Wis filters</a>{% endif %}
    <span style="font-size:12px;color:var(--gray-400);margin-left:auto;">{{ getoonde_orders|length }} van {{ alle_orders|length }} orders</span>
    <a href="/export-orders-csv?filter_status={{ filter_status }}&filter_materiaal={{ filter_materiaal|urlencode }}&filter_verantwoordelijke={{ filter_verantwoordelijke }}" style="font-size:12px;font-weight:600;color:var(--brand-600);text-decoration:none;border:1px solid var(--gray-200);padding:5px 10px;border-radius:6px;">⬇ Export CSV</a>
</form>

{% if getoonde_orders %}
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);">
    <div class="data-thead">
        <span style="flex:1.6;">Bedrijf &amp; materiaal</span>
        <span style="width:110px;text-align:right;">Waarde</span>
        <span style="width:100px;">Verwacht</span>
        <span style="width:150px;">Status</span>
        <span style="width:100px;">Verantw.</span>
    </div>
    {% for o in getoonde_orders %}
    <a href="/orders/{{ o.id }}" class="data-row">
        <span style="flex:1.6;">
            <span style="font-weight:600;color:var(--gray-800);">{{ o.bedrijf }}</span>
            {% if o.is_verlopen %} <span style="background:#fef2f2;color:#dc2626;font-size:9px;font-weight:700;padding:2px 6px;border-radius:5px;">VERLOPEN</span>{% endif %}
            <br><span class="zacht">{{ o.materiaal|default('—',true) }}{% if o.hoeveelheid %} · {{ o.hoeveelheid }}{% endif %}{% if o.bestemming %} · {{ o.bestemming }}{% endif %}</span>
        </span>
        <span style="width:110px;text-align:right;" class="num">{% if o.prijs %}€{{ o.prijs }}{% else %}—{% endif %}</span>
        <span style="width:100px;" class="zacht">{{ o.verwachte_datum|default('—',true) }}</span>
        <span style="width:150px;color:var(--gray-600);">{{ o.status }}</span>
        <span style="width:100px;" class="zacht">{{ o.verantwoordelijke }}</span>
    </a>
    {% endfor %}
</div>
{% else %}
<div class="lege-staat">Geen pipeline-orders gevonden.</div>
{% endif %}
    """
    pagina = render_simple_page("Orders", "orders", inhoud)
    return render_template_string(pagina, alle_orders=alle_orders, getoonde_orders=getoonde_orders, statussen=ORDER_STATUSSEN,
                                    statuskleuren=ORDER_KLEUREN, open_waarde=open_waarde, gewonnen_waarde=gewonnen_waarde,
                                    filter_status=filter_status, filter_materiaal=filter_materiaal, filter_verantwoordelijke=filter_verantwoordelijke,
                                    alle_materialen_in_orders=alle_materialen_in_orders, alle_verantwoordelijken=alle_verantwoordelijken,
                                    vooringevuld_bedrijf=vooringevuld_bedrijf, materiaal_taxonomie=laad_materiaal_taxonomie(),
                                    alle_bedrijfsnamen=alle_bedrijfsnamen, aantal_verlopen=aantal_verlopen,
                                    gebruikersnaam=session.get("gebruikersnaam", ""),
                                    per_accountmanager=per_accountmanager, per_bedrijfseenheid=per_bedrijfseenheid,
                                    kpi_totaal_gecombineerd=kpi_totaal_gecombineerd,
                                    kpi_handelsorders_concept=kpi_handelsorders_concept,
                                    kpi_handelsorders_definitief=kpi_handelsorders_definitief)

@orders_bp.route("/orders/<order_id>", methods=["GET", "POST"])
def order_detail(order_id):
    """Inzien + beheren van één pipeline-order. Bewust een aparte pagina — de
    overzichtslijst zelf toont nu alleen nog informatie, geen acties."""
    _guard = vereist_afdeling_of_403("orders")
    if _guard: return _guard

    alle_orders = laad_orders()
    order = next((o for o in alle_orders if o["id"] == order_id), None)
    if not order:
        pagina = render_simple_page("Niet gevonden", "orders", '<div class="page-title">Order niet gevonden</div><div class="lege-staat">Deze order bestaat niet (meer). <a href="/orders">Terug naar Orders</a></div>')
        return render_template_string(pagina), 404

    if request.method == "POST":
        actie = request.form.get("actie", "")
        if actie == "status_wijzigen":
            nieuwe_status = request.form.get("nieuwe_status", "")
            order["status"] = nieuwe_status
            bewaar_orders(alle_orders)

            if nieuwe_status == "Gewonnen":
                huidige_gebruikersnaam = session.get("gebruikersnaam", "")
                if order.get("materiaal") and order.get("prijs"):
                    _hoeveelheid_ton = parse_hoeveelheid_getal(order.get("hoeveelheid", ""))
                    try:
                        _prijs_totaal = float(str(order["prijs"]).replace(",", "").replace("€", "").strip())
                    except (ValueError, TypeError):
                        _prijs_totaal = 0
                    if _hoeveelheid_ton > 0 and _prijs_totaal > 0:
                        _marktprijzen = laad_marktprijzen()
                        _prijs_per_ton = round(_prijs_totaal / _hoeveelheid_ton, 2)
                        _marktprijzen.append({
                            "id": str(uuid.uuid4()), "materiaal": order["materiaal"],
                            "prijs_per_ton": _prijs_per_ton, "bron": "order",
                            "bedrijf": order.get("bedrijf", ""), "order_id": order["id"],
                            "notitie": "", "gebruiker": huidige_gebruikersnaam,
                            "datum": datetime.date.today().isoformat(),
                            "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
                        })
                        bewaar_marktprijzen(_marktprijzen)

                toegewezen_am = laad_accountmanagers().get(order["bedrijf"], "")
                if toegewezen_am and toegewezen_am != huidige_gebruikersnaam:
                    alle_meldingen = laad_meldingen()
                    prijs_tekst = f" (€{order['prijs']})" if order.get("prijs") else ""
                    alle_meldingen.append({
                        "id": str(uuid.uuid4()),
                        "tekst": f"Order gewonnen! {huidige_gebruikersnaam} heeft een order voor {order['bedrijf']} (jouw bedrijf) op 'Gewonnen' gezet{prijs_tekst}.",
                        "bedrijf": order["bedrijf"], "van": huidige_gebruikersnaam,
                        "voor_gebruiker": toegewezen_am, "voor_team": "",
                        "gelezen": False, "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
                    })
                    bewaar_meldingen(alle_meldingen)
        elif actie == "verwijderen":
            alle_orders = [o for o in alle_orders if o["id"] != order_id]
            bewaar_orders(alle_orders)
            return redirect(url_for("orders.orders_pagina"))
        return redirect(url_for("orders.order_detail", order_id=order_id))

    _alle_shipments_lookup = laad_shipments()
    gekoppelde_ref = f"Order-{order['id'][:8]}"
    gekoppelde_shipment = next((s for s in _alle_shipments_lookup if s.get("referentie") == gekoppelde_ref), None)

    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/orders" style="color:var(--gray-400);text-decoration:none;">Orders</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">{{ order.bedrijf }}</span>
</div>
<div class="page-title">{{ order.bedrijf }}</div>

<div style="background:var(--gray-50);border-radius:8px;padding:18px 20px;font-size:12.5px;color:var(--gray-600);max-width:600px;margin-bottom:20px;">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
        <div><b>Type:</b> {{ "Inkoop" if order.get("ordertype") == "inkoop" else "Verkoop" }}</div>
        <div><b>Materiaal:</b> {{ order.materiaal or '—' }}</div>
        <div><b>Hoeveelheid:</b> {{ order.hoeveelheid or '—' }}</div>
        <div><b>Waarde:</b> {% if order.prijs %}€{{ order.prijs }}{% else %}—{% endif %}</div>
        <div><b>Verwachte datum:</b> {{ order.verwachte_datum or '—' }}</div>
        <div><b>Bestemming:</b> {{ order.bestemming or '—' }}</div>
        <div><b>Transportmiddel:</b> {{ order.transportmiddel or '—' }}</div>
        <div><b>Verantwoordelijke:</b> {{ order.verantwoordelijke or '—' }}</div>
    </div>
    {% if order.notitie %}<div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--gray-200);"><b>Notitie:</b> {{ order.notitie }}</div>{% endif %}
    {% if gekoppelde_shipment %}<div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--gray-200);"><b>Gekoppelde shipment:</b> {{ gekoppelde_shipment.status }}</div>{% endif %}
</div>

<form method="POST" style="margin-bottom:16px;display:flex;gap:8px;align-items:center;">
    <input type="hidden" name="actie" value="status_wijzigen">
    <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Status:</label>
    <select name="nieuwe_status" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        {% for s in statussen %}<option value="{{ s }}" {% if s == order.status %}selected{% endif %}>{{ s }}</option>{% endfor %}
    </select>
</form>

{% if order.status == "Gewonnen" and not gekoppelde_shipment %}
<a href="/voorraad?prefill_order={{ order.id }}" style="display:inline-block;margin-bottom:16px;font-size:12.5px;font-weight:700;color:#fff;background:{{ '#0891b2' if order.get('ordertype') == 'inkoop' else '#dc2626' }};text-decoration:none;padding:8px 16px;border-radius:6px;">{{ 'Inboeken in voorraad' if order.get('ordertype') == 'inkoop' else 'Uitboeken uit voorraad' }}</a>
{% endif %}

<form method="POST" onsubmit="return confirm('Deze order definitief verwijderen?');">
    <input type="hidden" name="actie" value="verwijderen">
    <button type="submit" style="padding:8px 16px;background:#fff;color:#dc2626;border:1px solid #fecaca;border-radius:6px;font-size:12.5px;cursor:pointer;">Verwijderen</button>
</form>
    """
    pagina = render_simple_page(order["bedrijf"], "orders", inhoud)
    return render_template_string(pagina, order=order, statussen=ORDER_STATUSSEN, gekoppelde_shipment=gekoppelde_shipment)