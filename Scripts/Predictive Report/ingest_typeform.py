import requests
import json  # ✅ Add this if not already imported
from Engine.Files.write_supabase_file import write_supabase_file
from datetime import datetime

def process_typeform_submission(data):
    print("=== Typeform webhook triggered ===")
    print(json.dumps(data, indent=2))
    
    form_fields = {
        answer['field']['ref']: answer.get('text') or answer.get('email') or answer.get('choice', {}).get('label')
        for answer in data['form_response']['answers']
    }

    print("=== Extracted Form Fields ===")
    print(json.dumps(form_fields, indent=2))

    # ✅ Add this block to inspect what keys were extracted
    print("=== Extracted Form Fields ===")
    print(json.dumps(form_fields, indent=2))

    file_field = next((a for a in data['form_response']['answers'] if a['type'] == 'file_url'), None)
    if not file_field:
        raise Exception("Missing file upload in Typeform.")

    file_url = file_field['file_url']
    file_response = requests.get(file_url)
    file_content = file_response.text

    

    client_name = form_fields.get('26f95c88-43d4-4540-83b7-0d78e1c9535e', 'unknown').replace(" ", "_")
    timestamp = datetime.utcnow().strftime('%d%m%Y_%H%M')
    filename = f"{client_name}_Question_Context{timestamp}.txt"
    supabase_path = f"panelitix/The Big Question/Predictive Report/Question Context/{filename}"

    write_supabase_file(supabase_path, file_content)

    return {
        "prompt": "client_context",
        "client": form_fields.get("26f95c88-43d4-4540-83b7-0d78e1c9535e", ""),
        "client_context_url": f"https://ribebcjrzcinomtocqdo.supabase.co/storage/v1/object/public/{supabase_path}"
    }
