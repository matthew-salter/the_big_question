import openai
import os

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

    # Extract and return only the assistant's reply
    output = response.choices[0].message.content
    return {"output": output}
