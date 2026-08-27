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
    bewaar_bedrijven, PAPIERFABRIEKEN, laad_status,
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

<div style="margin-bottom:20px;">
    <a href="/contacten/nieuw" style="display:inline-block;padding:9px 18px;background:var(--brand-600);color:#fff;text-decoration:none;border-radius:6px;font-size:13px;font-weight:700;">+ Contact toevoegen</a>
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

@contacten_bp.route("/contacten/nieuw")
def contacten_nieuw_keuze():
    """Startpunt van het aanmaken van een contactpersoon: eerst kiezen tussen een
    nieuw bedrijf (bedrijf en contact tegelijk aanmaken) of een bestaand bedrijf
    (extra contactpersoon toevoegen, of een bestaande vervangen)."""
    _guard = vereist_afdeling_of_403("contacten")
    if _guard: return _guard

    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/contacten" style="color:var(--gray-400);text-decoration:none;">Contacten</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">Nieuw</span>
</div>
<div class="page-title">Contactpersoon toevoegen</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:24px;font-size:0.85rem;">Hoort deze persoon bij een bedrijf dat al in het systeem staat, of bij een nieuw bedrijf?</p>

<div style="display:flex;gap:16px;max-width:600px;">
    <a href="/contacten/nieuw/bedrijf" style="flex:1;display:block;padding:20px;border:1px solid var(--gray-200);border-radius:10px;text-decoration:none;color:inherit;">
        <div style="font-weight:700;color:var(--gray-800);font-size:14px;margin-bottom:6px;">Nieuw bedrijf</div>
        <div style="font-size:12.5px;color:var(--gray-500);">Het bedrijf staat nog niet in het systeem — bedrijf en contactpersoon in één keer aanmaken.</div>
    </a>
    <a href="/contacten/nieuw/bestaand" style="flex:1;display:block;padding:20px;border:1px solid var(--gray-200);border-radius:10px;text-decoration:none;color:inherit;">
        <div style="font-weight:700;color:var(--gray-800);font-size:14px;margin-bottom:6px;">Bestaand bedrijf</div>
        <div style="font-size:12.5px;color:var(--gray-500);">Een extra contactpersoon toevoegen bij een bedrijf dat al bestaat, of een bestaande vervangen.</div>
    </a>
</div>
    """
    pagina = render_simple_page("Contact toevoegen", "contacten", inhoud)
    return render_template_string(pagina)

@contacten_bp.route("/contacten/nieuw/bedrijf", methods=["GET", "POST"])
def contacten_nieuw_bedrijf():
    """Nieuw bedrijf + contactpersoon in één keer aanmaken."""
    _guard = vereist_afdeling_of_403("contacten")
    if _guard: return _guard

    fout = None
    if request.method == "POST":
        bedrijfsnaam = request.form.get("bedrijfsnaam", "").strip()
        contactnaam = request.form.get("naam", "").strip()
        if not bedrijfsnaam or not contactnaam:
            fout = "Bedrijfsnaam en naam van de contactpersoon zijn verplicht."
        elif any(b["naam"].strip().lower() == bedrijfsnaam.lower() for b in ENF_BEDRIJVEN):
            fout = f"'{bedrijfsnaam}' bestaat al als bedrijf — kies bij 'Bestaand bedrijf' om daar een contactpersoon aan toe te voegen."
        else:
            nieuw_bedrijf = {
                "naam": bedrijfsnaam, "url": "", "regio": request.form.get("regio", "").strip(),
                "land": request.form.get("land", "").strip(), "klanttype": "",
                "materialen": request.form.get("materialen", "").strip(), "volume": "",
                "lat": None, "lon": None,
            }
            ENF_BEDRIJVEN.append(nieuw_bedrijf)
            bewaar_bedrijven()

            personen = laad_contactpersonen()
            personen.append({
                "id": str(uuid.uuid4()), "naam": contactnaam, "bedrijf": bedrijfsnaam,
                "rol": request.form.get("rol", "").strip(), "email": request.form.get("email", "").strip(),
                "telefoon": request.form.get("telefoon", "").strip(),
                "laatst": datetime.date.today().isoformat(),
                "gebruiker": session.get("gebruikersnaam", ""),
                "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
            })
            bewaar_contactpersonen(personen)
            return redirect(url_for("contacten.contacten"))

    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/contacten" style="color:var(--gray-400);text-decoration:none;">Contacten</a> &nbsp;/&nbsp;
    <a href="/contacten/nieuw" style="color:var(--gray-400);text-decoration:none;">Nieuw</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">Nieuw bedrijf</span>
</div>
<div class="page-title">Nieuw bedrijf + contactpersoon</div>
{% if fout %}<div style="background:#fef2f2;color:#dc2626;padding:10px 14px;border-radius:8px;margin-bottom:16px;font-size:12.5px;">{{ fout }}</div>{% endif %}

<form method="POST" style="max-width:520px;">
    <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Bedrijf</div>
    <input type="text" name="bedrijfsnaam" placeholder="Bedrijfsnaam" required style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;box-sizing:border-box;margin-bottom:10px;">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <input type="text" name="land" placeholder="Land (optioneel)" style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
        <input type="text" name="regio" placeholder="Regio/stad (optioneel)" style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
    </div>
    <input type="text" name="materialen" placeholder="Materialen (optioneel)" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;box-sizing:border-box;margin-bottom:20px;">

    <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Contactpersoon</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <input type="text" name="naam" placeholder="Naam" required style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
        <input type="text" name="rol" placeholder="Rol (optioneel)" style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px;">
        <input type="email" name="email" placeholder="E-mail (optioneel)" style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
        <input type="text" name="telefoon" placeholder="Telefoon (optioneel)" style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
    </div>
    <button type="submit" style="padding:9px 18px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">Bedrijf en contact aanmaken</button>
</form>
    """
    pagina = render_simple_page("Nieuw bedrijf", "contacten", inhoud)
    return render_template_string(pagina, fout=fout)

@contacten_bp.route("/contacten/nieuw/bestaand", methods=["GET", "POST"])
def contacten_nieuw_bestaand():
    """Extra contactpersoon toevoegen bij een bestaand bedrijf, of een bestaande
    contactpersoon van dat bedrijf vervangen."""
    _guard = vereist_afdeling_of_403("contacten")
    if _guard: return _guard

    fout = None
    if request.method == "POST":
        bedrijfsnaam = request.form.get("bedrijfsnaam", "").strip()
        modus = request.form.get("modus", "extra")
        contactnaam = request.form.get("naam", "").strip()
        if not bedrijfsnaam or not contactnaam:
            fout = "Bedrijf en naam van de contactpersoon zijn verplicht."
        else:
            personen = laad_contactpersonen()
            nieuwe_gegevens = {
                "naam": contactnaam, "bedrijf": bedrijfsnaam,
                "rol": request.form.get("rol", "").strip(), "email": request.form.get("email", "").strip(),
                "telefoon": request.form.get("telefoon", "").strip(),
                "laatst": datetime.date.today().isoformat(),
                "gebruiker": session.get("gebruikersnaam", ""),
                "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
            }
            if modus == "vervangen":
                te_vervangen_id = request.form.get("te_vervangen_id", "")
                doel = next((p for p in personen if p["id"] == te_vervangen_id), None)
                if doel:
                    doel.update(nieuwe_gegevens)
                    bewaar_contactpersonen(personen)
                    return redirect(url_for("contacten.contacten"))
                fout = "De te vervangen contactpersoon is niet gevonden."
            else:
                nieuwe_gegevens["id"] = str(uuid.uuid4())
                personen.append(nieuwe_gegevens)
                bewaar_contactpersonen(personen)
                return redirect(url_for("contacten.contacten"))

    gekozen_bedrijf = request.args.get("bedrijf", "").strip()
    # Alleen bedrijven die al bij Leveranciers of Klanten staan — dus daadwerkelijk
    # een toegekende status óf accountmanager hebben, net als op die pagina's.
    # Geen doorzoeking van de volledige, ongefilterde bedrijvendatabase.
    status_alle = laad_status()
    accountmanagers_alle = laad_accountmanagers()
    bedrijfnamen = sorted({
        b["naam"] for b in list(ENF_BEDRIJVEN) + list(PAPIERFABRIEKEN)
        if status_alle.get(b["naam"]) or accountmanagers_alle.get(b["naam"])
    })
    personen_bij_bedrijf = [p for p in laad_contactpersonen() if p.get("bedrijf","").strip().lower() == gekozen_bedrijf.strip().lower()] if gekozen_bedrijf else []

    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/contacten" style="color:var(--gray-400);text-decoration:none;">Contacten</a> &nbsp;/&nbsp;
    <a href="/contacten/nieuw" style="color:var(--gray-400);text-decoration:none;">Nieuw</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">Bestaand bedrijf</span>
</div>
<div class="page-title">Contactpersoon bij een bestaand bedrijf</div>
{% if fout %}<div style="background:#fef2f2;color:#dc2626;padding:10px 14px;border-radius:8px;margin-bottom:16px;font-size:12.5px;">{{ fout }}</div>{% endif %}

<form method="GET" style="max-width:520px;margin-bottom:24px;">
    <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Bedrijf kiezen</div>
    <div style="display:flex;gap:8px;">
        <input type="text" name="bedrijf" value="{{ gekozen_bedrijf }}" list="bedrijvenLijstBestaand" placeholder="Begin te typen..." required style="flex:1;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
        <datalist id="bedrijvenLijstBestaand">{% for naam in bedrijfnamen %}<option value="{{ naam }}">{% endfor %}</datalist>
        <button type="submit" style="padding:8px 16px;background:#fff;color:var(--gray-700);border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-weight:600;cursor:pointer;">Verder</button>
    </div>
</form>

{% if gekozen_bedrijf %}
<form method="POST" style="max-width:520px;">
    <input type="hidden" name="bedrijfsnaam" value="{{ gekozen_bedrijf }}">
    <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">{{ gekozen_bedrijf }}</div>

    <label style="display:flex;align-items:center;gap:8px;font-size:13px;color:var(--gray-700);margin-bottom:8px;cursor:pointer;">
        <input type="radio" name="modus" value="extra" checked onchange="document.getElementById('vervangKeuze').style.display='none';">
        Extra contactpersoon toevoegen
    </label>
    {% if personen_bij_bedrijf %}
    <label style="display:flex;align-items:center;gap:8px;font-size:13px;color:var(--gray-700);margin-bottom:12px;cursor:pointer;">
        <input type="radio" name="modus" value="vervangen" onchange="document.getElementById('vervangKeuze').style.display='block';">
        Een bestaande contactpersoon vervangen
    </label>
    <div id="vervangKeuze" style="display:none;margin-bottom:16px;padding:10px 12px;background:var(--gray-50);border-radius:8px;">
        {% for p in personen_bij_bedrijf %}
        <label style="display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--gray-600);padding:4px 0;cursor:pointer;">
            <input type="radio" name="te_vervangen_id" value="{{ p.id }}">
            {{ p.naam }}{% if p.rol %} — {{ p.rol }}{% endif %}
        </label>
        {% endfor %}
    </div>
    {% else %}
    <div style="font-size:12px;color:var(--gray-300);margin-bottom:16px;">Nog geen bestaande contactpersonen bij dit bedrijf om te vervangen.</div>
    {% endif %}

    <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Gegevens</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <input type="text" name="naam" placeholder="Naam" required style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
        <input type="text" name="rol" placeholder="Rol (optioneel)" style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px;">
        <input type="email" name="email" placeholder="E-mail (optioneel)" style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
        <input type="text" name="telefoon" placeholder="Telefoon (optioneel)" style="padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;font-family:inherit;">
    </div>
    <button type="submit" style="padding:9px 18px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">Opslaan</button>
</form>
{% endif %}
    """
    pagina = render_simple_page("Bestaand bedrijf", "contacten", inhoud)
    return render_template_string(pagina, fout=fout, gekozen_bedrijf=gekozen_bedrijf, bedrijfnamen=bedrijfnamen,
                                    personen_bij_bedrijf=personen_bij_bedrijf)