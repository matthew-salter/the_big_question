# Scripts/Predicitive Report/ingest_typeform.py

import requests
from Engine.Files.write_supabase_file import write_supabase_file

def process_typeform_submission(data):
    form_fields = {
        answer['field']['ref']: answer.get('text') or answer.get('email') or answer.get('choice', {}).get('label')
        for answer in data['form_response']['answers']
    }

    file_field = next((a for a in data['form_response']['answers'] if a['type'] == 'file_url'), None)
    if not file_field:
        raise Exception("Missing file upload in Typeform.")

    file_url = file_field['file_url']
    file_response = requests.get(file_url)
    file_content = file_response.text

    # Save to Supabase
    client_name = form_fields.get('client_name', 'unknown').replace(" ", "_")
    supabase_path = f"panelitix/The Big Question/Client Contexts/{client_name}_context.txt"
    write_supabase_file(supabase_path, file_content)

    return {
        "prompt": "client_context",
        "client": form_fields.get("client_name", ""),
        "client_context_url": f"https://<your-project-ref>.supabase.co/storage/v1/object/public/{supabase_path}"
    }
