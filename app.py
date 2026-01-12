import csv, os, io, json, zipfile, requests, pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from flask import Flask, request, jsonify, send_file, abort
from flask_cors import CORS

# =========================================================
# 🚀 APP
# =========================================================

app = Flask(__name__)
CORS(app)

AGENT_KEY = os.environ.get("FIN_AGENT_API_KEY")

def verify_agent(req):
    if req.headers.get("X-AGENT-KEY") != AGENT_KEY:
        abort(401, "Unauthorized")

# =========================================================
# 🩺 HEALTH
# =========================================================

@app.route("/")
def root(): return {"status": "ok"}

@app.route("/handshake", methods=["POST"])
def handshake():
    verify_agent(request)
    return {"service": "data-pipeline", "status": "ready", "time": datetime.utcnow().isoformat()}

# =========================================================
# 🗂 STORAGE
# =========================================================

BASE = Path("storage")
RAW = BASE / "raw"
CLEAN = BASE / "cleaned"
ARTIFACTS = BASE / "artifacts"
DATA = Path("data")

for p in [RAW, CLEAN, ARTIFACTS, DATA]:
    p.mkdir(parents=True, exist_ok=True)

EQUITY_MASTER = DATA / "Equity Master_System.csv"
MF_MASTER     = DATA / "MF Master_System.csv"

# =========================================================
# 🧾 NSE ENGINE
# =========================================================

@app.route("/run-daily-nse", methods=["POST"])
def run_daily_nse():
    verify_agent(request)

    date = datetime.strptime(request.json["date"], "%Y-%m-%d")
    folder = RAW / "nse" / date.strftime("%Y/%m/%d")
    folder.mkdir(parents=True, exist_ok=True)

    fname = f"BhavCopy_NSE_CM_0_0_0_{date.strftime('%Y%m%d')}_F_0000.csv.zip"
    url = f"https://archives.nseindia.com/content/cm/{fname}"

    zip_path = folder / fname
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    zip_path.write_bytes(r.content)

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        z.extractall(folder)

    return {"date": request.json["date"], "files": [f.name for f in folder.iterdir()], "status": "SUCCESS"}

# =========================================================
# 🧹 CLEANING + MASTER SYNC
# =========================================================

@app.route("/run-cleaning", methods=["POST"])
def run_cleaning():
    verify_agent(request)
    date = datetime.strptime(request.json["date"], "%Y-%m-%d")

    folder = RAW / "nse" / date.strftime("%Y/%m/%d")
    csv_file = next(f for f in folder.iterdir() if f.suffix == ".csv")

    df = pd.read_csv(raw_csv, engine="python", on_bad_lines="skip")
    df.columns = [c.strip().upper() for c in df.columns]

    clean_file = CLEAN / f"bhav_{date.strftime('%Y%m%d')}.csv"
    df.to_csv(clean_file, index=False)

    master = pd.read_csv(EQUITY_MASTER, engine="python", on_bad_lines="skip")
    existing = set(zip(master["ISIN"], master["Code"], master["Series"]))

    new = []
    for _, r in df.iterrows():
        k = (r["ISIN"], r["SYMBOL"], r["SERIES"])
        if k not in existing:
            new.append({
                "ISIN": r["ISIN"], "Code": r["SYMBOL"], "Series": r["SERIES"],
                "Date Created": datetime.now().strftime("%d-%m-%Y"),
                "Created in system": "Y", "Is active": "Y"
            })
            existing.add(k)

    if new:
        pd.concat([master, pd.DataFrame(new)]).to_csv(EQUITY_MASTER, index=False)

    return {"date": request.json["date"], "new_equities": len(new), "status": "CLEANED"}

# =========================================================
# 💰 MUTUAL FUND ENGINE
# =========================================================

@app.route("/run-daily-mf", methods=["POST"])
def run_daily_mf():
    verify_agent(request)

    run_date = datetime.strptime(request.json["date"], "%Y-%m-%d")
    url = "https://www.amfiindia.com/spages/NAVAll.txt"
    
    r = requests.get(url, timeout=30)
    r.raise_for_status()

    folder = BASE_STORAGE / "raw" / "mf" / run_date.strftime("%Y/%m/%d")
    folder.mkdir(parents=True, exist_ok=True)

    csv_path = folder / f"MF_NAV_{run_date.strftime('%Y%m%d')}.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Scheme Code","ISIN","Scheme Name","NAV","Date"])

        for line in r.text.splitlines():
            parts = line.split(";")
            if len(parts) < 6 or not parts[0].isdigit():
                continue   # skip corrupt lines safely

            w.writerow([parts[0], parts[1], parts[3], parts[4], parts[5]])

    artifact = {
        "date": run_date.strftime("%Y-%m-%d"),
        "files": [csv_path.name],
        "status": "SUCCESS"
    }

    return jsonify(artifact)

# =========================================================
# 📊 NIFTY
# =========================================================

@app.route("/run-daily-nifty", methods=["POST"])
def run_daily_nifty():
    verify_agent(request)
    date = datetime.strptime(request.json["date"], "%Y-%m-%d")
    folder = RAW / "nifty" / date.strftime("%Y/%m/%d")
    folder.mkdir(parents=True, exist_ok=True)

    payload = {"cinfo": json.dumps({"name": "NIFTY 50","startDate": date.strftime("%d-%b-%Y"),"endDate": date.strftime("%d-%b-%Y"),"indexName": "NIFTY 50"})}
    r = requests.post("https://www.niftyindices.com/Backpage.aspx/getHistoricaldatatabletoString", json=payload)

    (folder / "NIFTY50.csv").write_text(r.json()["d"])

    return {"date": request.json["date"], "status": "SUCCESS"}

# =========================================================
# 🏦 GSEC
# =========================================================

@app.route("/run-daily-gsec", methods=["POST"])
def run_daily_gsec():
    verify_agent(request)
    date = datetime.strptime(request.json["date"], "%Y-%m-%d")
    folder = RAW / "gsec" / date.strftime("%Y/%m/%d")
    folder.mkdir(parents=True, exist_ok=True)

    html = requests.get("https://www.rbi.org.in/Scripts/BS_ViewGsecData.aspx").text
    (folder / "gsec.html").write_text(html)

    return {"date": request.json["date"], "status": "SUCCESS"}

# =========================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
