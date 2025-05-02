from flask import Flask, request, jsonify
import os
import openai
import importlib.util
from dotenv import load_dotenv
from logger import logger

load_dotenv()
app = Flask(__name__)
openai.api_key = os.getenv('OPENAI_API_KEY')

def load_module_from_path(module_name, file_path):
    logger.info(f"🔧 Loading module '{module_name}' from '{file_path}'")
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot find or load module: {module_name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

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

@app.route('/ingest-typeform', methods=['POST'])
def ingest_typeform():
    try:
        logger.info("📨 Received Typeform webhook: /ingest-typeform")
        ingest = load_module_from_path("ingest_typeform", "Scripts/Predictive Report/ingest_typeform.py")
        typeform_payload = ingest.process_typeform_submission(request.json)

        logger.info("📦 Typeform ingestion completed. Triggering client_context prompt.")
        context_runner = load_module_from_path("client_context", "Scripts/Predictive Report/client_context.py")
        context_result = context_runner.run_prompt(typeform_payload)

        logger.info("✅ client_context prompt executed successfully.")
        return jsonify(context_result)

    except Exception as e:
        logger.exception("❌ Failed during /ingest-typeform flow")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/', methods=['POST'])
def handle_webhook():
    data = request.json
    prompt = data.get('prompt')
    if not prompt:
        logger.warning("⚠️ Prompt key missing in request body.")
        return jsonify({"error": "Missing 'prompt' key in request."}), 400

    try:
        logger.info(f"🚦 Dispatching to prompt: {prompt}")

        prompt_map = {
            "client_context": "Scripts/Predictive Report/client_context.py",
            "prompt_1_thinking": "Scripts/Predictive Report/prompt_1_thinking.py",
            "prompt_2b": "Scripts/Predictive Report/prompt_2b.py",
            "prompt_2c": "Scripts/Predictive Report/prompt_2c.py",
            "prompt_3": "Scripts/Predictive Report/prompt_3.py"
        }

        if prompt not in prompt_map:
            logger.error(f"❌ Unknown prompt: {prompt}")
            return jsonify({"error": f"Unknown prompt: {prompt}"}), 400

        module = load_module_from_path(prompt, prompt_map[prompt])
        result = module.run_prompt(data)

        logger.info(f"✅ Prompt '{prompt}' executed successfully.")
        return jsonify(result)

    except Exception as e:
        logger.exception("❌ Error during prompt dispatch")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    logger.info("🚀 Starting Flask server on port 10000")
    app.run(host='0.0.0.0', port=10000)
