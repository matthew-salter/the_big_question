import openai
from logger import logger
import os

def safe_escape(value):
    return str(value).replace("{", "{{").replace("}", "}}")

def run_prompt(data):
    try:
        client = data["client"]
        website = data["client_website_url"]

        with open("Prompts/Client_Context/client_context.txt", "r", encoding="utf-8") as f:
            template = f.read()

        filled_prompt = template.format(
            client=safe_escape(client),
            client_website_url=safe_escape(website)
        )

        response = openai.ChatCompletion.create(
            model="gpt-4",
            temperature=0.2,
            messages=[{"role": "user", "content": filled_prompt}]
        )

        output = response.choices[0].message["content"].strip()
        logger.info("AI response received for client_context")
        return {"status": "complete", "result": output}

    except Exception as e:
        logger.exception("Error in run_prompt")
        return {"status": "error", "message": str(e)}
