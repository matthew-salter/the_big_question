from flask import Flask, request, jsonify
import os
import openai
import importlib.util
from dotenv import load_dotenv
from Engine.logger import logger

load_dotenv()
app = Flask(__name__)

openai.api_key = os.getenv('OPENAI_API_KEY')


# === HELPER FUNCTION ===
def load_module_from_path(module_name, file_path):
    logger.info(f"Loading module '{module_name}' from '{file_path}'")
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None:
        raise ImportError(f"Cannot find spec for module {module_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# === ROUTE: TEST SUPABASE FILE READ ===
@app.route('/test-supabase-read', methods=['GET'])
def test_supabase_read():
    from Engine.Files.read_supabase_file import read_supabase_file
    test_url = "https://ribebcjrzcinomtocqdo.supabase.co/storage/v1/object/public/panelitix/The%20Big%20Question/Predictive%20Report/Question%20Context/question_context_test.txt"
    try:
        logger.info("Testing Supabase file read")
        content = read_supabase_file(test_url)
        return jsonify({"success": True, "content": content})
    except Exception as e:
        logger.exception("Error during test-supabase-read")
        return jsonify({"success": False, "error": str(e)}), 500


# === ROUTE: INGEST TYPEFORM SUBMISSION ===
@app.route('/ingest-typeform', methods=['POST'])
def ingest_typeform():
    try:
        logger.info("Received Typeform webhook: /ingest-typeform")
        module = load_module_from_path(
            "ingest_typeform", "Scripts/Predictive Report/ingest_typeform.py"
        )
        result = module.process_typeform_submission(request.json)
        logger.info("Typeform processing completed successfully.")
        return jsonify(result)
    except Exception as e:
        logger.exception("Error in ingest-typeform")
        return jsonify({"success": False, "error": str(e)}), 500


# === ROUTE: MAIN WEBHOOK ===
@app.route('/', methods=['POST'])
def handle_webhook():
    data = request.json
    logger.info("Main webhook received.")
    prompt = data.get('prompt')
    if not prompt:
        logger.warning("Prompt missing in request body.")
        return jsonify({"error": "Missing 'prompt' key in request."}), 400

    try:
        logger.info(f"Dispatching to prompt: {prompt}")
        if prompt == "client_context":
            module = load_module_from_path("client_context", "Scripts/Client Context/client_context.py")
        elif prompt == "prompt_1_thinking":
            module = load_module_from_path("prompt_1_thinking", "Scripts/Predictive Report/prompt_1_thinking.py")
        elif prompt == "prompt_2b":
            module = load_module_from_path("prompt_2b", "Scripts/Predictive Report/prompt_2b.py")
        elif prompt == "prompt_2c":
            module = load_module_from_path("prompt_2c", "Scripts/Predictive Report/prompt_2c.py")
        elif prompt == "prompt_3":
            module = load_module_from_path("prompt_3", "Scripts/Predictive Report/prompt_3.py")
        else:
            logger.error(f"Unknown prompt: {prompt}")
            return jsonify({"error": f"Unknown prompt: {prompt}"}), 400

        response = module.run_prompt(data)
        logger.info(f"Prompt '{prompt}' executed successfully.")
        return jsonify(response)

    except Exception as e:
        logger.exception("Error handling main webhook")
        return jsonify({"error": str(e)}), 500


# === START FLASK APP ===
if __name__ == '__main__':
    logger.info("Starting Flask server on port 10000")
    app.run(host='0.0.0.0', port=10000)
