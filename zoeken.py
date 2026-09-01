"""
zoeken.py — Blueprint voor de Zoeken-, World Map- en Bedrijfsprofiel-modules.

De grootste en meest verweven module: hoofdzoekpagina (/, met kaart-tabel-
koppeling), World Map, bedrijfsprofiel (incl. fabrieken via dezelfde
profielpagina), export-csv/data, opgeslagen bedrijven, en alle bewerk-API's
die bij het profiel horen (status, accountmanager, bedrijfsveld,
materiaal-volume, fabriek-kwaliteiten, fabriek-analyse, transport, details).

Bewust als laatste Blueprint gebouwd: deze module raakt vrijwel alle andere
databronnen en was daarom het meest risicovol om als eerste te doen.

Registratie in app.py met: app.register_blueprint(zoeken_bp)
"""
import os
import json
import uuid
import datetime
import requests
from bs4 import BeautifulSoup
from flask import Blueprint, request, session, redirect, url_for, jsonify, render_template_string

from core import (
    datapad, laad_status, bewaar_status, laad_accountmanagers, bewaar_accountmanagers,
    laad_materiaal_taxonomie, laad_orders, laad_users, laad_notities, laad_meldingen,
    bewaar_meldingen, vereist_admin_of_403, render_simple_page, geocode_adres,
    bereken_afstand_km, vind_transport_tarieven_dichtbij, sync_contactpersoon_naar_contacten,
    parse_hoeveelheid_getal, voldoet_aan_materiaal_min_volume, is_huidige_gebruiker_admin,
    ENF_BEDRIJVEN, PAPIERFABRIEKEN, bewaar_bedrijven, bewaar_papierfabrieken, LANDEN,
    laad_shipments, shipment_hoeveelheid, ORDER_KLEUREN, mag_pagina_zien, vereist_afdeling_of_403,
    leverancier_instelling_voor, sidebar_html,
)

zoeken_bp = Blueprint("zoeken", __name__)

REGIO_PER_LAND = {}
for b in ENF_BEDRIJVEN:
    land = b["land"]
    regio = b["regio"]
    if land not in REGIO_PER_LAND:
        REGIO_PER_LAND[land] = set()
    REGIO_PER_LAND[land].add(regio)
REGIO_PER_LAND = {l: sorted(r) for l, r in REGIO_PER_LAND.items()}

def haal_bedrijf_details(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        tekst = soup.get_text()
        details = {}
        website = soup.find("a", href=lambda h: h and h.startswith("http") and "enfpaper" not in h)
        if website:
            details["website"] = website["href"]
        for tag in soup.find_all(["td", "div", "span"]):
            t = tag.get_text(strip=True)
            if "+" in t and any(c.isdigit() for c in t) and len(t) < 30:
                details["telefoon"] = t
                break
        lines = [l.strip() for l in tekst.split("\n") if l.strip()]
        for i, line in enumerate(lines):
            if "No. Staff" in line and i+1 < len(lines):
                details["medewerkers"] = lines[i+1]
            if "Type of Recycled" in line and i+1 < len(lines):
                details["materialen_detail"] = lines[i+1]

        adres_tag = soup.find("span", {"itemprop": "streetAddress"})
        stad_tag = soup.find("span", {"itemprop": "addressLocality"})
        if adres_tag:
            details["adres"] = adres_tag.get_text(strip=True)
        if stad_tag:
            details["stad"] = stad_tag.get_text(strip=True)

        if details.get("adres") and details.get("stad"):
            geo = geocode_adres(details["adres"], details["stad"])
            if geo:
                details["lat_precies"] = geo["lat"]
                details["lon_precies"] = geo["lon"]

        return details
    except:
        return {}


HTML = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FTNext — Global Recycling Intelligence</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<style>
.marker-cluster-small { background-color: rgba(179,217,218,0.7); }
.marker-cluster-small div { background-color: rgba(63,146,149,0.85); color: #fff; }
.marker-cluster-medium { background-color: rgba(63,146,149,0.6); }
.marker-cluster-medium div { background-color: rgba(20,118,123,0.9); color: #fff; }
.marker-cluster-large { background-color: rgba(10,74,79,0.6); }
.marker-cluster-large div { background-color: rgba(10,74,79,0.95); color: #fff; }
.marker-cluster div { font-weight: 700; font-family: 'Libre Franklin', -apple-system, sans-serif; }
</style>
    <link href="https://fonts.googleapis.com/css2?family=Libre+Franklin:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        /* ============================================
           DESIGN SYSTEM — RECYCLEFIND
           ============================================ */

        /* TOKENS */
        :root {
            /* Colors */
            --brand-50:  #eef6f6;
            --brand-100: #d9ecec;
            --brand-200: #b3d9da;
            --brand-300: #7fb9bb;
            --brand-400: #3f9295;
            --brand-500: #14767b;
            --brand-600: #0d5c62;
            --brand-700: #0a4a4f;
            --brand-800: #083c40;
            --brand-900: #062f33;

            --gray-50:  #f8fafc;
            --gray-100: #f1f5f9;
            --gray-200: #e2e8f0;
            --gray-300: #cbd5e1;
            --gray-400: #94a3b8;
            --gray-500: #64748b;
            --gray-600: #475569;
            --gray-700: #334155;
            --gray-800: #1e293b;
            --gray-900: #0f172a;

            --green-50:  #f0fdf4;
            --green-500: #22c55e;
            --green-600: #16a34a;

            --orange-50:  #eef6f6;
            --orange-500: #14767b;
            --orange-600: #0d5c62;

            --red-50:  #fef2f2;
            --red-500: #ef4444;

            /* Typography */
            --font: "Libre Franklin", -apple-system, sans-serif;
            --font-mono: "IBM Plex Mono", monospace;
            --text-xs:   0.7rem;
            --text-sm:   0.8rem;
            --text-base: 0.9rem;
            --text-lg:   1.05rem;
            --text-xl:   1.2rem;
            --text-2xl:  1.5rem;
            --text-3xl:  2rem;
            --text-4xl:  2.8rem;
            --text-5xl:  3.5rem;

            /* Spacing */
            --space-1: 4px;
            --space-2: 8px;
            --space-3: 12px;
            --space-4: 16px;
            --space-5: 20px;
            --space-6: 24px;
            --space-8: 32px;
            --space-10: 40px;
            --space-12: 48px;
            --space-16: 64px;

            /* Radius */
            --radius-sm: 6px;
            --radius-md: 10px;
            --radius-lg: 14px;
            --radius-xl: 20px;
            --radius-full: 9999px;

            /* Shadows */
            --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
            --shadow-md: 0 4px 12px rgba(0,0,0,0.08);
            --shadow-lg: 0 8px 24px rgba(0,0,0,0.1);
            --shadow-xl: 0 16px 48px rgba(0,0,0,0.12);
            --shadow-brand: 0 4px 14px rgba(37,99,235,0.25);

            /* Transitions */
            --transition: all 0.2s cubic-bezier(0.4,0,0.2,1);
        }

        /* RESET */
        *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
        html { scroll-behavior: smooth; }
        body { font-family: var(--font); background: var(--gray-50); color: var(--gray-800); min-height: 100vh; -webkit-font-smoothing: antialiased; }

        /* ============================================
           NAVBAR
           ============================================ */
        .navbar {
            position: sticky;
            top: 0;
            z-index: 100;
            background: rgba(255,255,255,0.9);
            backdrop-filter: blur(12px);
            border-bottom: 1px solid var(--gray-200);
            height: 56px;
            display: flex;
            align-items: center;
            padding: 0 var(--space-8);
            gap: var(--space-8);
        }
        .navbar-logo {
            font-size: var(--text-lg);
            font-weight: 800;
            color: var(--gray-900);
            letter-spacing: -0.5px;
            text-decoration: none;
            flex-shrink: 0;
        }
        .navbar-logo em { color: var(--brand-600); font-style: normal; }
        .navbar-divider { width: 1px; height: 20px; background: var(--gray-200); }
        .navbar-stat { font-size: var(--text-xs); color: var(--gray-400); white-space: nowrap; }
        .navbar-stat strong { color: var(--brand-600); font-weight: 600; }
        .navbar-right { margin-left: auto; display: flex; align-items: center; gap: var(--space-3); }
        .btn-nav {
            font-size: var(--text-sm);
            font-weight: 500;
            padding: 6px 14px;
            border-radius: var(--radius-sm);
            border: none;
            cursor: pointer;
            font-family: var(--font);
            transition: var(--transition);
            text-decoration: none;
        }
        .btn-nav-ghost { background: transparent; color: var(--gray-600); }
        .btn-nav-ghost:hover { background: var(--gray-100); color: var(--gray-900); }
        .btn-nav-primary { background: var(--brand-600); color: #fff; }
        .btn-nav-primary:hover { background: var(--brand-700); box-shadow: var(--shadow-brand); }

        /* ============================================
           HERO
           ============================================ */
        .search-bar-section {
            background: transparent;
            padding: 16px 24px 16px 20px;
            border-bottom: none;
        }
        @media (max-width: 1200px) { .search-bar-section { padding: 16px 16px 16px 0; } }
        @media (max-width: 768px)  { .search-bar-section { padding: 12px 12px 12px 0; } }
        .hero-content {
            width: 100%;
            max-width: min(1700px, calc(100vw - 260px));
            box-sizing: border-box;
            margin: 0;
        }

        /* ============================================
           SEARCH
           ============================================ */
        .search-container {
            background: #fff;
            border: 1px solid #E5E7EB;
            border-radius: 10px;
            width: 100%;
            max-width: 820px;
            margin: 0;
            box-shadow: none;
            overflow: hidden;
            height: 44px;
        }
        .search-row {
            display: flex;
            align-items: stretch;
            height: 44px;
        }
        .search-input, .search-select {
            background: transparent;
            border: none;
            border-right: 1px solid var(--gray-100);
            border-radius: 0;
            padding: 0 14px;
            font-size: 14px;
            font-family: var(--font);
            color: var(--gray-800);
            outline: none;
            transition: var(--transition);
            height: 44px;
            box-sizing: border-box;
        }
        .search-input { flex: 1; min-width: 140px; }
        .search-input::placeholder { color: #94A3B8; }
        .search-select { width: 130px; cursor: pointer; flex: none; }
        .search-input:focus, .search-select:focus {
            background: var(--gray-50);
        }
        .btn-search {
            background: var(--brand-600);
            color: #fff;
            border: none;
            border-radius: 0;
            padding: 0 20px;
            font-size: 14px;
            font-weight: 700;
            font-family: var(--font);
            cursor: pointer;
            transition: var(--transition);
            white-space: nowrap;
            flex: none;
            height: 44px;
            box-sizing: border-box;
        }
        .btn-search:hover { background: var(--brand-700); }
        .btn-search:hover { background: var(--brand-400); transform: translateY(-1px); box-shadow: var(--shadow-brand); }

        /* ============================================
           STATS BAR
           ============================================ */
        .stats-bar {
            background: #fff;
            border-bottom: 1px solid var(--gray-200);
            padding: var(--space-4) var(--space-10);
            display: flex;
            justify-content: center;
            gap: var(--space-12);
        }
        .stat { text-align: center; }
        .stat-num { font-size: var(--text-2xl); font-weight: 800; color: var(--brand-600); letter-spacing: -0.5px; }
        .stat-label { font-size: var(--text-xs); color: var(--gray-400); text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; margin-top: 2px; }

        /* ============================================
           MAIN LAYOUT
           ============================================ */
        .main {
            width: 100%;
            max-width: min(1700px, calc(100vw - 260px));
            box-sizing: border-box;
            margin: var(--space-6) 0 0 0;
            padding: 0 24px 0 0;
            display: flex;
            gap: 0;
            align-items: flex-start;
            position: relative;
        }
        @media (max-width: 1200px) { .main { padding: 0 16px 0 0; } }
        @media (max-width: 768px)  { .main { padding: 0 12px; max-width: 100%; } }

        /* ============================================
           FILTERS SIDEBAR
           ============================================ */
        .filters-panel {
            width: 300px;
            max-width: calc(100vw - 32px);
            position: fixed;
            top: 44px;
            left: 16px;
            z-index: 9999;
            background: #fff;
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-lg);
            padding: var(--space-5);
            box-shadow: 0 18px 44px -12px rgba(27,31,38,.28);
            max-height: 70vh;
            overflow-y: auto;
            box-sizing: border-box;
        }
        .filters-title {
            font-size: var(--text-xs);
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: var(--gray-400);
            margin-bottom: var(--space-4);
        }
        .filter-group { margin-bottom: var(--space-4); }
        .filter-label {
            font-size: var(--text-xs);
            font-weight: 600;
            color: var(--gray-600);
            margin-bottom: var(--space-2);
            display: block;
        }
        .filter-select {
            width: 100%;
            background: var(--gray-50);
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-sm);
            padding: 7px 10px;
            font-size: var(--text-sm);
            font-family: var(--font);
            color: var(--gray-700);
            outline: none;
            cursor: pointer;
            transition: var(--transition);
        }
        .filter-select:focus { border-color: var(--brand-400); background: #fff; }
        .filter-divider { border: none; border-top: 1px solid var(--gray-100); margin: var(--space-4) 0; }
        .btn-apply {
            width: 100%;
            background: var(--brand-600);
            color: #fff;
            border: none;
            border-radius: var(--radius-sm);
            padding: 9px;
            font-size: var(--text-sm);
            font-weight: 600;
            font-family: var(--font);
            cursor: pointer;
            transition: var(--transition);
        }
        .btn-apply:hover { background: var(--brand-700); }
        .btn-reset {
            width: 100%;
            background: transparent;
            color: var(--gray-400);
            border: 1px solid var(--gray-200);
            border-radius: var(--radius-sm);
            padding: 8px;
            font-size: var(--text-xs);
            font-family: var(--font);
            cursor: pointer;
            margin-top: var(--space-2);
            transition: var(--transition);
        }
        .btn-reset:hover { color: var(--gray-600); border-color: var(--gray-300); }

        /* ============================================
           RESULTS PANEL
           ============================================ */
        .results-panel { flex: 1; min-width: 0; }
        .results-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 0;
            padding: 10px 16px;
            background: var(--gray-50);
            border-top: 1px solid var(--gray-200);
        }
        .results-count { font-size: var(--text-sm); color: var(--gray-400); }
        .results-count strong { color: var(--brand-600); font-weight: 700; }
        .results-list { }
        .data-thead, .data-row { display: flex; align-items: center; padding: 0 var(--space-3); }
        .data-thead {
            padding-top: 10px; padding-bottom: 10px;
            background: var(--gray-50); border-bottom: 1px solid var(--gray-200);
            font-size: 10px; letter-spacing: 0.08em; text-transform: uppercase; color: #7d8792;
            position: sticky; top: 0; z-index: 2; border-radius: var(--radius-md) var(--radius-md) 0 0;
        }
        .data-thead span[data-sort] { cursor: pointer; user-select: none; }
        .data-thead span[data-sort]:hover { color: var(--brand-600); }
        .data-row {
            padding-top: 9px; padding-bottom: 9px;
            border-bottom: 1px solid var(--gray-100);
            font-size: 13px; cursor: pointer; text-decoration: none; color: inherit;
        }
        .data-row:hover { background: #f9fbfc; }
        .data-row .num { font-family: var(--font-mono); font-size: 12.5px; }
        .data-row .zacht { color: #4b5563; font-size: 12.5px; }

        /* ============================================
           COMPANY CARD
           ============================================ */
        .company-card {
            position: relative;
            background: #fff;
            border: 1px solid var(--gray-200);
            border-left: 3px solid transparent;
            border-radius: var(--radius-md);
            padding: var(--space-4);
            margin-bottom: var(--space-2);
            cursor: pointer;
            transition: var(--transition);
        }
        .company-card:hover {
            border-color: var(--brand-300);
            border-left-color: var(--brand-500);
            box-shadow: 0 8px 20px rgba(234,88,12,0.10);
            transform: translateY(-2px);
        }
        .company-card-top { display: flex; align-items: flex-start; gap: var(--space-3); margin-bottom: var(--space-2); }
        .company-index {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 22px;
            height: 22px;
            min-width: 22px;
            background: var(--brand-600);
            color: #fff;
            border-radius: 5px;
            font-size: 0.65rem;
            font-weight: 700;
            margin-top: 1px;
        }
        .company-name { font-size: var(--text-base); font-weight: 700; color: var(--gray-800); line-height: 1.3; letter-spacing: -0.2px; }
        .verificatie-badge {
            display: inline-flex; align-items: center; gap: 3px;
            font-size: 0.62rem; font-weight: 700; color: var(--green-600);
            background: var(--green-50); border: 1px solid #bbf7d0;
            padding: 1px 6px; border-radius: 4px; margin-left: 6px; vertical-align: middle;
        }
        .company-meta { font-size: var(--text-xs); color: var(--gray-400); margin-bottom: var(--space-2); padding-left: 34px; display: flex; align-items: center; gap: 4px; }
        .company-volume-badge {
            padding-left: 34px; margin-bottom: 6px; font-size: 0.72rem; font-weight: 700; color: var(--brand-700);
        }
        .company-tags { display: flex; flex-wrap: wrap; gap: 4px; padding-left: 34px; }
        .tag {
            display: inline-flex;
            align-items: center;
            padding: 2px 7px;
            border-radius: 4px;
            font-size: 0.65rem;
            font-weight: 600;
            letter-spacing: 0.2px;
        }
        .tag-blue { background: var(--brand-50); color: var(--brand-700); border: 1px solid var(--brand-100); }
        .tag-green { background: var(--green-50); color: var(--green-600); border: 1px solid #bbf7d0; }
        .tag-orange { background: var(--orange-50); color: var(--orange-600); border: 1px solid #b3d9da; }
        .tag-purple { background: #f5f3ff; color: #7c3aed; border: 1px solid #ddd6fe; }

        /* ============================================
           MAP
           ============================================ */
        .kaart-tabel-blok {
            width: 100%;
            border: none;
            border-radius: 0;
            box-shadow: none;
            overflow: visible;
            background: transparent;
        }
        .map-panel { width: 100%; margin-bottom: 0; }
        #kaart {
            height: 340px;
            border-radius: 0;
            border: 1px solid var(--gray-200);
            box-shadow: none;
        }

        /* ============================================
           DETAIL DRAWER
           ============================================ */
        .overlay {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(15,23,42,0.35);
            z-index: 9999;
            backdrop-filter: blur(3px);
        }
        .drawer {
            position: fixed;
            top: 0;
            right: -500px;
            width: 460px;
            height: 100vh;
            background: #fff;
            border-left: 1px solid var(--gray-200);
            box-shadow: var(--shadow-xl);
            z-index: 10000;
            overflow-y: auto;
            transition: right 0.3s cubic-bezier(0.4,0,0.2,1);
        }
        .drawer.open { right: 0; }
        .drawer-header {
            padding: var(--space-6) var(--space-6) var(--space-4);
            border-bottom: 1px solid var(--gray-100);
            position: sticky;
            top: 0;
            background: #fff;
            z-index: 1;
        }
        .drawer-close {
            position: absolute;
            top: var(--space-4);
            right: var(--space-4);
            width: 28px;
            height: 28px;
            background: var(--gray-100);
            border: none;
            border-radius: var(--radius-sm);
            color: var(--gray-500);
            cursor: pointer;
            font-size: 0.9em;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: var(--transition);
        }
        .drawer-close:hover { background: var(--gray-200); color: var(--gray-800); }
        .drawer-company-name { font-size: var(--text-xl); font-weight: 700; color: var(--gray-900); margin-bottom: 4px; padding-right: 36px; }
        .drawer-company-loc { font-size: var(--text-sm); color: var(--gray-400); }
        .drawer-body { padding: var(--space-5) var(--space-6); }
        .drawer-section { margin-bottom: var(--space-5); }
        .drawer-section-title {
            font-size: var(--text-xs);
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: var(--gray-400);
            margin-bottom: var(--space-3);
        }
        .drawer-row {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: var(--space-2) 0;
            border-bottom: 1px solid var(--gray-50);
        }
        .drawer-row:last-child { border-bottom: none; }
        .drawer-row-label { font-size: var(--text-sm); color: var(--gray-400); font-weight: 500; }
        .drawer-row-value { font-size: var(--text-sm); color: var(--gray-700); font-weight: 500; text-align: right; }
        .drawer-divider { border: none; border-top: 1px solid var(--gray-100); margin: var(--space-4) 0; }
        .btn-website {
            display: inline-flex;
            align-items: center;
            gap: var(--space-2);
            background: var(--brand-600);
            color: #fff;
            padding: 8px 16px;
            border-radius: var(--radius-sm);
            text-decoration: none;
            font-size: var(--text-sm);
            font-weight: 600;
            transition: var(--transition);
            margin-right: var(--space-2);
        }
        .btn-website:hover { background: var(--brand-700); box-shadow: var(--shadow-brand); }
        .btn-enf {
            display: inline-flex;
            align-items: center;
            gap: var(--space-2);
            background: var(--gray-100);
            color: var(--gray-600);
            padding: 8px 16px;
            border-radius: var(--radius-sm);
            text-decoration: none;
            font-size: var(--text-sm);
            font-weight: 600;
            transition: var(--transition);
        }
        .btn-enf:hover { background: var(--gray-200); color: var(--gray-800); }
        .score-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 36px;
            height: 36px;
            border-radius: var(--radius-sm);
            font-size: var(--text-sm);
            font-weight: 800;
        }
        .score-high { background: var(--green-50); color: var(--green-600); }
        .score-mid { background: var(--orange-50); color: var(--orange-600); }

        /* ============================================
           WELCOME STATE
           ============================================ */
        .welcome-state {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: var(--space-16);
            text-align: center;
        }
        .welcome-icon { font-size: 3em; margin-bottom: var(--space-4); }
        .welcome-title { font-size: var(--text-2xl); font-weight: 700; color: var(--gray-800); margin-bottom: var(--space-2); }
        .welcome-sub { font-size: var(--text-base); color: var(--gray-400); max-width: 400px; }

        /* ============================================
           SIDEBAR
           ============================================ */
        body { display: flex; }
        .sidebar {
            width: 240px;
            min-width: 240px;
            height: 100vh;
            position: sticky;
            top: 0;
            background: #1b1f26;
            display: flex;
            flex-direction: column;
            padding: var(--space-5) 0;
            flex-shrink: 0;
        }
        .sidebar-logo {
            font-size: var(--text-lg);
            font-weight: 600;
            color: #fff;
            letter-spacing: -0.5px;
            text-decoration: none;
            padding: 0 var(--space-5);
            margin-bottom: var(--space-2);
            display: flex;
            align-items: center;
            gap: 9px;
        }
        .sidebar-mark {
            width: 22px; height: 22px; flex: none;
            background: var(--brand-600); border-radius: 3px;
            display: inline-flex; align-items: center; justify-content: center;
            color: #fff; font-size: 11px; font-weight: 700; font-family: var(--font-mono);
            margin-right: 9px; vertical-align: middle;
        }
        .sidebar-logo em { color: #fff; font-style: normal; }
        .sidebar-cap { padding: 0 var(--space-5) 8px; font-family: var(--font-mono); font-size: 9px; letter-spacing: .16em; text-transform: uppercase; color: #626d7a; margin-bottom: var(--space-2); }
        .sidebar-nav { display: flex; flex-direction: column; gap: 1px; padding: 0 var(--space-3); }
        .sidebar-link {
            display: flex;
            align-items: center;
            gap: var(--space-3);
            padding: 9px var(--space-3);
            border-radius: var(--radius-sm);
            color: #aeb7c2;
            text-decoration: none;
            font-size: var(--text-sm);
            font-weight: 500;
            transition: var(--transition);
        }
        .sidebar-link:hover { background: #232830; color: #fff; }
        .sidebar-link.active { background: #232830; color: #fff; font-weight: 600; box-shadow: inset 3px 0 0 var(--brand-600); }
        .sidebar-link .icoon { font-family: var(--font-mono); font-size: 9px; color: #59636f; width: 18px; text-align: left; }
        .sidebar-me { margin-top: auto; padding: var(--space-4) var(--space-5) 0; border-top: 1px solid #2b3138; display: flex; align-items: center; gap: 9px; }
        .sidebar-avatar { width: 26px; height: 26px; flex: none; border-radius: 50%; background: #2f3641; display: flex; align-items: center; justify-content: center; font-size: 11px; color: #cdd4dc; }
        .sidebar-me-naam { font-size: 12.5px; color: #e6eaef; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .sidebar-me-rol { font-size: 10.5px; color: #6d7783; }
        .sidebar-me-uit { margin-left: auto; font-size: 15px; color: #6d7783; text-decoration: none; }
        .sidebar-me-uit:hover { color: #fff; }
        .content-wrapper { flex: 1; min-width: 0; }
        .mobiel-menu-knop { display: none; }
        .mobiel-overlay { display: none; }
        @media (max-width: 900px) {
            .sidebar {
                position: fixed;
                left: -240px;
                top: 0;
                z-index: 2000;
                transition: left 0.25s ease;
                box-shadow: 0 0 24px rgba(0,0,0,0.18);
            }
            .sidebar.open { left: 0; }
            .mobiel-menu-knop {
                display: flex;
                align-items: center;
                justify-content: center;
                width: 38px; height: 38px;
                border: 1px solid var(--gray-200); background: #fff;
                border-radius: 8px; cursor: pointer; font-size: 18px;
                position: fixed; top: 12px; left: 12px; z-index: 1500;
                box-shadow: var(--shadow-sm);
            }
            .mobiel-overlay.open {
                display: block;
                position: fixed; inset: 0; background: rgba(15,23,42,0.35); z-index: 1900;
            }
            .content-wrapper { padding-top: 52px; }
            .page-content { padding: var(--space-4) !important; }
            .main { flex-direction: column; padding: 0 var(--space-3); }
            .filters-panel { width: 100%; box-sizing: border-box; }
            .results-panel { width: 100%; }
            #kaart { height: 320px; }
            .map-panel { width: 100%; }
            .drawer { width: 100%; right: -100%; }
            .navbar { padding: 0 var(--space-4) 0 56px; flex-wrap: wrap; height: auto; min-height: 56px; gap: var(--space-3); }
            .navbar-stat { display: none; }
            .hero-content, .search-bar-section { padding-left: var(--space-3); padding-right: var(--space-3); }
            .search-row { flex-direction: column; align-items: stretch; }
            .search-input, .search-select { width: 100%; box-sizing: border-box; }
            .dg-grid { grid-template-columns: repeat(2, 1fr) !important; }
            .dg-rij-2 { flex-direction: column; }
            .profiel-grid { grid-template-columns: 1fr !important; }
            .drawer-row { flex-direction: column; align-items: flex-start; gap: 4px; }
            .drawer-row-value { text-align: left; width: 100%; }
            .drawer-row-value input[type="text"] { width: 100% !important; text-align: left !important; box-sizing: border-box; }
            .vrd-2koloms { grid-template-columns: 1fr !important; }
        }


        /* ============================================
           COLLAPSIBLE (uitklapbare secties in het paneel)
           ============================================ */
        .drawer-tabs { display: flex; gap: var(--space-1); border-bottom: 1px solid var(--gray-100); margin-bottom: var(--space-4); }
        .drawer-tab {
            background: none; border: none; cursor: pointer; font-family: var(--font);
            font-size: var(--text-sm); font-weight: 600; color: var(--gray-400);
            padding: var(--space-2) var(--space-1); margin-bottom: -1px;
            border-bottom: 2px solid transparent; transition: var(--transition);
        }
        .drawer-tab:hover { color: var(--gray-700); }
        .drawer-tab.actief { color: var(--brand-600); border-bottom-color: var(--brand-600); }
        .drawer-tab-paneel { display: none; }
        .drawer-tab-paneel.actief { display: block; }
        .collapsible-card { border: 1px solid var(--gray-200); border-radius: var(--radius-md); margin-bottom: var(--space-3); overflow: hidden; }
        .collapsible-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: var(--space-3) var(--space-4);
            background: var(--gray-50);
            cursor: pointer;
            user-select: none;
        }
        .collapsible-header-left { display: flex; align-items: center; gap: var(--space-2); font-weight: 700; font-size: var(--text-sm); color: var(--gray-800); }
        .collapsible-arrow { transition: transform 0.2s ease; color: var(--gray-400); }
        .collapsible-arrow.dicht { transform: rotate(-90deg); }
        .collapsible-body { padding: var(--space-4); }
        .collapsible-body.dicht { display: none; }

        /* ============================================
           SIMPELE PAGINA-KAARTEN (Dashboard/Inzichten/etc.)
           ============================================ */
        .page-content { padding: var(--space-8) var(--space-10); max-width: 1200px; }
        .page-title { font-size: 24px; font-weight: 600; letter-spacing: -0.025em; color: var(--gray-900); margin: 0 0 5px; }
        .kaartjes-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: var(--space-4); margin-bottom: var(--space-8); }
        .info-kaart { background: #fff; border: 1px solid var(--gray-200); border-radius: var(--radius-lg); padding: var(--space-5); }
        .info-kaart-getal { font-size: var(--text-3xl); font-weight: 800; color: var(--brand-600); }
        .info-kaart-label { font-size: var(--text-sm); color: var(--gray-400); margin-top: 4px; }
        .eenvoudige-tabel { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid var(--gray-200); border-radius: var(--radius-lg); overflow: hidden; }
        .eenvoudige-tabel th { text-align: left; padding: 10px 14px; background: var(--gray-50); font-size: var(--text-xs); text-transform: uppercase; color: var(--gray-400); border-bottom: 1px solid var(--gray-200); }
        .eenvoudige-tabel td { padding: 10px 14px; border-bottom: 1px solid var(--gray-100); font-size: var(--text-sm); color: var(--gray-700); }
        .lege-staat { text-align: center; padding: var(--space-16); color: var(--gray-400); }
    </style>
</head>
<body>

{{ sidebar_html_ingevoegd|safe }}
<script>
var CSRF_TOKEN = "{{ csrf_token }}";
// Vangnet voor formulieren die (nu of later) geen csrf_token-veld hebben —
// zelfde patroon als render_simple_page() in core.py.
document.addEventListener("submit", function(e) {
    var form = e.target;
    if (form.tagName === "FORM" && (form.method || "get").toLowerCase() === "post") {
        if (!form.querySelector('input[name="csrf_token"]')) {
            var veld = document.createElement("input");
            veld.type = "hidden";
            veld.name = "csrf_token";
            veld.value = CSRF_TOKEN;
            form.appendChild(veld);
        }
    }
}, true);
// Zelfde patroon als render_simple_page() in core.py: automatisch de CSRF-header
// toevoegen aan elke fetch()-aanroep vanaf deze pagina (bv. wijzigBedrijfVeld,
// wijzigMateriaalCheckbox) — zonder dit faalden die stilzwijgend met een 400.
var _origineleFetch = window.fetch;
window.fetch = function(url, opties) {
    opties = opties || {};
    var methode = (opties.method || "GET").toUpperCase();
    if (["POST","PUT","DELETE","PATCH"].indexOf(methode) !== -1) {
        opties.headers = opties.headers || {};
        if (opties.headers instanceof Headers) {
            opties.headers.set("X-CSRF-Token", CSRF_TOKEN);
        } else {
            opties.headers["X-CSRF-Token"] = CSRF_TOKEN;
        }
    }
    return _origineleFetch.call(this, url, opties);
};
</script>

<div class="content-wrapper">

<!-- ZOEKBALK -->
<section class="search-bar-section">
    <div class="hero-content" style="display:flex;align-items:center;gap:14px;">
        <form method="POST" id="searchForm" style="flex:1;">
            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
            <div class="search-container">
                <div class="search-row">
                    <input class="search-input" name="zoekterm" placeholder="Bedrijf, contactpersoon of stad..." value="{{ zoekterm }}">
                    <select class="search-select" name="land" id="landSelect" onchange="updateRegio()">
                        <option value="">All Countries</option>
                        {% for l in landen %}
                        <option value="{{ l }}" {% if land == l %}selected{% endif %}>{{ l }}</option>
                        {% endfor %}
                    </select>
                    <select class="search-select" name="regio" id="regioSelect">
                        <option value="">All Regions</option>
                        {% if land and land in regio_per_land %}
                        {% for r in regio_per_land[land] %}
                        <option value="{{ r }}" {% if regio == r %}selected{% endif %}>{{ r }}</option>
                        {% endfor %}
                        {% endif %}
                    </select>
                    <button type="submit" class="btn-search">Search →</button>
                </div>
            </div>
        </form>
        <button onclick="toonMeldingen()" style="background:none;border:none;cursor:pointer;font-size:13px;font-weight:600;color:var(--gray-500);white-space:nowrap;flex:none;padding:8px 4px;font-family:inherit;display:inline-flex;align-items:center;gap:5px;">
            <span style="white-space:nowrap;">Meldingen</span><span id="meldingBadge" style="display:none;background:var(--brand-600);color:#fff;font-size:11px;font-weight:700;border-radius:9px;padding:1px 7px;white-space:nowrap;"></span>
        </button>

    </div>
</section>

<!-- MAIN -->
<div class="main">

    {% if bedrijven %}
    <!-- FILTERS -->
    <form method="POST" id="filterForm" style="flex:0 0 0;width:0;margin:0;padding:0;overflow:visible;">
            <input type="hidden" name="csrf_token" value="{{ csrf_token }}">
        <input type="hidden" name="zoekterm" value="{{ zoekterm }}">
        <input type="hidden" name="land" value="{{ land }}">
        <input type="hidden" name="regio" value="{{ regio }}">
        <aside class="filters-panel" id="filtersPaneel" style="display:none;">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:var(--space-3);">
                <div class="filters-title" style="margin-bottom:0;display:flex;align-items:center;gap:8px;">
                    🎚️ Filters
                    {% if actieve_filter_count > 0 %}<span style="background:var(--brand-600);color:#fff;font-size:11px;font-weight:700;padding:1px 7px;border-radius:10px;">{{ actieve_filter_count }}</span>{% endif %}
                </div>
                <div style="display:flex;align-items:center;gap:10px;">
                    {% if actieve_filter_count > 0 %}<a href="/" style="font-size:var(--text-xs);color:var(--gray-400);text-decoration:none;font-weight:600;">Wis alles</a>{% endif %}
                    <button type="button" onclick="toggleFiltersPaneel()" style="background:none;border:none;color:var(--gray-400);cursor:pointer;font-size:1.1rem;line-height:1;padding:0;">✕</button>
                </div>
            </div>

            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:var(--space-2);">Bedrijfsprofiel</div>

            <div class="filter-group">
                <label class="filter-label">Customer Type</label>
                <select class="filter-select" name="klanttype">
                    <option value="">All types</option>
                    <option value="Commercial" {% if klanttype == "Commercial" %}selected{% endif %}>Commercial</option>
                    <option value="Industrial" {% if klanttype == "Industrial" %}selected{% endif %}>Industrial</option>
                    <option value="Residential" {% if klanttype == "Residential" %}selected{% endif %}>Residential</option>
                </select>
            </div>

            <div class="filter-group">
                <label class="filter-label">Bedrijfstype</label>
                <select class="filter-select" name="brontype">
                    <option value="">Alle types</option>
                    <option value="Schroothandel" {% if brontype == "Schroothandel" %}selected{% endif %}>Schroothandel</option>
                    <option value="Recyclingcentrum" {% if brontype == "Recyclingcentrum" %}selected{% endif %}>Recyclingcentrum</option>
                    <option value="Papierfabriek" {% if brontype == "Papierfabriek" %}selected{% endif %}>Papierfabriek</option>
                    <option value="Recycling-kantoor" {% if brontype == "Recycling-kantoor" %}selected{% endif %}>Recycling-kantoor</option>
                    <option value="Afvalbeheer" {% if brontype == "Afvalbeheer" %}selected{% endif %}>Afvalbeheer</option>
                </select>
            </div>

            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin:var(--space-4) 0 var(--space-2);">Materiaal</div>

            <div class="filter-group">
                <label class="filter-label">Material</label>
                <select class="filter-select" name="materiaal">
                    <option value="">All materials</option>
                    {% for cat_naam in materiaal_categorieen %}
                    <option value="{{ cat_naam }}" {% if materiaal == cat_naam %}selected{% endif %}>{{ cat_naam }}</option>
                    {% endfor %}
                </select>
            </div>

            <div class="filter-group">
                <label class="filter-label">Min. volume van dit materiaal (t/j)</label>
                <input type="number" class="filter-select" name="materiaal_min_volume" value="{{ materiaal_min_volume }}" placeholder="bv. 1000" min="0">
            </div>

            <div class="filter-group">
                <label class="filter-label">Kwaliteiten</label>
                <input type="text" class="filter-select" name="kwaliteiten" value="{{ kwaliteiten }}" placeholder="bv. OCC, HDPE...">
            </div>

            <div class="filter-group">
                <label class="filter-label">Annual Volume</label>
                <select class="filter-select" name="volume_filter">
                    <option value="">Any volume</option>
                    <option value="small" {% if volume_filter == "small" %}selected{% endif %}>Under 1,000 t/y</option>
                    <option value="medium" {% if volume_filter == "medium" %}selected{% endif %}>1,000 – 10,000 t/y</option>
                    <option value="large" {% if volume_filter == "large" %}selected{% endif %}>Over 10,000 t/y</option>
                </select>
            </div>

            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin:var(--space-4) 0 var(--space-2);">Team</div>

            <div class="filter-group">
                <label class="filter-label">Accountmanager</label>
                <select class="filter-select" name="accountmanager">
                    <option value="">Alle bedrijven</option>
                    <option value="__mij__" {% if accountmanager == "__mij__" %}selected{% endif %}>🙋 Alleen mijn bedrijven</option>
                    {% for gebruikersnaam in alle_gebruikersnamen %}
                    <option value="{{ gebruikersnaam }}" {% if accountmanager == gebruikersnaam %}selected{% endif %}>{{ gebruikersnaam }}</option>
                    {% endfor %}
                </select>
            </div>

            <hr class="filter-divider">
            <button type="submit" class="btn-apply">Filters toepassen</button>
        </aside>
    </form>

    <!-- RESULTS -->
    <div class="results-panel">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:14px;flex-wrap:wrap;gap:12px;padding-left:20px;">
            <div>
                <div style="font-size:28px;font-weight:600;letter-spacing:-0.02em;color:var(--gray-900);">
                    {% if materiaal %}{{ materiaal }}bedrijven{% if land %} in {{ land }}{% endif %}{% elif land %}Bedrijven in {{ land }}{% else %}Alle bedrijven{% endif %}
                </div>
            </div>
            <div style="display:flex;gap:22px;">
                <div><div style="font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Resultaten</div><div style="font-size:28px;font-weight:700;color:var(--gray-800);font-family:var(--font-mono);">{{ totaal_gevonden }}</div></div>
                <div><div style="font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Landen</div><div style="font-size:28px;font-weight:700;color:var(--gray-800);font-family:var(--font-mono);">{{ landen_in_resultaat }}</div></div>
                {% if volume_totaal_resultaat %}<div><div style="font-size:11px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Volume</div><div style="font-size:28px;font-weight:700;color:var(--gray-800);font-family:var(--font-mono);">{{ volume_totaal_resultaat }}</div></div>{% endif %}
            </div>
        </div>

        <div style="display:flex;flex-wrap:wrap;align-items:center;gap:7px;margin-bottom:14px;">
            {% for af in actieve_filters_lijst %}
            <a href="{{ af.url }}" style="display:inline-flex;align-items:center;gap:5px;background:var(--brand-600);color:#fff;border-radius:14px;padding:4px 11px;font-size:12px;font-weight:600;text-decoration:none;">
                {{ af.label }}<span style="font-weight:800;opacity:0.8;">✕</span>
            </a>
            {% endfor %}
            <button type="button" onclick="toggleFiltersPaneel()" style="font-size:12px;font-weight:600;color:var(--gray-500);background:#fff;border:1px solid var(--gray-200);border-radius:14px;padding:4px 11px;cursor:pointer;font-family:inherit;">+ filter</button>
            {% if actieve_filters_lijst %}<a href="/" style="font-size:12px;color:var(--gray-300);text-decoration:none;margin-left:4px;">Wis alles</a>{% endif %}
        </div>
        <!-- MAP + TABEL: één doorlopend blok -->
        <div class="kaart-tabel-blok">
            <div class="map-panel" style="position:relative;">
                <div id="kaart"></div>
                {% if legenda_tellingen.recyclingcentrum or legenda_tellingen.inzamelaar or legenda_tellingen.papierfabriek %}
                <div style="position:absolute;left:12px;bottom:12px;z-index:400;background:#fff;border:1px solid var(--gray-200);border-radius:8px;padding:8px 14px;display:flex;gap:16px;align-items:center;box-shadow:var(--shadow-sm);font-size:12px;">
                    {% if legenda_tellingen.recyclingcentrum %}<span style="display:flex;align-items:center;gap:6px;"><span style="width:9px;height:9px;border-radius:50%;background:#0d5c62;display:inline-block;"></span>Recyclingcentra <b>{{ legenda_tellingen.recyclingcentrum }}</b></span>{% endif %}
                    {% if legenda_tellingen.inzamelaar %}<span style="display:flex;align-items:center;gap:6px;"><span style="width:9px;height:9px;border-radius:50%;background:#3f9295;display:inline-block;"></span>Inzamelaars <b>{{ legenda_tellingen.inzamelaar }}</b></span>{% endif %}
                    {% if legenda_tellingen.papierfabriek %}<span style="display:flex;align-items:center;gap:6px;"><span style="width:9px;height:9px;border-radius:50%;background:#d97706;display:inline-block;"></span>Papierfabrieken <b>{{ legenda_tellingen.papierfabriek }}</b></span>{% endif %}
                </div>
                {% endif %}
            </div>

            <div class="results-list" id="resultatenLijst">
                <div class="data-thead">
                    <span style="width:26px;"></span>
                    <span style="flex:1.5;" data-sort="naam">Bedrijf</span>
                    <span style="flex:1;" data-sort="brontype">Bedrijfstype</span>
                <span style="flex:1.2;" data-sort="materialen">Materialen</span>
                <span style="flex:1.2;" data-sort="kwaliteiten">Kwaliteiten</span>
                <span style="flex:1;" data-sort="klanttype">Klanttype</span>
                <span style="width:90px;text-align:right;" data-sort="volume">Volume t/j</span>
                <span style="width:110px;" data-sort="accountmanager">Accountmgr.</span>
                <span style="width:90px;text-align:right;" data-sort="laatst_contact">Contact</span>
                <span style="width:28px;"></span>
            </div>
            {% for bedrijf in bedrijven %}
            <a class="data-row"
                href="#"
                data-naam="{{ bedrijf.naam|e }}" data-brontype="{{ bedrijf.brontype|default('',true)|e }}"
                data-materialen="{{ bedrijf.materialen|default('',true)|e }}" data-kwaliteiten="{{ bedrijf.kwaliteiten|default('',true)|e }}"
                data-klanttype="{{ bedrijf.klanttype|default('',true)|e }}" data-volume="{{ bedrijf.volume|default('',true)|e }}"
                data-accountmanager="{{ bedrijf.accountmanager|default('',true)|e }}"
                data-laatst_contact="{{ bedrijf.laatst_contact|default('',true)|e }}"
                data-lat="{{ bedrijf.lat or '' }}" data-lon="{{ bedrijf.lon or '' }}"
                onclick="event.preventDefault(); openDrawer('{{ bedrijf.naam|replace("'","&#39;") }}', '{{ bedrijf.regio }}', '{{ bedrijf.land }}', '{{ bedrijf.url }}', '{{ bedrijf.klanttype }}', '{{ bedrijf.materialen }}', '{{ bedrijf.volume }}', {{ bedrijf.lat }}, {{ bedrijf.lon }}, '{{ bedrijf.adres|default("", true)|replace("'","&#39;") }}', '{{ bedrijf.telefoon|default("", true) }}', '{{ bedrijf.certificeringen|default("", true)|replace("'","&#39;") }}', '{{ bedrijf.contactpersoon|default("", true)|replace("'","&#39;") }}', '{{ bedrijf.kwaliteiten|default("", true)|replace("'","&#39;") }}', '{{ bedrijf.brontype|default("", true)|replace("'","&#39;") }}')">
                <span style="width:26px;"><span class="star-btn {% if bedrijf.naam in opgeslagen_namen %}opgeslagen{% endif %}" onclick="event.stopPropagation(); toggleOpslaan(event, '{{ bedrijf.naam|replace("'","\\'") }}', this)">{% if bedrijf.naam in opgeslagen_namen %}★{% else %}☆{% endif %}</span></span>
                <span style="flex:1.5;font-weight:600;color:var(--gray-800);">{{ bedrijf.naam }}{% if bedrijf.adres or bedrijf.telefoon %} <span class="verificatie-badge" style="font-size:0.6rem;">✓</span>{% endif %}<br><span style="font-weight:400;font-size:11px;color:var(--gray-400);">{{ bedrijf.regio }}, {{ bedrijf.land }}</span></span>
                <span style="flex:1;" class="zacht">{{ bedrijf.brontype|default('—',true) }}</span>
                <span style="flex:1.2;" class="zacht">{{ bedrijf.materialen|default('—',true) }}</span>
                <span style="flex:1.2;" class="zacht">{{ bedrijf.kwaliteiten|default('—',true) }}</span>
                <span style="flex:1;" class="zacht">{{ bedrijf.klanttype|default('—',true) }}</span>
                <span style="width:90px;text-align:right;" class="num">{{ bedrijf.volume|default('—',true) }}</span>
                <span style="width:110px;" class="zacht">{{ bedrijf.accountmanager|default('—',true) }}</span>
                <span style="width:90px;text-align:right;font-size:11px;" class="zacht">{{ bedrijf.laatst_contact|default('—',true) }}</span>
                <span style="width:28px;text-align:center;color:var(--gray-300);">›</span>
            </a>
            {% endfor %}
        </div>
        <div class="results-header">
            <div class="results-count">
                <strong id="inBeeldTeller">{{ bedrijven|length }}</strong> bedrijven in kaartbeeld · <strong>{{ bedrijven|length }}</strong> van <strong>{{ totaal_gevonden }}</strong>
                {% if totaal_paginas > 1 %}<span style="color:var(--gray-300);"> · pagina {{ pagina }}/{{ totaal_paginas }}</span>{% endif %}
                <span style="color:var(--gray-300);font-size:11px;"> · zoom of sleep de kaart om te filteren</span>
            </div>
            <a href="/export-csv?{{ export_query }}" style="font-size:12px;font-weight:600;color:var(--brand-600);text-decoration:none;">⬇ Export to CSV</a>
        </div>
        </div>
        {% if totaal_paginas > 1 %}
        <div style="display:flex;gap:6px;justify-content:center;align-items:center;margin-top:14px;flex-wrap:wrap;">
            {% if pagina > 1 %}<a href="{{ maak_pagina_url(pagina - 1) }}" style="padding:6px 10px;border:1px solid var(--gray-200);border-radius:6px;text-decoration:none;color:var(--gray-600);font-size:13px;">←</a>{% endif %}
            {% if pagina > 2 %}<a href="{{ maak_pagina_url(1) }}" style="padding:6px 10px;border:1px solid var(--gray-200);border-radius:6px;text-decoration:none;color:var(--gray-600);font-size:13px;">1</a>{% endif %}
            {% if pagina > 3 %}<span style="color:var(--gray-300);">…</span>{% endif %}
            {% if pagina > 1 %}<a href="{{ maak_pagina_url(pagina - 1) }}" style="padding:6px 10px;border:1px solid var(--gray-200);border-radius:6px;text-decoration:none;color:var(--gray-600);font-size:13px;">{{ pagina - 1 }}</a>{% endif %}
            <span style="padding:6px 10px;border-radius:6px;background:var(--brand-600);color:#fff;font-weight:700;font-size:13px;">{{ pagina }}</span>
            {% if pagina < totaal_paginas %}<a href="{{ maak_pagina_url(pagina + 1) }}" style="padding:6px 10px;border:1px solid var(--gray-200);border-radius:6px;text-decoration:none;color:var(--gray-600);font-size:13px;">{{ pagina + 1 }}</a>{% endif %}
            {% if pagina < totaal_paginas - 2 %}<span style="color:var(--gray-300);">…</span>{% endif %}
            {% if pagina < totaal_paginas - 1 %}<a href="{{ maak_pagina_url(totaal_paginas) }}" style="padding:6px 10px;border:1px solid var(--gray-200);border-radius:6px;text-decoration:none;color:var(--gray-600);font-size:13px;">{{ totaal_paginas }}</a>{% endif %}
            {% if pagina < totaal_paginas %}<a href="{{ maak_pagina_url(pagina + 1) }}" style="padding:6px 10px;border:1px solid var(--gray-200);border-radius:6px;text-decoration:none;color:var(--gray-600);font-size:13px;">→</a>{% endif %}
        </div>
        {% endif %}
    </div>

    {% else %}
    <div class="welcome-state">
        <div class="welcome-icon">🔍</div>
        {% if er_is_gefilterd %}
        <div class="welcome-title">Geen bedrijven gevonden voor deze filters</div>
        <div class="welcome-sub">Probeer een andere combinatie, of klik op "Wis filters" om opnieuw te beginnen</div>
        {% else %}
        <div class="welcome-title">Search for recycling companies</div>
        <div class="welcome-sub">Use the search bar or filters above to find companies across {{ landen|length }} countries</div>
        {% endif %}
    </div>
    {% endif %}

</div>

<div id="fabriekAnalysePaneel" style="display:none;position:fixed;top:60px;right:20px;width:380px;max-height:600px;overflow-y:auto;background:white;border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,0.15);z-index:9998;padding:14px;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
        <div style="font-weight:700;" id="fabriekAnalyseTitel">Leveranciers</div>
        <button onclick="document.getElementById('fabriekAnalysePaneel').style.display='none'" style="background:none;border:none;cursor:pointer;font-size:16px;">✕</button>
    </div>
    <div style="margin-bottom:10px;padding-bottom:10px;border-bottom:1px solid #f1f5f9;">
        <label style="font-size:11px;color:#94a3b8;display:block;margin-bottom:4px;">Kwaliteiten die deze fabriek aanneemt</label>
        <input type="text" id="fabriekKwaliteitenInput" placeholder="bv. OCC, Mixed Paper..." onblur="wijzigFabriekKwaliteiten()" style="width:100%;padding:6px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;box-sizing:border-box;font-family:inherit;">
    </div>
    <div id="fabriekAnalyseLijst"></div>
</div>
<div id="meldingenPaneel" style="display:none;position:fixed;top:60px;right:20px;width:340px;max-height:400px;overflow-y:auto;background:white;border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,0.15);z-index:9998;padding:12px;">
    <div style="font-weight:700;margin-bottom:8px;">Meldingen</div>
    <div id="meldingenLijst"></div>
    <a href="/meldingen-overzicht" style="display:block;text-align:center;margin-top:10px;font-size:12px;color:var(--brand-600);text-decoration:none;font-weight:600;">Alle meldingen bekijken →</a>
</div>
<!-- DETAIL DRAWER -->
<div class="overlay" id="overlay" onclick="closeDrawer()"></div>
<div class="drawer" id="drawer">
    <div class="drawer-header">
        <button class="drawer-close" onclick="closeDrawer()">✕</button>
        <div class="drawer-company-name" id="drawerName"></div>
        <div class="drawer-company-loc" id="drawerLoc"></div>
    </div>
    <div class="drawer-body" id="drawerBody"></div>
</div>

<script>
var regioPer = {{ regio_per_land|tojson }};

function toggleFiltersPaneel() {
    var paneel = document.getElementById("filtersPaneel");
    var isOpen = paneel.style.display === "block";
    if (isOpen) {
        paneel.style.display = "none";
        return;
    }
    var knop = event.currentTarget;
    var rect = knop.getBoundingClientRect();
    paneel.style.position = "fixed";
    paneel.style.top = (rect.bottom + 8) + "px";
    paneel.style.left = rect.left + "px";
    paneel.style.zIndex = "9999";
    paneel.style.display = "block";
}
document.addEventListener("click", function(e) {
    var paneel = document.getElementById("filtersPaneel");
    if (!paneel || paneel.style.display === "none") return;
    if (paneel.contains(e.target)) return;
    if (e.target.closest && e.target.closest("[onclick='toggleFiltersPaneel()']")) return;
    paneel.style.display = "none";
});

function updateRegio() {
    var land = document.getElementById("landSelect").value;
    var sel = document.getElementById("regioSelect");
    sel.innerHTML = "<option value=''>All Regions</option>";
    if (land && regioPer[land]) {
        regioPer[land].forEach(function(r) {
            var o = document.createElement("option");
            o.value = r; o.text = r;
            sel.appendChild(o);
        });
    }
}

{% if bedrijven %}
var kaart = L.map("kaart").setView([{{ bedrijven[0].lat }}, {{ bedrijven[0].lon }}], 5);
var straatKaart = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {attribution:"© OpenStreetMap"});
var satellietKaart = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {attribution:"© Esri"});
straatKaart.addTo(kaart);
L.control.layers({"Kaart": straatKaart, "Satelliet": satellietKaart}).addTo(kaart);
var clusterGroep = L.markerClusterGroup();
var kaartCategorieKleuren = {"recyclingcentrum": "#0d5c62", "inzamelaar": "#3f9295", "papierfabriek": "#d97706", "overig": "#94a3b8"};
{% for b in bedrijven %}
L.marker([{{ b.lat }}, {{ b.lon }}], {icon: L.divIcon({
    html: '<div style="width:16px;height:16px;border-radius:50%;background:' + kaartCategorieKleuren["{{ b.kaart_categorie }}"] + ';border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,0.35);"></div>',
    className: '', iconSize: [16,16], iconAnchor: [8,8]
})})
    .bindPopup("<b>{{ b.naam|replace('"','') }}</b><br><small>{{ b.regio }}, {{ b.land }}</small>")
    .on("click", function(){ openDrawer("{{ b.naam|replace("'","&#39;") }}","{{ b.regio }}","{{ b.land }}","{{ b.url }}","{{ b.klanttype }}","{{ b.materialen }}","{{ b.volume }}",{{ b.lat }},{{ b.lon }},"{{ b.adres|default('', true)|replace("'","&#39;") }}","{{ b.telefoon|default('', true) }}","{{ b.certificeringen|default('', true)|replace("'","&#39;") }}","{{ b.contactpersoon|default('', true)|replace("'","&#39;") }}","{{ b.kwaliteiten|default('', true)|replace("'","&#39;") }}","{{ b.brontype|default('', true)|replace("'","&#39;") }}"); })
    .addTo(clusterGroep);
{% endfor %}
kaart.addLayer(clusterGroep);
var fabriekIcon = L.divIcon({
    html: '<div style="background:#0d5c62;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:16px;box-shadow:0 2px 8px rgba(0,0,0,0.3);border:2px solid white;">🏭</div>',
    className: '',
    iconSize: [32, 32],
    iconAnchor: [16, 16]
});
{% for f in papierfabrieken %}{% if f.lat and f.lon %}
L.marker([{{ f.lat }}, {{ f.lon }}], {icon: fabriekIcon})
    .addTo(kaart)
.bindPopup('<b>🏭 {{ f.naam }}</b><br><small>{{ f.stad }}, {{ f.land }}</small><br><small>{{ f.materialen }}</small><br><a href="/bedrijf/{{ f.naam|urlencode }}" style="display:inline-block;margin-top:6px;padding:4px 10px;background:#0d5c62;color:white;border-radius:6px;font-size:12px;text-decoration:none;">Bekijk profiel →</a> <button data-fabriek="{{ f.naam }}" onclick="toonFabriekAnalyse(this.dataset.fabriek)" style="margin-top:6px;padding:4px 10px;background:#fff;color:#0d5c62;border:1px solid #0d5c62;border-radius:6px;cursor:pointer;font-size:12px;">Toon leveranciers</button>');
{% endif %}{% endfor %}

// Kaart↔tabel-koppeling: zoomen/slepen van de kaart filtert live welke rijen zichtbaar zijn
var kaartTabelRijen = Array.prototype.slice.call(document.querySelectorAll("#resultatenLijst .data-row"));
function syncKaartMetTabel() {
    var bounds = kaart.getBounds();
    var teller = 0;
    kaartTabelRijen.forEach(function (rij) {
        var lat = parseFloat(rij.dataset.lat), lon = parseFloat(rij.dataset.lon);
        if (isNaN(lat) || isNaN(lon)) { rij.style.display = "none"; return; }
        var zichtbaar = bounds.contains([lat, lon]);
        rij.style.display = zichtbaar ? "" : "none";
        if (zichtbaar) teller++;
    });
    var tellerEl = document.getElementById("inBeeldTeller");
    if (tellerEl) tellerEl.textContent = teller;
}
kaart.on("moveend zoomend", syncKaartMetTabel);
kaart.whenReady(function () { setTimeout(syncKaartMetTabel, 300); });
{% endif %}

(function () {
    var lijst = document.getElementById("resultatenLijst");
    if (!lijst) return;
    var koppen = lijst.querySelectorAll(".data-thead [data-sort]");
    var richting = "desc", sleutel = null;
    var getal = function (v) { return parseFloat((v || "").replace(/[^\d,.-]/g, "").replace(/\./g, "").replace(",", ".")) || 0; };

    koppen.forEach(function (kop) {
        kop.addEventListener("click", function () {
            var k = kop.dataset.sort;
            richting = (sleutel === k && richting === "desc") ? "asc" : "desc";
            sleutel = k;
            koppen.forEach(function (x) { x.textContent = x.textContent.replace(/ [\u2191\u2193]$/, ""); });
            kop.textContent += richting === "desc" ? " \u2193" : " \u2191";

            var rijen = Array.prototype.slice.call(lijst.querySelectorAll(".data-row")).filter(function (r) { return r.dataset && r.dataset[k] !== undefined; });
            rijen.sort(function (a, b) {
                var va = a.dataset[k] || "", vb = b.dataset[k] || "";
                var numeriek = /^[\d.,\s-]+$/.test(va) && /^[\d.,\s-]+$/.test(vb) && va !== "";
                var r = numeriek ? getal(va) - getal(vb) : va.localeCompare(vb, "nl");
                return richting === "asc" ? r : -r;
            });
            rijen.forEach(function (r) { lijst.appendChild(r); });
        });
    });
})();

function kaartHTML(id, titel, icoon, inhoud, openStaan) {
    return `
        <div class="collapsible-card">
            <div class="collapsible-header" onclick="toggleKaart('${id}')">
                <span class="collapsible-header-left"><span>${icoon}</span> ${titel}</span>
                <span class="collapsible-arrow ${openStaan ? '' : 'dicht'}" id="pijl-${id}">▾</span>
            </div>
            <div class="collapsible-body ${openStaan ? '' : 'dicht'}" id="${id}">
                ${inhoud}
            </div>
        </div>`;
}

function toggleKaart(id) {
    document.getElementById(id).classList.toggle("dicht");
    document.getElementById("pijl-" + id).classList.toggle("dicht");
}

function wisselDrawerTab(naam) {
    ["info", "logistiek", "commercieel"].forEach(function(t) {
        var paneel = document.getElementById("tabpaneel-" + t);
        var knop = document.getElementById("tabknop-" + t);
        if (paneel) paneel.classList.toggle("actief", t === naam);
        if (knop) knop.classList.toggle("actief", t === naam);
    });
}

function bouwDrawerBody(klanttype, materialen, volume, contactHTML, websiteBtnHTML) {
    const geverifieerd = (window.currentDrawerData && (window.currentDrawerData.adres || window.currentDrawerData.telefoon))
        ? `<div class="drawer-row"><span class="drawer-row-label">Status</span><span class="drawer-row-value" style="color:var(--green-600);font-weight:700;">✓ Geverifieerd</span></div>` : "";

    const algemeen = `
        ${geverifieerd}
        <div class="drawer-row"><span class="drawer-row-label">Status</span><span class="drawer-row-value">
    <select id="statusSelect" onchange="wijzigStatus()" style="padding:4px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;">
        <option value="">Geen status</option>
        <option value="klant">🟢 Klant</option>
        <option value="potentie">🟡 Potentie</option>
        <option value="in_proces">🔵 In Proces</option>
        <option value="geen_interesse">⚪ Geen Interesse</option>
    </select>
</span></div>
        <div class="drawer-row"><span class="drawer-row-label">Accountmanager</span><span class="drawer-row-value" id="accountmanagerWaarde">—</span></div>
        <div class="drawer-row"><span class="drawer-row-label">Customer Type</span><span class="drawer-row-value">${klanttype || "—"}</span></div>
        ${window.currentDrawerData && window.currentDrawerData.brontype ? `<div class="drawer-row"><span class="drawer-row-label">Type</span><span class="drawer-row-value">${window.currentDrawerData.brontype}</span></div>` : ""}
        <div class="drawer-row"><span class="drawer-row-label">Materials</span><span class="drawer-row-value">${materialen || "—"}</span></div>
        ${window.currentDrawerData && window.currentDrawerData.kwaliteiten ? `<div class="drawer-row"><span class="drawer-row-label">Kwaliteiten</span><span class="drawer-row-value">${window.currentDrawerData.kwaliteiten}</span></div>` : ""}
        <div class="drawer-row"><span class="drawer-row-label">Annual Volume</span><span class="drawer-row-value">${volume ? volume + " t/y" : "—"}</span></div>
        ${window.currentDrawerData && window.currentDrawerData.contactpersoon ? `<div class="drawer-row"><span class="drawer-row-label">Contactpersoon</span><span class="drawer-row-value">${window.currentDrawerData.contactpersoon}</span></div>` : ""}
        ${window.currentDrawerData && window.currentDrawerData.certificeringen ? `<div class="drawer-row"><span class="drawer-row-label">Certificeringen</span><span class="drawer-row-value">🏅 ${window.currentDrawerData.certificeringen}</span></div>` : ""}`;

    const logistiek = `<div id="transportInfo"><div style="color:var(--gray-400);font-size:var(--text-sm);">Laden...</div></div>`;

    const commercieel = `
        <div style="font-size:12px;color:#94a3b8;margin-bottom:6px;">Stuur melding naar:</div>
        <select id="meldingOntvanger" style="width:100%;padding:6px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;margin-bottom:6px;">
            <option value="">Kies persoon/team...</option>
        </select>
        <div style="display:flex;gap:8px;">
            <input type="text" id="meldingTekst" placeholder="Melding..." style="flex:1;padding:6px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;">
            <button onclick="stuurMelding()" style="padding:6px 14px;background:#ef4444;color:white;border:none;border-radius:6px;cursor:pointer;font-size:13px;">Stuur</button>
        </div>`;

    const aiAnalyse = `
        <button id="equipmentBtn" onclick="analyseUitrusting()" style="padding:8px 16px;background:var(--brand-600);color:white;border:none;border-radius:6px;cursor:pointer;">AI Analyseren</button>
        <div id="equipmentResults" style="margin-top:12px;"></div>`;

    const notities = `
        <div id="notitiesLijst" style="margin-bottom:14px;"></div>
        <textarea id="notitieInput" placeholder="Schrijf een notitie..." style="width:100%;min-height:56px;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-family:inherit;font-size:13px;color:var(--gray-700);resize:vertical;box-sizing:border-box;"></textarea>
        <div style="display:flex;align-items:center;gap:16px;margin-top:10px;">
            <label style="font-size:12.5px;color:var(--gray-600);display:flex;align-items:center;gap:5px;cursor:pointer;"><input type="radio" name="notitieType" value="team" checked> Team</label>
            <label style="font-size:12.5px;color:var(--gray-600);display:flex;align-items:center;gap:5px;cursor:pointer;"><input type="radio" name="notitieType" value="prive"> Privé</label>
            <button onclick="voegNotitieToe()" style="margin-left:auto;padding:6px 16px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12.5px;font-weight:600;">Toevoegen</button>
        </div>`;

    const contactDetails = `
        <div id="fotosLijst" style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;"></div>
        <input type="file" id="fotoInput" accept="image/*" style="display:none;" onchange="uploadFoto()">
        <button onclick="document.getElementById('fotoInput').click()" style="padding:6px 14px;background:var(--brand-600);color:white;border:none;border-radius:6px;cursor:pointer;font-size:13px;margin-bottom:12px;">📷 Foto toevoegen</button>
        ${contactHTML}
        ${websiteBtnHTML}`;

    const tabbalk = `
        <div class="drawer-tabs">
            <button class="drawer-tab actief" id="tabknop-info" onclick="wisselDrawerTab('info')">Info</button>
            <button class="drawer-tab" id="tabknop-logistiek" onclick="wisselDrawerTab('logistiek')">Logistiek</button>
            <button class="drawer-tab" id="tabknop-commercieel" onclick="wisselDrawerTab('commercieel')">Commercieel</button>
        </div>`;

    const paneelInfo = `<div class="drawer-tab-paneel actief" id="tabpaneel-info">` +
        kaartHTML("kaartAlgemeen", "Algemene informatie", "ℹ️", algemeen, true) +
        kaartHTML("kaartNotities", "Notities", "📝", notities, false) +
        `</div>`;

    const paneelLogistiek = `<div class="drawer-tab-paneel" id="tabpaneel-logistiek">` +
        kaartHTML("kaartLogistiek", "Logistiek", "🚚", logistiek, true) +
        `</div>`;

    const paneelCommercieel = `<div class="drawer-tab-paneel" id="tabpaneel-commercieel">` +
        kaartHTML("kaartCommercieel", "Commercieel", "💬", commercieel, true) +
        kaartHTML("kaartAi", "AI-uitrusting analyse", "✨", aiAnalyse, false) +
        kaartHTML("kaartContact", "Contact & details", "📇", contactDetails, false) +
        `</div>`;

    return tabbalk + paneelInfo + paneelLogistiek + paneelCommercieel;
}

function openDrawer(naam, regio, land, url, klanttype, materialen, volume, lat, lon, adres, telefoon, certificeringen, contactpersoon, kwaliteiten, brontype) {
    window.currentDrawerData = {naam: naam, land: land, regio: regio, klanttype: klanttype, materialen: materialen, volume: volume, lat: lat, lon: lon, adres: adres || "", telefoon: telefoon || "", certificeringen: certificeringen || "", contactpersoon: contactpersoon || "", kwaliteiten: kwaliteiten || "", brontype: brontype || ""};
    {% if bedrijven %}kaart.flyTo([lat,lon], 12);{% endif %}
    document.getElementById("drawerName").textContent = naam;
    document.getElementById("drawerLoc").innerHTML = "📍 " + regio + ", " + land + ' · <a href="/bedrijf/' + encodeURIComponent(naam) + '" style="color:var(--brand-600);font-weight:600;text-decoration:none;">Volledig profiel →</a>';
    document.getElementById("drawerBody").innerHTML = bouwDrawerBody(klanttype, materialen, volume, `<div style="color:var(--gray-400);font-size:var(--text-sm);">⏳ Loading details...</div>`, "");
    document.getElementById("overlay").style.display = "block";
    document.getElementById("drawer").classList.add("open");
    laadNotities();
    laadTransport();
    laadStatus();
    laadAccountmanager();
    vulMeldingDropdowns();
    laadFotos();

    fetch("/details?url=" + encodeURIComponent(url))
        .then(r => r.json())
        .then(data => {
            window.currentDrawerData.stad = data.stad || "";
            if (data.lat_precies && data.lon_precies) {
                window.currentDrawerData.lat = data.lat_precies;
                window.currentDrawerData.lon = data.lon_precies;
            }
            var contactHTML = "";
            if (data.website) contactHTML += `<div class="drawer-row"><span class="drawer-row-label">Website</span><span class="drawer-row-value"><a href="${data.website}" target="_blank" style="color:var(--brand-600);font-weight:600;">${data.website.replace("https://","").replace("http://","").split("/")[0]}</a></span></div>`;
            var telefoon = data.telefoon || window.currentDrawerData.telefoon;
            var adres = data.adres || window.currentDrawerData.adres;
            if (telefoon) contactHTML += `<div class="drawer-row"><span class="drawer-row-label">Phone</span><span class="drawer-row-value">${telefoon}</span></div>`;
            if (adres) contactHTML += `<div class="drawer-row"><span class="drawer-row-label">Address</span><span class="drawer-row-value">${adres}${data.stad?", "+data.stad:""}</span></div>`;
            if (data.medewerkers) contactHTML += `<div class="drawer-row"><span class="drawer-row-label">Employees</span><span class="drawer-row-value">${data.medewerkers}</span></div>`;
            if (!contactHTML) contactHTML = `<div style="color:var(--gray-400);font-size:var(--text-sm);">No additional details available</div>`;
            if (data.lat_precies && data.lon_precies) {
                kaart.flyTo([data.lat_precies, data.lon_precies], 17);
                L.marker([data.lat_precies, data.lon_precies]).addTo(kaart)
                    .bindPopup("<b>" + naam + "</b>").openPopup();
            }
            var websiteBtnHTML = data.website ? `<a href="${data.website}" target="_blank" class="btn-website">🌐 Visit Website</a>` : "";

            document.getElementById("drawerBody").innerHTML = bouwDrawerBody(klanttype, materialen, volume, contactHTML, websiteBtnHTML);
            laadNotities();
            laadTransport();
            laadStatus();
            laadAccountmanager();
            vulMeldingDropdowns();
            laadFotos();
        });
}

async function analyseUitrusting() {
    const btn = document.getElementById("equipmentBtn");
    const resultsDiv = document.getElementById("equipmentResults");
    btn.disabled = true;
    btn.innerText = "Bezig met analyseren...";
    resultsDiv.innerHTML = "";

    try {
        const res = await fetch('/api/company-analysis', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(window.currentDrawerData || {})
        });
        const data = await res.json();

        const labels = {
            baler: "Baler",
            mrf: "MRF",
            transfer_station: "Transfer Station",
            loading_ramp: "Loading Ramp",
            weighbridge: "Weighbridge",
            walking_floor: "Walking Floor",
            containers: "Containers",
            shredder: "Shredder",
            sorteerinstallatie: "Sorteerinstallatie"
        };

        let html = "";
        for (const key in labels) {
            const pct = data[key] || 0;
            html += `
                <div style="margin-bottom:8px;">
                    <div style="display:flex;justify-content:space-between;font-size:13px;">
                        <span>${labels[key]}</span><span>${pct}%</span>
                    </div>
                    <div style="background:#e2e8f0;border-radius:4px;height:6px;overflow:hidden;">
                        <div style="background:#2563eb;height:100%;width:${pct}%;"></div>
                    </div>
                </div>`;
        }
        resultsDiv.innerHTML = html;

    } catch (err) {
        resultsDiv.innerHTML = "<p>Er ging iets mis bij de analyse.</p>";
        console.error(err);
    }

    btn.disabled = false;
    btn.innerText = "AI Analyseren";
}
async function laadNotities() {
    const bedrijf = window.currentDrawerData.naam;
    const lijstDiv = document.getElementById("notitiesLijst");
    if (!lijstDiv) return;
    lijstDiv.innerHTML = "<p style='font-size:13px;color:#94a3b8;'>Laden...</p>";
    try {
        const res = await fetch("/api/notities?bedrijf=" + encodeURIComponent(bedrijf));
        const notities = await res.json();
        if (notities.length === 0) {
            lijstDiv.innerHTML = "<p style='font-size:13px;color:#94a3b8;'>Nog geen notities.</p>";
            return;
        }
        let html = "";
        notities.forEach(n => {
            const badgeAchtergrond = n.type === "team" ? "var(--brand-50)" : "var(--gray-100)";
            const badgeKleur = n.type === "team" ? "var(--brand-600)" : "var(--gray-500)";
            const badge = n.type === "team" ? "Team" : "Privé";
            html += `
                <div style="padding:10px 0;border-bottom:1px solid var(--gray-100);font-size:13px;">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
                        <div style="color:var(--gray-700);">${n.tekst}</div>
                        <button onclick="verwijderNotitieDrawer('${n.id}')" title="Verwijderen" style="background:none;border:none;color:var(--gray-300);cursor:pointer;font-size:12px;flex-shrink:0;">✕</button>
                    </div>
                    <div style="margin-top:5px;display:flex;align-items:center;gap:7px;">
                        <span style="font-size:10px;font-weight:700;padding:1px 8px;border-radius:8px;background:${badgeAchtergrond};color:${badgeKleur};">${badge}</span>
                        <span style="color:var(--gray-400);font-size:11px;">${n.timestamp}</span>
                    </div>
                </div>`;
        });
        lijstDiv.innerHTML = html;
    } catch (err) {
        lijstDiv.innerHTML = "<p style='font-size:13px;color:#ef4444;'>Kon notities niet laden.</p>";
    }
}

async function verwijderNotitieDrawer(id) {
    if (!confirm("Deze notitie verwijderen?")) return;
    const bedrijf = window.currentDrawerData.naam;
    const res = await fetch("/api/notities", {method:"DELETE", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: bedrijf, id: id})});
    const data = await res.json();
    if (data.error) { alert(data.error); } else { laadNotities(); }
}

async function voegNotitieToe() {
    const input = document.getElementById("notitieInput");
    const tekst = input.value.trim();
    if (!tekst) return;
    const type_ = document.querySelector('input[name="notitieType"]:checked').value;
    const bedrijf = window.currentDrawerData.naam;

    try {
        await fetch("/api/notities", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({bedrijf: bedrijf, tekst: tekst, type: type_})
        });
        input.value = "";
        laadNotities();
    } catch (err) {
        alert("Er ging iets mis bij het opslaan.");
    }
}
async function laadStatus() {
    const bedrijf = window.currentDrawerData.naam;
    const select = document.getElementById("statusSelect");
    if (!select) return;
    try {
        const res = await fetch("/api/status?bedrijf=" + encodeURIComponent(bedrijf));
        const data = await res.json();
        select.value = data.status || "";
    } catch (err) {
        console.error(err);
    }
}

async function laadAccountmanager() {
    const bedrijf = window.currentDrawerData.naam;
    const el = document.getElementById("accountmanagerWaarde");
    if (!el) return;
    try {
        const res = await fetch("/api/accountmanager?bedrijf=" + encodeURIComponent(bedrijf));
        const data = await res.json();
        el.textContent = data.accountmanager ? ("👤 " + data.accountmanager) : "Niet toegewezen";
    } catch (err) {
        console.error(err);
    }
}

async function wijzigStatus() {
    const bedrijf = window.currentDrawerData.naam;
    const select = document.getElementById("statusSelect");
    const nieuweStatus = select.value;
    try {
        await fetch("/api/status", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({bedrijf: bedrijf, status: nieuweStatus})
        });
    } catch (err) {
        alert("Er ging iets mis bij het opslaan van de status.");
    }
}
async function laadMeldingenBadge() {
    try {
        const res = await fetch("/api/meldingen");
        const meldingen = await res.json();
        const ongelezen = meldingen.filter(m => !m.gelezen).length;
        const badge = document.getElementById("meldingBadge");
        if (ongelezen > 0) {
            badge.style.display = "flex";
            badge.innerText = ongelezen;
        } else {
            badge.style.display = "none";
        }
    } catch (err) { console.error(err); }
}

async function toonMeldingen() {
    const paneel = document.getElementById("meldingenPaneel");
    const lijstDiv = document.getElementById("meldingenLijst");
    const isOpen = paneel.style.display === "block";
    paneel.style.display = isOpen ? "none" : "block";
    if (isOpen) return;

    var knop = event.currentTarget;
    var rect = knop.getBoundingClientRect();
    paneel.style.top = (rect.bottom + 8) + "px";
    paneel.style.right = (window.innerWidth - rect.right) + "px";
    paneel.style.left = "auto";

    try {
        const res = await fetch("/api/meldingen");
        const meldingen = await res.json();
        if (meldingen.length === 0) {
            lijstDiv.innerHTML = "<p style='font-size:13px;color:#94a3b8;'>Geen meldingen.</p>";
            return;
        }
        let html = "";
        meldingen.slice().reverse().forEach(m => {
            html += `
                <div style="background:${m.gelezen ? '#f8fafc' : '#eff6ff'};border-radius:6px;padding:8px 10px;margin-bottom:6px;font-size:13px;cursor:pointer;" onclick="markeerGelezen('${m.id}')">
                    <div style="color:#334155;">${m.tekst}</div>
                    <div style="color:#94a3b8;font-size:11px;margin-top:4px;">van ${m.van} · ${m.bedrijf || ''} · ${m.timestamp}</div>
                </div>`;
        });
        lijstDiv.innerHTML = html;
    } catch (err) { console.error(err); }
    laadMeldingenBadge();
}

async function markeerGelezen(id) {
    await fetch("/api/meldingen/" + id + "/lezen", {method: "POST"});
    toonMeldingen();
    laadMeldingenBadge();
}

laadMeldingenBadge();
setInterval(laadMeldingenBadge, 30000);
async function vulMeldingDropdowns() {
    try {
        const res = await fetch("/api/gebruikers");
        const gebruikers = await res.json();
        const teams = [...new Set(gebruikers.map(g => g.team).filter(t => t))];
        document.querySelectorAll("#meldingOntvanger").forEach(select => {
            let html = "<option value=''>Kies persoon/team...</option>";
            if (teams.length) {
                html += "<optgroup label='Teams'>";
                teams.forEach(t => html += `<option value='team:${t}'>Team: ${t}</option>`);
                html += "</optgroup>";
            }
            html += "<optgroup label='Personen'>";
            gebruikers.forEach(g => html += `<option value='persoon:${g.gebruikersnaam}'>${g.gebruikersnaam}</option>`);
            html += "</optgroup>";
            select.innerHTML = html;
        });
    } catch (err) { console.error(err); }
}

async function stuurMelding() {
    const selects = document.querySelectorAll("#meldingOntvanger");
    const inputs = document.querySelectorAll("#meldingTekst");
    let select, input;
    selects.forEach((s, i) => { if (s.offsetParent !== null) { select = s; input = inputs[i]; } });
    if (!select || !input) return;

    const keuze = select.value;
    const tekst = input.value.trim();
    if (!keuze || !tekst) return;

    const [type, waarde] = keuze.split(":");
    const bedrijf = window.currentDrawerData.naam;

    try {
        await fetch("/api/meldingen", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                tekst: tekst,
                bedrijf: bedrijf,
                voor_team: type === "team" ? waarde : "",
                voor_gebruiker: type === "persoon" ? waarde : ""
            })
        });
        input.value = "";
        select.value = "";
        alert("Melding verstuurd!");
    } catch (err) {
        alert("Er ging iets mis.");
    }
}
async function toonFabriekAnalyse(fabriekNaam) {
if (window.actieveRelatieLijnen) {
        window.actieveRelatieLijnen.forEach(lijn => kaart.removeLayer(lijn));
    }
    window.actieveRelatieLijnen = [];
    window.huidigeFabriekNaam = fabriekNaam;
    const paneel = document.getElementById("fabriekAnalysePaneel");
    const titel = document.getElementById("fabriekAnalyseTitel");
    const lijstDiv = document.getElementById("fabriekAnalyseLijst");
    paneel.style.display = "block";
    titel.innerText = "🏭 " + fabriekNaam;
    lijstDiv.innerHTML = "<p style='font-size:13px;color:#94a3b8;'>Laden...</p>";

    try {
        const kwalRes = await fetch("/api/fabriek-kwaliteiten?fabriek=" + encodeURIComponent(fabriekNaam));
        const kwalData = await kwalRes.json();
        document.getElementById("fabriekKwaliteitenInput").value = kwalData.kwaliteiten || "";

        const res = await fetch("/api/fabriek-analyse?fabriek=" + encodeURIComponent(fabriekNaam));
        const resultaten = await res.json();
        if (resultaten.error) {
            lijstDiv.innerHTML = "<p style='font-size:13px;color:#ef4444;'>" + resultaten.error + "</p>";
            return;
        }
        if (resultaten.length === 0) {
            lijstDiv.innerHTML = "<p style='font-size:13px;color:#94a3b8;'>Geen passende leveranciers gevonden.</p>";
            return;
        }
        let html = "";
        resultaten.forEach((r, i) => {
            html += `
                <div style="background:#f8fafc;border-radius:8px;padding:10px;margin-bottom:8px;font-size:13px;">
                    <div style="font-weight:600;color:#1e293b;">${i+1}. ${r.naam}</div>
                    <div style="color:#64748b;font-size:12px;margin-top:2px;">${r.regio}, ${r.land}</div>
                    <div style="display:flex;justify-content:space-between;margin-top:6px;">
                        <span style="background:#dbeafe;color:#1d4ed8;padding:2px 8px;border-radius:4px;font-size:11px;">${r.gedeelde_materialen}</span>
                        <span style="font-weight:700;color:#0d5c62;">${r.afstand_km} km</span>
                    </div>
                    ${r.gedeelde_kwaliteiten ? `<div style="margin-top:4px;"><span style="background:#dcfce7;color:#16a34a;padding:2px 8px;border-radius:4px;font-size:11px;">✓ ${r.gedeelde_kwaliteiten}</span></div>` : ""}
                </div>`;
        });
        lijstDiv.innerHTML = html;
        const fabriek = {{ papierfabrieken|tojson }}.find(f => f.naam === fabriekNaam);
        if (fabriek) {
            resultaten.slice(0, 10).forEach(r => {
                const leverancier = {{ bedrijven|tojson if bedrijven else '[]' }}.find(b => b.naam === r.naam);
                if (leverancier) {
                    const kleur = r.afstand_km < 50 ? "#16a34a" : r.afstand_km < 150 ? "#2563eb" : "#94a3b8";
                    const dikte = Math.max(1, 5 - Math.floor(r.afstand_km / 100));
                    const lijn = L.polyline(
                        [[fabriek.lat, fabriek.lon], [leverancier.lat, leverancier.lon]],
                        {color: kleur, weight: dikte, opacity: 0.6, dashArray: r.afstand_km > 150 ? "6,6" : null}
                    ).addTo(kaart);
                    window.actieveRelatieLijnen.push(lijn);
                }
            });
        }
    } catch (err) {
        lijstDiv.innerHTML = "<p style='font-size:13px;color:#ef4444;'>Er ging iets mis.</p>";
        console.error(err);
    }
}

async function wijzigFabriekKwaliteiten() {
    const input = document.getElementById("fabriekKwaliteitenInput");
    if (!window.huidigeFabriekNaam) return;
    await fetch("/api/fabriek-kwaliteiten", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({fabriek: window.huidigeFabriekNaam, waarde: input.value})});
    toonFabriekAnalyse(window.huidigeFabriekNaam);
}

async function laadTransport() {
    const lat = window.currentDrawerData.lat;
    const lon = window.currentDrawerData.lon;
    const div = document.getElementById("transportInfo");
    if (!div) return;
    if (!lat || !lon) { div.innerHTML = ""; return; }

    try {
        const res = await fetch("/api/transport?lat=" + lat + "&lon=" + lon);
        const data = await res.json();
        const forwarders = Object.keys(data);
        if (forwarders.length === 0) {
            div.innerHTML = "";
            return;
        }

        const alleBestemmingen = [...new Set(forwarders.flatMap(fw => Object.keys(data[fw].tarieven)))].sort();

        let html = "<hr class='drawer-divider'><div class='drawer-section-title'>Logistiek</div>";
        html += "<div style='font-size:11px;color:#94a3b8;margin-bottom:6px;'>";
        html += forwarders.map(fw => `${fw}: nabij ${data[fw].stad} (${data[fw].afstand} km)`).join(" · ");
        html += "</div>";
        html += "<div style='overflow-x:auto;'><table style='width:100%;border-collapse:collapse;font-size:12px;'>";
        html += "<tr><th style='text-align:left;padding:6px 8px;color:#94a3b8;font-weight:600;border-bottom:1px solid #e2e8f0;'>Bestemming</th>";
        forwarders.forEach(fw => {
            html += `<th style='text-align:right;padding:6px 8px;color:#94a3b8;font-weight:600;border-bottom:1px solid #e2e8f0;'>${fw}</th>`;
        });
        html += "</tr>";

        alleBestemmingen.forEach(bestemming => {
            const prijzen = forwarders.map(fw => {
                const ruw = data[fw].tarieven[bestemming];
                const getal = ruw ? parseFloat(String(ruw).replace(/[^0-9.]/g, "")) : null;
                return { fw, ruw, getal };
            });
            const geldig = prijzen.filter(p => p.getal !== null && !isNaN(p.getal));
            const laagste = geldig.length ? Math.min(...geldig.map(p => p.getal)) : null;

            html += `<tr><td style='padding:6px 8px;color:#334155;border-bottom:1px solid #f1f5f9;'>${bestemming}</td>`;
            prijzen.forEach(p => {
                const isLaagste = p.getal === laagste && geldig.length > 1;
                const stijl = isLaagste
                    ? "font-weight:700;color:#16a34a;background:#f0fdf4;"
                    : "color:#64748b;";
                html += `<td style='text-align:right;padding:6px 8px;border-bottom:1px solid #f1f5f9;${stijl}'>${p.ruw || "—"}</td>`;
            });
            html += "</tr>";
        });

        html += "</table></div>";
        div.innerHTML = html;
    } catch (err) {
        console.error(err);
    }
}

async function laadFotos() {
    const bedrijf = window.currentDrawerData.naam;
    const lijstDiv = document.getElementById("fotosLijst");
    if (!lijstDiv) return;
    try {
        const res = await fetch("/api/fotos?bedrijf=" + encodeURIComponent(bedrijf));
        const fotos = await res.json();
        let html = "";
        fotos.forEach(f => {
            html += `<img src="/fotos_uploads/${f.bestandsnaam}" style="width:70px;height:70px;object-fit:cover;border-radius:6px;border:1px solid #e2e8f0;cursor:pointer;" onclick="window.open('/fotos_uploads/${f.bestandsnaam}', '_blank')" title="Door ${f.geupload_door} op ${f.timestamp}">`;
        });
        lijstDiv.innerHTML = html;
    } catch (err) {
        console.error(err);
    }
}

async function uploadFoto() {
    const input = document.getElementById("fotoInput");
    const bestand = input.files[0];
    if (!bestand) return;

    const formData = new FormData();
    formData.append("bedrijf", window.currentDrawerData.naam);
    formData.append("foto", bestand);

    try {
        const res = await fetch("/api/fotos", { method: "POST", body: formData });
        const data = await res.json();
        if (data.error) {
            alert(data.error);
        } else {
            laadFotos();
        }
    } catch (err) {
        alert("Er ging iets mis bij het uploaden.");
    }
    input.value = "";
}
function closeDrawer() {
    document.getElementById("overlay").style.display = "none";
    document.getElementById("drawer").classList.remove("open");
}
async function toggleOpslaan(event, naam, el) {
    event.stopPropagation();
    try {
        const res = await fetch("/api/opgeslagen", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({naam: naam})
        });
        const data = await res.json();
        el.textContent = data.opgeslagen ? "★" : "☆";
        el.classList.toggle("opgeslagen", data.opgeslagen);
    } catch (err) {
        console.error(err);
    }
}
</script>

</div>

</body>
</html>
'''

@zoeken_bp.route("/export-csv")
def export_csv():
    import csv
    import io

    zoekterm = request.args.get("zoekterm", "").lower()
    land     = request.args.get("land", "")
    regio    = request.args.get("regio", "")
    klanttype = request.args.get("klanttype", "")
    materiaal = request.args.get("materiaal", "")
    brontype  = request.args.get("brontype", "")
    accountmanager = request.args.get("accountmanager", "")
    kwaliteiten = request.args.get("kwaliteiten", "")
    volume_filter = request.args.get("volume_filter", "")
    materiaal_min_volume = request.args.get("materiaal_min_volume", "")

    bedrijven = ENF_BEDRIJVEN
    if zoekterm:  bedrijven = [b for b in bedrijven if zoekterm in b["naam"].lower() or zoekterm in b.get("contactpersoon","").lower() or zoekterm in b.get("regio","").lower()]
    if land:      bedrijven = [b for b in bedrijven if b.get("land","").strip().lower() == land.strip().lower()]
    if regio:     bedrijven = [b for b in bedrijven if b.get("regio","").strip().lower() == regio.strip().lower()]
    if klanttype: bedrijven = [b for b in bedrijven if klanttype.strip().lower() in b.get("klanttype","").lower()]
    if materiaal: bedrijven = [b for b in bedrijven if materiaal.strip().lower() in b.get("materialen","").lower()]
    if materiaal and materiaal_min_volume:
        bedrijven = [b for b in bedrijven if voldoet_aan_materiaal_min_volume(b, materiaal, materiaal_min_volume)]
    if brontype:  bedrijven = [b for b in bedrijven if b.get("brontype","").strip().lower() == brontype.strip().lower()]
    if kwaliteiten: bedrijven = [b for b in bedrijven if kwaliteiten.strip().lower() in b.get("kwaliteiten","").lower()]
    if volume_filter:
        def _volume_getal_csv(b):
            try:
                return float(str(b.get("volume","")).replace(",", "").strip())
            except (ValueError, TypeError):
                return None
        if volume_filter == "small":
            bedrijven = [b for b in bedrijven if (v := _volume_getal_csv(b)) is not None and v < 1000]
        elif volume_filter == "medium":
            bedrijven = [b for b in bedrijven if (v := _volume_getal_csv(b)) is not None and 1000 <= v <= 10000]
        elif volume_filter == "large":
            bedrijven = [b for b in bedrijven if (v := _volume_getal_csv(b)) is not None and v > 10000]
    if accountmanager:
        accountmanagers_alle = laad_accountmanagers()
        gezocht_am = session.get("gebruikersnaam", "") if accountmanager == "__mij__" else accountmanager
        bedrijven = [b for b in bedrijven if accountmanagers_alle.get(b["naam"], "") == gezocht_am]

    output = io.StringIO()
    schrijver = csv.writer(output)
    schrijver.writerow(["Naam", "Land", "Stad/Regio", "Bedrijfstype", "Materialen", "Kwaliteiten", "Klanttype", "Volume (t/jaar)",
                         "Volume per materiaal", "Adres", "Telefoonnummer", "Contactpersoon", "Accountmanager", "Certificeringen"])
    accountmanagers_export = laad_accountmanagers()
    for b in bedrijven:
        volumes_dict = b.get("materiaal_volumes", {})
        volumes_tekst = ", ".join(f"{k}: {v}" for k, v in volumes_dict.items()) if isinstance(volumes_dict, dict) else ""
        schrijver.writerow([
            b.get("naam",""), b.get("land",""), b.get("regio",""), b.get("brontype",""),
            b.get("materialen",""), b.get("kwaliteiten",""), b.get("klanttype",""), b.get("volume",""),
            volumes_tekst, b.get("adres",""), b.get("telefoon",""), b.get("contactpersoon",""),
            accountmanagers_export.get(b.get("naam",""), ""), b.get("certificeringen",""),
        ])

    from flask import Response
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=recyclefind_export.csv"}
    )

@zoeken_bp.route("/export-data")
def export_data():
    _guard = vereist_admin_of_403()
    if _guard: return _guard
    from flask import Response
    pakket = {
        "bedrijven": ENF_BEDRIJVEN,
        "papierfabrieken": PAPIERFABRIEKEN,
    }
    return Response(
        json.dumps(pakket, ensure_ascii=False, indent=2),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=live_data_export.json"}
    )

@zoeken_bp.route("/api/fabriek-analyse", methods=["GET"])
def fabriek_analyse():
    naam = request.args.get("fabriek", "")
    fabriek = next((f for f in PAPIERFABRIEKEN if f["naam"] == naam), None)
    if not fabriek or "lat" not in fabriek:
        return jsonify({"error": "Fabriek niet gevonden"}), 404

    fabriek_materialen = [m.strip().lower() for m in fabriek.get("materialen", "").split(",")]
    fabriek_kwaliteiten = [k.strip().lower() for k in fabriek.get("kwaliteiten", "").split(",") if k.strip()]

    resultaten = []
    for b in ENF_BEDRIJVEN:
        if "lat" not in b or "lon" not in b:
            continue
        bedrijf_materialen = [m.strip().lower() for m in b.get("materialen", "").split(",")]
        gedeeld = [m for m in fabriek_materialen if m in bedrijf_materialen]
        if not gedeeld:
            continue
        bedrijf_kwaliteiten = [k.strip().lower() for k in b.get("kwaliteiten", "").split(",") if k.strip()]
        gedeelde_kwaliteiten = [k for k in fabriek_kwaliteiten if k in bedrijf_kwaliteiten]
        afstand = bereken_afstand_km(fabriek["lat"], fabriek["lon"], b["lat"], b["lon"])
        resultaten.append({
            "naam": b["naam"],
            "land": b["land"],
            "regio": b["regio"],
            "materialen": b.get("materialen", ""),
            "gedeelde_materialen": ", ".join(gedeeld),
            "gedeelde_kwaliteiten": ", ".join(gedeelde_kwaliteiten),
            "afstand_km": round(afstand, 1)
        })

    resultaten.sort(key=lambda x: (0 if x["gedeelde_kwaliteiten"] else 1, x["afstand_km"]))
    return jsonify(resultaten[:25])

@zoeken_bp.route("/details")
def details():
    url = request.args.get("url", "")
    if not url or "enfpaper" not in url:
        return jsonify({})
    return jsonify(haal_bedrijf_details(url))

@zoeken_bp.route("/api/transport", methods=["GET"])
def get_transport():
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    return jsonify(vind_transport_tarieven_dichtbij(lat, lon))

@zoeken_bp.route("/api/status", methods=["GET"])
def get_status():
    bedrijf = request.args.get("bedrijf", "")
    alle = laad_status()
    return jsonify({"status": alle.get(bedrijf, "")})

@zoeken_bp.route("/api/accountmanager", methods=["GET"])
def get_accountmanager():
    bedrijf = request.args.get("bedrijf", "")
    alle = laad_accountmanagers()
    return jsonify({"accountmanager": alle.get(bedrijf, "")})

@zoeken_bp.route("/api/accountmanager", methods=["POST"])
def set_accountmanager():
    data = request.get_json()
    bedrijf = data.get("bedrijf", "")
    nieuwe_am = data.get("accountmanager", "")
    if not bedrijf:
        return jsonify({"error": "Bedrijf is verplicht"}), 400
    alle = laad_accountmanagers()
    oude_am = alle.get(bedrijf, "")
    if nieuwe_am:
        alle[bedrijf] = nieuwe_am
    else:
        alle.pop(bedrijf, None)
    bewaar_accountmanagers(alle)

    huidige_gebruikersnaam = session.get("gebruikersnaam", "")
    if nieuwe_am and nieuwe_am != oude_am and nieuwe_am != huidige_gebruikersnaam:
        alle_meldingen = laad_meldingen()
        alle_meldingen.append({
            "id": str(uuid.uuid4()),
            "tekst": f"{huidige_gebruikersnaam} heeft jou toegewezen als accountmanager voor {bedrijf}.",
            "bedrijf": bedrijf, "van": huidige_gebruikersnaam,
            "voor_gebruiker": nieuwe_am, "voor_team": "",
            "gelezen": False, "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
        })
        bewaar_meldingen(alle_meldingen)

    return jsonify({"accountmanager": nieuwe_am})

BEWERKBARE_BEDRIJFSVELDEN = {"brontype", "klanttype", "materialen", "contactpersoon", "volume", "adres", "telefoon", "kwaliteiten", "certificeringen", "betalingstermijn", "bankgegevens", "vat_nummer", "email_logistiek", "email_finance", "email_sales",
                              "email_algemeen", "kvk_nummer", "postcode", "stad", "bank_naam", "begunstigde", "bank_adres", "iban_eur", "iban_usd", "iban_gbp", "swift_bic",
                              "factuur_email", "factuur_contactpersoon", "vragen_betalingen_email", "sales_facturatie_email", "overige_informatie"}

@zoeken_bp.route("/api/bedrijf-veld", methods=["POST"])
def set_bedrijf_veld():
    data = request.get_json()
    bedrijf_naam = data.get("bedrijf", "")
    veld = data.get("veld", "")
    waarde = data.get("waarde", "")
    if not bedrijf_naam or veld not in BEWERKBARE_BEDRIJFSVELDEN:
        return jsonify({"error": "Ongeldig bedrijf of veld"}), 400
    for b in ENF_BEDRIJVEN:
        if b["naam"] == bedrijf_naam:
            b[veld] = waarde
            if veld == "adres" and waarde.strip():
                _geo = geocode_adres(waarde, b.get("regio", ""))
                if _geo:
                    b["lat"] = _geo["lat"]
                    b["lon"] = _geo["lon"]
            bewaar_bedrijven()
            if veld == "contactpersoon" and waarde:
                sync_contactpersoon_naar_contacten(bedrijf_naam, waarde, email=b.get("email_algemeen",""), telefoon=b.get("telefoon",""), gebruiker=session.get("gebruikersnaam",""))
            return jsonify({"veld": veld, "waarde": waarde, "lat": b.get("lat"), "lon": b.get("lon")})
    for f_item in PAPIERFABRIEKEN:
        if f_item["naam"] == bedrijf_naam:
            f_item[veld] = waarde
            if veld == "adres" and waarde.strip():
                _geo = geocode_adres(waarde, f_item.get("stad", ""))
                if _geo:
                    f_item["lat"] = _geo["lat"]
                    f_item["lon"] = _geo["lon"]
            bewaar_papierfabrieken()
            if veld == "contactpersoon" and waarde:
                sync_contactpersoon_naar_contacten(bedrijf_naam, waarde, email=f_item.get("email_algemeen",""), telefoon=f_item.get("telefoon",""), gebruiker=session.get("gebruikersnaam",""))
            return jsonify({"veld": veld, "waarde": waarde, "lat": f_item.get("lat"), "lon": f_item.get("lon")})
    return jsonify({"error": "Bedrijf niet gevonden"}), 404

@zoeken_bp.route("/api/materiaal-volume", methods=["POST"])
def set_materiaal_volume():
    data = request.get_json()
    bedrijf_naam = data.get("bedrijf", "")
    materiaal = data.get("materiaal", "").strip()
    volume = data.get("volume", "").strip()
    if not bedrijf_naam or not materiaal:
        return jsonify({"error": "Bedrijf en materiaal zijn verplicht"}), 400
    for b in ENF_BEDRIJVEN:
        if b["naam"] == bedrijf_naam:
            volumes = b.get("materiaal_volumes", {})
            if not isinstance(volumes, dict):
                volumes = {}
            if volume:
                volumes[materiaal] = volume
            else:
                volumes.pop(materiaal, None)
            b["materiaal_volumes"] = volumes
            bewaar_bedrijven()
            return jsonify({"materiaal": materiaal, "volume": volume})
    for f_item in PAPIERFABRIEKEN:
        if f_item["naam"] == bedrijf_naam:
            volumes = f_item.get("materiaal_volumes", {})
            if not isinstance(volumes, dict):
                volumes = {}
            if volume:
                volumes[materiaal] = volume
            else:
                volumes.pop(materiaal, None)
            f_item["materiaal_volumes"] = volumes
            bewaar_papierfabrieken()
            return jsonify({"materiaal": materiaal, "volume": volume})
    return jsonify({"error": "Bedrijf niet gevonden"}), 404

@zoeken_bp.route("/api/fabriek-kwaliteiten", methods=["GET"])
def get_fabriek_kwaliteiten():
    naam = request.args.get("fabriek", "")
    fabriek = next((f for f in PAPIERFABRIEKEN if f["naam"] == naam), None)
    return jsonify({"kwaliteiten": fabriek.get("kwaliteiten", "") if fabriek else ""})

@zoeken_bp.route("/api/fabriek-kwaliteiten", methods=["POST"])
def set_fabriek_kwaliteiten():
    data = request.get_json()
    naam = data.get("fabriek", "")
    waarde = data.get("waarde", "")
    for f in PAPIERFABRIEKEN:
        if f["naam"] == naam:
            f["kwaliteiten"] = waarde
            bewaar_papierfabrieken()
            return jsonify({"kwaliteiten": waarde})
    return jsonify({"error": "Fabriek niet gevonden"}), 404

@zoeken_bp.route("/api/status", methods=["POST"])
def set_status():
    data = request.get_json()
    bedrijf = data.get("bedrijf", "")
    nieuwe_status = data.get("status", "")
    if not bedrijf:
        return jsonify({"error": "Bedrijf is verplicht"}), 400
    alle = laad_status()
    alle[bedrijf] = nieuwe_status
    bewaar_status(alle)

    huidige_gebruikersnaam = session.get("gebruikersnaam", "")
    toegewezen_am = laad_accountmanagers().get(bedrijf, "")
    if toegewezen_am and toegewezen_am != huidige_gebruikersnaam and nieuwe_status:
        status_labels = {"klant": "Klant", "potentie": "Potentie", "in_proces": "In Proces", "geen_interesse": "Geen Interesse"}
        alle_meldingen = laad_meldingen()
        alle_meldingen.append({
            "id": str(uuid.uuid4()),
            "tekst": f"{huidige_gebruikersnaam} heeft de status van {bedrijf} (jouw bedrijf) gewijzigd naar \"{status_labels.get(nieuwe_status, nieuwe_status)}\".",
            "bedrijf": bedrijf, "van": huidige_gebruikersnaam,
            "voor_gebruiker": toegewezen_am, "voor_team": "",
            "gelezen": False, "timestamp": datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
        })
        bewaar_meldingen(alle_meldingen)

    return jsonify({"status": nieuwe_status})

@zoeken_bp.route("/api/company-analysis", methods=["POST"])
def company_analysis():
    from ai_filter import analyseer_uitrusting

    data = request.get_json()
    resultaat = analyseer_uitrusting(data)

    return jsonify(resultaat)

PAGINA_GROOTTE = 200

def _bouw_weergave_balk():
    """Zelfde balk als in core.py's sidebar_html() — hier apart opgebouwd omdat de
    zoekpagina een eigen, hardcoded zijbalk-template heeft (zie de LET OP in
    core.py's sidebar_html-docstring)."""
    if not (is_huidige_gebruiker_admin() or session.get("rol", "") == "directeur"):
        return ""
    huidige_weergave = session.get("weergave_als", "alles")
    opties_html = "".join(
        f'<option value="{waarde}" {"selected" if huidige_weergave == waarde else ""}>{label}</option>'
        for waarde, label in [("alles", "Alles"), ("accountmanager", "Commercieel"), ("logistiek", "Logistiek"), ("weegbrug", "Weegbrug"), ("backoffice", "Backoffice"), ("finance", "Finance")]
    )
    return f'''<div style="padding:10px 16px;border-bottom:1px solid rgba(255,255,255,0.1);">
        <label style="font-size:9.5px;text-transform:uppercase;letter-spacing:0.06em;color:rgba(255,255,255,0.4);display:block;margin-bottom:4px;">Weergave als</label>
        <select onchange="window.location.href='/wissel-weergave?afdeling='+this.value" style="width:100%;padding:5px 6px;border-radius:5px;border:1px solid rgba(255,255,255,0.15);background:rgba(255,255,255,0.08);color:#fff;font-size:11.5px;">
            {opties_html}
        </select>
    </div>'''

@zoeken_bp.route("/", methods=["GET", "POST"])
def index():
    _guard = vereist_afdeling_of_403("zoeken")
    if _guard: return _guard
    zoekterm = land = regio = klanttype = materiaal = brontype = accountmanager = kwaliteiten = volume_filter = materiaal_min_volume = ""
    pagina = 1

    if request.method == "POST":
        zoekterm = request.form.get("zoekterm", "").lower()
        land     = request.form.get("land", "")
        regio    = request.form.get("regio", "")
        klanttype = request.form.get("klanttype", "")
        materiaal = request.form.get("materiaal", "")
        brontype  = request.form.get("brontype", "")
        accountmanager = request.form.get("accountmanager", "")
        kwaliteiten = request.form.get("kwaliteiten", "")
        volume_filter = request.form.get("volume_filter", "")
        materiaal_min_volume = request.form.get("materiaal_min_volume", "")
        pagina    = request.form.get("pagina", "1")
    else:
        zoekterm = request.args.get("zoekterm", "").lower()
        land     = request.args.get("land", "")
        regio    = request.args.get("regio", "")
        klanttype = request.args.get("klanttype", "")
        materiaal = request.args.get("materiaal", "")
        brontype  = request.args.get("brontype", "")
        accountmanager = request.args.get("accountmanager", "")
        kwaliteiten = request.args.get("kwaliteiten", "")
        volume_filter = request.args.get("volume_filter", "")
        materiaal_min_volume = request.args.get("materiaal_min_volume", "")
        pagina    = request.args.get("pagina", "1")

    try:
        pagina = max(1, int(pagina))
    except (TypeError, ValueError):
        pagina = 1

    bedrijven = ENF_BEDRIJVEN
    if zoekterm:  bedrijven = [b for b in bedrijven if zoekterm in b["naam"].lower() or zoekterm in b.get("contactpersoon","").lower() or zoekterm in b.get("regio","").lower()]
    if land:      bedrijven = [b for b in bedrijven if b.get("land","").strip().lower() == land.strip().lower()]
    if regio:     bedrijven = [b for b in bedrijven if b.get("regio","").strip().lower() == regio.strip().lower()]
    if klanttype: bedrijven = [b for b in bedrijven if klanttype.strip().lower() in b.get("klanttype","").lower()]
    if materiaal: bedrijven = [b for b in bedrijven if materiaal.strip().lower() in b.get("materialen","").lower()]
    if materiaal and materiaal_min_volume:
        bedrijven = [b for b in bedrijven if voldoet_aan_materiaal_min_volume(b, materiaal, materiaal_min_volume)]
    if brontype:  bedrijven = [b for b in bedrijven if b.get("brontype","").strip().lower() == brontype.strip().lower()]
    if kwaliteiten: bedrijven = [b for b in bedrijven if kwaliteiten.strip().lower() in b.get("kwaliteiten","").lower()]
    if volume_filter:
        def _volume_getal(b):
            try:
                return float(str(b.get("volume","")).replace(",", "").strip())
            except (ValueError, TypeError):
                return None
        if volume_filter == "small":
            bedrijven = [b for b in bedrijven if (v := _volume_getal(b)) is not None and v < 1000]
        elif volume_filter == "medium":
            bedrijven = [b for b in bedrijven if (v := _volume_getal(b)) is not None and 1000 <= v <= 10000]
        elif volume_filter == "large":
            bedrijven = [b for b in bedrijven if (v := _volume_getal(b)) is not None and v > 10000]
    if accountmanager:
        accountmanagers_alle = laad_accountmanagers()
        gezocht_am = session.get("gebruikersnaam", "") if accountmanager == "__mij__" else accountmanager
        bedrijven = [b for b in bedrijven if accountmanagers_alle.get(b["naam"], "") == gezocht_am]

    totaal_gevonden = len(bedrijven)

    landen_in_resultaat = len({b.get("land","") for b in bedrijven if b.get("land")})
    _volume_som = sum(parse_hoeveelheid_getal(b.get("volume","")) for b in bedrijven)
    if _volume_som >= 1_000_000:
        volume_totaal_resultaat = f"{_volume_som/1_000_000:.1f} Mt"
    elif _volume_som >= 1000:
        volume_totaal_resultaat = f"{_volume_som/1000:.0f}k t"
    elif _volume_som > 0:
        volume_totaal_resultaat = f"{_volume_som:.0f} t"
    else:
        volume_totaal_resultaat = ""

    er_is_gefilterd = bool(zoekterm or land or regio or klanttype or materiaal or brontype or accountmanager or kwaliteiten or volume_filter)
    totaal_paginas = max(1, (totaal_gevonden + PAGINA_GROOTTE - 1) // PAGINA_GROOTTE)
    pagina = min(pagina, totaal_paginas)
    start = (pagina - 1) * PAGINA_GROOTTE
    bedrijven = bedrijven[start:start + PAGINA_GROOTTE]
    opgeslagen_namen = set(laad_opgeslagen())

    _am_lookup = laad_accountmanagers()
    _alle_notities_index = laad_notities()
    _vandaag_index = datetime.date.today()
    for b in bedrijven:
        b["accountmanager"] = _am_lookup.get(b["naam"], "")

        b["laatst_contact"] = ""
        notities_van_bedrijf = _alle_notities_index.get(b["naam"], [])
        laatste_datum = None
        for n in notities_van_bedrijf:
            try:
                dt = datetime.datetime.strptime(n.get("timestamp",""), "%d-%m-%Y %H:%M").date()
                if laatste_datum is None or dt > laatste_datum:
                    laatste_datum = dt
            except (ValueError, TypeError):
                continue
        if laatste_datum:
            dagen_geleden = (_vandaag_index - laatste_datum).days
            if dagen_geleden <= 0:
                b["laatst_contact"] = "Vandaag"
            elif dagen_geleden == 1:
                b["laatst_contact"] = "Gisteren"
            else:
                b["laatst_contact"] = f"{dagen_geleden} dagen"

    # Brontype-categorie bepalen voor kaartkleur + legenda (op basis van wat al bekend is, niks verzonnen)
    def _kaart_categorie(brontype_tekst):
        t = (brontype_tekst or "").strip().lower()
        if "papierfabriek" in t:
            return "papierfabriek"
        if "recyclingcentrum" in t:
            return "recyclingcentrum"
        if "inzamelaar" in t:
            return "inzamelaar"
        return "overig"
    for b in bedrijven:
        b["kaart_categorie"] = _kaart_categorie(b.get("brontype",""))
    _legenda_tellingen = {"recyclingcentrum": 0, "inzamelaar": 0, "papierfabriek": 0, "overig": 0}
    for b in bedrijven:
        _legenda_tellingen[b["kaart_categorie"]] += 1

    _volume_labels = {"small": "Volume: <1.000 t/j", "medium": "Volume: 1.000-10.000 t/j", "large": "Volume: >10.000 t/j"}
    _accountmanager_label = "Accountmanager: Mijn bedrijven" if accountmanager == "__mij__" else (f"Accountmanager: {accountmanager}" if accountmanager else "")
    _alle_filter_velden = [
        ("klanttype", klanttype, f"Customer Type: {klanttype}"),
        ("brontype", brontype, f"Bedrijfstype: {brontype}"),
        ("materiaal", materiaal, f"Materiaal: {materiaal}"),
        ("materiaal_min_volume", materiaal_min_volume, f"Min. volume {materiaal}: {materiaal_min_volume} t/j" if materiaal_min_volume else ""),
        ("kwaliteiten", kwaliteiten, f"Kwaliteiten: {kwaliteiten}"),
        ("volume_filter", volume_filter, _volume_labels.get(volume_filter, "")),
        ("accountmanager", accountmanager, _accountmanager_label),
    ]
    actieve_filter_count = sum(1 for _, waarde, _ in _alle_filter_velden if waarde)

    def _maak_filter_url_zonder(uit_te_sluiten_key):
        params = {"zoekterm": zoekterm, "land": land, "regio": regio, "klanttype": klanttype,
                   "materiaal": materiaal, "brontype": brontype, "accountmanager": accountmanager,
                   "kwaliteiten": kwaliteiten, "volume_filter": volume_filter, "materiaal_min_volume": materiaal_min_volume}
        params[uit_te_sluiten_key] = ""
        params = {k: v for k, v in params.items() if v}
        return "/?" + "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())

    actieve_filters_lijst = [
        {"label": label, "url": _maak_filter_url_zonder(key)}
        for key, waarde, label in _alle_filter_velden if waarde
    ]

    def maak_pagina_url(p):
        params = {"zoekterm": zoekterm, "land": land, "regio": regio, "klanttype": klanttype,
                   "materiaal": materiaal, "brontype": brontype, "accountmanager": accountmanager,
                   "kwaliteiten": kwaliteiten, "volume_filter": volume_filter, "materiaal_min_volume": materiaal_min_volume, "pagina": p}
        params = {k: v for k, v in params.items() if v}
        return "/?" + "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in params.items())

    export_params = {"zoekterm": zoekterm, "land": land, "regio": regio, "klanttype": klanttype,
                      "materiaal": materiaal, "brontype": brontype, "accountmanager": accountmanager,
                      "kwaliteiten": kwaliteiten, "volume_filter": volume_filter, "materiaal_min_volume": materiaal_min_volume}
    export_params = {k: v for k, v in export_params.items() if v}
    export_query = "&".join(f"{k}={requests.utils.quote(str(v))}" for k, v in export_params.items())

    return render_template_string(HTML,
        bedrijven=bedrijven, zoekterm=zoekterm, land=land, regio=regio,
        klanttype=klanttype, materiaal=materiaal, brontype=brontype, accountmanager=accountmanager,
        kwaliteiten=kwaliteiten, volume_filter=volume_filter, materiaal_min_volume=materiaal_min_volume,
        totaal=len(ENF_BEDRIJVEN), landen=LANDEN,
        totaal_gevonden=totaal_gevonden, regio_per_land=REGIO_PER_LAND,
        landen_in_resultaat=landen_in_resultaat, volume_totaal_resultaat=volume_totaal_resultaat,
        legenda_tellingen=_legenda_tellingen,
        papierfabrieken=PAPIERFABRIEKEN, opgeslagen_namen=opgeslagen_namen,
        er_is_gefilterd=er_is_gefilterd, pagina=pagina, totaal_paginas=totaal_paginas,
        maak_pagina_url=maak_pagina_url, export_query=export_query,
        alle_gebruikersnamen=sorted(laad_users().keys()),
        actieve_filter_count=actieve_filter_count, actieve_filters_lijst=actieve_filters_lijst,
        materiaal_categorieen=sorted(laad_materiaal_taxonomie().keys()),
        mag_pagina_zien=mag_pagina_zien, weergave_balk=_bouw_weergave_balk(),
        sidebar_html_ingevoegd=sidebar_html('zoeken'))

OPGESLAGEN_FILE = datapad("opgeslagen.json")

def laad_opgeslagen():
    try:
        with open(OPGESLAGEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def bewaar_opgeslagen(data):
    with open(OPGESLAGEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@zoeken_bp.route("/api/opgeslagen", methods=["GET"])
def get_opgeslagen():
    return jsonify(laad_opgeslagen())

@zoeken_bp.route("/api/opgeslagen", methods=["POST"])
def toggle_opgeslagen():
    data = request.get_json()
    naam = data.get("naam", "")
    if not naam:
        return jsonify({"error": "Naam is verplicht"}), 400
    lijst = laad_opgeslagen()
    if naam in lijst:
        lijst.remove(naam)
        opgeslagen = False
    else:
        lijst.append(naam)
        opgeslagen = True
    bewaar_opgeslagen(lijst)
    return jsonify({"opgeslagen": opgeslagen})

@zoeken_bp.route("/fabriek/<naam>")
def fabriek_detail(naam):
    return redirect(url_for("zoeken.bedrijf_profiel", naam=naam))

@zoeken_bp.route("/wereldkaart")
def wereldkaart():
    _guard = vereist_afdeling_of_403("wereldkaart")
    if _guard: return _guard
    status_alle = laad_status()
    kaart_data = [
        {"naam": b["naam"], "land": b["land"], "regio": b.get("regio",""), "lat": b["lat"], "lon": b["lon"],
         "materialen": b.get("materialen",""), "volume": b.get("volume",""), "status": status_alle.get(b["naam"],"")}
        for b in ENF_BEDRIJVEN if b.get("lat") and b.get("lon")
    ]

    inhoud = """
<style>
.wk-layout { display:flex; gap:20px; height:calc(100vh - 128px); }
.wk-filters { width:240px; flex-shrink:0; background:#fff; border:1px solid var(--gray-200); border-radius:14px; padding:18px; overflow-y:auto; }
.wk-map-wrap { flex:1; border-radius:14px; overflow:hidden; border:1px solid var(--gray-200); position:relative; }
#wereldKaart { width:100%; height:100%; }
.wk-stat { display:flex; justify-content:space-between; padding:6px 0; font-size:0.82rem; color:var(--gray-600); border-bottom:1px solid var(--gray-100); }
.wk-stat strong { color:var(--brand-700); }
.wk-legenda { display:flex; align-items:center; gap:6px; font-size:0.78rem; color:var(--gray-500); margin-top:4px; }
.wk-legenda span.stip { width:9px; height:9px; border-radius:50%; display:inline-block; }
</style>

<div class="page-title">World Map</div>

<div class="wk-layout">
    <aside class="wk-filters">
        <div class="filters-title" style="margin-bottom:14px;">🎚️ Filters</div>
        <div class="filter-group">
            <label class="filter-label">Land</label>
            <select class="filter-select" id="wkLand" onchange="wkFilter()">
                <option value="">Alle landen</option>
                {% for l in landen %}<option value="{{ l }}">{{ l }}</option>{% endfor %}
            </select>
        </div>
        <div class="filter-group">
            <label class="filter-label">Materiaal</label>
            <select class="filter-select" id="wkMateriaal" onchange="wkFilter()">
                <option value="">Alle materialen</option>
                <option value="Paper">Paper</option>
                <option value="Plastic">Plastic</option>
                <option value="Metal">Metal</option>
                <option value="Glass">Glass</option>
                <option value="Wood">Wood</option>
                <option value="Organic">Organic</option>
            </select>
        </div>
        <div class="filter-group">
            <label class="filter-label">Status</label>
            <select class="filter-select" id="wkStatus" onchange="wkFilter()">
                <option value="">Alle statussen</option>
                <option value="klant">🟢 Klant</option>
                <option value="potentie">🟡 Potentie</option>
                <option value="in_proces">🔵 In Proces</option>
            </select>
        </div>
        <hr class="filter-divider">
        <div class="wk-stat">Zichtbaar op kaart<strong id="wkAantal">0</strong></div>
        <div class="wk-stat">Totaal bedrijven<strong>{{ kaart_data|length }}</strong></div>
        <hr class="filter-divider">
        <div class="wk-legenda"><span class="stip" style="background:#22c55e;"></span> Klant</div>
        <div class="wk-legenda"><span class="stip" style="background:#f59e0b;"></span> Potentie</div>
        <div class="wk-legenda"><span class="stip" style="background:#3b82f6;"></span> In proces</div>
        <div class="wk-legenda"><span class="stip" style="background:#0d5c62;"></span> Geen status</div>
    </aside>
    <div class="wk-map-wrap">
        <div id="wereldKaart"></div>
    </div>
</div>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<style>
.marker-cluster-small { background-color: rgba(179,217,218,0.7); }
.marker-cluster-small div { background-color: rgba(63,146,149,0.85); color: #fff; }
.marker-cluster-medium { background-color: rgba(63,146,149,0.6); }
.marker-cluster-medium div { background-color: rgba(20,118,123,0.9); color: #fff; }
.marker-cluster-large { background-color: rgba(10,74,79,0.6); }
.marker-cluster-large div { background-color: rgba(10,74,79,0.95); color: #fff; }
.marker-cluster div { font-weight: 700; font-family: 'Libre Franklin', -apple-system, sans-serif; }
</style>
<script>
var ALLE_BEDRIJVEN_WK = {{ kaart_data|tojson }};
var wkKaart = L.map("wereldKaart").setView([30, 10], 2);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {attribution:"© OpenStreetMap"}).addTo(wkKaart);
var wkKleur = {"klant":"#22c55e","potentie":"#f59e0b","in_proces":"#3b82f6","geen_interesse":"#6b7280","":"#0d5c62"};
var wkCluster = null;

function wkFilter() {
    var land = document.getElementById("wkLand").value;
    var mat = document.getElementById("wkMateriaal").value;
    var status = document.getElementById("wkStatus").value;

    if (wkCluster) wkKaart.removeLayer(wkCluster);
    wkCluster = L.markerClusterGroup({
        iconCreateFunction: function(cluster) {
            return L.divIcon({
                html: '<div style="background:#0d5c62;color:#fff;width:34px;height:34px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:12px;border:2px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,0.25);">' + cluster.getChildCount() + '</div>',
                className: '', iconSize: [34, 34]
            });
        }
    });

    var zichtbaar = 0;
    ALLE_BEDRIJVEN_WK.forEach(function(b) {
        if (land && b.land !== land) return;
        if (mat && b.materialen.indexOf(mat) === -1) return;
        if (status && b.status !== status) return;
        zichtbaar++;
        var kleur = wkKleur[b.status] || wkKleur[""];
        var marker = L.circleMarker([b.lat, b.lon], {radius:6, color:"#fff", weight:1, fillColor:kleur, fillOpacity:0.9});
        var popup = "<b>" + b.naam + "</b><br><small>" + b.regio + ", " + b.land + "</small>";
        popup += "<br><small>" + (b.materialen || "—") + "</small>";
        if (b.volume) popup += "<br><small>" + b.volume + " t/jaar</small>";
        popup += '<br><a href="/bedrijf/' + encodeURIComponent(b.naam) + '" style="color:#0d5c62;font-weight:600;">Bekijk profiel →</a>';
        marker.bindPopup(popup);
        wkCluster.addLayer(marker);
    });
    wkKaart.addLayer(wkCluster);
    document.getElementById("wkAantal").textContent = zichtbaar;
}
wkFilter();
</script>
    """
    pagina = render_simple_page("World Map", "wereldkaart", inhoud)
    return render_template_string(pagina, landen=LANDEN, kaart_data=kaart_data)

@zoeken_bp.route("/bedrijf/<naam>")
def bedrijf_profiel(naam):
    bedrijf = next((b for b in ENF_BEDRIJVEN if b["naam"] == naam), None)
    is_fabriek_profiel = False
    if not bedrijf:
        _fabriek_bron = next((f for f in PAPIERFABRIEKEN if f["naam"] == naam), None)
        if _fabriek_bron:
            is_fabriek_profiel = True
            bedrijf = dict(_fabriek_bron)
            bedrijf.setdefault("regio", bedrijf.get("stad", ""))
            bedrijf.setdefault("brontype", "Papierfabriek")
    if not bedrijf:
        inhoud = '<div class="page-title">Niet gevonden</div><div class="lege-staat">Dit bedrijf bestaat niet (meer).</div>'
        pagina = render_simple_page("Niet gevonden", "zoeken", inhoud)
        return render_template_string(pagina), 404

    status_alle = laad_status()
    status = status_alle.get(bedrijf["naam"], "")
    opgeslagen = bedrijf["naam"] in set(laad_opgeslagen())
    geverifieerd = bool(bedrijf.get("adres") or bedrijf.get("telefoon"))
    afhaallocaties = [] if is_fabriek_profiel else leverancier_instelling_voor(naam).get("afhaallocaties", [])

    inhoud = """
{% if is_fabriek_profiel %}<input type="hidden" id="isFabriekProfiel" value="1">{% endif %}
<div class="bedrijfsprofiel-inhoud">
<style>
.profiel-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:24px; }
.veld-label { font-size:10px; letter-spacing:0.08em; text-transform:uppercase; color:var(--gray-400); margin-bottom:3px; }
.klik-bewerken-veld {
    width:100%; border:1px solid transparent; background:transparent; padding:3px 6px; margin-left:-6px;
    font-size:13px; font-family:inherit; color:var(--gray-800); border-radius:5px; box-sizing:border-box; cursor:text;
}
.klik-bewerken-veld:hover { background:var(--gray-50); border-color:var(--gray-100); }
.klik-bewerken-veld:focus { background:#fff; border-color:var(--brand-300); outline:none; box-shadow:0 0 0 2px rgba(20,118,123,0.12); cursor:auto; }
select.klik-bewerken-veld { cursor:pointer; }
.profiel-naam { font-size:1.6rem; font-weight:800; color:var(--gray-900); letter-spacing:-0.5px; }
.profiel-loc { color:var(--gray-400); font-size:0.9rem; margin-top:4px; }
.profiel-grid { display:grid; grid-template-columns:1.3fr 1fr; gap:20px; align-items:start; }
@media (max-width:900px) { .profiel-grid { grid-template-columns:1fr; } }
.bedrijfsprofiel-inhoud .info-kaart {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0 0 16px 0;
    border-bottom: 1px solid var(--gray-200);
    margin-bottom: 16px !important;
    box-shadow: none;
}
.bedrijfsprofiel-inhoud .info-kaart:last-child { border-bottom: none; }
.bedrijfsprofiel-inhoud .profiel-grid > div .info-kaart:last-child { margin-bottom: 0 !important; }
#profielKaart { height:260px; border-radius:14px; overflow:hidden; border:1px solid var(--gray-200); margin-top:16px; }
.profiel-terug { color:var(--gray-400); text-decoration:none; font-size:0.85rem; display:inline-block; margin-bottom:16px; }
.profiel-terug:hover { color:var(--brand-600); }
.verificatie-badge {
    display: inline-flex; align-items: center; gap: 3px;
    font-size: 0.68rem; font-weight: 700; color: var(--green-600);
    background: var(--green-50); border: 1px solid #bbf7d0;
    padding: 2px 8px; border-radius: 4px; vertical-align: middle;
}
.dg-kaart-titel { font-size:0.78rem; color:var(--gray-400); text-transform:uppercase; letter-spacing:1.2px; margin-bottom:14px; font-weight:700; }
.tag-purple { background: #f5f3ff; color: #7c3aed; border: 1px solid #ddd6fe; }
</style>

<div style="font-size:12px;color:var(--gray-400);margin-bottom:6px;">
    <a href="/" style="color:var(--gray-400);text-decoration:none;">Zoeken</a> &nbsp;/&nbsp; {{ bedrijf.land }} &nbsp;/&nbsp; <span style="color:var(--gray-600);">{{ bedrijf.naam }}</span>
</div>
<div class="profiel-header">
    <div class="profiel-naam">{{ bedrijf.naam }}{% if geverifieerd %}<span class="verificatie-badge" style="margin-left:10px;">✓ Geverifieerd</span>{% endif %}</div>
    <div style="display:flex;align-items:center;gap:8px;">
        <span class="star-btn {% if opgeslagen %}opgeslagen{% endif %}" id="profielSterBtn" onclick="toggleOpslaanProfiel(this)" style="font-size:1.3rem;margin-right:4px;">{% if opgeslagen %}★{% else %}☆{% endif %}</span>
        <a href="#notitiesSectie" onclick="document.getElementById('nieuweNotitieTekst').focus();" style="font-size:13px;font-weight:600;color:var(--gray-600);border:1px solid var(--gray-200);padding:8px 14px;border-radius:6px;text-decoration:none;">Notitie</a>
        <a href="/export-csv?zoekterm={{ bedrijf.naam|urlencode }}" style="font-size:13px;font-weight:600;color:var(--gray-600);border:1px solid var(--gray-200);padding:8px 14px;border-radius:6px;text-decoration:none;">Export</a>
        <a href="/handelsorders/nieuw" style="font-size:13px;font-weight:600;color:#fff;background:var(--brand-600);padding:8px 14px;border-radius:6px;text-decoration:none;">Order aanmaken</a>
    </div>
</div>
<div style="display:flex;align-items:center;gap:10px;margin-top:-14px;margin-bottom:20px;font-size:13px;color:var(--gray-500);">
    {% if bedrijf.brontype %}<span style="background:var(--brand-600);color:#fff;font-size:11.5px;font-weight:600;padding:4px 10px;border-radius:5px;">{{ bedrijf.brontype }}</span>{% endif %}
    <span>{{ bedrijf.regio }}, {{ bedrijf.land }}</span>
</div>

{% if is_fabriek_profiel %}
<div style="display:flex;border:1px solid var(--gray-200);border-radius:var(--radius-md);margin-bottom:20px;overflow:hidden;">
    <div style="flex:1;padding:14px 20px;border-right:1px solid var(--gray-100);">
        <div style="font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Volume totaal</div>
        <div style="font-size:1.2rem;font-weight:700;color:var(--gray-800);">{{ bedrijf.volume|default('—',true) }}</div>
        <div style="font-size:11px;color:var(--gray-400);">t/jaar{% if bedrijf.materiaal_volumes %}, {{ bedrijf.materiaal_volumes|length }} materialen{% endif %}</div>
    </div>
    <div style="flex:1;padding:14px 20px;border-right:1px solid var(--gray-100);">
        <div style="font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Open orders</div>
        <div style="font-size:1.2rem;font-weight:700;color:var(--gray-800);">{{ open_orders_aantal }}</div>
        <div style="font-size:11px;color:var(--gray-400);">{% if open_orders_ton %}{{ open_orders_ton }} t deze periode{% else %}&nbsp;{% endif %}</div>
    </div>
    <div style="flex:1;padding:14px 20px;border-right:1px solid var(--gray-100);">
        <div style="font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Laatste contact</div>
        <div style="font-size:1.2rem;font-weight:700;color:var(--gray-800);">{{ laatst_contact_profiel|default('—',true) }}</div>
        <div style="font-size:11px;color:var(--gray-400);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ bedrijf.accountmanager|default('',true) }}{% if bedrijf.telefoon %}, telefoon{% endif %}</div>
    </div>
    <div style="flex:1;padding:14px 20px;">
        <div style="font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Afstand tot Alblasserdam</div>
        <div style="font-size:1.2rem;font-weight:700;color:var(--gray-800);">{% if afstand_alblasserdam %}{{ afstand_alblasserdam }} km{% else %}—{% endif %}</div>
        <div style="font-size:11px;color:var(--gray-400);">{{ bedrijf.regio }}, {{ bedrijf.land }}</div>
    </div>
</div>
{% else %}
<div style="display:flex;border-top:1px solid var(--gray-200);border-bottom:1px solid var(--gray-200);margin-bottom:20px;">
    <div style="flex:1;padding:14px 20px;border-right:1px solid var(--gray-200);">
        <div style="font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Volume totaal</div>
        <div style="font-size:1.2rem;font-weight:700;color:var(--gray-800);">{{ bedrijf.volume|default('—',true) }}</div>
        <div style="font-size:11px;color:var(--gray-400);">t/jaar{% if bedrijf.materiaal_volumes %}, {{ bedrijf.materiaal_volumes|length }} materialen{% endif %}</div>
    </div>
    <div style="flex:1;padding:14px 20px;border-right:1px solid var(--gray-200);">
        <div style="font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Open orders</div>
        <a href="/logistiek?bedrijf={{ bedrijf.naam|urlencode }}" style="text-decoration:none;">
            <div style="font-size:1.2rem;font-weight:700;color:var(--brand-600);">{{ open_orders_aantal }} →</div>
        </a>
        <div style="font-size:11px;color:var(--gray-400);">{% if open_orders_ton %}{{ open_orders_ton }} t deze periode{% else %}&nbsp;{% endif %}</div>
    </div>
    <div style="flex:1;padding:14px 20px;border-right:1px solid var(--gray-200);">
        <div style="font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Laatste contact</div>
        <div style="font-size:1.2rem;font-weight:700;color:var(--gray-800);">{{ laatst_contact_profiel|default('—',true) }}</div>
        <div style="font-size:11px;color:var(--gray-400);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ bedrijf.accountmanager|default('',true) }}{% if bedrijf.telefoon %}, telefoon{% endif %}</div>
    </div>
    <div style="flex:1;padding:14px 20px;">
        <div style="font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:var(--gray-400);">Afstand tot Alblasserdam</div>
        <div style="font-size:1.2rem;font-weight:700;color:var(--gray-800);">{% if afstand_alblasserdam %}{{ afstand_alblasserdam }} km{% else %}—{% endif %}</div>
        <div style="font-size:11px;color:var(--gray-400);">{{ bedrijf.regio }}, {{ bedrijf.land }}</div>
    </div>
</div>
{% endif %}

{% if materialen_volume_lijst %}
<div class="info-kaart" style="margin-bottom:16px;">
    <div class="dg-kaart-titel" style="color:var(--gray-400);margin-bottom:12px;">Materialen en volume</div>
    <div style="display:flex;font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:var(--gray-400);padding-bottom:8px;border-bottom:1px solid var(--gray-100);">
        <span style="flex:1.4;">Materiaal</span>
        <span style="width:100px;text-align:right;">T/jaar</span>
        <span style="width:160px;padding-left:16px;">Aandeel</span>
    </div>
    {% for m in materialen_volume_lijst %}
    <div style="display:flex;align-items:center;padding:10px 0;border-bottom:1px solid var(--gray-50);font-size:13px;">
        <span style="flex:1.4;font-weight:600;color:var(--gray-800);">{{ m.naam }}</span>
        <span style="width:100px;text-align:right;font-family:var(--font-mono);">{{ "{:,.0f}".format(m.volume) }}</span>
        <span style="width:160px;padding-left:16px;display:flex;align-items:center;gap:8px;">
            <span style="flex:1;height:5px;background:var(--gray-100);border-radius:5px;overflow:hidden;"><span style="display:block;height:100%;background:var(--brand-600);width:{{ m.aandeel }}%;"></span></span>
            <span style="font-size:11px;color:var(--gray-400);width:32px;text-align:right;">{{ m.aandeel }}%</span>
        </span>
    </div>
    {% endfor %}
</div>
{% endif %}

{% if inkoop_voortgang_lijst %}
<div class="info-kaart" style="margin-bottom:16px;">
    <div class="dg-kaart-titel" style="color:var(--gray-400);margin-bottom:12px;">Inkoop dit jaar t.o.v. jaarvolume</div>
    <div style="display:flex;font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:var(--gray-400);padding-bottom:8px;border-bottom:1px solid var(--gray-100);">
        <span style="flex:1.2;">Materiaal</span>
        <span style="width:90px;text-align:right;">Beschikbaar</span>
        <span style="width:90px;text-align:right;">Ingekocht</span>
        <span style="width:90px;text-align:right;">Nog te leveren</span>
        <span style="width:130px;padding-left:16px;">Voortgang</span>
    </div>
    {% for i in inkoop_voortgang_lijst %}
    <div style="padding:10px 0;border-bottom:1px solid var(--gray-50);font-size:13px;">
        <div style="display:flex;align-items:center;">
            <span style="flex:1.2;font-weight:600;color:var(--gray-800);">{{ i.naam }}</span>
            <span style="width:90px;text-align:right;font-family:var(--font-mono);">{{ "{:,.0f}".format(i.beschikbaar_jaar) }}t</span>
            <span style="width:90px;text-align:right;font-family:var(--font-mono);color:var(--brand-600);">{{ "{:,.0f}".format(i.ingekocht_dit_jaar) }}t</span>
            <span style="width:90px;text-align:right;font-family:var(--font-mono);color:{{ '#d97706' if i.nog_te_leveren else 'var(--gray-400)' }};">{{ "{:,.0f}".format(i.nog_te_leveren) }}t</span>
            <span style="width:130px;padding-left:16px;display:flex;align-items:center;gap:8px;">
                <span style="flex:1;height:5px;background:var(--gray-100);border-radius:5px;overflow:hidden;"><span style="display:block;height:100%;background:var(--brand-600);width:{{ i.pct_ingekocht }}%;"></span></span>
                <span style="font-size:11px;color:var(--gray-400);width:32px;text-align:right;">{{ i.pct_ingekocht }}%</span>
            </span>
        </div>
        <div style="font-size:11px;color:var(--gray-400);margin-top:3px;">nog {{ "{:,.0f}".format(i.restant_jaarvolume) }}t beschikbaar dit jaar</div>
    </div>
    {% endfor %}
</div>
{% endif %}


{% if recente_orders_profiel %}
<div class="info-kaart" style="margin-bottom:16px;">
    <div class="dg-kaart-titel" style="color:var(--gray-400);margin-bottom:12px;">Recente orders</div>
    <div style="display:flex;font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:var(--gray-400);padding-bottom:8px;border-bottom:1px solid var(--gray-100);">
        <span style="width:90px;">Referentie</span>
        <span style="flex:1;">Materiaal</span>
        <span style="width:110px;">Datum</span>
        <span style="width:80px;text-align:right;">Besteld</span>
        <span style="width:100px;text-align:right;">Status</span>
    </div>
    {% for o in recente_orders_profiel %}
    <div style="padding:9px 0;border-bottom:1px solid var(--gray-50);font-size:13px;">
        <div style="display:flex;align-items:center;">
            <span style="width:90px;color:var(--gray-400);font-family:var(--font-mono);font-size:11.5px;">{{ o.referentie }}</span>
            <span style="flex:1;font-weight:600;color:var(--gray-800);">{{ o.materiaal }}</span>
            <span style="width:110px;color:var(--gray-400);">{{ o.datum }}</span>
            <span style="width:80px;text-align:right;font-family:var(--font-mono);">{{ o.hoeveelheid }}</span>
            <span style="width:100px;text-align:right;font-weight:600;color:{{ '#16a34a' if o.status == 'Gewonnen' else ('#dc2626' if o.status == 'Verloren' else 'var(--brand-600)') }};">{{ o.status }}</span>
        </div>
        {% if o.heeft_levering_data %}
        <div style="display:flex;align-items:center;gap:10px;margin-top:6px;padding-left:90px;">
            <span style="flex:1;height:5px;background:var(--gray-100);border-radius:5px;overflow:hidden;"><span style="display:block;height:100%;background:{{ '#16a34a' if o.openstaand_order == 0 else 'var(--brand-600)' }};width:{{ o.geleverd_pct }}%;"></span></span>
            <span style="font-size:11px;color:var(--gray-400);white-space:nowrap;">{{ "{:,.0f}".format(o.geleverd_order) }}t geleverd{% if o.openstaand_order > 0 %} · {{ "{:,.0f}".format(o.openstaand_order) }}t openstaand{% endif %}</span>
        </div>
        {% endif %}
    </div>
    {% endfor %}
    <a href="{{ '/handelsorders/nieuw/verkoop?klant=' if is_fabriek_profiel else '/handelsorders/nieuw/inkoop?leverancier=' }}{{ bedrijf.naam|urlencode }}" style="display:block;margin-top:10px;font-size:0.78rem;color:var(--brand-600);text-decoration:none;font-weight:600;">+ Order toevoegen voor {{ bedrijf.naam }} →</a>
</div>
{% endif %}

<div class="profiel-grid">
    <div>
        <div class="info-kaart" style="margin-bottom:16px;">
    <div class="dg-kaart-titel" style="color:var(--gray-400);">Bedrijfsgegevens</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px 24px;">
        <div>
            <div class="veld-label">Status</div>
            <select id="statusSelect" onchange="wijzigStatusProfiel()" class="klik-bewerken-veld">
                <option value="" {% if not status %}selected{% endif %}>Geen status</option>
                <option value="klant" {% if status=='klant' %}selected{% endif %}>🟢 Klant</option>
                <option value="potentie" {% if status=='potentie' %}selected{% endif %}>🟡 Potentie</option>
                <option value="in_proces" {% if status=='in_proces' %}selected{% endif %}>🔵 In Proces</option>
                <option value="geen_interesse" {% if status=='geen_interesse' %}selected{% endif %}>⚪ Geen Interesse</option>
            </select>
        </div>
        <div>
            <div class="veld-label">Accountmanager</div>
            <select id="accountmanagerSelect" onchange="wijzigAccountmanagerProfiel()" class="klik-bewerken-veld">
                <option value="" {% if not accountmanager %}selected{% endif %}>Niet toegewezen</option>
                {% for gebruikersnaam in alle_gebruikersnamen %}
                <option value="{{ gebruikersnaam }}" {% if accountmanager == gebruikersnaam %}selected{% endif %}>{{ gebruikersnaam }}</option>
                {% endfor %}
            </select>
        </div>
        <div>
            <div class="veld-label">Bedrijfstype</div>
            <input type="text" value="{{ bedrijf.brontype or '' }}" data-veld="brontype" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld">
        </div>
        <div>
            <div class="veld-label">Klanttype</div>
            <input type="text" value="{{ bedrijf.klanttype or '' }}" data-veld="klanttype" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld">
        </div>
        <div>
            <div class="veld-label">Certificering</div>
            <input type="text" value="{{ bedrijf.certificeringen or '' }}" data-veld="certificeringen" onblur="wijzigBedrijfVeld(this)" placeholder="bv. ISO 9001, FSC..." class="klik-bewerken-veld">
        </div>
        <div>
            <div class="veld-label">Contactpersoon</div>
            <input type="text" value="{{ bedrijf.contactpersoon or '' }}" data-veld="contactpersoon" onblur="wijzigBedrijfVeld(this)" placeholder="Naam invullen..." class="klik-bewerken-veld">
            <a href="/contacten/nieuw/bestaand?bedrijf={{ bedrijf.naam|urlencode }}" style="display:inline-block;margin-top:4px;font-size:11px;color:var(--brand-600);text-decoration:none;">+ Extra contactpersoon →</a>
        </div>
        <div>
            <div class="veld-label">Adres hoofdvestiging</div>
            <input type="text" value="{{ bedrijf.adres or '' }}" data-veld="adres" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld">
        </div>
        <div>
            <div class="veld-label">Telefoon</div>
            <input type="text" value="{{ bedrijf.telefoon or '' }}" data-veld="telefoon" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld">
        </div>
        <div>
            <div class="veld-label">Betalingstermijn</div>
            <input type="text" value="{{ bedrijf.betalingstermijn or '' }}" data-veld="betalingstermijn" onblur="wijzigBedrijfVeld(this)" placeholder="bv. 30 dagen" class="klik-bewerken-veld">
        </div>
    </div>
    <div style="margin-top:10px;font-size:13px;">
        <span id="echteWebsiteWrap" style="display:none;">🌐 <a id="echteWebsiteLink" href="#" target="_blank" style="color:var(--brand-600);font-weight:600;text-decoration:none;"></a></span>
    </div>

    {% if not is_fabriek_profiel %}
    <div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--gray-100);">
        <div class="veld-label" style="margin-bottom:8px;">Afhaallocaties</div>
        {% for loc in afhaallocaties %}
        <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;font-size:13px;color:var(--gray-700);border-bottom:1px solid var(--gray-100);">
            <span>{{ loc.naam or loc.stad }} — {{ loc.adres }}, {{ loc.postcode }} {{ loc.stad }}, {{ loc.land }}{% if not loc.lat %} <span style="color:var(--gray-300);font-size:11px;">(niet op kaart — adres kon niet gevonden worden)</span>{% endif %}</span>
        </div>
        {% endfor %}
        <button type="button" onclick="document.getElementById('afhaalToevoegForm').style.display='block';this.style.display='none';" id="afhaalPlusBtn" style="margin-top:8px;font-size:12px;font-weight:600;color:var(--brand-600);background:none;border:none;cursor:pointer;padding:0;">+ Afhaallocatie toevoegen</button>
        <form id="afhaalToevoegForm" method="POST" action="/leverancier/{{ bedrijf.naam|urlencode }}/commercieel" style="display:none;margin-top:10px;max-width:420px;">
            <input type="hidden" name="actie" value="locatie_toevoegen">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
                <input type="text" name="locatie_naam" placeholder="Naam (optioneel)" style="padding:6px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
                <input type="text" name="land" placeholder="Land" style="padding:6px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
            </div>
            <input type="text" name="adres" placeholder="Adres *" required style="width:100%;padding:6px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;margin-bottom:8px;box-sizing:border-box;">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;">
                <input type="text" name="postcode" placeholder="Postcode" style="padding:6px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
                <input type="text" name="stad" placeholder="Stad *" required style="padding:6px 8px;border:1px solid var(--gray-200);border-radius:6px;font-size:12.5px;font-family:inherit;">
            </div>
            <button type="submit" style="padding:6px 14px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;">Toevoegen</button>
        </form>
    </div>
    {% endif %}
    <div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--gray-100);">
        <button type="button" onclick="toggleMeerInfo()" id="meerInfoToggleBtn" style="font-size:12px;font-weight:600;color:var(--brand-600);background:none;border:none;cursor:pointer;padding:0;">+ Meer informatie (bank, VAT, contact per afdeling)</button>
        <div id="meerInfoPaneel" style="display:none;margin-top:12px;">
            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:8px;">Algemeen</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px 24px;margin-bottom:16px;">
                <div><div class="veld-label">Postcode</div><input type="text" value="{{ bedrijf.postcode or '' }}" data-veld="postcode" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">Stad</div><input type="text" value="{{ bedrijf.stad or bedrijf.regio or '' }}" data-veld="stad" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">Algemeen e-mailadres</div><input type="text" value="{{ bedrijf.email_algemeen or '' }}" data-veld="email_algemeen" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">KvK-nummer</div><input type="text" value="{{ bedrijf.kvk_nummer or '' }}" data-veld="kvk_nummer" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
            </div>

            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:8px;">Financieel</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px 24px;margin-bottom:16px;">
                <div><div class="veld-label">Naam bank</div><input type="text" value="{{ bedrijf.bank_naam or '' }}" data-veld="bank_naam" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">Begunstigde</div><input type="text" value="{{ bedrijf.begunstigde or '' }}" data-veld="begunstigde" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">Bankadres</div><input type="text" value="{{ bedrijf.bank_adres or '' }}" data-veld="bank_adres" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">SWIFT / BIC-code</div><input type="text" value="{{ bedrijf.swift_bic or '' }}" data-veld="swift_bic" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">IBAN (EUR)</div><input type="text" value="{{ bedrijf.iban_eur or '' }}" data-veld="iban_eur" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">IBAN (USD)</div><input type="text" value="{{ bedrijf.iban_usd or '' }}" data-veld="iban_usd" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">IBAN (GBP)</div><input type="text" value="{{ bedrijf.iban_gbp or '' }}" data-veld="iban_gbp" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">VAT / BTW-nummer</div><input type="text" value="{{ bedrijf.vat_nummer or '' }}" data-veld="vat_nummer" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">Bankgegevens (overig)</div><input type="text" value="{{ bedrijf.bankgegevens or '' }}" data-veld="bankgegevens" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
            </div>

            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:8px;">Facturatie</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px 24px;margin-bottom:16px;">
                <div><div class="veld-label">E-mail voor facturatie</div><input type="text" value="{{ bedrijf.factuur_email or '' }}" data-veld="factuur_email" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">Contactpersoon facturatie</div><input type="text" value="{{ bedrijf.factuur_contactpersoon or '' }}" data-veld="factuur_contactpersoon" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">E-mail vragen over betalingen</div><input type="text" value="{{ bedrijf.vragen_betalingen_email or '' }}" data-veld="vragen_betalingen_email" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">E-mail sales-facturatie</div><input type="text" value="{{ bedrijf.sales_facturatie_email or '' }}" data-veld="sales_facturatie_email" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
            </div>

            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:8px;">Contact per afdeling</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px 24px;margin-bottom:16px;">
                <div><div class="veld-label">E-mail logistiek</div><input type="text" value="{{ bedrijf.email_logistiek or '' }}" data-veld="email_logistiek" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">E-mail finance</div><input type="text" value="{{ bedrijf.email_finance or '' }}" data-veld="email_finance" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
                <div><div class="veld-label">E-mail sales</div><input type="text" value="{{ bedrijf.email_sales or '' }}" data-veld="email_sales" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld"></div>
            </div>

            {% if bedrijf.overige_contacten %}
            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:8px;">Overige contacten</div>
            <table style="width:100%;border-collapse:collapse;margin-bottom:16px;font-size:12.5px;">
                <thead><tr style="text-align:left;color:var(--gray-400);font-size:10px;text-transform:uppercase;border-bottom:1px solid var(--gray-100);">
                    <th style="padding:4px 6px;">Afdeling</th><th style="padding:4px 6px;">Naam</th><th style="padding:4px 6px;">E-mail</th><th style="padding:4px 6px;">Telefoon</th><th style="padding:4px 6px;">Functie</th>
                </tr></thead>
                <tbody>
                {% for c in bedrijf.overige_contacten %}
                <tr style="border-bottom:1px solid var(--gray-50);">
                    <td style="padding:6px;color:var(--gray-700);">{{ c.afdeling|default('—',true) }}</td>
                    <td style="padding:6px;color:var(--gray-800);font-weight:600;">{{ c.naam|default('—',true) }}</td>
                    <td style="padding:6px;color:var(--gray-600);">{{ c.email|default('—',true) }}</td>
                    <td style="padding:6px;color:var(--gray-600);">{{ c.telefoon|default('—',true) }}</td>
                    <td style="padding:6px;color:var(--gray-600);">{{ c.functie|default('—',true) }}</td>
                </tr>
                {% endfor %}
                </tbody>
            </table>
            {% endif %}

            {% if bedrijf.depot_adressen %}
            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:8px;">Depot-adressen</div>
            <table style="width:100%;border-collapse:collapse;margin-bottom:16px;font-size:12.5px;">
                <thead><tr style="text-align:left;color:var(--gray-400);font-size:10px;text-transform:uppercase;border-bottom:1px solid var(--gray-100);">
                    <th style="padding:4px 6px;">Naam</th><th style="padding:4px 6px;">Adres</th><th style="padding:4px 6px;">Telefoon</th><th style="padding:4px 6px;">E-mail</th><th style="padding:4px 6px;">Openingsuren</th><th style="padding:4px 6px;">Overig</th>
                </tr></thead>
                <tbody>
                {% for d in bedrijf.depot_adressen %}
                <tr style="border-bottom:1px solid var(--gray-50);">
                    <td style="padding:6px;color:var(--gray-800);font-weight:600;">{{ d.naam|default('—',true) }}</td>
                    <td style="padding:6px;color:var(--gray-600);">{{ d.adres|default('—',true) }}</td>
                    <td style="padding:6px;color:var(--gray-600);">{{ d.telefoon|default('—',true) }}</td>
                    <td style="padding:6px;color:var(--gray-600);">{{ d.email|default('—',true) }}</td>
                    <td style="padding:6px;color:var(--gray-600);">{{ d.openingsuren|default('—',true) }}</td>
                    <td style="padding:6px;color:var(--gray-600);">{{ d.overig|default('—',true) }}</td>
                </tr>
                {% endfor %}
                </tbody>
            </table>
            {% endif %}

            <div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin-bottom:8px;">Overig</div>
            <div class="veld-label">Overige informatie</div>
            <textarea data-veld="overige_informatie" onblur="wijzigBedrijfVeld(this)" placeholder="—" class="klik-bewerken-veld" style="min-height:56px;resize:vertical;">{{ bedrijf.overige_informatie or '' }}</textarea>
        </div>
    </div>
</div>

<div class="info-kaart" style="margin-bottom:16px;">
    <div style="display:flex;justify-content:space-between;align-items:center;">
        <div class="dg-kaart-titel" style="color:var(--gray-400);margin-bottom:0;">Materialen &amp; Kwaliteiten</div>
        <button type="button" onclick="toggleMaterialenBewerken()" id="materialenToggleBtn" style="font-size:12px;font-weight:600;color:var(--brand-600);background:none;border:none;cursor:pointer;">Bewerken</button>
    </div>
    <div id="materialenBewerkenPaneel" style="display:none;margin-top:12px;">
            {% set gekozen_materialen = (bedrijf.materialen or "").split(",") | map("trim") | list %}
            {% set gekozen_kwaliteiten = (bedrijf.kwaliteiten or "").split(",") | map("trim") | list %}
            {% for categorie, kwaliteiten_lijst in materiaal_taxonomie.items() %}
            <div style="padding:8px 0;border-bottom:1px solid var(--gray-50);">
                <label style="display:flex;align-items:center;gap:8px;font-weight:600;font-size:13px;color:var(--gray-700);cursor:pointer;">
                    <input type="checkbox" class="materiaal-checkbox" data-categorie="{{ categorie }}" {% if categorie in gekozen_materialen %}checked{% endif %} onchange="wijzigMateriaalCheckbox()">
                    {{ categorie }}
                </label>
                {% if kwaliteiten_lijst %}
                <div style="margin-left:24px;margin-top:6px;display:flex;flex-wrap:wrap;gap:10px;">
                    {% for kw in kwaliteiten_lijst %}
                    <label style="display:flex;align-items:center;gap:5px;font-size:12px;color:var(--gray-500);cursor:pointer;">
                        <input type="checkbox" class="kwaliteit-checkbox" data-categorie="{{ categorie }}" value="{{ kw }}" {% if kw in gekozen_kwaliteiten %}checked{% endif %} onchange="wijzigKwaliteitCheckbox()">
                        {{ kw }}
                    </label>
                    {% endfor %}
                </div>
                {% endif %}
            </div>
            {% else %}
            <div style="font-size:0.8rem;color:var(--gray-300);">Nog geen materialen gedefinieerd. Ga naar Instellingen → Materialen beheren (admin).</div>
            {% endfor %}
    <div id="volumeRijenContainer"></div>
    </div>
</div>

{% if not is_fabriek_profiel %}
<div class="info-kaart" style="margin-bottom:16px;">
    <div class="dg-kaart-titel" style="color:var(--gray-400);margin-bottom:4px;">Financieel</div>
    <a href="/facturen?bedrijf={{ bedrijf.naam|urlencode }}" id="facturenSamenvattingLink" style="display:block;text-decoration:none;padding:4px 0;">
        <div id="facturenSamenvatting" style="font-size:1.2rem;font-weight:700;color:var(--brand-600);">Laden...</div>
        <div style="font-size:11px;color:var(--gray-400);margin-top:2px;">Bekijk alle facturen →</div>
    </a>
</div>

<div class="info-kaart" style="margin-bottom:16px;">
    <div class="dg-kaart-titel" style="color:var(--gray-400);">Documenten</div>
    <div id="documentenLijst" style="margin-bottom:10px;"></div>
    <label style="display:inline-block;padding:6px 12px;background:var(--gray-100);color:var(--gray-700);border-radius:6px;cursor:pointer;font-size:12.5px;font-weight:600;">
        📄 Document uploaden (PDF/Word)
        <input type="file" id="documentInput" accept=".pdf,.doc,.docx" onchange="uploadDocumentProfiel()" style="display:none;">
    </label>
</div>
{% endif %}

        {% if bedrijf_shipments %}
        <div class="info-kaart" style="margin-bottom:16px;">
            <div class="dg-kaart-titel" style="color:var(--gray-400);">Shipments</div>
                {% for s in bedrijf_shipments %}
                <div class="dg-activiteit-item">
                    {{ s.referentie or s.id[:8] }} · {{ s.materiaal }} · {{ s.origin_land }} → {{ s.destination_land }}
                    <span style="color:{{ '#16a34a' if s.status in ('Delivered','Received') else 'var(--gray-500)' }};font-weight:700;"> · {{ s.status }}</span>
                    <small>{{ s.datum }}{% if s.werkelijk_hoeveelheid %} · {{ s.werkelijk_hoeveelheid }} ton (gewogen){% elif s.gepland_hoeveelheid %} · {{ s.gepland_hoeveelheid }} ton (gepland){% endif %}</small>
                </div>
                {% endfor %}
            <a href="/voorraad" style="display:block;margin-top:8px;font-size:0.78rem;color:var(--brand-600);text-decoration:none;font-weight:600;">Naar Voorraad →</a>
        </div>
        {% endif %}

        <div class="info-kaart" style="margin-bottom:16px;">
            <div class="dg-kaart-titel" style="color:var(--gray-400);">Foto's</div>
            <div id="fotoCategorieTabs" style="display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap;"></div>
            <div id="fotoBreadcrumb" style="font-size:0.78rem;color:var(--gray-400);margin-bottom:10px;"></div>
            <div id="fotoMappenGrid" style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;"></div>
            <div id="fotoGrid" style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;"></div>
            <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;">
                <input type="text" id="nieuweMapNaam" placeholder="Nieuwe map (bv. kwaliteit A)..." style="flex:1;padding:6px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;font-family:inherit;">
                <button onclick="maakFotoSubmapProfiel()" style="padding:6px 12px;background:var(--gray-100);color:var(--gray-700);border:none;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;">+ Map</button>
            </div>
            <label style="display:inline-block;padding:6px 12px;background:var(--brand-600);color:#fff;border-radius:6px;cursor:pointer;font-size:13px;font-weight:600;">
                📷 Foto uploaden
                <input type="file" id="fotoInputProfiel" accept="image/*" onchange="uploadFotoProfiel()" style="display:none;">
            </label>
        </div>
    </div>

    <div>
        <div class="info-kaart">
            <div id="profielKaart" style="height:200px;border-radius:10px;overflow:hidden;"></div>
        </div>

        {% if fabrieken_gedeelde_kwaliteiten %}
        <div class="info-kaart" style="margin-top:16px;">
            <div class="dg-kaart-titel" style="color:var(--gray-400);">{{ matchpoel_label }}</div>
            {% for f in fabrieken_gedeelde_kwaliteiten %}
            <a href="/bedrijf/{{ f.naam|urlencode }}" style="display:block;padding:10px 0;border-bottom:1px solid var(--gray-50);text-decoration:none;color:inherit;">
                <div style="display:flex;justify-content:space-between;align-items:baseline;">
                    <b style="font-size:13px;color:var(--gray-800);">{{ f.naam }}</b>
                    {% if f.afstand %}<span style="font-size:11.5px;color:var(--brand-600);font-family:var(--font-mono);">{{ f.afstand }} km</span>{% endif %}
                </div>
                <div style="font-size:11.5px;color:var(--gray-400);margin-top:2px;">{{ f.regio }}, {{ f.land }} · match op {{ f.gedeelde_kwaliteiten }}</div>
            </a>
            {% endfor %}
        </div>
        {% endif %}

        {% if is_fabriek_profiel %}
        <div class="info-kaart" style="margin-top:16px;">
            <div class="dg-kaart-titel" style="color:var(--gray-400);">Leveranciers die leveren</div>
            {% if actieve_leveranciers %}
            {% for l in actieve_leveranciers %}
            <a href="/bedrijf/{{ l.naam|urlencode }}" style="display:block;padding:10px 0;border-bottom:1px solid var(--gray-50);text-decoration:none;color:inherit;">
                <div style="display:flex;justify-content:space-between;align-items:baseline;">
                    <b style="font-size:13px;color:var(--gray-800);">{{ l.naam }}</b>
                    {% if l.totaal_volume %}<span style="font-size:11.5px;color:var(--brand-600);font-family:var(--font-mono);">{{ "{:,.0f}".format(l.totaal_volume) }} t</span>{% endif %}
                </div>
                <div style="font-size:11.5px;color:var(--gray-400);margin-top:2px;">{{ l.land }} · {{ l.aantal_shipments }} shipment{{ 's' if l.aantal_shipments != 1 else '' }}{% if l.laatste_datum %} · laatst {{ l.laatste_datum }}{% endif %}</div>
            </a>
            {% endfor %}
            {% else %}
            <div style="font-size:13px;color:var(--gray-400);">Nog geen leveranties geregistreerd (via Voorraad-shipments).</div>
            {% endif %}
        </div>
        {% else %}
        <div class="info-kaart" style="margin-top:16px;">
            <div class="dg-kaart-titel" style="color:var(--gray-400);">Waar het naartoe gaat</div>
            {% if bestemmingen_lijst %}
            {% for b in bestemmingen_lijst %}
            <div style="padding:10px 0;border-bottom:1px solid var(--gray-50);">
                <div style="display:flex;justify-content:space-between;align-items:baseline;">
                    <b style="font-size:13px;color:var(--gray-800);">{{ b.naam or "Onbekende bestemming" }}{% if b.naam and b.land %}, {% endif %}{{ b.land }}</b>
                    {% if b.totaal_volume %}<span style="font-size:11.5px;color:var(--brand-600);font-family:var(--font-mono);">{{ "{:,.0f}".format(b.totaal_volume) }} t</span>{% endif %}
                </div>
                <div style="font-size:11.5px;color:var(--gray-400);margin-top:2px;">{{ b.aantal_shipments }} shipment{{ 's' if b.aantal_shipments != 1 else '' }}{% if b.laatste_datum %} · laatst {{ b.laatste_datum }}{% endif %}</div>
            </div>
            {% endfor %}
            {% else %}
            <div style="font-size:13px;color:var(--gray-400);">Nog geen vervolg-bestemmingen bekend — koppel een vervolg-shipment via Logistiek zodra dit materiaal wordt doorverscheept.</div>
            {% endif %}
        </div>
        {% endif %}

        <div class="info-kaart" style="margin-top:16px;">
            <div class="dg-kaart-titel" style="color:var(--gray-400);">Notities</div>
            <div id="notitiesLijst" style="margin-bottom:14px;"></div>
            <textarea id="notitieInput" placeholder="Schrijf een notitie..." style="width:100%;min-height:56px;padding:8px 10px;border:1px solid var(--gray-200);border-radius:6px;font-family:inherit;font-size:13px;color:var(--gray-700);resize:vertical;box-sizing:border-box;"></textarea>
            <div style="display:flex;align-items:center;gap:16px;margin-top:10px;">
                <label style="font-size:12.5px;color:var(--gray-600);display:flex;align-items:center;gap:5px;cursor:pointer;"><input type="radio" name="notitieType" value="team" checked> Team</label>
                <label style="font-size:12.5px;color:var(--gray-600);display:flex;align-items:center;gap:5px;cursor:pointer;"><input type="radio" name="notitieType" value="prive"> Privé</label>
                <button onclick="voegNotitieToeProfiel()" style="margin-left:auto;padding:6px 16px;background:var(--brand-600);color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:12.5px;font-weight:600;">Toevoegen</button>
            </div>
        </div>
    </div>
</div>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
var BEDRIJF_NAAM = {{ (bedrijf.naam or "")|tojson }};
var HUIDIGE_GEBRUIKER = {{ (gebruikersnaam or "")|tojson }};
var MATERIAAL_TAXONOMIE = {{ materiaal_taxonomie|tojson }};
var BEDRIJF_MATERIAAL_VOLUMES = {{ (bedrijf.get('materiaal_volumes', {}))|tojson }};
var BEDRIJF_URL = {{ (bedrijf.url or "")|tojson }};
var pKaart = L.map("profielKaart", {zoomControl:true}).setView([{{ bedrijf.lat or 20 }}, {{ bedrijf.lon or 0 }}], {{ 12 if bedrijf.lat else 2 }});
L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {attribution:"© OpenStreetMap, © CARTO", subdomains:"abcd", maxZoom:19}).addTo(pKaart);
var pMarker = null;
{% if bedrijf.lat and bedrijf.lon %}
pMarker = L.marker([{{ bedrijf.lat }}, {{ bedrijf.lon }}]).addTo(pKaart).bindPopup({{ bedrijf.naam|tojson }} + " (hoofdvestiging)");
{% endif %}
var afhaalMarkers = [];
{% for loc in afhaallocaties %}
{% if loc.lat and loc.lon %}
afhaalMarkers.push(L.marker([{{ loc.lat }}, {{ loc.lon }}], {icon: L.divIcon({className:"", html:'<div style="background:#f59e0b;width:12px;height:12px;border-radius:50%;border:2px solid #fff;box-shadow:0 0 0 1px #f59e0b;"></div>', iconSize:[12,12]})}).addTo(pKaart).bindPopup({{ (loc.naam or loc.stad)|tojson }} + " (afhaallocatie)"));
{% endif %}
{% endfor %}

function vulContact(data) {
    var telInput = document.querySelector('[data-veld="telefoon"]');
    var adrInput = document.querySelector('[data-veld="adres"]');
    if (telInput && !telInput.value && data.telefoon) telInput.value = data.telefoon;
    if (adrInput && !adrInput.value && data.adres) adrInput.value = data.adres;
    if (data.website) {
        var wrap = document.getElementById("echteWebsiteWrap");
        var link = document.getElementById("echteWebsiteLink");
        if (wrap && link) {
            link.href = data.website;
            link.textContent = data.website.replace("https://", "").replace("http://", "").split("/")[0];
            wrap.style.display = "inline";
        }
    }
}

if (BEDRIJF_URL) {
    fetch("/details?url=" + encodeURIComponent(BEDRIJF_URL)).then(r => r.json()).then(vulContact);
} else {
    vulContact({});
}

function toggleMeerInfo() {
    var paneel = document.getElementById("meerInfoPaneel");
    var knop = document.getElementById("meerInfoToggleBtn");
    var isOpen = paneel.style.display !== "none";
    paneel.style.display = isOpen ? "none" : "block";
    knop.textContent = isOpen ? "+ Meer informatie (bank, VAT, contact per afdeling)" : "− Meer informatie verbergen";
}

async function laadNotities() {
    const res = await fetch("/api/notities?bedrijf=" + encodeURIComponent(BEDRIJF_NAAM));
    const notities = await res.json();
    const div = document.getElementById("notitiesLijst");
    if (notities.length === 0) { div.innerHTML = "<p style='font-size:13px;color:var(--gray-400);'>Nog geen notities.</p>"; return; }
    let html = "";
    notities.forEach(n => {
        const badgeAchtergrond = n.type === "team" ? "var(--brand-50)" : "var(--gray-100)";
        const badgeKleur = n.type === "team" ? "var(--brand-600)" : "var(--gray-500)";
        const badge = n.type === "team" ? "Team" : "Privé";
        html += `<div style="padding:10px 0;border-bottom:1px solid var(--gray-100);font-size:13px;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
                <div style="color:var(--gray-700);">${n.tekst}</div>
                <button onclick="verwijderNotitieProfiel('${n.id}')" title="Verwijderen" style="background:none;border:none;color:var(--gray-300);cursor:pointer;font-size:12px;flex-shrink:0;">✕</button>
            </div>
            <div style="margin-top:5px;display:flex;align-items:center;gap:7px;">
                <span style="font-size:10px;font-weight:700;padding:1px 8px;border-radius:8px;background:${badgeAchtergrond};color:${badgeKleur};">${badge}</span>
                <span style="color:var(--gray-400);font-size:11px;">${n.timestamp}</span>
            </div>
        </div>`;
    });
    div.innerHTML = html;
}
async function verwijderNotitieProfiel(id) {
    if (!confirm("Deze notitie verwijderen?")) return;
    const res = await fetch("/api/notities", {method:"DELETE", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, id: id})});
    const data = await res.json();
    if (data.error) { alert(data.error); } else { laadNotities(); }
}
async function voegNotitieToeProfiel() {
    const input = document.getElementById("notitieInput");
    const tekst = input.value.trim();
    if (!tekst) return;
    const type_ = document.querySelector('input[name="notitieType"]:checked').value;
    await fetch("/api/notities", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, tekst: tekst, type: type_})});
    input.value = "";
    laadNotities();
}
async function wijzigStatusProfiel() {
    const select = document.getElementById("statusSelect");
    await fetch("/api/status", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, status: select.value})});
}
async function wijzigAccountmanagerProfiel() {
    const select = document.getElementById("accountmanagerSelect");
    await fetch("/api/accountmanager", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, accountmanager: select.value})});
}
async function wijzigBedrijfVeld(input) {
    const veld = input.dataset.veld;
    const origineel = input.dataset.origineel !== undefined ? input.dataset.origineel : input.defaultValue;
    if (input.value === origineel) return;
    input.style.opacity = "0.5";
    try {
        const res = await fetch("/api/bedrijf-veld", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, veld: veld, waarde: input.value})});
        const data = await res.json();
        input.dataset.origineel = input.value;
        if (veld === "adres" && data.lat && data.lon) {
            if (pMarker) {
                pMarker.setLatLng([data.lat, data.lon]);
            } else {
                pMarker = L.marker([data.lat, data.lon]).addTo(pKaart).bindPopup(BEDRIJF_NAAM + " (hoofdvestiging)");
            }
            pKaart.setView([data.lat, data.lon], 12);
        }
    } finally {
        input.style.opacity = "1";
    }
}
async function wijzigMateriaalCheckbox() {
    const aangevinkt = Array.from(document.querySelectorAll(".materiaal-checkbox:checked")).map(el => el.dataset.categorie);
    herbouwVolumeRijen();
    await fetch("/api/bedrijf-veld", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, veld: "materialen", waarde: aangevinkt.join(", ")})});
}
async function wijzigKwaliteitCheckbox() {
    const aangevinkt = Array.from(document.querySelectorAll(".kwaliteit-checkbox:checked")).map(el => el.value);
    herbouwVolumeRijen();
    await fetch("/api/bedrijf-veld", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, veld: "kwaliteiten", waarde: aangevinkt.join(", ")})});
}
async function wijzigMateriaalVolume(input) {
    const materiaal = input.dataset.materiaal;
    const origineel = input.dataset.origineel !== undefined ? input.dataset.origineel : input.defaultValue;
    if (input.value === origineel) return;
    BEDRIJF_MATERIAAL_VOLUMES[materiaal] = input.value;
    input.style.opacity = "0.5";
    try {
        await fetch("/api/materiaal-volume", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, materiaal: materiaal, volume: input.value})});
        input.dataset.origineel = input.value;
    } finally {
        input.style.opacity = "1";
    }
}
function toggleMaterialenBewerken() {
    var paneel = document.getElementById("materialenBewerkenPaneel");
    var knop = document.getElementById("materialenToggleBtn");
    var isOpen = paneel.style.display !== "none";
    paneel.style.display = isOpen ? "none" : "block";
    knop.textContent = isOpen ? "Bewerken" : "Sluiten";
}

function herbouwVolumeRijen() {
    const container = document.getElementById("volumeRijenContainer");
    if (!container) return;
    const aangevinkteMaterialen = Array.from(document.querySelectorAll(".materiaal-checkbox:checked")).map(el => el.dataset.categorie);
    const aangevinkteKwaliteiten = Array.from(document.querySelectorAll(".kwaliteit-checkbox:checked")).map(el => ({categorie: el.dataset.categorie, naam: el.value}));

    let regels = [];
    aangevinkteMaterialen.forEach(cat => {
        const kwaliteitenOnderCat = aangevinkteKwaliteiten.filter(k => k.categorie === cat);
        if (kwaliteitenOnderCat.length > 0) {
            kwaliteitenOnderCat.forEach(k => regels.push(k.naam));
        } else {
            regels.push(cat);
        }
    });

    if (regels.length === 0) {
        container.innerHTML = "";
        return;
    }

    let html = '<div style="font-size:10.5px;font-weight:700;color:var(--gray-300);text-transform:uppercase;letter-spacing:0.6px;margin:10px 0 8px;">Volume per kwaliteit (t/jaar)</div>';
    regels.forEach(naam => {
        const waarde = BEDRIJF_MATERIAAL_VOLUMES[naam] || "";
        const veiligeNaam = naam.replace(/"/g, "&quot;");
        html += `<div class="drawer-row">
            <span class="drawer-row-label">${naam}</span>
            <span class="drawer-row-value">
                <input type="text" value="${waarde}" data-materiaal="${veiligeNaam}" onblur="wijzigMateriaalVolume(this)" placeholder="0" style="width:90px;padding:4px 8px;border:1px solid #e2e8f0;border-radius:6px;font-size:13px;text-align:right;font-family:inherit;">
            </span>
        </div>`;
    });
    container.innerHTML = html;
}
async function toggleOpslaanProfiel(el) {
    const res = await fetch("/api/opgeslagen", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({naam: BEDRIJF_NAAM})});
    const data = await res.json();
    el.textContent = data.opgeslagen ? "★" : "☆";
    el.classList.toggle("opgeslagen", data.opgeslagen);
}
laadNotities();

async function laadFacturen() {
    const samenvattingDiv = document.getElementById("facturenSamenvatting");
    if (!samenvattingDiv) return;
    samenvattingDiv.textContent = "Laden...";
    try {
        const res = await fetch("/api/facturen?bedrijf=" + encodeURIComponent(BEDRIJF_NAAM));
        const facturen = await res.json();
        const openstaand = facturen.filter(f => f.status !== "Betaald");
        const teLaat = facturen.filter(f => f.status === "Te laat");
        const totaalOpenstaand = openstaand.reduce((som, f) => som + (parseFloat(String(f.bedrag).replace(",", ".")) || 0), 0);
        if (facturen.length === 0) {
            samenvattingDiv.textContent = "0";
        } else {
            samenvattingDiv.innerHTML = `${openstaand.length}<span style="font-size:0.7rem;font-weight:600;color:var(--gray-300);"> openstaand</span>`;
            const subDiv = samenvattingDiv.parentElement.querySelector("div:last-child");
            if (subDiv) subDiv.textContent = `€${totaalOpenstaand.toLocaleString("nl-NL", {maximumFractionDigits:0})} · ${teLaat.length} te laat — Bekijk alle facturen →`;
        }
    } catch (err) {
        samenvattingDiv.textContent = "—";
    }
}

async function laadDocumentenProfiel() {
    const lijstDiv = document.getElementById("documentenLijst");
    if (!lijstDiv) return;
    lijstDiv.innerHTML = "<p style='font-size:13px;color:#94a3b8;'>Laden...</p>";
    try {
        const res = await fetch("/api/documenten?bedrijf=" + encodeURIComponent(BEDRIJF_NAAM));
        const documenten = await res.json();
        if (documenten.length === 0) {
            lijstDiv.innerHTML = "<p style='font-size:13px;color:#94a3b8;'>Nog geen documenten geupload.</p>";
            return;
        }
        let html = "";
        documenten.forEach(d => {
            html += `
                <div style="display:flex;justify-content:space-between;align-items:center;padding:7px 0;border-bottom:1px solid #f1f5f9;font-size:13px;">
                    <span style="color:#1e293b;">📄 ${d.originele_naam}<br><small style="color:#94a3b8;">${d.timestamp} · ${d.geupload_door}</small></span>
                    <span style="display:flex;gap:8px;align-items:center;">
                        <a href="/documenten_uploads/${d.bestandsnaam}" style="font-size:11.5px;font-weight:600;color:var(--brand-600);text-decoration:none;">Download</a>
                        <button onclick="verwijderDocumentProfiel('${d.bestandsnaam}')" title="Verwijderen" style="background:none;border:none;color:#cbd5e1;cursor:pointer;font-size:12px;">✕</button>
                    </span>
                </div>`;
        });
        lijstDiv.innerHTML = html;
    } catch (err) {
        lijstDiv.innerHTML = "<p style='font-size:13px;color:#ef4444;'>Kon documenten niet laden.</p>";
    }
}

async function uploadDocumentProfiel() {
    const input = document.getElementById("documentInput");
    const bestand = input.files[0];
    if (!bestand) return;
    const formData = new FormData();
    formData.append("bedrijf", BEDRIJF_NAAM);
    formData.append("document", bestand);
    const res = await fetch("/api/documenten", {method: "POST", body: formData});
    const data = await res.json();
    if (data.error) { alert(data.error); } else { laadDocumentenProfiel(); }
    input.value = "";
}

async function verwijderDocumentProfiel(bestandsnaam) {
    if (!confirm("Dit document verwijderen?")) return;
    const res = await fetch("/api/documenten", {method: "DELETE", headers: {"Content-Type": "application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, bestandsnaam: bestandsnaam})});
    const data = await res.json();
    if (data.error) { alert(data.error); } else { laadDocumentenProfiel(); }
}

if (!document.getElementById("isFabriekProfiel")) {
    laadFacturen();
    laadDocumentenProfiel();
}

const FOTO_STAAT = {categorie: "Algemeen", submap: ""};
const FOTO_CATEGORIEEN_LIJST = {{ (["Algemeen"] + materiaal_categorieen_lijst)|tojson }};

function initFotoBrowser() {
    const tabsDiv = document.getElementById("fotoCategorieTabs");
    if (!tabsDiv) return;
    tabsDiv.innerHTML = FOTO_CATEGORIEEN_LIJST.map(c =>
        `<button onclick="wisselFotoCategorieProfiel('${c}')" data-cat="${c}" style="padding:5px 12px;border-radius:6px;border:1px solid #e2e8f0;background:${c === FOTO_STAAT.categorie ? 'var(--brand-600)' : '#fff'};color:${c === FOTO_STAAT.categorie ? '#fff' : 'var(--gray-600)'};cursor:pointer;font-size:12px;font-weight:600;">${c}</button>`
    ).join("");
    laadFotoBrowser();
}

function wisselFotoCategorieProfiel(cat) {
    FOTO_STAAT.categorie = cat;
    FOTO_STAAT.submap = "";
    initFotoBrowser();
}

function openFotoSubmapProfiel(naam) {
    FOTO_STAAT.submap = naam;
    laadFotoBrowser();
}

function gaNaarFotoRootProfiel() {
    FOTO_STAAT.submap = "";
    laadFotoBrowser();
}

async function laadFotoBrowser() {
    const breadcrumb = document.getElementById("fotoBreadcrumb");
    const mappenGrid = document.getElementById("fotoMappenGrid");
    const fotoGrid = document.getElementById("fotoGrid");
    if (!breadcrumb) return;

    breadcrumb.innerHTML = FOTO_STAAT.submap
        ? `<a href="#" onclick="gaNaarFotoRootProfiel();return false;" style="color:var(--brand-600);text-decoration:none;">${FOTO_STAAT.categorie}</a> / ${FOTO_STAAT.submap}`
        : FOTO_STAAT.categorie;

    if (!FOTO_STAAT.submap) {
        const res = await fetch("/api/fotomappen?bedrijf=" + encodeURIComponent(BEDRIJF_NAAM) + "&categorie=" + encodeURIComponent(FOTO_STAAT.categorie));
        const mappen = await res.json();
        mappenGrid.innerHTML = mappen.map(m =>
            `<div onclick="openFotoSubmapProfiel('${m.replace(/'/g,"&#39;")}')" style="padding:8px 12px;background:var(--gray-50);border:1px solid #e2e8f0;border-radius:8px;cursor:pointer;font-size:12px;font-weight:600;color:var(--gray-700);">📁 ${m}</div>`
        ).join("");
    } else {
        mappenGrid.innerHTML = "";
    }

    const res2 = await fetch("/api/fotos?bedrijf=" + encodeURIComponent(BEDRIJF_NAAM) + "&categorie=" + encodeURIComponent(FOTO_STAAT.categorie) + "&submap=" + encodeURIComponent(FOTO_STAAT.submap));
    const fotos = await res2.json();
    fotoGrid.innerHTML = fotos.map(f =>
        `<div style="position:relative;width:70px;height:70px;">
            <img src="/fotos_uploads/${f.bestandsnaam}" style="width:70px;height:70px;object-fit:cover;border-radius:6px;border:1px solid #e2e8f0;cursor:pointer;" onclick="window.open('/fotos_uploads/${f.bestandsnaam}','_blank')" title="Door ${f.geupload_door} op ${f.timestamp}">
            <button onclick="verwijderFotoProfiel('${f.bestandsnaam}')" title="Verwijderen" style="position:absolute;top:-6px;right:-6px;width:18px;height:18px;border-radius:50%;background:#ef4444;color:#fff;border:2px solid #fff;cursor:pointer;font-size:10px;line-height:1;padding:0;">✕</button>
        </div>`
    ).join("") || `<div style="font-size:0.78rem;color:var(--gray-300);">Nog geen foto's hier.</div>`;
}

async function verwijderFotoProfiel(bestandsnaam) {
    if (!confirm("Deze foto verwijderen?")) return;
    const res = await fetch("/api/fotos", {method:"DELETE", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, bestandsnaam: bestandsnaam})});
    const data = await res.json();
    if (data.error) { alert(data.error); } else { laadFotoBrowser(); }
}

async function maakFotoSubmapProfiel() {
    const input = document.getElementById("nieuweMapNaam");
    const naam = input.value.trim();
    if (!naam) return;
    await fetch("/api/fotomappen", {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({bedrijf: BEDRIJF_NAAM, categorie: FOTO_STAAT.categorie, submap: naam})});
    input.value = "";
    laadFotoBrowser();
}

async function uploadFotoProfiel() {
    const input = document.getElementById("fotoInputProfiel");
    const bestand = input.files[0];
    if (!bestand) return;
    const formData = new FormData();
    formData.append("bedrijf", BEDRIJF_NAAM);
    formData.append("categorie", FOTO_STAAT.categorie);
    formData.append("submap", FOTO_STAAT.submap);
    formData.append("foto", bestand);
    const res = await fetch("/api/fotos", {method:"POST", body: formData});
    const data = await res.json();
    if (data.error) { alert(data.error); } else { laadFotoBrowser(); }
    input.value = "";
}

initFotoBrowser();
herbouwVolumeRijen();
</script>
</div>
    """

    # --- Open orders + laatste contact (echte data, dezelfde logica als op de zoekpagina) ---
    _orders_alle_profiel = laad_orders()
    _orders_van_bedrijf = [o for o in _orders_alle_profiel if o.get("bedrijf","") == bedrijf["naam"]]
    open_orders_lijst = [o for o in _orders_van_bedrijf if o.get("status") in ("Open", "Onderhandeling")]
    open_orders_aantal = len(open_orders_lijst)
    open_orders_ton = round(sum(parse_hoeveelheid_getal(o.get("hoeveelheid","")) for o in open_orders_lijst))
    open_orders_ton = f"{open_orders_ton:,.0f}" if open_orders_ton else ""

    _notities_alle_profiel = laad_notities()
    laatst_contact_profiel = ""
    _laatste_datum_profiel = None
    for n in _notities_alle_profiel.get(bedrijf["naam"], []):
        try:
            dt = datetime.datetime.strptime(n.get("timestamp",""), "%d-%m-%Y %H:%M").date()
            if _laatste_datum_profiel is None or dt > _laatste_datum_profiel:
                _laatste_datum_profiel = dt
        except (ValueError, TypeError):
            continue
    if _laatste_datum_profiel:
        _dagen_geleden_profiel = (datetime.date.today() - _laatste_datum_profiel).days
        if _dagen_geleden_profiel <= 0:
            laatst_contact_profiel = "Vandaag"
        elif _dagen_geleden_profiel == 1:
            laatst_contact_profiel = "Gisteren"
        else:
            laatst_contact_profiel = f"{_dagen_geleden_profiel} dagen"

    # --- Afstand tot Alblasserdam (haversine, echte berekening) ---
    def _haversine_km(lat1, lon1, lat2, lon2):
        import math
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * 2 * math.asin(math.sqrt(a))
    ALBLASSERDAM_LAT, ALBLASSERDAM_LON = 51.868, 4.663
    afstand_alblasserdam = None
    if bedrijf.get("lat") and bedrijf.get("lon"):
        afstand_alblasserdam = round(_haversine_km(ALBLASSERDAM_LAT, ALBLASSERDAM_LON, bedrijf["lat"], bedrijf["lon"]))

    # --- Materialen en volume (echte data uit materiaal_volumes) ---
    materialen_volume_lijst = []
    _volumes_dict = bedrijf.get("materiaal_volumes", {})
    if isinstance(_volumes_dict, dict) and _volumes_dict:
        _totaal_volume = sum(parse_hoeveelheid_getal(v) for v in _volumes_dict.values())
        for mat_naam, waarde in sorted(_volumes_dict.items(), key=lambda x: -parse_hoeveelheid_getal(x[1])):
            vol = parse_hoeveelheid_getal(waarde)
            materialen_volume_lijst.append({"naam": mat_naam, "volume": vol, "aandeel": round(vol / _totaal_volume * 100) if _totaal_volume else 0})

    # --- Inkoop-voortgang dit jaar vs. jaarlijks beschikbaar volume (alleen leveranciers, echte shipment-data) ---
    inkoop_voortgang_lijst = []
    if not is_fabriek_profiel and isinstance(_volumes_dict, dict) and _volumes_dict:
        _huidig_jaar = datetime.date.today().year
        _ontvangen_statussen = ("Weighed", "Received", "Delivered")
        _gepland_statussen = ("Planned", "Confirmed", "Loading", "Loaded", "In Transit", "Arrived")
        for mat_naam, waarde in _volumes_dict.items():
            beschikbaar_jaar = parse_hoeveelheid_getal(waarde)
            if beschikbaar_jaar <= 0:
                continue
            ingekocht_dit_jaar = 0.0
            nog_te_leveren = 0.0
            for s in laad_shipments():
                if s.get("origin_leverancier", "").strip().lower() != bedrijf["naam"].strip().lower():
                    continue
                if s.get("materiaal", "") != mat_naam:
                    continue
                if not s.get("datum"):
                    continue
                try:
                    jaar_shipment = datetime.datetime.strptime(s["datum"], "%Y-%m-%d").date().year
                except (ValueError, TypeError):
                    continue
                if jaar_shipment != _huidig_jaar:
                    continue
                if s.get("status") in _ontvangen_statussen:
                    ingekocht_dit_jaar += shipment_hoeveelheid(s)
                elif s.get("status") in _gepland_statussen:
                    nog_te_leveren += shipment_hoeveelheid(s)
            restant_jaarvolume = max(0.0, beschikbaar_jaar - ingekocht_dit_jaar)
            inkoop_voortgang_lijst.append({
                "naam": mat_naam, "beschikbaar_jaar": beschikbaar_jaar,
                "ingekocht_dit_jaar": ingekocht_dit_jaar, "nog_te_leveren": nog_te_leveren,
                "restant_jaarvolume": restant_jaarvolume,
                "pct_ingekocht": round(min(100, ingekocht_dit_jaar / beschikbaar_jaar * 100)) if beschikbaar_jaar else 0,
            })
        inkoop_voortgang_lijst.sort(key=lambda x: -x["beschikbaar_jaar"])

    # --- Recente orders (echte data, laatste 5) + geleverd/openstaand obv gekoppelde shipments ---
    _alle_shipments_profiel = laad_shipments()
    recente_orders_profiel = []
    for o in sorted(_orders_van_bedrijf, key=lambda x: x.get("aangemaakt",""), reverse=True)[:5]:
        _order_ref = f"Order-{o['id'][:8]}"
        _gekoppelde_shipments = [s for s in _alle_shipments_profiel if s.get("referentie","") == _order_ref]
        _totaal_order = parse_hoeveelheid_getal(o.get("hoeveelheid",""))
        _geleverd_order = sum(parse_hoeveelheid_getal(s.get("werkelijk_hoeveelheid","")) for s in _gekoppelde_shipments if s.get("werkelijk_hoeveelheid"))
        _openstaand_order = max(0, _totaal_order - _geleverd_order) if _totaal_order else 0
        recente_orders_profiel.append({
            "referentie": f"ORD-{o['id'][:4].upper()}", "materiaal": o.get("materiaal","—"),
            "datum": o.get("verwachte_datum","") or o.get("aangemaakt","").split(" ")[0],
            "hoeveelheid": o.get("hoeveelheid",""), "status": o.get("status",""),
            "totaal_order": _totaal_order, "geleverd_order": _geleverd_order, "openstaand_order": _openstaand_order,
            "geleverd_pct": round(_geleverd_order / _totaal_order * 100) if _totaal_order else 0,
            "heeft_levering_data": bool(_gekoppelde_shipments and _totaal_order),
        })

    # --- Fabrieken met gedeelde kwaliteiten (echte data: overlap in kwaliteiten, gesorteerd op afstand) ---
    fabrieken_gedeelde_kwaliteiten = []
    _matchpoel = PAPIERFABRIEKEN if not is_fabriek_profiel else ENF_BEDRIJVEN
    matchpoel_label = "Fabrieken met gedeelde kwaliteiten" if not is_fabriek_profiel else "Leveranciers met gedeelde kwaliteiten"
    _eigen_kwaliteiten = set(k.strip().lower() for k in (bedrijf.get("kwaliteiten","") or "").split(",") if k.strip())
    if _eigen_kwaliteiten:
        for ander in _matchpoel:
            if ander["naam"] == bedrijf["naam"] or not ander.get("kwaliteiten"):
                continue
            _andere_kwaliteiten = set(k.strip().lower() for k in ander["kwaliteiten"].split(",") if k.strip())
            _gedeeld = _eigen_kwaliteiten & _andere_kwaliteiten
            if _gedeeld:
                _afstand = None
                if bedrijf.get("lat") and bedrijf.get("lon") and ander.get("lat") and ander.get("lon"):
                    _afstand = round(_haversine_km(bedrijf["lat"], bedrijf["lon"], ander["lat"], ander["lon"]))
                fabrieken_gedeelde_kwaliteiten.append({
                    "naam": ander["naam"], "regio": ander.get("regio", ander.get("stad","")), "land": ander.get("land",""),
                    "afstand": _afstand, "gedeelde_kwaliteiten": ", ".join(sorted(_gedeeld, key=str.lower))[:60],
                    "_sorteer_afstand": _afstand if _afstand is not None else 999999,
                })
        fabrieken_gedeelde_kwaliteiten.sort(key=lambda x: x["_sorteer_afstand"])
        fabrieken_gedeelde_kwaliteiten = fabrieken_gedeelde_kwaliteiten[:5]

    pagina = render_simple_page(bedrijf["naam"], "zoeken", inhoud)
    _bedrijf_naam_laag = bedrijf["naam"].strip().lower()
    _bedrijf_shipments = sorted(
        [s for s in laad_shipments() if _bedrijf_naam_laag in (s.get("origin_leverancier","").strip().lower(), s.get("destination_naam","").strip().lower())],
        key=lambda s: s.get("datum",""), reverse=True
    )

    # --- Echte leveranciers die aan dit bedrijf leveren (uit shipment-geschiedenis, geen matching-gok) ---
    _leveren_aan_dict = {}
    for s in laad_shipments():
        if s.get("destination_naam","").strip().lower() != _bedrijf_naam_laag:
            continue
        _lev_naam = s.get("origin_leverancier","").strip()
        if not _lev_naam:
            continue
        if _lev_naam not in _leveren_aan_dict:
            _leveren_aan_dict[_lev_naam] = {"naam": _lev_naam, "land": s.get("origin_land",""), "aantal_shipments": 0, "totaal_volume": 0.0, "laatste_datum": ""}
        _entry = _leveren_aan_dict[_lev_naam]
        _entry["aantal_shipments"] += 1
        _entry["totaal_volume"] += parse_hoeveelheid_getal(s.get("werkelijk_hoeveelheid") or s.get("gepland_hoeveelheid") or "")
        if s.get("datum","") > _entry["laatste_datum"]:
            _entry["laatste_datum"] = s.get("datum","")
    actieve_leveranciers = sorted(_leveren_aan_dict.values(), key=lambda x: -x["totaal_volume"])

    # --- Voor leveranciers: waar hun materiaal uiteindelijk naartoe gaat (via gekoppelde vervolg-shipments) ---
    bestemmingen_lijst = []
    if not is_fabriek_profiel:
        _inbound_ids_van_leverancier = {
            s.get("id") for s in laad_shipments()
            if s.get("origin_leverancier", "").strip().lower() == _bedrijf_naam_laag
        }
        _bestemmingen_dict = {}
        for s in laad_shipments():
            if s.get("gekoppelde_shipment_id") not in _inbound_ids_van_leverancier:
                continue
            sleutel = (s.get("destination_land", ""), s.get("destination_naam", ""))
            if sleutel not in _bestemmingen_dict:
                _bestemmingen_dict[sleutel] = {
                    "land": s.get("destination_land", ""), "naam": s.get("destination_naam", ""),
                    "aantal_shipments": 0, "totaal_volume": 0.0, "laatste_datum": "",
                }
            _entry2 = _bestemmingen_dict[sleutel]
            _entry2["aantal_shipments"] += 1
            _entry2["totaal_volume"] += shipment_hoeveelheid(s)
            if s.get("datum", "") > _entry2["laatste_datum"]:
                _entry2["laatste_datum"] = s.get("datum", "")
        bestemmingen_lijst = sorted(_bestemmingen_dict.values(), key=lambda x: -x["totaal_volume"])

    return render_template_string(pagina, bedrijf=bedrijf, status=status, opgeslagen=opgeslagen, geverifieerd=geverifieerd,
                                    is_fabriek_profiel=is_fabriek_profiel, afhaallocaties=afhaallocaties,
                                    open_orders_aantal=open_orders_aantal, open_orders_ton=open_orders_ton,
                                    laatst_contact_profiel=laatst_contact_profiel, afstand_alblasserdam=afstand_alblasserdam,
                                    materialen_volume_lijst=materialen_volume_lijst, inkoop_voortgang_lijst=inkoop_voortgang_lijst,
                                    recente_orders_profiel=recente_orders_profiel,
                                    actieve_leveranciers=actieve_leveranciers, bestemmingen_lijst=bestemmingen_lijst,
                                    fabrieken_gedeelde_kwaliteiten=fabrieken_gedeelde_kwaliteiten, matchpoel_label=matchpoel_label,
                                    bedrijf_orders=[o for o in laad_orders() if o.get("bedrijf","").strip().lower() == bedrijf["naam"].strip().lower()],
                                    orderkleuren=ORDER_KLEUREN,
                                    accountmanager=laad_accountmanagers().get(bedrijf["naam"], ""),
                                    alle_gebruikersnamen=sorted(laad_users().keys()),
                                    gebruikersnaam=session.get("gebruikersnaam", ""),
                                    bedrijf_shipments=_bedrijf_shipments,
                                    materiaal_categorieen_lijst=[k.strip() for k in (bedrijf.get("kwaliteiten","") or "").split(",") if k.strip()],
                                    materiaal_taxonomie=laad_materiaal_taxonomie())