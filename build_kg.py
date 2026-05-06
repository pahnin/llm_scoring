import sqlite3
import json
import os
import glob
import hashlib
import requests
import time
from datetime import datetime
import numpy as np
import importlib.resources
import re
# =========================
# CONFIG
# =========================
DB_NAME = "knowledge_graph.db"
RESULTS_DIR = "results/1777977547"
EMBEDDING_API_URL = "http://localhost:11434/api/embeddings"
EMBEDDING_MODEL = "nomic-embed-text:latest"


EXPECTED_PROBLEM_1 = [
    "conv is undefined in buildChatCommand",
    "conv not passed as parameter to buildChatCommand",
    "buildHistoryContext depends on conv but it is missing",
]

OPTIONAL_PROBLEM_1 = [
    "runtime reference error for conv",
    "history construction fails due to missing conv",
]


EXPECTED_PROBLEM_2 = [
    "loading set to false before async calls complete",
    "race condition between user and posts fetch",
    "no synchronization between parallel requests",
]

OPTIONAL_PROBLEM_2 = [
    "state updates happen independently causing mismatch",
    "ui shows inconsistent data due to async timing",
]

EXPECTED_PROBLEM_3 = [
    "is_active vs isActive mismatch",
    "name vs fullName mismatch",
]

OPTIONAL_PROBLEM_3 = [
    "frontend expects camelCase but backend returns snake_case",
    "undefined values cause ui rendering issues",
]

EXPECTED_PROBLEM_4 = [
    "computed value is not stored in cache",
]

OPTIONAL_PROBLEM_4 = [
    "cache miss always recomputes value",
    "cache behavior lost after refactor",
]

EXPECTED_PROBLEM_5 = [
    "input messages are mutated",
    "shared state causes side effects",
    "function modifies original array elements",
]

OPTIONAL_PROBLEM_5 = [
    "timestamp overwritten mutates original objects",
    "reusing array leads to inconsistent ordering",
]

EXPECTED_MAP = {
    1: EXPECTED_PROBLEM_1,
    2: EXPECTED_PROBLEM_2,
    3: EXPECTED_PROBLEM_3,
    4: EXPECTED_PROBLEM_4,
    5: EXPECTED_PROBLEM_5,
}

OPTIONAL_MAP = {
    1: OPTIONAL_PROBLEM_1,
    2: OPTIONAL_PROBLEM_2,
    3: OPTIONAL_PROBLEM_3,
    4: OPTIONAL_PROBLEM_4,
    5: OPTIONAL_PROBLEM_5,
}

# =========================
# DB INIT
# =========================
def init_db(conn):
    cursor = conn.cursor()
    ext_path = importlib.resources.files("sqlite_vector.binaries") / "vector"

    conn.enable_load_extension(True)
    conn.load_extension(str(ext_path))
    conn.enable_load_extension(False)

    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS problems (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        problem_name TEXT,
        problem_text TEXT,
        problem_id TEXT UNIQUE
    );

    CREATE TABLE IF NOT EXISTS models (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_name TEXT UNIQUE
    );

    CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_name TEXT,
        run_number INTEGER,
        start_time TEXT,
        UNIQUE(model_name, run_number)
    );

    CREATE TABLE IF NOT EXISTS facts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fact_text TEXT,
        embedding VECTOR(768),
        confidence REAL
    );

    CREATE TABLE IF NOT EXISTS relationships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fact_id INTEGER,
        problem_id INTEGER,
        model_name TEXT,
        run_number INTEGER,
        relationship_type TEXT DEFAULT 'supports'
    );

    CREATE TABLE IF NOT EXISTS run_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        model_name TEXT,
        problem_id INTEGER,
        run_number INTEGER,
        task_completion REAL,
        consistency_hint REAL DEFAULT 0
    );
    """)

    conn.commit()


# =========================
# HELPERS
# =========================
def cosine_sim(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def score_task_completion(problem_id, content):
    content = content.lower()

    expected = EXPECTED_MAP.get(problem_id, [])
    optional = OPTIONAL_MAP.get(problem_id, [])

    expected_score = fuzzy_match(content, expected)
    optional_score = fuzzy_match(content, optional)

    if len(expected) == 0:
        return 0

    # weight expected much higher
    return (
        0.8 * (expected_score / len(expected)) +
        0.2 * (optional_score / max(len(optional), 1))
    )

def extract_problem_and_run(filename):
    base = filename.replace(".json", "")
    parts = base.split("_")

    for i, part in enumerate(parts):
        if part.startswith("problem"):
            model = "_".join(parts[:i])
            problem = int(part.replace("problem", ""))
            run = int(parts[i + 1].replace("run", ""))
            return model, problem, run

    return base, 1, 1

def fuzzy_match(content, expected_items):
    content = content.lower()
    score = 0

    for item in expected_items:
        keywords = item.split()
        if all(word in content for word in keywords[:2]):  # loose match
            score += 1

    return score / len(expected_items)

def split_into_facts(content):
    # remove markdown noise
    content = re.sub(r'[`*#>-]', ' ', content)

    # split into sentences
    sentences = re.split(r'(?<=[.!?])\s+', content)

    facts = []
    buffer = ""

    for s in sentences:
        s = s.strip()

        if not s:
            continue

        # merge short fragments into buffer
        if len(s) < 40:
            buffer += " " + s
            continue

        # flush buffer if exists
        if buffer:
            s = buffer + " " + s
            buffer = ""

        # filter junk
        if any(x in s.lower() for x in ["```", "function(", "fetch(", "const ", "let "]):
            continue

        facts.append(s.strip())

    return facts

def normalize_fact(f):
    f = f.lower()

    # remove code + punctuation noise
    f = re.sub(r'[`*]', '', f)
    f = re.sub(r'\b\d+\.', '', f)  # remove numbering like "1."
    f = re.sub(r'\s+', ' ', f)

    # normalize common phrases (VERY high ROI)
    replacements = {
        "race conditions": "race condition",
        "asynchronous": "async",
        "promise.all": "promise all",
        "loading state": "loading",
    }

    for k, v in replacements.items():
        f = f.replace(k, v)

    return f.strip()

def is_good_fact(f):
    return (
        len(f) > 40 and
        not f.startswith(("function", "fetch(", "const ", "let ")) and
        "```" not in f
    )

def find_similar_fact(conn, embedding, threshold=0.75):
    cursor = conn.cursor()

    cursor.execute("SELECT id, embedding FROM facts LIMIT 5000")
    rows = cursor.fetchall()

    best_id = None
    best_sim = 0

    for fid, emb_blob in rows:
        existing = np.frombuffer(emb_blob, dtype=np.float32)

        sim = cosine_sim(existing, embedding)

        if sim > best_sim:
            best_sim = sim
            best_id = fid

    if best_sim > threshold:
        return best_id

    return None

# =========================
# DB UPSERT HELPERS
# =========================
def get_or_create_problem(conn, problem_text):
    cursor = conn.cursor()

    pid = hashlib.md5(problem_text.encode()).hexdigest()[:8]

    cursor.execute("SELECT id FROM problems WHERE problem_id = ?", (pid,))
    row = cursor.fetchone()

    if row:
        return row[0]

    cursor.execute(
        "INSERT INTO problems (problem_name, problem_text, problem_id) VALUES (?, ?, ?)",
        (problem_text, problem_text, pid),
    )
    conn.commit()
    return cursor.lastrowid


def get_or_create_model(conn, model_name):
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM models WHERE model_name = ?", (model_name,))
    row = cursor.fetchone()

    if row:
        return row[0]

    cursor.execute("INSERT INTO models (model_name) VALUES (?)", (model_name,))
    conn.commit()
    return cursor.lastrowid


def get_or_create_run(conn, model_name, run_number):
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id FROM runs WHERE model_name = ? AND run_number = ?",
        (model_name, run_number),
    )
    row = cursor.fetchone()

    if row:
        return row[0]

    cursor.execute(
        "INSERT INTO runs (model_name, run_number, start_time) VALUES (?, ?, ?)",
        (model_name, run_number, datetime.now().isoformat()),
    )
    conn.commit()
    return cursor.lastrowid


# =========================
# EMBEDDINGS
# =========================
def get_embedding(text, retries=3):
    payload = {"model": EMBEDDING_MODEL, "prompt": text}

    for i in range(retries):
        try:
            r = requests.post(EMBEDDING_API_URL, json=payload, timeout=30)

            if r.status_code == 200:
                data = r.json()
                ## print keys
                # print(data.keys())
                return data.get("embedding", [])

        except Exception:
            pass

        time.sleep(1)

    return []


# =========================
# FACT INSERT
# =========================
def insert_fact(conn, fact, problem_id, model, run):
    cursor = conn.cursor()

    # ✅ normalize
    fact = normalize_fact(fact)

    # ✅ filter bad facts
    if not is_good_fact(fact):
        return None

    embedding = get_embedding(fact)
    embedding_np = np.array(embedding, dtype=np.float32)

    fid = find_similar_fact(conn, embedding_np)

    if fid is None:
        embedding_bytes = embedding_np.tobytes()
        cursor.execute(
            "INSERT INTO facts (fact_text, embedding, confidence) VALUES (?, ?, ?)",
            (fact, embedding_bytes, 1.0),
        )
        fid = cursor.lastrowid

    # relationship always added
    cursor.execute(
        "INSERT INTO relationships (fact_id, problem_id, model_name, run_number) VALUES (?, ?, ?, ?)",
        (fid, problem_id, model, run),
    )

    conn.commit()
    return fid


# =========================
# MAIN PIPELINE
# =========================
def build_kg():
    print("\n🔍 Building Knowledge Graph...\n")

    conn = sqlite3.connect(DB_NAME)
    init_db(conn)

    files = glob.glob(os.path.join(RESULTS_DIR, "*.json"))
    print(f"📂 Found {len(files)} files\n")

    for path in files:
        try:
            data = json.load(open(path))
            filename = os.path.basename(path)

            model, problem, run = extract_problem_and_run(filename)

            problem_id = get_or_create_problem(conn, f"Problem {problem}")
            get_or_create_model(conn, model)
            get_or_create_run(conn, model, run)

            content = data.get("content", "")

            task_score = score_task_completion(problem, content)
            print(f"✅ Task score: {task_score:.2f} | Model: {model} | Problem: {problem}")

            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO run_scores (model_name, problem_id, run_number, task_completion)
                VALUES (?, ?, ?, ?)
            """, (model, problem_id, run, task_score))
            conn.commit()

            facts = split_into_facts(data.get("content", ""))

            print(f"📝 {filename} → {len(facts)} facts")
            # print("RAW CONTENT:", repr(content[:200]))
            # print("FACTS:", facts[:5])

            for f in facts:
                insert_fact(conn, f, problem_id, model, run)

        except Exception as e:
            print(f"⚠️ Error: {path} → {e}")

    conn.close()
    print("\n✅ Done\n")

    generate_rankings()


# =========================
# RANKING
# =========================
def generate_rankings(problem_id=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    print("\n📊 Quality-Aware Rankings:\n")

    # If problem_id not given → aggregate across all
    problem_filter = ""
    params = ()

    if problem_id is not None:
        problem_filter = "WHERE r.problem_id = ?"
        params = (problem_id,)

    query = f"""
    WITH fact_stats AS (
        SELECT 
            f.id,
            COUNT(DISTINCT r.model_name) AS model_support
        FROM facts f
        JOIN relationships r ON f.id = r.fact_id
        GROUP BY f.id
    ),

    model_fact_stats AS (
        SELECT
            r.model_name,
            COUNT(*) AS total_facts,
            COUNT(DISTINCT f.fact_text) AS unique_facts,
            SUM(CASE WHEN fs.model_support >= 2 THEN 1 ELSE 0 END) AS agreement_facts
        FROM facts f
        JOIN relationships r ON f.id = r.fact_id
        JOIN fact_stats fs ON fs.id = f.id
        GROUP BY r.model_name
    ),

    task_scores AS (
        SELECT
            model_name,
            AVG(task_completion) AS task_completion_score
        FROM run_scores
        GROUP BY model_name
    ),

    run_variance AS (
        SELECT
            model_name,
            problem_id,
            AVG(task_completion) AS avg_score,
            (MAX(task_completion) - MIN(task_completion)) AS variance
        FROM run_scores
        GROUP BY model_name, problem_id
    ),

    consistency AS (
        SELECT
            model_name,
            AVG(1.0 - variance) AS consistency_score
        FROM run_variance
        GROUP BY model_name
    )

    SELECT
        m.model_name,
        total_facts,
        unique_facts,
        ROUND(CAST(unique_facts AS FLOAT)/total_facts, 3) AS uniqueness_ratio,
        ROUND(ts.task_completion_score, 3) AS task_score,
        ROUND(c.consistency_score, 3) AS consistency_score,

        ROUND(
            (0.5 * ts.task_completion_score) +
            (0.3 * c.consistency_score) +
            (0.15 * (CAST(unique_facts AS FLOAT)/total_facts)) +
            (0.05 * (CAST(agreement_facts AS FLOAT)/total_facts)),
            3
        ) AS final_score

    FROM model_fact_stats m
    JOIN task_scores ts ON m.model_name = ts.model_name
    JOIN consistency c ON m.model_name = c.model_name

    ORDER BY final_score DESC;
    """

    cursor.execute(query, params * 2 if problem_id is not None else ())
    rows = cursor.fetchall()

    print(f"{'Model':30} | Tot | Uniq | U%   | Cons | C%   | Score")
    print("-" * 80)

    for row in rows:
        model, total, unique, u_ratio, cons, c_ratio, score = row
        print(f"{model:30} | {total:3} | {unique:4} | {u_ratio:.3f} | {cons:4} | {c_ratio:.3f} | {score:.3f}")

    conn.close()


# =========================
# ENTRY
# =========================
if __name__ == "__main__":
    build_kg()