import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from supabase import create_client

load_dotenv()

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_KEY"],
)


def insert_weight_log(user_id: str, weight_kg: float) -> None:
    supabase.table("weight_logs").insert({
        "user_id": user_id,
        "weight_kg": weight_kg,
    }).execute()


def get_weight_logs(user_id: str) -> list[dict]:
    response = (
        supabase.table("weight_logs")
        .select("*")
        .eq("user_id", user_id)
        .order("id")
        .execute()
    )
    return response.data


app = FastAPI()


@app.post("/weight")
def record_weight(user_id: str, weight_kg: float):
    insert_weight_log(user_id, weight_kg)
    return {"status": "ok"}


@app.get("/weight")
def list_weight(user_id: str):
    return get_weight_logs(user_id)


app.mount("/", StaticFiles(directory="static_weight", html=True), name="static")
