from supabase_sample import insert_meal_log, get_meal_logs


def suggest_replacement(dish_name: str) -> dict:
    # ダミー(本物のOpenAI APIは呼ばない)
    return {
        "original_dish": dish_name,
        "original_calories": 600,
        "replacement_name": "ダミーの置き換えレシピ",
        "replacement_calories": 350,
        "calorie_diff": 250,
        "estimated_cost_yen": 300,
    }


test_user_id = "00000000-0000-0000-0000-000000000002"

result = suggest_replacement("チャーハン")
print("ダミーの結果:", result)

insert_meal_log(test_user_id, result["original_dish"], result["calorie_diff"])
print("Supabaseに保存しました")

print("保存されたログ一覧:", get_meal_logs(test_user_id))
