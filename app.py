import csv
from datetime import datetime
from pathlib import Path
from flask import Flask, request, send_file, jsonify

app = Flask(__name__)

BASE = Path("data")
OUT  = Path("outputs")

BASE.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

# ----------------- MASTER FILE PATHS -----------------

EQUITY_MASTER  = BASE / "equity_master.csv"
MF_MASTER      = BASE / "mf_master.csv"
INDICES_MASTER = BASE / "indices_master.csv"

# ----------------- INITIALIZE MASTER FILES -----------------

def init_master(file_path, headers):
    if not file_path.exists():
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)

init_master(EQUITY_MASTER,  ["isin", "symbol", "series"])
init_master(MF_MASTER,      ["scheme_code", "isin"])
init_master(INDICES_MASTER, ["index_code", "index_name"])

# ----------------- CORE LOGIC -----------------

def process_keys(records, master_file, fields):
    existing = set()

    with open(master_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = tuple(row[field] for field in fields)
            existing.add(key)

    new_rows = []
    for r in records:
        key = tuple(r[field] for field in fields)
        if key not in existing:
            new_rows.append(r)
            existing.add(key)

    if new_rows:
        with open(master_file, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            for r in new_rows:
                writer.writerow({k: r[k] for k in fields})

    return new_rows

# ----------------- API ENDPOINTS -----------------

@app.route("/check-securities", methods=["POST"])
def check_securities():
    payload = request.json

    new_equity = process_keys(payload.get("equity", []),  EQUITY_MASTER,  ["isin", "symbol", "series"])
    new_mf     = process_keys(payload.get("mf", []),      MF_MASTER,      ["scheme_code", "isin"])
    new_index  = process_keys(payload.get("indices", []), INDICES_MASTER, ["index_code", "index_name"])

    return jsonify({
        "new_equity": new_equity,
        "new_mf": new_mf,
        "new_indices": new_index
    })

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files["file"]
    path = OUT / file.filename
    file.save(path)
    return jsonify({"download_url": f"/download/{file.filename}"})

@app.route("/download/<name>")
def download(name):
    return send_file(OUT / name, as_attachment=True)

# ----------------- SERVER -----------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
