import pandas as pd
import pytest

from core.query_executor import QueryExecutionError, QueryExecutor
from core.sql_generator import SQLGenerator, clean_sql
from core.sql_validator import SQLValidator
from database.database_manager import DatabaseManager


class FakeLLM:
    def __init__(self, reply: str):
        self.reply = reply
        self.calls = []

    def chat(self, system, user, **kwargs):
        self.calls.append(user)
        return self.reply


@pytest.fixture
def db():
    manager = DatabaseManager()
    manager.load_tables(
        {"employees": pd.DataFrame({"name": ["Asha", "Ravi", "Meera"], "salary": [100.0, 200.0, 300.0]})}
    )
    return manager


def test_clean_sql_strips_fences_and_semicolon():
    assert clean_sql("```sql\nSELECT 1;\n```") == "SELECT 1"


def test_clean_sql_drops_leading_chatter():
    assert clean_sql("Sure! Here you go: SELECT AVG(salary) FROM employees;") == (
        "SELECT AVG(salary) FROM employees"
    )


def test_generator_returns_clean_sql():
    llm = FakeLLM("```sql\nSELECT COUNT(*) FROM employees;\n```")
    sql = SQLGenerator(llm).generate("how many?", "Table: employees", clarifications="", assumptions=[])
    assert sql == "SELECT COUNT(*) FROM employees"
    assert "how many?" in llm.calls[0]


def test_generator_includes_clarifications_in_prompt():
    llm = FakeLLM("SELECT 1")
    SQLGenerator(llm).generate("top staff", "schema", clarifications="- by what? -> salary")
    assert "by what? -> salary" in llm.calls[0]


def test_validator_accepts_select(db):
    assert SQLValidator(db).validate("SELECT AVG(salary) FROM employees;").is_valid


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE employees",
        "DELETE FROM employees",
        "UPDATE employees SET salary = 0",
        "SELECT 1; DROP TABLE employees",
        "PRAGMA table_info(employees)",
    ],
)
def test_validator_rejects_unsafe_sql(db, sql):
    assert not SQLValidator(db).validate(sql).is_valid


def test_validator_rejects_unknown_column(db):
    result = SQLValidator(db).validate("SELECT bonus FROM employees")
    assert not result.is_valid
    assert "bonus" in result.error


def test_validator_ignores_keywords_inside_strings(db):
    assert SQLValidator(db).validate("SELECT * FROM employees WHERE name = 'drop table'").is_valid


def test_executor_returns_dataframe(db):
    result = QueryExecutor(db).execute("SELECT AVG(salary) AS avg_salary FROM employees")
    assert result.df.iat[0, 0] == 200.0
    assert not result.truncated


def test_executor_truncates(db):
    result = QueryExecutor(db, max_rows=2).execute("SELECT * FROM employees")
    assert result.row_count == 2 and result.truncated


def test_database_is_read_only(db):
    with pytest.raises(QueryExecutionError):
        QueryExecutor(db).execute("DELETE FROM employees")
