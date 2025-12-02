"""Helper utilities for SQL-of-Thought framework."""

import re
from typing import Optional

import sqlparse


def extract_sql_from_text(text: str) -> Optional[str]:
    """Extract SQL query from text containing code blocks or raw SQL.

    Args:
        text: Text potentially containing SQL

    Returns:
        Extracted SQL query or None
    """
    if not text:
        return None

    # Try to find SQL in code blocks
    sql_block_pattern = r"```sql\s*([\s\S]*?)\s*```"
    matches = re.findall(sql_block_pattern, text, re.IGNORECASE)
    if matches:
        return matches[-1].strip()

    # Try generic code blocks
    code_block_pattern = r"```\s*([\s\S]*?)\s*```"
    matches = re.findall(code_block_pattern, text)
    for match in matches:
        if _looks_like_sql(match):
            return match.strip()

    # Try to find SQL statements directly
    sql_keywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "WITH", "CREATE"]
    for keyword in sql_keywords:
        pattern = rf"({keyword}\s+[\s\S]+?)(;|$)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            sql = match.group(1).strip()
            if not sql.endswith(";"):
                sql += ";"
            return sql

    return None


def _looks_like_sql(text: str) -> bool:
    """Check if text appears to be SQL."""
    sql_keywords = [
        "SELECT",
        "FROM",
        "WHERE",
        "JOIN",
        "INSERT",
        "UPDATE",
        "DELETE",
        "CREATE",
        "DROP",
        "ALTER",
    ]
    text_upper = text.upper()
    return any(keyword in text_upper for keyword in sql_keywords)


def format_sql(sql: str, indent: int = 2) -> str:
    """Format SQL query for better readability.

    Args:
        sql: SQL query to format
        indent: Number of spaces for indentation

    Returns:
        Formatted SQL query
    """
    return sqlparse.format(
        sql,
        reindent=True,
        indent_width=indent,
        keyword_case="upper",
        identifier_case="lower",
        strip_comments=False,
        use_space_around_operators=True,
    )


def sanitize_sql(sql: str) -> str:
    """Basic sanitization of SQL query.

    Note: This is NOT a security measure against SQL injection.
    It only cleans up the query for display/logging purposes.

    Args:
        sql: SQL query to sanitize

    Returns:
        Sanitized SQL query
    """
    # Remove leading/trailing whitespace
    sql = sql.strip()

    # Normalize line endings
    sql = sql.replace("\r\n", "\n").replace("\r", "\n")

    # Remove multiple consecutive empty lines
    sql = re.sub(r"\n{3,}", "\n\n", sql)

    # Ensure it ends with semicolon
    if sql and not sql.endswith(";"):
        sql += ";"

    return sql


def get_sql_type(sql: str) -> str:
    """Determine the type of SQL statement.

    Args:
        sql: SQL query

    Returns:
        Statement type (SELECT, INSERT, UPDATE, DELETE, etc.)
    """
    parsed = sqlparse.parse(sql)
    if parsed:
        return parsed[0].get_type()
    return "UNKNOWN"


def count_sql_statements(sql: str) -> int:
    """Count the number of SQL statements in a string.

    Args:
        sql: SQL text potentially containing multiple statements

    Returns:
        Number of statements
    """
    parsed = sqlparse.parse(sql)
    return len([stmt for stmt in parsed if stmt.get_type() != "UNKNOWN"])


def extract_table_names(sql: str) -> list[str]:
    """Extract table names from SQL query.

    Args:
        sql: SQL query

    Returns:
        List of table names
    """
    tables = set()

    # Simple regex patterns for table extraction
    # FROM clause
    from_pattern = r"\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*)"
    tables.update(re.findall(from_pattern, sql, re.IGNORECASE))

    # JOIN clauses
    join_pattern = r"\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_]*)"
    tables.update(re.findall(join_pattern, sql, re.IGNORECASE))

    # INTO clause (for INSERT)
    into_pattern = r"\bINTO\s+([a-zA-Z_][a-zA-Z0-9_]*)"
    tables.update(re.findall(into_pattern, sql, re.IGNORECASE))

    # UPDATE clause
    update_pattern = r"\bUPDATE\s+([a-zA-Z_][a-zA-Z0-9_]*)"
    tables.update(re.findall(update_pattern, sql, re.IGNORECASE))

    return list(tables)


def truncate_sql_for_display(sql: str, max_length: int = 200) -> str:
    """Truncate SQL for display purposes.

    Args:
        sql: SQL query
        max_length: Maximum length

    Returns:
        Truncated SQL with ellipsis if needed
    """
    sql = " ".join(sql.split())  # Normalize whitespace
    if len(sql) <= max_length:
        return sql
    return sql[: max_length - 3] + "..."
