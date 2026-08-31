"""
meldingen.py — Blueprint voor de Meldingen-module.

Bevat: /api/meldingen (GET/POST), /api/meldingen/<id>/lezen,
/api/meldingen/alles-gelezen en /meldingen-overzicht.

Registratie in app.py met: app.register_blueprint(meldingen_bp)
"""
import uuid
import datetime
from flask import Blueprint, request, session, jsonify, render_template_string

from core import laad_meldingen, bewaar_meldingen, render_simple_page

meldingen_bp = Blueprint("meldingen", __name__)

@meldingen_bp.route("/api/meldingen", methods=["GET"])
def get_meldingen():
    gebruiker = session.get("gebruikersnaam", "")
    team = session.get("team", "")
    alle = laad_meldingen()
    van_mij = [m for m in alle if m["voor_gebruiker"] == gebruiker or (m["voor_team"] and m["voor_team"] == team)]
    return jsonify(van_mij)

@meldingen_bp.route("/api/meldingen", methods=["POST"])
def add_melding():
    data = request.get_json()
    tekst = data.get("tekst", "").strip()
    bedrijf = data.get("bedrijf", "")
    voor_gebruiker = data.get("voor_gebruiker", "")
    voor_team = data.get("voor_team", "")
    van = session.get("gebruikersnaam", "")

    if not tekst or (not voor_gebruiker and not voor_team):
        return jsonify({"error": "Tekst en ontvanger zijn verplicht"}), 400

    alle = laad_meldingen()
    nieuwe = {
        "id": str(uuid.uuid4()),
        "tekst": tekst,
        "bedrijf": bedrijf,
        "van": van,
        "voor_gebruiker": voor_gebruiker,
        "voor_team": voor_team,
        "gelezen": False,
        "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
    }
    alle.append(nieuwe)
    bewaar_meldingen(alle)
    return jsonify(nieuwe)

@meldingen_bp.route("/api/meldingen/<melding_id>/lezen", methods=["POST"])
def markeer_gelezen(melding_id):
    gebruiker = session.get("gebruikersnaam", "")
    team = session.get("team", "")
    alle = laad_meldingen()
    for m in alle:
        if m["id"] == melding_id and (m.get("voor_gebruiker") == gebruiker or (m.get("voor_team") and m.get("voor_team") == team)):
            m["gelezen"] = True
    bewaar_meldingen(alle)
    return jsonify({"ok": True})

@meldingen_bp.route("/api/meldingen/alles-gelezen", methods=["POST"])
def markeer_alles_gelezen():
    gebruiker = session.get("gebruikersnaam", "")
    team = session.get("team", "")
    alle = laad_meldingen()
    for m in alle:
        if m.get("voor_gebruiker") == gebruiker or (m.get("voor_team") and m.get("voor_team") == team):
            m["gelezen"] = True
    bewaar_meldingen(alle)
    return jsonify({"ok": True})

@meldingen_bp.route("/meldingen-overzicht")
def meldingen_overzicht():
    gebruiker = session.get("gebruikersnaam", "")
    team = session.get("team", "")
    alle = laad_meldingen()
    van_mij = [m for m in alle if m.get("voor_gebruiker") == gebruiker or (m.get("voor_team") and m.get("voor_team") == team)]
    van_mij.sort(key=lambda m: m.get("timestamp",""), reverse=True)
    aantal_ongelezen = sum(1 for m in van_mij if not m.get("gelezen"))

    inhoud = """
    <div class="page-title">Meldingen</div>
    {% if aantal_ongelezen > 0 %}
    <button onclick="alleMeldingenGelezen()" style="padding:6px 14px;background:var(--gray-100);color:var(--gray-700);border:none;border-radius:6px;font-weight:600;cursor:pointer;font-size:12.5px;margin-top:0;margin-bottom:16px;">Alles gelezen markeren ({{ aantal_ongelezen }})</button>
    <script>
    async function alleMeldingenGelezen() {
        await fetch("/api/meldingen/alles-gelezen", {method: "POST"});
        window.location.reload();
    }
    </script>
    {% endif %}
    {% if van_mij %}
    <div class="info-kaart" style="max-width:700px;">
        {% for m in van_mij %}
        <div class="dg-activiteit-item" style="background:{{ '#eff6ff' if not m.gelezen else 'transparent' }};padding:10px;border-radius:6px;">
            {% if m.bedrijf %}<a href="/bedrijf/{{ m.bedrijf|urlencode }}" style="color:var(--gray-800);font-weight:700;text-decoration:none;">{{ m.bedrijf }}</a><br>{% endif %}
            {{ m.tekst }}
            <small>{{ m.timestamp }}{% if m.van %} · van {{ m.van }}{% endif %}</small>
        </div>
        {% endfor %}
    </div>
    {% else %}
    <div class="lege-staat">Nog geen meldingen.</div>
    {% endif %}
    """
    pagina = render_simple_page("Meldingen", "instellingen", inhoud)
    return render_template_string(pagina, van_mij=van_mij, aantal_ongelezen=aantal_ongelezen)