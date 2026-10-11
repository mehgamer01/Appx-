import os
import json
import base64
import sqlite3
import hashlib
import hmac
import math

from datetime import datetime, timezone
from functools import wraps

from flask import Flask, request, jsonify, g

app = Flask(__name__)

# ==========================================
# CONFIGURATION
# ==========================================

ADMIN_KEY = os.environ.get("ADMIN_KEY", "")

DATABASE = os.environ.get(
    "DATABASE_PATH",
    os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "results.db"
    )
)

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "ALLOWED_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000"
    ).split(",")
    if origin.strip()
]

app.config["MAX_CONTENT_LENGTH"] = 65536


# ==========================================
# CORS
# ==========================================

@app.after_request
def add_cors_headers(response):

    origin = request.headers.get("Origin")

    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"

    response.headers["Access-Control-Allow-Headers"] = (
        "Content-Type, Authorization, X-Admin-Key"
    )

    response.headers["Access-Control-Allow-Methods"] = (
        "GET, POST, OPTIONS"
    )

    return response


@app.route(
    "/",
    defaults={"path": ""},
    methods=["OPTIONS"]
)
@app.route(
    "/<path:path>",
    methods=["OPTIONS"]
)
def handle_options(path):
    return "", 204


# ==========================================
# JWT PAYLOAD DECODER
# ==========================================

def decode_jwt_payload(token):

    try:
        parts = token.split(".")

        if len(parts) != 3:
            return {}

        payload = parts[1]

        if len(payload) > 16000:
            return {}

        payload += "=" * (-len(payload) % 4)

        decoded = base64.urlsafe_b64decode(
            payload.encode("ascii")
        )

        data = json.loads(
            decoded.decode("utf-8")
        )

        if not isinstance(data, dict):
            return {}

        return data

    except Exception:
        return {}


# ==========================================
# EXTRACT USERNAME FROM JWT
# ==========================================

def get_jwt_username(token):

    data = decode_jwt_payload(token)

    fields = [
        "username",
        "user_name",
        "name",
        "full_name",
        "first_name"
    ]

    for field in fields:

        value = data.get(field)

        if isinstance(value, str) and value.strip():
            return value.strip()[:120]

    return "Unknown User"


# ==========================================
# GET JWT FROM AUTHORIZATION HEADER
# ==========================================

def get_request_jwt():

    auth_header = request.headers.get(
        "Authorization", ""
    )

    parts = auth_header.split(None, 1)

    if (
        len(parts) == 2
        and parts[0].lower() == "bearer"
    ):
        return parts[1].strip()

    return ""


# ==========================================
# DATABASE
# ==========================================

def get_db():

    if "db" not in g:

        db = sqlite3.connect(DATABASE)

        db.row_factory = sqlite3.Row

        db.execute("""
            CREATE TABLE IF NOT EXISTS results (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                user_id TEXT NOT NULL,

                user_name TEXT DEFAULT '',

                jwt_username TEXT DEFAULT '',

                test_id TEXT NOT NULL,

                test_name TEXT DEFAULT '',

                score REAL DEFAULT 0,

                total_marks REAL DEFAULT 0,

                correct INTEGER DEFAULT 0,

                wrong INTEGER DEFAULT 0,

                unattempted INTEGER DEFAULT 0,

                token_fingerprint TEXT DEFAULT '',

                submitted_at TEXT NOT NULL

            )
        """)

        # Existing database migration
        columns = [
            row["name"]
            for row in db.execute(
                "PRAGMA table_info(results)"
            ).fetchall()
        ]

        if "jwt_username" not in columns:

            db.execute("""
                ALTER TABLE results
                ADD COLUMN jwt_username TEXT DEFAULT ''
            """)

        if "token_fingerprint" not in columns:

            db.execute("""
                ALTER TABLE results
                ADD COLUMN token_fingerprint TEXT DEFAULT ''
            """)

        db.commit()

        g.db = db

    return g.db


@app.teardown_appcontext
def close_db(error=None):

    db = g.pop("db", None)

    if db is not None:
        db.close()


# ==========================================
# ADMIN AUTHENTICATION
# ==========================================

def admin_required(function):

    @wraps(function)
    def wrapper(*args, **kwargs):

        if not ADMIN_KEY:

            return jsonify({
                "ok": False,
                "error": "ADMIN_KEY not configured"
            }), 503

        supplied_key = request.headers.get(
            "X-Admin-Key", ""
        )

        if not hmac.compare_digest(
            supplied_key,
            ADMIN_KEY
        ):

            return jsonify({
                "ok": False,
                "error": "Unauthorized"
            }), 401

        return function(*args, **kwargs)

    return wrapper


# ==========================================
# HOME
# ==========================================

@app.route("/", methods=["GET"])
def home():

    return jsonify({

        "ok": True,

        "message": "RWA Mock Test Backend Running",

        "features": [
            "Save Test Results",
            "Extract JWT Username",
            "Admin Results",
            "Admin Summary"
        ],

        "endpoints": {

            "health": "/api/health",

            "submit_result": "/api/results",

            "admin_results": "/api/admin/results",

            "admin_summary": "/api/admin/summary"

        }

    })


# ==========================================
# HEALTH CHECK
# ==========================================

@app.route("/api/health", methods=["GET"])
def health():

    return jsonify({

        "ok": True,

        "status": "running",

        "time": datetime.now(
            timezone.utc
        ).isoformat()

    })


# ==========================================
# SAVE TEST RESULT
# ==========================================

@app.route("/api/results", methods=["POST"])
def save_result():

    data = request.get_json(silent=True)

    if not isinstance(data, dict):

        return jsonify({
            "ok": False,
            "error": "Invalid JSON"
        }), 400

    # User details
    user_id = str(
        data.get("user_id", "")
    ).strip()

    test_id = str(
        data.get("test_id", "")
    ).strip()

    if not user_id or not test_id:

        return jsonify({
            "ok": False,
            "error": "user_id and test_id required"
        }), 400

    # Read JWT
    token = get_request_jwt()

    if not token:

        return jsonify({
            "ok": False,
            "error": "RWA JWT required"
        }), 401

    jwt_data = decode_jwt_payload(token)

    if not jwt_data:

        return jsonify({
            "ok": False,
            "error": "Invalid JWT format"
        }), 401

    # Username from JWT
    jwt_username = get_jwt_username(token)

    # Token fingerprint only
    token_fingerprint = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    # Marks
    try:

        score = float(
            data.get("score", 0)
        )

        total_marks = float(
            data.get("total_marks", 0)
        )

        correct = int(
            data.get("correct", 0)
        )

        wrong = int(
            data.get("wrong", 0)
        )

        unattempted = int(
            data.get("unattempted", 0)
        )

    except (TypeError, ValueError):

        return jsonify({
            "ok": False,
            "error": "Invalid marks"
        }), 400

    if not (
        math.isfinite(score)
        and math.isfinite(total_marks)
    ):

        return jsonify({
            "ok": False,
            "error": "Invalid score"
        }), 400

    if (
        score < 0
        or total_marks < 0
        or score > total_marks
        or min(correct, wrong, unattempted) < 0
    ):

        return jsonify({
            "ok": False,
            "error": "Invalid result values"
        }), 400

    if correct + wrong + unattempted > 10000:

        return jsonify({
            "ok": False,
            "error": "Invalid question count"
        }), 400

    user_name = str(
        data.get("user_name", "")
    )[:120]

    test_name = str(
        data.get("test_name", "")
    )[:200]

    submitted_at = datetime.now(
        timezone.utc
    ).isoformat()

    # Save result
    db = get_db()

    cursor = db.execute("""

        INSERT INTO results (

            user_id,
            user_name,
            jwt_username,
            test_id,
            test_name,
            score,
            total_marks,
            correct,
            wrong,
            unattempted,
            token_fingerprint,
            submitted_at

        )

        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

    """, (

        user_id[:120],
        user_name,
        jwt_username,
        test_id[:120],
        test_name,
        score,
        total_marks,
        correct,
        wrong,
        unattempted,
        token_fingerprint,
        submitted_at

    ))

    db.commit()

    return jsonify({

        "ok": True,

        "message": "Result saved successfully",

        "result_id": cursor.lastrowid,

        "jwt_username": jwt_username,

        "identity_verified": False,

        "submitted_at": submitted_at

    }), 201


# ==========================================
# ADMIN RESULTS
# ==========================================

@app.route(
    "/api/admin/results",
    methods=["GET"]
)
@admin_required
def admin_results():

    db = get_db()

    rows = db.execute("""

        SELECT

            id,
            user_id,
            user_name,
            jwt_username,
            test_id,
            test_name,
            score,
            total_marks,
            correct,
            wrong,
            unattempted,
            token_fingerprint,
            submitted_at

        FROM results

        ORDER BY id DESC

        LIMIT 500

    """).fetchall()

    return jsonify({

        "ok": True,

        "count": len(rows),

        "results": [
            dict(row)
            for row in rows
        ]

    })


# ==========================================
# ADMIN SUMMARY
# ==========================================

@app.route(
    "/api/admin/summary",
    methods=["GET"]
)
@admin_required
def admin_summary():

    db = get_db()

    row = db.execute("""

        SELECT

            COUNT(*) AS total_submissions,

            COUNT(DISTINCT user_id) AS total_users,

            COALESCE(AVG(score), 0) AS average_score

        FROM results

    """).fetchone()

    return jsonify({

        "ok": True,

        "summary": dict(row)

    })


# ==========================================
# START SERVER
# ==========================================

if __name__ == "__main__":

    print("=" * 45)

    print("RWA MOCK TEST BACKEND")

    print("=" * 45)

    print("JWT Username Extraction Enabled")

    print("Server: http://127.0.0.1:8000")

    print("Health: http://127.0.0.1:8000/api/health")

    app.run(

        host="0.0.0.0",

        port=int(
            os.environ.get("PORT", "8000")
        ),

        debug=False

        )
