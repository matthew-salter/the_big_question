import openai
import os
import time
import json
from datetime import datetime
from logger import logger
from Runtime.run_assistant import run_assistant
from Engine.Files.write_supabase_file import write_supabase_file

def safe_escape(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    return str(value).replace("{", "{{").replace("}", "}}")

def run_prompt(data):
    logger.info("🧠 Running prompt_1_thinking")
    logger.debug("Input variables:\n%s", json.dumps(data, indent=2))

    with open("Prompts/Predictive Report/prompt_1_thinking.txt", "r") as f:
        template = f.read()

    try:
        filled_prompt = template.format(**data)
    except KeyError as e:
        logger.error("❌ Missing variable in prompt template: %s", e)
        raise

    logger.debug("📝 Final prompt sent to assistant:\n%s", filled_prompt)

    response = run_assistant(filled_prompt)
    return {"response": response}

    # === Load environment variables ===
    assistant_id = os.getenv("ASSISTANT_ID")
    if not assistant_id:
        logger.error("❌ Missing ASSISTANT_ID environment variable.")
        return {"error": "Missing ASSISTANT_ID environment variable"}

    # === Extract & sanitize input ===
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

    logger.info("🧪 Sanitized Variables:")
    logger.info(f"Client: {client} | Main Question: {main_question} | Sections: {number_sections} | Sub-sections: {number_sub_sections}")

    # === Load prompt template ===
    prompt_path = 'Prompts/Predictive Report/prompt_1_thinking.txt'
    try:
        with open(prompt_path, 'r') as f:
            prompt_template = f.read()
        logger.debug("📄 Prompt template loaded.")
    except Exception as e:
        logger.exception("❌ Failed to load prompt template")
        return {"error": f"Failed to load prompt template: {str(e)}"}

    if prompt_template.strip().lower() == "thinking":
        logger.warning("⚠️ Prompt template contains only 'Thinking'")
        return {"error": "Prompt template contains only 'Thinking'"}

    # === Populate template ===
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
        logger.debug("🧾 Final prompt:\n%s", prompt)
    except Exception as e:
        logger.exception("❌ Prompt formatting failed")
        return {"error": f"Prompt formatting failed: {str(e)}"}

    if not prompt.strip():
        return {"error": "Final prompt is empty after population."}

    # === Step 1: Create thread ===
    try:
        thread = openai.beta.threads.create()
        thread_id = thread.id
        logger.info(f"✅ New thread created: {thread_id}")
    except Exception as e:
        logger.exception("❌ Thread creation failed")
        return {"error": f"Thread creation failed: {str(e)}"}

    # === Step 2: Add message ===
    try:
        openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=prompt
        )
        logger.info(f"✅ Prompt added to thread {thread_id}")
    except Exception as e:
        logger.exception("❌ Message creation failed")
        return {"error": f"Message creation failed: {str(e)}", "thread_id": thread_id}

    time.sleep(1)

    # === Step 3: Run the assistant ===
    try:
        run = openai.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id,
            temperature=0.2,
            response_format="auto"
        )
        logger.info(f"🚀 Assistant run started: {run.id}")
    except Exception as e:
        logger.exception("❌ Run creation failed")
        return {"error": f"Run creation failed: {str(e)}", "thread_id": thread_id}

    # === Step 4: Poll for completion ===
    while True:
        run_status = openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        if run_status.status == "completed":
            logger.info("✅ Assistant run completed")
            break
        elif run_status.status in ["cancelled", "failed", "expired"]:
            logger.error(f"❌ Run failed with status: {run_status.status}")
            return {"error": f"Run failed: {run_status.status}", "thread_id": thread_id}
        time.sleep(1)

    # === Step 5: Retrieve and parse response ===
    try:
        messages = openai.beta.threads.messages.list(thread_id=thread_id)
        for msg in messages.data:
            if msg.role == "assistant":
                for content in msg.content:
                    if content.type == "json_object":
                        parsed = content.json
                        logger.info("✅ Assistant returned structured JSON")
                    elif content.type == "text":
                        try:
                            parsed = json.loads(content.text.value)
                            logger.info("✅ Assistant returned parsable text")
                        except json.JSONDecodeError:
                            logger.warning("⚠️ Assistant returned unstructured text")
                            return {
                                "error": "Returned text was not valid JSON.",
                                "raw_response": content.text.value,
                                "thread_id": thread_id
                            }

                    # === Step 6: Write to Supabase ===
                    filename = f"{client}_Prompt_1_thinking_{datetime.utcnow().strftime('%d%m%Y_%H%M')}.txt"
                    supabase_path = f"The Big Question/Predictive Report/Ai Responses/{filename}"
                    write_supabase_file(supabase_path, json.dumps(parsed, indent=2))
                    logger.info(f"✅ Prompt 1 Thinking saved to Supabase: {supabase_path}")

                    return {
                        "output": parsed,
                        "thread_id": thread_id,
                        "supabase_path": supabase_path
                    }

    except Exception as e:
        logger.exception("❌ Message retrieval failed")
        return {"error": f"Message retrieval failed: {str(e)}", "thread_id": thread_id}

    logger.warning("⚠️ No valid assistant response found.")
    return {"error": "No valid assistant response found.", "thread_id": thread_id}
