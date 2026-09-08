import os
import sqlite3
from functools import wraps
from pathlib import Path

from flask import Flask, jsonify, request

app = Flask(__name__)
ARCHIVE_API_KEY = os.environ.get("ARCHIVE_API_KEY", "")


def require_write_key(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        if not ARCHIVE_API_KEY:
            return jsonify({"error": "Write access is not configured"}), 503
        if request.headers.get("X-API-Key") != ARCHIVE_API_KEY:
            return jsonify({"error": "Invalid API key"}), 401
        return function(*args, **kwargs)

    return wrapped


def get_database_file():
    app_data = Path(os.environ.get("APPDATA", Path.home())) / "PersonLookup"
    app_data.mkdir(parents=True, exist_ok=True)
    return app_data / "people.db"


def connect_database():
    connection = sqlite3.connect(get_database_file())
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with connect_database() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS people (
                name TEXT PRIMARY KEY,
                age TEXT NOT NULL,
                school TEXT NOT NULL,
                field_of_study TEXT NOT NULL
            )
            """
        )


def person_from_row(row):
    return {
        "name": row["name"],
        "age": row["age"],
        "school": row["school"],
        "field of study": row["field_of_study"],
    }


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/people")
def list_people():
    search = request.args.get("search", "").strip()
    with connect_database() as connection:
        if search:
            rows = connection.execute(
                "SELECT * FROM people WHERE name LIKE ? COLLATE NOCASE ORDER BY name",
                (f"%{search}%",),
            ).fetchall()
        else:
            rows = connection.execute("SELECT * FROM people ORDER BY name").fetchall()
    return jsonify([person_from_row(row) for row in rows])


@app.get("/people/<path:name>")
def get_person(name):
    with connect_database() as connection:
        row = connection.execute("SELECT * FROM people WHERE name = ?", (name,)).fetchone()
    if row is None:
        return jsonify({"error": "Person not found"}), 404
    return jsonify(person_from_row(row))


@app.post("/people")
def add_person():
    person = request.get_json(silent=True) or {}
    name = str(person.get("name", "")).strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400

    values = (
        name,
        str(person.get("age", "unknown")).strip() or "unknown",
        str(person.get("school", "unknown")).strip() or "unknown",
        str(person.get("field of study", "unknown")).strip() or "unknown",
    )
    try:
        with connect_database() as connection:
            connection.execute(
                "INSERT INTO people (name, age, school, field_of_study) VALUES (?, ?, ?, ?)",
                values,
            )
    except sqlite3.IntegrityError:
        return jsonify({"error": "A person with that name already exists"}), 409
    return jsonify({"name": name}), 201


@app.put("/people/<path:old_name>")
@require_write_key
def edit_person(old_name):
    person = request.get_json(silent=True) or {}
    new_name = str(person.get("name", old_name)).strip() or old_name
    values = (
        new_name,
        str(person.get("age", "unknown")).strip() or "unknown",
        str(person.get("school", "unknown")).strip() or "unknown",
        str(person.get("field of study", "unknown")).strip() or "unknown",
        old_name,
    )
    with connect_database() as connection:
        existing = connection.execute("SELECT 1 FROM people WHERE name = ?", (old_name,)).fetchone()
        if existing is None:
            return jsonify({"error": "Person not found"}), 404
        try:
            connection.execute(
                """
                UPDATE people
                SET name = ?, age = ?, school = ?, field_of_study = ?
                WHERE name = ?
                """,
                values,
            )
        except sqlite3.IntegrityError:
            return jsonify({"error": "The new name already exists"}), 409
    return jsonify({"name": new_name})


@app.delete("/people/<path:name>")
@require_write_key
def delete_person(name):
    with connect_database() as connection:
        result = connection.execute("DELETE FROM people WHERE name = ?", (name,))
    if result.rowcount == 0:
        return jsonify({"error": "Person not found"}), 404
    return jsonify({"deleted": name})


initialize_database()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
