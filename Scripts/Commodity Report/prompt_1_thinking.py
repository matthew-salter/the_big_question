import openai
import os
import time
import json

def safe_escape(value):
    """Safely escape incoming Zapier field values."""
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value).replace("{", "{{").replace("}", "}}")

def run_prompt(data):
    # Extract and sanitize incoming variables
    assistant_id = safe_escape(data.get('assistant_id'))
    thread_id = safe_escape(data.get('thread_id'))

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

    # Load the prompt template
    prompt_path = 'Prompts/Commodity Report/prompt_1_thinking.txt'
    try:
        with open(prompt_path, 'r') as f:
            prompt_template = f.read()
    except Exception as e:
        return {"error": f"Failed to load prompt template: {str(e)}"}

    # Fill the prompt safely
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
        return {"error": f"Prompt formatting failed: {str(e)}"}

    if not prompt.strip():
        return {"error": "Formatted prompt is empty after population."}

    # (Optional) Print the final prompt to Render logs for debugging
    print("=== Final Populated Prompt ===")
    print(prompt)

    # Step 1: Add message to existing thread
    try:
        openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=prompt
        )
    except Exception as e:
        return {"error": f"Message creation failed: {str(e)}"}

    # Step 1.5: Give OpenAI time to register the message
    time.sleep(1)

    # Step 2: Run the Assistant on that Thread
    try:
        run = openai.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
            temperature=0.2,
            response_format="text"
        )
    except Exception as e:
        return {"error": f"Run creation failed: {str(e)}"}

    # Step 3: Poll until the run is complete
    while True:
        run_status = openai.beta.threads.runs.retrieve(
            thread_id=thread_id,
            run_id=run.id
        )
        if run_status.status == "completed":
            break
        elif run_status.status in ["cancelled", "failed", "expired"]:
            return {"error": f"Run failed with status: {run_status.status}"}
        time.sleep(1)

    # Step 4: Retrieve the final message from the Thread
    try:
        messages = openai.beta.threads.messages.list(thread_id=thread_id)
        for msg in messages.data:
            if msg.role == "assistant":
                for content in msg.content:
                    if content.type == "text":
                        try:
                            # Attempt to parse JSON output
                            parsed_json = json.loads(content.text.value)
                            return {"output": parsed_json}
                        except json.JSONDecodeError:
                            # Return raw text if not valid JSON
                            return {
                                "error": "Invalid JSON format returned by Assistant.",
                                "raw_response": content.text.value,
                                "thread_id": thread_id,
                                "prompt_used": prompt
                            }
    except Exception as e:
        return {"error": f"Message retrieval failed: {str(e)}"}

    # Final fallback
    return {"error": "No valid Assistant message found.", "thread_id": thread_id, "prompt_used": prompt}
