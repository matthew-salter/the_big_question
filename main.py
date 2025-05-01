from flask import Flask, request, jsonify
import importlib
import os
import openai
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Load your OpenAI API key
openai.api_key = os.getenv('OPENAI_API_KEY')

# === ROUTE: TEST SUPABASE FILE READ ===
@app.route('/test-supabase-read', methods=['GET'])
def test_supabase_read():
    from Engine.Files.read_supabase_file import read_supabase_file
    test_url = "https://ribebcjrzcinomtocqdo.supabase.co/storage/v1/object/public/panelitix/The%20Big%20Question/Predictive%20Report/Question%20Context/question_context_test.txt"
    try:
        content = read_supabase_file(test_url)
        return jsonify({"success": True, "content": content})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# === ROUTE: MAIN WEBHOOK ===
@app.route('/', methods=['POST'])
def handle_webhook():
    data = request.json

    # Read which prompt they want to trigger
    prompt = data.get('prompt')
    if not prompt:
        return jsonify({"error": "Missing 'prompt' key in request."}), 400

    try:
        # Dynamically import the correct script from Scripts folder
        if prompt == "client_context":
            module = importlib.import_module('Scripts.Client Context.client_context')
        elif prompt == "prompt_1_thinking":
            module = importlib.import_module('Scripts.Commodity Report.prompt_1_thinking')
        elif prompt == "prompt_2b":
            module = importlib.import_module('Scripts.Commodity Report.prompt_2b')
        elif prompt == "prompt_2c":
            module = importlib.import_module('Scripts.Commodity Report.prompt_2c')
        elif prompt == "prompt_3":
            module = importlib.import_module('Scripts.Commodity Report.prompt_3')
        else:
            return jsonify({"error": f"Unknown prompt: {prompt}"}), 400

        # Call the script's main function
        response = module.run_prompt(data)
        return jsonify(response)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# === FLASK APP START ===
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
