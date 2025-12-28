import pandas as pd
from datetime import datetime
from pathlib import Path
from flask import Flask, request, send_file

app = Flask(__name__)

BASE = Path("data")
BASE.mkdir(exist_ok=True)

MASTER_FILE = BASE / "Master file.xlsx"

@app.route("/process", methods=["POST"])
def process():
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
        updated_master = pd.concat([master.drop(columns="KEY"), new_rows], ignore_index=True)
        updated_master.to_excel(MASTER_FILE, index=False)

        out_file = BASE / f"New_Securities_{datetime.now():%d%m%Y}.csv"
        new_rows.to_csv(out_file, index=False)
        return send_file(out_file)

    return "No new securities found"

app.run(host="0.0.0.0", port=10000)
