"""
SQLite DB setup and operations for PromptCI.
"""

import sqlite3
from config.settings import DB_PATH

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS runs (
      id TEXT PRIMARY KEY,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
      prompt_file TEXT,
      prompt_v1_hash TEXT,
      prompt_v2_hash TEXT,
      status TEXT,
      total_tests INTEGER DEFAULT 0,
      passed INTEGER DEFAULT 0,
      regressions INTEGER DEFAULT 0,
      improvements INTEGER DEFAULT 0,
      failures INTEGER DEFAULT 0,
      errors INTEGER DEFAULT 0,
      pass_rate REAL DEFAULT 0.0,
      has_fix BOOLEAN DEFAULT 0,
      fix_status TEXT,
      fix_iterations INTEGER DEFAULT 0,
      fixed_prompt TEXT,
      report_path TEXT,
      repo_path TEXT,
      approval_status TEXT DEFAULT 'pending'
    )
    ''')

    c.execute('''
    CREATE TABLE IF NOT EXISTS test_results (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id TEXT,
      test_case_id TEXT,
      category TEXT,
      input_text TEXT,
      expected_behaviour TEXT,
      output_v1 TEXT,
      output_v2 TEXT,
      output_v1_error TEXT,
      output_v2_error TEXT,
      v1_score REAL,
      v2_score REAL,
      verdict TEXT,
      regression_reason TEXT,
      recommendation TEXT,
      FOREIGN KEY(run_id) REFERENCES runs(id)
    )
    ''')
    conn.commit()

    # Migrations — safely add columns that may not exist in older DB files
    existing = {row[1] for row in c.execute("PRAGMA table_info(runs)")}
    migrations = [
        ("repo_path", "ALTER TABLE runs ADD COLUMN repo_path TEXT"),
        ("failures", "ALTER TABLE runs ADD COLUMN failures INTEGER DEFAULT 0"),
        ("errors", "ALTER TABLE runs ADD COLUMN errors INTEGER DEFAULT 0"),
    ]
    for col, sql in migrations:
        if col not in existing:
            c.execute(sql)

    test_result_existing = {row[1] for row in c.execute("PRAGMA table_info(test_results)")}
    test_result_migrations = [
        ("output_v1_error", "ALTER TABLE test_results ADD COLUMN output_v1_error TEXT DEFAULT ''"),
        ("output_v2_error", "ALTER TABLE test_results ADD COLUMN output_v2_error TEXT DEFAULT ''"),
    ]
    for col, sql in test_result_migrations:
        if col not in test_result_existing:
            c.execute(sql)
    conn.commit()
    conn.close()

def create_run(run_id: str, prompt_file: str, prompt_v1_hash: str, prompt_v2_hash: str, repo_path: str = "") -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO runs (id, prompt_file, prompt_v1_hash, prompt_v2_hash, status, repo_path) VALUES (?, ?, ?, ?, ?, ?)",
        (run_id, prompt_file, prompt_v1_hash, prompt_v2_hash, "running", repo_path)
    )
    conn.commit()
    conn.close()

def update_run_status(run_id: str, status: str) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE runs SET status = ? WHERE id = ?", (status, run_id))
    conn.commit()
    conn.close()

def complete_run(run_id: str, summary_dict: dict, fix_result_dict: dict, report_path: str) -> None:
    conn = get_connection()
    c = conn.cursor()
    
    has_fix = 1 if fix_result_dict.get("status") == "resolved" else 0
    c.execute('''
        UPDATE runs 
        SET status = 'complete',
            total_tests = ?, passed = ?, regressions = ?, improvements = ?, failures = ?, errors = ?, pass_rate = ?,
            has_fix = ?, fix_status = ?, fix_iterations = ?, fixed_prompt = ?,
            report_path = ?
        WHERE id = ?
    ''', (
        summary_dict.get("total", 0),
        summary_dict.get("passed", 0),
        summary_dict.get("regressions", 0),
        summary_dict.get("improvements", 0),
        summary_dict.get("failures", 0),
        summary_dict.get("errors", 0),
        summary_dict.get("pass_rate", 0.0),
        has_fix,
        fix_result_dict.get("status", "no_fix_needed"),
        fix_result_dict.get("iterations", 0),
        fix_result_dict.get("fixed_prompt", ""),
        report_path,
        run_id
    ))
    conn.commit()
    conn.close()

def save_test_result(run_id: str, test_case_id: str, result_dict: dict) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO test_results 
        (run_id, test_case_id, category, input_text, expected_behaviour, output_v1, output_v2, output_v1_error, output_v2_error, v1_score, v2_score, verdict, regression_reason, recommendation)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        run_id,
        test_case_id,
        result_dict.get("category", ""),
        result_dict.get("input", ""),
        result_dict.get("expected_behaviour", ""),
        result_dict.get("output_v1", ""),
        result_dict.get("output_v2", ""),
        result_dict.get("output_v1_error", ""),
        result_dict.get("output_v2_error", ""),
        result_dict.get("v1_average", 0.0),
        result_dict.get("v2_average", 0.0),
        result_dict.get("verdict", "PASS"),
        result_dict.get("regression_reason", ""),
        result_dict.get("recommendation", "")
    ))
    conn.commit()
    conn.close()

def get_run(run_id: str) -> dict | None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None

def get_test_results(run_id: str) -> list[dict]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM test_results WHERE run_id = ?", (run_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_recent_runs(limit: int = 20) -> list[dict]:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_approval_status(run_id: str, status: str) -> None:
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE runs SET approval_status = ? WHERE id = ?", (status, run_id))
    conn.commit()
    conn.close()

def get_stats() -> dict:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as total_runs, SUM(regressions) as total_regressions_caught, SUM(has_fix) as total_fixes_applied, AVG(pass_rate) as avg_pass_rate, SUM(errors) as total_errors FROM runs")
    row = c.fetchone()
    conn.close()
    
    return {
        "total_runs": row["total_runs"] or 0,
        "total_regressions_caught": row["total_regressions_caught"] or 0,
        "total_fixes_applied": row["total_fixes_applied"] or 0,
        "avg_pass_rate": row["avg_pass_rate"] or 0.0,
        "total_errors": row["total_errors"] or 0
    }
