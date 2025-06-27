import uuid
from decimal import Decimal, ROUND_HALF_UP
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

# --- Helpers ---
def parse_percent(value: str) -> Decimal:
    try:
        return Decimal(str(value).replace('%', '').strip())
    except:
        return Decimal("0.0")

def parse_number(value: str) -> Decimal:
    try:
        return Decimal(str(value).strip())
    except:
        return Decimal("0.0")

def format_decimal(value: Decimal, dp: int = 1) -> str:
    precision = '1.' + ('0' * dp)
    return f"{value.quantize(Decimal(precision), rounding=ROUND_HALF_UP)}%"

# --- Main function ---
def run_prompt(data):
    try:
        run_id = data.get("run_id") or str(uuid.uuid4())

        # Step 1: Safely extract and parse all inputs
        supply_change_raw = data.get("supply_change") or "0"
        demand_change_raw = data.get("demand_change") or "0"
        supply_elasticity_raw = data.get("supply_elasticity") or "0"
        demand_elasticity_raw = data.get("demand_elasticity") or "0"

        supply_change = parse_percent(supply_change_raw)
        demand_change = parse_percent(demand_change_raw)
        supply_elasticity = parse_number(supply_elasticity_raw)
        demand_elasticity = parse_number(demand_elasticity_raw)

        # Step 2: Log values for debugging
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

        # Step 3: Perform the calculation
        numerator = demand_change - supply_change
        denominator = supply_elasticity + abs(demand_elasticity)

        if denominator == 0:
            raw_change = Decimal("0.0")
        else:
            raw_change = numerator / denominator

        rounded_change = raw_change.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

        # Step 4: Format output string
        calc_string = (
            f"Expected Price Change = ({demand_change:+.1f}% - ({supply_change:+.1f}%)) / "
            f"({supply_elasticity} + |{demand_elasticity}|) = "
            f"[{numerator:+.1f}% / {denominator}] = {raw_change:.2f}%, rounded to {rounded_change:.1f}%."
        )

        # Step 5: Write to Supabase
        filename = f"{run_id}.txt"
        supabase_path = f"Elasticity/Ai_Responses/Elasticity_Maths/{filename}"
        write_supabase_file(supabase_path, calc_string)
        logger.info(f"✅ Elasticity calculation written to Supabase: {supabase_path}")

        # Step 6: Return meta data blocks
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
