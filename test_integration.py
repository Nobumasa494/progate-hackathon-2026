from main import suggest_replacement
from supabase_sample import insert_meal_log, get_meal_logs

test_user_id = "00000000-0000-0000-0000-000000000001"

result = suggest_replacement("チャーハン")
print("AIの結果:", result)

insert_meal_log(test_user_id, result["original_dish"], result["calorie_diff"])
print("Supabaseに保存しました")

print("保存されたログ一覧:", get_meal_logs(test_user_id))
