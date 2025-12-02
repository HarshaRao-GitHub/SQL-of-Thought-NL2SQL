#!/usr/bin/env python3
"""
SQL-of-Thought Basic Usage Examples

This script demonstrates how to use the SQL-of-Thought framework
for converting natural language to SQL queries.
"""

import os
from pathlib import Path

# Add the project root to the path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import Config, LLMConfig, DatabaseConfig
from src.core.orchestrator import SQLOfThought, text_to_sql


# Sample schema for testing
SAMPLE_SCHEMA = """
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE,
    city VARCHAR(50),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(50),
    price DECIMAL(10, 2) NOT NULL,
    stock_quantity INTEGER DEFAULT 0
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(customer_id),
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_amount DECIMAL(10, 2),
    status VARCHAR(20) DEFAULT 'pending'
);

CREATE TABLE order_items (
    item_id INTEGER PRIMARY KEY,
    order_id INTEGER REFERENCES orders(order_id),
    product_id INTEGER REFERENCES products(product_id),
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL
);
"""


def example_quick_conversion():
    """Quick conversion using the convenience function."""
    print("=" * 60)
    print("Example 1: Quick Conversion")
    print("=" * 60)

    question = "Find all customers who have placed orders over $500"

    sql, reasoning = text_to_sql(
        question=question,
        schema=SAMPLE_SCHEMA,
        provider="openai",
    )

    print(f"\nQuestion: {question}")
    print(f"\nGenerated SQL:\n{sql}")
    if reasoning:
        print(f"\nReasoning:\n{reasoning[:500]}...")


def example_full_pipeline():
    """Full pipeline with validation and execution."""
    print("\n" + "=" * 60)
    print("Example 2: Full Pipeline")
    print("=" * 60)

    # Create configuration
    config = Config(
        llm=LLMConfig(
            provider="openai",
            model="gpt-4-turbo-preview",
            temperature=0.0,
        ),
        verbose=True,
    )

    # Initialize the orchestrator
    sot = SQLOfThought(config)

    # Process a query
    question = "What are the top 5 products by total sales value?"

    result = sot.query(
        natural_language=question,
        schema_override=SAMPLE_SCHEMA,
    )

    print(f"\nQuestion: {question}")
    print(f"\nStatus: {result.status.value}")
    print(f"Iterations: {result.iterations}")

    if result.success:
        print(f"\nGenerated SQL:\n{result.sql}")
    else:
        print(f"\nError: {result.error_message}")
        if result.sql:
            print(f"\nLast attempted SQL:\n{result.sql}")


def example_with_database():
    """Example with actual database connection."""
    print("\n" + "=" * 60)
    print("Example 3: With Database Connection")
    print("=" * 60)

    # Check if sample database exists
    db_path = Path(__file__).parent / "sample.db"

    if not db_path.exists():
        print("Creating sample database...")
        create_sample_database(db_path)

    # Create configuration
    config = Config(
        llm=LLMConfig(
            provider="openai",
            model="gpt-4-turbo-preview",
        ),
        database=DatabaseConfig(
            dialect="sqlite",
            database=str(db_path),
        ),
        verbose=True,
    )

    # Initialize and connect
    sot = SQLOfThought(config)
    sot.connect_database(f"sqlite:///{db_path}")

    # Show extracted schema
    print("\nExtracted Schema:")
    print(sot.get_schema()[:500] + "...")

    # Process queries
    questions = [
        "How many customers do we have?",
        "What is the total revenue from completed orders?",
        "Which customer has the highest total order value?",
    ]

    for question in questions:
        print(f"\n{'─' * 40}")
        print(f"Question: {question}")

        result = sot.query(question)

        if result.success:
            print(f"SQL: {result.sql}")
            if result.execution_result:
                print(f"Results: {result.execution_result.data[:3]}")
        else:
            print(f"Error: {result.error_message}")


def example_validation_only():
    """Example of validating SQL without execution."""
    print("\n" + "=" * 60)
    print("Example 4: Validation Only")
    print("=" * 60)

    config = Config(
        llm=LLMConfig(provider="openai"),
    )

    sot = SQLOfThought(config)

    # Valid SQL
    valid_sql = """
    SELECT c.name, SUM(o.total_amount) as total_spent
    FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    WHERE o.status = 'completed'
    GROUP BY c.customer_id, c.name
    ORDER BY total_spent DESC
    LIMIT 10;
    """

    # Invalid SQL
    invalid_sql = """
    SELECT name, SUM(total
    FROM customers c
    JOIN orders ON customer_id = order_customer_id
    GROUP BY name
    """

    print("\nValidating correct SQL...")
    result = sot.validate_only(valid_sql, SAMPLE_SCHEMA, "Top customers by spending")
    print(f"Is valid: {result['is_valid']}")
    print(f"Errors: {result['errors']}")
    print(f"Warnings: {result['warnings']}")

    print("\nValidating incorrect SQL...")
    result = sot.validate_only(invalid_sql, SAMPLE_SCHEMA, "")
    print(f"Is valid: {result['is_valid']}")
    print(f"Errors: {result['errors']}")


def create_sample_database(db_path: Path):
    """Create a sample SQLite database for testing."""
    import sqlite3

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Read and execute the sample schema
    schema_path = Path(__file__).parent / "sample_schema.sql"
    if schema_path.exists():
        schema_sql = schema_path.read_text()
        cursor.executescript(schema_sql)
    else:
        # Minimal schema if file not found
        cursor.executescript("""
            CREATE TABLE customers (
                customer_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE
            );

            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                customer_id INTEGER,
                total_amount REAL,
                status TEXT DEFAULT 'pending'
            );

            INSERT INTO customers VALUES (1, 'John Doe', 'john@example.com');
            INSERT INTO customers VALUES (2, 'Jane Smith', 'jane@example.com');
            INSERT INTO orders VALUES (1, 1, 150.00, 'completed');
            INSERT INTO orders VALUES (2, 1, 250.00, 'completed');
            INSERT INTO orders VALUES (3, 2, 75.00, 'pending');
        """)

    conn.commit()
    conn.close()
    print(f"Created sample database at {db_path}")


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("   SQL-of-Thought Usage Examples")
    print("   Multi-agentic Text-to-SQL Framework")
    print("=" * 60)

    # Check for API key
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("ANTHROPIC_API_KEY"):
        print("\nWarning: No API key found!")
        print("Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable.")
        print("Examples will fail without a valid API key.\n")
        return

    try:
        example_quick_conversion()
        example_full_pipeline()
        example_with_database()
        example_validation_only()
    except Exception as e:
        print(f"\nError running examples: {e}")
        raise


if __name__ == "__main__":
    main()
