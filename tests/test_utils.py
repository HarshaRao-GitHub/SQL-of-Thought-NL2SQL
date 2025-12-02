"""Tests for utility functions."""

import pytest
from src.utils.helpers import (
    extract_sql_from_text,
    format_sql,
    sanitize_sql,
    get_sql_type,
    extract_table_names,
)


class TestExtractSQLFromText:
    """Tests for extract_sql_from_text function."""

    def test_extract_from_sql_code_block(self):
        text = """Here is the query:
```sql
SELECT * FROM users WHERE active = true;
```
That's it!"""
        result = extract_sql_from_text(text)
        assert result == "SELECT * FROM users WHERE active = true;"

    def test_extract_from_generic_code_block(self):
        text = """```
SELECT name FROM customers;
```"""
        result = extract_sql_from_text(text)
        assert result == "SELECT name FROM customers;"

    def test_extract_from_raw_text(self):
        text = "The query is SELECT id, name FROM products WHERE price > 100"
        result = extract_sql_from_text(text)
        assert "SELECT id, name FROM products" in result

    def test_empty_text(self):
        assert extract_sql_from_text("") is None
        assert extract_sql_from_text(None) is None


class TestFormatSQL:
    """Tests for format_sql function."""

    def test_basic_formatting(self):
        sql = "select * from users where id=1"
        result = format_sql(sql)
        assert "SELECT" in result
        assert "FROM" in result
        assert "WHERE" in result

    def test_multiline_query(self):
        sql = "SELECT a, b, c FROM table1 JOIN table2 ON table1.id = table2.id WHERE x > 10"
        result = format_sql(sql)
        assert len(result.split("\n")) > 1  # Should be multi-line


class TestSanitizeSQL:
    """Tests for sanitize_sql function."""

    def test_adds_semicolon(self):
        sql = "SELECT * FROM users"
        result = sanitize_sql(sql)
        assert result.endswith(";")

    def test_strips_whitespace(self):
        sql = "  SELECT * FROM users;  "
        result = sanitize_sql(sql)
        assert not result.startswith(" ")
        assert not result.endswith(" ") or result.endswith(";")

    def test_normalizes_newlines(self):
        sql = "SELECT *\r\nFROM users\rWHERE id = 1"
        result = sanitize_sql(sql)
        assert "\r" not in result


class TestGetSQLType:
    """Tests for get_sql_type function."""

    def test_select(self):
        assert get_sql_type("SELECT * FROM users;") == "SELECT"

    def test_insert(self):
        assert get_sql_type("INSERT INTO users VALUES (1);") == "INSERT"

    def test_update(self):
        assert get_sql_type("UPDATE users SET name = 'x';") == "UPDATE"

    def test_delete(self):
        assert get_sql_type("DELETE FROM users WHERE id = 1;") == "DELETE"


class TestExtractTableNames:
    """Tests for extract_table_names function."""

    def test_simple_select(self):
        sql = "SELECT * FROM users;"
        tables = extract_table_names(sql)
        assert "users" in tables

    def test_with_join(self):
        sql = "SELECT * FROM users JOIN orders ON users.id = orders.user_id;"
        tables = extract_table_names(sql)
        assert "users" in tables
        assert "orders" in tables

    def test_multiple_joins(self):
        sql = """
        SELECT * FROM customers c
        JOIN orders o ON c.id = o.customer_id
        LEFT JOIN products p ON o.product_id = p.id
        """
        tables = extract_table_names(sql)
        assert "customers" in tables
        assert "orders" in tables
        assert "products" in tables
