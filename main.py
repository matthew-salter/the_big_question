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
        thread = threading.Thread(target=module.run_prompt, args=(data,), daemon=True)
        thread.start()

        return jsonify({
            "status": "processing",
            "run_id": data.get("run_id")
        })

    except Exception as e:
        logger.exception("Error in dispatch_prompt")
        return jsonify({"error": str(e)}), 500
