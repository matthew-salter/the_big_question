from flask import Flask, request, jsonify
import importlib
import threading
from logger import logger
from Scripts.Predictive_Report.ingest_typeform import process_typeform_submission

app = Flask(__name__)

# Prompts that should block until the result is returned
BLOCKING_PROMPTS = {
    "website",
    "year",
    "read_client_context",
    "read_question_context",
    "read_prompt_1_thinking",
    "read_prompt_2_section_assets",
    "read_prompt_3_report_assets",
    "read_prompt_4_tables",
    "combine",
    "format_combine",
    "read_section_image_prompts",
    "read_report_image_prompts",
    "format_image_prompts",
    "csv_content",
    "report_and_section_table_csv",
    "write_create_folders",
    "read_create_folders",
    "move_files_1",
    "move_files_2"
}

# Explicit static mapping of prompt names to module paths
PROMPT_MODULES = {
    "website": "Scripts.Website_Year.website",
    "year": "Scripts.Website_Year.year",
    "read_client_context": "Scripts.Client_Context.read_client_context",
    "write_client_context": "Scripts.Client_Context.write_client_context",
    "read_question_context": "Scripts.Predictive_Report.read_question_context",
    "write_prompt_1_thinking": "Scripts.Predictive_Report.write_prompt_1_thinking",
    "read_prompt_1_thinking": "Scripts.Predictive_Report.read_prompt_1_thinking",
    "write_prompt_2_section_assets": "Scripts.Predictive_Report.write_prompt_2_section_assets",
    "read_prompt_2_section_assets": "Scripts.Predictive_Report.read_prompt_2_section_assets",
    "write_prompt_3_report_assets": "Scripts.Predictive_Report.write_prompt_3_report_assets",
    "read_prompt_3_report_assets": "Scripts.Predictive_Report.read_prompt_3_report_assets",
    "write_prompt_4_tables": "Scripts.Predictive_Report.write_prompt_4_tables",
    "read_prompt_4_tables": "Scripts.Predictive_Report.read_prompt_4_tables",
    "combine": "Scripts.Predictive_Report.combine",
    "format_combine": "Scripts.Predictive_Report.format_combine",
    "write_section_image_prompts": "Scripts.Image_Prompts.write_section_image_prompts",
    "read_section_image_prompts": "Scripts.Image_Prompts.read_section_image_prompts",
    "write_report_image_prompts": "Scripts.Image_Prompts.write_report_image_prompts",
    "read_report_image_prompts": "Scripts.Image_Prompts.read_report_image_prompts",
    "format_image_prompts": "Scripts.Image_Prompts.format_image_prompts",
    "csv_content": "Scripts.Predictive_Report.csv_content",
    "report_and_section_table_csv": "Scripts.Predictive_Report.report_and_section_table_csv",
    "write_create_folders": "Scripts.Predictive_Report.write_create_folders",
    "read_create_folders": "Scripts.Predictive_Report.read_create_folders",
    "move_files_1": "Scripts.Predictive_Report.move_files_1",
    "move_files_2": "Scripts.Predictive_Report.move_files_2"
}

@app.route("/ingest-typeform", methods=["POST"])
def ingest_typeform():
    try:
        data = request.get_json(force=True)
        logger.info("📩 Typeform webhook received.")
        process_typeform_submission(data)
        return jsonify({"status": "success", "message": "Files processed and saved to Supabase."})
    except Exception as e:
        logger.exception("❌ Error handling Typeform submission")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/", methods=["POST"])
def dispatch_prompt():
    try:
        data = request.get_json(force=True)
        prompt_name = data.get("prompt")
        if not prompt_name:
            return jsonify({"error": "Missing 'prompt' key"}), 400

        module_path = PROMPT_MODULES.get(prompt_name)
        if not module_path:
            return jsonify({"error": f"Unknown prompt: {prompt_name}"}), 400

        module = importlib.import_module(module_path)
        logger.info(f"Dispatching prompt asynchronously: {prompt_name}")
        result_container = {}

        # Generate run_id upfront for non-blocking prompts
        import uuid
        if prompt_name not in BLOCKING_PROMPTS:
            run_id = data.get("run_id") or str(uuid.uuid4())
            data["run_id"] = run_id
            result_container["run_id"] = run_id

        def run_and_capture():
            try:
                result = module.run_prompt(data)
                result_container.update(result or {})
            except Exception:
                logger.exception("Background prompt execution failed.")

        thread = threading.Thread(target=run_and_capture)
        thread.start()

        if prompt_name in BLOCKING_PROMPTS:
            thread.join()
            return jsonify(result_container)

        return jsonify({
            "status": "processing",
            "message": "Script launched, run_id will be available via follow-up.",
            "run_id": result_container.get("run_id")
        })

    except Exception as e:
        logger.exception("Error in dispatch_prompt")
        return jsonify({"error": str(e)}), 500
