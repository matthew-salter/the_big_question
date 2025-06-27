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
        commodity = safe_escape(data["commodity"])
        report_date = safe_escape(data["report_date"])
        time_range = safe_escape(data["time_range"])
        region = safe_escape(data["region"])
        supply_change = safe_escape(data["supply_change"])
        demand_change = safe_escape(data["demand_change"])
        supply_report = safe_escape(data["supply_report"])
        demand_report = safe_escape(data["demand_report"])

        # Load and populate prompt template
        with open("Prompts/Elasticity/prompt_1_elasticity.txt", "r", encoding="utf-8") as f:
            template = f.read()

        prompt = template.format(
            commodity=commodity,
            report_date=report_date,
            time_range=time_range,
            region=region,
            supply_change=supply_change,
            demand_change=demand_change,
            supply_report=supply_report,
            demand_report=demand_report
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
        supabase_path = f"Elasticity/Ai_Responses/Prompt_1_Elasticity/{run_id}.txt"
        write_supabase_file(supabase_path, formatted)
        logger.info(f"✅ AI response written to Supabase: {supabase_path}")

        return {"status": "processing", "run_id": run_id}

    except Exception:
        logger.exception("❌ Error in run_prompt")
        return {"status": "error", "message": "Failed to write Prompt 1 Elasticity"}
