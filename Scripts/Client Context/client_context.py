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

    # Now simply extract the real text between the quotation marks
    # Use a regular expression to pull out the text inside the first pair of quotes
    match = re.search(r'\"(.*?)\"', raw_output, re.DOTALL)
    if match:
        client_context = match.group(1).strip()
    else:
        client_context = raw_output.strip()  # fallback if no match found

    # Return the clean text directly
    return {"client_context": client_context}
