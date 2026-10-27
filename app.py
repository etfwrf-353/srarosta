import os
import sqlite3
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List

app = FastAPI()
DB_FILE = 'starosta_final.db'

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # Таблица студентов
    c.execute('''CREATE TABLE IF NOT EXISTS students (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    name TEXT, 
                    order_index INTEGER
                )''')
    # Таблица посещаемости
    c.execute('''CREATE TABLE IF NOT EXISTS attendance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    student_id INTEGER, 
                    status TEXT, 
                    date TEXT
                )''')
    # Таблица настроек
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('group_name', 'Моя группа')")
    
    # ПРОВЕРКА: Если база пустая, загружаем туда ваших студентов из журнала
    c.execute("SELECT COUNT(*) FROM students")
    if c.fetchone()[0] == 0:
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
            c.execute("INSERT INTO students (name, order_index) VALUES (?, ?)", (name, idx))

    conn.commit()
    conn.close()

init_db()

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

# --- API ---

@app.get("/api/students")
def get_students():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, name FROM students ORDER BY order_index ASC")
    result = [{"id": r[0], "name": r[1]} for r in c.fetchall()]
    conn.close()
    return result

@app.get("/api/attendance/{date}")
def get_attendance(date: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT student_id, status FROM attendance WHERE date = ?", (date,))
    result = {r[0]: r[1] for r in c.fetchall()}
    conn.close()
    return result

@app.post("/api/mark")
def mark_attendance(req: MarkRequest):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM attendance WHERE student_id = ? AND date = ?", (req.student_id, req.date))
    c.execute("INSERT INTO attendance (student_id, status, date) VALUES (?, ?, ?)", 
              (req.student_id, req.status, req.date))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.post("/api/add_student")
def add_student(req: NewStudent):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT MAX(order_index) FROM students")
    max_order = c.fetchone()[0] or 0
    c.execute("INSERT INTO students (name, order_index) VALUES (?, ?)", (req.name, max_order + 1))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.post("/api/delete_student")
def delete_student(req: DeleteStudent):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM attendance WHERE student_id = ?", (req.student_id,))
    c.execute("DELETE FROM students WHERE id = ?", (req.student_id,))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.post("/api/reorder")
def reorder_students(req: ReorderRequest):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    for index, student_id in enumerate(req.student_ids):
        c.execute("UPDATE students SET order_index = ? WHERE id = ?", (index, student_id))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/api/group")
def get_group():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = 'group_name'")
    name = c.fetchone()[0]
    conn.close()
    return {"name": name}

@app.post("/api/group")
def set_group(req: GroupName):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE settings SET value = ? WHERE key = 'group_name'", (req.name,))
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/api/stats")
def get_stats():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT date) FROM attendance")
    total_days = c.fetchone()[0]
    
    c.execute("SELECT id, name FROM students ORDER BY order_index ASC")
    students = c.fetchall()
    
    stats = []
    for s_id, name in students:
        c.execute("SELECT status, COUNT(*) FROM attendance WHERE student_id = ? GROUP BY status", (s_id,))
        counts = dict(c.fetchall())
        
        stats.append({
            "id": s_id,
            "name": name,
            "present": counts.get("present", 0),
            "absent": counts.get("absent", 0),
            "excused": counts.get("excused", 0),
            "late": counts.get("late", 0),
            "silent": counts.get("silent", 0),
            "total_days": total_days
        })
    conn.close()
    return {"total_days": total_days, "stats": stats}

# Раздача HTML файла
app.mount("/", StaticFiles(directory=".", html=True), name="static")

# Запуск сервера для Render
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)