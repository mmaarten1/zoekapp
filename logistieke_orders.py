"""
logistieke_orders.py — Blueprint voor Logistieke Orders (Weegbrug Fase 2).

LET OP — dit is een ANDER concept dan orders.py (/orders, voor
accountmanagers/trading: klant, prijs, marge). Dit volgt de fysieke
aflevering van een inkomende vracht: Order aangemaakt -> Transport verwacht
-> Truck aangekomen -> Ingewogen -> Order gekoppeld -> Uitgewogen ->
Weegbon compleet -> Afhandeling -> Klaar voor Finance -> Gefactureerd ->
Afgerond. Een order wordt gekoppeld aan een Weegbrug-record; vanaf dat
moment lopen werkelijke hoeveelheid/aankomst automatisch mee vanuit de
weging (netto gewicht in kg -> ton).

Documenten (CMR/pakbon/etc.) worden gekoppeld via het bestaande, generieke
/api/documenten-systeem, met het ordernummer als sleutel — zelfde patroon
als eerder toegepast op shipments in de Logistiek-pagina.

Registratie in app.py met: app.register_blueprint(logistieke_orders_bp)
"""
import uuid
import datetime
from flask import Blueprint, request, session, redirect, url_for, render_template_string

from core import (
    laad_logistieke_orders, bewaar_logistieke_orders, genereer_logistiek_ordernummer,
    LOGISTIEKE_ORDER_STATUSSEN, laad_weegbrug, bewaar_weegbrug, WEEGBRUG_STATUS_BADGES,
    ENF_BEDRIJVEN, is_huidige_gebruiker_admin, vereist_afdeling_of_403, render_simple_page,
    laad_documenten, laad_orders, laad_shipments, bereken_voorraad_status, parse_hoeveelheid_getal,
    laad_handelsorders, laad_marktprijzen,
)

logistieke_orders_bp = Blueprint("logistieke_orders", __name__)

def _weegbrug_status_naar_orderstatus(weegbrug_status):
    """Vertaalt de weegbrug-status naar een passende suggestie voor de orderstatus, bij koppelen/synchroniseren."""
    if weegbrug_status == "Compleet":
        return "Weegbon compleet"
    if weegbrug_status == "Ingewogen":
        return "Ingewogen"
    return None


@logistieke_orders_bp.route("/logistiek/orders")
def logistieke_orders_pagina():
    _guard = vereist_afdeling_of_403("logistieke_orders")
    if _guard: return _guard

    alle_orders = laad_logistieke_orders()
    filter_status = request.args.get("filter_status", "")
    zoekterm = request.args.get("zoekterm", "").strip().lower()

    getoond = alle_orders
    if filter_status:
        getoond = [o for o in getoond if o.get("status") == filter_status]
    if zoekterm:
        getoond = [o for o in getoond if zoekterm in o.get("ordernummer","").lower() or zoekterm in o.get("leverancier","").lower() or zoekterm in o.get("kenteken","").lower()]
    getoond = sorted(getoond, key=lambda o: o.get("aangemaakt",""), reverse=True)

    # --- Dashboard-KPI's "Vandaag", exact zoals in het gevraagde voorbeeld ---
    _vandaag = datetime.date.today().isoformat()
    kpi_verwacht_vandaag = [o for o in alle_orders if o.get("verwachte_aankomst","") == _vandaag]
    kpi_aangekomen = [o for o in kpi_verwacht_vandaag if o.get("status") not in ("Order aangemaakt", "Transport verwacht")]
    kpi_volledig_gewogen = [o for o in alle_orders if o.get("status") in ("Weegbon compleet","Afhandeling","Klaar voor Finance","Gefactureerd","Afgerond")]
    kpi_wacht_uitwegen = [o for o in alle_orders if o.get("status") == "Ingewogen"]
    kpi_wacht_koppeling = [o for o in alle_orders if o.get("status") in ("Order aangemaakt","Transport verwacht","Truck aangekomen") and not o.get("gekoppeld_weegbrug_id")]
    kpi_wacht_afhandeling = [o for o in alle_orders if o.get("status") == "Afhandeling"]

    inhoud = """
<div class="page-title">Orders (logistiek)</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Volgt de fysieke aflevering van inkomende vrachten van order tot Finance-overdracht.</p>

<style>
.lo-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; }
.lo-kaart { background:transparent; border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); padding:14px 4px; }
.lo-getal { font-size:1.5rem; font-weight:800; color:var(--gray-800); }
.lo-label { font-size:0.7rem; color:var(--gray-400); text-transform:uppercase; letter-spacing:0.6px; margin-top:2px; font-weight:600; }
.lo-tabel-kop { display:flex; align-items:center; padding:10px 16px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); font-size:10px; letter-spacing:0.08em; text-transform:uppercase; color:#7d8792; }
.lo-tabel-rij { display:flex; align-items:center; padding:10px 16px; border-bottom:1px solid var(--gray-100); font-size:12.5px; }
</style>

<div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Vandaag</div>
<div class="lo-grid" style="margin-bottom:20px;">
    <div class="lo-kaart"><div class="lo-getal">{{ kpi_verwacht_vandaag|length }}</div><div class="lo-label">Verwachte vrachten</div></div>
    <div class="lo-kaart"><div class="lo-getal">{{ kpi_aangekomen|length }}</div><div class="lo-label">Aangekomen</div></div>
    <div class="lo-kaart"><div class="lo-getal">{{ kpi_volledig_gewogen|length }}</div><div class="lo-label">Volledig gewogen</div></div>
    <div class="lo-kaart"><div class="lo-getal">{{ kpi_wacht_uitwegen|length }}</div><div class="lo-label">Wacht op uitweging</div></div>
    <div class="lo-kaart"><div class="lo-getal">{{ kpi_wacht_koppeling|length }}</div><div class="lo-label">Wacht op orderkoppeling</div></div>
    <div class="lo-kaart"><div class="lo-getal">{{ kpi_wacht_afhandeling|length }}</div><div class="lo-label">Wacht op afhandeling</div></div>
</div>

<a href="/logistiek/orders/nieuw" style="display:inline-block;margin-bottom:20px;font-size:12.5px;font-weight:700;color:#fff;background:var(--brand-600);text-decoration:none;padding:8px 16px;border-radius:6px;">+ Nieuwe order aanmaken</a>

<form method="GET" style="display:flex;gap:8px;margin-bottom:16px;">
    <select name="filter_status" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle statussen</option>
        {% for st in statussen %}<option value="{{ st }}" {% if filter_status == st %}selected{% endif %}>{{ st }}</option>{% endfor %}
    </select>
    <input type="text" name="zoekterm" value="{{ zoekterm }}" placeholder="Zoek op ordernr, leverancier, kenteken" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;width:240px;">
    <button type="submit" style="padding:7px 14px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;background:#fff;cursor:pointer;">Filteren</button>
</form>

{% if getoond %}
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);">
    <div class="lo-tabel-kop">
        <span style="width:120px;">Ordernummer</span>
        <span style="flex:1;">Leverancier</span>
        <span style="width:100px;">Kenteken</span>
        <span style="flex:1;">Materiaal</span>
        <span style="width:100px;text-align:right;">Verw. ton</span>
        <span style="width:100px;text-align:right;">Werk. ton</span>
        <span style="width:160px;">Status</span>
    </div>
    {% for o in getoond %}
    <div class="lo-tabel-rij">
        <span style="width:120px;font-family:var(--font-mono);color:var(--gray-500);"><a href="/logistiek/orders/{{ o.id }}" style="color:var(--brand-600);text-decoration:none;font-weight:600;">{{ o.ordernummer }}</a></span>
        <span style="flex:1;color:var(--gray-700);">{{ o.leverancier or '—' }}</span>
        <span style="width:100px;color:var(--gray-600);">{{ o.kenteken or '—' }}</span>
        <span style="flex:1;color:var(--gray-600);">{{ o.materiaal or '—' }}</span>
        <span style="width:100px;text-align:right;font-family:var(--font-mono);color:var(--gray-500);">{{ o.verwachte_hoeveelheid or '—' }}</span>
        <span style="width:100px;text-align:right;font-family:var(--font-mono);color:var(--gray-600);">{{ o.werkelijke_hoeveelheid or '—' }}</span>
        <span style="width:160px;font-size:11.5px;font-weight:600;color:var(--gray-600);">{{ o.status }}</span>
    </div>
    {% endfor %}
</div>
<div style="padding:10px 4px;font-size:0.8rem;color:var(--gray-400);">{{ getoond|length }} orders</div>
{% else %}
<div class="lege-staat">Nog geen logistieke orders aangemaakt.</div>
{% endif %}
    """
    pagina = render_simple_page("Orders (logistiek)", "logistieke_orders", inhoud)
    return render_template_string(pagina, getoond=getoond, statussen=LOGISTIEKE_ORDER_STATUSSEN,
                                    filter_status=filter_status, zoekterm=zoekterm,
                                    kpi_verwacht_vandaag=kpi_verwacht_vandaag, kpi_aangekomen=kpi_aangekomen,
                                    kpi_volledig_gewogen=kpi_volledig_gewogen, kpi_wacht_uitwegen=kpi_wacht_uitwegen,
                                    kpi_wacht_koppeling=kpi_wacht_koppeling, kpi_wacht_afhandeling=kpi_wacht_afhandeling)

@logistieke_orders_bp.route("/logistiek/orders/nieuw", methods=["GET", "POST"])
def logistieke_order_nieuw():
    _guard = vereist_afdeling_of_403("logistieke_orders")
    if _guard: return _guard

    if request.method == "POST":
        orders = laad_logistieke_orders()
        nu = datetime.datetime.now()
        nieuw = {
            "id": str(uuid.uuid4()),
            "ordernummer": genereer_logistiek_ordernummer(orders),
            "leverancier": request.form.get("leverancier", "").strip(),
            "transporteur": request.form.get("transporteur", "").strip(),
            "kenteken": request.form.get("kenteken", "").strip().upper(),
            "materiaal": request.form.get("materiaal", "").strip(),
            "kwaliteit": request.form.get("kwaliteit", "").strip(),
            "verwachte_hoeveelheid": request.form.get("verwachte_hoeveelheid", "").strip(),
            "werkelijke_hoeveelheid": "",
            "datum": request.form.get("datum", "") or nu.date().isoformat(),
            "verwachte_aankomst": request.form.get("verwachte_aankomst", "").strip(),
            "werkelijke_aankomst": "",
            "gekoppeld_weegbrug_id": "",
            "contract_referentie": "", "prijstype": "", "prijs_per_ton": None, "totale_waarde": None,
            "verantwoordelijke_afdeling": "",
            "status": "Transport verwacht" if request.form.get("verwachte_aankomst","").strip() else "Order aangemaakt",
            "opmerkingen": request.form.get("opmerkingen", "").strip(),
            "aangemaakt_door": session.get("gebruikersnaam", ""),
            "aangemaakt": nu.strftime("%d-%m-%Y %H:%M"),
        }
        orders.append(nieuw)
        bewaar_logistieke_orders(orders)
        return redirect(url_for("logistieke_orders.logistieke_order_detail", order_id=nieuw["id"]))

    leverancier_namen = sorted({b["naam"] for b in ENF_BEDRIJVEN})
    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/logistiek/orders" style="color:var(--gray-400);text-decoration:none;">Orders (logistiek)</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">Nieuw</span>
</div>
<div class="page-title">Nieuwe order aanmaken</div>

<form method="POST" style="max-width:640px;">
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
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Kenteken (indien bekend)</label>
            <input type="text" name="kenteken" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;text-transform:uppercase;font-family:inherit;">
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Verwachte aankomst</label>
            <input type="date" name="verwachte_aankomst" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Materiaal</label>
            <input type="text" name="materiaal" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
        <div>
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Kwaliteit</label>
            <input type="text" name="kwaliteit" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
    </div>
    <div style="margin-bottom:10px;">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Verwachte hoeveelheid (ton)</label>
        <input type="text" name="verwachte_hoeveelheid" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
    </div>
    <div style="margin-bottom:16px;">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Opmerkingen</label>
        <textarea name="opmerkingen" rows="2" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;"></textarea>
    </div>
    <button type="submit" style="padding:9px 20px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">Order aanmaken</button>
    <a href="/logistiek/orders" style="margin-left:10px;font-size:12.5px;color:var(--gray-400);text-decoration:none;">Annuleren</a>
</form>
    """
    pagina = render_simple_page("Nieuwe order", "logistieke_orders", inhoud)
    return render_template_string(pagina, leverancier_namen=leverancier_namen)

@logistieke_orders_bp.route("/logistiek/orders/<order_id>")
def logistieke_order_detail(order_id):
    _guard = vereist_afdeling_of_403("logistieke_orders")
    if _guard: return _guard

    orders = laad_logistieke_orders()
    order = next((o for o in orders if o["id"] == order_id), None)
    if not order:
        pagina = render_simple_page("Niet gevonden", "logistieke_orders", '<div class="page-title">Order niet gevonden</div><div class="lege-staat">Deze order bestaat niet (meer). <a href="/logistiek/orders">Terug naar Orders</a></div>')
        return render_template_string(pagina), 404

    gekoppeld_weegrecord = None
    if order.get("gekoppeld_weegbrug_id"):
        gekoppeld_weegrecord = next((r for r in laad_weegbrug() if r["id"] == order["gekoppeld_weegbrug_id"]), None)

    # Ongekoppelde weegrecords (voor het koppel-formulier)
    ongekoppelde_weegrecords = [r for r in laad_weegbrug() if not r.get("ordernummer","").strip() and r.get("status") != "Geannuleerd"]

    contract_voortgang = None
    if order.get("contract_referentie"):
        gekoppeld_contract = next((h for h in laad_handelsorders() if h.get("contractnummer") == order["contract_referentie"]), None)
        if gekoppeld_contract:
            try:
                totaal_vol = float(str(gekoppeld_contract.get("hoeveelheid_mt","0")).replace(",",""))
            except (ValueError, TypeError):
                totaal_vol = 0.0
            contract_voortgang = {"totaal": round(totaal_vol,1), "geleverd": _contract_geleverd_volume(order["contract_referentie"], orders)}

    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/logistiek/orders" style="color:var(--gray-400);text-decoration:none;">Orders (logistiek)</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">{{ order.ordernummer }}</span>
</div>
<div class="page-title">{{ order.ordernummer }}</div>

<div style="display:flex;gap:24px;flex-wrap:wrap;">
<div style="flex:1;min-width:340px;">
    <div class="dg-kaart" style="margin-bottom:16px;">
        <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Orderstatus</div>
        <form method="POST" action="/logistiek/orders/{{ order.id }}/status">
            <select name="nieuwe_status" onchange="this.form.submit()" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-weight:600;">
                {% for st in statussen %}<option value="{{ st }}" {% if order.status == st %}selected{% endif %}>{{ st }}</option>{% endfor %}
            </select>
        </form>
    </div>

    <div style="background:var(--gray-50);border-radius:8px;padding:14px 16px;margin-bottom:16px;font-size:12.5px;color:var(--gray-600);">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
            <div><b>Leverancier:</b> {{ order.leverancier or '—' }}</div>
            <div><b>Transporteur:</b> {{ order.transporteur or '—' }}</div>
            <div><b>Kenteken:</b> {{ order.kenteken or '—' }}</div>
            <div><b>Materiaal:</b> {{ order.materiaal or '—' }}{% if order.kwaliteit %} ({{ order.kwaliteit }}){% endif %}</div>
            <div><b>Verwachte aankomst:</b> {{ order.verwachte_aankomst or '—' }}</div>
            <div><b>Werkelijke aankomst:</b> {{ order.werkelijke_aankomst or '—' }}</div>
            <div><b>Verwachte hoeveelheid:</b> {{ order.verwachte_hoeveelheid or '—' }} ton</div>
            <div><b>Werkelijke hoeveelheid:</b> {{ order.werkelijke_hoeveelheid or '—' }}{% if order.werkelijke_hoeveelheid %} ton{% endif %}</div>
        </div>
        {% if order.opmerkingen %}<div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--gray-200);"><b>Opmerkingen:</b> {{ order.opmerkingen }}</div>{% endif %}
    </div>

    <div class="dg-kaart" style="margin-bottom:16px;">
        <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Contract / prijs</div>
        {% if order.contract_referentie or order.prijstype %}
        <div style="font-size:12.5px;color:var(--gray-600);">
            <div><b>{{ 'Contract' if order.contract_referentie else 'Type' }}:</b> {{ order.contract_referentie or order.prijstype }}</div>
            {% if order.prijs_per_ton %}<div><b>Prijs per ton:</b> €{{ order.prijs_per_ton }}</div>{% endif %}
            {% if order.totale_waarde %}<div><b>Totale waarde:</b> €{{ "{:,.2f}".format(order.totale_waarde).replace(",", "X").replace(".", ",").replace("X", ".") }}</div>{% endif %}
            {% if order.verantwoordelijke_afdeling %}<div><b>Verantwoordelijk:</b> {{ order.verantwoordelijke_afdeling|capitalize }}</div>{% endif %}
            {% if order.contract_referentie and contract_voortgang %}<div style="margin-top:6px;padding-top:6px;border-top:1px solid var(--gray-200);color:var(--gray-500);">Geleverd onder dit contract (via Live Operaties): {{ contract_voortgang.geleverd }} van {{ contract_voortgang.totaal }} ton</div>{% endif %}
        </div>
        <a href="/logistiek/orders/{{ order.id }}/koppel-contract" style="display:inline-block;margin-top:8px;font-size:11.5px;color:var(--brand-600);text-decoration:none;font-weight:600;">Wijzigen →</a>
        {% else %}
        <div style="font-size:12.5px;color:var(--gray-400);margin-bottom:8px;">Nog geen contract of prijstype gekoppeld.</div>
        <a href="/logistiek/orders/{{ order.id }}/koppel-contract" style="font-size:12.5px;color:var(--brand-600);text-decoration:none;font-weight:600;">Contract koppelen →</a>
        {% endif %}
    </div>

    <div class="dg-kaart" style="margin-bottom:16px;">
        <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Weegbrug-koppeling</div>
        {% if gekoppeld_weegrecord %}
        <div style="font-size:12.5px;color:var(--gray-600);">
            <div><b>Weegnummer:</b> <a href="/weegbrug" style="color:var(--brand-600);text-decoration:none;">{{ gekoppeld_weegrecord.weegnummer }}</a></div>
            <div><b>Bruto:</b> {{ gekoppeld_weegrecord.bruto_gewicht or '—' }} kg</div>
            <div><b>Tarra:</b> {{ gekoppeld_weegrecord.tarra_gewicht or '—' }} kg</div>
            <div><b>Netto:</b> {{ gekoppeld_weegrecord.netto_gewicht or '—' }}{% if gekoppeld_weegrecord.netto_gewicht %} kg ({{ "%.3f"|format(gekoppeld_weegrecord.netto_gewicht|float / 1000) }} ton){% endif %}</div>
            <div><b>Weegstatus:</b> {{ badges[gekoppeld_weegrecord.status].label }}</div>
            {% if gekoppeld_weegrecord.status == "Compleet" %}<div style="margin-top:8px;"><a href="/weegbrug/weegbon/{{ gekoppeld_weegrecord.id }}" target="_blank" style="color:var(--brand-600);text-decoration:none;font-weight:600;">Weegbon bekijken (PDF) →</a></div>{% endif %}
        </div>
        {% else %}
        <div style="font-size:12.5px;color:var(--gray-400);margin-bottom:10px;">Nog geen weegrecord gekoppeld.</div>
        {% if ongekoppelde_weegrecords %}
        <form method="POST" action="/logistiek/orders/{{ order.id }}/koppelen" style="display:flex;gap:6px;">
            <select name="weegbrug_id" style="flex:1;padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
                {% for r in ongekoppelde_weegrecords %}<option value="{{ r.id }}">{{ r.weegnummer }} — {{ r.kenteken }} ({{ r.leverancier or 'onbekend' }})</option>{% endfor %}
            </select>
            <button type="submit" style="padding:7px 12px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;">Koppelen</button>
        </form>
        {% else %}
        <div style="font-size:11.5px;color:var(--gray-300);">Geen ongekoppelde weegrecords beschikbaar. <a href="/weegbrug/inwegen" style="color:var(--brand-600);">Nieuw voertuig inwegen →</a></div>
        {% endif %}
        {% endif %}
    </div>
</div>

<div style="flex:1;min-width:300px;">
    <div class="dg-kaart">
        <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Documenten (CMR, pakbon, etc.)</div>
        <div id="docslijst" style="margin-bottom:8px;font-size:12.5px;color:var(--gray-400);">Laden...</div>
        <input type="file" id="docupload" accept=".pdf,.doc,.docx" style="font-size:12px;">
        <button type="button" onclick="uploadOrderDoc()" style="font-size:11.5px;padding:4px 10px;background:var(--brand-600);color:#fff;border:none;border-radius:5px;cursor:pointer;margin-left:6px;">Uploaden</button>
    </div>
</div>
</div>

<style>.dg-kaart { background:transparent; border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); padding:16px 4px; }</style>
<script>
var ORDERNUMMER = "{{ order.ordernummer }}";
async function laadOrderDocs() {
    var lijstDiv = document.getElementById("docslijst");
    try {
        const res = await fetch("/api/documenten?bedrijf=" + encodeURIComponent(ORDERNUMMER));
        const docs = await res.json();
        if (!docs.length) { lijstDiv.innerHTML = "Nog geen documenten geüpload."; return; }
        lijstDiv.innerHTML = docs.map(function(d) {
            return '<div style="display:flex;justify-content:space-between;align-items:center;padding:4px 0;">' +
                '<a href="/documenten_uploads/' + encodeURIComponent(d.bestandsnaam) + '" target="_blank" style="color:var(--brand-600);text-decoration:none;">' + d.originele_naam + '</a>' +
                '<span style="font-size:11px;color:var(--gray-300);">' + d.timestamp + '</span></div>';
        }).join("");
    } catch (e) { lijstDiv.innerHTML = "Kon documenten niet laden."; }
}
async function uploadOrderDoc() {
    var input = document.getElementById("docupload");
    if (!input.files.length) { alert("Kies eerst een bestand."); return; }
    var form = new FormData();
    form.append("bedrijf", ORDERNUMMER);
    form.append("document", input.files[0]);
    const res = await fetch("/api/documenten", {method: "POST", body: form});
    const data = await res.json();
    if (data.error) { alert(data.error); return; }
    input.value = "";
    laadOrderDocs();
}
laadOrderDocs();
</script>
    """
    pagina = render_simple_page(order["ordernummer"], "logistieke_orders", inhoud)
    return render_template_string(pagina, order=order, statussen=LOGISTIEKE_ORDER_STATUSSEN,
                                    gekoppeld_weegrecord=gekoppeld_weegrecord, ongekoppelde_weegrecords=ongekoppelde_weegrecords,
                                    badges=WEEGBRUG_STATUS_BADGES, contract_voortgang=contract_voortgang)

@logistieke_orders_bp.route("/logistiek/orders/<order_id>/koppelen", methods=["POST"])
def logistieke_order_koppelen(order_id):
    _guard = vereist_afdeling_of_403("logistieke_orders")
    if _guard: return _guard

    orders = laad_logistieke_orders()
    order = next((o for o in orders if o["id"] == order_id), None)
    weegbrug_id = request.form.get("weegbrug_id", "")
    weegrecords = laad_weegbrug()
    weegrecord = next((r for r in weegrecords if r["id"] == weegbrug_id), None)

    if order and weegrecord and not order.get("gekoppeld_weegbrug_id"):
        order["gekoppeld_weegbrug_id"] = weegbrug_id
        order["kenteken"] = order["kenteken"] or weegrecord.get("kenteken", "")
        order["werkelijke_aankomst"] = weegrecord.get("aangemaakt", "").split(" ")[0] if weegrecord.get("aangemaakt") else ""
        if weegrecord.get("netto_gewicht"):
            order["werkelijke_hoeveelheid"] = str(round(float(weegrecord["netto_gewicht"]) / 1000, 3))
        nieuwe_status = _weegbrug_status_naar_orderstatus(weegrecord.get("status", ""))
        order["status"] = nieuwe_status or "Order gekoppeld"
        bewaar_logistieke_orders(orders)

        weegrecord["ordernummer"] = order["ordernummer"]
        bewaar_weegbrug(weegrecords)

    return redirect(url_for("logistieke_orders.logistieke_order_detail", order_id=order_id))

@logistieke_orders_bp.route("/logistiek/orders/<order_id>/status", methods=["POST"])
def logistieke_order_status(order_id):
    _guard = vereist_afdeling_of_403("logistieke_orders")
    if _guard: return _guard

    orders = laad_logistieke_orders()
    order = next((o for o in orders if o["id"] == order_id), None)
    nieuwe_status = request.form.get("nieuwe_status", "")
    if order and nieuwe_status in LOGISTIEKE_ORDER_STATUSSEN:
        order["status"] = nieuwe_status
        bewaar_logistieke_orders(orders)
    return redirect(url_for("logistieke_orders.logistieke_order_detail", order_id=order_id))

@logistieke_orders_bp.route("/logistiek/afhandeling")
def afhandeling_pagina():
    _guard = vereist_afdeling_of_403("afhandeling")
    if _guard: return _guard

    alle_orders = laad_logistieke_orders()
    alle_weegrecords = {r["id"]: r for r in laad_weegbrug()}
    alle_documenten = laad_documenten()

    def gekoppelde_weging(order):
        return alle_weegrecords.get(order.get("gekoppeld_weegbrug_id", ""))

    openstaand = [o for o in alle_orders if o.get("status") in ("Weegbon compleet", "Afhandeling")]
    afwijkend = [o for o in alle_orders if gekoppelde_weging(o) and gekoppelde_weging(o).get("status") == "Probleem"]
    ontbrekende_docs = [o for o in openstaand if not alle_documenten.get(o.get("ordernummer",""), [])]
    klaar_voor_finance = [o for o in alle_orders if o.get("status") == "Klaar voor Finance"]
    afgehandeld = [o for o in alle_orders if o.get("status") in ("Gefactureerd", "Afgerond")]

    inhoud = """
<div class="page-title">Afhandeling</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Vrachten die fysiek zijn afgerond maar administratief nog verwerkt moeten worden — vóórdat ze naar Finance gaan.</p>

<style>
.af-sectie { border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); margin-bottom:18px; }
.af-sectie-kop { padding:12px 16px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); font-size:12.5px; font-weight:700; color:var(--gray-700); display:flex; justify-content:space-between; align-items:center; }
.af-rij { display:flex; align-items:center; padding:9px 16px; border-bottom:1px solid var(--gray-100); font-size:12.5px; }
</style>

<div class="af-sectie">
    <div class="af-sectie-kop"><span>Openstaande afhandelingen</span><span>{{ openstaand|length }}</span></div>
    {% for o in openstaand %}
    <div class="af-rij">
        <span style="flex:1;"><a href="/logistiek/orders/{{ o.id }}" style="color:var(--brand-600);text-decoration:none;font-weight:600;">{{ o.ordernummer }}</a> — {{ o.leverancier or '—' }}</span>
        <span style="width:120px;color:var(--gray-500);">{{ o.werkelijke_hoeveelheid or '—' }}{% if o.werkelijke_hoeveelheid %} ton{% endif %}</span>
        <form method="POST" action="/logistiek/orders/{{ o.id }}/status" style="margin:0;">
            <input type="hidden" name="nieuwe_status" value="Klaar voor Finance">
            <button type="submit" style="font-size:11px;padding:4px 10px;background:var(--brand-600);color:#fff;border:none;border-radius:5px;cursor:pointer;font-weight:600;">Vrijgeven voor Finance</button>
        </form>
    </div>
    {% else %}
    <div class="af-rij" style="color:var(--gray-300);">Niets openstaand — helemaal bij.</div>
    {% endfor %}
</div>

<div class="af-sectie">
    <div class="af-sectie-kop" style="color:#dc2626;"><span>Afwijkende gewichten</span><span>{{ afwijkend|length }}</span></div>
    {% for o in afwijkend %}
    <div class="af-rij"><span style="flex:1;"><a href="/logistiek/orders/{{ o.id }}" style="color:var(--brand-600);text-decoration:none;font-weight:600;">{{ o.ordernummer }}</a> — {{ o.leverancier or '—' }}</span><span style="color:#dc2626;font-weight:600;">Controleer weegrecord</span></div>
    {% else %}
    <div class="af-rij" style="color:var(--gray-300);">Geen afwijkingen.</div>
    {% endfor %}
</div>

<div class="af-sectie">
    <div class="af-sectie-kop"><span>Ontbrekende documenten</span><span>{{ ontbrekende_docs|length }}</span></div>
    {% for o in ontbrekende_docs %}
    <div class="af-rij"><span style="flex:1;"><a href="/logistiek/orders/{{ o.id }}" style="color:var(--brand-600);text-decoration:none;font-weight:600;">{{ o.ordernummer }}</a> — {{ o.leverancier or '—' }}</span><span style="color:var(--gray-400);">Nog geen documenten geüpload</span></div>
    {% else %}
    <div class="af-rij" style="color:var(--gray-300);">Alle openstaande orders hebben documenten.</div>
    {% endfor %}
</div>

<div class="af-sectie">
    <div class="af-sectie-kop" style="color:var(--brand-600);"><span>Klaar voor Finance</span><span>{{ klaar_voor_finance|length }}</span></div>
    {% for o in klaar_voor_finance %}
    <div class="af-rij"><span style="flex:1;"><a href="/logistiek/orders/{{ o.id }}" style="color:var(--brand-600);text-decoration:none;font-weight:600;">{{ o.ordernummer }}</a> — {{ o.leverancier or '—' }}</span><span style="color:var(--gray-500);">{{ o.werkelijke_hoeveelheid or '—' }}{% if o.werkelijke_hoeveelheid %} ton{% endif %}</span></div>
    {% else %}
    <div class="af-rij" style="color:var(--gray-300);">Nog niets vrijgegeven.</div>
    {% endfor %}
</div>

<div class="af-sectie">
    <div class="af-sectie-kop" style="color:var(--gray-400);"><span>Reeds afgehandeld</span><span>{{ afgehandeld|length }}</span></div>
    {% for o in afgehandeld[:10] %}
    <div class="af-rij"><span style="flex:1;color:var(--gray-500);"><a href="/logistiek/orders/{{ o.id }}" style="color:var(--gray-500);text-decoration:none;">{{ o.ordernummer }}</a> — {{ o.leverancier or '—' }}</span><span style="color:var(--gray-400);">{{ o.status }}</span></div>
    {% else %}
    <div class="af-rij" style="color:var(--gray-300);">Nog geen afgeronde orders.</div>
    {% endfor %}
</div>
    """
    pagina = render_simple_page("Afhandeling", "afhandeling", inhoud)
    return render_template_string(pagina, openstaand=openstaand, afwijkend=afwijkend,
                                    ontbrekende_docs=ontbrekende_docs, klaar_voor_finance=klaar_voor_finance,
                                    afgehandeld=afgehandeld)

@logistieke_orders_bp.route("/live-operations")
def live_operations_pagina():
    _guard = vereist_afdeling_of_403("live_operations")
    if _guard: return _guard

    alle_orders = laad_logistieke_orders()
    alle_weegrecords = laad_weegbrug()
    weegrecords_lookup = {r["id"]: r for r in alle_weegrecords}

    # --- Eén rij per vracht: order als basis, aangevuld met weegbrug-data indien gekoppeld.
    # Voor weegrecords die nog GEEN order hebben, tonen we die ook als losse rij
    # (anders zou een net ingewogen, nog niet gekoppelde vracht onzichtbaar blijven). ---
    rijen = []
    for o in alle_orders:
        weging = weegrecords_lookup.get(o.get("gekoppeld_weegbrug_id", ""))
        rijen.append({
            "type": "order", "id": o["id"], "referentie": o["ordernummer"],
            "datum": o.get("datum",""), "leverancier": o.get("leverancier",""),
            "transporteur": o.get("transporteur",""),
            "kenteken": weging.get("kenteken","") if weging else o.get("kenteken",""),
            "materiaal": o.get("materiaal",""), "status": o.get("status",""),
            "herkomst": weging.get("herkomst","") if weging else "",
            "bestemming": weging.get("bestemming","") if weging else "",
            "contract_referentie": o.get("contract_referentie",""), "prijstype": o.get("prijstype",""),
        })
    gekoppelde_weeg_ids = {o.get("gekoppeld_weegbrug_id") for o in alle_orders if o.get("gekoppeld_weegbrug_id")}
    for r in alle_weegrecords:
        if r["id"] in gekoppelde_weeg_ids or r.get("status") == "Geannuleerd":
            continue
        rijen.append({
            "type": "weegbrug", "id": r["id"], "referentie": r["weegnummer"],
            "datum": r.get("aangemaakt","").split(" ")[0] if r.get("aangemaakt") else "",
            "leverancier": r.get("leverancier",""), "transporteur": r.get("transporteur",""),
            "kenteken": r.get("kenteken",""), "materiaal": r.get("materiaal",""),
            "status": "Ingewogen (geen order)" if r.get("status")=="Ingewogen" else r.get("status",""),
            "herkomst": r.get("herkomst",""), "bestemming": r.get("bestemming",""),
        })

    # --- Filters ---
    f_datum = request.args.get("datum", "")
    f_leverancier = request.args.get("leverancier", "").strip().lower()
    f_transporteur = request.args.get("transporteur", "").strip().lower()
    f_kenteken = request.args.get("kenteken", "").strip().lower()
    f_materiaal = request.args.get("materiaal", "").strip().lower()
    f_ordernummer = request.args.get("ordernummer", "").strip().lower()
    f_status = request.args.get("status", "")
    f_herkomst = request.args.get("herkomst", "").strip().lower()
    f_bestemming = request.args.get("bestemming", "").strip().lower()

    getoond = rijen
    if f_datum: getoond = [r for r in getoond if r["datum"] == f_datum]
    if f_leverancier: getoond = [r for r in getoond if f_leverancier in r["leverancier"].lower()]
    if f_transporteur: getoond = [r for r in getoond if f_transporteur in r["transporteur"].lower()]
    if f_kenteken: getoond = [r for r in getoond if f_kenteken in r["kenteken"].lower()]
    if f_materiaal: getoond = [r for r in getoond if f_materiaal in r["materiaal"].lower()]
    if f_ordernummer: getoond = [r for r in getoond if f_ordernummer in r["referentie"].lower()]
    if f_status: getoond = [r for r in getoond if r["status"] == f_status]
    if f_herkomst: getoond = [r for r in getoond if f_herkomst in r["herkomst"].lower()]
    if f_bestemming: getoond = [r for r in getoond if f_bestemming in r["bestemming"].lower()]
    getoond = sorted(getoond, key=lambda r: r["datum"], reverse=True)

    # --- Statustabel, precies zoals gevraagd: Onderweg/Aangekomen/Op weegbrug/
    # Ingewogen/Wachten op uitwegen/Volledig afgerond. Alleen o.b.v. data die we
    # daadwerkelijk bijhouden — geen extra granulariteit verzonnen. ---
    kpi_onderweg = len([r for r in rijen if r["status"] == "Transport verwacht"])
    kpi_aangekomen = len([r for r in rijen if r["status"] == "Truck aangekomen"])
    kpi_ingewogen = len([r for r in rijen if r["status"] in ("Ingewogen", "Ingewogen (geen order)")])
    kpi_afgerond = len([r for r in rijen if r["status"] == "Afgerond"])

    alle_statussen_voor_filter = sorted({r["status"] for r in rijen})

    inhoud = """
<div class="page-title">Live Operations</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Control tower: alle inkomende vrachten in één overzicht — Weegbrug en Orders gecombineerd.</p>

<style>
.lv-statustabel { width:100%; max-width:520px; border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); margin-bottom:24px; }
.lv-statusrij { display:flex; justify-content:space-between; padding:10px 16px; border-bottom:1px solid var(--gray-100); font-size:13px; }
.lv-tabel-kop { display:flex; align-items:center; padding:10px 16px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); font-size:10px; letter-spacing:0.08em; text-transform:uppercase; color:#7d8792; }
.lv-tabel-rij { display:flex; align-items:center; padding:9px 16px; border-bottom:1px solid var(--gray-100); font-size:12px; }
</style>

<div class="lv-statustabel">
    <div class="lv-statusrij"><span>Onderweg (transport verwacht)</span><b>{{ kpi_onderweg }}</b></div>
    <div class="lv-statusrij"><span>Aangekomen</span><b>{{ kpi_aangekomen }}</b></div>
    <div class="lv-statusrij"><span>Ingewogen / wachten op uitwegen</span><b>{{ kpi_ingewogen }}</b></div>
    <div class="lv-statusrij" style="border-bottom:none;"><span>Volledig afgerond</span><b>{{ kpi_afgerond }}</b></div>
</div>

<form method="GET" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px;">
    <input type="date" name="datum" value="{{ f_datum }}" style="padding:6px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:11.5px;">
    <input type="text" name="leverancier" value="{{ f_leverancier }}" placeholder="Leverancier" style="padding:6px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:11.5px;font-family:inherit;width:110px;">
    <input type="text" name="transporteur" value="{{ f_transporteur }}" placeholder="Transporteur" style="padding:6px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:11.5px;font-family:inherit;width:110px;">
    <input type="text" name="kenteken" value="{{ f_kenteken }}" placeholder="Kenteken" style="padding:6px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:11.5px;font-family:inherit;width:90px;">
    <input type="text" name="materiaal" value="{{ f_materiaal }}" placeholder="Materiaal" style="padding:6px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:11.5px;font-family:inherit;width:100px;">
    <input type="text" name="ordernummer" value="{{ f_ordernummer }}" placeholder="Ordernr." style="padding:6px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:11.5px;font-family:inherit;width:100px;">
    <select name="status" style="padding:6px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:11.5px;">
        <option value="">Alle statussen</option>
        {% for st in alle_statussen_voor_filter %}<option value="{{ st }}" {% if f_status == st %}selected{% endif %}>{{ st }}</option>{% endfor %}
    </select>
    <input type="text" name="herkomst" value="{{ f_herkomst }}" placeholder="Herkomst" style="padding:6px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:11.5px;font-family:inherit;width:100px;">
    <input type="text" name="bestemming" value="{{ f_bestemming }}" placeholder="Bestemming" style="padding:6px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:11.5px;font-family:inherit;width:100px;">
    <button type="submit" style="padding:6px 14px;border:1px solid var(--gray-200);border-radius:6px;font-size:11.5px;background:#fff;cursor:pointer;">Filteren</button>
</form>

{% if getoond %}
<div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);">
    <div class="lv-tabel-kop">
        <span style="width:90px;">Datum</span>
        <span style="width:110px;">Referentie</span>
        <span style="flex:1;">Leverancier</span>
        <span style="width:90px;">Kenteken</span>
        <span style="flex:1;">Materiaal</span>
        <span style="width:160px;">Status</span>
        <span style="width:130px;">Contract</span>
    </div>
    {% for r in getoond %}
    <div class="lv-tabel-rij">
        <span style="width:90px;color:var(--gray-500);">{{ r.datum or '—' }}</span>
        <span style="width:110px;font-family:var(--font-mono);">
            {% if r.type == "order" %}<a href="/logistiek/orders/{{ r.id }}" style="color:var(--brand-600);text-decoration:none;font-weight:600;">{{ r.referentie }}</a>
            {% else %}<span style="color:var(--gray-500);">{{ r.referentie }}</span>{% endif %}
        </span>
        <span style="flex:1;color:var(--gray-700);">{{ r.leverancier or '—' }}</span>
        <span style="width:90px;color:var(--gray-600);">{{ r.kenteken or '—' }}</span>
        <span style="flex:1;color:var(--gray-600);">{{ r.materiaal or '—' }}</span>
        <span style="width:160px;font-size:11px;font-weight:600;color:var(--gray-600);">{{ r.status }}</span>
        <span style="width:130px;">
            {% if r.type == "order" %}
                {% if r.contract_referentie %}<span style="font-size:11px;color:var(--gray-600);">{{ r.contract_referentie }}</span>
                {% elif r.prijstype %}<span style="font-size:11px;color:var(--gray-500);">{{ r.prijstype }}</span>
                {% else %}<a href="/logistiek/orders/{{ r.id }}/koppel-contract" style="font-size:11px;color:var(--brand-600);text-decoration:none;font-weight:600;">Contract koppelen</a>{% endif %}
            {% endif %}
        </span>
    </div>
    {% endfor %}
</div>
<div style="padding:10px 4px;font-size:0.8rem;color:var(--gray-400);">{{ getoond|length }} vrachten</div>
{% else %}
<div class="lege-staat">Geen vrachten gevonden voor deze filters.</div>
{% endif %}
    """
    pagina = render_simple_page("Live Operations", "live_operations", inhoud)
    return render_template_string(pagina, getoond=getoond, kpi_onderweg=kpi_onderweg, kpi_aangekomen=kpi_aangekomen,
                                    kpi_ingewogen=kpi_ingewogen, kpi_afgerond=kpi_afgerond,
                                    alle_statussen_voor_filter=alle_statussen_voor_filter,
                                    f_datum=f_datum, f_leverancier=f_leverancier, f_transporteur=f_transporteur,
                                    f_kenteken=f_kenteken, f_materiaal=f_materiaal, f_ordernummer=f_ordernummer,
                                    f_status=f_status, f_herkomst=f_herkomst, f_bestemming=f_bestemming)

@logistieke_orders_bp.route("/inzichten/logistiek")
def logistieke_inzichten_pagina():
    """Logistieke Inzichten — alleen met echt berekenbare data. Bewust NIET gebouwd:
    'materialen die tekort dreigen te komen' (geen minimum-voorraadniveau vastgelegd),
    'percentage volledig geladen trucks' (geen laadcapaciteit-referentie), en
    'kosten door wachttijd' (geen wachttijd-tracking + tarief). Die vragen eerst
    nieuwe datavelden vóór ze zinvol gebouwd kunnen worden."""
    _guard = vereist_afdeling_of_403("inzichten_logistiek")
    if _guard: return _guard

    _vandaag = datetime.date.today()
    voorraad_status = bereken_voorraad_status()
    alle_verkooporders = laad_orders()
    alle_logistieke_orders = laad_logistieke_orders()
    alle_shipments = laad_shipments()
    alle_weegrecords = laad_weegbrug()

    # --- Beschikbaar volume nu + verwacht binnenkomend (7/14/30 dagen) ---
    def _binnenkomend_binnen(dagen):
        grens = (_vandaag + datetime.timedelta(days=dagen)).isoformat()
        result = {}
        for o in alle_logistieke_orders:
            verwacht = o.get("verwachte_aankomst", "")
            if verwacht and _vandaag.isoformat() <= verwacht <= grens and o.get("status") not in ("Afgerond", "Gefactureerd"):
                mat = o.get("materiaal", "Onbekend")
                result[mat] = result.get(mat, 0) + parse_hoeveelheid_getal(o.get("verwachte_hoeveelheid",""))
        return result

    binnenkomend_7d = _binnenkomend_binnen(7)
    binnenkomend_14d = _binnenkomend_binnen(14)
    binnenkomend_30d = _binnenkomend_binnen(30)
    alle_materialen_volume = sorted(set(voorraad_status["fysiek_per_materiaal"].keys()) | set(binnenkomend_30d.keys()))
    volume_overzicht = [{
        "materiaal": m,
        "nu": round(voorraad_status["fysiek_per_materiaal"].get(m, 0), 1),
        "d7": round(binnenkomend_7d.get(m, 0), 1),
        "d14": round(binnenkomend_14d.get(m, 0), 1),
        "d30": round(binnenkomend_30d.get(m, 0), 1),
    } for m in alle_materialen_volume]

    # --- Klanten die binnenkort volume nodig hebben (open verkooporders, verwachte_datum binnen 14 dagen) ---
    _grens_klant = (_vandaag + datetime.timedelta(days=14)).isoformat()
    klanten_binnenkort = sorted(
        [o for o in alle_verkooporders if o.get("status") in ("Open", "Onderhandeling") and o.get("verwachte_datum","") and _vandaag.isoformat() <= o["verwachte_datum"] <= _grens_klant],
        key=lambda o: o.get("verwachte_datum","")
    )

    # --- Openstaande orders vs. beschikbaar volume (per materiaal) ---
    open_vraag_per_materiaal = {}
    for o in alle_verkooporders:
        if o.get("status") in ("Open", "Onderhandeling"):
            mat = o.get("materiaal", "Onbekend")
            open_vraag_per_materiaal[mat] = open_vraag_per_materiaal.get(mat, 0) + parse_hoeveelheid_getal(o.get("hoeveelheid",""))
    vraag_vs_aanbod = []
    for m in sorted(set(open_vraag_per_materiaal.keys()) | set(voorraad_status["fysiek_per_materiaal"].keys())):
        aanbod = voorraad_status["fysiek_per_materiaal"].get(m, 0) + binnenkomend_30d.get(m, 0)
        vraag = open_vraag_per_materiaal.get(m, 0)
        vraag_vs_aanbod.append({"materiaal": m, "vraag": round(vraag,1), "aanbod": round(aanbod,1), "tekort": round(vraag - aanbod, 1) if vraag > aanbod else 0})

    # --- Leveranciers-volumetrend (laatste 30 dagen vs. de 30 dagen daarvoor) ---
    _30d_geleden = (_vandaag - datetime.timedelta(days=30)).isoformat()
    _60d_geleden = (_vandaag - datetime.timedelta(days=60)).isoformat()
    def _weegdatum(r):
        return r.get("aangemaakt","").split(" ")[0] if r.get("aangemaakt") else ""
    def _weeg_iso(r):
        d = _weegdatum(r)
        try:
            return datetime.datetime.strptime(d, "%d-%m-%Y").date().isoformat()
        except (ValueError, TypeError):
            return ""
    per_leverancier_recent = {}
    per_leverancier_vorige = {}
    for r in alle_weegrecords:
        if r.get("status") != "Compleet" or not r.get("leverancier"):
            continue
        d_iso = _weeg_iso(r)
        netto = parse_hoeveelheid_getal(r.get("netto_gewicht","")) / 1000
        if d_iso >= _30d_geleden:
            per_leverancier_recent[r["leverancier"]] = per_leverancier_recent.get(r["leverancier"], 0) + netto
        elif d_iso >= _60d_geleden:
            per_leverancier_vorige[r["leverancier"]] = per_leverancier_vorige.get(r["leverancier"], 0) + netto
    leverancier_trend = []
    for lev in sorted(set(per_leverancier_recent.keys()) | set(per_leverancier_vorige.keys())):
        recent = per_leverancier_recent.get(lev, 0)
        vorige = per_leverancier_vorige.get(lev, 0)
        verschil_pct = round((recent - vorige) / vorige * 100, 1) if vorige > 0 else None
        leverancier_trend.append({"leverancier": lev, "recent": round(recent,1), "vorige": round(vorige,1), "verschil_pct": verschil_pct})
    leverancier_trend.sort(key=lambda x: (x["verschil_pct"] is None, -(x["verschil_pct"] or 0)))

    # --- Transportkosten: per ton, per route (land->land), hoogste kosten ---
    shipments_met_kosten = [s for s in alle_shipments if s.get("transportkosten") and s.get("werkelijk_hoeveelheid")]
    totaal_kosten = sum(parse_hoeveelheid_getal(s["transportkosten"]) for s in shipments_met_kosten)
    totaal_ton_kosten = sum(parse_hoeveelheid_getal(s["werkelijk_hoeveelheid"]) for s in shipments_met_kosten)
    kosten_per_ton_gemiddeld = round(totaal_kosten / totaal_ton_kosten, 2) if totaal_ton_kosten > 0 else None

    per_route = {}
    for s in shipments_met_kosten:
        route = f"{s.get('origin_land','?')} → {s.get('destination_land','?')}"
        per_route.setdefault(route, {"kosten": 0, "ton": 0})
        per_route[route]["kosten"] += parse_hoeveelheid_getal(s["transportkosten"])
        per_route[route]["ton"] += parse_hoeveelheid_getal(s["werkelijk_hoeveelheid"])
    route_overzicht = sorted(
        [{"route": r, "totaal_kosten": round(v["kosten"],2), "kosten_per_ton": round(v["kosten"]/v["ton"],2) if v["ton"]>0 else None} for r, v in per_route.items()],
        key=lambda x: -x["totaal_kosten"]
    )[:10]

    # --- Vertraagde inkomende orders (verwachte_aankomst verstreken, nog niet gekoppeld/uitgewogen) ---
    vertraagde_inkomend = [
        o for o in alle_logistieke_orders
        if o.get("verwachte_aankomst","") and o["verwachte_aankomst"] < _vandaag.isoformat()
        and o.get("status") in ("Order aangemaakt", "Transport verwacht", "Truck aangekomen")
    ]

    inhoud = """
<div class="page-title">Logistieke Inzichten</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Operationele rapportages voor Logistiek — voorraad, vraag/aanbod, transportkosten.</p>

<style>
.li-sectie { border:none; border-top:1px solid var(--gray-200); border-bottom:1px solid var(--gray-200); margin-bottom:24px; }
.li-kop { padding:12px 16px; background:var(--gray-50); border-bottom:1px solid var(--gray-200); font-size:12.5px; font-weight:700; color:var(--gray-700); }
.li-rij { display:flex; align-items:center; padding:9px 16px; border-bottom:1px solid var(--gray-100); font-size:12.5px; }
</style>

<div class="li-sectie">
    <div class="li-kop">Beschikbaar volume — nu en verwacht binnenkomend</div>
    {% for v in volume_overzicht %}
    <div class="li-rij">
        <span style="flex:1;font-weight:600;color:var(--gray-800);">{{ v.materiaal }}</span>
        <span style="width:90px;text-align:right;">Nu: <b>{{ v.nu }}t</b></span>
        <span style="width:100px;text-align:right;color:var(--gray-500);">+7d: {{ v.d7 }}t</span>
        <span style="width:100px;text-align:right;color:var(--gray-500);">+14d: {{ v.d14 }}t</span>
        <span style="width:100px;text-align:right;color:var(--gray-500);">+30d: {{ v.d30 }}t</span>
    </div>
    {% else %}
    <div class="li-rij" style="color:var(--gray-300);">Geen voorraad- of orderdata.</div>
    {% endfor %}
</div>

<div class="li-sectie">
    <div class="li-kop">Openstaande vraag vs. beschikbaar aanbod (incl. binnenkomend)</div>
    {% for v in vraag_vs_aanbod %}
    <div class="li-rij">
        <span style="flex:1;font-weight:600;color:var(--gray-800);">{{ v.materiaal }}</span>
        <span style="width:100px;text-align:right;color:var(--gray-500);">Vraag: {{ v.vraag }}t</span>
        <span style="width:100px;text-align:right;color:var(--gray-500);">Aanbod: {{ v.aanbod }}t</span>
        {% if v.tekort > 0 %}<span style="width:110px;text-align:right;color:#dc2626;font-weight:700;">Tekort: {{ v.tekort }}t</span>{% else %}<span style="width:110px;text-align:right;color:#16a34a;">Voldoende</span>{% endif %}
    </div>
    {% else %}
    <div class="li-rij" style="color:var(--gray-300);">Geen data.</div>
    {% endfor %}
</div>

<div class="li-sectie">
    <div class="li-kop">Klanten die binnenkort volume nodig hebben (komende 14 dagen)</div>
    {% for o in klanten_binnenkort %}
    <div class="li-rij">
        <span style="flex:1;color:var(--gray-700);">{{ o.bedrijf }}</span>
        <span style="width:100px;color:var(--gray-500);">{{ o.materiaal }}</span>
        <span style="width:90px;text-align:right;color:var(--gray-500);">{{ o.hoeveelheid }}</span>
        <span style="width:100px;text-align:right;color:var(--gray-600);">{{ o.verwachte_datum }}</span>
    </div>
    {% else %}
    <div class="li-rij" style="color:var(--gray-300);">Geen openstaande orders met verwachte datum binnen 14 dagen.</div>
    {% endfor %}
</div>

<div class="li-sectie">
    <div class="li-kop">Leveranciers-volumetrend (laatste 30 dagen t.o.v. de 30 dagen daarvoor)</div>
    {% for l in leverancier_trend %}
    <div class="li-rij">
        <span style="flex:1;color:var(--gray-700);">{{ l.leverancier }}</span>
        <span style="width:90px;text-align:right;color:var(--gray-500);">{{ l.recent }}t</span>
        {% if l.verschil_pct is not none %}<span style="width:90px;text-align:right;font-weight:700;color:{{ '#16a34a' if l.verschil_pct >= 0 else '#dc2626' }};">{{ '+' if l.verschil_pct >= 0 else '' }}{{ l.verschil_pct }}%</span>{% else %}<span style="width:90px;text-align:right;color:var(--gray-300);">nieuw</span>{% endif %}
    </div>
    {% else %}
    <div class="li-rij" style="color:var(--gray-300);">Geen weegdata beschikbaar.</div>
    {% endfor %}
</div>

<div class="li-sectie">
    <div class="li-kop">Transportkosten {% if kosten_per_ton_gemiddeld %}— gemiddeld €{{ kosten_per_ton_gemiddeld }}/ton{% endif %}</div>
    {% for r in route_overzicht %}
    <div class="li-rij">
        <span style="flex:1;color:var(--gray-700);">{{ r.route }}</span>
        <span style="width:120px;text-align:right;color:var(--gray-500);">€{{ "{:,.0f}".format(r.totaal_kosten) }} totaal</span>
        <span style="width:120px;text-align:right;color:var(--gray-600);">{% if r.kosten_per_ton %}€{{ r.kosten_per_ton }}/ton{% else %}—{% endif %}</span>
    </div>
    {% else %}
    <div class="li-rij" style="color:var(--gray-300);">Geen shipments met ingevulde transportkosten.</div>
    {% endfor %}
</div>

{% if vertraagde_inkomend %}
<div class="li-sectie">
    <div class="li-kop" style="color:#dc2626;">Vertraagde inkomende orders ({{ vertraagde_inkomend|length }})</div>
    {% for o in vertraagde_inkomend %}
    <div class="li-rij"><a href="/logistiek/orders/{{ o.id }}" style="flex:1;color:var(--brand-600);text-decoration:none;font-weight:600;">{{ o.ordernummer }}</a><span style="color:var(--gray-500);">{{ o.leverancier or '—' }}</span><span style="width:110px;text-align:right;color:#dc2626;">Verwacht: {{ o.verwachte_aankomst }}</span></div>
    {% endfor %}
</div>
{% endif %}
    """
    pagina = render_simple_page("Logistieke Inzichten", "inzichten_logistiek", inhoud)
    return render_template_string(pagina, volume_overzicht=volume_overzicht, vraag_vs_aanbod=vraag_vs_aanbod,
                                    klanten_binnenkort=klanten_binnenkort, leverancier_trend=leverancier_trend,
                                    route_overzicht=route_overzicht, kosten_per_ton_gemiddeld=kosten_per_ton_gemiddeld,
                                    vertraagde_inkomend=vertraagde_inkomend)

def _contract_geleverd_volume(contract_referentie, alle_orders=None):
    """Som van werkelijke_hoeveelheid van alle logistieke orders die aan dit contract
    gekoppeld zijn EN daadwerkelijk afgerond/gefactureerd zijn (dus echt geleverd,
    niet alleen gepland)."""
    if alle_orders is None:
        alle_orders = laad_logistieke_orders()
    geleverd = sum(
        parse_hoeveelheid_getal(o.get("werkelijke_hoeveelheid",""))
        for o in alle_orders
        if o.get("contract_referentie") == contract_referentie and o.get("status") in ("Weegbon compleet", "Afhandeling", "Klaar voor Finance", "Gefactureerd", "Afgerond")
    )
    return round(geleverd, 3)

@logistieke_orders_bp.route("/logistiek/orders/<order_id>/koppel-contract", methods=["GET", "POST"])
def logistieke_order_koppel_contract(order_id):
    """Koppelt een weging (via de logistieke order) aan een inkoopcontract dat de
    accountmanager heeft aangemaakt en goedgekeurd (Handelsorders, type inkoop, status
    Definitief — een Concept telt niet als een echt contract). Geldt alleen voor
    vrachtwagen-transport (deze hele module is weegbrug-gebaseerd, dus dat klopt vanzelf).

    FIFO: het oudste passende contract staat bovenaan, zodat je eerst het langst
    openstaande contract afhandelt vóór een nieuwer."""
    _guard = vereist_afdeling_of_403("live_operations")
    if _guard: return _guard

    orders = laad_logistieke_orders()
    order = next((o for o in orders if o["id"] == order_id), None)
    if not order:
        pagina = render_simple_page("Niet gevonden", "live_operations", '<div class="page-title">Order niet gevonden</div><div class="lege-staat">Deze order bestaat niet (meer). <a href="/live-operations">Terug naar Live Operaties</a></div>')
        return render_template_string(pagina), 404

    alle_handelsorders = [
        h for h in laad_handelsorders()
        if h.get("order_type") == "inkoop" and h.get("status") == "Definitief"
    ]
    # FIFO: oudste eerst (op aanmaakdatum/-tijd, "%d-%m-%Y %H:%M").
    def _aangemaakt_sorteersleutel(h):
        try:
            return datetime.datetime.strptime(h.get("aangemaakt",""), "%d-%m-%Y %H:%M")
        except (ValueError, TypeError):
            return datetime.datetime.max
    alle_handelsorders.sort(key=_aangemaakt_sorteersleutel)

    passende_contracten = [h for h in alle_handelsorders if h.get("materiaal","") == order.get("materiaal","") and h.get("tegenpartij_naam","") == order.get("leverancier","")]
    overige_contracten = [h for h in alle_handelsorders if h not in passende_contracten]

    if request.method == "POST":
        keuze = request.form.get("contract_keuze", "")
        verantwoordelijke_afdeling = request.form.get("verantwoordelijke_afdeling", "")

        if keuze == "spot":
            marktprijzen_materiaal = sorted(
                [p for p in laad_marktprijzen() if p.get("materiaal","") == order.get("materiaal","")],
                key=lambda p: p.get("datum",""), reverse=True
            )
            dagprijs = marktprijzen_materiaal[0]["prijs_per_ton"] if marktprijzen_materiaal else None
            order["contract_referentie"] = ""
            order["prijstype"] = "Spot (dagprijs)"
            order["prijs_per_ton"] = dagprijs
        else:
            gekozen_contract = next((h for h in alle_handelsorders if h["id"] == keuze), None)
            if gekozen_contract:
                order["contract_referentie"] = gekozen_contract["contractnummer"]
                order["prijstype"] = "Contract"
                try:
                    order["prijs_per_ton"] = float(str(gekozen_contract.get("prijs","0")).replace(",","."))
                except (ValueError, TypeError):
                    order["prijs_per_ton"] = None

        if order.get("werkelijke_hoeveelheid") and order.get("prijs_per_ton"):
            try:
                order["totale_waarde"] = round(float(order["werkelijke_hoeveelheid"]) * float(order["prijs_per_ton"]), 2)
            except (ValueError, TypeError):
                order["totale_waarde"] = None

        order["verantwoordelijke_afdeling"] = verantwoordelijke_afdeling if verantwoordelijke_afdeling in ("finance", "logistiek", "backoffice") else order.get("verantwoordelijke_afdeling","")
        bewaar_logistieke_orders(orders)
        return redirect(url_for("logistieke_orders.logistieke_order_detail", order_id=order_id))

    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/logistiek/orders/{{ order.id }}" style="color:var(--gray-400);text-decoration:none;">{{ order.ordernummer }}</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">Contract koppelen</span>
</div>
<div class="page-title">Contract koppelen — {{ order.ordernummer }}</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">{{ order.leverancier }} — {{ order.materiaal }}. Koppel een goedgekeurd inkoopcontract (prijs komt automatisch mee) of markeer als spot-transactie (dagprijs). Oudste contract staat bovenaan (FIFO).</p>

<form method="POST" style="max-width:520px;">
    <div style="margin-bottom:16px;">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;display:block;margin-bottom:6px;">
            <input type="radio" name="contract_keuze" value="spot" checked onchange="document.getElementById('contract_select').disabled=true;"> Spot-transactie (dagprijs uit marktprijzen)
        </label>
        {% if passende_contracten %}
        <div style="font-size:11px;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin:12px 0 4px 0;">Passende contracten (zelfde materiaal + leverancier) — oudste eerst</div>
        {% for c in passende_contracten %}
        <label style="font-size:12.5px;color:var(--gray-700);display:block;margin-bottom:6px;">
            <input type="radio" name="contract_keuze" value="{{ c.id }}" onchange="document.getElementById('contract_select').disabled=true;"> {{ c.contractnummer }} — {{ c.hoeveelheid_mt or '—' }} MT{% if c.prijs %} à €{{ c.prijs }}/MT{% endif %} <span style="color:var(--gray-400);">({{ c.aangemaakt }})</span>
        </label>
        {% endfor %}
        {% endif %}
        {% if overige_contracten %}
        <div style="font-size:11px;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin:12px 0 4px 0;">Overige goedgekeurde contracten</div>
        <select id="contract_select" name="contract_keuze" onchange="document.querySelectorAll('input[name=contract_keuze][type=radio]').forEach(function(r){r.checked=false;});" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
            <option value="">— geen —</option>
            {% for c in overige_contracten %}<option value="{{ c.id }}">{{ c.contractnummer }} — {{ c.tegenpartij_naam }} ({{ c.materiaal }}, {{ c.hoeveelheid_mt or '—' }} MT{% if c.prijs %}, €{{ c.prijs }}/MT{% endif %})</option>{% endfor %}
        </select>
        {% endif %}
        {% if not passende_contracten and not overige_contracten %}
        <div style="font-size:12px;color:var(--gray-300);margin-top:8px;">Nog geen goedgekeurde (Definitieve) inkoopcontracten beschikbaar.</div>
        {% endif %}
    </div>
    <div style="margin-bottom:18px;">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Verantwoordelijke afdeling</label>
        <select name="verantwoordelijke_afdeling" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
            <option value="">— geen specifieke afdeling —</option>
            <option value="backoffice" {% if order.verantwoordelijke_afdeling == "backoffice" %}selected{% endif %}>Backoffice</option>
            <option value="logistiek" {% if order.verantwoordelijke_afdeling == "logistiek" %}selected{% endif %}>Logistiek</option>
            <option value="finance" {% if order.verantwoordelijke_afdeling == "finance" %}selected{% endif %}>Finance</option>
        </select>
    </div>
    <button type="submit" style="padding:9px 20px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">Koppelen</button>
    <a href="/logistiek/orders/{{ order.id }}" style="margin-left:10px;font-size:12.5px;color:var(--gray-400);text-decoration:none;">Annuleren</a>
</form>
    """
    pagina = render_simple_page("Contract koppelen", "live_operations", inhoud)
    return render_template_string(pagina, order=order, passende_contracten=passende_contracten, overige_contracten=overige_contracten)