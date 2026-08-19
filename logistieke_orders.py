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
    laad_documenten,
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
        <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Weegbrug-koppeling</div>
        {% if gekoppeld_weegrecord %}
        <div style="font-size:12.5px;color:var(--gray-600);">
            <div><b>Weegnummer:</b> <a href="/weegbrug" style="color:var(--brand-600);text-decoration:none;">{{ gekoppeld_weegrecord.weegnummer }}</a></div>
            <div><b>Bruto:</b> {{ gekoppeld_weegrecord.bruto_gewicht or '—' }} kg</div>
            <div><b>Tarra:</b> {{ gekoppeld_weegrecord.tarra_gewicht or '—' }} kg</div>
            <div><b>Netto:</b> {{ gekoppeld_weegrecord.netto_gewicht or '—' }}{% if gekoppeld_weegrecord.netto_gewicht %} kg ({{ "%.3f"|format(gekoppeld_weegrecord.netto_gewicht|float / 1000) }} ton){% endif %}</div>
            <div><b>Weegstatus:</b> {{ badges[gekoppeld_weegrecord.status].bol }} {{ badges[gekoppeld_weegrecord.status].label }}</div>
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
                                    badges=WEEGBRUG_STATUS_BADGES)

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