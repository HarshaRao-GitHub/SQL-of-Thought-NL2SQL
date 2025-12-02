"""FastAPI Web Application for SQL-of-Thought.

This module provides a RESTful API and web interface for the
SQL-of-Thought multi-agent Text-to-SQL system.
"""

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from src.core.config import Config, LLMConfig, DatabaseConfig
from src.core.orchestrator import SQLOfThought, PipelineStatus


# Pydantic models for API
class QueryRequest(BaseModel):
    """Request model for SQL generation."""

    question: str
    schema: Optional[str] = None
    database_url: Optional[str] = None
    provider: str = "openai"
    model: Optional[str] = None
    max_iterations: int = 3


class QueryResponse(BaseModel):
    """Response model for SQL generation."""

    success: bool
    sql: Optional[str] = None
    reasoning: Optional[str] = None
    iterations: int = 0
    execution_result: Optional[dict] = None
    error: Optional[str] = None


class ValidationRequest(BaseModel):
    """Request model for SQL validation."""

    sql: str
    schema: str
    question: Optional[str] = None


class ValidationResponse(BaseModel):
    """Response model for SQL validation."""

    is_valid: bool
    errors: list[dict]
    warnings: list[dict]


class ExecuteRequest(BaseModel):
    """Request model for SQL execution."""

    sql: str
    database_url: str


class ExecuteResponse(BaseModel):
    """Response model for SQL execution."""

    success: bool
    data: Optional[list[dict]] = None
    columns: Optional[list[str]] = None
    row_count: int = 0
    error: Optional[str] = None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""

    app = FastAPI(
        title="SQL-of-Thought",
        description="Multi-agentic Text-to-SQL with Guided Error Correction",
        version="1.0.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    # Template directory
    template_dir = Path(__file__).parent.parent.parent / "templates"
    static_dir = Path(__file__).parent.parent.parent / "static"

    if template_dir.exists():
        templates = Jinja2Templates(directory=str(template_dir))
    else:
        templates = None

    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    # In-memory session storage (for demo purposes)
    sessions: dict[str, SQLOfThought] = {}

    def get_sot(provider: str, model: Optional[str] = None) -> SQLOfThought:
        """Get or create SQLOfThought instance."""
        key = f"{provider}:{model}"
        if key not in sessions:
            config = Config(
                llm=LLMConfig(
                    provider=provider,
                    model=model or ("gpt-4-turbo-preview" if provider == "openai" else "claude-3-sonnet-20240229"),
                ),
                verbose=False,
            )
            sessions[key] = SQLOfThought(config)
        return sessions[key]

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        """Render the home page."""
        if templates:
            return templates.TemplateResponse("index.html", {"request": request})
        return HTMLResponse(get_default_html())

    @app.post("/api/query", response_model=QueryResponse)
    async def generate_sql(request: QueryRequest):
        """Generate SQL from natural language query.

        This endpoint implements the full SQL-of-Thought pipeline:
        1. Query Generation
        2. Validation
        3. Execution Verification
        4. Iterative Error Correction
        """
        try:
            sot = get_sot(request.provider, request.model)

            # Connect to database if URL provided
            if request.database_url:
                sot.connect_database(request.database_url)

            result = sot.query(
                request.question,
                schema_override=request.schema,
            )

            execution_data = None
            if result.execution_result:
                execution_data = {
                    "success": result.execution_result.success,
                    "data": result.execution_result.data[:100],  # Limit results
                    "columns": result.execution_result.columns,
                    "row_count": result.execution_result.row_count,
                }

            return QueryResponse(
                success=result.success,
                sql=result.sql,
                reasoning=result.reasoning,
                iterations=result.iterations,
                execution_result=execution_data,
                error=result.error_message,
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/validate", response_model=ValidationResponse)
    async def validate_sql(request: ValidationRequest):
        """Validate an SQL query."""
        try:
            sot = get_sot("openai")  # Use default for validation

            result = sot.validate_only(
                request.sql,
                request.schema,
                request.question or "",
            )

            return ValidationResponse(
                is_valid=result["is_valid"],
                errors=result["errors"],
                warnings=result["warnings"],
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/execute", response_model=ExecuteResponse)
    async def execute_sql(request: ExecuteRequest):
        """Execute an SQL query directly."""
        try:
            from src.database.executor import SQLExecutor

            executor = SQLExecutor(request.database_url, read_only=True)
            result = executor.execute(request.sql)

            return ExecuteResponse(
                success=result.success,
                data=result.data[:100] if result.data else None,
                columns=result.columns,
                row_count=result.row_count,
                error=result.error_message,
            )

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/api/schema")
    async def extract_schema(database_url: str = Form(...)):
        """Extract schema from a database."""
        try:
            from src.core.schema import SchemaExtractor

            extractor = SchemaExtractor(database_url)
            schema = extractor.extract(include_samples=True)

            return {
                "success": True,
                "schema": schema.to_schema_string(),
                "tables": schema.get_table_names(),
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy", "version": "1.0.0"}

    return app


def get_default_html() -> str:
    """Return default HTML if templates are not available."""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SQL-of-Thought</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: #e0e0e0;
            padding: 2rem;
        }
        .container { max-width: 1000px; margin: 0 auto; }
        h1 {
            text-align: center;
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
            background: linear-gradient(90deg, #00d4ff, #7b2cbf);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .subtitle { text-align: center; color: #888; margin-bottom: 2rem; }
        .card {
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
            border: 1px solid rgba(255,255,255,0.1);
        }
        label { display: block; margin-bottom: 0.5rem; color: #aaa; }
        textarea, input, select {
            width: 100%;
            padding: 1rem;
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 8px;
            background: rgba(0,0,0,0.3);
            color: #fff;
            font-size: 1rem;
            margin-bottom: 1rem;
        }
        textarea { min-height: 100px; resize: vertical; }
        button {
            background: linear-gradient(90deg, #00d4ff, #7b2cbf);
            color: white;
            border: none;
            padding: 1rem 2rem;
            border-radius: 8px;
            font-size: 1rem;
            cursor: pointer;
            width: 100%;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        button:hover { transform: translateY(-2px); box-shadow: 0 4px 20px rgba(0,212,255,0.3); }
        button:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
        .result { margin-top: 1.5rem; }
        .sql-output {
            background: #0d1117;
            border-radius: 8px;
            padding: 1rem;
            font-family: 'Monaco', 'Menlo', monospace;
            overflow-x: auto;
            white-space: pre-wrap;
        }
        .success { border-left: 4px solid #00d4ff; }
        .error { border-left: 4px solid #ff4757; }
        .loading { text-align: center; padding: 2rem; }
        .spinner {
            border: 3px solid rgba(255,255,255,0.1);
            border-top: 3px solid #00d4ff;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 1rem;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .row { display: flex; gap: 1rem; }
        .row > * { flex: 1; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
        }
        th, td {
            padding: 0.75rem;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        th { background: rgba(0,0,0,0.3); color: #00d4ff; }
    </style>
</head>
<body>
    <div class="container">
        <h1>SQL-of-Thought</h1>
        <p class="subtitle">Multi-agentic Text-to-SQL with Guided Error Correction</p>

        <div class="card">
            <label>Database Schema (CREATE TABLE statements)</label>
            <textarea id="schema" placeholder="CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    total DECIMAL(10,2),
    created_at TIMESTAMP
);"></textarea>

            <label>Natural Language Question</label>
            <input type="text" id="question" placeholder="Find all users who have placed orders over $100">

            <div class="row">
                <div>
                    <label>LLM Provider</label>
                    <select id="provider">
                        <option value="openai">OpenAI</option>
                        <option value="anthropic">Anthropic</option>
                    </select>
                </div>
                <div>
                    <label>Model (optional)</label>
                    <input type="text" id="model" placeholder="gpt-4-turbo-preview">
                </div>
            </div>

            <button id="submit" onclick="generateSQL()">Generate SQL</button>
        </div>

        <div id="result"></div>
    </div>

    <script>
        async function generateSQL() {
            const btn = document.getElementById('submit');
            const resultDiv = document.getElementById('result');

            const schema = document.getElementById('schema').value.trim();
            const question = document.getElementById('question').value.trim();
            const provider = document.getElementById('provider').value;
            const model = document.getElementById('model').value.trim();

            if (!schema || !question) {
                alert('Please provide both schema and question');
                return;
            }

            btn.disabled = true;
            resultDiv.innerHTML = '<div class="loading"><div class="spinner"></div>Generating SQL...</div>';

            try {
                const response = await fetch('/api/query', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question, schema, provider, model: model || null })
                });

                const data = await response.json();

                if (data.success) {
                    let html = `
                        <div class="card success">
                            <h3>Generated SQL</h3>
                            <div class="sql-output">${escapeHtml(data.sql)}</div>
                            <p style="margin-top:1rem;color:#888">Iterations: ${data.iterations}</p>
                        </div>
                    `;

                    if (data.reasoning) {
                        html += `
                            <div class="card">
                                <h3>Reasoning</h3>
                                <p style="white-space:pre-wrap">${escapeHtml(data.reasoning)}</p>
                            </div>
                        `;
                    }

                    resultDiv.innerHTML = html;
                } else {
                    resultDiv.innerHTML = `
                        <div class="card error">
                            <h3>Error</h3>
                            <p>${escapeHtml(data.error || 'Unknown error')}</p>
                            ${data.sql ? `<div class="sql-output" style="margin-top:1rem">${escapeHtml(data.sql)}</div>` : ''}
                        </div>
                    `;
                }
            } catch (err) {
                resultDiv.innerHTML = `<div class="card error"><h3>Error</h3><p>${escapeHtml(err.message)}</p></div>`;
            }

            btn.disabled = false;
        }

        function escapeHtml(text) {
            if (!text) return '';
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    </script>
</body>
</html>
    """


# Create the app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
