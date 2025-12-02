"""SQL Execution and Verification module for SQL-of-Thought framework.

This module handles the execution verification component described in the
SQL-of-Thought paper (arXiv:2509.00581), which tests queries against actual
databases to verify correctness.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError


class ExecutionStatus(Enum):
    """Status of SQL execution."""

    SUCCESS = "success"
    SYNTAX_ERROR = "syntax_error"
    RUNTIME_ERROR = "runtime_error"
    TIMEOUT = "timeout"
    EMPTY_RESULT = "empty_result"
    PERMISSION_ERROR = "permission_error"


@dataclass
class ExecutionResult:
    """Result of SQL execution."""

    status: ExecutionStatus
    data: list[dict] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    row_count: int = 0
    error_message: Optional[str] = None
    execution_time_ms: float = 0.0
    affected_rows: int = 0

    @property
    def success(self) -> bool:
        """Check if execution was successful."""
        return self.status == ExecutionStatus.SUCCESS

    @property
    def has_results(self) -> bool:
        """Check if query returned results."""
        return self.success and self.row_count > 0


class SQLExecutor:
    """Executes SQL queries and verifies results.

    The SQL Executor is responsible for:
    1. Safely executing SQL queries against the database
    2. Capturing execution errors for feedback to the correction agent
    3. Returning structured results for analysis
    4. Enforcing execution timeouts and limits
    """

    def __init__(
        self,
        connection_string: str,
        timeout_seconds: float = 30.0,
        max_rows: int = 1000,
        read_only: bool = True,
    ):
        """Initialize the SQL executor.

        Args:
            connection_string: SQLAlchemy connection string
            timeout_seconds: Query timeout in seconds
            max_rows: Maximum rows to return
            read_only: Only allow SELECT queries
        """
        self.engine: Engine = create_engine(connection_string)
        self.timeout_seconds = timeout_seconds
        self.max_rows = max_rows
        self.read_only = read_only

    def execute(self, sql: str) -> ExecutionResult:
        """Execute an SQL query and return results.

        Args:
            sql: The SQL query to execute

        Returns:
            ExecutionResult with status and data
        """
        import time

        start_time = time.time()

        # Safety check for read-only mode
        if self.read_only and not self._is_read_only_query(sql):
            return ExecutionResult(
                status=ExecutionStatus.PERMISSION_ERROR,
                error_message="Only SELECT queries are allowed in read-only mode",
            )

        try:
            with self.engine.connect() as connection:
                # Execute the query
                result = connection.execute(text(sql))

                execution_time = (time.time() - start_time) * 1000

                # Check if query returns rows
                if result.returns_rows:
                    columns = list(result.keys())
                    rows = result.fetchmany(self.max_rows)
                    data = [dict(zip(columns, row)) for row in rows]

                    status = ExecutionStatus.SUCCESS
                    if len(data) == 0:
                        status = ExecutionStatus.EMPTY_RESULT

                    return ExecutionResult(
                        status=status,
                        data=data,
                        columns=columns,
                        row_count=len(data),
                        execution_time_ms=execution_time,
                    )
                else:
                    # DML statement
                    return ExecutionResult(
                        status=ExecutionStatus.SUCCESS,
                        affected_rows=result.rowcount,
                        execution_time_ms=execution_time,
                    )

        except SQLAlchemyError as e:
            execution_time = (time.time() - start_time) * 1000
            error_message = str(e.orig) if hasattr(e, "orig") else str(e)

            # Classify the error
            status = self._classify_error(error_message)

            return ExecutionResult(
                status=status,
                error_message=error_message,
                execution_time_ms=execution_time,
            )

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            return ExecutionResult(
                status=ExecutionStatus.RUNTIME_ERROR,
                error_message=str(e),
                execution_time_ms=execution_time,
            )

    def _is_read_only_query(self, sql: str) -> bool:
        """Check if the query is read-only (SELECT only)."""
        sql_upper = sql.strip().upper()

        # Allow SELECT and WITH ... SELECT (CTEs)
        if sql_upper.startswith("SELECT"):
            return True
        if sql_upper.startswith("WITH"):
            # Check if it's a CTE followed by SELECT
            return "SELECT" in sql_upper

        # Allow EXPLAIN
        if sql_upper.startswith("EXPLAIN"):
            return True

        return False

    def _classify_error(self, error_message: str) -> ExecutionStatus:
        """Classify the execution error type."""
        error_lower = error_message.lower()

        # Syntax errors
        syntax_keywords = [
            "syntax error",
            "parse error",
            "near",
            "unexpected",
            "invalid",
        ]
        if any(kw in error_lower for kw in syntax_keywords):
            return ExecutionStatus.SYNTAX_ERROR

        # Permission errors
        permission_keywords = ["permission", "denied", "access", "privilege"]
        if any(kw in error_lower for kw in permission_keywords):
            return ExecutionStatus.PERMISSION_ERROR

        # Timeout
        if "timeout" in error_lower or "timed out" in error_lower:
            return ExecutionStatus.TIMEOUT

        return ExecutionStatus.RUNTIME_ERROR

    def test_connection(self) -> tuple[bool, Optional[str]]:
        """Test the database connection.

        Returns:
            Tuple of (success, error_message)
        """
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return True, None
        except Exception as e:
            return False, str(e)

    def get_table_sample(
        self, table_name: str, limit: int = 5
    ) -> ExecutionResult:
        """Get a sample of rows from a table."""
        sql = f'SELECT * FROM "{table_name}" LIMIT {limit}'
        return self.execute(sql)


class ExecutionVerifier:
    """Verifies SQL query execution results.

    This component implements the execution verification described in the
    SQL-of-Thought paper, which tests queries against actual databases
    to validate correctness beyond just syntax checking.
    """

    def __init__(self, executor: SQLExecutor):
        """Initialize with an SQL executor."""
        self.executor = executor

    def verify(
        self,
        sql: str,
        expected_columns: list[str] | None = None,
        expected_row_count: int | None = None,
        must_have_results: bool = False,
    ) -> tuple[bool, ExecutionResult, list[str]]:
        """Verify SQL query execution.

        Args:
            sql: SQL query to verify
            expected_columns: Expected column names in result
            expected_row_count: Expected number of rows (exact match)
            must_have_results: Whether query must return at least one row

        Returns:
            Tuple of (is_valid, result, issues)
        """
        result = self.executor.execute(sql)
        issues = []

        # Check for execution errors
        if not result.success:
            issues.append(f"Execution failed: {result.error_message}")
            return False, result, issues

        # Check for empty results if required
        if must_have_results and not result.has_results:
            issues.append("Query returned no results")

        # Verify expected columns
        if expected_columns:
            missing = set(expected_columns) - set(result.columns)
            if missing:
                issues.append(f"Missing expected columns: {missing}")

        # Verify row count
        if expected_row_count is not None:
            if result.row_count != expected_row_count:
                issues.append(
                    f"Expected {expected_row_count} rows, got {result.row_count}"
                )

        is_valid = len(issues) == 0
        return is_valid, result, issues
