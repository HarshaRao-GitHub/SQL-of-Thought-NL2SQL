# SQL-of-Thought

**Multi-agentic Text-to-SQL with Guided Error Correction**

Based on the research paper [arXiv:2509.00581](https://arxiv.org/abs/2509.00581) by Chaturvedi, Chadha, and Bindschaedler.

## Overview

SQL-of-Thought is a multi-agent framework for converting natural language queries into accurate SQL statements. Unlike single-pass generation approaches, this system employs specialized agents that collaborate through an iterative refinement process with automatic error detection and correction.

### Key Features

- **Multi-Agent Architecture**: Specialized agents for generation, validation, and correction
- **Guided Error Correction**: Targeted refinement using structured feedback from execution results
- **Execution Verification**: Tests queries against actual databases to validate correctness
- **Iterative Refinement**: Multiple correction passes to ensure accuracy
- **Multiple LLM Support**: Works with OpenAI and Anthropic models
- **CLI & Web Interface**: Easy-to-use command line and browser interfaces

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     SQL-of-Thought Pipeline                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐   │
│  │   Natural    │    │    Query     │    │    Generated     │   │
│  │   Language   │───▶│  Generator   │───▶│       SQL        │   │
│  │   Question   │    │    Agent     │    │                  │   │
│  └──────────────┘    └──────────────┘    └────────┬─────────┘   │
│                                                    │             │
│                                          ┌────────▼─────────┐   │
│                                          │   Validation     │   │
│                                          │     Agent        │   │
│                                          └────────┬─────────┘   │
│                                                    │             │
│  ┌──────────────┐    ┌──────────────┐    ┌────────▼─────────┐   │
│  │   Corrected  │    │    Error     │◀───│   Execution      │   │
│  │     SQL      │◀───│  Correction  │    │   Verification   │   │
│  │              │    │    Agent     │    │                  │   │
│  └──────────────┘    └──────────────┘    └──────────────────┘   │
│                             ▲                      │             │
│                             └──────────────────────┘             │
│                           Iterative Feedback Loop                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Installation

```bash
# Clone the repository
git clone https://github.com/sql-of-thought/sql-of-thought.git
cd sql-of-thought

# Install with pip
pip install -e .

# Or install with development dependencies
pip install -e ".[dev]"
```

## Configuration

Set your LLM API key as an environment variable:

```bash
# For OpenAI
export OPENAI_API_KEY="your-api-key"

# For Anthropic
export ANTHROPIC_API_KEY="your-api-key"
```

## Quick Start

### Python API

```python
from src import SQLOfThought
from src.core.config import Config, LLMConfig

# Create configuration
config = Config(
    llm=LLMConfig(
        provider="openai",
        model="gpt-4-turbo-preview"
    )
)

# Initialize the system
sot = SQLOfThought(config)

# Connect to a database
sot.connect_database("sqlite:///mydb.sqlite")

# Convert natural language to SQL
result = sot.query("Find all customers who spent more than $500")

if result.success:
    print(f"Generated SQL: {result.sql}")
    print(f"Iterations: {result.iterations}")
```

### Quick Conversion

```python
from src.core.orchestrator import text_to_sql

schema = """
CREATE TABLE customers (id INT, name TEXT, email TEXT);
CREATE TABLE orders (id INT, customer_id INT, total DECIMAL);
"""

sql, reasoning = text_to_sql(
    question="Which customers have no orders?",
    schema=schema,
    provider="openai"
)
print(sql)
```

### Command Line

```bash
# Generate SQL from a question
sot query "Find the top 10 products by sales" -d mydb.sqlite

# Interactive mode
sot interactive -d mydb.sqlite

# Validate SQL
sot validate "SELECT * FROM users WHERE age > 18" -d mydb.sqlite

# View database schema
sot schema -d mydb.sqlite
```

### Web Interface

```bash
# Start the web server
python -m src.api.app

# Or use uvicorn directly
uvicorn src.api.app:app --reload --port 8000
```

Then open http://localhost:8000 in your browser.

## Agents

### Query Generator Agent
Converts natural language questions into initial SQL queries using chain-of-thought reasoning.

### Validation Agent
Checks generated SQL for:
- Syntactic correctness
- Schema compliance (valid tables/columns)
- Semantic correctness (matches the intent)
- Logical issues

### Error Correction Agent
Applies targeted fixes based on structured error feedback:
- Analyzes specific errors
- Identifies root causes
- Makes minimal corrections
- Preserves correct parts of the query

## API Reference

### REST API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/query` | POST | Generate SQL from natural language |
| `/api/validate` | POST | Validate an SQL query |
| `/api/execute` | POST | Execute an SQL query |
| `/api/schema` | POST | Extract database schema |
| `/api/health` | GET | Health check |

### Example API Request

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Find all active customers",
    "schema": "CREATE TABLE customers (id INT, name TEXT, active BOOL);",
    "provider": "openai"
  }'
```

## Configuration Options

| Option | Environment Variable | Default | Description |
|--------|---------------------|---------|-------------|
| `llm.provider` | `SOT_LLM_PROVIDER` | `openai` | LLM provider |
| `llm.model` | `SOT_LLM_MODEL` | `gpt-4-turbo-preview` | Model name |
| `llm.temperature` | `SOT_LLM_TEMPERATURE` | `0.0` | Sampling temperature |
| `agents.max_correction_iterations` | `SOT_MAX_ITERATIONS` | `3` | Max correction attempts |
| `verbose` | `SOT_VERBOSE` | `false` | Enable verbose logging |

## Examples

See the `examples/` directory for more detailed examples:

- `basic_usage.py` - Python API examples
- `sample_schema.sql` - Sample e-commerce database

## Testing

```bash
# Run tests
pytest tests/

# With coverage
pytest tests/ --cov=src --cov-report=html
```

## Research Background

This implementation is based on the SQL-of-Thought paper which introduces:

1. **Multi-Agent Collaboration**: Specialized agents for distinct SQL generation tasks
2. **Guided Error Correction**: Using structured execution feedback for targeted fixes
3. **Iterative Refinement**: Multiple correction passes rather than single-shot generation

The key insight is that "invalid or semantically incorrect SQL statements receive structured feedback from database execution results, enabling targeted refinement rather than wholesale regeneration."

## License

MIT License - see [LICENSE](LICENSE) for details.

## Citation

If you use this implementation in your research, please cite the original paper:

```bibtex
@article{chaturvedi2024sqlofthought,
  title={SQL-of-Thought: Multi-agentic Text-to-SQL with Guided Error Correction},
  author={Chaturvedi, Anubhav and Chadha, Arnav and Bindschaedler, Laurent},
  journal={arXiv preprint arXiv:2509.00581},
  year={2024}
}
```

## Contributing

Contributions are welcome! Please read our contributing guidelines before submitting a pull request.
