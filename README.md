# SwiftEmployee
Understand → Plan → Execute → Verify → Complete. One controller (`agent.py`), three tools (`search_web`, `create_report`, `verify_report`). Gemini is called at most twice (plan; synthesis only if >8s remain). Search via Tavily + `requests`/BeautifulSoup. 30s deadline, 5s fetch timeouts, one retry per source.

## Setup (PowerShell, from this folder)
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # then fill GEMINI_API_KEY and SEARCH_API_KEY (Tavily)
```
## Run
Terminal 1:
```powershell
cd backend; .\.venv\Scripts\Activate.ps1; uvicorn main:app --port 8000
```
Terminal 2:
```powershell
cd frontend; npm install; npm run dev
```
Open http://localhost:5173. Tick **Demo mode** to test the UI with fixtures (no keys; report is labeled DEMO).

Status meanings: `completed` = all checks passed with the requested source count in time; `partial` = checks passed but fewer sources or deadline passed; `failed` = checks failed or no sources.
