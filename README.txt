IPHW Rate Calculator - A-to-Z Final Update

Replace these 3 files in the existing GitHub repo:
1. app.py
2. templates/index.html
3. static/style.css

Important:
- The old static/oda_suggestions.json is no longer required.
- City and Postal ODA suggestions/counts now come directly from the database through /api/meta.
- After Admin uploads a new Excel Rate Master, City/Postal suggestions and counts update automatically for users after refresh.
- Existing Calculator A/B, Zone, Rate Master, ODA calculation, Admin login and Excel upload logic are preserved.

After GitHub commit:
Render -> Manual Deploy -> Deploy latest commit.
