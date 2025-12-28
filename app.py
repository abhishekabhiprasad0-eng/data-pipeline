import pandas as pd
from datetime import datetime
from pathlib import Path
from flask import Flask, request, send_file, jsonify

app = Flask(__name__)

BASE = Path("data")
OUT  = Path("outputs")
BASE.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

MASTER_FILE = BASE / "Master file.xlsx"

@app.route("/register", methods=["POST"])
def register():
    incoming_file = request.files["file"]
    incoming_path = BASE / "incoming.xlsx"
    incoming_file.save(incoming_path)

    master = pd.read_excel(MASTER_FILE)
    incoming = pd.read_excel(incoming_path)

    key_cols = ["ISIN", "Code", "Series"]
    master["KEY"] = master[key_cols].astype(str).agg("|".join, axis=1)
    incoming["KEY"] = incoming[key_cols].astype(str).agg("|".join, axis=1)

    new_rows = incoming[~incoming["KEY"].isin(master["KEY"])].copy()

    if not new_rows.empty:
        new_rows["Date Created"] = datetime.now().strftime("%d-%m-%Y")
        new_rows["Created in system"] = "Y"
        new_rows["Is active"] = "Y"

        new_rows = new_rows[master.columns.drop("KEY")]
        master = pd.concat([master.drop(columns="KEY"), new_rows], ignore_index=True)
        master.to_excel(MASTER_FILE, index=False)

        out_file = OUT / f"New_Securities_{datetime.now():%d%m%Y}.csv"
        new_rows.to_csv(out_file, index=False)

        return send_file(out_file)

    return "No new securities found"


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files["file"]
    path = OUT / file.filename
    file.save(path)
    return jsonify({"download_url": f"/download/{file.filename}"})


@app.route("/download/<name>")
def download(name):
    return send_file(OUT / name, as_attachment=True)


app.run(host="0.0.0.0", port=10000)
