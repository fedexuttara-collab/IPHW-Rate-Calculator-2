<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>IPHW Rate Calculator</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
</head>
<body>
    <header class="main-header">
        <div class="logo-area">
            <h1>IPHW RATE CALCULATOR</h1>
            <p class="subtitle">Calculator A / Calculator B • Shared Rate Master</p>
        </div>
        <div class="admin-link">
            <a href="/admin" class="btn-admin">Admin / Rate Update</a>
        </div>
    </header>

    <main class="container">
        <div class="calc-tabs">
            <button id="tabA" class="tab-btn active" onclick="switchCalc('A')">Calculator A</button>
            <button id="tabB" class="tab-btn" onclick="switchCalc('B')">Calculator B</button>
        </div>

        <div class="calc-grid">
            <section class="card form-card">
                <h2>Shipment Input</h2>
                <form id="calcForm">
                    <input type="hidden" id="calc_type" name="calc_type" value="A">

                    <div class="form-group">
                        <label for="weight">Weight / Package Code (KG)</label>
                        <input type="number" step="any" id="weight" name="weight" placeholder="e.g. 54" required oninput="calculateRate()">
                    </div>

                    <div class="form-group">
                        <label for="country">Destination Country</label>
                        <select id="country" name="country" onchange="onCountryChange()" required>
                            <option value="">-- Select Country --</option>
                            {% for c in countries %}
                            <option value="{{ c }}">{{ c }}</option>
                            {% endfor %}
                        </select>
                    </div>

                    <div class="form-group">
                        <label for="postal_code">Postal Code</label>
                        <input type="text" id="postal_code" name="postal_code" list="postal_list" placeholder="Enter postal code..." oninput="calculateRate()">
                        <datalist id="postal_list"></datalist>
                    </div>

                    <div class="form-group">
                        <label for="city">City (Optional)</label>
                        <input type="text" id="city" name="city" list="city_list" placeholder="Enter city name..." oninput="calculateRate()">
                        <datalist id="city_list"></datalist>
                    </div>

                    <div id="oda_info_badge" class="oda-info-badge">
                        <span id="oda_available_text">ODA Master: Select Country</span>
                    </div>

                    <button type="button" class="btn-primary" onclick="calculateRate()">Calculate Rate</button>
                </form>
            </section>

            <section class="card result-card">
                <div class="result-header">
                    <h2>Calculation Result</h2>
                    <span id="calc_label" class="badge-calc">Calculator A</span>
                </div>

                <div id="resultContainer" class="result-table-container">
                    <p class="placeholder-text">Enter shipment details to calculate rate.</p>
                </div>
            </section>
        </div>
    </main>

    <footer class="footer">
        <p>Prepared by <strong>Amir Hamza</strong></p>
    </footer>

    <script>
        function switchCalc(type) {
            document.getElementById('calc_type').value = type;
            document.getElementById('tabA').classList.toggle('active', type === 'A');
            document.getElementById('tabB').classList.toggle('active', type === 'B');
            document.getElementById('calc_label').innerText = 'Calculator ' + type;
            calculateRate();
        }

        async function onCountryChange() {
            const country = document.getElementById('country').value;
            const cityList = document.getElementById('city_list');
            const postalList = document.getElementById('postal_list');
            const odaText = document.getElementById('oda_available_text');

            cityList.innerHTML = '';
            postalList.innerHTML = '';
            
            if (!country) {
                odaText.innerText = "ODA Master Status: Select a Country";
                return;
            }

            try {
                const res = await fetch(`/api/oda_suggestions?country=${encodeURIComponent(country)}`);
                const data = await res.json();

                if (data.cities) {
                    data.cities.forEach(c => {
                        const opt = document.createElement('option');
                        opt.value = c;
                        cityList.appendChild(opt);
                    });
                }

                if (data.postals) {
                    data.postals.forEach(p => {
                        const opt = document.createElement('option');
                        opt.value = p;
                        postalList.appendChild(opt);
                    });
                }

                odaText.innerText = `ODA Master available: ${data.cities.length} Cities / ${data.postals.length} Postals`;
            } catch (err) {
                odaText.innerText = "ODA Master: Checked";
            }

            calculateRate();
        }

        async function calculateRate() {
            const weight = document.getElementById('weight').value;
            const country = document.getElementById('country').value;

            if (!weight || !country) return;

            const formData = new FormData(document.getElementById('calcForm'));
            const resContainer = document.getElementById('resultContainer');
            
            try {
                const response = await fetch('/calculate', { method: 'POST', body: formData });
                const data = await response.json();

                if (data.error) {
                    resContainer.innerHTML = `<div class="error-msg">${data.error}</div>`;
                    return;
                }

                resContainer.innerHTML = `
                    <table class="result-table">
                        <tr><td>Input Weight</td><td>${data.input_weight} KG</td></tr>
                        <tr><td>Billing Weight</td><td>${data.billing_weight} KG</td></tr>
                        <tr><td>Destination Zone</td><td><strong>${data.zone}</strong></td></tr>
                        <tr><td>Per KG Rate</td><td>${data.per_kg_rate} BDT</td></tr>
                        <tr><td>Base Tariff</td><td>${data.base_tariff} BDT</td></tr>
                        <tr class="${data.is_oda ? 'oda-highlight' : ''}">
                            <td>ODA Charge</td>
                            <td>${data.oda_charge_usd} USD / ${data.oda_charge_bdt} BDT (${data.oda_status})</td>
                        </tr>
                        <tr><td>ODA Fuel Surcharge</td><td>${data.oda_fuel_bdt} BDT</td></tr>
                        <tr class="total-row"><td>GRAND TOTAL WITHOUT VAT</td><td><strong>${data.grand_total_novat} BDT</strong></td></tr>
                        <tr><td>VAT (${data.vat_percent}%)</td><td>${data.vat_bdt} BDT</td></tr>
                        <tr class="grand-total-row"><td>GRAND TOTAL WITH VAT</td><td><strong>${data.grand_total_vat} BDT</strong></td></tr>
                    </table>
                `;
            } catch (err) {
                console.error(err);
            }
        }
    </script>
</body>
</html>
