import uuid
import json
from openai import OpenAI
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

def safe_escape(value):
    return str(value).replace("{", "{{").replace("}", "}}")

def run_prompt(data):
    try:
        run_id = data.get("run_id") or str(uuid.uuid4())
        data["run_id"] = run_id  # ensure it's injected if missing

        # Extract and escape all inputs
        client = safe_escape(data["client"])
        client_context = safe_escape(data["client_context"])
        main_question = safe_escape(data["main_question"])
        question_context = safe_escape(data["question_context"])
        tone_of_voice = safe_escape(data["tone_of_voice"])
        special_instructions = safe_escape(data["special_instructions"])
        prompt_1_thinking = safe_escape(data["prompt_1_thinking"])
        prompt_2_section_assets = safe_escape(data["prompt_2_section_assets"])

        # Load and populate prompt template
        with open("Prompts/Predictive_Report/prompt_3_report_assets.txt", "r", encoding="utf-8") as f:
            template = f.read()

        prompt = template.format(
            client=client,
            client_context=client_context,
            main_question=main_question,
            question_context=question_context,
            tone_of_voice=tone_of_voice,
            special_instructions=special_instructions,
            prompt_1_thinking=prompt_1_thinking,
            prompt_2_section_assets=prompt_2_section_assets
        )

        # Send prompt to OpenAI
        client_openai = OpenAI()
        response = client_openai.chat.completions.create(
            model="gpt-4o",
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}]
        )

        raw_result = response.choices[0].message.content.strip()

        # Try parsing the response into JSON if possible
        try:
            parsed = json.loads(raw_result)
            formatted = json.dumps(parsed, indent=2)
        except json.JSONDecodeError:
            logger.warning("AI response is not valid JSON. Writing raw output.")
            formatted = raw_result

        # Write AI response to Supabase
        supabase_path = f"The_Big_Question/Predictive_Report/Ai_Responses/Prompt_3_Report_Assets/{run_id}.txt"
        write_supabase_file(supabase_path, formatted)
        logger.info(f"✅ AI response written to Supabase: {supabase_path}")

        return {"status": "processing", "run_id": run_id}

    except Exception:
        logger.exception("❌ Error in run_prompt")
        return {"status": "error", "message": "Failed to write Prompt 3 Report Assets"}
