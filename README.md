# IPHW Rate Calculator - Full Web Version

## Included calculation logic
- Calculator A and Calculator B use separate Rate Master sheets.
- Billing weight = ROUNDUP(input weight, 0).
- Minimum billing weight is 10 KG.
- Base Tariff = Billing Weight × Per KG Rate.
- ODA Charge (USD) = MAX(ODA Base USD, Billing Weight × ODA Per KG USD) when a City or Postal ODA match exists.
- ODA Charge (BDT) = ODA USD × Exchange Rate.
- ODA Fuel Surcharge = ODA Charge (BDT) × ODA Fuel Surcharge rate.
- Grand Total Without VAT = Base Tariff + ODA Charge (BDT) + ODA Fuel Surcharge.
- VAT Amount = Grand Total Without VAT × VAT Rate.
- Grand Total With VAT = Grand Total Without VAT + VAT Amount.

## Render
Build command: `pip install -r requirements.txt`
Start command: `gunicorn --bind 0.0.0.0:$PORT app:app`

Set environment variables:
- ADMIN_PASSWORD = your admin password
- SECRET_KEY = a long random secret

Default admin password if ADMIN_PASSWORD is not set: `admin123` (change it in production).

## Rate updates
Admin -> Upload Updated Excel Rate Master. The workbook should retain the original sheet names and structure.

Note: SQLite on free/ephemeral hosting may not retain database changes after a service replacement/redeploy. For permanent online rate updates, connect a persistent database (e.g. PostgreSQL) later.
