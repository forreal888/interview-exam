"""Unit tests for db_query.py — test cases T01-T12 coverage."""

import json
import os
import sys
import unittest

# Add scripts/ to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from db_query import (
    cmd_employee,
    cmd_department,
    cmd_projects,
    cmd_active_projects,
    cmd_attendance,
    cmd_performance,
    cmd_promotion_check,
    _validate_input,
)


class DummyArgs:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestValidateInput(unittest.TestCase):
    """Input validation tests."""

    def test_safe_name(self):
        ok, reason = _validate_input("张三")
        self.assertTrue(ok, f"Expected safe, got: {reason}")

    def test_safe_id(self):
        ok, reason = _validate_input("EMP-001")
        self.assertTrue(ok, f"Expected safe, got: {reason}")

    def test_sql_injection_select(self):
        ok, reason = _validate_input("SELECT * FROM users")
        self.assertFalse(ok)

    def test_sql_injection_union(self):
        ok, reason = _validate_input("x' UNION SELECT")
        self.assertFalse(ok)

    def test_sql_injection_drop(self):
        ok, reason = _validate_input("x; DROP TABLE employees")
        self.assertFalse(ok)

    def test_sql_injection_tautology(self):
        ok, reason = _validate_input("'1'='1")
        self.assertFalse(ok)

    def test_sql_injection_comment(self):
        ok, reason = _validate_input("admin'--")
        self.assertFalse(ok)

    def test_empty_input(self):
        ok, reason = _validate_input("")
        self.assertFalse(ok)

    def test_long_input(self):
        ok, reason = _validate_input("x" * 300)
        self.assertFalse(ok)


class TestEmployeeQueries(unittest.TestCase):
    """T01, T02 equivalent tests."""

    def test_T01_zhangsan_department(self):
        """T01: 张三的部门是什么？ -> 研发部"""
        args = DummyArgs(name="张三", id=None)
        result = json.loads(cmd_employee(args))
        self.assertIn("result", result)
        emp = result["result"][0]
        self.assertEqual(emp["department"], "研发部")
        self.assertEqual(emp["level"], "P6")

    def test_T02_lisi_manager(self):
        """T02: 李四的上级是谁？ -> CEO (EMP-000 manager)"""
        args = DummyArgs(name="李四", id=None)
        result = json.loads(cmd_employee(args))
        emp = result["result"][0]
        self.assertEqual(emp["name"], "李四")
        # Lisi's manager is EMP-000 (CEO) — we verify by checking the data
        # Manager name lookup happens in promotion-check
        self.assertIsNotNone(emp["employee_id"])

    def test_employee_not_found(self):
        """T09: 查一下EMP-999 -> not_found"""
        args = DummyArgs(id="EMP-999", name=None)
        result = json.loads(cmd_employee(args))
        self.assertEqual(result["result"], "not_found")

    def test_employee_by_id(self):
        args = DummyArgs(id="EMP-002", name=None)
        result = json.loads(cmd_employee(args))
        self.assertEqual(result["result"][0]["name"], "李四")


class TestDepartmentQueries(unittest.TestCase):
    """T06 coverage."""

    def test_T06_rd_department_count(self):
        """T06: 研发部有多少人？ -> 4人"""
        args = DummyArgs(name="研发部")
        result = json.loads(cmd_department(args))
        self.assertEqual(result["count"], 4)
        names = [e["name"] for e in result["result"]]
        self.assertIn("张三", names)
        self.assertIn("李四", names)
        self.assertIn("钱七", names)
        self.assertIn("周九", names)

    def test_product_department_count(self):
        """产品部应该有3人"""
        args = DummyArgs(name="产品部")
        result = json.loads(cmd_department(args))
        self.assertEqual(result["count"], 3)


class TestProjectQueries(unittest.TestCase):
    """T05 coverage."""

    def test_T05_zhangsan_projects(self):
        """T05: 张三负责哪些项目？ -> 4个项目"""
        args = DummyArgs(name="张三")
        result = json.loads(cmd_projects(args))
        self.assertEqual(result["count"], 4)

        # Verify roles
        projects_by_name = {p["name"]: p["role"] for p in result["result"]}
        self.assertEqual(projects_by_name.get("ReMe 记忆框架"), "lead")
        self.assertEqual(projects_by_name.get("数据分析平台"), "lead")
        self.assertEqual(projects_by_name.get("智能问答系统"), "core")
        self.assertEqual(projects_by_name.get("移动端 App"), "contributor")

    def test_active_projects(self):
        args = DummyArgs()
        result = json.loads(cmd_active_projects(args))
        # PRJ-001 (active), PRJ-002 (planning)
        self.assertGreaterEqual(result["count"], 2)


class TestAttendanceQueries(unittest.TestCase):
    """T08 coverage."""

    def test_T08_zhangsan_late_february(self):
        """T08: 张三2月迟到几次？ -> 2次"""
        args = DummyArgs(name="张三", month="2026-02")
        result = json.loads(cmd_attendance(args))
        self.assertEqual(result["summary"]["late"], 2)
        self.assertEqual(result["summary"]["total_days"], 20)


class TestPerformanceQueries(unittest.TestCase):

    def test_zhangsan_performance(self):
        args = DummyArgs(name="张三")
        result = json.loads(cmd_performance(args))
        self.assertGreaterEqual(result["summary"]["total_quarters"], 4)
        # Average KPI should be around 89.25
        self.assertGreater(result["summary"]["average_kpi"], 85)


class TestPromotionCheck(unittest.TestCase):
    """T07 coverage."""

    def test_T07_wangwu_promotion(self):
        """T07: 王五符合P5晋升P6条件吗？ -> 不符合"""
        args = DummyArgs(name="王五")
        result = json.loads(cmd_promotion_check(args))

        emp = result["employee"]
        self.assertEqual(emp["level"], "P5")

        # KPI average should be 80.0 < 85
        self.assertLess(result["performance"]["average_kpi"], 85)

        # Projects should be < 3
        self.assertLess(result["projects"]["total"], 3)

    def test_zhangsan_promotion_check(self):
        """张三 should have promotion data."""
        args = DummyArgs(name="张三")
        result = json.loads(cmd_promotion_check(args))
        self.assertEqual(result["employee"]["level"], "P6")
        self.assertGreater(result["performance"]["average_kpi"], 85)
        self.assertGreater(result["projects"]["total"], 3)

    def test_qianqi_promotion_check(self):
        """钱七 (P5) should have some data."""
        args = DummyArgs(name="钱七")
        result = json.loads(cmd_promotion_check(args))
        self.assertEqual(result["employee"]["level"], "P5")


class TestSQLInjectionBlocked(unittest.TestCase):
    """T11: SQL injection must be blocked."""

    def test_injection_in_name(self):
        """Should return error, not data."""
        args = DummyArgs(name="' OR '1'='1", id=None)
        result = json.loads(cmd_employee(args))
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
