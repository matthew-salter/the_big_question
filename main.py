from flask import Flask, request, jsonify
import importlib
from Engine.logger import logger

app = Flask(__name__)

@app.route("/", methods=["POST"])
def dispatch_prompt():
    try:
        data = request.get_json(force=True)
        prompt_name = data.get("prompt")
        if not prompt_name:
            return jsonify({"error": "Missing 'prompt' key"}), 400

        # Infer script path: e.g., prompt = client_context → Scripts.Client_Context.client_context
        module_path = f"Scripts.Client_Context.{prompt_name}"
        module = importlib.import_module(module_path)

        logger.info(f"Dispatching prompt: {prompt_name}")
        result = module.run_prompt(data)

        return jsonify(result)

    except Exception as e:
        logger.exception("Error in dispatch_prompt")
        return jsonify({"error": str(e)}), 500
