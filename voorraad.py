"""
voorraad.py — Blueprint voor de Voorraad-module.

De grootste module: fysieke voorraad (transacties, keuring, aging),
shipments (weegbrug-workflow), contracten, voorraadmomenten, en de
bijbehorende CSV-exports. Gebruikt bereken_voorraad_status() als centrale
berekening zodat dashboard/KPI's/per-commodity-tabel altijd consistent zijn.

Registratie in app.py met: app.register_blueprint(voorraad_bp)
"""
import uuid
import datetime
from flask import Blueprint, request, session, redirect, url_for, render_template_string, Response

from core import (
    laad_voorraad, bewaar_voorraad, laad_shipments, bewaar_shipments,
    laad_contracten, bewaar_contracten, laad_voorraadmomenten, bewaar_voorraadmomenten,
    laad_orders, laad_status, laad_accountmanagers, laad_materiaal_taxonomie,
    parse_hoeveelheid_getal, bereken_voorraad_status, is_huidige_gebruiker_admin,
    vereist_admin_of_403, render_simple_page, ENF_BEDRIJVEN,
    ALBLASSERDAM_NAAM, bepaal_shipment_flow_type, shipment_hoeveelheid, SHIPMENT_STATUSSEN,
    vereist_afdeling_of_403, laad_handelsorders,
)

voorraad_bp = Blueprint("voorraad", __name__)

@voorraad_bp.route("/export-voorraad-csv")
def export_voorraad_csv():
    import csv, io
    from flask import Response
    filter_materiaal = request.args.get("filter_materiaal", "")
    filter_type = request.args.get("filter_type", "")
    filter_locatie = request.args.get("filter_locatie", "")

    transacties = laad_voorraad()
    if filter_materiaal:
        transacties = [t for t in transacties if t.get("materiaal") == filter_materiaal]
    if filter_type:
        transacties = [t for t in transacties if t.get("type") == filter_type]
    if filter_locatie:
        transacties = [t for t in transacties if t.get("locatie") == filter_locatie or t.get("locatie_van") == filter_locatie or t.get("locatie_naar") == filter_locatie]

    output = io.StringIO()
    schrijver = csv.writer(output)
    schrijver.writerow(["Type", "Materiaal", "Hoeveelheid (ton)", "Locatie", "Van locatie", "Naar locatie", "Keuringsstatus",
                         "Reden (adjustment)", "Bedrijf", "Prijs", "Datum", "Gebruiker", "Notitie", "Aangemaakt"])
    for t in transacties:
        schrijver.writerow([t.get("type",""), t.get("materiaal",""), t.get("hoeveelheid",""), t.get("locatie",""),
                             t.get("locatie_van",""), t.get("locatie_naar",""), t.get("keuringsstatus",""),
                             t.get("reden",""), t.get("bedrijf",""), t.get("prijs",""), t.get("datum",""),
                             t.get("gebruiker",""), t.get("notitie",""), t.get("aangemaakt","")])

    return Response(output.getvalue(), mimetype="text/csv",
                     headers={"Content-Disposition": "attachment; filename=voorraad_transacties_export.csv"})

@voorraad_bp.route("/export-shipments-csv")
def export_shipments_csv():
    import csv, io
    from flask import Response
    filter_flow_type = request.args.get("filter_flow_type", "")
    filter_shipment_status = request.args.get("filter_shipment_status", "")
    filter_shipment_materiaal = request.args.get("filter_shipment_materiaal", "")

    shipments = laad_shipments()
    for s in shipments:
        s["flow_type"] = bepaal_shipment_flow_type(s)
    if filter_flow_type:
        shipments = [s for s in shipments if s.get("flow_type") == filter_flow_type]
    if filter_shipment_status:
        shipments = [s for s in shipments if s.get("status") == filter_shipment_status]
    if filter_shipment_materiaal:
        shipments = [s for s in shipments if s.get("materiaal") == filter_shipment_materiaal]

    output = io.StringIO()
    schrijver = csv.writer(output)
    schrijver.writerow(["Referentie", "Flow type", "Origin land", "Origin leverancier", "Loading locatie",
                         "Destination land", "Destination naam", "Materiaal", "Gepland (ton)", "Werkelijk (ton)",
                         "Bruto", "Tara", "Netto", "Weegbon", "Transport", "Status", "Datum", "Gebruiker", "Notitie"])
    for s in shipments:
        schrijver.writerow([s.get("referentie",""), s.get("flow_type",""), s.get("origin_land",""), s.get("origin_leverancier",""),
                             s.get("loading_locatie",""), s.get("destination_land",""), s.get("destination_naam",""),
                             s.get("materiaal",""), s.get("gepland_hoeveelheid",""), s.get("werkelijk_hoeveelheid",""),
                             s.get("bruto_gewicht",""), s.get("tara_gewicht",""), s.get("netto_gewicht",""), s.get("weegbon_nummer",""),
                             s.get("transport",""), s.get("status",""), s.get("datum",""), s.get("gebruiker",""), s.get("notitie","")])

    return Response(output.getvalue(), mimetype="text/csv",
                     headers={"Content-Disposition": "attachment; filename=shipments_export.csv"})

@voorraad_bp.route("/voorraad/shipments", methods=["POST"])
def voorraad_shipments_actie():
    actie = request.form.get("actie", "")
    shipments = laad_shipments()

    if actie == "toevoegen":
        nieuw = {
            "id": str(uuid.uuid4()),
            "referentie": request.form.get("referentie", "").strip(),
            "origin_land": request.form.get("origin_land", "").strip(),
            "origin_leverancier": request.form.get("origin_leverancier", "").strip(),
            "loading_locatie": request.form.get("loading_locatie", "").strip(),
            "destination_land": request.form.get("destination_land", "").strip(),
            "destination_naam": request.form.get("destination_naam", "").strip(),
            "transport": request.form.get("transport", "").strip(),
            "materiaal": request.form.get("materiaal", "").strip(),
            "contract_id": request.form.get("contract_id", "").strip(),
            "gepland_hoeveelheid": request.form.get("gepland_hoeveelheid", "").strip(),
            "werkelijk_hoeveelheid": "",
            "bruto_gewicht": "", "tara_gewicht": "", "netto_gewicht": "", "weegbon_nummer": "",
            "transportkosten": "",
            "gekoppelde_shipment_id": request.form.get("gekoppelde_shipment_id", "").strip(),
            "datum": request.form.get("datum", "").strip(),
            "status": "Planned",
            "voorraad_verwerkt": False,
            "notitie": request.form.get("notitie", "").strip(),
            "gebruiker": session.get("gebruikersnaam", ""),
            "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
        }
        if nieuw["materiaal"] and nieuw["gepland_hoeveelheid"] and nieuw["origin_land"] and nieuw["destination_land"]:
            shipments.append(nieuw)
            bewaar_shipments(shipments)

    elif actie == "status_wijzigen":
        shipment_id = request.form.get("shipment_id", "")
        nieuwe_status = request.form.get("nieuwe_status", "")
        doel = next((s for s in shipments if s["id"] == shipment_id), None)
        if doel:
            flow_type = bepaal_shipment_flow_type(doel)

            # Bij 'Weighed' het weegbrug-gewicht vastleggen (bruto - tara = netto)
            if nieuwe_status == "Weighed":
                bruto = request.form.get("bruto_gewicht", "").strip()
                tara = request.form.get("tara_gewicht", "").strip()
                if bruto and tara:
                    netto = parse_hoeveelheid_getal(bruto) - parse_hoeveelheid_getal(tara)
                    doel["bruto_gewicht"] = bruto
                    doel["tara_gewicht"] = tara
                    doel["netto_gewicht"] = str(round(netto, 2))
                    doel["werkelijk_hoeveelheid"] = str(round(netto, 2))
                doel["weegbon_nummer"] = request.form.get("weegbon_nummer", "").strip()

            doel["status"] = nieuwe_status
            bewaar_shipments(shipments)

            # Automatisch effect op de fysieke voorraad: alleen bij Alblasserdam-gerelateerde legs
            aantal = shipment_hoeveelheid(doel)
            if flow_type == "inbound" and nieuwe_status in ("Weighed", "Received") and not doel.get("voorraad_verwerkt"):
                transacties = laad_voorraad()
                transacties.append({
                    "id": str(uuid.uuid4()), "type": "in", "materiaal": doel["materiaal"],
                    "hoeveelheid": str(aantal), "locatie": ALBLASSERDAM_NAAM,
                    "bedrijf": doel.get("origin_leverancier",""), "prijs": "",
                    "notitie": f"Automatisch aangemaakt bij {nieuwe_status.lower()} van shipment {doel.get('referentie','')}",
                    "gebruiker": session.get("gebruikersnaam",""), "datum": datetime.date.today().isoformat(),
                    "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
                    "keuringsstatus": "te_keuren",
                })
                bewaar_voorraad(transacties)
                doel["voorraad_verwerkt"] = True
                bewaar_shipments(shipments)
            elif flow_type == "outbound" and nieuwe_status == "Loaded" and not doel.get("voorraad_verwerkt"):
                transacties = laad_voorraad()
                transacties.append({
                    "id": str(uuid.uuid4()), "type": "uit", "materiaal": doel["materiaal"],
                    "hoeveelheid": str(aantal), "locatie": ALBLASSERDAM_NAAM,
                    "bedrijf": doel.get("destination_naam",""), "prijs": "",
                    "notitie": f"Automatisch aangemaakt bij verlading shipment {doel.get('referentie','')}",
                    "gebruiker": session.get("gebruikersnaam",""), "datum": datetime.date.today().isoformat(),
                    "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
                })
                bewaar_voorraad(transacties)
                doel["voorraad_verwerkt"] = True
                bewaar_shipments(shipments)

    elif actie == "kosten_bijwerken":
        shipment_id = request.form.get("shipment_id", "")
        doel = next((s for s in shipments if s["id"] == shipment_id), None)
        if doel:
            doel["transportkosten"] = request.form.get("transportkosten", "").strip()
            bewaar_shipments(shipments)

    elif actie == "verwijderen":
        shipment_id = request.form.get("shipment_id", "")
        doel = next((s for s in shipments if s["id"] == shipment_id), None)
        if doel and (doel.get("gebruiker") == session.get("gebruikersnaam","") or is_huidige_gebruiker_admin()):
            shipments = [s for s in shipments if s["id"] != shipment_id]
            bewaar_shipments(shipments)

    _terug_naar = request.form.get("terug_naar", "")
    if _terug_naar == "logistiek":
        return redirect(url_for("logistiek_pagina"))
    return redirect(url_for("voorraad.voorraad_pagina"))

@voorraad_bp.route("/voorraad/contracten", methods=["POST"])
def voorraad_contracten_actie():
    actie = request.form.get("actie", "")
    contracten = laad_contracten()

    if actie == "toevoegen":
        nieuw = {
            "id": str(uuid.uuid4()),
            "referentie": request.form.get("referentie", "").strip(),
            "tegenpartij": request.form.get("tegenpartij", "").strip(),
            "richting": request.form.get("richting", "inkoop"),
            "materiaal": request.form.get("materiaal", "").strip(),
            "contract_volume": request.form.get("contract_volume", "").strip(),
            "prijs_per_ton": request.form.get("prijs_per_ton", "").strip(),
            "notitie": request.form.get("notitie", "").strip(),
            "gebruiker": session.get("gebruikersnaam", ""),
            "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
        }
        if nieuw["referentie"] and nieuw["materiaal"] and nieuw["contract_volume"]:
            contracten.append(nieuw)
            bewaar_contracten(contracten)

    elif actie == "verwijderen":
        contract_id = request.form.get("contract_id", "")
        doel = next((c for c in contracten if c["id"] == contract_id), None)
        if doel and (doel.get("gebruiker") == session.get("gebruikersnaam","") or is_huidige_gebruiker_admin()):
            contracten = [c for c in contracten if c["id"] != contract_id]
            bewaar_contracten(contracten)

    return redirect(url_for("voorraad.voorraad_pagina"))

@voorraad_bp.route("/voorraad", methods=["GET", "POST"])
def voorraad_pagina():
    _guard = vereist_afdeling_of_403("voorraad")
    if _guard: return _guard
    if request.method == "POST":
        actie = request.form.get("actie", "")
        # Handmatige voorraadmutaties (los van shipments/orders) zijn alleen voor admins.
        # Gewone gebruikers passen voorraad alleen aan via inkooporders (inbound) en het uitboeken van verkooporders (outbound).
        # Keuring (goed-/afkeuren van al aangekomen materiaal) blijft een normale werf-taak, geen 'aanpassen'.
        if actie == "toevoegen":
            _guard = vereist_admin_of_403()
            if _guard: return _guard
        transacties = laad_voorraad()

        if actie == "toevoegen":
            type_ = request.form.get("type", "in")
            nieuwe_transactie = {
                "id": str(uuid.uuid4()),
                "type": type_,
                "materiaal": request.form.get("materiaal", "").strip(),
                "hoeveelheid": request.form.get("hoeveelheid", "").strip(),
                "locatie": request.form.get("locatie", "").strip() or "Alblasserdam",
                "bedrijf": request.form.get("bedrijf", "").strip(),
                "prijs": request.form.get("prijs", "").strip(),
                "notitie": request.form.get("notitie", "").strip(),
                "gebruiker": session.get("gebruikersnaam", ""),
                "datum": request.form.get("datum", "") or datetime.date.today().isoformat(),
                "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
                # Keuring is alleen relevant bij binnenkomende materialen; uitgaande zijn per definitie al goedgekeurd
                "keuringsstatus": (request.form.get("keuringsstatus", "te_keuren") if type_ == "in" else "goedgekeurd"),
            }
            if type_ == "transfer":
                nieuwe_transactie["locatie_van"] = request.form.get("locatie_van", "").strip()
                nieuwe_transactie["locatie_naar"] = request.form.get("locatie_naar", "").strip()
            if type_ == "adjustment":
                nieuwe_transactie["richting"] = request.form.get("richting", "plus")
                nieuwe_transactie["reden"] = request.form.get("reden", "").strip()

            geldig = nieuwe_transactie["materiaal"] and nieuwe_transactie["hoeveelheid"]
            if type_ == "transfer":
                geldig = geldig and nieuwe_transactie["locatie_van"] and nieuwe_transactie["locatie_naar"]
            if type_ == "adjustment":
                geldig = geldig and nieuwe_transactie["reden"]

            if geldig:
                transacties.append(nieuwe_transactie)
                bewaar_voorraad(transacties)

        elif actie == "keuring_wijzigen":
            transactie_id = request.form.get("transactie_id", "")
            nieuwe_keuringsstatus = request.form.get("nieuwe_keuringsstatus", "")
            for t in transacties:
                if t["id"] == transactie_id:
                    t["keuringsstatus"] = nieuwe_keuringsstatus
            bewaar_voorraad(transacties)

        elif actie == "verwijderen":
            transactie_id = request.form.get("transactie_id", "")
            doel = next((t for t in transacties if t["id"] == transactie_id), None)
            if doel and (doel.get("gebruiker") == session.get("gebruikersnaam","") or is_huidige_gebruiker_admin()):
                transacties = [t for t in transacties if t["id"] != transactie_id]
                bewaar_voorraad(transacties)

        elif actie == "moment_toevoegen":
            momenten = laad_voorraadmomenten()
            nieuw_moment = {
                "id": str(uuid.uuid4()),
                "materiaal": request.form.get("moment_materiaal", "").strip(),
                "locatie": request.form.get("moment_locatie", "").strip() or "Alblasserdam",
                "hoeveelheid": request.form.get("moment_hoeveelheid", "").strip(),
                "notitie": request.form.get("moment_notitie", "").strip(),
                "gebruiker": session.get("gebruikersnaam", ""),
                "datum": request.form.get("moment_datum", "") or datetime.date.today().isoformat(),
                "aangemaakt": datetime.datetime.now().strftime("%d-%m-%Y %H:%M"),
            }
            if nieuw_moment["materiaal"] and nieuw_moment["hoeveelheid"]:
                momenten.append(nieuw_moment)
                bewaar_voorraadmomenten(momenten)

        elif actie == "moment_verwijderen":
            moment_id = request.form.get("moment_id", "")
            momenten = laad_voorraadmomenten()
            doel = next((m for m in momenten if m["id"] == moment_id), None)
            if doel and (doel.get("gebruiker") == session.get("gebruikersnaam","") or is_huidige_gebruiker_admin()):
                momenten = [m for m in momenten if m["id"] != moment_id]
                bewaar_voorraadmomenten(momenten)

        return redirect(url_for("voorraad.voorraad_pagina"))

    transacties = laad_voorraad()
    transacties_gesorteerd = sorted(transacties, key=lambda t: t.get("aangemaakt",""), reverse=True)

    vs = bereken_voorraad_status()
    voorraad_per_materiaal = vs["fysiek_per_materiaal"]
    te_keuren_per_materiaal = vs["te_keuren_per_materiaal"]
    per_locatie_materiaal = vs["per_locatie_materiaal"]
    transit_per_materiaal = vs["transit_per_materiaal"]
    verkocht_per_materiaal = vs["gereserveerd_per_materiaal"]
    inkooporders_per_materiaal = vs["inkooporders_per_materiaal"]
    aging_buckets = vs["aging_buckets"]
    inkomend_7d = vs["inkomend_7d"]
    uitgaand_7d = vs["uitgaand_7d"]

    voorraad_lijst = sorted(voorraad_per_materiaal.items(), key=lambda x: -x[1])

    filter_materiaal = request.args.get("filter_materiaal", "")
    filter_type = request.args.get("filter_type", "")
    filter_locatie = request.args.get("filter_locatie", "")
    getoonde_transacties = transacties_gesorteerd
    if filter_materiaal:
        getoonde_transacties = [t for t in getoonde_transacties if t.get("materiaal") == filter_materiaal]
    if filter_type:
        getoonde_transacties = [t for t in getoonde_transacties if t.get("type") == filter_type]
    if filter_locatie:
        getoonde_transacties = [t for t in getoonde_transacties if t.get("locatie") == filter_locatie or t.get("locatie_van") == filter_locatie or t.get("locatie_naar") == filter_locatie]

    alle_locaties = sorted({loc for (loc, _naam) in per_locatie_materiaal.keys()} | {t.get("locatie","") for t in transacties if t.get("locatie")}) or ["Alblasserdam"]

    stock_per_locatie = {}
    for (loc, naam), aantal in per_locatie_materiaal.items():
        stock_per_locatie.setdefault(loc, 0)
        stock_per_locatie[loc] += aantal
    stock_per_locatie_lijst = sorted(stock_per_locatie.items(), key=lambda x: -x[1])

    _status_alle = laad_status()
    _accountmanagers_alle = laad_accountmanagers()
    alle_bedrijfsnamen_voorraad = sorted(set(_status_alle.keys()) | set(_accountmanagers_alle.keys()))[:500]

    voorraadmomenten = sorted(laad_voorraadmomenten(), key=lambda m: m.get("aangemaakt",""), reverse=True)
    for m in voorraadmomenten:
        m["huidige_berekende_voorraad"] = voorraad_per_materiaal.get(m.get("materiaal",""), 0)
        try:
            m["verschil"] = float(str(m.get("hoeveelheid","0")).replace(",","")) - m["huidige_berekende_voorraad"]
        except (ValueError, TypeError):
            m["verschil"] = 0

    alle_materiaalnamen = sorted(set(voorraad_per_materiaal) | set(te_keuren_per_materiaal) | set(verkocht_per_materiaal) | set(inkooporders_per_materiaal) | set(transit_per_materiaal))
    per_commodity = []
    for naam in alle_materiaalnamen:
        fysiek = voorraad_per_materiaal.get(naam, 0)
        binnenkort = te_keuren_per_materiaal.get(naam, 0)
        verkocht = verkocht_per_materiaal.get(naam, 0)
        per_commodity.append({
            "naam": naam, "fysiek": fysiek, "binnenkort_binnen": binnenkort,
            "verkocht": verkocht, "vrij": fysiek - verkocht,
            "gepland_inkoop": inkooporders_per_materiaal.get(naam, 0),
            "transit": transit_per_materiaal.get(naam, 0),
        })
    per_commodity.sort(key=lambda x: -x["fysiek"])

    kpi_fysiek_totaal = sum(voorraad_per_materiaal.values())
    kpi_binnenkort_totaal = sum(te_keuren_per_materiaal.values())
    kpi_verkocht_totaal = sum(verkocht_per_materiaal.values())
    kpi_inkoop_totaal = sum(inkooporders_per_materiaal.values())
    kpi_vrij_totaal = kpi_fysiek_totaal - kpi_verkocht_totaal
    kpi_transit_totaal = sum(transit_per_materiaal.values())
    kpi_forecast_totaal = kpi_fysiek_totaal + inkomend_7d - uitgaand_7d

    # Shipments (unified model: systeem classificeert zelf inbound/outbound/direct)
    alle_shipments = sorted(laad_shipments(), key=lambda s: s.get("datum",""))
    for s in alle_shipments:
        s["flow_type"] = bepaal_shipment_flow_type(s)
    actieve_shipments = [s for s in alle_shipments if s.get("status") != "Cancelled"]
    filter_flow_type = request.args.get("filter_flow_type", "")
    filter_shipment_status = request.args.get("filter_shipment_status", "")
    filter_shipment_materiaal = request.args.get("filter_shipment_materiaal", "")
    getoonde_shipments = actieve_shipments
    if filter_flow_type:
        getoonde_shipments = [s for s in getoonde_shipments if s.get("flow_type") == filter_flow_type]
    if filter_shipment_status:
        getoonde_shipments = [s for s in getoonde_shipments if s.get("status") == filter_shipment_status]
    if filter_shipment_materiaal:
        getoonde_shipments = [s for s in getoonde_shipments if s.get("materiaal") == filter_shipment_materiaal]
    alle_shipments_dropdown = actieve_shipments
    kpi_direct_flow_totaal = sum(vs["direct_flow_per_materiaal"].values())
    flow_by_origin_lijst = sorted(vs["flow_by_origin"].items(), key=lambda x: -x[1])
    flow_by_destination_lijst = sorted(vs["flow_by_destination"].items(), key=lambda x: -x[1])
    kpi_totaal_controlled = kpi_fysiek_totaal + kpi_transit_totaal + kpi_direct_flow_totaal
    shipment_materialen = sorted({s.get("materiaal","") for s in actieve_shipments if s.get("materiaal")})

    _alle_bedrijven_landen = sorted({b.get("land","") for b in ENF_BEDRIJVEN if b.get("land")})

    # Prefill van het shipment-formulier vanuit een order ("Uitboeken"/"Inboeken"-knop op /orders)
    prefill = None
    prefill_order_id = request.args.get("prefill_order", "")
    if prefill_order_id:
        order = next((o for o in laad_orders() if o["id"] == prefill_order_id), None)
        if order:
            bedrijf_land = next((b.get("land","") for b in ENF_BEDRIJVEN if b["naam"] == order.get("bedrijf","")), "")
            if order.get("ordertype") == "inkoop":
                prefill = {
                    "origin_land": bedrijf_land, "origin_leverancier": order.get("bedrijf",""),
                    "loading_locatie": "", "destination_land": ALBLASSERDAM_NAAM, "destination_naam": "",
                    "materiaal": order.get("materiaal",""), "gepland_hoeveelheid": str(parse_hoeveelheid_getal(order.get("hoeveelheid",""))),
                    "referentie": f"Order-{order['id'][:8]}", "transport": order.get("transportmiddel",""),
                }
            else:
                prefill = {
                    "origin_land": ALBLASSERDAM_NAAM, "origin_leverancier": "",
                    "loading_locatie": ALBLASSERDAM_NAAM, "destination_land": order.get("bestemming","") or bedrijf_land,
                    "destination_naam": order.get("bedrijf",""),
                    "materiaal": order.get("materiaal",""), "gepland_hoeveelheid": str(parse_hoeveelheid_getal(order.get("hoeveelheid",""))),
                    "referentie": f"Order-{order['id'][:8]}", "transport": order.get("transportmiddel",""),
                }

    # Prefill voor een vervolg-leg vanuit een al ontvangen inbound-shipment (bv. UK->Alblasserdam gevolgd door Alblasserdam->Azie)
    prefill_leg_id = request.args.get("prefill_leg", "")
    if prefill_leg_id and not prefill:
        bron_shipment = next((s for s in laad_shipments() if s["id"] == prefill_leg_id), None)
        if bron_shipment:
            prefill = {
                "origin_land": ALBLASSERDAM_NAAM, "origin_leverancier": "",
                "loading_locatie": ALBLASSERDAM_NAAM, "destination_land": "", "destination_naam": "",
                "materiaal": bron_shipment.get("materiaal",""),
                "gepland_hoeveelheid": bron_shipment.get("werkelijk_hoeveelheid") or bron_shipment.get("gepland_hoeveelheid",""),
                "referentie": f"Vervolg-{bron_shipment.get('referentie','') or bron_shipment['id'][:8]}",
                "transport": "", "gekoppelde_shipment_id": prefill_leg_id,
            }

    # Contracten met voortgang
    alle_contracten = laad_contracten()
    for c in alle_contracten:
        try:
            volume = float(str(c.get("contract_volume","0")).replace(",",""))
        except (ValueError, TypeError):
            volume = 0.0

        if c.get("richting") == "verkoop":
            # Verkoop naar een fabriek/klant: "geleverd" = shipments die daadwerkelijk afgeleverd zijn
            voortgang = sum(shipment_hoeveelheid(s) for s in alle_shipments
                             if s.get("contract_id") == c["id"] and s.get("status") == "Delivered")
        else:
            # Inkoop: "ontvangen" = goedgekeurde inbound-transacties op de fysieke voorraad
            voortgang = sum(parse_hoeveelheid_getal(t.get("hoeveelheid","")) for t in transacties
                             if t.get("type") in ("in","inbound") and t.get("keuringsstatus","goedgekeurd") == "goedgekeurd"
                             and t.get("materiaal") == c.get("materiaal") and t.get("contract_id") == c["id"])

        gepland = sum(shipment_hoeveelheid(s) for s in alle_shipments
                       if s.get("contract_id") == c["id"] and s.get("status") not in ("Received","Delivered","Cancelled"))
        c["ontvangen"] = voortgang
        c["voortgang_label"] = "Geleverd" if c.get("richting") == "verkoop" else "Ontvangen"
        c["gepland"] = gepland
        c["resterend"] = max(0, volume - voortgang - gepland)
        c["percentage"] = round((voortgang / volume * 100), 1) if volume else 0

    # Handelsorders (het huidige, actieve contractsysteem — vervangt het oude
    # handmatige 'Contracten'-blok hierboven, dat nu alleen nog voor bestaande,
    # historische data getoond wordt). Geleverd/gepland wordt hier op dezelfde
    # manier bepaald als bij Inkoop-/Verkoop-planning: via logistieke orders
    # (vrachtwagen) resp. transport planning (schip).
    from core import laad_logistieke_orders, laad_transport_planning
    _alle_logistieke_orders_vr = laad_logistieke_orders()
    _alle_transport_planning_vr = laad_transport_planning()

    def _geleverd_handelsorder(contractnummer, order_type, transportmodus):
        # Vrachtwagen-inkoop: via logistieke orders (Weegbrug/Live Operaties)
        if order_type == "inkoop" and transportmodus != "Schip":
            _via_logistiek = sum(
                parse_hoeveelheid_getal(o.get("werkelijke_hoeveelheid",""))
                for o in _alle_logistieke_orders_vr
                if o.get("contract_referentie") == contractnummer and o.get("status") in ("Weegbon compleet", "Afhandeling", "Klaar voor Finance", "Gefactureerd", "Afgerond")
            )
        else:
            _via_logistiek = sum(
                parse_hoeveelheid_getal(t.get("hoeveelheid",""))
                for t in _alle_transport_planning_vr
                if t.get("contract_referentie") == contractnummer and t.get("status") != "Geannuleerd"
            )
        # Plus: shipments (Voorraad-module) die aan dit contractnummer gekoppeld zijn
        # en daadwerkelijk aangekomen/afgeleverd zijn.
        _via_shipments = sum(
            shipment_hoeveelheid(s) for s in alle_shipments
            if s.get("contract_id") == contractnummer and s.get("status") in ("Received", "Delivered")
        )
        return round(_via_logistiek + _via_shipments, 3)

    alle_handelsorder_contracten = []
    for h in laad_handelsorders():
        if h.get("status") != "Definitief":
            continue
        try:
            _volume = float(str(h.get("hoeveelheid_mt","0")).replace(",",""))
        except (ValueError, TypeError):
            _volume = 0.0
        _geleverd = _geleverd_handelsorder(h["contractnummer"], h.get("order_type",""), h.get("transportmodus",""))
        alle_handelsorder_contracten.append({
            "id": h["id"], "contractnummer": h["contractnummer"], "tegenpartij": h.get("tegenpartij_naam",""),
            "richting": h.get("order_type",""), "materiaal": f"{h.get('materiaal','')} — {h.get('kwaliteit','')}",
            "volume": round(_volume,1), "geleverd": _geleverd, "resterend": round(max(0,_volume-_geleverd),1),
            "percentage": round((_geleverd/_volume*100),1) if _volume else 0,
        })
    alle_handelsorder_contracten.sort(key=lambda c: -c["resterend"])

    # Fabrieken-overzicht: verkoop-contracten gegroepeerd per tegenpartij (fabriek/klant)
    fabrieken_overzicht = {}
    for c in alle_contracten:
        if c.get("richting") != "verkoop":
            continue
        naam = c.get("tegenpartij") or "Onbekend"
        fabrieken_overzicht.setdefault(naam, []).append(c)
    fabrieken_overzicht_lijst = sorted(fabrieken_overzicht.items())

    inhoud = """
<style>
.vrd-kaart { background:#fff; border:1px solid var(--gray-200); border-radius:10px; padding:14px 16px; }
.vrd-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(180px,1fr)); gap:12px; margin-bottom:24px; }
.vrd-getal { font-size:1.3rem; font-weight:800; }
.vrd-label { font-size:0.78rem; color:var(--gray-400); margin-top:2px; }
.vrd-te-keuren { font-size:0.7rem; color:#d97706; margin-top:4px; font-weight:600; }
.vrd-transactie { display:flex; justify-content:space-between; align-items:center; padding:10px 0; border-bottom:1px solid var(--gray-50); font-size:13px; }
.vrd-badge-in { background:#f0fdf4; color:#16a34a; font-weight:700; font-size:11px; padding:2px 8px; border-radius:5px; }
.vrd-badge-uit { background:#fef2f2; color:#dc2626; font-weight:700; font-size:11px; padding:2px 8px; border-radius:5px; }
.vrd-badge-te-keuren { background:#fffbeb; color:#d97706; font-weight:700; font-size:11px; padding:2px 8px; border-radius:5px; }
.vrd-badge-afgekeurd { background:var(--gray-100); color:var(--gray-500); font-weight:700; font-size:11px; padding:2px 8px; border-radius:5px; text-decoration:line-through; }
.form-voorraad input, .form-voorraad select, .form-voorraad textarea { width:100%; padding:8px 10px; border:1px solid var(--gray-200); border-radius:6px; font-size:13px; margin-bottom:10px; font-family:inherit; box-sizing:border-box; }
.vrd-tabs { display:flex; gap:6px; margin-bottom:20px; }
.vrd-tab { padding:7px 16px; border-radius:6px; border:1px solid var(--gray-200); background:#fff; color:var(--gray-600); font-size:13px; font-weight:600; cursor:pointer; text-decoration:none; }
.vrd-tab.actief { background:var(--brand-600); color:#fff; border-color:var(--brand-600); }
</style>
<div class="page-title">Voorraad</div>
<p style="color:var(--gray-400);margin-top:0;margin-bottom:20px;font-size:0.85rem;">Handelsvoorraad op de werf, alles in <b>ton</b>. Binnenkomend materiaal telt pas mee zodra het is goedgekeurd. Verkocht/vrij wordt live berekend uit je Orders en shipments.</p>

<div class="vrd-grid" style="grid-template-columns:repeat(auto-fill,minmax(150px,1fr));margin-bottom:16px;">
    <div class="vrd-kaart"><div class="vrd-getal">{{ "{:,.1f}".format(kpi_fysiek_totaal) }}</div><div class="vrd-label">📦 TOTAL STOCK (ton)</div></div>
    <div class="vrd-kaart"><div class="vrd-getal" style="color:var(--brand-600);">{{ "{:,.1f}".format(kpi_vrij_totaal) }}</div><div class="vrd-label">✅ AVAILABLE (ton)</div></div>
    <div class="vrd-kaart"><div class="vrd-getal" style="color:#dc2626;">{{ "{:,.1f}".format(kpi_verkocht_totaal) }}</div><div class="vrd-label">🔒 RESERVED (ton)</div></div>
    <div class="vrd-kaart"><div class="vrd-getal" style="color:#7c3aed;">{{ "{:,.1f}".format(kpi_transit_totaal) }}</div><div class="vrd-label">🚚 IN TRANSIT (ton)</div></div>
    <div class="vrd-kaart"><div class="vrd-getal" style="color:#0891b2;">{{ "{:,.1f}".format(kpi_direct_flow_totaal) }}</div><div class="vrd-label">🌍 DIRECT FLOW (ton)</div></div>
    <div class="vrd-kaart" style="background:var(--gray-800);"><div class="vrd-getal" style="color:#fff;">{{ "{:,.1f}".format(kpi_totaal_controlled) }}</div><div class="vrd-label" style="color:var(--gray-300);">📊 TOTAL CONTROLLED VOLUME</div></div>
    <div class="vrd-kaart"><div class="vrd-getal" style="color:#16a34a;">{{ "{:,.1f}".format(inkomend_7d) }}</div><div class="vrd-label">📥 INCOMING 7 DAYS (ton)</div></div>
    <div class="vrd-kaart"><div class="vrd-getal" style="color:#dc2626;">{{ "{:,.1f}".format(uitgaand_7d) }}</div><div class="vrd-label">📤 OUTGOING 7 DAYS (ton)</div></div>
    <div class="vrd-kaart"><div class="vrd-getal" style="color:var(--gray-600);">{{ "{:,.1f}".format(kpi_forecast_totaal) }}</div><div class="vrd-label">🔮 FORECAST STOCK (ton)</div></div>
</div>

<div class="vrd-kaart" style="margin-bottom:24px;overflow-x:auto;">
    <div class="dg-kaart-titel" style="margin-bottom:10px;">Voorraad per commodity</div>
    <table style="width:100%;border-collapse:collapse;font-size:12.5px;">
        <thead>
            <tr style="text-align:left;color:var(--gray-400);font-size:10.5px;text-transform:uppercase;letter-spacing:0.4px;">
                <th style="padding:6px 8px;">Commodity</th>
                <th style="padding:6px 8px;text-align:right;">Fysiek</th>
                <th style="padding:6px 8px;text-align:right;">In transit</th>
                <th style="padding:6px 8px;text-align:right;">Binnenkort binnen</th>
                <th style="padding:6px 8px;text-align:right;">Verkocht</th>
                <th style="padding:6px 8px;text-align:right;">Vrij beschikbaar</th>
            </tr>
        </thead>
        <tbody>
            {% for c in per_commodity %}
            <tr style="border-top:1px solid var(--gray-50);">
                <td style="padding:7px 8px;font-weight:700;color:var(--gray-800);">{{ c.naam }}</td>
                <td style="padding:7px 8px;text-align:right;">{{ "{:,.1f}".format(c.fysiek) }}</td>
                <td style="padding:7px 8px;text-align:right;color:#7c3aed;">{{ "{:,.1f}".format(c.transit) if c.transit else "—" }}</td>
                <td style="padding:7px 8px;text-align:right;color:#d97706;">{{ "{:,.1f}".format(c.binnenkort_binnen) if c.binnenkort_binnen else "—" }}</td>
                <td style="padding:7px 8px;text-align:right;color:#dc2626;">{{ "{:,.1f}".format(c.verkocht) if c.verkocht else "—" }}</td>
                <td style="padding:7px 8px;text-align:right;font-weight:700;color:{{ 'var(--brand-600)' if c.vrij >= 0 else '#dc2626' }};">{{ "{:,.1f}".format(c.vrij) }}</td>
            </tr>
            {% else %}
            <tr><td colspan="6" style="padding:16px 8px;color:var(--gray-300);">Nog geen data.</td></tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<div class="vrd-2koloms" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px;">
    <div class="vrd-kaart">
        <div class="dg-kaart-titel" style="margin-bottom:10px;">Voorraad per locatie</div>
        {% for loc, aantal in stock_per_locatie_lijst %}
        <div class="vrd-transactie" style="padding:7px 0;">
            <span>📍 {{ loc }}</span>
            <b>{{ "{:,.1f}".format(aantal) }} ton</b>
        </div>
        {% else %}
        <div style="color:var(--gray-300);font-size:12.5px;">Nog geen locatiedata.</div>
        {% endfor %}
    </div>
    <div class="vrd-kaart">
        <div class="dg-kaart-titel" style="margin-bottom:10px;">Aging (goedgekeurde voorraad)</div>
        {% set aging_totaal = aging_buckets.values() | sum %}
        {% for bucket, aantal in aging_buckets.items() %}
        <div style="margin-bottom:8px;">
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:3px;">
                <span style="color:{{ '#dc2626' if bucket == '90+' and aantal > 0 else 'var(--gray-500)' }};font-weight:{{ '700' if bucket == '90+' and aantal > 0 else '500' }};">{{ bucket }} dagen{{ ' ⚠' if bucket == '90+' and aantal > 0 else '' }}</span>
                <span>{{ "{:,.1f}".format(aantal) }} ton</span>
            </div>
            <div style="background:var(--gray-100);border-radius:4px;height:6px;overflow:hidden;">
                <div style="background:{{ '#dc2626' if bucket == '90+' else ('#d97706' if bucket == '61-90' else 'var(--brand-500)') }};height:100%;width:{{ (aantal / aging_totaal * 100) if aging_totaal else 0 }}%;"></div>
            </div>
        </div>
        {% endfor %}
    </div>
</div>

<div class="vrd-2koloms" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px;">
    <div class="vrd-kaart">
        <div class="dg-kaart-titel" style="margin-bottom:10px;">Flow by origin</div>
        {% for land, aantal in flow_by_origin_lijst %}
        <div class="vrd-transactie" style="padding:6px 0;"><span>🌍 {{ land }}</span><b>{{ "{:,.1f}".format(aantal) }} ton</b></div>
        {% else %}
        <div style="color:var(--gray-300);font-size:12.5px;">Nog geen flow-data.</div>
        {% endfor %}
    </div>
    <div class="vrd-kaart">
        <div class="dg-kaart-titel" style="margin-bottom:10px;">Flow by destination</div>
        {% for land, aantal in flow_by_destination_lijst %}
        <div class="vrd-transactie" style="padding:6px 0;"><span>🎯 {{ land }}</span><b>{{ "{:,.1f}".format(aantal) }} ton</b></div>
        {% else %}
        <div style="color:var(--gray-300);font-size:12.5px;">Nog geen flow-data.</div>
        {% endfor %}
    </div>
</div>

<div class="vrd-grid">
    {% for naam, aantal in voorraad_lijst %}
    <div class="vrd-kaart">
        <div class="vrd-getal" style="color:{{ 'var(--brand-600)' if aantal >= 0 else '#dc2626' }};">{{ "{:,.1f}".format(aantal) }} <span style="font-size:0.7rem;font-weight:600;color:var(--gray-300);">ton</span></div>
        <div class="vrd-label">{{ naam }}</div>
        {% if te_keuren_per_materiaal.get(naam) %}<div class="vrd-te-keuren">⏳ {{ "{:,.1f}".format(te_keuren_per_materiaal[naam]) }} ton te keuren</div>{% endif %}
    </div>
    {% else %}
    <div class="lege-staat">Nog geen voorraadtransacties.</div>
    {% endfor %}
</div>

<div class="dg-kaart-titel" style="margin-bottom:12px;">🚢 Shipment plannen (systeem bepaalt zelf inbound/outbound/direct)</div>
{% if prefill %}
<div style="background:#eff6ff;color:#1d4ed8;padding:8px 14px;border-radius:8px;margin-bottom:10px;font-size:0.82rem;font-weight:600;max-width:680px;">Formulier vooringevuld vanuit de order — controleer en bevestig hieronder.</div>
{% endif %}
<div class="vrd-kaart" style="max-width:680px;margin-bottom:16px;">
    <p style="color:var(--gray-400);font-size:0.78rem;margin-top:0;margin-bottom:12px;">Vul origin en destination in. Is destination = Alblasserdam → inbound. Is origin = Alblasserdam → outbound. Anders → direct flow (raakt onze voorraad niet, blijft wel zichtbaar in de flow-tabellen).</p>
    <form method="POST" action="/voorraad/shipments" class="form-voorraad">
        <input type="hidden" name="actie" value="toevoegen">
        <div class="form-rij-2" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <input type="text" name="referentie" placeholder="Referentie" value="{{ prefill.referentie if prefill else '' }}">
            <input type="date" name="datum" placeholder="Datum (ETA/ETD)">
        </div>
        <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;margin:8px 0 4px;">Origin</div>
        <div class="form-rij-2" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;">
            <input type="text" name="origin_land" placeholder="Land (bv. UK, Alblasserdam)" value="{{ prefill.origin_land if prefill else '' }}" list="landenLijstVoorraad" required>
            <input type="text" name="origin_leverancier" placeholder="Leverancier" value="{{ prefill.origin_leverancier if prefill else '' }}" list="bedrijvenLijstVoorraad">
            <input type="text" name="loading_locatie" placeholder="Loading locatie" value="{{ prefill.loading_locatie if prefill else '' }}">
        </div>
        <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;margin:8px 0 4px;">Destination</div>
        <div class="form-rij-2" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <input type="text" name="destination_land" placeholder="Land (bv. Alblasserdam, Asia)" value="{{ prefill.destination_land if prefill else '' }}" list="landenLijstVoorraad" required>
            <input type="text" name="destination_naam" placeholder="Fabriek/klant" value="{{ prefill.destination_naam if prefill else '' }}" list="bedrijvenLijstVoorraad">
        </div>
        <datalist id="landenLijstVoorraad">
            <option value="Alblasserdam">
            {% for land in landen %}<option value="{{ land }}">{% endfor %}
        </datalist>
        <datalist id="bedrijvenLijstVoorraad">
            {% for naam in alle_bedrijfsnamen_voorraad %}<option value="{{ naam }}">{% endfor %}
        </datalist>
        <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;margin:8px 0 4px;">Materiaal &amp; transport</div>
        <div class="form-rij-2" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <select name="materiaal" required>
                <option value="">Materiaal...</option>
                {% for categorie, kwaliteiten_lijst in materiaal_taxonomie.items() %}
                <optgroup label="{{ categorie }}">
                    <option value="{{ categorie }}" {% if prefill and prefill.materiaal == categorie %}selected{% endif %}>{{ categorie }} (algemeen)</option>
                    {% for kw in kwaliteiten_lijst %}<option value="{{ kw }}" {% if prefill and prefill.materiaal == kw %}selected{% endif %}>{{ kw }}</option>{% endfor %}
                </optgroup>
                {% endfor %}
            </select>
            <input type="text" name="gepland_hoeveelheid" placeholder="Gepland gewicht (ton)" value="{{ prefill.gepland_hoeveelheid if prefill else '' }}" required>
        </div>
        <div class="form-rij-2" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <input type="text" name="transport" placeholder="Transport (Truck/Container/MSC)" value="{{ prefill.transport if prefill else '' }}">
            <select name="gekoppelde_shipment_id">
                <option value="">Geen gekoppelde leg</option>
                {% for s in alle_shipments_dropdown %}<option value="{{ s.id }}" {% if prefill and prefill.get("gekoppelde_shipment_id") == s.id %}selected{% endif %}>{{ s.referentie or s.id[:8] }} ({{ s.origin_land }} → {{ s.destination_land }})</option>{% endfor %}
            </select>
        </div>
        <select name="contract_id" style="width:100%;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:13px;margin-bottom:10px;box-sizing:border-box;">
            <option value="">Geen contract koppelen</option>
            {% for c in alle_handelsorder_contracten %}<option value="{{ c.contractnummer }}">{{ c.contractnummer }} — {{ c.tegenpartij }} ({{ c.materiaal }}, {{ c.richting }})</option>{% endfor %}
        </select>
        <textarea name="notitie" placeholder="Notitie (optioneel)" rows="2"></textarea>
        <button type="submit" class="btn-nav btn-nav-primary" style="border:none;cursor:pointer;width:100%;">+ Shipment plannen</button>
    </form>
</div>

<div class="vrd-kaart" id="shipments" style="margin-bottom:24px;overflow-x:auto;">
    <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:10px;">
        <div class="dg-kaart-titel" style="margin-bottom:0;">Alle actieve shipments</div>
        <form method="GET" style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
            <select name="filter_flow_type" onchange="this.form.submit()" style="padding:5px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:11.5px;">
                <option value="">Alle types</option>
                <option value="inbound" {% if filter_flow_type == "inbound" %}selected{% endif %}>Inbound</option>
                <option value="outbound" {% if filter_flow_type == "outbound" %}selected{% endif %}>Outbound</option>
                <option value="direct" {% if filter_flow_type == "direct" %}selected{% endif %}>Direct</option>
            </select>
            <select name="filter_shipment_status" onchange="this.form.submit()" style="padding:5px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:11.5px;">
                <option value="">Alle statussen</option>
                {% for st in shipment_statussen %}<option value="{{ st }}" {% if filter_shipment_status == st %}selected{% endif %}>{{ st }}</option>{% endfor %}
            </select>
            <select name="filter_shipment_materiaal" onchange="this.form.submit()" style="padding:5px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:11.5px;">
                <option value="">Alle materialen</option>
                {% for m in shipment_materialen %}<option value="{{ m }}" {% if filter_shipment_materiaal == m %}selected{% endif %}>{{ m }}</option>{% endfor %}
            </select>
            {% if filter_flow_type or filter_shipment_status or filter_shipment_materiaal %}<a href="/voorraad#shipments" style="font-size:11px;color:var(--gray-400);text-decoration:none;">Wis</a>{% endif %}
            <span style="font-size:11px;color:var(--gray-400);">{{ getoonde_shipments|length }} van {{ actieve_shipments|length }}</span>
            <a href="/export-shipments-csv?filter_flow_type={{ filter_flow_type }}&filter_shipment_status={{ filter_shipment_status|urlencode }}&filter_shipment_materiaal={{ filter_shipment_materiaal|urlencode }}" style="font-size:11px;font-weight:600;color:var(--brand-600);text-decoration:none;border:1px solid var(--gray-200);padding:4px 8px;border-radius:5px;">⬇ CSV</a>
        </form>
    </div>
    <table style="width:100%;border-collapse:collapse;font-size:12px;">
        <thead><tr style="text-align:left;color:var(--gray-400);font-size:10px;text-transform:uppercase;">
            <th style="padding:6px 8px;">Datum</th><th style="padding:6px 8px;">Route</th><th style="padding:6px 8px;">Materiaal</th>
            <th style="padding:6px 8px;text-align:right;">Ton (gepl./werk.)</th><th style="padding:6px 8px;">Type</th><th style="padding:6px 8px;">Status</th><th></th>
        </tr></thead>
        <tbody>
        {% for s in getoonde_shipments %}
        <tr style="border-top:1px solid var(--gray-50);">
            <td style="padding:7px 8px;">{{ s.datum }}</td>
            <td style="padding:7px 8px;">{{ s.origin_land }}{% if s.origin_leverancier %} ({{ s.origin_leverancier }}){% endif %} → {{ s.destination_land }}{% if s.destination_naam %} ({{ s.destination_naam }}){% endif %}</td>
            <td style="padding:7px 8px;font-weight:600;">{{ s.materiaal }}</td>
            <td style="padding:7px 8px;text-align:right;">{{ s.gepland_hoeveelheid }}{% if s.werkelijk_hoeveelheid %} / <b>{{ s.werkelijk_hoeveelheid }}</b>{% endif %}</td>
            <td style="padding:7px 8px;">
                <span style="font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;background:{{ '#eff6ff' if s.flow_type=='inbound' else ('#fef2f2' if s.flow_type=='outbound' else '#f5f3ff') }};color:{{ '#1d4ed8' if s.flow_type=='inbound' else ('#dc2626' if s.flow_type=='outbound' else '#7c3aed') }};">{{ s.flow_type|upper }}</span>
            </td>
            <td style="padding:7px 8px;">
                <form method="POST" action="/voorraad/shipments" style="margin:0;" onsubmit="return voorraadStatusSubmit(this, {{ (s.flow_type == 'inbound')|tojson }});">
                    <input type="hidden" name="actie" value="status_wijzigen">
                    <input type="hidden" name="shipment_id" value="{{ s.id }}">
                    <select name="nieuwe_status" onchange="this.form.requestSubmit()" style="font-size:11px;font-weight:700;padding:3px 6px;border-radius:5px;border:1px solid var(--gray-200);">
                        {% for st in shipment_statussen %}<option value="{{ st }}" {% if s.status == st %}selected{% endif %}>{{ st }}</option>{% endfor %}
                    </select>
                    <span class="weegveldjes" style="display:none;">
                        <input type="text" name="bruto_gewicht" placeholder="Bruto" style="width:55px;font-size:11px;padding:2px 4px;">
                        <input type="text" name="tara_gewicht" placeholder="Tara" style="width:55px;font-size:11px;padding:2px 4px;">
                        <input type="text" name="weegbon_nummer" placeholder="Weegbon" style="width:65px;font-size:11px;padding:2px 4px;">
                        <button type="submit" style="font-size:11px;padding:3px 6px;">OK</button>
                    </span>
                </form>
            </td>
            <td style="padding:7px 8px;">
                {% if s.flow_type == "inbound" and s.status in ("Weighed", "Received") %}
                <a href="/voorraad?prefill_leg={{ s.id }}#shipments" style="font-size:10px;font-weight:700;color:#fff;background:#0891b2;padding:4px 7px;border-radius:5px;text-decoration:none;white-space:nowrap;">+ Vervolg-leg</a>
                {% endif %}
                <form method="POST" action="/voorraad/shipments" onsubmit="return confirm('Verwijderen?');" style="margin:0;display:inline-block;">
                    <input type="hidden" name="actie" value="verwijderen"><input type="hidden" name="shipment_id" value="{{ s.id }}">
                    <button type="submit" style="background:none;border:none;color:var(--gray-300);cursor:pointer;">✕</button>
                </form>
            </td>
        </tr>
        {% else %}
        <tr><td colspan="7" style="padding:16px 8px;color:var(--gray-300);">Nog geen shipments.</td></tr>
        {% endfor %}
        </tbody>
    </table>
</div>
<script>
function voorraadStatusSubmit(form, isInbound) {
    const status = form.nieuwe_status.value;
    if (status === "Weighed") {
        const weegveld = form.querySelector(".weegveldjes");
        if (weegveld.style.display !== "inline") {
            weegveld.style.display = "inline";
            return false; // eerst bruto/tara laten invullen, submit uitstellen
        }
    }
    return true;
}
</script>

<div class="dg-kaart-titel" style="margin-bottom:12px;">🏭 Fabrieken — openstaande leveringen</div>
<p style="color:var(--gray-400);font-size:0.82rem;margin-top:-8px;margin-bottom:16px;">Wat kan er nog geleverd worden per fabriek/klant, gebaseerd op je verkoopcontracten hieronder.</p>
<div class="vrd-kaart" style="margin-bottom:24px;">
    {% for fabriek_naam, contracten_lijst in fabrieken_overzicht_lijst %}
    <div style="padding:10px 0;border-bottom:1px solid var(--gray-50);">
        <div style="font-weight:700;color:var(--gray-800);margin-bottom:6px;">🏭 {{ fabriek_naam }}</div>
        {% for c in contracten_lijst %}
        <div style="display:flex;justify-content:space-between;align-items:center;font-size:12.5px;padding:4px 0;">
            <span>{{ c.materiaal }} <span style="color:var(--gray-400);">({{ c.referentie }})</span></span>
            <span>
                totaal <b>{{ c.contract_volume }}t</b> ·
                geleverd <b style="color:#16a34a;">{{ "{:,.0f}".format(c.ontvangen) }}t</b> ·
                gepland <b style="color:#d97706;">{{ "{:,.0f}".format(c.gepland) }}t</b> ·
                <span style="color:{{ '#dc2626' if c.resterend > 0 else 'var(--gray-400)' }};font-weight:700;">nog open {{ "{:,.0f}".format(c.resterend) }}t</span>
            </span>
        </div>
        {% endfor %}
    </div>
    {% else %}
    <div class="lege-staat">Nog geen verkoopcontracten met een fabriek/klant.</div>
    {% endfor %}
</div>

<div class="dg-kaart-titel" style="margin-bottom:12px;">Contracten</div>
<div class="vrd-kaart" style="max-width:520px;margin-bottom:16px;background:#eff6ff;">
    <div style="font-size:12.5px;color:#1d4ed8;">Nieuwe contracten worden nu aangemaakt via Handelsorders.</div>
    <a href="/handelsorders/nieuw" style="display:inline-block;margin-top:8px;font-size:12.5px;font-weight:700;color:#fff;background:var(--brand-600);text-decoration:none;padding:7px 14px;border-radius:6px;">+ Nieuw contract (Handelsorders) →</a>
</div>
<div class="vrd-kaart" style="margin-bottom:24px;">
    {% for c in alle_handelsorder_contracten %}
    <a href="/handelsorders/{{ c.id }}" style="display:block;padding:10px 0;border-bottom:1px solid var(--gray-50);text-decoration:none;color:inherit;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <div><b>{{ c.contractnummer }}</b> · {{ c.tegenpartij }} · {{ c.materiaal }} <span style="color:var(--gray-400);font-size:11px;">({{ c.richting }})</span></div>
        </div>
        <div style="font-size:12px;color:var(--gray-500);margin-top:4px;">
            Volume: {{ c.volume }} t · Geleverd: {{ c.geleverd }} t · Resterend: {{ c.resterend }} t
        </div>
        <div style="background:var(--gray-100);border-radius:4px;height:6px;overflow:hidden;margin-top:6px;">
            <div style="background:var(--brand-500);height:100%;width:{{ c.percentage }}%;"></div>
        </div>
        <div style="font-size:11px;color:var(--gray-400);margin-top:2px;">{{ c.percentage }}% vervuld</div>
    </a>
    {% else %}
    <div class="lege-staat">Nog geen definitieve contracten via Handelsorders.</div>
    {% endfor %}
</div>

{% if alle_contracten %}
<div class="dg-kaart-titel" style="margin-bottom:12px;color:var(--gray-400);">Oude contracten (gearchiveerd, alleen-lezen)</div>
    {% for c in alle_contracten %}
    <div style="padding:10px 0;border-bottom:1px solid var(--gray-50);">
        <div style="display:flex;justify-content:space-between;align-items:center;">
            <div><b>{{ c.referentie }}</b> · {{ c.tegenpartij }} · {{ c.materiaal }} <span style="color:var(--gray-400);font-size:11px;">({{ c.richting }})</span></div>
            <form method="POST" action="/voorraad/contracten" onsubmit="return confirm('Contract verwijderen?');" style="margin:0;">
                <input type="hidden" name="actie" value="verwijderen"><input type="hidden" name="contract_id" value="{{ c.id }}">
                <button type="submit" style="background:none;border:none;color:var(--gray-300);cursor:pointer;">✕</button>
            </form>
        </div>
        <div style="font-size:12px;color:var(--gray-500);margin-top:4px;">
            Volume: {{ c.contract_volume }} t · {{ c.voortgang_label }}: {{ "{:,.1f}".format(c.ontvangen) }} t · Gepland: {{ "{:,.1f}".format(c.gepland) }} t · Resterend: {{ "{:,.1f}".format(c.resterend) }} t
        </div>
        <div style="background:var(--gray-100);border-radius:4px;height:6px;overflow:hidden;margin-top:6px;">
            <div style="background:var(--brand-500);height:100%;width:{{ c.percentage }}%;"></div>
        </div>
        <div style="font-size:11px;color:var(--gray-400);margin-top:2px;">{{ c.percentage }}% vervuld</div>
    </div>
    {% else %}
    <div class="lege-staat">Nog geen contracten.</div>
    {% endfor %}
</div>
{% endif %}

{% if is_admin %}
<div class="vrd-kaart" style="max-width:520px;margin-bottom:20px;">
    <div class="dg-kaart-titel">Transactie toevoegen <span style="font-size:10px;font-weight:700;color:var(--gray-400);background:var(--gray-100);padding:2px 6px;border-radius:4px;">ADMIN</span></div>
    <p style="color:var(--gray-400);font-size:0.75rem;margin-top:-4px;margin-bottom:10px;">Handmatige correctie. Normale voorraadmutaties lopen via inkooporders (inbound) en het uitboeken van verkooporders (outbound) hieronder.</p>
    <form method="POST" class="form-voorraad">
        <input type="hidden" name="actie" value="toevoegen">
        <div class="form-rij-2" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <select name="type" id="voorraadTypeSelect" onchange="toggleTransactieVelden()">
                <option value="in">📥 Inbound (binnenkomend materiaal)</option>
                <option value="uit">📤 Outbound (verkoop/afvoer)</option>
                <option value="transfer">🔄 Transfer (tussen locaties)</option>
                <option value="adjustment">⚖️ Adjustment (correctie)</option>
            </select>
            <input type="date" name="datum" value="{{ vandaag }}">
        </div>
        <select name="materiaal" required>
            <option value="">Materiaal kiezen...</option>
            {% for categorie, kwaliteiten_lijst in materiaal_taxonomie.items() %}
            <optgroup label="{{ categorie }}">
                <option value="{{ categorie }}">{{ categorie }} (algemeen)</option>
                {% for kw in kwaliteiten_lijst %}<option value="{{ kw }}">{{ kw }}</option>{% endfor %}
            </optgroup>
            {% endfor %}
        </select>
        <div class="form-rij-2" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <input type="text" name="hoeveelheid" placeholder="Hoeveelheid (ton)" required>
            <div id="locatieVeldWrap"><input type="text" name="locatie" placeholder="Locatie" value="Alblasserdam" list="locatieLijstVoorraad"></div>
        </div>
        <datalist id="locatieLijstVoorraad">
            {% for loc in alle_locaties %}<option value="{{ loc }}">{% endfor %}
        </datalist>
        <div id="transferVeldWrap" style="display:none;">
            <div class="form-rij-2" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
                <input type="text" name="locatie_van" placeholder="Van locatie" list="locatieLijstVoorraad">
                <input type="text" name="locatie_naar" placeholder="Naar locatie" list="locatieLijstVoorraad">
            </div>
        </div>
        <div id="adjustmentVeldWrap" style="display:none;">
            <div class="form-rij-2" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
                <select name="richting"><option value="plus">➕ Voorraad erbij</option><option value="min">➖ Voorraad eraf</option></select>
                <input type="text" name="reden" placeholder="Reden (verplicht)">
            </div>
        </div>
        <div id="keuringVeldWrap">
            <select name="keuringsstatus">
                <option value="te_keuren">⏳ Te keuren (nog niet in handelsvoorraad)</option>
                <option value="goedgekeurd">✅ Direct goedgekeurd (telt meteen mee)</option>
            </select>
        </div>
        <div class="form-rij-2" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <input type="text" name="bedrijf" placeholder="Leverancier/klant (optioneel)" list="bedrijvenLijstVoorraad">
            <input type="text" name="prijs" placeholder="Prijs (optioneel)">
        </div>
        <datalist id="bedrijvenLijstVoorraad">
            {% for naam in alle_bedrijfsnamen_voorraad %}<option value="{{ naam }}">{% endfor %}
        </datalist>
        <textarea name="notitie" placeholder="Notitie (optioneel)" rows="2"></textarea>
        <button type="submit" class="btn-nav btn-nav-primary" style="border:none;cursor:pointer;width:100%;">+ Transactie toevoegen</button>
    </form>
</div>
{% endif %}
<script>
function toggleTransactieVelden() {
    const type = document.getElementById("voorraadTypeSelect").value;
    document.getElementById("keuringVeldWrap").style.display = (type === "in") ? "block" : "none";
    document.getElementById("transferVeldWrap").style.display = (type === "transfer") ? "block" : "none";
    document.getElementById("adjustmentVeldWrap").style.display = (type === "adjustment") ? "block" : "none";
    document.getElementById("locatieVeldWrap").style.display = (type === "transfer") ? "none" : "block";
}
</script>

<form method="GET" style="display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
    <select name="filter_type" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle transacties</option>
        <option value="in" {% if filter_type == "in" %}selected{% endif %}>Alleen binnenkomend</option>
        <option value="uit" {% if filter_type == "uit" %}selected{% endif %}>Alleen verkoop/afvoer</option>
    </select>
    <select name="filter_materiaal" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle materialen</option>
        {% for naam, aantal in voorraad_lijst %}<option value="{{ naam }}" {% if filter_materiaal == naam %}selected{% endif %}>{{ naam }}</option>{% endfor %}
    </select>
    <select name="filter_locatie" onchange="this.form.submit()" style="padding:7px 10px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;">
        <option value="">Alle locaties</option>
        {% for loc in alle_locaties %}<option value="{{ loc }}" {% if filter_locatie == loc %}selected{% endif %}>{{ loc }}</option>{% endfor %}
    </select>
    {% if filter_type or filter_materiaal or filter_locatie %}<a href="/voorraad" style="font-size:12px;color:var(--gray-400);text-decoration:none;">Wis filters</a>{% endif %}
    <span style="font-size:12px;color:var(--gray-400);margin-left:auto;">{{ getoonde_transacties|length }} van {{ transacties_gesorteerd|length }} transacties</span>
    <a href="/export-voorraad-csv?filter_type={{ filter_type }}&filter_materiaal={{ filter_materiaal|urlencode }}&filter_locatie={{ filter_locatie|urlencode }}" style="font-size:12px;font-weight:600;color:var(--brand-600);text-decoration:none;border:1px solid var(--gray-200);padding:5px 10px;border-radius:6px;">⬇ Export CSV</a>
</form>

<div class="vrd-kaart" style="margin-bottom:24px;">
    {% if getoonde_transacties %}
        {% for t in getoonde_transacties %}
        <div class="vrd-transactie">
            <div>
                {% if t.type == "transfer" %}<span style="background:#eef2ff;color:#4f46e5;font-weight:700;font-size:11px;padding:2px 8px;border-radius:5px;">🔄 TRANSFER</span>
                {% elif t.type == "adjustment" %}<span style="background:{{ '#f0fdf4' if t.get('richting') == 'plus' else '#fef2f2' }};color:{{ '#16a34a' if t.get('richting') == 'plus' else '#dc2626' }};font-weight:700;font-size:11px;padding:2px 8px;border-radius:5px;">⚖️ {{ 'CORRECTIE +' if t.get('richting') == 'plus' else 'CORRECTIE -' }}</span>
                {% else %}<span class="{{ 'vrd-badge-in' if t.type == 'in' else 'vrd-badge-uit' }}">{{ '📥 IN' if t.type == 'in' else '📤 UIT' }}</span>{% endif %}
                {% if t.type == "in" %}
                    {% if t.get("keuringsstatus","goedgekeurd") == "te_keuren" %}<span class="vrd-badge-te-keuren">⏳ Te keuren</span>
                    {% elif t.get("keuringsstatus") == "afgekeurd" %}<span class="vrd-badge-afgekeurd">✕ Afgekeurd</span>
                    {% else %}<span style="color:#16a34a;font-size:11px;">✓ Goedgekeurd</span>{% endif %}
                {% endif %}
                <b>{{ t.materiaal }}</b> · {{ t.hoeveelheid }} ton
                {% if t.type == "transfer" %} · 📍{{ t.locatie_van }} → {{ t.locatie_naar }}
                {% elif t.locatie %} · 📍{{ t.locatie }}{% endif %}
                {% if t.type == "adjustment" and t.reden %} · reden: {{ t.reden }}{% endif %}
                {% if t.bedrijf %} · {{ t.bedrijf }}{% endif %}
                {% if t.prijs %} · €{{ t.prijs }}{% endif %}
                <br><small style="color:var(--gray-400);">{{ t.datum }} · {{ t.gebruiker }}{% if t.notitie %} · {{ t.notitie }}{% endif %}</small>
            </div>
            <div style="display:flex;align-items:center;gap:8px;">
                {% if t.type == "in" and t.get("keuringsstatus","goedgekeurd") == "te_keuren" %}
                <form method="POST" style="margin:0;">
                    <input type="hidden" name="actie" value="keuring_wijzigen">
                    <input type="hidden" name="transactie_id" value="{{ t.id }}">
                    <input type="hidden" name="nieuwe_keuringsstatus" value="goedgekeurd">
                    <button type="submit" style="background:#f0fdf4;color:#16a34a;border:none;border-radius:5px;padding:4px 8px;cursor:pointer;font-size:11px;font-weight:700;">✓ Keur goed</button>
                </form>
                <form method="POST" style="margin:0;">
                    <input type="hidden" name="actie" value="keuring_wijzigen">
                    <input type="hidden" name="transactie_id" value="{{ t.id }}">
                    <input type="hidden" name="nieuwe_keuringsstatus" value="afgekeurd">
                    <button type="submit" style="background:#fef2f2;color:#dc2626;border:none;border-radius:5px;padding:4px 8px;cursor:pointer;font-size:11px;font-weight:700;">✕ Keur af</button>
                </form>
                {% endif %}
                <form method="POST" onsubmit="return confirm('Transactie verwijderen?');" style="margin:0;">
                    <input type="hidden" name="actie" value="verwijderen">
                    <input type="hidden" name="transactie_id" value="{{ t.id }}">
                    <button type="submit" style="background:none;border:none;color:var(--gray-300);cursor:pointer;font-size:1rem;">✕</button>
                </form>
            </div>
        </div>
        {% endfor %}
    {% else %}
    <div class="lege-staat">Geen transacties gevonden.</div>
    {% endif %}
</div>

<div class="dg-kaart-titel" style="margin-bottom:12px;">📋 Voorraadmomenten (fysieke telling)</div>
<p style="color:var(--gray-400);font-size:0.82rem;margin-top:-8px;margin-bottom:16px;">Leg een fysieke telling vast om te vergelijken met de berekende voorraad — handig om afwijkingen op te sporen.</p>

<div class="vrd-kaart" style="max-width:520px;margin-bottom:20px;">
    <form method="POST" class="form-voorraad">
        <input type="hidden" name="actie" value="moment_toevoegen">
        <div class="form-rij-2" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <select name="moment_materiaal" required>
                <option value="">Materiaal kiezen...</option>
                {% for categorie, kwaliteiten_lijst in materiaal_taxonomie.items() %}
                <optgroup label="{{ categorie }}">
                    <option value="{{ categorie }}">{{ categorie }} (algemeen)</option>
                    {% for kw in kwaliteiten_lijst %}<option value="{{ kw }}">{{ kw }}</option>{% endfor %}
                </optgroup>
                {% endfor %}
            </select>
            <input type="text" name="moment_hoeveelheid" placeholder="Getelde hoeveelheid (ton)" required>
        </div>
        <div class="form-rij-2" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <input type="text" name="moment_locatie" placeholder="Locatie" value="Alblasserdam" list="locatieLijstVoorraad">
            <input type="date" name="moment_datum" value="{{ vandaag }}">
        </div>
        <textarea name="moment_notitie" placeholder="Notitie (optioneel)" rows="2"></textarea>
        <button type="submit" class="btn-nav btn-nav-primary" style="border:none;cursor:pointer;width:100%;">+ Voorraadmoment vastleggen</button>
    </form>
</div>

<div class="vrd-kaart">
    {% if voorraadmomenten %}
        {% for m in voorraadmomenten %}
        <div class="vrd-transactie">
            <div>
                <b>{{ m.materiaal }}</b> · geteld: {{ m.hoeveelheid }} ton
                {% if m.locatie %} · 📍{{ m.locatie }}{% endif %}
                {% if m.verschil %}
                    <span style="color:{{ '#dc2626' if m.verschil|abs > 0.5 else 'var(--gray-400)' }};font-weight:700;">
                        ({{ '+' if m.verschil > 0 else '' }}{{ "{:,.1f}".format(m.verschil) }} vs berekend)
                    </span>
                {% else %}
                    <span style="color:#16a34a;">✓ komt overeen</span>
                {% endif %}
                <br><small style="color:var(--gray-400);">{{ m.datum }} · {{ m.gebruiker }}{% if m.notitie %} · {{ m.notitie }}{% endif %}</small>
            </div>
            <form method="POST" onsubmit="return confirm('Voorraadmoment verwijderen?');" style="margin:0;">
                <input type="hidden" name="actie" value="moment_verwijderen">
                <input type="hidden" name="moment_id" value="{{ m.id }}">
                <button type="submit" style="background:none;border:none;color:var(--gray-300);cursor:pointer;font-size:1rem;">✕</button>
            </form>
        </div>
        {% endfor %}
    {% else %}
    <div class="lege-staat">Nog geen voorraadmomenten vastgelegd.</div>
    {% endif %}
</div>
    """
    pagina = render_simple_page("Voorraad", "voorraad", inhoud)
    return render_template_string(pagina, voorraad_lijst=voorraad_lijst, transacties_gesorteerd=transacties_gesorteerd,
                                    getoonde_transacties=getoonde_transacties, filter_materiaal=filter_materiaal, filter_type=filter_type,
                                    materiaal_taxonomie=laad_materiaal_taxonomie(), alle_bedrijfsnamen_voorraad=alle_bedrijfsnamen_voorraad,
                                    vandaag=datetime.date.today().isoformat(),
                                    te_keuren_per_materiaal=te_keuren_per_materiaal, alle_locaties=alle_locaties, filter_locatie=filter_locatie,
                                    voorraadmomenten=voorraadmomenten,
                                    per_commodity=per_commodity, kpi_fysiek_totaal=kpi_fysiek_totaal,
                                    kpi_binnenkort_totaal=kpi_binnenkort_totaal, kpi_verkocht_totaal=kpi_verkocht_totaal,
                                    kpi_inkoop_totaal=kpi_inkoop_totaal, kpi_vrij_totaal=kpi_vrij_totaal,
                                    kpi_transit_totaal=kpi_transit_totaal, kpi_forecast_totaal=kpi_forecast_totaal,
                                    kpi_direct_flow_totaal=kpi_direct_flow_totaal, kpi_totaal_controlled=kpi_totaal_controlled,
                                    inkomend_7d=inkomend_7d, uitgaand_7d=uitgaand_7d,
                                    stock_per_locatie_lijst=stock_per_locatie_lijst, aging_buckets=aging_buckets,
                                    flow_by_origin_lijst=flow_by_origin_lijst, flow_by_destination_lijst=flow_by_destination_lijst,
                                    actieve_shipments=actieve_shipments, alle_shipments_dropdown=alle_shipments_dropdown,
                                    shipment_statussen=SHIPMENT_STATUSSEN, landen=_alle_bedrijven_landen,
                                    alle_contracten=alle_contracten, alle_handelsorder_contracten=alle_handelsorder_contracten,
                                    is_admin=is_huidige_gebruiker_admin(), prefill=prefill,
                                    fabrieken_overzicht_lijst=fabrieken_overzicht_lijst,
                                    getoonde_shipments=getoonde_shipments, filter_flow_type=filter_flow_type,
                                    filter_shipment_status=filter_shipment_status, filter_shipment_materiaal=filter_shipment_materiaal,
                                    shipment_materialen=shipment_materialen)