"""
notities.py — Blueprint voor de Notities-module.

Bevat: /api/notities (GET/POST/DELETE) en /notities-overzicht (teamnotities-
lijst over alle bedrijven).

Registratie in app.py met: app.register_blueprint(notities_bp)
"""
import uuid
import os
import datetime
from flask import Blueprint, request, session, jsonify, render_template_string, redirect, url_for

from core import (
    get_user_id, laad_notities, bewaar_notities, laad_accountmanagers,
    laad_meldingen, bewaar_meldingen, is_huidige_gebruiker_admin, render_simple_page,
    ENF_BEDRIJVEN, PAPIERFABRIEKEN, laad_status, laad_users, AFDELINGEN, FOTOS_MAP,
)

notities_bp = Blueprint("notities", __name__)

@notities_bp.route("/api/notities", methods=["GET"])
def get_notities():
    bedrijf = request.args.get("bedrijf", "")
    user_id = get_user_id()
    alle = laad_notities()
    lijst = alle.get(bedrijf, [])
    gewijzigd = False
    for n in lijst:
        if "id" not in n:
            n["id"] = str(uuid.uuid4())
            gewijzigd = True
    if gewijzigd:
        bewaar_notities(alle)
    zichtbaar = [n for n in lijst if n["type"] == "team" or n["user_id"] == user_id]
    return jsonify(zichtbaar)

@notities_bp.route("/api/notities", methods=["POST"])
def add_notitie():
    data = request.get_json()
    bedrijf = data.get("bedrijf", "")
    tekst = data.get("tekst", "").strip()
    type_ = data.get("type", "team")
    user_id = get_user_id()

    if not bedrijf or not tekst:
        return jsonify({"error": "Bedrijf en tekst zijn verplicht"}), 400

    alle = laad_notities()
    if bedrijf not in alle:
        alle[bedrijf] = []

    nieuwe_notitie = {
        "id": str(uuid.uuid4()),
        "tekst": tekst,
        "type": type_,
        "user_id": user_id,
        "gebruikersnaam": session.get("gebruikersnaam", ""),
        "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
    }
    alle[bedrijf].append(nieuwe_notitie)
    bewaar_notities(alle)

    if type_ == "team":
        toegewezen_am = laad_accountmanagers().get(bedrijf, "")
        if toegewezen_am and toegewezen_am != nieuwe_notitie["gebruikersnaam"]:
            alle_meldingen = laad_meldingen()
            alle_meldingen.append({
                "id": str(uuid.uuid4()),
                "tekst": f"{nieuwe_notitie['gebruikersnaam']} heeft een notitie toegevoegd bij {bedrijf} (jouw bedrijf): \"{tekst[:80]}{'...' if len(tekst) > 80 else ''}\"",
                "bedrijf": bedrijf, "van": nieuwe_notitie["gebruikersnaam"],
                "voor_gebruiker": toegewezen_am, "voor_team": "",
                "gelezen": False, "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
            })
            bewaar_meldingen(alle_meldingen)

    return jsonify(nieuwe_notitie)

@notities_bp.route("/api/notities", methods=["DELETE"])
def verwijder_notitie():
    data = request.get_json()
    bedrijf = data.get("bedrijf", "")
    notitie_id = data.get("id", "")
    huidige_gebruikersnaam = session.get("gebruikersnaam", "")

    alle = laad_notities()
    lijst = alle.get(bedrijf, [])
    doel = next((n for n in lijst if n.get("id") == notitie_id), None)
    if not doel:
        return jsonify({"error": "Notitie niet gevonden"}), 404
    # gebruikersnaam is de betrouwbare eigenaarscheck; user_id (anoniem cookie) alleen als fallback voor oude notities
    is_eigenaar = doel.get("gebruikersnaam") == huidige_gebruikersnaam if doel.get("gebruikersnaam") else doel.get("user_id") == get_user_id()
    if not is_eigenaar and not is_huidige_gebruiker_admin():
        return jsonify({"error": "Je kunt alleen je eigen notities verwijderen."}), 403

    alle[bedrijf] = [n for n in lijst if n.get("id") != notitie_id]
    bewaar_notities(alle)
    return jsonify({"ok": True})


def _notitie_sleutel(entiteit_type, entiteit_naam):
    """Bepaalt de opslagsleutel voor een notitie. Leverancier/klant gebruiken
    gewoon de kale bedrijfsnaam als sleutel — dat is de sleutel die de
    bedrijfsprofielpagina (zoeken.py) al gebruikt voor zijn notities-widget,
    dus dit blijft achterwaarts compatibel zonder dat de widget iets hoeft te
    weten van entiteit-typen. Afdeling/team/persoon krijgen een herkenbaar
    prefix, zodat ze nooit per ongeluk samenvallen met een bedrijfsnaam."""
    if entiteit_type in ("leverancier", "klant"):
        return entiteit_naam
    prefix = {"afdeling": "Afdeling", "team": "Team", "persoon": "Persoon"}.get(entiteit_type, "")
    return f"{prefix}: {entiteit_naam}" if prefix else entiteit_naam

@notities_bp.route("/notities-overzicht", methods=["GET", "POST"])
def notities_overzicht():
    if request.method == "POST":
        entiteit_type = request.form.get("entiteit_type", "").strip()
        entiteit_naam = request.form.get("entiteit_naam", "").strip()
        tekst = request.form.get("tekst", "").strip()
        if entiteit_type and entiteit_naam and tekst:
            sleutel = _notitie_sleutel(entiteit_type, entiteit_naam)
            alle_notities = laad_notities()
            alle_notities.setdefault(sleutel, [])

            foto_bestandsnaam = None
            foto = request.files.get("foto")
            if foto and foto.filename:
                extensie = foto.filename.rsplit(".", 1)[-1].lower() if "." in foto.filename else ""
                if extensie in ("jpg", "jpeg", "png", "gif", "webp"):
                    if not os.path.exists(FOTOS_MAP):
                        os.makedirs(FOTOS_MAP)
                    foto_bestandsnaam = f"{uuid.uuid4()}.{extensie}"
                    foto.save(os.path.join(FOTOS_MAP, foto_bestandsnaam))

            nieuwe_notitie = {
                "id": str(uuid.uuid4()),
                "tekst": tekst,
                "type": "team",
                "entiteit_type": entiteit_type,
                "entiteit_naam": entiteit_naam,
                "foto_bestandsnaam": foto_bestandsnaam,
                "user_id": get_user_id(),
                "gebruikersnaam": session.get("gebruikersnaam", ""),
                "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
            }
            alle_notities[sleutel].append(nieuwe_notitie)
            bewaar_notities(alle_notities)

            if entiteit_type in ("leverancier", "klant"):
                toegewezen_am = laad_accountmanagers().get(entiteit_naam, "")
                if toegewezen_am and toegewezen_am != nieuwe_notitie["gebruikersnaam"]:
                    alle_meldingen = laad_meldingen()
                    alle_meldingen.append({
                        "id": str(uuid.uuid4()),
                        "tekst": f"{nieuwe_notitie['gebruikersnaam']} heeft een notitie toegevoegd bij {entiteit_naam} (jouw bedrijf): \"{tekst[:80]}{'...' if len(tekst) > 80 else ''}\"",
                        "bedrijf": entiteit_naam, "van": nieuwe_notitie["gebruikersnaam"],
                        "voor_gebruiker": toegewezen_am, "voor_team": "",
                        "gelezen": False, "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
                    })
                    bewaar_meldingen(alle_meldingen)
        return redirect(url_for("notities.notities_overzicht"))

    alle = laad_notities()
    rijen = []
    for sleutel, lijst in alle.items():
        for n in lijst:
            if n["type"] != "team":
                continue
            entiteit_type = n.get("entiteit_type", "leverancier")  # oudere notities (van vóór deze wijziging) hadden geen entiteit_type -- default op leverancier/klant-gedrag
            entiteit_naam = n.get("entiteit_naam", sleutel)
            rijen.append({
                "sleutel": sleutel, "entiteit_type": entiteit_type, "entiteit_naam": entiteit_naam,
                "tekst": n["tekst"], "timestamp": n["timestamp"], "foto_bestandsnaam": n.get("foto_bestandsnaam"),
            })
    rijen.sort(key=lambda x: x["timestamp"], reverse=True)

    status_alle = laad_status()
    leverancier_namen = sorted(n for n, s in status_alle.items() if s == "leverancier")
    klant_namen = sorted(n for n, s in status_alle.items() if s == "klant")
    afdeling_namen = sorted(AFDELINGEN)
    team_namen = sorted({u.get("team", "").strip() for u in laad_users().values() if u.get("team", "").strip()})
    persoon_namen = sorted(laad_users().keys())

    inhoud = """
    <div class="page-title">Notities</div>

    <div id="notitieKnopRij" style="margin-bottom:24px;">
        <button type="button" onclick="document.getElementById('notitieKnopRij').style.display='none'; document.getElementById('notitieFormulier').style.display='block';" style="padding:8px 18px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">+ Notitie toevoegen</button>
    </div>
    <div id="notitieFormulier" style="display:none;max-width:560px;margin-bottom:24px;background:var(--gray-50);border-radius:10px;padding:16px;">
        <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Nieuwe teamnotitie</div>
        <form method="POST" enctype="multipart/form-data">
            <div style="margin-bottom:10px;display:flex;gap:6px;flex-wrap:wrap;">
                {% for waarde, label in [("leverancier","Leverancier"),("klant","Klant"),("afdeling","Afdeling"),("team","Team"),("persoon","Persoon")] %}
                <label style="font-size:12px;padding:6px 10px;border:1px solid var(--gray-200);border-radius:6px;cursor:pointer;">
                    <input type="radio" name="entiteit_type" value="{{ waarde }}" onchange="wisselEntiteitType('{{ waarde }}')" {% if loop.first %}checked{% endif %} style="margin-right:4px;">{{ label }}
                </label>
                {% endfor %}
            </div>
            <div style="margin-bottom:10px;">
                <select name="entiteit_naam" id="entiteit_select_leverancier" required style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
                    <option value="">Leverancier kiezen...</option>
                    {% for naam in leverancier_namen %}<option value="{{ naam }}">{{ naam }}</option>{% endfor %}
                </select>
                <select name="entiteit_naam" id="entiteit_select_klant" disabled style="display:none;width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
                    <option value="">Klant kiezen...</option>
                    {% for naam in klant_namen %}<option value="{{ naam }}">{{ naam }}</option>{% endfor %}
                </select>
                <select name="entiteit_naam" id="entiteit_select_afdeling" disabled style="display:none;width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
                    <option value="">Afdeling kiezen...</option>
                    {% for naam in afdeling_namen %}<option value="{{ naam }}">{{ naam }}</option>{% endfor %}
                </select>
                <select name="entiteit_naam" id="entiteit_select_team" disabled style="display:none;width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
                    <option value="">Team kiezen...</option>
                    {% for naam in team_namen %}<option value="{{ naam }}">{{ naam }}</option>{% endfor %}
                </select>
                <select name="entiteit_naam" id="entiteit_select_persoon" disabled style="display:none;width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
                    <option value="">Persoon kiezen...</option>
                    {% for naam in persoon_namen %}<option value="{{ naam }}">{{ naam }}</option>{% endfor %}
                </select>
                {% if not leverancier_namen %}<div style="font-size:11px;color:var(--gray-400);margin-top:4px;">Nog geen bedrijven met status 'leverancier' — zet die status bij Klanten/Leveranciers.</div>{% endif %}
            </div>
            <div style="margin-bottom:10px;">
                <textarea name="tekst" required rows="3" placeholder="Notitie..." style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;"></textarea>
            </div>
            <div style="margin-bottom:10px;">
                <label style="font-size:11.5px;color:var(--gray-500);font-weight:600;display:block;margin-bottom:4px;">Foto (optioneel)</label>
                <input type="file" name="foto" accept="image/*" style="font-size:12.5px;">
            </div>
            <button type="submit" style="padding:8px 18px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">Notitie toevoegen</button>
            <button type="button" onclick="document.getElementById('notitieFormulier').style.display='none'; document.getElementById('notitieKnopRij').style.display='block';" style="background:none;border:none;color:var(--gray-400);cursor:pointer;font-size:12.5px;margin-left:8px;">Annuleren</button>
        </form>
    </div>
    <script>
    function wisselEntiteitType(gekozen) {
        ["leverancier","klant","afdeling","team","persoon"].forEach(function(type) {
            var el = document.getElementById("entiteit_select_" + type);
            var actief = (type === gekozen);
            el.style.display = actief ? "block" : "none";
            el.disabled = !actief;
        });
    }
    </script>

    {% if rijen %}
    <div class="info-kaart" style="max-width:700px;">
        {% for r in rijen %}
        <div class="dg-activiteit-item">
            <span style="display:inline-block;font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px;background:var(--gray-100);color:var(--gray-500);text-transform:uppercase;letter-spacing:0.04em;margin-right:6px;">
                {{ {"leverancier":"Leverancier","klant":"Klant","afdeling":"Afdeling","team":"Team","persoon":"Persoon"}.get(r.entiteit_type, "Leverancier") }}
            </span>
            {% if r.entiteit_type in ("leverancier","klant") %}
            <a href="/bedrijf/{{ r.entiteit_naam|urlencode }}" style="color:var(--gray-800);font-weight:700;text-decoration:none;">{{ r.entiteit_naam }}</a>
            {% else %}
            <b style="color:var(--gray-800);">{{ r.entiteit_naam }}</b>
            {% endif %}
            <br>{{ r.tekst }}
            {% if r.foto_bestandsnaam %}<br><img src="/fotos_uploads/{{ r.foto_bestandsnaam }}" style="max-width:220px;max-height:220px;border-radius:8px;margin-top:8px;display:block;"><br>{% endif %}
            <small>{{ r.timestamp }}</small>
        </div>
        {% endfor %}
    </div>
    {% else %}
    <div class="lege-staat">Nog geen teamnotities.</div>
    {% endif %}
    """
    pagina = render_simple_page("Notities", "notities", inhoud)
    return render_template_string(pagina, rijen=rijen, leverancier_namen=leverancier_namen,
                                    klant_namen=klant_namen, afdeling_namen=afdeling_namen,
                                    team_namen=team_namen, persoon_namen=persoon_namen)