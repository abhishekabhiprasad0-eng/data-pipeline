import csv
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_file, abort

app = Flask(__name__)

@app.route("/", methods=["GET"])
def root():
    return jsonify({"status": "ok", "service": "data-pipeline"}), 200

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok", "service": "data-pipeline"}), 200

DATA = Path("data")
OUT  = Path("outputs")
DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

# 🔒 DO NOT RENAME — MATCH AGENT CONTRACT
EQUITY_MASTER  = DATA / "Equity Master_System.csv"
MF_MASTER      = DATA / "MF Master_System.csv"
INDICES_MASTER = DATA / "Indicies Master_System.csv"


# ---------------- CORE FUNCTION ----------------

def process_keys(records, master_file, key_map):
    if not master_file.exists():
        abort(500, f"Master file missing: {master_file.name}")

    with open(master_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames

        if not fieldnames:
            abort(500, f"Master file has no header: {master_file.name}")

        for k, col in key_map.items():
            if col not in fieldnames:
                abort(500, f"Missing column '{col}' in {master_file.name}")

        existing = set()
        for row in reader:
            key = tuple(row[key_map[k]].strip() for k in key_map)
            existing.add(key)

    new_rows = []
    for r in records:
        key = tuple(str(r[k]).strip() for k in key_map)
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
                row[col] = r[k]
            row["Date Created"] = datetime.now().strftime("%d-%m-%Y")
            row["Created in system"] = "Y"
            row["Is active"] = "Y"
            writer.writerow(row)

    return new_rows


# ---------------- API ----------------

@app.route("/check-securities", methods=["POST"])
def check_securities():
    payload = request.get_json(force=True)

    new_equity = process_keys(
        payload.get("equity", []),
        EQUITY_MASTER,
        {"isin": "ISIN", "symbol": "Code", "series": "Series"}
    )

    new_mf = process_keys(
        payload.get("mf", []),
        MF_MASTER,
        {"scheme_code": "Scheme Code", "isin": "ISIN"}
    )

    new_indices = process_keys(
        payload.get("indices", []),
        INDICES_MASTER,
        {"index_code": "Code", "index_name": "Index Name"}
    )

    return jsonify({
        "new_equity": new_equity,
        "new_mf": new_mf,
        "new_indices": new_indices
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
