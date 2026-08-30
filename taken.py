"""
taken.py — Blueprint voor de Takenlijst-module.

Persoonlijke of team-taken, met een vaste statusflow:
Toegewezen -> Aangenomen -> In proces -> Afgehandeld.

Een taak kan drie vormen hebben:
- Persoonlijk: toegewezen aan één specifieke gebruiker, alleen voor die
  gebruiker (en admins) zichtbaar.
- Team: toegewezen aan een heel team (uit Afdelingen & Teams) — iedereen in
  dat team ziet 'm en kan 'm aannemen, waarna de taak persoonlijk wordt.
- Gedeeld: persoonlijk van één eigenaar, maar ook zichtbaar voor de rest van
  het team (voor coördinatie/overzicht, niet om over te nemen).

Geen aparte afdelingsbeperking (PAGINA_AFDELINGEN) — dit is een hulpmiddel
voor iedereen, ongeacht afdeling.

Registratie in app.py met: app.register_blueprint(taken_bp)
"""
import uuid
import datetime
from flask import Blueprint, request, session, redirect, url_for, render_template_string

from core import (
    laad_taken, bewaar_taken, TAAK_STATUSSEN, laad_users, laad_organisatiestructuur,
    render_simple_page, is_huidige_gebruiker_admin,
)

taken_bp = Blueprint("taken", __name__)

def _eigen_team():
    """(org_afdeling, team) van de ingelogde gebruiker, of (None, None)."""
    users = laad_users()
    info = users.get(session.get("gebruikersnaam", ""), {})
    return info.get("org_afdeling", ""), info.get("team", "")

def _taak_zichtbaar_voor_mij(taak, gebruikersnaam, eigen_org_afdeling, eigen_team):
    """Mag ik deze taak zien? Persoonlijk: alleen de toegewezen gebruiker (of
    nog niemand toegewezen bij een team-taak). Team: iedereen in dat team.
    Gedeeld: de eigenaar + iedereen in diens team."""
    if is_huidige_gebruiker_admin():
        return True
    if taak["toewijzing_type"] == "persoonlijk":
        return taak.get("toegewezen_aan_gebruiker") == gebruikersnaam
    # team of gedeeld: zichtbaar voor het hele team, plus (bij gedeeld) altijd voor de eigenaar zelf
    if taak.get("toegewezen_aan_gebruiker") == gebruikersnaam:
        return True
    if not eigen_org_afdeling or not eigen_team:
        return False
    return taak.get("toegewezen_aan_org_afdeling") == eigen_org_afdeling and taak.get("toegewezen_aan_team") == eigen_team

@taken_bp.route("/taken")
def taken_pagina():
    gebruikersnaam = session.get("gebruikersnaam", "")
    eigen_org_afdeling, eigen_team = _eigen_team()
    alle_taken = laad_taken()
    mijn_taken = [t for t in alle_taken if _taak_zichtbaar_voor_mij(t, gebruikersnaam, eigen_org_afdeling, eigen_team)]

    kolommen = {status: [] for status in TAAK_STATUSSEN}
    for t in sorted(mijn_taken, key=lambda t: t.get("vervaldatum") or "9999-99-99"):
        kolommen.setdefault(t.get("status", "Toegewezen"), []).append(t)

    _vandaag = datetime.date.today().isoformat()

    inhoud = """
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
    <div class="page-title" style="margin-bottom:0;">Mijn takenlijst</div>
    <a href="/taken/nieuw" style="padding:8px 16px;background:var(--brand-600);color:#fff;text-decoration:none;border-radius:6px;font-size:12.5px;font-weight:700;">+ Taak toevoegen</a>
</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Persoonlijke taken, teamtaken (iedereen in je team kan ze aannemen) en gedeelde taken (van je teamgenoten, ter info).</p>

<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px;align-items:start;">
    {% for status in statussen %}
    <div>
        <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:8px;padding-bottom:6px;border-bottom:2px solid var(--gray-800);">{{ status }} <span style="color:var(--gray-300);">({{ kolommen[status]|length }})</span></div>
        {% for t in kolommen[status] %}
        <a href="/taken/{{ t.id }}" style="display:block;background:#fff;border:1px solid var(--gray-200);border-radius:8px;padding:10px 12px;margin-bottom:8px;text-decoration:none;color:inherit;">
            <div style="font-size:12.5px;font-weight:700;color:var(--gray-800);margin-bottom:4px;">{{ t.titel }}</div>
            {% if t.vervaldatum %}<div style="font-size:11px;color:{{ '#dc2626' if t.vervaldatum < vandaag and t.status != 'Afgehandeld' else 'var(--gray-400)' }};margin-bottom:4px;">{{ '⚠ ' if t.vervaldatum < vandaag and t.status != 'Afgehandeld' else '' }}Vervalt: {{ t.vervaldatum }}</div>{% endif %}
            <div style="font-size:10.5px;color:var(--gray-300);">
                {% if t.toewijzing_type == "persoonlijk" %}Persoonlijk — {{ t.toegewezen_aan_gebruiker }}
                {% elif t.toewijzing_type == "team" %}Team — {{ t.toegewezen_aan_team }}{% if t.toegewezen_aan_gebruiker %} ({{ t.toegewezen_aan_gebruiker }}){% endif %}
                {% else %}Gedeeld — {{ t.toegewezen_aan_gebruiker }} ({{ t.toegewezen_aan_team }})
                {% endif %}
            </div>
        </a>
        {% else %}
        <div style="font-size:11.5px;color:var(--gray-300);padding:8px 0;">Geen taken.</div>
        {% endfor %}
    </div>
    {% endfor %}
</div>
    """
    pagina = render_simple_page("Takenlijst", "taken", inhoud)
    return render_template_string(pagina, kolommen=kolommen, statussen=TAAK_STATUSSEN, vandaag=_vandaag)

@taken_bp.route("/taken/nieuw", methods=["GET", "POST"])
def taken_nieuw():
    if request.method == "POST":
        taken = laad_taken()
        toewijzing_type = request.form.get("toewijzing_type", "persoonlijk")
        nieuw = {
            "id": str(uuid.uuid4()),
            "titel": request.form.get("titel", "").strip(),
            "omschrijving": request.form.get("omschrijving", "").strip(),
            "vervaldatum": request.form.get("vervaldatum", "").strip(),
            "toewijzing_type": toewijzing_type,
            "status": "Toegewezen",
            "aangemaakt_door": session.get("gebruikersnaam", ""),
            "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
        }
        if toewijzing_type == "persoonlijk":
            nieuw["toegewezen_aan_gebruiker"] = request.form.get("toegewezen_aan_gebruiker", "").strip()
            nieuw["toegewezen_aan_org_afdeling"] = ""
            nieuw["toegewezen_aan_team"] = ""
        elif toewijzing_type == "team":
            nieuw["toegewezen_aan_gebruiker"] = ""
            nieuw["toegewezen_aan_org_afdeling"] = request.form.get("toegewezen_aan_org_afdeling", "").strip()
            nieuw["toegewezen_aan_team"] = request.form.get("toegewezen_aan_team", "").strip()
        else:  # gedeeld: eigenaar = ikzelf, team = mijn eigen team
            _gedeeld_org_afdeling, _gedeeld_team = _eigen_team()
            nieuw["toegewezen_aan_gebruiker"] = session.get("gebruikersnaam", "")
            nieuw["toegewezen_aan_org_afdeling"] = _gedeeld_org_afdeling
            nieuw["toegewezen_aan_team"] = _gedeeld_team

        if nieuw["titel"]:
            taken.append(nieuw)
            bewaar_taken(taken)
        return redirect(url_for("taken.taken_pagina"))

    organisatiestructuur = laad_organisatiestructuur()
    alle_users = laad_users()
    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/taken" style="color:var(--gray-400);text-decoration:none;">Takenlijst</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">Nieuw</span>
</div>
<div class="page-title">Taak toevoegen</div>

<form method="POST" style="max-width:520px;">
    <div style="margin-bottom:10px;">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Titel</label>
        <input type="text" name="titel" required style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
    </div>
    <div style="margin-bottom:10px;">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Omschrijving (optioneel)</label>
        <textarea name="omschrijving" rows="3" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;"></textarea>
    </div>
    <div style="margin-bottom:16px;">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Vervaldatum (optioneel)</label>
        <input type="date" name="vervaldatum" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
    </div>

    <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Voor wie</div>
    <div style="margin-bottom:10px;display:flex;gap:14px;">
        <label style="display:flex;align-items:center;gap:6px;font-size:12.5px;cursor:pointer;">
            <input type="radio" name="toewijzing_type" value="persoonlijk" checked onchange="wisselToewijzing()"> Persoonlijk
        </label>
        <label style="display:flex;align-items:center;gap:6px;font-size:12.5px;cursor:pointer;">
            <input type="radio" name="toewijzing_type" value="team" onchange="wisselToewijzing()"> Voor een team
        </label>
        <label style="display:flex;align-items:center;gap:6px;font-size:12.5px;cursor:pointer;">
            <input type="radio" name="toewijzing_type" value="gedeeld" onchange="wisselToewijzing()"> Van mij, gedeeld met mijn team
        </label>
    </div>

    <div id="persoonlijk_blok" style="margin-bottom:16px;">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Toewijzen aan</label>
        <select name="toegewezen_aan_gebruiker" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
            <option value="">Mezelf ({{ eigen_gebruikersnaam }})</option>
            {% for gnaam in alle_users.keys() %}{% if gnaam != eigen_gebruikersnaam %}<option value="{{ gnaam }}">{{ gnaam }}</option>{% endif %}{% endfor %}
        </select>
    </div>
    <div id="team_blok" style="display:none;margin-bottom:16px;">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <div>
                <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Afdeling</label>
                <select name="toegewezen_aan_org_afdeling" id="taak_org_afdeling_select" onchange="verversTaakTeams()" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
                    <option value="">— kies —</option>
                    {% for a in organisatiestructuur.keys() %}<option value="{{ a }}">{{ a }}</option>{% endfor %}
                </select>
            </div>
            <div>
                <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Team</label>
                <select name="toegewezen_aan_team" id="taak_team_select" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;">
                    <option value="">— kies eerst een afdeling —</option>
                </select>
            </div>
        </div>
    </div>

    <button type="submit" style="padding:9px 20px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">Taak aanmaken</button>
    <a href="/taken" style="margin-left:10px;font-size:12.5px;color:var(--gray-400);text-decoration:none;">Annuleren</a>
</form>

<script>
var ORGANISATIESTRUCTUUR_TAAK = {{ organisatiestructuur|tojson }};
function wisselToewijzing() {
    var type = document.querySelector('input[name="toewijzing_type"]:checked').value;
    document.getElementById("persoonlijk_blok").style.display = (type === "persoonlijk") ? "block" : "none";
    document.getElementById("team_blok").style.display = (type === "team") ? "block" : "none";
}
function verversTaakTeams() {
    var afdeling = document.getElementById("taak_org_afdeling_select").value;
    var teamSelect = document.getElementById("taak_team_select");
    var teams = ORGANISATIESTRUCTUUR_TAAK[afdeling] || [];
    teamSelect.innerHTML = '<option value="">— kies —</option>';
    teams.forEach(function(t) {
        var optie = document.createElement("option");
        optie.value = t;
        optie.textContent = t;
        teamSelect.appendChild(optie);
    });
}
</script>
    """
    pagina = render_simple_page("Taak toevoegen", "taken", inhoud)
    return render_template_string(pagina, organisatiestructuur=organisatiestructuur, alle_users=alle_users,
                                    eigen_gebruikersnaam=session.get("gebruikersnaam",""))

@taken_bp.route("/taken/<taak_id>")
def taken_detail(taak_id):
    taken = laad_taken()
    taak = next((t for t in taken if t["id"] == taak_id), None)
    if not taak:
        pagina = render_simple_page("Niet gevonden", "taken", '<div class="page-title">Taak niet gevonden</div><div class="lege-staat">Deze taak bestaat niet (meer). <a href="/taken">Terug naar de takenlijst</a></div>')
        return render_template_string(pagina), 404

    gebruikersnaam = session.get("gebruikersnaam", "")
    eigen_org_afdeling, eigen_team = _eigen_team()
    if not _taak_zichtbaar_voor_mij(taak, gebruikersnaam, eigen_org_afdeling, eigen_team):
        pagina = render_simple_page("Geen toegang", "taken", '<div class="page-title">Geen toegang</div><div class="lege-staat">Deze taak is niet voor jou of je team. <a href="/taken">Terug naar de takenlijst</a></div>')
        return render_template_string(pagina), 403

    # Wat kan ik met deze taak: een team-taak (nog niemand toegewezen) kan
    # iedereen in het team AANNEMEN, waarna hij van diegene wordt. Een
    # persoonlijke/gedeelde taak kan alleen de eigenaar zelf verder zetten.
    mag_aannemen = (taak["toewijzing_type"] == "team" and not taak.get("toegewezen_aan_gebruiker") and taak["status"] == "Toegewezen")
    mag_status_wijzigen = (taak.get("toegewezen_aan_gebruiker") == gebruikersnaam) or is_huidige_gebruiker_admin()

    inhoud = """
<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/taken" style="color:var(--gray-400);text-decoration:none;">Takenlijst</a> &nbsp;/&nbsp; <span style="color:var(--gray-600);">{{ taak.titel }}</span>
</div>
<div class="page-title">{{ taak.titel }}</div>

<div style="max-width:560px;">
    <div style="background:var(--gray-50);border-radius:8px;padding:14px 16px;font-size:12.5px;color:var(--gray-600);margin-bottom:16px;">
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
            <div><b>Status:</b> {{ taak.status }}</div>
            <div><b>Vervaldatum:</b> {{ taak.vervaldatum or '—' }}</div>
            <div><b>Type:</b> {{ {"persoonlijk":"Persoonlijk", "team":"Team", "gedeeld":"Gedeeld met team"}[taak.toewijzing_type] }}</div>
            <div><b>Toegewezen aan:</b> {{ taak.toegewezen_aan_gebruiker or ('Team: ' + taak.toegewezen_aan_team) if taak.toegewezen_aan_gebruiker or taak.toegewezen_aan_team else '—' }}</div>
            <div><b>Aangemaakt door:</b> {{ taak.aangemaakt_door }}</div>
            <div><b>Aangemaakt op:</b> {{ taak.aangemaakt }}</div>
        </div>
        {% if taak.omschrijving %}<div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--gray-200);">{{ taak.omschrijving }}</div>{% endif %}
    </div>

    {% if mag_aannemen %}
    <form method="POST" action="/taken/{{ taak.id }}/aannemen" style="margin-bottom:10px;">
        <button type="submit" style="padding:9px 18px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">Taak aannemen</button>
    </form>
    {% endif %}

    {% if mag_status_wijzigen and not mag_aannemen %}
    <form method="POST" action="/taken/{{ taak.id }}/status" style="display:flex;gap:8px;align-items:center;">
        <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;">Status wijzigen:</label>
        <select name="nieuwe_status" onchange="this.form.requestSubmit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
            {% for s in statussen %}<option value="{{ s }}" {% if taak.status == s %}selected{% endif %}>{{ s }}</option>{% endfor %}
        </select>
    </form>
    {% endif %}
</div>
    """
    pagina = render_simple_page(taak["titel"], "taken", inhoud)
    return render_template_string(pagina, taak=taak, mag_aannemen=mag_aannemen, mag_status_wijzigen=mag_status_wijzigen,
                                    statussen=TAAK_STATUSSEN)

@taken_bp.route("/taken/<taak_id>/aannemen", methods=["POST"])
def taken_aannemen(taak_id):
    taken = laad_taken()
    taak = next((t for t in taken if t["id"] == taak_id), None)
    gebruikersnaam = session.get("gebruikersnaam", "")
    eigen_org_afdeling, eigen_team = _eigen_team()
    if taak and taak["toewijzing_type"] == "team" and not taak.get("toegewezen_aan_gebruiker"):
        if taak.get("toegewezen_aan_org_afdeling") == eigen_org_afdeling and taak.get("toegewezen_aan_team") == eigen_team:
            taak["toegewezen_aan_gebruiker"] = gebruikersnaam
            taak["status"] = "Aangenomen"
            bewaar_taken(taken)
    return redirect(url_for("taken.taken_detail", taak_id=taak_id))

@taken_bp.route("/taken/<taak_id>/status", methods=["POST"])
def taken_status_wijzigen(taak_id):
    taken = laad_taken()
    taak = next((t for t in taken if t["id"] == taak_id), None)
    gebruikersnaam = session.get("gebruikersnaam", "")
    nieuwe_status = request.form.get("nieuwe_status", "")
    if taak and nieuwe_status in TAAK_STATUSSEN and (taak.get("toegewezen_aan_gebruiker") == gebruikersnaam or is_huidige_gebruiker_admin()):
        taak["status"] = nieuwe_status
        bewaar_taken(taken)
    return redirect(url_for("taken.taken_detail", taak_id=taak_id))