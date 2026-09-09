import os

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_KEY"],
)


def insert_meal_log(user_id: str, dish_name: str, calorie_diff: int) -> None:
    supabase.table("meal_logs").insert({
        "user_id": user_id,
        "dish_name": dish_name,
        "calorie_diff": calorie_diff,
    }).execute()


def get_meal_logs(user_id: str) -> list[dict]:
    response = supabase.table("meal_logs").select("*").eq("user_id", user_id).execute()
    return response.data


def upsert_goal(user_id: str, current_weight_kg: float, target_weight_kg: float, target_date: str) -> None:
    supabase.table("goals").upsert({
        "user_id": user_id,
        "current_weight_kg": current_weight_kg,
        "target_weight_kg": target_weight_kg,
        "target_date": target_date,
    }).execute()


def get_goal(user_id: str) -> dict | None:
    response = supabase.table("goals").select("*").eq("user_id", user_id).execute()
    return response.data[0] if response.data else None


if __name__ == "__main__":
    test_user_id = "00000000-0000-0000-0000-000000000001"

    insert_meal_log(test_user_id, "ラーメン", 480)
    print("meal_logs:", get_meal_logs(test_user_id))

    upsert_goal(test_user_id, current_weight_kg=65.0, target_weight_kg=60.0, target_date="2026-10-01")
    print("goal:", get_goal(test_user_id))
