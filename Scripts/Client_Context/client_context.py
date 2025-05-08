from openai import OpenAI
from logger import logger

def safe_escape(value):
    return str(value).replace("{", "{{").replace("}", "}}")

def run_prompt(data):
    try:
        client_name = data["client"]
        website = data["client_website_url"]

        with open("Prompts/Client_Context/client_context.txt", "r", encoding="utf-8") as f:
            template = f.read()

        prompt = template.format(
            client=safe_escape(client_name),
            client_website_url=safe_escape(website)
        )

        client = OpenAI()  # uses OPENAI_API_KEY from environment

        response = client.chat.completions.create(
            model="gpt-4",
            temperature=0.2,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        result = response.choices[0].message.content.strip()

        logger.info("AI response received for client_context")
        return {
            "status": "complete",
            "result": result
        }

    except Exception as e:
        logger.exception("Error in run_prompt")
        return {
            "status": "error",
            "message": str(e)
        }
from openai import OpenAI
from logger import logger

def safe_escape(value):
    return str(value).replace("{", "{{").replace("}", "}}")

def run_prompt(data):
    try:
        client_name = data["client"]
        website = data["client_website_url"]

        with open("Prompts/Client_Context/client_context.txt", "r", encoding="utf-8") as f:
            template = f.read()

        prompt = template.format(
            client=safe_escape(client_name),
            client_website_url=safe_escape(website)
        )

        client = OpenAI()  # uses OPENAI_API_KEY from environment

        response = client.chat.completions.create(
            model="gpt-4",
            temperature=0.2,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        result = response.choices[0].message.content.strip()

        logger.info("AI response received for client_context")
        return {
            "status": "complete",
            "result": result
        }

    except Exception as e:
        logger.exception("Error in run_prompt")
        return {
            "status": "error",
            "message": str(e)
        }
