import openai
import os
import re
import logging

logger = logging.getLogger(__name__)

def run_prompt(data):
    logger.info("🚀 Running client context prompt")

    # Extract the incoming variables
    client = data.get('client')
    client_website_url = data.get('client_website_url')
    logger.info("🔍 Client: %s | Website: %s", client, client_website_url)

    # Load the correct prompt template
    prompt_path = 'Prompts/Client Context/client_context.txt'
    try:
        with open(prompt_path, 'r') as f:
            prompt_template = f.read()
    except Exception as e:
        logger.exception("❌ Failed to read prompt template")
        return {"error": f"Failed to load prompt: {str(e)}"}

    # Fill in the prompt
    try:
        prompt = prompt_template.format(
            client=client,
            client_website_url=client_website_url
        )
    except Exception as e:
        logger.exception("❌ Failed to fill prompt template")
        return {"error": f"Failed to fill prompt: {str(e)}"}

    logger.debug("📄 Final prompt:\n%s", prompt)

    # Send to OpenAI
    try:
        response = openai.chat.completions.create(
            model="gpt-4-turbo",
            messages=[
                {"role": "system", "content": "You are a professional, commodity report writing analyst."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
    except Exception as e:
        logger.exception("❌ OpenAI API call failed")
        return {"error": f"OpenAI request failed: {str(e)}"}

    # Extract the raw output
    try:
        raw_output = response.choices[0].message.content
        logger.debug("📝 Raw output:\n%s", raw_output)
    except Exception as e:
        logger.exception("❌ Failed to extract response content")
        return {"error": f"Failed to extract OpenAI response: {str(e)}"}

    # Clean the output
    try:
        cleaned_output = raw_output.replace("**", "").replace("{", "").replace("}", "").strip()
        match = re.findall(r'\"(.*?)\"', cleaned_output, re.DOTALL)
        if match and len(match) >= 1:
            client_context_text = match[-1].strip()
        else:
            client_context_text = cleaned_output.strip()
        logger.info("✅ Client context extracted successfully")
    except Exception as e:
        logger.exception("❌ Failed to clean or parse client context")
        return {"error": f"Error cleaning client context: {str(e)}", "raw_response": raw_output}

    return {
        "client_context": client_context_text,
        "file_id": data.get('file_id')  # optional, pass-through
    }
