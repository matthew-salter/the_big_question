import uuid
from decimal import Decimal, ROUND_HALF_UP
from logger import logger
from Engine.Files.write_supabase_file import write_supabase_file

# --- Helper: Percent string to Decimal ---
def parse_percent(value: str) -> Decimal:
    try:
        return Decimal(str(value).replace('%', '').strip())
    except:
        return Decimal("0.0")

# --- Helper: Raw number string to Decimal ---
def parse_number(value: str) -> Decimal:
    try:
        return Decimal(str(value).strip())
    except:
        return Decimal("0.0")

# --- Helper: Format Decimal as percent string to 1 dp ---
def format_decimal(value: Decimal, dp: int = 1) -> str:
    precision = '1.' + ('0' * dp)
    return f"{value.quantize(Decimal(precision), rounding=ROUND_HALF_UP)}%"

# --- Main entry point ---
def run_prompt(data):
    try:
        run_id = data.get("run_id") or str(uuid.uuid4())

        # Parse inputs safely
        supply_change = parse_percent(data.get("supply_change", "0%"))
        supply_elasticity = parse_number(data.get("supply_elasticity", "0"))
        demand_change = parse_percent(data.get("demand_change", "0%"))
        demand_elasticity = parse_number(data.get("demand_elasticity", "0"))

        # Core calculation
        numerator = demand_change - supply_change
        denominator = supply_elasticity + abs(demand_elasticity)

        if denominator == 0:
            raw_change = Decimal("0.0")
        else:
            raw_change = numerator / denominator

        rounded_change = raw_change.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)

        # Format the full calculation string
        calc_string = (
            f"Expected Price Change = ({demand_change:+.1f}% - ({supply_change:+.1f}%)) / "
            f"({supply_elasticity} + |{demand_elasticity}|) = "
            f"[{numerator:+.1f}% / {denominator}] = {raw_change:.2f}%, rounded to {rounded_change:.1f}%."
        )

        # Save to file
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
