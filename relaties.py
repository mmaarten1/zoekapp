"""
relaties.py — Blueprint voor de Klanten- en Leveranciers-modules.

Beide pagina's tonen een subset van de hoofddatabron (ENF_BEDRIJVEN resp.
PAPIERFABRIEKEN) — alleen bedrijven met een toegekende status of
accountmanager — met zoeken/filteren/sorteren. Samengevoegd in één bestand
omdat ze functioneel vrijwel identiek zijn (zelfde UI-patroon, ander filter).

Registratie in app.py met: app.register_blueprint(relaties_bp)
"""
import requests
from flask import Blueprint, request, session, render_template_string, redirect, url_for

from core import (
    ENF_BEDRIJVEN, PAPIERFABRIEKEN, laad_status, laad_accountmanagers,
    laad_users, render_simple_page, vereist_afdeling_of_403, is_huidige_gebruiker_admin,
    laad_leverancier_instellingen, bewaar_leverancier_instellingen, leverancier_instelling_voor,
    laad_betalingstermijnen, geocode_adres, laad_handelsorders, laad_logistieke_orders,
    parse_hoeveelheid_getal,
)

relaties_bp = Blueprint("relaties", __name__)

@relaties_bp.route("/leveranciers")
def leveranciers_pagina():
    _guard = vereist_afdeling_of_403("leveranciers")
    if _guard: return _guard
    bericht_lev = ("succes", "Leverancier toegevoegd.") if request.args.get("toegevoegd") else None

    zoekterm_lev = request.args.get("zoekterm", "").strip().lower()
    land_lev = request.args.get("land", "")
    filter_status_lev = request.args.get("filter_status", "")
    filter_am_lev = request.args.get("accountmanager", "")
    pagina_nr = request.args.get("pagina", "1")
    try:
        pagina_nr = max(1, int(pagina_nr))
    except (TypeError, ValueError):
        pagina_nr = 1

    status_alle_lev = laad_status()
    accountmanagers_alle_lev = laad_accountmanagers()
    huidige_gebruiker_lev = session.get("gebruikersnaam", "")

    # Alleen bedrijven die daadwerkelijk zijn toegekend/ingevuld: een status OF een accountmanager.
    # Dit is bewust GEEN kopie van Zoeken (dat doorzoekt de volledige, ongefilterde database).
    leveranciers_lijst = [b for b in ENF_BEDRIJVEN if status_alle_lev.get(b["naam"]) or accountmanagers_alle_lev.get(b["naam"])]

    if zoekterm_lev:
        leveranciers_lijst = [b for b in leveranciers_lijst if zoekterm_lev in b.get("naam","").lower() or zoekterm_lev in b.get("regio","").lower()]
    if land_lev:
        leveranciers_lijst = [b for b in leveranciers_lijst if b.get("land","").strip().lower() == land_lev.strip().lower()]
    if filter_status_lev:
        if filter_status_lev == "geen":
            leveranciers_lijst = [b for b in leveranciers_lijst if not status_alle_lev.get(b["naam"])]
        else:
            leveranciers_lijst = [b for b in leveranciers_lijst if status_alle_lev.get(b["naam"]) == filter_status_lev]
    if filter_am_lev == "__mij__":
        leveranciers_lijst = [b for b in leveranciers_lijst if accountmanagers_alle_lev.get(b["naam"]) == huidige_gebruiker_lev]
    elif filter_am_lev:
        leveranciers_lijst = [b for b in leveranciers_lijst if accountmanagers_alle_lev.get(b["naam"]) == filter_am_lev]

    totaal_gevonden_lev = len(leveranciers_lijst)
    PAGINA_GROOTTE_LEV = 200
    totaal_paginas_lev = max(1, (totaal_gevonden_lev + PAGINA_GROOTTE_LEV - 1) // PAGINA_GROOTTE_LEV)
    pagina_nr = min(pagina_nr, totaal_paginas_lev)
    start_lev = (pagina_nr - 1) * PAGINA_GROOTTE_LEV
    leveranciers_lijst = sorted(leveranciers_lijst, key=lambda b: b.get("naam",""))[start_lev:start_lev + PAGINA_GROOTTE_LEV]
    for b in leveranciers_lijst:
        b["status"] = status_alle_lev.get(b["naam"], "")
        b["accountmanager"] = accountmanagers_alle_lev.get(b["naam"], "")

    alle_landen_lev = sorted({b.get("land","") for b in ENF_BEDRIJVEN if b.get("land","")})
    alle_gebruikersnamen_lev = sorted(laad_users().keys())

    _relatiepool = [b for b in ENF_BEDRIJVEN if status_alle_lev.get(b["naam"]) or accountmanagers_alle_lev.get(b["naam"])]
    aantal_per_status_lev = {
        "klant": sum(1 for b in _relatiepool if status_alle_lev.get(b["naam"]) == "klant"),
        "in_proces": sum(1 for b in _relatiepool if status_alle_lev.get(b["naam"]) == "in_proces"),
        "potentie": sum(1 for b in _relatiepool if status_alle_lev.get(b["naam"]) == "potentie"),
    }

    actieve_filters_lev = []
    if land_lev:
        actieve_filters_lev.append({"label": f"Land: {land_lev}", "url": f"/leveranciers?zoekterm={zoekterm_lev}"})
    if filter_status_lev:
        _status_labels_lev = {"klant": "Status: Klant", "in_proces": "Status: In Proces", "potentie": "Status: Potentie", "geen_interesse": "Status: Geen Interesse", "geen": "Status: Geen status"}
        actieve_filters_lev.append({"label": _status_labels_lev.get(filter_status_lev, filter_status_lev), "url": f"/leveranciers?zoekterm={zoekterm_lev}&land={land_lev}"})
    if filter_am_lev:
        _am_label_lev = "Accountmanager: Mijn leveranciers" if filter_am_lev == "__mij__" else f"Accountmanager: {filter_am_lev}"
        actieve_filters_lev.append({"label": _am_label_lev, "url": f"/leveranciers?zoekterm={zoekterm_lev}&land={land_lev}&filter_status={filter_status_lev}"})

    def maak_pagina_url_lev(p):
        params = {"zoekterm": zoekterm_lev, "land": land_lev, "filter_status": filter_status_lev, "accountmanager": filter_am_lev, "pagina": p}
        params = {k: v for k, v in params.items() if v}
        return "/leveranciers?" + "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())

    inhoud = """
<style>
.data-thead, .data-row { display: flex; align-items: center; padding: 0 var(--space-4); }
.data-thead { padding-top: 10px; padding-bottom: 10px; background: var(--gray-50); border-bottom: 1px solid var(--gray-200); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: #7d8792; }
.data-thead span[data-sort] { cursor: pointer; user-select: none; }
.data-thead span[data-sort]:hover { color: var(--brand-600); }
.data-row { padding-top: 9px; padding-bottom: 9px; border-bottom: 1px solid var(--gray-100); font-size: 13px; text-decoration: none; color: inherit; }
.data-row:hover { background: #f9fbfc; }
.data-row .zacht { color: #4b5563; font-size: 12.5px; }
.klant-status-badge { font-size: 10.5px; font-weight: 700; padding: 2px 9px; border-radius: 10px; }
.klant-status-tab { padding: 7px 14px; border-radius: 6px; font-size: 12.5px; font-weight: 600; text-decoration: none; border: 1px solid var(--gray-200); background: #fff; color: var(--gray-600); }
.klant-status-tab.actief { background: var(--brand-600); color: #fff; border-color: var(--brand-600); }
.tvf-label { font-size: 10px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--gray-400); margin-bottom: 4px; display: block; }
.tvf-input { width: 100%; padding: 8px 10px; border: 1px solid var(--gray-200); border-radius: 6px; font-size: 13px; box-sizing: border-box; font-family: inherit; }
.tvf-sectiekop { font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--gray-300); margin: 16px 0 10px; padding-top: 12px; border-top: 1px solid var(--gray-100); }
.tvf-sectiekop:first-of-type { margin-top: 0; padding-top: 0; border-top: none; }
</style>

<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px;flex-wrap:wrap;gap:12px;padding-left:20px;">
    <div>
        <div style="font-size:28px;font-weight:600;letter-spacing:-0.02em;color:var(--gray-900);">Leveranciers</div>
    </div>
    <div style="display:flex;align-items:center;gap:22px;">
        <div><div style="font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Resultaten</div><div style="font-size:28px;font-weight:700;color:var(--gray-800);font-family:var(--font-mono);">{{ totaal_gevonden_lev }}</div></div>
        <div><div style="font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Landen</div><div style="font-size:28px;font-weight:700;color:var(--gray-800);font-family:var(--font-mono);">{{ alle_landen_lev|length }}</div></div>
        <a href="/bedrijf-toevoegen?type=leverancier" id="toevoegLevBtn" style="align-self:center;padding:9px 16px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-weight:600;cursor:pointer;font-size:13px;white-space:nowrap;text-decoration:none;">+ Nieuwe leverancier</a>
    </div>
</div>
<p style="color:var(--gray-400);margin:0 0 16px 20px;font-size:0.82rem;">Je eigen leveranciersbestand — alleen bedrijven met een toegekende status of accountmanager. Voor de volledige database: <a href="/" style="color:var(--brand-600);">Zoeken</a>.</p>

{% if bericht_lev %}
<div style="background:{{ '#f0fdf4' if bericht_lev[0] == 'succes' else '#fef2f2' }};color:{{ '#16a34a' if bericht_lev[0] == 'succes' else '#dc2626' }};padding:10px 16px;border-radius:8px;margin-bottom:16px;font-size:13.5px;margin-left:20px;max-width:820px;">{{ bericht_lev[1] }}</div>
{% endif %}


<form method="GET" style="max-width:820px;height:44px;background:#fff;border:1px solid #E5E7EB;border-radius:10px;overflow:hidden;display:flex;align-items:stretch;margin-bottom:14px;margin-left:20px;">
    {% if filter_status_lev %}<input type="hidden" name="filter_status" value="{{ filter_status_lev }}">{% endif %}
    {% if filter_am_lev %}<input type="hidden" name="accountmanager" value="{{ filter_am_lev }}">{% endif %}
    <input type="text" name="zoekterm" value="{{ zoekterm_lev }}" placeholder="Leverancier of stad..." style="flex:1;min-width:140px;border:none;padding:0 14px;font-size:14px;outline:none;">
    <select name="land" onchange="this.form.submit()" style="width:150px;border:none;border-left:1px solid var(--gray-100);padding:0 14px;font-size:14px;cursor:pointer;">
        <option value="">Alle landen</option>
        {% for l in alle_landen_lev %}<option value="{{ l }}" {% if land_lev == l %}selected{% endif %}>{{ l }}</option>{% endfor %}
    </select>
    <button type="submit" style="background:var(--brand-600);color:#fff;border:none;padding:0 20px;font-weight:700;font-size:14px;cursor:pointer;">Search →</button>
</form>

<div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;margin-left:20px;">
    <a href="/leveranciers" class="klant-status-tab {% if not filter_status_lev %}actief{% endif %}">Alle</a>
    <a href="/leveranciers?filter_status=klant" class="klant-status-tab {% if filter_status_lev == 'klant' %}actief{% endif %}">🟢 Klant ({{ aantal_per_status_lev.klant }})</a>
    <a href="/leveranciers?filter_status=in_proces" class="klant-status-tab {% if filter_status_lev == 'in_proces' %}actief{% endif %}">🔵 In Proces ({{ aantal_per_status_lev.in_proces }})</a>
    <a href="/leveranciers?filter_status=potentie" class="klant-status-tab {% if filter_status_lev == 'potentie' %}actief{% endif %}">🟡 Potentie ({{ aantal_per_status_lev.potentie }})</a>
    <a href="/leveranciers?filter_status=geen" class="klant-status-tab {% if filter_status_lev == 'geen' %}actief{% endif %}">⚪ Geen status</a>
</div>

<div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;align-items:center;margin-left:20px;">
    <a href="/leveranciers?accountmanager=__mij__{% if filter_status_lev %}&filter_status={{ filter_status_lev }}{% endif %}" class="klant-status-tab {% if filter_am_lev == '__mij__' %}actief{% endif %}">🙋 Mijn leveranciers</a>
    <a href="/leveranciers{% if filter_status_lev %}?filter_status={{ filter_status_lev }}{% endif %}" class="klant-status-tab {% if not filter_am_lev %}actief{% endif %}">Hele bedrijf</a>
</div>

<div style="display:flex;flex-wrap:wrap;align-items:center;gap:7px;margin-bottom:20px;margin-left:20px;">
    {% for af in actieve_filters_lev %}
    <a href="{{ af.url }}" style="display:inline-flex;align-items:center;gap:5px;background:var(--brand-600);color:#fff;border-radius:14px;padding:4px 11px;font-size:12px;font-weight:600;text-decoration:none;">{{ af.label }}<span style="font-weight:800;opacity:0.8;">✕</span></a>
    {% endfor %}
</div>

{% if leveranciers_lijst %}
<div style="border:1px solid var(--gray-200);border-radius:var(--radius-md);overflow:hidden;">
    <div class="results-list" id="leveranciersLijst">
        <div class="data-thead">
            <span style="flex:1.4;" data-sort="naam">Leverancier</span>
            <span style="flex:1;" data-sort="locatie">Locatie</span>
            <span style="flex:1.2;" data-sort="materialen">Materialen</span>
            <span style="width:110px;" data-sort="status">Status</span>
            <span style="width:110px;" data-sort="accountmanager">Accountmgr.</span>
            <span style="width:90px;text-align:right;"></span>
        </div>
        {% for b in leveranciers_lijst %}
        <div class="data-row" style="cursor:default;">
        <a href="/bedrijf/{{ b.naam|urlencode }}" style="display:contents;color:inherit;text-decoration:none;"
           data-naam="{{ b.naam|e }}" data-locatie="{{ b.regio|default('',true)|e }}, {{ b.land|default('',true)|e }}" data-materialen="{{ b.materialen|default('',true)|e }}"
           data-status="{{ b.status|default('',true)|e }}" data-accountmanager="{{ b.accountmanager|default('',true)|e }}">
            <span style="flex:1.4;font-weight:600;color:var(--gray-800);">{{ b.naam }}</span>
            <span style="flex:1;" class="zacht">{{ b.regio }}, {{ b.land }}</span>
            <span style="flex:1.2;" class="zacht">{{ b.materialen|default('—',true) }}</span>
            <span style="width:110px;">
                {% if b.status == "klant" %}<span class="klant-status-badge" style="background:#f0fdf4;color:#16a34a;">🟢 Klant</span>
                {% elif b.status == "in_proces" %}<span class="klant-status-badge" style="background:#eff6ff;color:#1d4ed8;">🔵 In Proces</span>
                {% elif b.status == "potentie" %}<span class="klant-status-badge" style="background:#fffbeb;color:#d97706;">🟡 Potentie</span>
                {% elif b.status == "geen_interesse" %}<span class="klant-status-badge" style="background:var(--gray-100);color:var(--gray-500);">⚪ Geen interesse</span>
                {% else %}<span class="zacht">—</span>{% endif %}
            </span>
            <span style="width:110px;" class="zacht">{{ b.accountmanager|default('—',true) }}</span>
            <span style="width:90px;text-align:right;">
                <span style="font-size:12px;font-weight:600;color:var(--brand-600);">Profiel →</span>
            </span>
        </a>
        <a href="/leverancier/{{ b.naam|urlencode }}/commercieel" style="font-size:11px;color:var(--gray-400);text-decoration:none;margin-left:8px;white-space:nowrap;">Commercieel →</a>
        </div>
        {% endfor %}
    </div>
</div>
{% if totaal_paginas_lev > 1 %}
<div style="display:flex;gap:6px;justify-content:center;align-items:center;margin-top:14px;flex-wrap:wrap;">
    {% if pagina_nr > 1 %}<a href="{{ maak_pagina_url_lev(pagina_nr - 1) }}" style="padding:6px 10px;border:1px solid var(--gray-200);border-radius:6px;text-decoration:none;color:var(--gray-600);font-size:13px;">←</a>{% endif %}
    <span style="padding:6px 10px;border-radius:6px;background:var(--brand-600);color:#fff;font-weight:700;font-size:13px;">{{ pagina_nr }}</span>
    <span style="font-size:12px;color:var(--gray-400);">van {{ totaal_paginas_lev }}</span>
    {% if pagina_nr < totaal_paginas_lev %}<a href="{{ maak_pagina_url_lev(pagina_nr + 1) }}" style="padding:6px 10px;border:1px solid var(--gray-200);border-radius:6px;text-decoration:none;color:var(--gray-600);font-size:13px;">→</a>{% endif %}
</div>
{% endif %}
{% else %}
<div class="lege-staat">Nog geen leveranciers met een status of accountmanager. Ken een status toe via Zoeken, of voeg er hierboven een handmatig toe.</div>
{% endif %}

<script>
(function () {
    var lijst = document.getElementById("leveranciersLijst");
    if (!lijst) return;
    var koppen = lijst.querySelectorAll(".data-thead [data-sort]");
    var richting = "desc", sleutel = null;
    koppen.forEach(function (kop) {
        kop.addEventListener("click", function () {
            var k = kop.dataset.sort;
            richting = (sleutel === k && richting === "desc") ? "asc" : "desc";
            sleutel = k;
            koppen.forEach(function (x) { x.textContent = x.textContent.replace(/ [\u2191\u2193]$/, ""); });
            kop.textContent += richting === "desc" ? " \u2193" : " \u2191";
            var rijen = Array.prototype.slice.call(lijst.querySelectorAll(".data-row"));
            rijen.sort(function (a, b) {
                var va = a.dataset[k] || "", vb = b.dataset[k] || "";
                var r = va.localeCompare(vb, "nl");
                return richting === "asc" ? r : -r;
            });
            rijen.forEach(function (r) { lijst.appendChild(r); });
        });
    });
})();
</script>
    """
    pagina = render_simple_page("Leveranciers", "leveranciers", inhoud)
    return render_template_string(pagina, leveranciers_lijst=leveranciers_lijst, totaal_gevonden_lev=totaal_gevonden_lev,
                                    zoekterm_lev=zoekterm_lev, land_lev=land_lev, alle_landen_lev=alle_landen_lev,
                                    filter_status_lev=filter_status_lev, filter_am_lev=filter_am_lev,
                                    aantal_per_status_lev=aantal_per_status_lev, alle_gebruikersnamen_lev=alle_gebruikersnamen_lev,
                                    actieve_filters_lev=actieve_filters_lev, pagina_nr=pagina_nr, totaal_paginas_lev=totaal_paginas_lev,
                                    maak_pagina_url_lev=maak_pagina_url_lev, bericht_lev=bericht_lev)


@relaties_bp.route("/klanten")
def klanten_pagina():
    _guard = vereist_afdeling_of_403("klanten")
    if _guard: return _guard
    bericht_klant = ("succes", "Klant toegevoegd.") if request.args.get("toegevoegd") else None

    zoekterm_fab = request.args.get("zoekterm", "").strip().lower()
    land_fab = request.args.get("land", "")
    filter_status_klant = request.args.get("filter_status", "")

    status_alle_klant = laad_status()
    accountmanagers_alle_klant = laad_accountmanagers()
    huidige_gebruiker_klant = session.get("gebruikersnaam", "")
    _is_bevoorrecht_klant = is_huidige_gebruiker_admin() or session.get("rol", "") == "directeur"

    # Alleen de fabrieken die aan de ingelogde accountmanager zijn toegewezen — geen
    # bedrijfsbrede lijst meer. Admin/directeur zien (net als overal elders) wel alles.
    if _is_bevoorrecht_klant:
        klanten_lijst = list(PAPIERFABRIEKEN)
    else:
        klanten_lijst = [f for f in PAPIERFABRIEKEN if accountmanagers_alle_klant.get(f["naam"]) == huidige_gebruiker_klant]
    _eigen_klanten_basis = list(klanten_lijst)  # vóór zoek-/land-/status-filters, voor de tellingen hieronder
    if zoekterm_fab:
        klanten_lijst = [f for f in klanten_lijst if zoekterm_fab in f.get("naam","").lower() or zoekterm_fab in f.get("stad","").lower()]
    if land_fab:
        klanten_lijst = [f for f in klanten_lijst if f.get("land","") == land_fab]
    for f in klanten_lijst:
        f["status"] = status_alle_klant.get(f["naam"], "")
    if filter_status_klant:
        if filter_status_klant == "geen":
            klanten_lijst = [f for f in klanten_lijst if not f["status"]]
        else:
            klanten_lijst = [f for f in klanten_lijst if f["status"] == filter_status_klant]
    klanten_lijst.sort(key=lambda f: f.get("naam",""))

    alle_landen_fab = sorted({f.get("land","") for f in _eigen_klanten_basis if f.get("land","")})
    landen_in_resultaat_fab = len({f.get("land","") for f in klanten_lijst if f.get("land","")})

    aantal_per_status = {
        "klant": sum(1 for f in _eigen_klanten_basis if status_alle_klant.get(f["naam"]) == "klant"),
        "in_proces": sum(1 for f in _eigen_klanten_basis if status_alle_klant.get(f["naam"]) == "in_proces"),
        "potentie": sum(1 for f in _eigen_klanten_basis if status_alle_klant.get(f["naam"]) == "potentie"),
    }

    actieve_filters_fab = []
    if land_fab:
        actieve_filters_fab.append({"label": f"Land: {land_fab}", "url": f"/klanten?zoekterm={zoekterm_fab}"})
    if filter_status_klant:
        _status_labels_klant = {"klant": "Status: Klant", "in_proces": "Status: In Proces", "potentie": "Status: Potentie", "geen_interesse": "Status: Geen Interesse", "geen": "Status: Geen status"}
        actieve_filters_fab.append({"label": _status_labels_klant.get(filter_status_klant, filter_status_klant), "url": f"/klanten?zoekterm={zoekterm_fab}&land={land_fab}"})

    inhoud = """
<style>
.data-thead, .data-row { display: flex; align-items: center; padding: 0 var(--space-4); }
.data-thead { padding-top: 10px; padding-bottom: 10px; background: var(--gray-50); border-bottom: 1px solid var(--gray-200); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: #7d8792; }
.data-thead span[data-sort] { cursor: pointer; user-select: none; }
.data-thead span[data-sort]:hover { color: var(--brand-600); }
.data-row { padding-top: 9px; padding-bottom: 9px; border-bottom: 1px solid var(--gray-100); font-size: 13px; text-decoration: none; color: inherit; }
.data-row:hover { background: #f9fbfc; }
.data-row .zacht { color: #4b5563; font-size: 12.5px; }
.klant-status-badge { font-size: 10.5px; font-weight: 700; padding: 2px 9px; border-radius: 10px; }
.klant-status-tab { padding: 7px 14px; border-radius: 6px; font-size: 12.5px; font-weight: 600; text-decoration: none; border: 1px solid var(--gray-200); background: #fff; color: var(--gray-600); }
.klant-status-tab.actief { background: var(--brand-600); color: #fff; border-color: var(--brand-600); }
.tvf-label { font-size: 10px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--gray-400); margin-bottom: 4px; display: block; }
.tvf-input { width: 100%; padding: 8px 10px; border: 1px solid var(--gray-200); border-radius: 6px; font-size: 13px; box-sizing: border-box; font-family: inherit; }
.tvf-sectiekop { font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: var(--gray-300); margin: 16px 0 10px; padding-top: 12px; border-top: 1px solid var(--gray-100); }
.tvf-sectiekop:first-of-type { margin-top: 0; padding-top: 0; border-top: none; }
</style>

<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px;flex-wrap:wrap;gap:12px;padding-left:20px;">
    <div>
        <div style="font-size:28px;font-weight:600;letter-spacing:-0.02em;color:var(--gray-900);">Klanten</div>
    </div>
    <div style="display:flex;align-items:center;gap:22px;">
        <div><div style="font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Resultaten</div><div style="font-size:28px;font-weight:700;color:var(--gray-800);font-family:var(--font-mono);">{{ klanten_lijst|length }}</div></div>
        <div><div style="font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Landen</div><div style="font-size:28px;font-weight:700;color:var(--gray-800);font-family:var(--font-mono);">{{ landen_in_resultaat_fab }}</div></div>
        <a href="/bedrijf-toevoegen?type=klant" id="toevoegKlantBtn" style="align-self:center;padding:9px 16px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-weight:600;cursor:pointer;font-size:13px;white-space:nowrap;text-decoration:none;">+ Nieuwe klant</a>
    </div>
</div>

{% if bericht_klant %}
<div style="background:{{ '#f0fdf4' if bericht_klant[0] == 'succes' else '#fef2f2' }};color:{{ '#16a34a' if bericht_klant[0] == 'succes' else '#dc2626' }};padding:10px 16px;border-radius:8px;margin-bottom:16px;font-size:13.5px;margin-left:20px;max-width:820px;">{{ bericht_klant[1] }}</div>
{% endif %}


<form method="GET" id="klantZoekForm" style="max-width:820px;height:44px;background:#fff;border:1px solid #E5E7EB;border-radius:10px;overflow:hidden;display:flex;align-items:stretch;margin-bottom:14px;margin-left:20px;">
    {% if filter_status_klant %}<input type="hidden" name="filter_status" value="{{ filter_status_klant }}">{% endif %}
    <input type="text" name="zoekterm" value="{{ zoekterm_fab }}" placeholder="Klant of stad..." style="flex:1;min-width:140px;border:none;padding:0 14px;font-size:14px;outline:none;">
    <select name="land" onchange="this.form.submit()" style="width:150px;border:none;border-left:1px solid var(--gray-100);padding:0 14px;font-size:14px;cursor:pointer;">
        <option value="">Alle landen</option>
        {% for l in alle_landen_fab %}<option value="{{ l }}" {% if land_fab == l %}selected{% endif %}>{{ l }}</option>{% endfor %}
    </select>
    <button type="submit" style="background:var(--brand-600);color:#fff;border:none;padding:0 20px;font-weight:700;font-size:14px;cursor:pointer;">Search →</button>
</form>

<div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;margin-left:20px;">
    <a href="/klanten" class="klant-status-tab {% if not filter_status_klant %}actief{% endif %}">Alle</a>
    <a href="/klanten?filter_status=klant" class="klant-status-tab {% if filter_status_klant == 'klant' %}actief{% endif %}">🟢 Klant ({{ aantal_per_status.klant }})</a>
    <a href="/klanten?filter_status=in_proces" class="klant-status-tab {% if filter_status_klant == 'in_proces' %}actief{% endif %}">🔵 In Proces ({{ aantal_per_status.in_proces }})</a>
    <a href="/klanten?filter_status=potentie" class="klant-status-tab {% if filter_status_klant == 'potentie' %}actief{% endif %}">🟡 Potentie ({{ aantal_per_status.potentie }})</a>
    <a href="/klanten?filter_status=geen" class="klant-status-tab {% if filter_status_klant == 'geen' %}actief{% endif %}">⚪ Geen status</a>
</div>

<div style="display:flex;flex-wrap:wrap;align-items:center;gap:7px;margin-bottom:14px;margin-left:20px;">
    {% for af in actieve_filters_fab %}
    <a href="{{ af.url }}" style="display:inline-flex;align-items:center;gap:5px;background:var(--brand-600);color:#fff;border-radius:14px;padding:4px 11px;font-size:12px;font-weight:600;text-decoration:none;">{{ af.label }}<span style="font-weight:800;opacity:0.8;">✕</span></a>
    {% endfor %}
</div>

{% if klanten_lijst %}
<div style="border:1px solid var(--gray-200);border-radius:var(--radius-md);overflow:hidden;">
    <div class="results-list" id="klantenLijst">
        <div class="data-thead">
            <span style="flex:1.6;" data-sort="naam">Klant</span>
            <span style="flex:1;" data-sort="locatie">Locatie</span>
            <span style="flex:1.4;" data-sort="materialen">Materialen</span>
            <span style="width:120px;" data-sort="status">Status</span>
            <span style="width:100px;text-align:right;"></span>
        </div>
        {% for f in klanten_lijst %}
        <a class="data-row" href="/bedrijf/{{ f.naam|urlencode }}"
           data-naam="{{ f.naam|e }}" data-locatie="{{ f.stad|default('',true)|e }}, {{ f.land|default('',true)|e }}" data-materialen="{{ f.materialen|default('',true)|e }}"
           data-status="{{ f.status|default('',true)|e }}">
            <span style="flex:1.6;font-weight:600;color:var(--gray-800);">🏭 {{ f.naam }}</span>
            <span style="flex:1;" class="zacht">{{ f.stad }}, {{ f.land }}</span>
            <span style="flex:1.4;" class="zacht">{{ f.materialen|default('—',true) }}</span>
            <span style="width:120px;">
                {% if f.status == "klant" %}<span class="klant-status-badge" style="background:#f0fdf4;color:#16a34a;">🟢 Klant</span>
                {% elif f.status == "in_proces" %}<span class="klant-status-badge" style="background:#eff6ff;color:#1d4ed8;">🔵 In Proces</span>
                {% elif f.status == "potentie" %}<span class="klant-status-badge" style="background:#fffbeb;color:#d97706;">🟡 Potentie</span>
                {% elif f.status == "geen_interesse" %}<span class="klant-status-badge" style="background:var(--gray-100);color:var(--gray-500);">⚪ Geen interesse</span>
                {% else %}<span class="zacht">—</span>{% endif %}
            </span>
            <span style="width:100px;text-align:right;">
                <span style="font-size:12px;font-weight:600;color:var(--brand-600);">Profiel →</span>
            </span>
        </a>
        {% endfor %}
    </div>
</div>
{% else %}
<div class="lege-staat">Geen klanten gevonden voor deze filters.</div>
{% endif %}

<script>
(function () {
    var lijst = document.getElementById("klantenLijst");
    if (!lijst) return;
    var koppen = lijst.querySelectorAll(".data-thead [data-sort]");
    var richting = "desc", sleutel = null;
    koppen.forEach(function (kop) {
        kop.addEventListener("click", function () {
            var k = kop.dataset.sort;
            richting = (sleutel === k && richting === "desc") ? "asc" : "desc";
            sleutel = k;
            koppen.forEach(function (x) { x.textContent = x.textContent.replace(/ [\u2191\u2193]$/, ""); });
            kop.textContent += richting === "desc" ? " \u2193" : " \u2191";
            var rijen = Array.prototype.slice.call(lijst.querySelectorAll(".data-row"));
            rijen.sort(function (a, b) {
                var va = a.dataset[k] || "", vb = b.dataset[k] || "";
                var r = va.localeCompare(vb, "nl");
                return richting === "asc" ? r : -r;
            });
            rijen.forEach(function (r) { lijst.appendChild(r); });
        });
    });
})();
</script>
    """
    pagina = render_simple_page("Klanten", "klanten", inhoud)
    return render_template_string(pagina, klanten_lijst=klanten_lijst,
                                    zoekterm_fab=zoekterm_fab, land_fab=land_fab, actieve_filters_fab=actieve_filters_fab,
                                    alle_landen_fab=alle_landen_fab, landen_in_resultaat_fab=landen_in_resultaat_fab,
                                    filter_status_klant=filter_status_klant, aantal_per_status=aantal_per_status,
                                    bericht_klant=bericht_klant)


@relaties_bp.route("/leverancier/<naam>/commercieel", methods=["GET", "POST"])
def leverancier_commercieel_instellingen(naam):
    """Beheert de commerciële instellingen van één leverancier: afhaallocatie(s),
    standaard betalingstermijn, en de korte code voor supplier-referentienummers.
    Bewust een aparte, kleine pagina — niet toegevoegd aan het al zeer grote
    bedrijfsprofiel, om die pagina niet nog fragieler te maken."""
    _guard = vereist_afdeling_of_403("leveranciers")
    if _guard: return _guard

    bedrijf = next((b for b in ENF_BEDRIJVEN if b["naam"] == naam), None)
    if not bedrijf:
        inhoud = '<div class="page-title">Niet gevonden</div><div class="lege-staat">Deze leverancier bestaat niet (meer).</div>'
        pagina = render_simple_page("Niet gevonden", "leveranciers", inhoud)
        return render_template_string(pagina), 404

    alle_instellingen = laad_leverancier_instellingen()
    instelling = alle_instellingen.setdefault(naam, {"afhaallocaties": [], "standaard_betalingstermijn": "", "leverancier_code": "", "referentie_teller": 0})

    if request.method == "POST":
        actie = request.form.get("actie", "")
        if actie == "locatie_toevoegen":
            nieuwe_locatie = {
                "naam": request.form.get("locatie_naam", "").strip(),
                "adres": request.form.get("adres", "").strip(),
                "postcode": request.form.get("postcode", "").strip(),
                "stad": request.form.get("stad", "").strip(),
                "land": request.form.get("land", "").strip(),
            }
            if nieuwe_locatie["adres"] and nieuwe_locatie["stad"]:
                _geo = geocode_adres(nieuwe_locatie["adres"], nieuwe_locatie["stad"])
                if _geo:
                    nieuwe_locatie["lat"] = _geo["lat"]
                    nieuwe_locatie["lon"] = _geo["lon"]
                instelling["afhaallocaties"].append(nieuwe_locatie)
                bewaar_leverancier_instellingen(alle_instellingen)
        elif actie == "locatie_verwijderen":
            index = int(request.form.get("index", "-1"))
            if 0 <= index < len(instelling["afhaallocaties"]):
                instelling["afhaallocaties"].pop(index)
                bewaar_leverancier_instellingen(alle_instellingen)
        elif actie == "instellingen_opslaan":
            instelling["standaard_betalingstermijn"] = request.form.get("standaard_betalingstermijn", "").strip()
            instelling["leverancier_code"] = request.form.get("leverancier_code", "").strip().upper()
            bewaar_leverancier_instellingen(alle_instellingen)
        return redirect(url_for("relaties.leverancier_commercieel_instellingen", naam=naam))

    # --- Contractvoortgang: alle goedgekeurde inkoopcontracten van deze leverancier,
    # met geleverd/resterend tonnage — noodzakelijk om vanuit Commercieel te kunnen
    # zien wat er via de weegbrug al daadwerkelijk binnengekomen is. ---
    alle_logistieke_orders = laad_logistieke_orders()
    def _geleverd_op_contract(contractnummer):
        return round(sum(
            parse_hoeveelheid_getal(o.get("werkelijke_hoeveelheid",""))
            for o in alle_logistieke_orders
            if o.get("contract_referentie") == contractnummer and o.get("status") in ("Weegbon compleet", "Afhandeling", "Klaar voor Finance", "Gefactureerd", "Afgerond")
        ), 3)
    contracten_lev = []
    for h in laad_handelsorders():
        if h.get("order_type") == "inkoop" and h.get("tegenpartij_naam") == naam and h.get("status") == "Definitief":
            try:
                totaal = float(str(h.get("hoeveelheid_mt","0")).replace(",",""))
            except (ValueError, TypeError):
                totaal = 0.0
            geleverd = _geleverd_op_contract(h["contractnummer"])
            contracten_lev.append({
                "contractnummer": h["contractnummer"], "materiaal": h.get("materiaal",""), "kwaliteit": h.get("kwaliteit",""),
                "totaal": round(totaal,1), "geleverd": geleverd, "resterend": round(totaal-geleverd,1),
                "aangemaakt": h.get("aangemaakt",""),
            })
    contracten_lev.sort(key=lambda c: c["aangemaakt"], reverse=True)

    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/leveranciers" style="color:var(--gray-400);text-decoration:none;">Leveranciers</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">{{ naam }}</span> &nbsp;/&nbsp; <span style="color:var(--gray-600);">Commercieel</span>
</div>
<div class="page-title">{{ naam }} — Commerciële instellingen</div>

<div style="display:flex;gap:24px;flex-wrap:wrap;">
<div style="flex:1;min-width:320px;">
    <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Algemeen</div>
    <form method="POST" style="margin-bottom:24px;">
        <input type="hidden" name="actie" value="instellingen_opslaan">
        <div style="margin-bottom:10px;">
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Standaard betalingstermijn</label>
            <select name="standaard_betalingstermijn" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
                <option value="">— geen —</option>
                {% for termijn in betalingstermijnen %}<option value="{{ termijn }}" {% if instelling.standaard_betalingstermijn == termijn %}selected{% endif %}>{{ termijn }}</option>{% endfor %}
            </select>
        </div>
        <div style="margin-bottom:10px;">
            <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Leverancier-code (voor referentienummers, bv. 'ACME')</label>
            <input type="text" name="leverancier_code" value="{{ instelling.leverancier_code }}" placeholder="Automatisch als leeg" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
        </div>
        <button type="submit" style="padding:8px 16px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:12.5px;font-weight:700;cursor:pointer;">Opslaan</button>
    </form>
</div>

<div style="flex:1;min-width:340px;">
    <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Afhaallocaties</div>
    <div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);margin-bottom:16px;">
        {% for loc in instelling.afhaallocaties %}
        <div style="display:flex;justify-content:space-between;align-items:center;padding:9px 4px;border-bottom:1px solid var(--gray-100);font-size:12.5px;">
            <span style="color:var(--gray-700);">{{ loc.naam or loc.stad }} — {{ loc.adres }}, {{ loc.postcode }} {{ loc.stad }}, {{ loc.land }}</span>
            <form method="POST" onsubmit="return confirm('Deze locatie verwijderen?');" style="margin:0;">
                <input type="hidden" name="actie" value="locatie_verwijderen">
                <input type="hidden" name="index" value="{{ loop.index0 }}">
                <button type="submit" style="background:none;border:none;color:var(--gray-300);cursor:pointer;font-size:12px;">✕</button>
            </form>
        </div>
        {% else %}
        <div style="padding:10px 4px;color:var(--gray-300);font-size:12px;">Nog geen afhaallocaties toegevoegd.</div>
        {% endfor %}
    </div>
    <form method="POST" style="max-width:400px;">
        <input type="hidden" name="actie" value="locatie_toevoegen">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
            <input type="text" name="locatie_naam" placeholder="Naam (optioneel, bv. 'Hoofdmagazijn')" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
            <input type="text" name="land" placeholder="Land" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
        </div>
        <input type="text" name="adres" placeholder="Adres *" required style="width:100%;padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;margin-bottom:8px;box-sizing:border-box;">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
            <input type="text" name="postcode" placeholder="Postcode" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
            <input type="text" name="stad" placeholder="Stad *" required style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
        </div>
        <button type="submit" style="padding:7px 14px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;">+ Locatie toevoegen</button>
    </form>
</div>
</div>

<div style="margin-top:28px;">
    <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;">Contractvoortgang (goedgekeurde inkoopcontracten)</div>
    {% if contracten_lev %}
    <div style="border:none;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);max-width:720px;">
        {% for c in contracten_lev %}
        <div style="display:flex;align-items:center;padding:9px 4px;border-bottom:1px solid var(--gray-100);font-size:12.5px;">
            <span style="flex:1.3;font-family:var(--font-mono);color:var(--gray-500);">{{ c.contractnummer }}</span>
            <span style="flex:1;color:var(--gray-700);">{{ c.materiaal }} — {{ c.kwaliteit }}</span>
            <span style="width:110px;text-align:right;color:var(--gray-500);">{{ c.geleverd }} / {{ c.totaal }} MT</span>
            <span style="width:110px;text-align:right;font-weight:700;color:{{ '#dc2626' if c.resterend > 0 else '#16a34a' }};">{{ c.resterend }} MT open</span>
        </div>
        {% endfor %}
    </div>
    {% else %}
    <div class="lege-staat">Nog geen goedgekeurde inkoopcontracten voor deze leverancier.</div>
    {% endif %}
</div>
    """
    pagina = render_simple_page(f"{naam} — Commercieel", "leveranciers", inhoud)
    return render_template_string(pagina, naam=naam, instelling=instelling, betalingstermijnen=laad_betalingstermijnen(),
                                    contracten_lev=contracten_lev)