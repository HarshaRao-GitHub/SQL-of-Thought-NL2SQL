"""Database schema extraction and representation."""

from dataclasses import dataclass, field
from typing import Optional
from sqlalchemy import create_engine, inspect, MetaData, text
from sqlalchemy.engine import Engine


@dataclass
class ColumnInfo:
    """Information about a database column."""

    name: str
    data_type: str
    nullable: bool = True
    primary_key: bool = False
    foreign_key: Optional[str] = None
    default: Optional[str] = None
    comment: Optional[str] = None

    def to_schema_string(self) -> str:
        """Convert to schema representation string."""
        parts = [f"{self.name} {self.data_type}"]
        if self.primary_key:
            parts.append("PRIMARY KEY")
        if not self.nullable:
            parts.append("NOT NULL")
        if self.foreign_key:
            parts.append(f"REFERENCES {self.foreign_key}")
        return " ".join(parts)


@dataclass
class TableInfo:
    """Information about a database table."""

    name: str
    columns: list[ColumnInfo] = field(default_factory=list)
    primary_keys: list[str] = field(default_factory=list)
    foreign_keys: list[dict] = field(default_factory=list)
    comment: Optional[str] = None
    sample_values: dict[str, list] = field(default_factory=dict)

    def to_schema_string(self, include_samples: bool = True) -> str:
        """Convert to schema representation string."""
        lines = [f"CREATE TABLE {self.name} ("]
        col_defs = [f"  {col.to_schema_string()}" for col in self.columns]
        lines.append(",\n".join(col_defs))
        lines.append(");")

        schema_str = "\n".join(lines)

        if include_samples and self.sample_values:
            samples = []
            for col, values in self.sample_values.items():
                if values:
                    samples.append(f"  {col}: {values[:3]}")
            if samples:
                schema_str += "\n-- Sample values:\n" + "\n".join(samples)

        return schema_str


@dataclass
class DatabaseSchema:
    """Complete database schema representation."""

    tables: list[TableInfo] = field(default_factory=list)
    database_name: Optional[str] = None

    def to_schema_string(self, include_samples: bool = True) -> str:
        """Convert to full schema representation string."""
        parts = []
        if self.database_name:
            parts.append(f"-- Database: {self.database_name}\n")

        for table in self.tables:
            parts.append(table.to_schema_string(include_samples))
            parts.append("")

        return "\n".join(parts)

    def get_table(self, name: str) -> Optional[TableInfo]:
        """Get table by name."""
        for table in self.tables:
            if table.name.lower() == name.lower():
                return table
        return None

    def get_table_names(self) -> list[str]:
        """Get all table names."""
        return [t.name for t in self.tables]


class SchemaExtractor:
    """Extract schema information from databases."""

    def __init__(self, connection_string: str):
        """Initialize with database connection string."""
        self.engine: Engine = create_engine(connection_string)
        self.metadata = MetaData()

    def extract(self, include_samples: bool = True, sample_limit: int = 5) -> DatabaseSchema:
        """Extract complete database schema."""
        inspector = inspect(self.engine)
        tables = []

        for table_name in inspector.get_table_names():
            table_info = self._extract_table(table_name, inspector)

            if include_samples:
                table_info.sample_values = self._get_sample_values(
                    table_name, [c.name for c in table_info.columns], sample_limit
                )

            tables.append(table_info)

        return DatabaseSchema(tables=tables, database_name=str(self.engine.url.database))

    def _extract_table(self, table_name: str, inspector) -> TableInfo:
        """Extract information about a single table."""
        columns = []
        pk_columns = inspector.get_pk_constraint(table_name).get("constrained_columns", [])
        fk_info = inspector.get_foreign_keys(table_name)

        # Build FK lookup
        fk_lookup = {}
        for fk in fk_info:
            for col in fk.get("constrained_columns", []):
                ref_table = fk.get("referred_table", "")
                ref_cols = fk.get("referred_columns", [])
                if ref_cols:
                    fk_lookup[col] = f"{ref_table}({ref_cols[0]})"

        for col_info in inspector.get_columns(table_name):
            col = ColumnInfo(
                name=col_info["name"],
                data_type=str(col_info["type"]),
                nullable=col_info.get("nullable", True),
                primary_key=col_info["name"] in pk_columns,
                foreign_key=fk_lookup.get(col_info["name"]),
                default=str(col_info.get("default")) if col_info.get("default") else None,
                comment=col_info.get("comment"),
            )
            columns.append(col)

        return TableInfo(
            name=table_name,
            columns=columns,
            primary_keys=pk_columns,
            foreign_keys=fk_info,
        )

    def _get_sample_values(
        self, table_name: str, columns: list[str], limit: int = 5
    ) -> dict[str, list]:
        """Get sample values from a table."""
        samples = {}
        try:
            with self.engine.connect() as conn:
                for col in columns:
                    query = text(
                        f"SELECT DISTINCT \"{col}\" FROM \"{table_name}\" "
                        f"WHERE \"{col}\" IS NOT NULL LIMIT {limit}"
                    )
                    result = conn.execute(query)
                    values = [row[0] for row in result]
                    if values:
                        samples[col] = values
        except Exception:
            pass  # Silently handle errors for sample extraction
        return samples

    def execute_query(self, sql: str) -> tuple[list[dict], Optional[str]]:
        """Execute a SQL query and return results."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(sql))
                if result.returns_rows:
                    columns = list(result.keys())
                    rows = [dict(zip(columns, row)) for row in result.fetchall()]
                    return rows, None
                return [], None
        except Exception as e:
            return [], str(e)

    def validate_sql_syntax(self, sql: str) -> tuple[bool, Optional[str]]:
        """Validate SQL syntax without executing."""
        import sqlparse

        try:
            parsed = sqlparse.parse(sql)
            if not parsed:
                return False, "Empty or invalid SQL statement"

            stmt = parsed[0]
            if stmt.get_type() == "UNKNOWN":
                return False, "Could not determine SQL statement type"

            return True, None
        except Exception as e:
            return False, str(e)
