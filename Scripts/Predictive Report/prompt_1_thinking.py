import openai
import os
import time
import json
from logger import logger

def safe_escape(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value).replace("{", "{{").replace("}", "}}")

def run_prompt(data):
    logger.info("🚀 Incoming Webhook Payload")
    logger.debug(json.dumps(data, indent=2))

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

    logger.info("🧪 Sanitized Variables")
    logger.info(f"client: {client}")
    logger.info(f"client_context: {client_context}")
    logger.info(f"main_question: {main_question}")
    logger.info(f"question_context: {question_context}")
    logger.info(f"number_sections: {number_sections}")
    logger.info(f"number_sub_sections: {number_sub_sections}")
    logger.info(f"target_variable: {target_variable}")
    logger.info(f"commodity: {commodity}")
    logger.info(f"region: {region}")
    logger.info(f"time_range: {time_range}")

    # Load the prompt template
    prompt_path = 'Prompts/Predictive Report/prompt_1_thinking.txt'
    try:
        with open(prompt_path, 'r') as f:
            prompt_template = f.read()
        logger.debug("📄 RAW PROMPT TEMPLATE CONTENT\n%s", prompt_template)
    except Exception as e:
        logger.exception("❌ Failed to load prompt template")
        return {"error": f"Failed to load prompt template: {str(e)}"}

    if prompt_template.strip().lower() == "thinking":
        logger.warning("⚠️ Prompt template contains only 'Thinking' — likely file sync or path issue.")
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
        logger.debug("🧾 FINAL PROMPT (POST-FILL)\n%s", prompt)
    except Exception as e:
        logger.exception("❌ Prompt formatting failed")
        return {"error": f"Prompt formatting failed: {str(e)}"}

    if not prompt.strip():
        logger.error("❌ Final prompt is empty after population.")
        return {"error": "Final prompt is empty after population."}

    # Step 1: Create a new thread
    try:
        thread = openai.beta.threads.create()
        thread_id = thread.id
        logger.info("✅ New thread created: %s", thread_id)
    except Exception as e:
        logger.exception("❌ Thread creation failed")
        return {"error": f"Thread creation failed: {str(e)}"}

    # Step 2: Add message to thread
    try:
        openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=prompt
        )
        logger.info("✅ Message added to thread %s", thread_id)
    except Exception as e:
        logger.exception("❌ Message creation failed")
        return {"error": f"Message creation failed: {str(e)}", "thread_id": thread_id}

    time.sleep(1)

    # Step 3: Run the assistant
    try:
        run = openai.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
            temperature=0.2,
            response_format="auto",
        )
        logger.info("🚀 Assistant run started: %s", run.id)
    except Exception as e:
        logger.exception("❌ Run creation failed")
        return {"error": f"Run creation failed: {str(e)}", "thread_id": thread_id}

    # Step 4: Poll for completion
    while True:
        run_status = openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if run_status.status == "completed":
            logger.info("✅ Assistant run completed")
            break
        elif run_status.status in ["cancelled", "failed", "expired"]:
            logger.error("❌ Run failed with status: %s", run_status.status)
            return {"error": f"Run failed with status: {run_status.status}", "thread_id": thread_id}
        time.sleep(1)

    # Step 5: Retrieve response
    try:
        messages = openai.beta.threads.messages.list(thread_id=thread_id)
        for msg in messages.data:
            if msg.role == "assistant":
                for content in msg.content:
                    if content.type == "json_object":
                        logger.info("✅ Assistant returned structured JSON")
                        return {"output": content.json, "thread_id": thread_id}
                    elif content.type == "text":
                        try:
                            parsed_json = json.loads(content.text.value)
                            logger.info("✅ Assistant returned parsable text")
                            return {"output": parsed_json, "thread_id": thread_id}
                        except json.JSONDecodeError:
                            logger.warning("⚠️ Assistant returned unstructured text")
                            return {
                                "error": "Assistant returned text but it was not valid JSON.",
                                "raw_response": content.text.value,
                                "thread_id": thread_id
                            }
    except Exception as e:
        logger.exception("❌ Message retrieval failed")
        return {"error": f"Message retrieval failed: {str(e)}", "thread_id": thread_id}

    logger.warning("⚠️ No valid assistant response found.")
    return {"error": "No valid assistant response found.", "thread_id": thread_id}
