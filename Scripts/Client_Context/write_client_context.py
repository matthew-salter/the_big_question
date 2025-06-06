import uuid
import json
from openai import OpenAI
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

def safe_escape(value):
    return str(value).replace("{", "{{").replace("}", "}}")

def run_prompt(data):
    try:
        run_id = data.get("run_id") or str(uuid.uuid4())
        data["run_id"] = run_id  # ensure it's injected if missing

        client_name = data["client"]
        website = data["client_website_url"]

        # Load prompt template
        with open("Prompts/Client_Context/client_context.txt", "r", encoding="utf-8") as f:
            template = f.read()

        # Format prompt with escaped input
        prompt = template.format(
            client=safe_escape(client_name),
            client_website_url=safe_escape(website)
        )

        # Send prompt to OpenAI
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4",
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}]
        )

        raw_result = response.choices[0].message.content.strip()

        # Try parsing the JSON and extract the value
        try:
            parsed_json = json.loads(raw_result)
            formatted_result = parsed_json.get("CLIENT CONTEXT", "").strip()
            if not formatted_result:
                logger.warning("CLIENT CONTEXT key missing or empty in AI response.")
        except json.JSONDecodeError:
            logger.error("AI response was not valid JSON. Writing raw output.")
            formatted_result = raw_result

        supabase_path = f"Predictive_Report/Ai_Responses/Client_Context/{run_id}.txt"
        write_supabase_file(supabase_path, formatted_result)
        logger.info(f"AI response written to Supabase at {supabase_path}")

    except Exception:
        logger.exception("Error in run_prompt")
