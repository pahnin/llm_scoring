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
    """)

    conn.commit()


# =========================
# HELPERS
# =========================
def cosine_sim(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


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


def split_into_facts(content):
    # Split into sentences instead of arbitrary chunks
    sentences = re.split(r'(?<=[.!?])\s+', content)

    facts = []
    for s in sentences:
        s = s.strip()

        # keep only meaningful sentences
        if len(s) < 40:
            continue
        if "```" in s:
            continue
        if s.lower().startswith(("function", "fetch(", "const ", "let ")):
            continue

        facts.append(s)

    return facts

def normalize_fact(f):
    f = f.lower()
    f = re.sub(r'[`*]', '', f)  # remove markdown
    f = re.sub(r'\s+', ' ', f)
    return f.strip()

def is_good_fact(f):
    return (
        len(f) > 40 and
        not f.startswith(("function", "fetch(", "const ", "let ")) and
        "```" not in f
    )

def find_similar_fact(conn, embedding, threshold=0.9):
    cursor = conn.cursor()

    cursor.execute("SELECT id, embedding FROM facts")
    rows = cursor.fetchall()

    for fid, emb_blob in rows:
        existing = np.frombuffer(emb_blob, dtype=np.float32)
        if cosine_sim(existing, embedding) > threshold:
            return fid

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
            facts = split_into_facts(data.get("content", ""))

            print(f"📝 {filename} → {len(facts)} facts")
            print("RAW CONTENT:", repr(content[:200]))
            print("FACTS:", facts[:5])

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
            f.fact_text,
            COUNT(DISTINCT r.model_name) AS model_support
        FROM facts f
        JOIN relationships r ON f.id = r.fact_id
        {problem_filter}
        GROUP BY f.id
    ),
    model_stats AS (
        SELECT
            r.model_name,
            COUNT(*) AS total_facts,
            COUNT(DISTINCT f.fact_text) AS unique_facts,
            SUM(CASE WHEN fs.model_support >= 2 THEN 1 ELSE 0 END) AS consensus_facts
        FROM facts f
        JOIN relationships r ON f.id = r.fact_id
        JOIN fact_stats fs ON fs.id = f.id
        {problem_filter}
        GROUP BY r.model_name
    )
    SELECT
        model_name,
        total_facts,
        unique_facts,
        ROUND(CAST(unique_facts AS FLOAT) / total_facts, 3) AS uniqueness_ratio,
        consensus_facts,
        ROUND(CAST(consensus_facts AS FLOAT) / total_facts, 3) AS consensus_ratio,
        ROUND(
            (0.4 * (CAST(unique_facts AS FLOAT) / total_facts)) +
            (0.6 * (CAST(consensus_facts AS FLOAT) / total_facts)),
            3
        ) AS score
    FROM model_stats
    ORDER BY score DESC;
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