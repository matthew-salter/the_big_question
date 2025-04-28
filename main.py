from flask import Flask, request, jsonify
import importlib
import os
import openai
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Load your OpenAI API key
openai.api_key = os.getenv('OPENAI_API_KEY')

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
            module = importlib.import_module('Scripts.Client_Context.client_context')
        elif prompt == "prompt_2a":
            module = importlib.import_module('Scripts.Commodity_Report.prompt_2a')
        elif prompt == "prompt_2b":
            module = importlib.import_module('Scripts.Commodity_Report.prompt_2b')
        elif prompt == "prompt_2c":
            module = importlib.import_module('Scripts.Commodity_Report.prompt_2c')
        elif prompt == "prompt_3":
            module = importlib.import_module('Scripts.Commodity_Report.prompt_3')
        else:
            return jsonify({"error": f"Unknown prompt: {prompt}"}), 400

        # Call the script's main function
        response = module.run_prompt(data)
        return jsonify(response)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

