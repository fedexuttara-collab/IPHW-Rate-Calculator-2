import os, sqlite3, tempfile, re, math
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash
from openpyxl import load_workbook

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(APP_DIR, "rate_master.db")
DEFAULT_XLSX = os.path.join(APP_DIR, "IPHW_RATE_MASTER.xlsx")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS zones(country TEXT PRIMARY KEY, zone TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS rates(
      calculator TEXT NOT NULL, weight_from REAL NOT NULL, weight_to REAL NOT NULL,
      zone TEXT NOT NULL, rate REAL NOT NULL,
      PRIMARY KEY(calculator, weight_from, weight_to, zone)
    );
    CREATE TABLE IF NOT EXISTS oda(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      country TEXT NOT NULL, city TEXT, postal_from INTEGER, postal_to INTEGER,
      oda_type TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS import_log(
      id INTEGER PRIMARY KEY AUTOINCREMENT, imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
      filename TEXT, status TEXT, message TEXT
    );
    """)
    c.commit()
    c.close()


def num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def import_xlsx(path, filename="IPHW_RATE_MASTER.xlsx"):
    wb = load_workbook(path, data_only=True)
    required = ["Calculatore -A", "Rate ; A", "Rate; B", "Sheet1", "Sheet2"]
    missing = [s for s in required if s not in wb.sheetnames]
    if missing:
        raise ValueError("Missing required sheet(s): " + ", ".join(missing))

    c = db()
    try:
        ws = wb["Calculatore -A"]
        settings = {
            "exchange_rate": num(ws["B7"].value, 123.65),
            "vat_rate": num(ws["B8"].value, 0.15),
            "oda_fuel": num(ws["B9"].value, 0.5325),
            "oda_base_usd": num(ws["B15"].value, 25),
            "oda_perkg_usd": num(ws["B16"].value, 0.5),
        }
        for k, v in settings.items():
            c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))

        c.execute("DELETE FROM zones")
        ws = wb["Sheet2"]
        for r in range(5, ws.max_row + 1):
            country, zone = ws.cell(r, 1).value, ws.cell(r, 2).value
            if country and zone:
                c.execute("INSERT OR REPLACE INTO zones(country,zone) VALUES(?,?)", (str(country).strip(), str(zone).strip()))

        c.execute("DELETE FROM rates")
        for sheet, calc_type in [("Rate ; A", "A"), ("Rate; B", "B")]:
            ws = wb[sheet]
            zones = [ws.cell(1, col).value for col in range(2, ws.max_column + 1)]
            for r in range(2, 9):
                label = ws.cell(r, 1).value
                if not label:
                    continue
                text = str(label).strip()
                if text.startswith("101"):
                    lo, hi = 101, 999999999
                else:
                    m = re.match(r"(\d+)\s*-\s*(\d+)", text)
                    if not m:
                        continue
                    lo, hi = int(m.group(1)), int(m.group(2))
                for i, zone in enumerate(zones, start=2):
                    val = ws.cell(r, i).value
                    if zone and isinstance(val, (int, float)):
                        c.execute("INSERT INTO rates VALUES(?,?,?,?,?)", (calc_type, lo, hi, str(zone).strip(), float(val)))

        c.execute("DELETE FROM oda")
        ws = wb["Sheet1"]
        for r in range(9, ws.max_row + 1):
            country = ws.cell(r, 1).value
            if not country:
                continue
            city = ws.cell(r, 2).value
            pf, pt = ws.cell(r, 3).value, ws.cell(r, 4).value
            country = str(country).strip()
            city = str(city).strip() if city is not None else ""
            try:
                pf = int(float(pf)) if pf is not None else None
            except (TypeError, ValueError):
                pf = None
            try:
                pt = int(float(pt)) if pt is not None else None
            except (TypeError, ValueError):
                pt = None
            oda_type = "Postal" if pf is not None else "City"
            c.execute("INSERT INTO oda(country,city,postal_from,postal_to,oda_type) VALUES(?,?,?,?,?)", (country, city, pf, pt, oda_type))

        c.execute("INSERT INTO import_log(filename,status,message) VALUES(?,?,?)", (filename, "OK", "Calculator A/B, Zone, Rate and ODA master imported"))
        c.commit()
    except Exception as e:
        c.rollback()
        c.execute("INSERT INTO import_log(filename,status,message) VALUES(?,?,?)", (filename, "ERROR", str(e)))
        c.commit()
        raise
    finally:
        c.close()


def get_settings():
    c = db()
    d = {r["key"]: float(r["value"]) for r in c.execute("SELECT key,value FROM settings")}
    c.close()
    return d


def meta_data():
    c = db()
    countries = [r["country"] for r in c.execute("SELECT country FROM zones ORDER BY country COLLATE NOCASE")]
    rows = c.execute("SELECT country, oda_type, COUNT(*) AS n FROM oda GROUP BY country, oda_type").fetchall()
    oda_map = {}
    for r in rows:
        oda_map.setdefault(r["country"], {})[r["oda_type"]] = r["n"]
    c.close()
    return countries, oda_map


def calculate(payload):
    try:
        weight = float(payload.get("weight", 0))
    except (TypeError, ValueError):
        raise ValueError("Enter a valid weight.")
    if weight < 10:
        raise ValueError("Minimum 10 KG required.")

    country = (payload.get("country") or "").strip()
    postal = (payload.get("postal") or "").strip()
    city = (payload.get("city") or "").strip()
    calc_type = (payload.get("calculator") or "A").upper()
    if calc_type not in ("A", "B"):
        calc_type = "A"
    if not country:
        raise ValueError("Select a destination country.")

    settings = get_settings()
    rounded_weight = math.ceil(weight)
    c = db()
    zrow = c.execute("SELECT zone FROM zones WHERE lower(country)=lower(?)", (country,)).fetchone()
    if not zrow:
        c.close()
        raise ValueError("Country not found in Zone Master.")
    zone = zrow["zone"]

    rate_row = c.execute("""
        SELECT rate FROM rates
        WHERE calculator=? AND weight_from<=? AND weight_to>=? AND lower(zone)=lower(?)
        ORDER BY weight_from DESC LIMIT 1
    """, (calc_type, rounded_weight, rounded_weight, zone)).fetchone()
    if not rate_row:
        c.close()
        raise ValueError(f"No rate found for Calculator {calc_type}, Zone {zone}, weight {rounded_weight} KG.")
    per_kg = float(rate_row["rate"])

    oda_rows = c.execute("SELECT * FROM oda WHERE lower(country)=lower(?)", (country,)).fetchall()
    c.close()

    postal_num = None
    if postal:
        digits = re.sub(r"\D", "", postal)
        if digits:
            postal_num = int(digits)

    matched = []
    for row in oda_rows:
        hit = False
        if row["oda_type"] == "City" and city and row["city"].strip().lower() == city.lower():
            hit = True
        elif row["oda_type"] == "Postal" and postal_num is not None:
            if row["postal_from"] <= postal_num <= row["postal_to"]:
                hit = True
        if hit:
            matched.append(dict(row))

    oda = bool(matched)
    base_tariff = rounded_weight * per_kg
    oda_usd = max(settings.get("oda_base_usd", 25), rounded_weight * settings.get("oda_perkg_usd", 0.5)) if oda else 0
    oda_bdt = oda_usd * settings.get("exchange_rate", 0)
    oda_fuel_bdt = oda_bdt * settings.get("oda_fuel", 0) if oda else 0
    subtotal = base_tariff + oda_bdt + oda_fuel_bdt
    vat = subtotal * settings.get("vat_rate", 0)
    total = subtotal + vat

    return {
        "calculator": calc_type, "weight": weight, "rounded_weight": rounded_weight,
        "country": country, "zone": zone, "per_kg_rate": per_kg,
        "base_tariff": base_tariff, "oda_status": "ODA" if oda else "No ODA",
        "oda_usd": oda_usd, "oda_bdt": oda_bdt, "oda_fuel_bdt": oda_fuel_bdt,
        "subtotal_without_vat": subtotal, "vat_rate": settings.get("vat_rate", 0),
        "vat_amount": vat, "grand_total_with_vat": total,
        "exchange_rate": settings.get("exchange_rate", 0),
        "matched_by": sorted(set(x["oda_type"] for x in matched)),
        "matched_rows": matched[:100],
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return "OK", 200


@app.route("/api/meta")
def meta():
    countries, oda_map = meta_data()
    return jsonify({"countries": countries, "oda_map": oda_map, "settings": get_settings()})


@app.route("/api/calculate", methods=["POST"])
def api_calculate():
    try:
        return jsonify(calculate(request.get_json(force=True)))
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
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


@app.route("/admin/upload", methods=["POST"])
def upload():
    if not session.get("admin"):
        return redirect(url_for("login"))
    f = request.files.get("rate_file")
    if not f or not f.filename.lower().endswith(".xlsx"):
        flash("Please select an .xlsx rate master file.")
        return redirect(url_for("admin"))
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as t:
        f.save(t.name)
        tmp = t.name
    try:
        import_xlsx(tmp, f.filename)
        flash("Rate A/B, Zone and ODA master updated successfully for all active users.")
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
    flash("Settings updated.")
    return redirect(url_for("admin"))


# Initialize database when imported by Gunicorn/Render.
init_db()
c = db()
count = c.execute("SELECT COUNT(*) AS n FROM zones").fetchone()["n"]
c.close()
if count == 0 and os.path.exists(DEFAULT_XLSX):
    import_xlsx(DEFAULT_XLSX)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
