# IPHW Rate Calculator — Multi-PC / Multi-User Web Version

## What this is
A shared web calculator based on the supplied Excel workbook. Calculator A and B, country/zone mapping, Rate A/B, ODA city/postal matching, VAT, exchange rate, ODA base/per-KG and ODA fuel are stored centrally in SQLite.

## Multi-user behavior
Run this app on ONE server/PC inside your office LAN or on a cloud/VPS. Other PCs open the server IP, e.g. `http://192.168.1.10:5000`. All users read the same database, so an admin rate update is shared immediately.

## Start on Windows
1. Install Python 3.11+.
2. Open Command Prompt in this folder.
3. `py -m venv venv`
4. `venv\Scripts\activate`
5. `pip install -r requirements.txt`
6. Set an admin password (recommended): `set ADMIN_PASSWORD=YourStrongPassword`
7. `py app.py`
8. Server PC: `http://localhost:5000`
9. Other PCs: `http://SERVER-IP:5000`

Default admin password if you do not set one: `admin123` — change it before use.

## Updating rates
Go to `/admin`, log in, and upload the updated `.xlsx` master file. The workbook should keep these sheet names:
- Calculatore -A
- Calculatore -B
- Sheet2
- Rate ; A
- Rate; B
- Sheet1

The upload replaces the shared Rate A/B, Zone and ODA master data and imports the current settings from Calculator A.

## Production
For many users, run behind a proper WSGI server (Waitress/Gunicorn) and HTTPS. For a larger organization, SQLite can be replaced with PostgreSQL/MySQL without changing the front-end concept.
