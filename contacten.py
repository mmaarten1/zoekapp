"""
contacten.py — Blueprint voor de Contacten-module.

Bevat: /contacten (GET/POST) — contactpersonen bij bedrijven bekijken,
toevoegen, verwijderen, doorzoeken op naam/bedrijf/e-mail/accountmanager.

Registratie in app.py met: app.register_blueprint(contacten_bp)
"""
import uuid
import datetime
from flask import Blueprint, request, session, redirect, url_for, render_template_string

from core import (
    laad_contactpersonen, bewaar_contactpersonen, laad_accountmanagers,
    is_huidige_gebruiker_admin, ENF_BEDRIJVEN, render_simple_page, vereist_afdeling_of_403,
)

contacten_bp = Blueprint("contacten", __name__)

@contacten_bp.route("/contacten", methods=["GET", "POST"])
def contacten():
    _guard = vereist_afdeling_of_403("contacten")
    if _guard: return _guard
    if request.method == "POST":
        actie = request.form.get("actie", "")
        personen = laad_contactpersonen()

        if actie == "toevoegen":
            nieuw = {
                "id": str(uuid.uuid4()),
                "naam": request.form.get("naam", "").strip(),
                "bedrijf": request.form.get("bedrijf", "").strip(),
                "rol": request.form.get("rol", "").strip(),
                "email": request.form.get("email", "").strip(),
                "telefoon": request.form.get("telefoon", "").strip(),
                "laatst": request.form.get("laatst", "") or datetime.date.today().isoformat(),
                "gebruiker": session.get("gebruikersnaam", ""),
                "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
            }
            if nieuw["naam"] and nieuw["bedrijf"]:
                personen.append(nieuw)
                bewaar_contactpersonen(personen)

        elif actie == "verwijderen":
            persoon_id = request.form.get("persoon_id", "")
            doel = next((p for p in personen if p["id"] == persoon_id), None)
            if doel and (doel.get("gebruiker") == session.get("gebruikersnaam","") or is_huidige_gebruiker_admin()):
                personen = [p for p in personen if p["id"] != persoon_id]
                bewaar_contactpersonen(personen)

        return redirect(url_for("contacten.contacten", **request.args))

    zoekterm = request.args.get("zoekterm", "").strip().lower()
    gekozen_am = request.args.get("accountmanager", "")

    accountmanagers_alle = laad_accountmanagers()
    _bedrijven_land_lookup = {b["naam"]: b.get("land","") for b in ENF_BEDRIJVEN}

    personen = laad_contactpersonen()
    bekende_namen_bedrijven = {(p["naam"].strip().lower(), p["bedrijf"].strip().lower()) for p in personen}

    contacten_lijst = []
    for p in personen:
        contacten_lijst.append({
            "id": p["id"], "naam": p["naam"], "bedrijf": p["bedrijf"], "rol": p.get("rol",""),
            "email": p.get("email",""), "telefoon": p.get("telefoon",""),
            "accountmanager": accountmanagers_alle.get(p["bedrijf"], ""), "laatst": p.get("laatst",""),
            "eigen": p.get("gebruiker") == session.get("gebruikersnaam",""),
        })

    # Bedrijven met een los ingevuld 'contactpersoon'-veld die nog geen formeel record hebben: ook tonen (niet verzinnen, wel niet verliezen)
    for b in ENF_BEDRIJVEN:
        naam_veld = (b.get("contactpersoon","") or "").strip()
        if naam_veld and (naam_veld.lower(), b["naam"].strip().lower()) not in bekende_namen_bedrijven:
            contacten_lijst.append({
                "id": "", "naam": naam_veld, "bedrijf": b["naam"], "rol": "", "email": "", "telefoon": b.get("telefoon",""),
                "accountmanager": accountmanagers_alle.get(b["naam"], ""), "laatst": "", "eigen": False,
            })

    if zoekterm:
        contacten_lijst = [c for c in contacten_lijst if zoekterm in c["naam"].lower() or zoekterm in c["bedrijf"].lower() or zoekterm in c["email"].lower()]
    if gekozen_am:
        contacten_lijst = [c for c in contacten_lijst if c["accountmanager"] == gekozen_am]
    contacten_lijst.sort(key=lambda c: c["naam"])

    alle_accountmanagers = sorted({v for v in accountmanagers_alle.values() if v})

    inhoud = """
<style>
.data-thead, .data-row { display: flex; align-items: center; padding: 0 var(--space-4); }
.data-thead { padding-top: 10px; padding-bottom: 10px; background: var(--gray-50); border-bottom: 1px solid var(--gray-200); font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: #7d8792; }
.data-thead span[data-sort] { cursor: pointer; user-select: none; }
.data-thead span[data-sort]:hover { color: var(--brand-600); }
.data-row { padding-top: 11px; padding-bottom: 11px; border-bottom: 1px solid var(--gray-100); font-size: 12.5px; text-decoration: none; color: inherit; }
.data-row:hover { background: #f9fbfc; }
.data-row .zacht { color: #4b5563; font-size: 12px; }
</style>

<div class="page-title">Contacten</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:16px;font-size:0.85rem;">Contactpersonen bij bedrijven, met rol en laatste contactmoment</p>

<form method="GET" style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
    <input type="text" name="zoekterm" value="{{ zoekterm }}" placeholder="Naam, bedrijf of e-mail" style="flex:1;max-width:280px;padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
    <select name="accountmanager" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle accountmanagers</option>
        {% for a in alle_accountmanagers %}<option value="{{ a }}" {% if gekozen_am == a %}selected{% endif %}>{{ a }}</option>{% endfor %}
    </select>
    <button type="submit" class="btn-nav btn-nav-primary" style="border:none;cursor:pointer;">Zoeken</button>
    {% if zoekterm or gekozen_am %}<a href="/contacten" style="font-size:12px;color:var(--gray-400);text-decoration:none;">Wis filters</a>{% endif %}
</form>

<div style="max-width:460px;background:#fff;border:1px solid var(--gray-200);border-radius:10px;padding:14px 16px;margin-bottom:20px;">
    <div class="dg-kaart-titel" style="margin-bottom:8px;">Contactpersoon toevoegen</div>
    <form method="POST">
        <input type="hidden" name="actie" value="toevoegen">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
            <input type="text" name="naam" placeholder="Naam" required style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
            <input type="text" name="bedrijf" placeholder="Bedrijf" required list="bedrijvenLijstContacten" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
        </div>
        <datalist id="bedrijvenLijstContacten">{% for naam in bedrijfnamen_lijst %}<option value="{{ naam }}">{% endfor %}</datalist>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
            <input type="text" name="rol" placeholder="Rol (optioneel)" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
            <input type="text" name="telefoon" placeholder="Telefoon (optioneel)" style="padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
        </div>
        <input type="email" name="email" placeholder="E-mail (optioneel)" style="width:100%;padding:7px 9px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;margin-bottom:8px;box-sizing:border-box;">
        <button type="submit" class="btn-nav btn-nav-primary" style="border:none;cursor:pointer;width:100%;">+ Toevoegen</button>
    </form>
</div>

{% if contacten_lijst %}
<div class="data-thead" style="border-radius:var(--radius-md) var(--radius-md) 0 0;">
    <span style="flex:1.2;" data-sort="naam">Contactpersoon</span>
    <span style="flex:1.4;" data-sort="bedrijf">Bedrijf</span>
    <span style="flex:1;" data-sort="rol">Rol</span>
    <span style="flex:1.2;" data-sort="email">E-mail</span>
    <span style="width:130px;" data-sort="telefoon">Telefoon</span>
    <span style="width:110px;" data-sort="accountmanager">Accountmgr.</span>
    <span style="width:90px;text-align:right;" data-sort="laatst">Contact</span>
    <span style="width:26px;"></span>
</div>
<div id="contactenLijst" style="border:1px solid var(--gray-200);border-top:none;border-radius:0 0 var(--radius-md) var(--radius-md);overflow:hidden;">
    {% for c in contacten_lijst %}
    <div class="data-row"
       data-naam="{{ c.naam|e }}" data-bedrijf="{{ c.bedrijf|e }}" data-rol="{{ c.rol|default('',true)|e }}"
       data-email="{{ c.email|default('',true)|e }}" data-telefoon="{{ c.telefoon|default('',true)|e }}"
       data-accountmanager="{{ c.accountmanager|default('',true)|e }}" data-laatst="{{ c.laatst|default('',true)|e }}">
        <span style="flex:1.2;"><a href="/bedrijf/{{ c.bedrijf|urlencode }}" style="font-weight:600;color:var(--gray-800);text-decoration:none;">{{ c.naam }}</a></span>
        <span style="flex:1.4;" class="zacht">{{ c.bedrijf }}</span>
        <span style="flex:1;" class="zacht">{{ c.rol|default('—',true) }}</span>
        <span style="flex:1.2;" class="zacht" style="color:var(--brand-600);">{{ c.email|default('—',true) }}</span>
        <span style="width:130px;" class="num">{{ c.telefoon|default('—',true) }}</span>
        <span style="width:110px;" class="zacht">{{ c.accountmanager|default('—',true) }}</span>
        <span style="width:90px;text-align:right;font-size:11.5px;color:var(--gray-400);">{{ c.laatst|default('—',true) }}</span>
        <span style="width:26px;">
            {% if c.id and c.eigen %}
            <form method="POST" onsubmit="return confirm('Contactpersoon verwijderen?');" style="margin:0;">
                <input type="hidden" name="actie" value="verwijderen"><input type="hidden" name="persoon_id" value="{{ c.id }}">
                <button type="submit" style="background:none;border:none;color:var(--gray-300);cursor:pointer;">✕</button>
            </form>
            {% endif %}
        </span>
    </div>
    {% endfor %}
</div>
<div style="display:flex;justify-content:space-between;padding:10px 4px;font-size:0.8rem;color:var(--gray-400);">
    <span>{{ contacten_lijst|length }} contactpersonen</span>
    <a href="/export-csv" style="color:var(--brand-600);text-decoration:none;font-weight:600;">Export naar CSV</a>
</div>
<script>
(function () {
    var lijst = document.getElementById("contactenLijst");
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
<div class="lege-staat">Geen contactpersonen gevonden.</div>
{% endif %}
    """
    pagina = render_simple_page("Contacten", "contacten", inhoud)
    return render_template_string(pagina, contacten_lijst=contacten_lijst, zoekterm=zoekterm, gekozen_am=gekozen_am,
                                    alle_accountmanagers=alle_accountmanagers, bedrijfnamen_lijst=sorted(_bedrijven_land_lookup.keys())[:500])