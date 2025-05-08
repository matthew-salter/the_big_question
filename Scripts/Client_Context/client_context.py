import uuid
from openai import OpenAI
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

def safe_escape(value):
    return str(value).replace("{", "{{").replace("}", "}}")

def run_prompt(data):
    try:
        client_name = data["client"]
        website = data["client_website_url"]
        run_id = str(uuid.uuid4())

        with open("Prompts/Client_Context/client_context.txt", "r", encoding="utf-8") as f:
            template = f.read()

        prompt = template.format(
            client=safe_escape(client_name),
            client_website_url=safe_escape(website)
        )

        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4",
            temperature=0.2,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        result = response.choices[0].message.content.strip()

        # Write raw text to Supabase (not JSON encoded)
        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/Client_Context/{run_id}.txt"
        write_supabase_file(supabase_path, result)

        logger.info(f"AI response written to Supabase at {supabase_path}")

    except Exception as e:
        logger.exception("Error in run_prompt")
