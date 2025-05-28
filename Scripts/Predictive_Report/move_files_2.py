from dotenv import load_dotenv
from flask import Flask, request, jsonify
from supabase import create_client, Client
import os

load_dotenv()

app = Flask(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_BUCKET = "storage"  # Update if your bucket name is different
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# Define paths
READ_DIRECTORIES = {
    "Logos": "The_Big_Question/Predictive_Report/Logos",
    "Question_Context": "The_Big_Question/Predictive_Report/Question_Context",
    "Report_and_Section_Tables": "The_Big_Question/Predictive_Report/Ai_Responses/Report_and_Section_Tables"
}

WRITE_DIRECTORIES = {
    "Logos": "The_Big_Question/Write/Assets/Logos",
    "Question_Context": "The_Big_Question/Write/Assets/Question_Context",
    "Report_and_Section_Tables": "The_Big_Question/Write/Ai_Responses/Report_and_Section_Tables"
}


@app.route("/", methods=["POST"])
def handle_directories():
    read_results = {}
    write_results = {}

    for label, path in READ_DIRECTORIES.items():
        try:
            files = supabase.storage.from_(SUPABASE_BUCKET).list(path)
            file_names = [file["name"] for file in files if file["name"] != ".keep"]
            read_results[f"{label}_files_found"] = file_names
        except Exception as e:
            read_results[f"{label}_error"] = f"❌ Failed to list files in: {path} – {str(e)}"
            read_results[f"{label}_files_found"] = []

    for label, path in WRITE_DIRECTORIES.items():
        try:
            files = supabase.storage.from_(SUPABASE_BUCKET).list(path)
            folder_present = any(file["name"] == ".keep" for file in files)
            write_results[f"{label}_folder_exists"] = folder_present
        except Exception as e:
            write_results[f"{label}_folder_error"] = f"❌ Failed to verify folder: {path} – {str(e)}"
            write_results[f"{label}_folder_exists"] = False

    return jsonify({
        "status": "completed",
        "message": "Read and write directory scan complete.",
        "read_directories": read_results,
        "write_directories": write_results
    })


if __name__ == "__main__":
    app.run(debug=True)
