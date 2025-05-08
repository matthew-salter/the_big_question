from flask import Flask, request, jsonify
import importlib
import threading
from logger import logger

app = Flask(__name__)

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

        # Run prompt in background
        def run_and_log():
            try:
                module.run_prompt(data)
            except Exception:
                logger.exception("Background prompt execution failed.")

        thread = threading.Thread(target=run_and_log)
        thread.start()

        # Expect module.run_prompt to inject run_id into data before return
        return jsonify({
            "status": "processing",
            "message": "Script launched, run_id will be available via follow-up.",
            "run_id": data.get("run_id")
        })

    except Exception as e:
        logger.exception("Error in dispatch_prompt")
        return jsonify({"error": str(e)}), 500

