import openai
import os
import re

def run_prompt(data):
    # Extract the incoming variables
    client = data.get('client')
    client_website_url = data.get('client_website_url')

    # Load the correct prompt template
    prompt_path = 'Prompts/Client Context/client_context.txt'
    with open(prompt_path, 'r') as f:
        prompt_template = f.read()

    # Fill in the prompt
    prompt = prompt_template.format(
        client=client,
        client_website_url=client_website_url
    )

    # Send to OpenAI
    response = openai.chat.completions.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": "You are a professional, commodity report writing analyst."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2
    )

    # Extract the raw output
    raw_output = response.choices[0].message.content

    # Clean the output:
    # 1. Remove any "**CLIENT CONTEXT**" labels
    # 2. Pull out the actual business description
    try:
        # Step 1: Remove bold text and braces if any
        cleaned_output = raw_output.replace("**", "").replace("{", "").replace("}", "").strip()

        # Step 2: Find the first quoted block that is not the key label
        match = re.findall(r'\"(.*?)\"', cleaned_output, re.DOTALL)

        if match and len(match) >= 1:
            # We assume the *last* quoted string is the business summary (safer than taking the first)
            client_context_text = match[-1].strip()
        else:
            client_context_text = cleaned_output.strip()

    except Exception as e:
        return {"error": f"Error cleaning client context: {str(e)}", "raw_response": raw_output}

    # Return BOTH clean text and file ID (if needed)
    return {
        "client_context": client_context_text,
        "file_id": data.get('file_id')  # Pass through if available
    }
