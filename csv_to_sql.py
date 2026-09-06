import csv
import sqlite3

CSV_PATH = "/home/mamoruisa/path/to/your/folder/progate-hackathon-2026/Food_kcal.csv"
DB_PATH = "food_kcal.db"
SQL_PATH = "food_kcal.sql"

rows = []
with open(CSV_PATH, encoding="utf-8-sig") as f:
    reader = csv.reader(f)
    header = next(reader)
    for line in reader:
        if not line:
            continue
        no = int(line[0].strip())
        name = line[1].strip()
        kcal = int(line[2].strip())
        rows.append((no, name, kcal))

conn = sqlite3.connect(DB_PATH)
conn.execute(
    "CREATE TABLE IF NOT EXISTS food_kcal (no INTEGER PRIMARY KEY, food_name TEXT NOT NULL, kcal INTEGER NOT NULL)"
)
conn.executemany(
    "INSERT OR REPLACE INTO food_kcal (no, food_name, kcal) VALUES (?, ?, ?)", rows
)
conn.commit()
conn.close()

with open(SQL_PATH, "w", encoding="utf-8") as f:
    f.write("DROP TABLE IF EXISTS food_kcal;\n")
    f.write("CREATE TABLE food_kcal (\n")
    f.write("    no INTEGER PRIMARY KEY,\n")
    f.write("    food_name TEXT NOT NULL,\n")
    f.write("    kcal INTEGER NOT NULL\n")
    f.write(");\n\n")
    for no, name, kcal in rows:
        escaped = name.replace("'", "''")
        f.write(f"INSERT INTO food_kcal (no, food_name, kcal) VALUES ({no}, '{escaped}', {kcal});\n")

print(f"{len(rows)} rows written to {DB_PATH} and {SQL_PATH}")