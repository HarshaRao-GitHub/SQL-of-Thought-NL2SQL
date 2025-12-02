"""Multi-Agent Orchestrator for SQL-of-Thought framework.

This module implements the core multi-agent coordination described in the
SQL-of-Thought paper (arXiv:2509.00581). The orchestrator manages the
collaboration between specialized agents for SQL generation, validation,
and error correction.

The key innovation is the iterative refinement loop where execution errors
guide targeted corrections rather than wholesale regeneration.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum

from src.core.config import Config
from src.core.schema import SchemaExtractor, DatabaseSchema
from src.agents.base import AgentContext, AgentResponse
from src.agents.generator import QueryGeneratorAgent
from src.agents.validator import ValidationAgent
from src.agents.corrector import ErrorCorrectionAgent
from src.database.executor import SQLExecutor, ExecutionResult, ExecutionStatus


class PipelineStatus(Enum):
    """Status of the SQL generation pipeline."""

    SUCCESS = "success"
    GENERATION_FAILED = "generation_failed"
    VALIDATION_FAILED = "validation_failed"
    EXECUTION_FAILED = "execution_failed"
    MAX_ITERATIONS_REACHED = "max_iterations_reached"
    ERROR = "error"


@dataclass
class PipelineResult:
    """Result of the SQL-of-Thought pipeline."""

    status: PipelineStatus
    sql: Optional[str] = None
    execution_result: Optional[ExecutionResult] = None
    iterations: int = 0
    history: list[dict] = field(default_factory=list)
    reasoning: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def success(self) -> bool:
        """Check if the pipeline succeeded."""
        return self.status == PipelineStatus.SUCCESS


class SQLOfThought:
    """Main orchestrator for the SQL-of-Thought multi-agent system.

    The SQLOfThought class implements the complete pipeline described in
    the paper:

    1. Query Generation: Natural language -> Initial SQL
    2. Validation: Syntax and semantic checking
    3. Execution Verification: Test against actual database
    4. Error Correction: Iterative refinement with feedback

    The agents collaborate through a shared context, with each agent
    specializing in a distinct aspect of SQL generation and validation.
    """

    def __init__(self, config: Config):
        """Initialize the SQL-of-Thought system.

        Args:
            config: Configuration for the system
        """
        self.config = config
        self.verbose = config.verbose

        # Initialize LLM client
        self.llm_client = self._create_llm_client()

        # Initialize agents
        self.generator = self._create_generator()
        self.validator = self._create_validator()
        self.corrector = self._create_corrector()

        # Initialize database components
        self.schema_extractor: Optional[SchemaExtractor] = None
        self.executor: Optional[SQLExecutor] = None
        self.schema: Optional[DatabaseSchema] = None

        if config.database.database != ":memory:":
            self._init_database()

    def _create_llm_client(self) -> Any:
        """Create the LLM client based on configuration."""
        if self.config.llm.provider == "openai":
            from openai import OpenAI

            return OpenAI(api_key=self.config.llm.api_key)
        elif self.config.llm.provider == "anthropic":
            from anthropic import Anthropic

            return Anthropic(api_key=self.config.llm.api_key)
        else:
            raise ValueError(f"Unknown LLM provider: {self.config.llm.provider}")

    def _create_generator(self) -> QueryGeneratorAgent:
        """Create the query generation agent."""
        model = self.config.agents.generator_model or self.config.llm.model
        temp = self.config.agents.generator_temperature
        return QueryGeneratorAgent(
            llm_client=self.llm_client,
            model=model,
            temperature=temp,
            verbose=self.verbose,
        )

    def _create_validator(self) -> ValidationAgent:
        """Create the validation agent."""
        model = self.config.agents.validator_model or self.config.llm.model
        temp = self.config.agents.validator_temperature
        return ValidationAgent(
            llm_client=self.llm_client,
            model=model,
            temperature=temp,
            verbose=self.verbose,
        )

    def _create_corrector(self) -> ErrorCorrectionAgent:
        """Create the error correction agent."""
        model = self.config.agents.corrector_model or self.config.llm.model
        temp = self.config.agents.corrector_temperature
        return ErrorCorrectionAgent(
            llm_client=self.llm_client,
            model=model,
            temperature=temp,
            verbose=self.verbose,
        )

    def _init_database(self):
        """Initialize database connection and extract schema."""
        conn_str = self.config.database.get_connection_string()
        self.schema_extractor = SchemaExtractor(conn_str)
        self.executor = SQLExecutor(conn_str, read_only=True)
        self.schema = self.schema_extractor.extract(include_samples=True)

    def connect_database(self, connection_string: str):
        """Connect to a database.

        Args:
            connection_string: SQLAlchemy connection string
        """
        self.schema_extractor = SchemaExtractor(connection_string)
        self.executor = SQLExecutor(connection_string, read_only=True)
        self.schema = self.schema_extractor.extract(include_samples=True)
        self._log(f"Connected to database. Found {len(self.schema.tables)} tables.")

    def load_schema(self, schema_string: str):
        """Load a schema from a string (for databases without direct connection).

        Args:
            schema_string: SQL schema definition string
        """
        # Create a minimal schema object from string
        from src.core.schema import DatabaseSchema, TableInfo

        self.schema = DatabaseSchema()
        # The schema string will be passed directly to agents

    def query(
        self,
        natural_language: str,
        schema_override: str | None = None,
    ) -> PipelineResult:
        """Convert natural language to SQL using the multi-agent pipeline.

        This is the main entry point for the SQL-of-Thought system. It
        coordinates the generation, validation, and correction agents
        to produce a correct SQL query.

        Args:
            natural_language: The natural language question
            schema_override: Optional schema string to use instead of extracted schema

        Returns:
            PipelineResult with the final SQL and execution results
        """
        self._log(f"Processing query: {natural_language[:80]}...")

        # Prepare schema
        if schema_override:
            schema_str = schema_override
        elif self.schema:
            schema_str = self.schema.to_schema_string()
        else:
            return PipelineResult(
                status=PipelineStatus.ERROR,
                error_message="No database schema available. Connect to a database or provide a schema.",
            )

        # Initialize context
        context = AgentContext(
            natural_query=natural_language,
            schema=schema_str,
        )

        # Step 1: Generate initial SQL
        gen_response = self.generator.process(context)
        if not gen_response.success:
            return PipelineResult(
                status=PipelineStatus.GENERATION_FAILED,
                error_message=gen_response.message,
                history=context.history,
            )

        context.current_sql = gen_response.content
        initial_reasoning = gen_response.reasoning

        # Iterative refinement loop
        max_iterations = self.config.agents.max_correction_iterations

        for iteration in range(max_iterations):
            context.iteration = iteration
            self._log(f"Iteration {iteration + 1}/{max_iterations}")

            # Step 2: Validate the SQL
            val_response = self.validator.process(context)
            validation_result = val_response.content

            # Step 3: Execute if validation passed
            execution_result = None
            if validation_result.is_valid and self.executor:
                execution_result = self.executor.execute(context.current_sql)
                context.execution_result = execution_result.data if execution_result.success else None
                context.execution_error = execution_result.error_message

                if execution_result.success:
                    self._log("Query executed successfully!")
                    return PipelineResult(
                        status=PipelineStatus.SUCCESS,
                        sql=context.current_sql,
                        execution_result=execution_result,
                        iterations=iteration + 1,
                        history=context.history,
                        reasoning=initial_reasoning,
                    )
            elif validation_result.is_valid and not self.executor:
                # No executor, but validation passed - return success
                self._log("Validation passed (no execution verification)")
                return PipelineResult(
                    status=PipelineStatus.SUCCESS,
                    sql=context.current_sql,
                    iterations=iteration + 1,
                    history=context.history,
                    reasoning=initial_reasoning,
                )

            # Step 4: Correct errors if any
            if context.validation_errors or context.execution_error:
                corr_response = self.corrector.process(context)
                if not corr_response.success:
                    self._log(f"Correction failed: {corr_response.message}")
                    # Continue to next iteration anyway
                else:
                    context.current_sql = corr_response.content
                    # Clear errors for next iteration
                    context.validation_errors = []
                    context.execution_error = None
            else:
                # No errors but execution failed for other reasons
                break

        # Max iterations reached
        self._log("Max iterations reached")
        return PipelineResult(
            status=PipelineStatus.MAX_ITERATIONS_REACHED,
            sql=context.current_sql,
            iterations=max_iterations,
            history=context.history,
            reasoning=initial_reasoning,
            error_message="Could not produce a valid query within the iteration limit",
        )

    def generate_only(self, natural_language: str, schema: str) -> tuple[str | None, str | None]:
        """Generate SQL without validation or execution.

        Args:
            natural_language: The natural language question
            schema: Database schema string

        Returns:
            Tuple of (sql, reasoning)
        """
        context = AgentContext(natural_query=natural_language, schema=schema)
        response = self.generator.process(context)
        return response.content, response.reasoning

    def validate_only(self, sql: str, schema: str, question: str = "") -> dict:
        """Validate an SQL query.

        Args:
            sql: SQL query to validate
            schema: Database schema string
            question: Original question (optional)

        Returns:
            Validation result dictionary
        """
        context = AgentContext(
            natural_query=question,
            schema=schema,
            current_sql=sql,
        )
        response = self.validator.process(context)
        result = response.content

        return {
            "is_valid": result.is_valid,
            "errors": [{"type": e.error_type.value, "message": e.message} for e in result.errors],
            "warnings": [{"message": w.message} for w in result.warnings],
        }

    def execute_only(self, sql: str) -> ExecutionResult:
        """Execute an SQL query directly.

        Args:
            sql: SQL query to execute

        Returns:
            ExecutionResult
        """
        if not self.executor:
            raise RuntimeError("No database connected")
        return self.executor.execute(sql)

    def get_schema(self) -> str | None:
        """Get the current database schema as string."""
        if self.schema:
            return self.schema.to_schema_string()
        return None

    def _log(self, message: str):
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            print(f"[ORCHESTRATOR] {message}")


# Convenience function for quick usage
def text_to_sql(
    question: str,
    schema: str,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
) -> tuple[str | None, str | None]:
    """Quick conversion of natural language to SQL.

    Args:
        question: Natural language question
        schema: Database schema string
        provider: LLM provider ("openai" or "anthropic")
        model: Model name (optional)
        api_key: API key (optional, uses environment variable if not provided)

    Returns:
        Tuple of (sql_query, reasoning)
    """
    from src.core.config import Config, LLMConfig

    default_models = {
        "openai": "gpt-4-turbo-preview",
        "anthropic": "claude-3-sonnet-20240229",
    }

    config = Config(
        llm=LLMConfig(
            provider=provider,
            model=model or default_models.get(provider, "gpt-4-turbo-preview"),
            api_key=api_key,
        )
    )

    sot = SQLOfThought(config)
    return sot.generate_only(question, schema)
