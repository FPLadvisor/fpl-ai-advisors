# FPL AI Advisor V3 — Online

Team ID: **1643829**

## What V3 fixes

- Single online Streamlit application
- No local FastAPI server required
- Public FPL data refreshes every 5 minutes while the dashboard is active
- Official FDR used as a fixture adjustment
- 3-GW expected-points projection
- Captain and vice-captain ranking
- Differential finder
- Transfer optimizer
- Explicit -4 hit economics
- Availability/injury flags
- Price-pressure indicators
- No FPL password stored

## Important limitation

FPL manager picks are a manager-specific endpoint and can require authentication. This app therefore does **not** ask for or store your FPL password. If the public endpoint does not return your picks, enter your 15 players once in the sidebar; the app then keeps using the public live player/fixture data around that squad.

## Deploy to Render

1. Create a GitHub repository and upload these files.
2. In Render, create a **Web Service** from the repository.
3. Render can use `render.yaml`.
4. Set:
   FPL_TEAM_ID=1643829
5. Deploy.
6. Open the generated HTTPS URL.

The free web service may sleep when idle depending on the hosting plan. For truly continuous uptime, use an always-on paid instance or another always-on hosting plan.

## Local test

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```
