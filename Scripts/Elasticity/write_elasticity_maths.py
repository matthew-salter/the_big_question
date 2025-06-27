import uuid
from decimal import Decimal, ROUND_HALF_UP
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

# --- Format decimal as percent string ---
def format_decimal(value: Decimal, dp: int = 1) -> str:
    precision = '1.' + ('0' * dp)
    return f"{value.quantize(Decimal(precision), rounding=ROUND_HALF_UP)}%"

# --- Main function ---
def run_prompt(data):
    try:
        run_id = data.get("run_id") or str(uuid.uuid4())

        # Full payload log
        logger.info(f"📦 Full incoming data: {data}")

        # If payload is nested under "data", extract it
        payload = data.get("data", data)

        # Raw values (strings or numbers from Zapier)
        supply_change_raw = payload.get("supply_change") or "0"
        demand_change_raw = payload.get("demand_change") or "0"
        supply_elasticity_raw = payload.get("supply_elasticity") or "0"
        demand_elasticity_raw = payload.get("demand_elasticity") or "0"

        # Parse using safe string conversion
        supply_change = Decimal(str(supply_change_raw).replace('%', '').strip())
        demand_change = Decimal(str(demand_change_raw).replace('%', '').strip())
        supply_elasticity = Decimal(str(supply_elasticity_raw))
        demand_elasticity = Decimal(str(demand_elasticity_raw))

        # Debug log
        logger.info("📥 Raw inputs:")
        logger.info(f"  supply_change = {supply_change_raw}")
        logger.info(f"  demand_change = {demand_change_raw}")
        logger.info(f"  supply_elasticity = {supply_elasticity_raw}")
        logger.info(f"  demand_elasticity = {demand_elasticity_raw}")

        logger.info("📊 Parsed values:")
        logger.info(f"  supply_change = {supply_change}")
        logger.info(f"  demand_change = {demand_change}")
        logger.info(f"  supply_elasticity = {supply_elasticity}")
        logger.info(f"  demand_elasticity = {demand_elasticity}")

        # Elasticity maths
        numerator = demand_change - supply_change
        denominator = supply_elasticity + abs(demand_elasticity)

        if denominator == 0:
            raw_change = Decimal("0.0")
        else:
            raw_change = numerator / denominator

        rounded_change = raw_change.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

        # Calculation explanation string
        calc_string = (
            f"Expected Price Change = ({demand_change:+.1f}% - ({supply_change:+.1f}%)) / "
            f"({supply_elasticity} + |{demand_elasticity}|) = "
            f"[{numerator:+.1f}% / {denominator}] = {raw_change:.2f}%, rounded to {rounded_change:.1f}%."
        )

        # Save output to Supabase
        filename = f"{run_id}.txt"
        supabase_path = f"Elasticity/Ai_Responses/Elasticity_Maths/{filename}"
        write_supabase_file(supabase_path, calc_string)
        logger.info(f"✅ Elasticity calculation written to Supabase: {supabase_path}")

        return {
            "status": "success",
            "run_id": run_id,
            "Elasticity Change:": f"{rounded_change:.1f}%",
            "Elasticity Calculation:": calc_string
        }

    except Exception as e:
        logger.exception("❌ Failed to calculate elasticity maths")
        return {
            "status": "error",
            "message": f"Elasticity calculation failed: {str(e)}"
        }
