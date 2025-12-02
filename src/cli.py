"""Command Line Interface for SQL-of-Thought.

This module provides a rich CLI experience for using the SQL-of-Thought
multi-agent Text-to-SQL system.
"""

import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.markdown import Markdown

from src.core.config import Config, LLMConfig, DatabaseConfig
from src.core.orchestrator import SQLOfThought, PipelineStatus


console = Console()


def print_banner():
    """Print the SQL-of-Thought banner."""
    banner = """
╔═══════════════════════════════════════════════════════════════════╗
║                      SQL-of-Thought                               ║
║          Multi-agentic Text-to-SQL with Error Correction          ║
║                   Based on arXiv:2509.00581                       ║
╚═══════════════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold blue")


def create_config_from_options(
    provider: str,
    model: str | None,
    database: str | None,
    verbose: bool,
) -> Config:
    """Create configuration from CLI options."""
    llm_config = LLMConfig(
        provider=provider,
        model=model or ("gpt-4-turbo-preview" if provider == "openai" else "claude-3-sonnet-20240229"),
    )

    db_config = DatabaseConfig(
        dialect="sqlite",
        database=database or ":memory:",
    )

    return Config(
        llm=llm_config,
        database=db_config,
        verbose=verbose,
    )


@click.group()
@click.version_option(version="1.0.0")
def main():
    """SQL-of-Thought: Multi-agentic Text-to-SQL with Guided Error Correction.

    Convert natural language questions to SQL queries using a multi-agent
    system with automatic error detection and correction.
    """
    pass


@main.command()
@click.argument("question")
@click.option("--database", "-d", help="SQLite database file path")
@click.option("--schema", "-s", help="Schema file path (SQL format)")
@click.option("--provider", "-p", default="openai", type=click.Choice(["openai", "anthropic"]))
@click.option("--model", "-m", help="LLM model to use")
@click.option("--execute/--no-execute", default=True, help="Execute the generated SQL")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
def query(
    question: str,
    database: str | None,
    schema: str | None,
    provider: str,
    model: str | None,
    execute: bool,
    verbose: bool,
):
    """Convert a natural language question to SQL.

    Example:
        sot query "Find all customers who made purchases over $100" -d mydb.sqlite
    """
    print_banner()

    config = create_config_from_options(provider, model, database, verbose)

    try:
        sot = SQLOfThought(config)

        # Load schema if provided
        schema_str = None
        if schema:
            schema_path = Path(schema)
            if schema_path.exists():
                schema_str = schema_path.read_text()
                console.print(f"[green]Loaded schema from {schema}[/green]")
            else:
                console.print(f"[red]Schema file not found: {schema}[/red]")
                sys.exit(1)
        elif database:
            sot.connect_database(f"sqlite:///{database}")
            console.print(f"[green]Connected to database: {database}[/green]")

        console.print(Panel(question, title="Question", border_style="blue"))

        # Process the query
        with console.status("[bold blue]Generating SQL..."):
            result = sot.query(question, schema_override=schema_str)

        # Display result
        if result.success:
            console.print("\n[bold green]✓ SQL Generated Successfully[/bold green]")
            console.print(f"[dim]Iterations: {result.iterations}[/dim]\n")

            if result.reasoning:
                console.print(Panel(result.reasoning, title="Reasoning", border_style="dim"))

            syntax = Syntax(result.sql, "sql", theme="monokai", line_numbers=True)
            console.print(Panel(syntax, title="Generated SQL", border_style="green"))

            if result.execution_result and result.execution_result.success:
                _display_results(result.execution_result)

        else:
            console.print(f"\n[bold red]✗ {result.status.value}[/bold red]")
            if result.error_message:
                console.print(f"[red]{result.error_message}[/red]")

            if result.sql:
                console.print("\n[yellow]Last attempted SQL:[/yellow]")
                syntax = Syntax(result.sql, "sql", theme="monokai")
                console.print(syntax)

    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        if verbose:
            console.print_exception()
        sys.exit(1)


def _display_results(execution_result):
    """Display query execution results in a table."""
    if not execution_result.data:
        console.print("\n[yellow]Query returned no results[/yellow]")
        return

    table = Table(title="Query Results", show_lines=True)

    # Add columns
    for col in execution_result.columns:
        table.add_column(col, style="cyan")

    # Add rows (limit to 20 for display)
    for row in execution_result.data[:20]:
        table.add_row(*[str(row.get(col, "")) for col in execution_result.columns])

    console.print(table)

    if execution_result.row_count > 20:
        console.print(f"[dim]... and {execution_result.row_count - 20} more rows[/dim]")


@main.command()
@click.argument("sql")
@click.option("--database", "-d", required=True, help="SQLite database file path")
@click.option("--schema", "-s", help="Schema file path for validation context")
@click.option("--provider", "-p", default="openai", type=click.Choice(["openai", "anthropic"]))
@click.option("--model", "-m", help="LLM model to use")
def validate(
    sql: str,
    database: str,
    schema: str | None,
    provider: str,
    model: str | None,
):
    """Validate an SQL query.

    Example:
        sot validate "SELECT * FROM users WHERE age > 18" -d mydb.sqlite
    """
    config = create_config_from_options(provider, model, database, False)

    try:
        sot = SQLOfThought(config)
        sot.connect_database(f"sqlite:///{database}")

        schema_str = sot.get_schema() or ""
        if schema:
            schema_str = Path(schema).read_text()

        result = sot.validate_only(sql, schema_str)

        if result["is_valid"]:
            console.print("[bold green]✓ SQL is valid[/bold green]")
        else:
            console.print("[bold red]✗ SQL has issues[/bold red]")

        for error in result["errors"]:
            console.print(f"  [red]• [{error['type']}] {error['message']}[/red]")

        for warning in result["warnings"]:
            console.print(f"  [yellow]• {warning['message']}[/yellow]")

    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        sys.exit(1)


@main.command()
@click.option("--database", "-d", required=True, help="SQLite database file path")
def schema(database: str):
    """Display the database schema.

    Example:
        sot schema -d mydb.sqlite
    """
    try:
        from src.core.schema import SchemaExtractor

        extractor = SchemaExtractor(f"sqlite:///{database}")
        db_schema = extractor.extract(include_samples=True)

        console.print(Panel(
            db_schema.to_schema_string(),
            title=f"Schema: {database}",
            border_style="blue",
        ))

    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        sys.exit(1)


@main.command()
@click.option("--database", "-d", help="SQLite database file path")
@click.option("--schema", "-s", help="Schema file path")
@click.option("--provider", "-p", default="openai", type=click.Choice(["openai", "anthropic"]))
@click.option("--model", "-m", help="LLM model to use")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
def interactive(
    database: str | None,
    schema: str | None,
    provider: str,
    model: str | None,
    verbose: bool,
):
    """Start an interactive SQL-of-Thought session.

    Example:
        sot interactive -d mydb.sqlite
    """
    print_banner()
    console.print("[dim]Type 'exit' or 'quit' to end the session[/dim]")
    console.print("[dim]Type 'schema' to view the database schema[/dim]\n")

    config = create_config_from_options(provider, model, database, verbose)

    try:
        sot = SQLOfThought(config)

        schema_str = None
        if database:
            sot.connect_database(f"sqlite:///{database}")
            console.print(f"[green]Connected to: {database}[/green]\n")
        elif schema:
            schema_str = Path(schema).read_text()
            console.print(f"[green]Loaded schema from: {schema}[/green]\n")
        else:
            console.print("[yellow]No database connected. Provide a schema with each query.[/yellow]\n")

        while True:
            try:
                question = console.input("[bold blue]Question>[/bold blue] ").strip()

                if not question:
                    continue

                if question.lower() in ("exit", "quit", "q"):
                    console.print("[dim]Goodbye![/dim]")
                    break

                if question.lower() == "schema":
                    if sot.schema:
                        console.print(sot.get_schema())
                    else:
                        console.print("[yellow]No schema available[/yellow]")
                    continue

                # Process query
                with console.status("[bold blue]Generating SQL..."):
                    result = sot.query(question, schema_override=schema_str)

                if result.success:
                    syntax = Syntax(result.sql, "sql", theme="monokai")
                    console.print(Panel(syntax, title="SQL", border_style="green"))

                    if result.execution_result and result.execution_result.data:
                        _display_results(result.execution_result)
                else:
                    console.print(f"[red]Failed: {result.error_message}[/red]")
                    if result.sql:
                        console.print(f"[dim]Attempted: {result.sql}[/dim]")

                console.print()

            except KeyboardInterrupt:
                console.print("\n[dim]Use 'exit' to quit[/dim]")
                continue

    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        sys.exit(1)


@main.command()
@click.argument("sql")
@click.option("--database", "-d", required=True, help="SQLite database file path")
def execute(sql: str, database: str):
    """Execute an SQL query directly.

    Example:
        sot execute "SELECT * FROM users LIMIT 10" -d mydb.sqlite
    """
    try:
        from src.database.executor import SQLExecutor

        executor = SQLExecutor(f"sqlite:///{database}")
        result = executor.execute(sql)

        if result.success:
            _display_results(result)
        else:
            console.print(f"[bold red]Execution error: {result.error_message}[/bold red]")

    except Exception as e:
        console.print(f"[bold red]Error: {str(e)}[/bold red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
