import openai
import os
import re
from datetime import datetime
from Engine.Files.write_supabase_file import write_supabase_file
from logger import logger

def run_prompt(data):
    logger.info("🚀 Running client context prompt")

    # === Extract incoming variables ===
    client = data.get('client')
    client_website_url = data.get('client_website_url')
    logger.info("🔍 Client: %s | Website: %s", client, client_website_url)

    # === Load prompt template ===
    prompt_path = 'Prompts/Client Context/client_context.txt'
    try:
        with open(prompt_path, 'r') as f:
            prompt_template = f.read()
    except Exception as e:
        logger.exception("❌ Failed to read prompt template")
        return {"error": f"Failed to load prompt: {str(e)}"}

    # === Inject variables ===
    try:
        prompt = prompt_template.format(
            client=client,
            client_website_url=client_website_url
        )
        logger.debug("📄 Final prompt:\n%s", prompt)
    except Exception as e:
        logger.exception("❌ Failed to fill prompt template")
        return {"error": f"Failed to fill prompt: {str(e)}"}

    # === Send prompt to OpenAI ===
    try:
        logger.info("🧠 Sending prompt to OpenAI")
        response = openai.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "You are a professional, commodity report writing analyst."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        logger.info("🧠 Received response from OpenAI")
    except Exception as e:
        logger.exception("❌ OpenAI API call failed")
        return {"error": f"OpenAI request failed: {str(e)}"}

    # === Parse and clean AI output ===
    try:
        raw_output = response.choices[0].message.content
        logger.debug("📝 Raw output:\n%s", raw_output)

        cleaned_output = raw_output.replace("**", "").replace("{", "").replace("}", "").strip()
        match = re.findall(r'\"(.*?)\"', cleaned_output, re.DOTALL)
        if match and len(match) >= 1:
            client_context_text = match[-1].strip()
        else:
            client_context_text = cleaned_output.strip()

        logger.info("✅ Client context extracted successfully")
    except Exception as e:
        logger.exception("❌ Failed to clean or parse client context")
        return {
            "error": f"Error cleaning client context: {str(e)}",
            "raw_response": raw_output
        }

    # === Write AI response to Supabase ===
    try:
        filename = f"{client}_Client_Context_{datetime.utcnow().strftime('%d%m%Y_%H%M')}.txt"
        supabase_path = f"panelitix/The Big Question/Predictive Report/Ai Responses/{filename}"
        write_supabase_file(supabase_path, client_context_text)
        logger.info(f"✅ Client context written to Supabase: {supabase_path}")
    except Exception as e:
        logger.exception("❌ Failed to write client context to Supabase")
        return {"error": f"Supabase write failed: {str(e)}"}

    # === Return structured payload ===
    return {
        "client_context": client_context_text,
        "client_context_url": f"https://ribebcjrzcinomtocqdo.supabase.co/storage/v1/object/public/{supabase_path}",
        "file_id": data.get('file_id')  # optional
    }
