# move_files_2.py

import os
from flask import Flask, request, jsonify
from supabase import create_client
from dotenv import load_dotenv
from logger import logger

load_dotenv()

app = Flask(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

READ_FOLDERS = {
    "Logos": "The_Big_Question/Predictive_Report/Logos",
    "Question_Context": "The_Big_Question/Predictive_Report/Question_Context",
    "Report_and_Section_Tables": "The_Big_Question/Predictive_Report/Ai_Responses/Report_and_Section_Tables"
}

WRITE_FOLDERS = {
    "Logos": "The_Big_Question/Structured_Report_Files/{run_id}/Logos",
    "Question_Context": "The_Big_Question/Structured_Report_Files/{run_id}/Question_Context",
    "Report_and_Section_Tables": "The_Big_Question/Structured_Report_Files/{run_id}/Report_and_Section_Tables"
}


def list_files(bucket, prefix):
    try:
        response = supabase.storage.from_(bucket).list(path=prefix)
        if isinstance(response, list):
            file_names = [f['name'] for f in response if not f['name'].startswith('.')]
            return file_names
        else:
            logger.warning(f"❌ Unexpected response type for listing: {prefix}")
            return []
    except Exception as e:
        logger.warning(f"❌ Failed to list files in: {prefix}")
        return []


@app.route("/", methods=["POST"])
def handle_request():
    payload = request.json or {}
    run_id = payload.get("run_id")

    output = {
        "message": "File listing complete.",
        "status": "completed",
        "read_folders": {},
        "write_folders": {},
    }

    # Read folders — always check
    for label, folder in READ_FOLDERS.items():
        files = list_files("storage", folder)
        output["read_folders"][label] = files or []

    # Write folders — only check if run_id is supplied
    if run_id:
        for label, template in WRITE_FOLDERS.items():
            path = template.format(run_id=run_id)
            files = list_files("storage", path)
            output["write_folders"][label] = files or []

    return jsonify(output)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
