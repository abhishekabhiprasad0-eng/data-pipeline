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

    df = pd.read_csv(csv_file)
    df.columns = [c.strip().upper() for c in df.columns]

    clean_file = CLEAN / f"bhav_{date.strftime('%Y%m%d')}.csv"
    df.to_csv(clean_file, index=False)

    master = pd.read_csv(EQUITY_MASTER)
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
    date = datetime.strptime(request.json["date"], "%Y-%m-%d")
    folder = RAW / "mf" / date.strftime("%Y/%m/%d")
    folder.mkdir(parents=True, exist_ok=True)

    all_rows = []

    for d in [date, date + timedelta(days=1)]:
        url = f"https://www.amfiindia.com/spages/NAVAll.txt?t={d.strftime('%d-%b-%Y')}"
        text = requests.get(url).text

        rows = [r.split(";") for r in text.splitlines() if r and r[0].isdigit()]
        out = folder / f"MF_{d.strftime('%Y%m%d')}.csv"

        with open(out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Scheme Code","ISIN","Name","NAV","Date"])
            for r in rows:
                w.writerow([r[0], r[1], r[3], r[4], r[5]])
                all_rows.append({"Scheme Code": r[0], "ISIN": r[1]})

    master = pd.read_csv(MF_MASTER)
    existing = set(zip(master["Scheme Code"], master["ISIN"]))

    new = [r for r in all_rows if (r["Scheme Code"], r["ISIN"]) not in existing]

    if new:
        pd.concat([master, pd.DataFrame(new)]).to_csv(MF_MASTER, index=False)

    return {"date": request.json["date"], "new_master": len(new), "status": "SUCCESS"}

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
