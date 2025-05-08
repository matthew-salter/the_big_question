from flask import Flask, request, jsonify
from Scripts.Ingest.ingest_typeform import process_typeform_submission
import importlib
import threading
from logger import logger

@app.route("/ingest-typeform", methods=["POST"])
def ingest_typeform():
    try:
        data = request.get_json(force=True)
        process_typeform_submission(data)
        return jsonify({"status": "success", "message": "Typeform files are being processed."})
    except Exception as e:
        logger.exception("Error in ingest_typeform")
        return jsonify({"error": str(e)}), 500

app = Flask(__name__)

# Prompts that should wait for the file to be read and return the result synchronously
BLOCKING_PROMPTS = {"read_client_context"}

@app.route("/", methods=["POST"])
def dispatch_prompt():
    try:
        data = request.get_json(force=True)
        prompt_name = data.get("prompt")
        if not prompt_name:
            return jsonify({"error": "Missing 'prompt' key"}), 400

        module_path = f"Scripts.Client_Context.{prompt_name}"
        module = importlib.import_module(module_path)

        logger.info(f"Dispatching prompt asynchronously: {prompt_name}")

        result_container = {}

        def run_and_capture():
            try:
                result = module.run_prompt(data)
                result_container.update(result or {})
            except Exception:
                logger.exception("Background prompt execution failed.")

        thread = threading.Thread(target=run_and_capture)
        thread.start()

        if prompt_name in BLOCKING_PROMPTS:
            thread.join()
            return jsonify(result_container)
        else:
            return jsonify({
                "status": "processing",
                "message": "Script launched, run_id will be available via follow-up.",
                "run_id": data.get("run_id")
            })

    except Exception as e:
        logger.exception("Error in dispatch_prompt")
        return jsonify({"error": str(e)}), 500

