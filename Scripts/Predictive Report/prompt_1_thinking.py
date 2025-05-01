import openai
import os
import time
import json

def safe_escape(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value).replace("{", "{{").replace("}", "}}")

def run_prompt(data):
    print("=== Incoming Webhook Payload ===")
    print(json.dumps(data, indent=2))

    # Extract and sanitize incoming variables
    assistant_id = safe_escape(data.get('assistant_id'))

    client = safe_escape(data.get('client'))
    client_context = safe_escape(data.get('client_context'))
    main_question = safe_escape(data.get('main_question'))
    question_context = safe_escape(data.get('question_context'))
    number_sections = safe_escape(data.get('number_sections'))
    number_sub_sections = safe_escape(data.get('number_sub_sections'))
    target_variable = safe_escape(data.get('target_variable'))
    commodity = safe_escape(data.get('commodity'))
    region = safe_escape(data.get('region'))
    time_range = safe_escape(data.get('time_range'))

    print("=== Sanitized Variables ===")
    print(f"client: {client}")
    print(f"client_context: {client_context}")
    print(f"main_question: {main_question}")
    print(f"question_context: {question_context}")
    print(f"number_sections: {number_sections}")
    print(f"number_sub_sections: {number_sub_sections}")
    print(f"target_variable: {target_variable}")
    print(f"commodity: {commodity}")
    print(f"region: {region}")
    print(f"time_range: {time_range}")

    # Load the prompt template
    prompt_path = 'Prompts/Commodity Report/prompt_1_thinking.txt'
    try:
        with open(prompt_path, 'r') as f:
            prompt_template = f.read()
        print("=== RAW PROMPT TEMPLATE CONTENT ===")
        print(prompt_template)
    except Exception as e:
        print(f"ERROR: Failed to load prompt template: {str(e)}")
        return {"error": f"Failed to load prompt template: {str(e)}"}

    if prompt_template.strip().lower() == "thinking":
        print("❗ WARNING: Prompt template contains only 'Thinking' — likely file sync or path issue.")
        return {"error": "Prompt template contains only 'Thinking'"}

    # Fill the prompt
    try:
        prompt = prompt_template.format(
            client=client,
            client_context=client_context,
            main_question=main_question,
            question_context=question_context,
            number_sections=number_sections,
            number_sub_sections=number_sub_sections,
            target_variable=target_variable,
            commodity=commodity,
            region=region,
            time_range=time_range
        )
    except Exception as e:
        print(f"ERROR: Prompt formatting failed: {str(e)}")
        return {"error": f"Prompt formatting failed: {str(e)}"}

    if not prompt.strip():
        print("ERROR: Final prompt is empty after population.")
        return {"error": "Final prompt is empty after population."}

    print("=== FINAL PROMPT (POST-FILL) ===")
    print(prompt)

    # Step 1: Always create a new Thread
    try:
        thread = openai.beta.threads.create()
        thread_id = thread.id
        print(f"✅ New thread created: {thread_id}")
    except Exception as e:
        print(f"ERROR: Thread creation failed: {str(e)}")
        return {"error": f"Thread creation failed: {str(e)}"}

    # Step 2: Add message to Thread
    try:
        openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=prompt
        )
    except Exception as e:
        print(f"ERROR: Message creation failed: {str(e)}")
        return {"error": f"Message creation failed: {str(e)}", "thread_id": thread_id}

    time.sleep(1)

    # Step 3: Run the Assistant
    try:
        run = openai.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
            temperature=0.2,
            response_format="auto",
        )
    except Exception as e:
        print(f"ERROR: Run creation failed: {str(e)}")
        return {"error": f"Run creation failed: {str(e)}", "thread_id": thread_id}

    # Step 4: Poll until Run is complete
    while True:
        run_status = openai.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
        if run_status.status == "completed":
            break
        elif run_status.status in ["cancelled", "failed", "expired"]:
            print(f"ERROR: Run failed with status: {run_status.status}")
            return {"error": f"Run failed with status: {run_status.status}", "thread_id": thread_id}
        time.sleep(1)

    # Step 5: Retrieve the final message
    try:
        messages = openai.beta.threads.messages.list(thread_id=thread_id)
        for msg in messages.data:
            if msg.role == "assistant":
                for content in msg.content:
                    if content.type == "json_object":
                        return {
                            "output": content.json,
                            "thread_id": thread_id
                        }
                    elif content.type == "text":
                        try:
                            parsed_json = json.loads(content.text.value)
                            return {
                                "output": parsed_json,
                                "thread_id": thread_id
                            }
                        except json.JSONDecodeError:
                            return {
                                "error": "Assistant returned text but it was not valid JSON.",
                                "raw_response": content.text.value,
                                "thread_id": thread_id
                            }
    except Exception as e:
        print(f"ERROR: Message retrieval failed: {str(e)}")
        return {"error": f"Message retrieval failed: {str(e)}", "thread_id": thread_id}

    return {"error": "No valid assistant response found.", "thread_id": thread_id}
