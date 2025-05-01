import requests
from Engine.Files.write_supabase_file import write_supabase_file

# Map field refs to internal keys
FIELD_MAP = {
    "26f95c88-43d4-4540-83b7-0d78e1c9535e": "client",  # Client name
    "554e54d9-4cdf-41ce-935c-b2d8c5136b56": "client_website_url",
    "717e4266-95c8-4687-bbed-d77a49f93e44": "main_question",
    "8ff80e5b-5bae-4107-a06f-81cd00f813ca": "number_sections",
    "4c3507a2-26a2-4c03-b46a-59ecfa74cfa1": "number_sub_sections",
    "4f5dd7ef-3ec0-4bf8-9f3b-4183dda1546e": "target_variable",
    "af7ff0b3-2b30-454b-bafa-7a853f681a4c": "commodity",
    "cb419693-49c7-4e6e-8a5e-0433227db306": "region",
    "73359da3-ed78-4e20-9080-25895f70b299": "time_range",
    "aebcaeaf-2b0c-406d-9ef3-2dcfc465e084": "reference_age_range",
    "df96b970-1262-4202-9b7d-96cf6b7b4e76": "question_context_file"
}

def process_typeform_submission(data):
    form_fields = {}

    for answer in data['form_response']['answers']:
        ref = answer['field']['ref']
        if ref in FIELD_MAP:
            key = FIELD_MAP[ref]
            if answer['type'] == "choice":
                form_fields[key] = answer['choice']['label']
            elif answer['type'] == "file_url":
                form_fields[key] = answer['file_url']
            elif answer['type'] in ["text", "email", "url"]:
                form_fields[key] = answer.get('text') or answer.get('email') or answer.get('url')

    if "question_context_file" not in form_fields:
        raise Exception("Missing question context file.")

    # Download file and write to Supabase
    file_url = form_fields["question_context_file"]
    file_response = requests.get(file_url)
    file_content = file_response.text

    client_name_safe = form_fields.get("client", "unknown").replace(" ", "_")
    supabase_path = f"panelitix/The Big Question/Client Contexts/{client_name_safe}_context.txt"
    write_supabase_file(supabase_path, file_content)

    # Return full payload including all mapped vars
    return {
        "prompt": "client_context",
        "client": form_fields.get("client", ""),
        "client_website_url": form_fields.get("client_website_url", ""),
        "main_question": form_fields.get("main_question", ""),
        "number_sections": form_fields.get("number_sections", ""),
        "number_sub_sections": form_fields.get("number_sub_sections", ""),
        "target_variable": form_fields.get("target_variable", ""),
        "commodity": form_fields.get("commodity", ""),
        "region": form_fields.get("region", ""),
        "time_range": form_fields.get("time_range", ""),
        "reference_age_range": form_fields.get("reference_age_range", ""),
        "client_context_url": f"https://ribebcjrzcinomtocqdo.supabase.co/storage/v1/object/public/{supabase_path}"
    }
