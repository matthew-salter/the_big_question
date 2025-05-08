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
        
        # container to store the result
        result_container = {}

        # inline thread target that updates result_container
        def run_and_capture():
            result_container.update(module.run_prompt(data))

        thread = threading.Thread(target=run_and_capture, daemon=True)
        thread.start()
        thread.join(timeout=1.0)

        if "run_id" in result_container:
            return jsonify({
                "status": "processing",
                "run_id": result_container["run_id"]
            })
        else:
            return jsonify({"status": "processing", "message": "Script launched, run_id will be available via follow-up."})

    except Exception as e:
        logger.exception("Error in dispatch_prompt")
        return jsonify({"error": str(e)}), 500
