"""
materialen.py — Blueprint voor de Materialen-module.

Bevat: /materialen (overzichtstabel), /materialen-beheer (grondstofgroepen
en kwaliteiten beheren, admin-only), /certificeringen (certificeringen-
overzicht met vervaldatums), /api/cert-vervaldatum.

Registratie in app.py met: app.register_blueprint(materialen_bp)
"""
import datetime
from flask import Blueprint, request, jsonify, render_template_string

from core import (
    laad_materiaal_taxonomie, bewaar_materiaal_taxonomie, vereist_admin_of_403,
    render_simple_page, ENF_BEDRIJVEN, laad_accountmanagers, laad_cert_vervaldatums,
    bewaar_cert_vervaldatums, _cert_sleutel, parse_hoeveelheid_getal,
)

materialen_bp = Blueprint("materialen", __name__)

@materialen_bp.route("/api/cert-vervaldatum", methods=["POST"])
def set_cert_vervaldatum():
    data = request.get_json()
    bedrijf_naam = data.get("bedrijf", "")
    certificaat = data.get("certificaat", "")
    vervaldatum = data.get("vervaldatum", "")
    if not bedrijf_naam or not certificaat:
        return jsonify({"error": "Bedrijf en certificaat zijn verplicht"}), 400
    alle = laad_cert_vervaldatums()
    sleutel = _cert_sleutel(bedrijf_naam, certificaat)
    if vervaldatum:
        alle[sleutel] = vervaldatum
    else:
        alle.pop(sleutel, None)
    bewaar_cert_vervaldatums(alle)
    return jsonify({"vervaldatum": vervaldatum})

@materialen_bp.route("/materialen-beheer", methods=["GET", "POST"])
def materialen_beheer():
    _guard = vereist_admin_of_403()
    if _guard: return _guard

    bericht = None
    if request.method == "POST":
        actie = request.form.get("actie", "")
        taxonomie = laad_materiaal_taxonomie()

        if actie == "categorie_toevoegen":
            naam = request.form.get("categorie_naam", "").strip()
            if not naam:
                bericht = "Naam van de grondstofgroep is verplicht."
            elif naam in taxonomie:
                bericht = f"'{naam}' bestaat al."
            else:
                taxonomie[naam] = []
                bewaar_materiaal_taxonomie(taxonomie)
                bericht = f"Grondstofgroep '{naam}' toegevoegd."

        elif actie == "categorie_verwijderen":
            naam = request.form.get("categorie_naam", "")
            if naam in taxonomie:
                del taxonomie[naam]
                bewaar_materiaal_taxonomie(taxonomie)
                bericht = f"'{naam}' verwijderd."

        elif actie == "kwaliteit_toevoegen":
            categorie = request.form.get("categorie", "")
            kwaliteit = request.form.get("kwaliteit_naam", "").strip()
            if categorie in taxonomie and kwaliteit:
                if kwaliteit not in taxonomie[categorie]:
                    taxonomie[categorie].append(kwaliteit)
                    bewaar_materiaal_taxonomie(taxonomie)
                bericht = f"'{kwaliteit}' toegevoegd aan {categorie}."

        elif actie == "kwaliteit_verwijderen":
            categorie = request.form.get("categorie", "")
            kwaliteit = request.form.get("kwaliteit_naam", "")
            if categorie in taxonomie and kwaliteit in taxonomie[categorie]:
                taxonomie[categorie].remove(kwaliteit)
                bewaar_materiaal_taxonomie(taxonomie)
                bericht = f"'{kwaliteit}' verwijderd uit {categorie}."

    taxonomie = laad_materiaal_taxonomie()
    inhoud = """
    <div class="page-title">Materialen beheren</div>
    <p style="color:var(--gray-400);font-size:0.85rem;margin-top:0;margin-bottom:20px;max-width:600px;">
        Deze grondstofgroepen en kwaliteiten gelden voor <b>alle</b> bedrijven in FTNext — pas je hier iets aan, dan zie je dat overal terug (zoekfilter, bedrijfsprofielen, fotomappen).
    </p>
    {% if bericht %}<div style="background:#f0fdf4;color:#16a34a;padding:10px 16px;border-radius:8px;margin-bottom:16px;font-size:14px;max-width:600px;">{{ bericht }}</div>{% endif %}

    <div class="info-kaart" style="max-width:500px;margin-bottom:20px;">
        <div class="dg-kaart-titel">Nieuwe grondstofgroep</div>
        <form method="POST" style="display:flex;gap:8px;">
            <input type="hidden" name="actie" value="categorie_toevoegen">
            <input type="text" name="categorie_naam" placeholder="bv. Textiel, Hout, E-waste..." required style="flex:1;padding:8px 10px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;font-family:inherit;">
            <button type="submit" style="padding:8px 16px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-weight:600;cursor:pointer;font-size:13px;">+ Toevoegen</button>
        </form>
    </div>

    {% for categorie, kwaliteiten_lijst in taxonomie.items() %}
    <div class="info-kaart" style="max-width:500px;margin-bottom:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <div class="dg-kaart-titel" style="margin-bottom:0;">{{ categorie }}</div>
            <form method="POST" onsubmit="return confirm('Grondstofgroep {{ categorie }} volledig verwijderen?');" style="margin:0;">
                <input type="hidden" name="actie" value="categorie_verwijderen">
                <input type="hidden" name="categorie_naam" value="{{ categorie }}">
                <button type="submit" style="background:none;border:none;color:var(--gray-300);cursor:pointer;font-size:12px;">Groep verwijderen ✕</button>
            </form>
        </div>
        <div class="company-tags" style="padding-left:0;margin-bottom:10px;">
            {% for kw in kwaliteiten_lijst %}
            <span class="tag tag-purple" style="display:inline-flex;align-items:center;gap:5px;">
                {{ kw }}
                <form method="POST" style="margin:0;display:inline;" onsubmit="return confirm('{{ kw }} verwijderen?');">
                    <input type="hidden" name="actie" value="kwaliteit_verwijderen">
                    <input type="hidden" name="categorie" value="{{ categorie }}">
                    <input type="hidden" name="kwaliteit_naam" value="{{ kw }}">
                    <button type="submit" style="background:none;border:none;color:inherit;cursor:pointer;font-size:10px;padding:0;">✕</button>
                </form>
            </span>
            {% else %}
            <span style="font-size:0.78rem;color:var(--gray-300);">Nog geen kwaliteiten toegevoegd.</span>
            {% endfor %}
        </div>
        <form method="POST" style="display:flex;gap:8px;">
            <input type="hidden" name="actie" value="kwaliteit_toevoegen">
            <input type="hidden" name="categorie" value="{{ categorie }}">
            <input type="text" name="kwaliteit_naam" placeholder="Nieuwe kwaliteit toevoegen..." required style="flex:1;padding:6px 10px;border:1px solid #e2e8f0;border-radius:6px;font-size:12.5px;font-family:inherit;">
            <button type="submit" style="padding:6px 12px;background:var(--gray-100);color:var(--gray-700);border:none;border-radius:6px;font-weight:600;cursor:pointer;font-size:12.5px;">+</button>
        </form>
    </div>
    {% endfor %}
    """
    pagina = render_simple_page("Materialen beheren", "instellingen", inhoud)
    return render_template_string(pagina, taxonomie=taxonomie, bericht=bericht)

@materialen_bp.route("/certificeringen")
def certificeringen_pagina():
    _am_lookup_cert = laad_accountmanagers()
    _vervaldatums = laad_cert_vervaldatums()
    vandaag_cert = datetime.date.today()

    cert_rijen = []
    for b in ENF_BEDRIJVEN:
        for c in [x.strip() for x in b.get("certificeringen", "").split(",") if x.strip()]:
            sleutel = _cert_sleutel(b["naam"], c)
            geldig_tot = _vervaldatums.get(sleutel, "")
            status_tekst = ""
            if geldig_tot:
                try:
                    geldig_datum = datetime.datetime.strptime(geldig_tot, "%Y-%m-%d").date()
                    status_tekst = "Geldig" if geldig_datum >= vandaag_cert else "Verlopen"
                except (ValueError, TypeError):
                    status_tekst = ""
            cert_rijen.append({
                "bedrijf": b["naam"], "certificaat": c, "land": b.get("land",""),
                "regio": b.get("regio",""), "accountmanager": _am_lookup_cert.get(b["naam"], ""),
                "geldig_tot": geldig_tot, "status": status_tekst,
            })
    cert_rijen.sort(key=lambda r: r["bedrijf"])

    per_cert_telling = {}
    for r in cert_rijen:
        per_cert_telling[r["certificaat"]] = per_cert_telling.get(r["certificaat"], 0) + 1
    aantal_verlopen_cert = sum(1 for r in cert_rijen if r["status"] == "Verlopen")
    kpis = [
        {"label": "Certificeringen totaal", "value": len(cert_rijen), "sub": f"{len(per_cert_telling)} soorten"},
        {"label": "Bedrijven met certificering", "value": len({r['bedrijf'] for r in cert_rijen}), "sub": f"van {len(ENF_BEDRIJVEN)} totaal"},
        {"label": "Verlopen", "value": aantal_verlopen_cert, "sub": "vraagt aandacht" if aantal_verlopen_cert else "alles op orde"},
    ]

    inhoud = """
<style>
.data-thead, .data-row { display: flex; align-items: center; padding: 0 var(--space-4); }
.data-thead { padding-top: 10px; padding-bottom: 10px; background: var(--gray-50); border-bottom: 1px solid var(--gray-200); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: #7d8792; }
.data-thead span[data-sort] { cursor: pointer; user-select: none; }
.data-thead span[data-sort]:hover { color: var(--brand-600); }
.data-row { padding-top: 11px; padding-bottom: 11px; border-bottom: 1px solid var(--gray-100); font-size: 12.5px; text-decoration: none; color: inherit; }
.data-row:hover { background: #f9fbfc; }
.data-row .zacht { color: #4b5563; font-size: 12px; }
.kpi-mini-cert { display:flex; gap:16px; margin-bottom:20px; }
.kpi-mini-cert div { background:#fff; border:1px solid var(--gray-200); border-radius:10px; padding:14px 18px; flex:1; }
.kpi-mini-cert .getal { font-size:1.2rem; font-weight:800; color:var(--brand-600); }
.kpi-mini-cert .label { font-size:0.72rem; color:var(--gray-400); text-transform:uppercase; letter-spacing:0.06em; }
.kpi-mini-cert .sub { font-size:0.72rem; color:var(--gray-400); margin-top:2px; }
.cert-status { font-size:10.5px; padding:3px 9px; border-radius:11px; border:1px solid var(--gray-200); color:var(--gray-500); background:#fff; display:inline-block; }
.cert-status.geldig { border-color:#bcd9da; background:#eef6f6; color:var(--brand-600); }
.cert-status.verlopen { border-color:#e6d3b8; background:#fdf6ea; color:#8a6320; }
</style>

<div class="page-title">Certifications</div>

{% if cert_rijen %}
<div class="kpi-mini-cert">
    {% for k in kpis %}
    <div><div class="getal">{{ k.value }}</div><div class="label">{{ k.label }}</div><div class="sub">{{ k.sub }}</div></div>
    {% endfor %}
</div>

<div class="data-thead" style="border-radius:var(--radius-md) var(--radius-md) 0 0;">
    <span style="flex:1.6;" data-sort="bedrijf">Bedrijf</span>
    <span style="flex:1;" data-sort="certificaat">Certificaat</span>
    <span style="flex:1;" data-sort="land">Land</span>
    <span style="width:130px;" data-sort="geldig_tot">Geldig tot</span>
    <span style="width:130px;" data-sort="status">Status</span>
    <span style="width:120px;" data-sort="accountmanager">Accountmgr.</span>
</div>
<div id="certLijst" style="border:1px solid var(--gray-200);border-top:none;border-radius:0 0 var(--radius-md) var(--radius-md);overflow:hidden;">
    {% for r in cert_rijen %}
    <div class="data-row"
       data-bedrijf="{{ r.bedrijf|e }}" data-certificaat="{{ r.certificaat|e }}" data-land="{{ r.land|e }}"
       data-geldig_tot="{{ r.geldig_tot|default('',true)|e }}" data-status="{{ r.status|default('',true)|e }}" data-accountmanager="{{ r.accountmanager|default('',true)|e }}">
        <span style="flex:1.6;"><a href="/bedrijf/{{ r.bedrijf|urlencode }}" style="font-weight:600;color:var(--gray-800);text-decoration:none;">{{ r.bedrijf }}</a></span>
        <span style="flex:1;" class="zacht">🏅 {{ r.certificaat }}</span>
        <span style="flex:1;" class="zacht">{{ r.land }}{% if r.regio %}, {{ r.regio }}{% endif %}</span>
        <span style="width:130px;">
            <input type="date" value="{{ r.geldig_tot }}" data-bedrijf-veld="{{ r.bedrijf|e }}" data-cert-veld="{{ r.certificaat|e }}" onchange="wijzigCertVervaldatum(this)" style="font-size:11.5px;border:1px solid var(--gray-200);border-radius:5px;padding:3px 5px;font-family:inherit;">
        </span>
        <span style="width:130px;">{% if r.status %}<span class="cert-status {{ 'geldig' if r.status == 'Geldig' else 'verlopen' }}">{{ r.status }}</span>{% else %}<span class="zacht">—</span>{% endif %}</span>
        <span style="width:120px;" class="zacht">{{ r.accountmanager|default('—',true) }}</span>
    </div>
    {% endfor %}
</div>
<div style="display:flex;justify-content:space-between;padding:10px 4px;font-size:0.8rem;color:var(--gray-400);">
    <span>{{ cert_rijen|length }} certificeringen</span>
    <a href="/export-csv" style="color:var(--brand-600);text-decoration:none;font-weight:600;">Export naar CSV</a>
</div>
<script>
function wijzigCertVervaldatum(input) {
    fetch("/api/cert-vervaldatum", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: input.dataset.bedrijfVeld, certificaat: input.dataset.certVeld, vervaldatum: input.value})}).then(() => location.reload());
}
(function () {
    var lijst = document.getElementById("certLijst");
    if (!lijst) return;
    var koppen = document.querySelectorAll(".data-thead [data-sort]");
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
{% else %}
<div class="lege-staat">
    Nog geen bedrijven met certificeringen. Voeg de kolom "Certificeringen" toe bij je volgende Excel-import (bv. "ISO 9001, FSC"), of vul het direct in op een bedrijfsprofiel.
</div>
{% endif %}
    """
    pagina = render_simple_page("Certifications", "certificeringen", inhoud)
    return render_template_string(pagina, cert_rijen=cert_rijen, kpis=kpis)

@materialen_bp.route("/materialen")
def materialen():
    taxonomie = laad_materiaal_taxonomie()

    materialen_data = []
    for categorie, kwaliteiten_lijst in taxonomie.items():
        bedrijven_in_categorie = [b for b in ENF_BEDRIJVEN if categorie.strip().lower() in b.get("materialen","").lower()]
        landen = {b.get("land","") for b in bedrijven_in_categorie}

        kwaliteit_tellingen = {}
        for kw in kwaliteiten_lijst:
            aantal_kw = sum(1 for b in ENF_BEDRIJVEN if kw.strip().lower() in b.get("kwaliteiten","").lower())
            if aantal_kw > 0:
                kwaliteit_tellingen[kw] = aantal_kw
        top_kwaliteiten = sorted(kwaliteit_tellingen.items(), key=lambda x: -x[1])[:4]
        kwaliteiten_tekst = ", ".join(kw for kw, _ in top_kwaliteiten)

        volume_totaal = 0.0
        for b in bedrijven_in_categorie:
            volumes_dict = b.get("materiaal_volumes", {})
            if isinstance(volumes_dict, dict):
                for mat_naam, waarde in volumes_dict.items():
                    if mat_naam.strip().lower() == categorie.strip().lower() or any(mat_naam.strip().lower() == kw.strip().lower() for kw in kwaliteiten_lijst):
                        volume_totaal += parse_hoeveelheid_getal(waarde)

        materialen_data.append({
            "naam": categorie, "kwaliteiten": kwaliteiten_tekst, "bedrijven": len(bedrijven_in_categorie),
            "volume": (f"{volume_totaal:,.0f}" if volume_totaal else ""), "landen": len(landen),
        })

    materialen_data.sort(key=lambda x: -x["bedrijven"])
    max_bedrijven = max([m["bedrijven"] for m in materialen_data], default=1)
    for m in materialen_data:
        m["aandeel"] = f"{round(m['bedrijven'] / max_bedrijven * 100, 1) if max_bedrijven else 0}%"

    inhoud = """
<div class="page-title">Materials</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Alle materialen en kwaliteiten in de database, met dekking en volume</p>

<div class="data-thead" style="border-radius:var(--radius-md) var(--radius-md) 0 0;">
    <span style="flex:1.4;" data-sort="naam">Materiaal</span>
    <span style="flex:1.6;" data-sort="kwaliteiten">Kwaliteiten</span>
    <span style="width:110px;text-align:right;" data-sort="bedrijven">Bedrijven</span>
    <span style="width:120px;text-align:right;" data-sort="volume">Volume t/j</span>
    <span style="width:180px;">Aandeel</span>
    <span style="width:80px;text-align:right;" data-sort="landen">Landen</span>
</div>
<div id="matLijst" style="border:1px solid var(--gray-200);border-top:none;border-radius:0 0 var(--radius-md) var(--radius-md);overflow:hidden;">
    {% for m in materialen_data %}
    <a class="data-row" href="/?materiaal={{ m.naam|urlencode }}"
       data-naam="{{ m.naam|e }}" data-kwaliteiten="{{ m.kwaliteiten|default('',true)|e }}"
       data-bedrijven="{{ m.bedrijven|default(0,true) }}" data-volume="{{ m.volume|default('',true)|e }}" data-landen="{{ m.landen|default(0,true) }}">
        <span style="flex:1.4;"><b style="color:var(--gray-800);">{{ m.naam }}</b></span>
        <span style="flex:1.6;" class="zacht">{{ m.kwaliteiten|default('—',true) }}</span>
        <span style="width:110px;text-align:right;" class="num">{{ m.bedrijven }}</span>
        <span style="width:120px;text-align:right;" class="num">{{ m.volume|default('—',true) }}</span>
        <span style="width:180px;display:flex;align-items:center;gap:10px;">
            <span class="mat-bar-track" style="flex:1;"><span class="mat-bar-fill" style="width:{{ m.aandeel }}"></span></span>
            <span style="font-size:11.5px;color:var(--gray-400);width:36px;text-align:right;">{{ m.aandeel }}</span>
        </span>
        <span style="width:80px;text-align:right;" class="zacht">{{ m.landen|default('—',true) }}</span>
    </a>
    {% else %}
    <div class="lege-staat">Nog geen grondstofgroepen. Ga naar Instellingen → Materialen beheren.</div>
    {% endfor %}
</div>
<div style="display:flex;justify-content:space-between;padding:10px 4px;font-size:0.8rem;color:var(--gray-400);">
    <span>{{ materialen_data|length }} materialen</span>
    <a href="/export-csv" style="color:var(--brand-600);text-decoration:none;font-weight:600;">Export naar CSV</a>
</div>
<style>
.mat-bar-track { height:5px; background:var(--gray-100); border-radius:6px; position:relative; overflow:hidden; }
.mat-bar-fill { position:absolute; top:0; left:0; bottom:0; background:var(--brand-600); }
</style>
<script>
(function () {
    var lijst = document.getElementById("matLijst");
    if (!lijst) return;
    var koppen = document.querySelectorAll(".data-thead [data-sort]");
    var richting = "desc", sleutel = null;
    var getal = function (v) { return parseFloat((v || "").replace(/[^\\d,.-]/g, "").replace(/\\./g, "").replace(",", ".")) || 0; };
    koppen.forEach(function (kop) {
        kop.addEventListener("click", function () {
            var k = kop.dataset.sort;
            richting = (sleutel === k && richting === "desc") ? "asc" : "desc";
            sleutel = k;
            koppen.forEach(function (x) { x.textContent = x.textContent.replace(/ [\\u2191\\u2193]$/, ""); });
            kop.textContent += richting === "desc" ? " \\u2193" : " \\u2191";
            var rijen = Array.prototype.slice.call(lijst.querySelectorAll(".data-row"));
            rijen.sort(function (a, b) {
                var va = a.dataset[k] || "", vb = b.dataset[k] || "";
                var numeriek = /^[\\d.,\\s-]+$/.test(va) && /^[\\d.,\\s-]+$/.test(vb) && va !== "";
                var r = numeriek ? getal(va) - getal(vb) : va.localeCompare(vb, "nl");
                return richting === "asc" ? r : -r;
            });
            rijen.forEach(function (r) { lijst.appendChild(r); });
        });
    });
})();
</script>
    """
    pagina = render_simple_page("Materials", "materialen", inhoud)
    return render_template_string(pagina, materialen_data=materialen_data, totaal=len(ENF_BEDRIJVEN))