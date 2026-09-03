"""
notities.py — Blueprint voor de Notities-module.

Bevat: /api/notities (GET/POST/DELETE) en /notities-overzicht (teamnotities-
lijst over alle bedrijven).

Registratie in app.py met: app.register_blueprint(notities_bp)
"""
import uuid
import datetime
from flask import Blueprint, request, session, jsonify, render_template_string, redirect, url_for

from core import (
    get_user_id, laad_notities, bewaar_notities, laad_accountmanagers,
    laad_meldingen, bewaar_meldingen, is_huidige_gebruiker_admin, render_simple_page,
    ENF_BEDRIJVEN,
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


@notities_bp.route("/notities-overzicht", methods=["GET", "POST"])
def notities_overzicht():
    if request.method == "POST":
        bedrijf = request.form.get("bedrijf", "").strip()
        tekst = request.form.get("tekst", "").strip()
        if bedrijf and tekst:
            alle_notities = laad_notities()
            alle_notities.setdefault(bedrijf, [])
            nieuwe_notitie = {
                "id": str(uuid.uuid4()),
                "tekst": tekst,
                "type": "team",
                "user_id": get_user_id(),
                "gebruikersnaam": session.get("gebruikersnaam", ""),
                "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
            }
            alle_notities[bedrijf].append(nieuwe_notitie)
            bewaar_notities(alle_notities)

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
        return redirect(url_for("notities.notities_overzicht"))

    alle = laad_notities()
    rijen = []
    for bedrijf, lijst in alle.items():
        for n in lijst:
            if n["type"] == "team":
                rijen.append({"bedrijf": bedrijf, "tekst": n["tekst"], "timestamp": n["timestamp"]})
    rijen.sort(key=lambda x: x["timestamp"], reverse=True)

    bedrijfsnamen = sorted({b["naam"] for b in ENF_BEDRIJVEN})

    inhoud = """
    <div class="page-title">Notities</div>

    <div id="notitieKnopRij" style="margin-bottom:24px;">
        <button type="button" onclick="document.getElementById('notitieKnopRij').style.display='none'; document.getElementById('notitieFormulier').style.display='block';" style="padding:8px 18px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">+ Notitie toevoegen</button>
    </div>
    <div id="notitieFormulier" style="display:none;max-width:560px;margin-bottom:24px;background:var(--gray-50);border-radius:10px;padding:16px;">
        <div style="font-size:11px;font-weight:700;color:var(--gray-400);text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">Nieuwe teamnotitie</div>
        <form method="POST">
            <div style="margin-bottom:10px;">
                <input type="text" name="bedrijf" list="notitie_bedrijven_lijst" required placeholder="Bedrijf" autocomplete="off" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
                <datalist id="notitie_bedrijven_lijst">{% for naam in bedrijfsnamen %}<option value="{{ naam }}">{% endfor %}</datalist>
            </div>
            <div style="margin-bottom:10px;">
                <textarea name="tekst" required rows="3" placeholder="Notitie..." style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;"></textarea>
            </div>
            <button type="submit" style="padding:8px 18px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:700;cursor:pointer;">Notitie toevoegen</button>
            <button type="button" onclick="document.getElementById('notitieFormulier').style.display='none'; document.getElementById('notitieKnopRij').style.display='block';" style="background:none;border:none;color:var(--gray-400);cursor:pointer;font-size:12.5px;margin-left:8px;">Annuleren</button>
        </form>
    </div>

    {% if rijen %}
    <div class="info-kaart" style="max-width:700px;">
        {% for r in rijen %}
        <div class="dg-activiteit-item">
            <a href="/bedrijf/{{ r.bedrijf|urlencode }}" style="color:var(--gray-800);font-weight:700;text-decoration:none;">{{ r.bedrijf }}</a><br>
            {{ r.tekst }}
            <small>{{ r.timestamp }}</small>
        </div>
        {% endfor %}
    </div>
    {% else %}
    <div class="lege-staat">Nog geen teamnotities.</div>
    {% endif %}
    """
    pagina = render_simple_page("Notities", "notities", inhoud)
    return render_template_string(pagina, rijen=rijen, bedrijfsnamen=bedrijfsnamen)