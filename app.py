import csv
import os
import io
import json
import zipfile
import requests
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_file, abort
from flask_cors import CORS

# =========================
# 🚀 APP INITIALIZATION
# =========================

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, allow_headers=["Content-Type", "X-AGENT-KEY"])

# =========================
# 🔐 AGENT AUTHENTICATION
# =========================

AGENT_KEY = os.environ.get("FIN_AGENT_API_KEY")

def verify_agent(req):
    key = req.headers.get("X-AGENT-KEY")
    if key != AGENT_KEY:
        abort(401, "Unauthorized agent")

# =========================
# 🩺 HEALTH ENDPOINTS
# =========================

@app.route("/", methods=["GET"])
def root():
    return jsonify({"status": "ok", "service": "data-pipeline"}), 200

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "service": "data-pipeline"}), 200

@app.route("/handshake", methods=["POST"])
def handshake():
    verify_agent(request)
    return jsonify({
        "status": "ready",
        "service": "data-pipeline",
        "version": "1.0",
        "time": datetime.utcnow().isoformat()
    })

# =========================
# 🗂 FILE SYSTEM SETUP
# =========================

DATA = Path("data")
OUT  = Path("outputs")
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

# 🔒 MASTER FILES
EQUITY_MASTER  = DATA / "Equity Master_System.csv"
MF_MASTER      = DATA / "MF Master_System.csv"
INDICES_MASTER = DATA / "Indicies Master_System.csv"

# =========================
# 📦 NSE STORAGE LAYOUT
# =========================

BASE_STORAGE = Path("storage")
RAW = BASE_STORAGE / "raw" / "nse"
ARTIFACTS = BASE_STORAGE / "artifacts" / "daily_reports"

RAW.mkdir(parents=True, exist_ok=True)
ARTIFACTS.mkdir(parents=True, exist_ok=True)

# =========================
# 🧠 MASTER SYNC ENGINE
# =========================

def process_keys(records, master_file, key_map):
    if not master_file.exists():
        abort(500, f"Master file missing: {master_file.name}")

    with open(master_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames

        existing = set()
        for row in reader:
            key = tuple(str(row.get(key_map[k], "")).strip() for k in key_map)
            existing.add(key)

    new_rows = []
    for r in records:
        key = tuple(str(r.get(k, "")).strip() for k in key_map)
        if key not in existing:
            new_rows.append(r)
            existing.add(key)

    if not new_rows:
        return []

    with open(master_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        for r in new_rows:
            row = {col: "" for col in fieldnames}
            for k, col in key_map.items():
                row[col] = r.get(k, "")
            writer.writerow(row)

    return new_rows

# =========================
# 🌐 API ENDPOINTS
# =========================

@app.route("/check-securities", methods=["POST"])
def check_securities():
    verify_agent(request)
    payload = request.get_json(force=True)

    return jsonify({
        "new_equity": process_keys(payload.get("equity", []), EQUITY_MASTER, {"isin":"ISIN","symbol":"Code","series":"Series"}),
        "new_mf": process_keys(payload.get("mf", []), MF_MASTER, {"scheme_code":"Scheme Code","isin":"ISIN"}),
        "new_indices": process_keys(payload.get("indices", []), INDICES_MASTER, {"index_code":"Code","index_name":"Index Name"})
    })

@app.route("/upload", methods=["POST"])
def upload():
    verify_agent(request)
    file = request.files["file"]
    path = OUT / file.filename
    file.save(path)
    return jsonify({"download_url": f"/download/{file.filename}"})

@app.route("/download/<name>")
def download(name):
    verify_agent(request)
    return send_file(OUT / name, as_attachment=True)

# ===============================
# 🧾 DAILY NSE ENGINE
# ===============================

def build_paths(date: datetime):
    base = RAW / date.strftime("%Y") / date.strftime("%m") / date.strftime("%d")
    base.mkdir(parents=True, exist_ok=True)
    return base

@app.route("/run-daily-nse", methods=["POST"])
def run_daily_nse():
    verify_agent(request)

    run_date = datetime.strptime(request.json["date"], "%Y-%m-%d")
    folder = build_paths(run_date)

    fname = f"BhavCopy_NSE_CM_0_0_0_{run_date.strftime('%Y%m%d')}_F_0000.csv.zip"
    url = f"https://archives.nseindia.com/content/cm/{fname}"

    zip_path = folder / fname
    r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    zip_path.write_bytes(r.content)

    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        z.extractall(folder)

    artifact = {
        "date": run_date.strftime("%Y-%m-%d"),
        "status": "SUCCESS",
        "files": [f.name for f in folder.iterdir()]
    }

    report_path = ARTIFACTS / f"{run_date.strftime('%Y-%m-%d')}.json"
    report_path.write_text(json.dumps(artifact, indent=2))

    return jsonify(artifact)

@app.route("/list-nse-files")
def list_nse_files():
    base = RAW
    result = {}
    for path in base.rglob("*"):
        if path.is_file():
            result[str(path.relative_to(RAW))] = path.stat().st_size
    return jsonify(result)

# ===============================
# 🤖 AGENT COMMAND BRIDGE
# ===============================

@app.route("/agent-command", methods=["POST"])
def agent_command():
    verify_agent(request)

    payload = request.get_json(force=True)
    command = payload.get("command", "").strip().lower()

    if not command.startswith("start "):
        return jsonify({"error": "Invalid command. Use: start YYYY-MM-DD bhav"}), 400

    try:
        _, date_str, mode = command.split()

        if mode != "bhav":
            return jsonify({"error": "Invalid mode. Only 'bhav' supported."}), 400

        # 🔗 Call your existing NSE engine internally
        return run_daily_nse_internal(date_str)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def run_daily_nse_internal(date_str):
    run_date = datetime.strptime(date_str, "%Y-%m-%d")

    # Build a fake request payload and reuse your real engine
    class DummyRequest:
        json = {"date": date_str}

    global request
    old_request = request
    request = DummyRequest()

    response = run_daily_nse()

    request = old_request
    return response

# =========================
# 🏁 SERVER
# =========================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
