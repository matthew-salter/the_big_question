from flask import Flask, request, jsonify
import os
import openai
import importlib.util
from dotenv import load_dotenv
from logger import logger

load_dotenv()
app = Flask(__name__)

openai.api_key = os.getenv('OPENAI_API_KEY')


# === HELPER: Load Python Module Dynamically ===
def load_module_from_path(module_name, file_path):
    logger.info(f"🔧 Loading module '{module_name}' from '{file_path}'")
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None:
        raise ImportError(f"❌ Cannot find spec for module: {module_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# === ROUTE: TEST SUPABASE FILE READ ===
@app.route('/test-supabase-read', methods=['GET'])
def test_supabase_read():
    from Engine.Files.read_supabase_file import read_supabase_file
    test_url = "https://ribebcjrzcinomtocqdo.supabase.co/storage/v1/object/public/panelitix/The%20Big%20Question/Predictive%20Report/Question%20Context/question_context_test.txt"
    try:
        logger.info("🧪 Testing Supabase file read")
        content = read_supabase_file(test_url)
        return jsonify({"success": True, "content": content})
    except Exception as e:
        logger.exception("❌ Error during test-supabase-read")
        return jsonify({"success": False, "error": str(e)}), 500


# === ROUTE: INGEST TYPEFORM SUBMISSION ===
@app.route('/ingest-typeform', methods=['POST'])
def ingest_typeform():
    try:
        logger.info("📨 Received Typeform webhook: /ingest-typeform")
        ingest = load_module_from_path("ingest_typeform", "Scripts/Predictive Report/ingest_typeform.py")
        result = ingest.process_typeform_submission(request.json)

        logger.info("📦 Typeform ingestion completed. Triggering client_context prompt.")
        context_runner = load_module_from_path("client_context", "Scripts/Client Context/client_context.py")
        response = context_runner.run_prompt(result)

        logger.info("✅ client_context prompt executed.")
        return jsonify(response)
    except Exception as e:
        logger.exception("❌ Failed during /ingest-typeform flow")
        return jsonify({"success": False, "error": str(e)}), 500


# === ROUTE: MAIN DISPATCH FOR ANY PROMPT ===
@app.route('/', methods=['POST'])
def handle_webhook():
    data = request.json
    logger.info("🧠 Main webhook received")
    prompt = data.get('prompt')
    if not prompt:
        return jsonify({"error": "Missing 'prompt' key in request."}), 400

    prompt_map = {
        "client_context": "Scripts/Client Context/client_context.py",
        "prompt_1_thinking": "Scripts/Predictive Report/prompt_1_thinking.py",
        "prompt_2b": "Scripts/Predictive Report/prompt_2b.py",
        "prompt_2c": "Scripts/Predictive Report/prompt_2c.py",
        "prompt_3": "Scripts/Predictive Report/prompt_3.py"
    }

    if prompt not in prompt_map:
        return jsonify({"error": f"Unknown prompt: {prompt}"}), 400

    try:
        module = load_module_from_path(prompt, prompt_map[prompt])
        response = module.run_prompt(data)
        logger.info(f"✅ Prompt '{prompt}' executed successfully")
        return jsonify(response)
    except Exception as e:
        logger.exception("❌ Error handling main webhook prompt")
        return jsonify({"error": str(e)}), 500


# === LAUNCH SERVER ===
if __name__ == '__main__':
    logger.info("🚀 Starting Flask server on port 10000")
    app.run(host='0.0.0.0', port=10000)
