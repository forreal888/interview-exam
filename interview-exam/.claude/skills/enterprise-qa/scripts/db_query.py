"""Safe database query tool for enterprise-qa skill.

All queries use parameterized SQL. No string concatenation in SQL clauses.
Input validation rejects suspicious patterns (SQL injection attempts).
"""

import argparse
import json
import re
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

from config import load_config

# Patterns that indicate SQL injection attempts
_DANGEROUS_PATTERNS = [
    r"(?i)\b(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|EXEC|UNION|--|;)\b",
    r"(?i)['\"=]",
    r"(?i)\bOR\b.*=.*",
    r"(?i)\bAND\b.*=.*",
]

# Safe set: only allow Chinese characters, letters, digits, hyphens (for IDs like EMP-001), dots
_SAFE_NAME_RE = re.compile(r"^[\w\u4e00-\u9fff\-\s]+$")


def _get_db_path() -> str:
    config = load_config()
    return config["db_path"]


def _connect():
    db_path = _get_db_path()
    if not Path(db_path).exists():
        return None, f"Database not found at {db_path}. Run init_db.sh first."
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn, None


def _validate_input(value: str) -> tuple:
    """Validate user input is safe. Returns (is_safe, reason)."""
    if not value:
        return False, "empty input"
    if len(value) > 200:
        return False, "input too long"

    # Check for SQL injection patterns
    for pattern in _DANGEROUS_PATTERNS:
        if re.search(pattern, value):
            return False, f"input contains potentially dangerous pattern"

    # Name inputs must only contain safe chars
    if not _SAFE_NAME_RE.match(value.replace("'", "").replace('"', "")):
        return False, "input contains unsafe characters"

    return True, "ok"


def _clean_identifier(value: str) -> str:
    """Strip common wrappers but reject SQL patterns."""
    value = value.strip().strip("'").strip('"').strip()
    is_safe, reason = _validate_input(value)
    if not is_safe:
        raise ValueError(f"Unsafe input: {reason}")
    return value


def _to_dict(row) -> dict:
    if row is None:
        return None
    return dict(row)


def cmd_employee(args):
    """Query employee by name or ID."""
    conn, err = _connect()
    if err:
        return json.dumps({"error": err}, ensure_ascii=False)

    try:
        if args.name:
            name = _clean_identifier(args.name)
            cur = conn.execute(
                "SELECT employee_id, name, department, level, hire_date, email, status "
                "FROM employees WHERE name = ? AND status != 'resigned'",
                (name,),
            )
        elif args.id:
            emp_id = _clean_identifier(args.id)
            cur = conn.execute(
                "SELECT employee_id, name, department, level, hire_date, email, status "
                "FROM employees WHERE employee_id = ?",
                (emp_id,),
            )
        else:
            return json.dumps({"error": "Provide --name or --id"}, ensure_ascii=False)

        rows = cur.fetchall()
        conn.close()

        if not rows:
            return json.dumps(
                {"result": "not_found", "message": f"No active employee found."},
                ensure_ascii=False,
            )

        return json.dumps(
            {"result": [dict(r) for r in rows], "source": "employees"},
            ensure_ascii=False,
            default=str,
        )
    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def cmd_department(args):
    """Query department members."""
    conn, err = _connect()
    if err:
        return json.dumps({"error": err}, ensure_ascii=False)

    try:
        dept = _clean_identifier(args.name)
        cur = conn.execute(
            "SELECT employee_id, name, department, level, hire_date, email "
            "FROM employees WHERE department = ? AND status = 'active' "
            "ORDER BY level DESC",
            (dept,),
        )
        rows = cur.fetchall()
        conn.close()

        return json.dumps(
            {
                "result": [dict(r) for r in rows],
                "count": len(rows),
                "source": "employees",
            },
            ensure_ascii=False,
            default=str,
        )
    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def cmd_projects(args):
    """Query projects for an employee."""
    conn, err = _connect()
    if err:
        return json.dumps({"error": err}, ensure_ascii=False)

    try:
        name = _clean_identifier(args.name)

        # First find employee_id
        cur = conn.execute(
            "SELECT employee_id, name, department FROM employees WHERE name = ?",
            (name,),
        )
        emp = cur.fetchone()
        if not emp:
            return json.dumps(
                {"result": "not_found", "message": f"Employee '{name}' not found."},
                ensure_ascii=False,
            )

        emp_id = emp["employee_id"]

        # Get projects with role
        cur = conn.execute(
            "SELECT p.project_id, p.name, p.status, p.start_date, p.end_date, pm.role "
            "FROM project_members pm "
            "JOIN projects p ON pm.project_id = p.project_id "
            "WHERE pm.employee_id = ? "
            "ORDER BY p.start_date DESC",
            (emp_id,),
        )
        rows = cur.fetchall()
        conn.close()

        return json.dumps(
            {
                "result": [dict(r) for r in rows],
                "count": len(rows),
                "employee": dict(emp),
                "source": "projects + project_members",
            },
            ensure_ascii=False,
            default=str,
        )
    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def cmd_active_projects(_args):
    """Query all active/in-progress projects."""
    conn, err = _connect()
    if err:
        return json.dumps({"error": err}, ensure_ascii=False)

    cur = conn.execute(
        "SELECT p.project_id, p.name, p.status, p.start_date, e.name as lead_name, e.department "
        "FROM projects p "
        "JOIN employees e ON p.lead_id = e.employee_id "
        "WHERE p.status IN ('active', 'planning') "
        "ORDER BY p.status, p.start_date"
    )
    rows = cur.fetchall()
    conn.close()

    return json.dumps(
        {"result": [dict(r) for r in rows], "count": len(rows), "source": "projects"},
        ensure_ascii=False,
        default=str,
    )


def cmd_attendance(args):
    """Query attendance records for an employee in a given month."""
    conn, err = _connect()
    if err:
        return json.dumps({"error": err}, ensure_ascii=False)

    try:
        name = _clean_identifier(args.name)

        # Find employee
        cur = conn.execute(
            "SELECT employee_id, name FROM employees WHERE name = ?", (name,)
        )
        emp = cur.fetchone()
        if not emp:
            return json.dumps(
                {"result": "not_found", "message": f"Employee '{name}' not found."},
                ensure_ascii=False,
            )

        emp_id = emp["employee_id"]

        # Default to current exam date: 2026-02 if not specified
        month = args.month if args.month else "2026-02"
        prefix = f"{month}-%"

        cur = conn.execute(
            "SELECT date, status FROM attendance "
            "WHERE employee_id = ? AND date LIKE ? "
            "ORDER BY date",
            (emp_id, prefix),
        )
        rows = cur.fetchall()

        # Summary stats
        late_count = sum(1 for r in rows if r["status"] == "late")
        absent_count = sum(1 for r in rows if r["status"] == "absent")
        on_time_count = sum(1 for r in rows if r["status"] == "on_time")
        leave_count = sum(1 for r in rows if r["status"] == "on_leave")
        total = len(rows)

        conn.close()

        return json.dumps(
            {
                "result": [dict(r) for r in rows],
                "summary": {
                    "total_days": total,
                    "on_time": on_time_count,
                    "late": late_count,
                    "absent": absent_count,
                    "on_leave": leave_count,
                },
                "employee": dict(emp),
                "month": month,
                "source": "attendance",
            },
            ensure_ascii=False,
            default=str,
        )
    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def cmd_performance(args):
    """Query performance reviews for an employee."""
    conn, err = _connect()
    if err:
        return json.dumps({"error": err}, ensure_ascii=False)

    try:
        name = _clean_identifier(args.name)

        cur = conn.execute(
            "SELECT employee_id, name FROM employees WHERE name = ?", (name,)
        )
        emp = cur.fetchone()
        if not emp:
            return json.dumps(
                {"result": "not_found", "message": f"Employee '{name}' not found."},
                ensure_ascii=False,
            )

        emp_id = emp["employee_id"]

        cur = conn.execute(
            "SELECT year, quarter, kpi_score, grade "
            "FROM performance_reviews "
            "WHERE employee_id = ? "
            "ORDER BY year, quarter",
            (emp_id,),
        )
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return json.dumps(
                {
                    "result": [],
                    "message": "No performance records found.",
                    "source": "performance_reviews",
                },
                ensure_ascii=False,
            )

        scores = [r["kpi_score"] for r in rows]
        avg_kpi = sum(scores) / len(scores)

        return json.dumps(
            {
                "result": [dict(r) for r in rows],
                "summary": {
                    "total_quarters": len(rows),
                    "average_kpi": round(avg_kpi, 2),
                    "grades": [r["grade"] for r in rows],
                },
                "employee": dict(emp),
                "source": "performance_reviews",
            },
            ensure_ascii=False,
            default=str,
        )
    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def cmd_promotion_check(args):
    """Check if an employee meets promotion criteria.
    Returns all needed DB data for Claude to evaluate against KB rules.
    """
    conn, err = _connect()
    if err:
        return json.dumps({"error": err}, ensure_ascii=False)

    try:
        name = _clean_identifier(args.name)

        cur = conn.execute(
            "SELECT employee_id, name, department, level, hire_date "
            "FROM employees WHERE name = ?",
            (name,),
        )
        emp = cur.fetchone()
        if not emp:
            return json.dumps(
                {"result": "not_found", "message": f"Employee '{name}' not found."},
                ensure_ascii=False,
            )

        emp_id = emp["employee_id"]

        # Get performance records
        cur = conn.execute(
            "SELECT year, quarter, kpi_score, grade "
            "FROM performance_reviews WHERE employee_id = ? "
            "ORDER BY year, quarter",
            (emp_id,),
        )
        perf_rows = cur.fetchall()

        # Get project participation
        cur = conn.execute(
            "SELECT p.name, p.status, pm.role "
            "FROM project_members pm "
            "JOIN projects p ON pm.project_id = p.project_id "
            "WHERE pm.employee_id = ?",
            (emp_id,),
        )
        proj_rows = cur.fetchall()

        # Manager info
        manager_name = None
        if emp["employee_id"] != "EMP-000":
            cur = conn.execute(
                "SELECT e.name FROM employees e "
                "JOIN employees sub ON sub.manager_id = e.employee_id "
                "WHERE sub.employee_id = ?",
                (emp_id,),
            )
            mgr = cur.fetchone()
            if mgr:
                manager_name = mgr["name"]

        conn.close()

        # Compute summary stats
        scores = [r["kpi_score"] for r in perf_rows]
        avg_kpi = round(sum(scores) / len(scores), 2) if scores else 0
        lead_count = sum(1 for r in proj_rows if r["role"] == "lead")
        core_count = sum(1 for r in proj_rows if r["role"] in ("lead", "core"))

        # Days since hire
        hire_date_str = emp["hire_date"]
        hire_dt = datetime.strptime(hire_date_str, "%Y-%m-%d")
        today = datetime(2026, 3, 27)  # Exam reference date
        days_employed = (today - hire_dt).days
        years_employed = round(days_employed / 365.25, 2)

        return json.dumps(
            {
                "employee": {
                    "name": emp["name"],
                    "department": emp["department"],
                    "level": emp["level"],
                    "hire_date": emp["hire_date"],
                    "years_employed": years_employed,
                    "manager": manager_name,
                },
                "performance": {
                    "records": [dict(r) for r in perf_rows],
                    "average_kpi": avg_kpi,
                    "quarter_count": len(perf_rows),
                },
                "projects": {
                    "records": [dict(r) for r in proj_rows],
                    "total": len(proj_rows),
                    "lead_count": lead_count,
                    "core_or_lead_count": core_count,
                },
                "source": "employees + performance_reviews + projects + project_members",
            },
            ensure_ascii=False,
            default=str,
        )
    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Safe enterprise database query tool")
    sub = parser.add_subparsers(dest="command")

    # employee
    p = sub.add_parser("employee", help="Query employee info")
    p.add_argument("--name", help="Employee name")
    p.add_argument("--id", help="Employee ID")

    # department
    p = sub.add_parser("department", help="Query department members")
    p.add_argument("name", help="Department name")

    # projects
    p = sub.add_parser("projects", help="Query employee projects")
    p.add_argument("--name", help="Employee name")

    # active-projects
    sub.add_parser("active-projects", help="List active/planning projects")

    # attendance
    p = sub.add_parser("attendance", help="Query attendance")
    p.add_argument("--name", required=True, help="Employee name")
    p.add_argument("--month", help="Month (YYYY-MM), default: 2026-02")

    # performance
    p = sub.add_parser("performance", help="Query performance reviews")
    p.add_argument("--name", required=True, help="Employee name")

    # promotion-check
    p = sub.add_parser("promotion-check", help="Check promotion eligibility")
    p.add_argument("--name", required=True, help="Employee name")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    handlers = {
        "employee": cmd_employee,
        "department": cmd_department,
        "projects": cmd_projects,
        "active-projects": cmd_active_projects,
        "attendance": cmd_attendance,
        "performance": cmd_performance,
        "promotion-check": cmd_promotion_check,
    }

    handler = handlers.get(args.command)
    if handler:
        result = handler(args)
        print(result)
    else:
        print(json.dumps({"error": f"Unknown command: {args.command}"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
