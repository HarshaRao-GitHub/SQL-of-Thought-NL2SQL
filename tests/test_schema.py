"""Tests for schema extraction and database operations."""

import pytest
import tempfile
import sqlite3
from pathlib import Path

from src.core.schema import SchemaExtractor, DatabaseSchema, TableInfo, ColumnInfo
from src.database.executor import SQLExecutor, ExecutionStatus


@pytest.fixture
def sample_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE
        );

        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            total DECIMAL(10, 2),
            status TEXT DEFAULT 'pending'
        );

        INSERT INTO users VALUES (1, 'Alice', 'alice@example.com');
        INSERT INTO users VALUES (2, 'Bob', 'bob@example.com');
        INSERT INTO orders VALUES (1, 1, 100.00, 'completed');
        INSERT INTO orders VALUES (2, 1, 50.00, 'pending');
        INSERT INTO orders VALUES (3, 2, 200.00, 'completed');
    """)

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


class TestSchemaExtractor:
    """Tests for SchemaExtractor class."""

    def test_extract_tables(self, sample_db):
        extractor = SchemaExtractor(f"sqlite:///{sample_db}")
        schema = extractor.extract(include_samples=False)

        assert len(schema.tables) == 2
        assert "users" in schema.get_table_names()
        assert "orders" in schema.get_table_names()

    def test_extract_columns(self, sample_db):
        extractor = SchemaExtractor(f"sqlite:///{sample_db}")
        schema = extractor.extract(include_samples=False)

        users_table = schema.get_table("users")
        assert users_table is not None
        assert len(users_table.columns) == 3

        column_names = [c.name for c in users_table.columns]
        assert "id" in column_names
        assert "name" in column_names
        assert "email" in column_names

    def test_extract_with_samples(self, sample_db):
        extractor = SchemaExtractor(f"sqlite:///{sample_db}")
        schema = extractor.extract(include_samples=True)

        users_table = schema.get_table("users")
        assert users_table.sample_values
        assert "name" in users_table.sample_values

    def test_to_schema_string(self, sample_db):
        extractor = SchemaExtractor(f"sqlite:///{sample_db}")
        schema = extractor.extract(include_samples=False)

        schema_str = schema.to_schema_string()
        assert "CREATE TABLE" in schema_str
        assert "users" in schema_str
        assert "orders" in schema_str


class TestSQLExecutor:
    """Tests for SQLExecutor class."""

    def test_execute_select(self, sample_db):
        executor = SQLExecutor(f"sqlite:///{sample_db}")
        result = executor.execute("SELECT * FROM users;")

        assert result.success
        assert result.row_count == 2
        assert "id" in result.columns
        assert "name" in result.columns

    def test_execute_with_filter(self, sample_db):
        executor = SQLExecutor(f"sqlite:///{sample_db}")
        result = executor.execute("SELECT * FROM users WHERE name = 'Alice';")

        assert result.success
        assert result.row_count == 1
        assert result.data[0]["name"] == "Alice"

    def test_execute_join(self, sample_db):
        executor = SQLExecutor(f"sqlite:///{sample_db}")
        result = executor.execute("""
            SELECT u.name, o.total
            FROM users u
            JOIN orders o ON u.id = o.user_id
            WHERE o.status = 'completed';
        """)

        assert result.success
        assert result.row_count == 2

    def test_execute_aggregate(self, sample_db):
        executor = SQLExecutor(f"sqlite:///{sample_db}")
        result = executor.execute("""
            SELECT user_id, SUM(total) as total_spent
            FROM orders
            GROUP BY user_id;
        """)

        assert result.success
        assert result.row_count == 2

    def test_syntax_error(self, sample_db):
        executor = SQLExecutor(f"sqlite:///{sample_db}")
        result = executor.execute("SELEC * FROM users;")

        assert not result.success
        assert result.status in [ExecutionStatus.SYNTAX_ERROR, ExecutionStatus.RUNTIME_ERROR]
        assert result.error_message is not None

    def test_table_not_found(self, sample_db):
        executor = SQLExecutor(f"sqlite:///{sample_db}")
        result = executor.execute("SELECT * FROM nonexistent;")

        assert not result.success
        assert result.error_message is not None

    def test_read_only_mode(self, sample_db):
        executor = SQLExecutor(f"sqlite:///{sample_db}", read_only=True)
        result = executor.execute("INSERT INTO users VALUES (3, 'Charlie', 'c@x.com');")

        assert not result.success
        assert result.status == ExecutionStatus.PERMISSION_ERROR

    def test_test_connection(self, sample_db):
        executor = SQLExecutor(f"sqlite:///{sample_db}")
        success, error = executor.test_connection()

        assert success
        assert error is None


class TestDatabaseSchema:
    """Tests for DatabaseSchema class."""

    def test_get_table(self):
        tables = [
            TableInfo(name="users", columns=[ColumnInfo(name="id", data_type="INTEGER")]),
            TableInfo(name="orders", columns=[ColumnInfo(name="id", data_type="INTEGER")]),
        ]
        schema = DatabaseSchema(tables=tables)

        assert schema.get_table("users") is not None
        assert schema.get_table("orders") is not None
        assert schema.get_table("nonexistent") is None

    def test_get_table_names(self):
        tables = [
            TableInfo(name="users", columns=[]),
            TableInfo(name="orders", columns=[]),
        ]
        schema = DatabaseSchema(tables=tables)

        names = schema.get_table_names()
        assert "users" in names
        assert "orders" in names
