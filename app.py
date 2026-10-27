import os
import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List
import uvicorn

app = FastAPI()

# === НАСТРОЙКИ АВТОРИЗАЦИИ ===
# ВАЖНО: Замените 123456789 на ваш реальный ID из бота @userinfobot
ALLOWED_TELEGRAM_IDS = [8902982456] 

# Ссылка на базу данных (Render подставит её автоматически из настроек)
DATABASE_URL = os.environ.get("DATABASE_URL")

# --- МОДЕЛИ ДАННЫХ ---
class MarkRequest(BaseModel):
    student_id: int
    status: str
    date: str

class NewStudent(BaseModel):
    name: str

class GroupName(BaseModel):
    name: str

class DeleteStudent(BaseModel):
    student_id: int

class ReorderRequest(BaseModel):
    student_ids: List[int]

# --- ПОДКЛЮЧЕНИЕ К БАЗЕ ---
async def get_db():
    if DATABASE_URL:
        conn = await asyncpg.connect(DATABASE_URL.replace("postgres://", "postgresql://"))
        return conn
    else:
        raise Exception("DATABASE_URL не задан в переменных окружения!")

async def init_db():
    conn = await get_db()
    # Создаем таблицы
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id SERIAL PRIMARY KEY,
            name TEXT,
            order_index INTEGER
        );
    ''')
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id SERIAL PRIMARY KEY,
            student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
            status TEXT,
            date TEXT
        );
    ''')
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    ''')
    await conn.execute("INSERT INTO settings (key, value) VALUES ('group_name', 'Моя группа') ON CONFLICT (key) DO NOTHING")
    
    # Проверка на пустую базу и загрузка списка из журнала
    count = await conn.fetchval("SELECT COUNT(*) FROM students")
    if count == 0:
        students_list = [
            "Афанасьев Павел Павлович", "Бойцов Константин Дмитриевич", "Голубев Илья Александрович",
            "Гусев Максим Иванович", "Егоров Павел Сергеевич", "Еремеев Роман Александрович",
            "Изотов Глеб Константинович", "Зимин Игнатий Михайлович", "Кудрявый Сергей Павлович",
            "Кузнецов Егор Леонидович", "Кузнецов Максим Денисович", "Куренон Андрей Ильич",
            "Мартынов Дмитрий Александрович", "Москалев Матвей Дмитриевич", "Оско Сергей Игоревич",
            "Проворов Иван Евгеньевич", "Служителей Иван Антонович", "Соколов Артём Дмитриевич",
            "Соколов Виктор Александрович", "Соловьев Владислав Владимирович", "Удальцов Максим Николаевич",
            "Филин Илья Александрович", "Фомин Матвей Анатольевич", "Цикин Захар Сергеевич",
            "Ширяев Богдан Анатольевич", "Белков Матвей Константинович", "Вожаков Виталий Артемович",
            "Маямсин Дмитрий Даниилович", "Шумов Евгений Валерьевич", "Бердов Аркадий Романович"
        ]
        for idx, name in enumerate(students_list):
            await conn.execute("INSERT INTO students (name, order_index) VALUES ($1, $2)", name, idx)
    await conn.close()

@app.on_event("startup")
async def startup():
    await init_db()

# --- API ---

@app.get("/api/students")
async def get_students():
    conn = await get_db()
    rows = await conn.fetch("SELECT id, name FROM students ORDER BY order_index ASC")
    await conn.close()
    return [{"id": r['id'], "name": r['name']} for r in rows]

@app.get("/api/attendance/{date}")
async def get_attendance(date: str):
    conn = await get_db()
    rows = await conn.fetch("SELECT student_id, status FROM attendance WHERE date = $1", date)
    await conn.close()
    return {r['student_id']: r['status'] for r in rows}

@app.post("/api/mark")
async def mark_attendance(req: MarkRequest):
    conn = await get_db()
    await conn.execute("DELETE FROM attendance WHERE student_id = $1 AND date = $2", req.student_id, req.date)
    await conn.execute("INSERT INTO attendance (student_id, status, date) VALUES ($1, $2, $3)", 
                       req.student_id, req.status, req.date)
    await conn.close()
    return {"ok": True}

@app.post("/api/add_student")
async def add_student(req: NewStudent):
    conn = await get_db()
    max_order = await conn.fetchval("SELECT MAX(order_index) FROM students")
    max_order = max_order if max_order else 0
    await conn.execute("INSERT INTO students (name, order_index) VALUES ($1, $2)", req.name, max_order + 1)
    await conn.close()
    return {"ok": True}

@app.post("/api/delete_student")
async def delete_student(req: DeleteStudent):
    conn = await get_db()
    await conn.execute("DELETE FROM students WHERE id = $1", req.student_id)
    await conn.close()
    return {"ok": True}

@app.post("/api/reorder")
async def reorder_students(req: ReorderRequest):
    conn = await get_db()
    for index, student_id in enumerate(req.student_ids):
        await conn.execute("UPDATE students SET order_index = $1 WHERE id = $2", index, student_id)
    await conn.close()
    return {"ok": True}

@app.get("/api/group")
async def get_group():
    conn = await get_db()
    name = await conn.fetchval("SELECT value FROM settings WHERE key = 'group_name'")
    await conn.close()
    return {"name": name}

@app.post("/api/group")
async def set_group(req: GroupName):
    conn = await get_db()
    await conn.execute("UPDATE settings SET value = $1 WHERE key = 'group_name'", req.name)
    await conn.close()
    return {"ok": True}

@app.get("/api/stats")
async def get_stats():
    conn = await get_db()
    total_days = await conn.fetchval("SELECT COUNT(DISTINCT date) FROM attendance")
    
    students = await conn.fetch("SELECT id, name FROM students ORDER BY order_index ASC")
    stats = []
    for s in students:
        counts = await conn.fetch("SELECT status, COUNT(*) as cnt FROM attendance WHERE student_id = $1 GROUP BY status", s['id'])
        count_dict = {r['status']: r['cnt'] for r in counts}
        
        stats.append({
            "id": s['id'],
            "name": s['name'],
            "present": count_dict.get("present", 0),
            "absent": count_dict.get("absent", 0),
            "excused": count_dict.get("excused", 0),
            "late": count_dict.get("late", 0),
            "silent": count_dict.get("silent", 0),
            "total_days": total_days
        })
    await conn.close()
    return {"total_days": total_days, "stats": stats}

app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
