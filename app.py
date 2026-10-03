import os
import sqlite3
import tempfile
import re
import math
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "iphw-secret-key-12345")

DB_PATH = "rate_master.db"
DEFAULT_XLSX = "IPHW_RATE_MASTER.xlsx"

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    c = db()
    c.execute("""
        CREATE TABLE IF NOT EXISTS zones (
            country TEXT PRIMARY KEY,
            zone TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS oda_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country TEXT,
            city TEXT,
            postal_code TEXT,
            type TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS import_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            filename TEXT,
            status TEXT,
            message TEXT
        )
    """)
    
    # Default settings setup
    default_settings = {
        "exchange_rate": "120",
        "vat_rate": "0.15",
        "oda_fuel": "0.0",
        "oda_base_usd": "25.0",
        "oda_perkg_usd": "0.5"
    }
    for k, v in default_settings.items():
        c.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (k, v))
        
    c.commit()
    c.close()

def get_settings():
    c = db()
    rows = c.execute("SELECT key, value FROM settings").fetchall()
    c.close()
    s = {r["key"]: r["value"] for r in rows}
    return s

@app.route("/")
def index():
    c = db()
    # Zone টেবিল থেকে সব দেশের নামের লিস্ট নিয়ে আসা
    countries_rows = c.execute("SELECT DISTINCT country FROM zones ORDER BY country ASC").fetchall()
    c.close()
    
    countries = [r["country"] for r in countries_rows]
    return render_template("index.html", countries=countries)

@app.route("/api/oda_suggestions")
def oda_suggestions():
    country = request.args.get("country", "").strip()
    if not country:
        return jsonify({"cities": [], "postals": []})

    c = db()
    cities_rows = c.execute(
        "SELECT DISTINCT city FROM oda_master WHERE country = ? AND city IS NOT NULL AND city != '' ORDER BY city ASC LIMIT 200", 
        (country,)
    ).fetchall()
    
    postals_rows = c.execute(
        "SELECT DISTINCT postal_code FROM oda_master WHERE country = ? AND postal_code IS NOT NULL AND postal_code != '' ORDER BY postal_code ASC LIMIT 200", 
        (country,)
    ).fetchall()
    c.close()

    cities = [r["city"] for r in cities_rows]
    postals = [r["postal_code"] for r in postals_rows]

    return jsonify({"cities": cities, "postals": postals})

@app.route("/calculate", methods=["POST"])
def calculate():
    calc_type = request.form.get("calc_type", "A")
    weight_str = request.form.get("weight", "0").strip()
    country = request.form.get("country", "").strip()
    city = request.form.get("city", "").strip()
    postal_code = request.form.get("postal_code", "").strip()

    try:
        weight = float(weight_str)
    except ValueError:
        return jsonify({"error": "Invalid weight entered."})

    billing_weight = math.ceil(weight) if weight > 0 else 0

    c = db()
    zone_row = c.execute("SELECT zone FROM zones WHERE country = ?", (country,)).fetchone()
    if not zone_row:
        c.close()
        return jsonify({"error": f"Zone not found for country: {country}"})

    zone = zone_row["zone"]

    # Check ODA
    is_oda = False
    if city or postal_code:
        oda_check = c.execute(
            "SELECT id FROM oda_master WHERE country = ? AND (city = ? OR postal_code = ?)",
            (country, city, postal_code)
        ).fetchone()
        if oda_check:
            is_oda = True

    c.close()

    settings = get_settings()
    exchange_rate = float(settings.get("exchange_rate", 120))
    vat_rate = float(settings.get("vat_rate", 0.15))

    # Base pricing logic (dummy rate calculation placeholder)
    per_kg_rate = 1670.0  
    base_tariff = billing_weight * per_kg_rate

    oda_charge_usd = 0.0
    if is_oda:
        base_oda = float(settings.get("oda_base_usd", 25.0))
        perkg_oda = float(settings.get("oda_perkg_usd", 0.5))
        oda_charge_usd = base_oda + (billing_weight * perkg_oda)

    oda_charge_bdt = oda_charge_usd * exchange_rate
    oda_fuel_bdt = 0.0

    grand_total_novat = base_tariff + oda_charge_bdt + oda_fuel_bdt
    vat_bdt = grand_total_novat * vat_rate
    grand_total_vat = grand_total_novat + vat_bdt

    return jsonify({
        "input_weight": f"{weight:.2f}",
        "billing_weight": billing_weight,
        "zone": zone,
        "per_kg_rate": f"{per_kg_rate:,.2f}",
        "base_tariff": f"{base_tariff:,.2f}",
        "is_oda": is_oda,
        "oda_status": "ODA Area" if is_oda else "No ODA",
        "oda_charge_usd": f"{oda_charge_usd:.2f}",
        "oda_charge_bdt": f"{oda_charge_bdt:,.2f}",
        "oda_fuel_bdt": f"{oda_fuel_bdt:,.2f}",
        "grand_total_novat": f"{grand_total_novat:,.2f}",
        "vat_percent": f"{vat_rate * 100:.2f}",
        "vat_bdt": f"{vat_bdt:,.2f}",
        "grand_total_vat": f"{grand_total_vat:,.2f}"
    })

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pwd = request.form.get("password")
        if pwd == "admin123":
            session["admin"] = True
            return redirect(url_for("admin"))
        flash("Invalid admin password.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("index"))

@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect(url_for("login"))
    c = db()
    logs = c.execute("SELECT * FROM import_log ORDER BY id DESC LIMIT 20").fetchall()
    c.close()
    return render_template("admin.html", settings=get_settings(), logs=logs)

@app.route("/admin/settings", methods=["POST"])
def settings_update():
    if not session.get("admin"):
        return redirect(url_for("login"))
    c = db()
    for k in ["exchange_rate", "vat_rate", "oda_fuel", "oda_base_usd", "oda_perkg_usd"]:
        if k in request.form:
            c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, request.form[k]))
    c.commit()
    c.close()
    flash("Settings updated successfully.")
    return redirect(url_for("admin"))

# Initialize DB on start
init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
