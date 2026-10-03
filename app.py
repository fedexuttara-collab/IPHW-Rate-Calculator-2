import os
import sqlite3
import tempfile
import math
import pandas as pd
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "iphw-secret-key-12345")

DB_PATH = "rate_master.db"

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
            postal_begin TEXT,
            postal_end TEXT
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
    
    default_settings = {
        "exchange_rate": "123.65",
        "vat_rate": "0.15",
        "oda_fuel": "0.53",
        "oda_base_usd": "25.0",
        "oda_perkg_usd": "0.5"
    }
    for k, v in default_settings.items():
        c.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (k, v))
        
    c.commit()
    c.close()

def import_xlsx(filepath, filename="IPHW_RATE_MASTER.xlsx"):
    c = db()
    try:
        xls = pd.ExcelFile(filepath)
        df_z = pd.read_excel(xls, 'Zone', header=None)
        c.execute("DELETE FROM zones")
        for i in range(3, len(df_z)):
            cntry = str(df_z.iloc[i, 0]).strip()
            if cntry and cntry != 'nan' and cntry != 'Grand Total':
                c.execute("INSERT OR REPLACE INTO zones(country, zone) VALUES(?, ?)", (cntry, 'A'))

        df_ra = pd.read_excel(xls, 'Rate ; A')
        for i in range(11, len(df_ra)):
            c_name = str(df_ra.iloc[i, 11]).strip()
            z_name = str(df_ra.iloc[i, 12]).strip()
            if c_name and c_name != 'nan' and z_name and z_name != 'nan':
                c.execute("INSERT OR REPLACE INTO zones(country, zone) VALUES(?, ?)", (c_name, z_name))

        df_oda = pd.read_excel(xls, 'Sheet1', header=6)
        c.execute("DELETE FROM oda_master")
        for _, row in df_oda.iterrows():
            cntry = str(row[0]).strip() if pd.notna(row[0]) else ''
            cty = str(row[1]).strip() if pd.notna(row[1]) else ''
            p_beg = str(row[2]).strip() if pd.notna(row[2]) else ''
            p_end = str(row[3]).strip() if pd.notna(row[3]) else ''
            if cntry and cntry != 'nan':
                c.execute("INSERT INTO oda_master(country, city, postal_begin, postal_end) VALUES(?, ?, ?, ?)",
                          (cntry, cty, p_beg, p_end))

        c.execute("INSERT INTO import_log(filename, status, message) VALUES(?, ?, ?)",
                  (filename, "Success", "Database updated successfully."))
        c.commit()
    except Exception as e:
        c.execute("INSERT INTO import_log(filename, status, message) VALUES(?, ?, ?)",
                  (filename, "Failed", str(e)))
        c.commit()
        raise e
    finally:
        c.close()

def get_settings():
    c = db()
    rows = c.execute("SELECT key, value FROM settings").fetchall()
    c.close()
    return {r["key"]: r["value"] for r in rows}

@app.route("/")
def index():
    c = db()
    countries_rows = c.execute("SELECT DISTINCT country FROM zones WHERE country IS NOT NULL AND country != '' ORDER BY country ASC").fetchall()
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
        "SELECT DISTINCT postal_begin FROM oda_master WHERE country = ? AND postal_begin IS NOT NULL AND postal_begin != '' ORDER BY postal_begin ASC LIMIT 200", 
        (country,)
    ).fetchall()
    c.close()

    return jsonify({
        "cities": [r["city"] for r in cities_rows],
        "postals": [r["postal_begin"] for r in postals_rows]
    })

@app.route("/calculate", methods=["POST"])
def calculate():
    calc_type = request.form.get("calc_type", "A")
    weight_str = request.form.get("weight", "0").strip()
    country = request.form.get("country", "").strip()
    city = request.form.get("city", "").strip().lower()
    postal_code = request.form.get("postal_code", "").strip()

    try:
        weight = float(weight_str)
    except ValueError:
        return jsonify({"error": "Invalid weight entered."})

    billing_weight = math.ceil(weight) if weight > 0 else 0

    c = db()
    zone_row = c.execute("SELECT zone FROM zones WHERE country = ?", (country,)).fetchone()
    zone = zone_row["zone"] if zone_row else "I"

    is_oda = False
    if city or postal_code:
        oda_rows = c.execute("SELECT city, postal_begin, postal_end FROM oda_master WHERE country = ?", (country,)).fetchall()
        for r in oda_rows:
            oda_city = (r["city"] or "").strip().lower()
            p_beg = (r["postal_begin"] or "").strip()
            p_end = (r["postal_end"] or "").strip()

            if city and oda_city and city == oda_city:
                is_oda = True
                break

            if postal_code and p_beg:
                if p_end:
                    if p_beg <= postal_code <= p_end:
                        is_oda = True
                        break
                elif postal_code == p_beg:
                    is_oda = True
                    break

    c.close()

    settings = get_settings()
    exchange_rate = float(settings.get("exchange_rate", 123.65))
    vat_rate = float(settings.get("vat_rate", 0.15))
    oda_fuel_rate = float(settings.get("oda_fuel", 0.53))

    per_kg_rate = 1670.0 if calc_type == "A" else 1680.0
    base_tariff = (billing_weight * per_kg_rate) + (6 if calc_type == "B" else 0)

    oda_charge_usd = 0.0
    if is_oda:
        base_oda = float(settings.get("oda_base_usd", 25.0))
        perkg_oda = float(settings.get("oda_perkg_usd", 0.5))
        oda_charge_usd = max(base_oda, billing_weight * perkg_oda)

    oda_charge_bdt = oda_charge_usd * exchange_rate
    oda_fuel_bdt = oda_charge_bdt * oda_fuel_rate if is_oda else 0.0

    grand_total_novat = base_tariff + oda_charge_bdt + oda_fuel_bdt
    vat_bdt = grand_total_novat * vat_rate
    grand_total_vat = grand_total_novat + vat_bdt

    return jsonify({
        "calc_type": calc_type,
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
        if request.form.get("password") == "admin123":
            session["admin"] = True
            return redirect(url_for("admin"))
        flash("Invalid password.")
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

@app.route("/admin/upload", methods=["POST"])
def upload():
    if not session.get("admin"):
        return redirect(url_for("login"))
    f = request.files.get("rate_file")
    if not f or not f.filename.lower().endswith(".xlsx"):
        flash("Please upload a valid .xlsx file.")
        return redirect(url_for("admin"))
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as t:
        f.save(t.name)
        tmp = t.name
    try:
        import_xlsx(tmp, f.filename)
        flash("Rate master updated successfully.")
    except Exception as e:
        flash("Update failed: " + str(e))
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return redirect(url_for("admin"))

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
    flash("Settings saved successfully.")
    return redirect(url_for("admin"))

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
