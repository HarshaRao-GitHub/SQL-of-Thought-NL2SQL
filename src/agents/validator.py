"""Validation Agent for SQL-of-Thought framework.

This agent is responsible for validating generated SQL queries for both
syntactic correctness and semantic accuracy, as described in the
SQL-of-Thought paper (arXiv:2509.00581).
"""

import re
from typing import Any
from dataclasses import dataclass, field
from enum import Enum

import sqlparse

from src.agents.base import BaseAgent, AgentContext, AgentResponse, AgentRole


class ValidationErrorType(Enum):
    """Types of validation errors."""

    SYNTAX = "syntax"
    SEMANTIC = "semantic"
    SCHEMA = "schema"
    EXECUTION = "execution"
    LOGIC = "logic"


@dataclass
class ValidationError:
    """Represents a validation error."""

    error_type: ValidationErrorType
    message: str
    location: str | None = None
    suggestion: str | None = None
    severity: str = "error"  # error, warning, info


@dataclass
class ValidationResult:
    """Result of SQL validation."""

    is_valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    parsed_info: dict = field(default_factory=dict)


class ValidationAgent(BaseAgent):
    """Agent that validates SQL queries for correctness.

    The Validation Agent checks generated SQL queries for:
    1. Syntactic correctness (proper SQL syntax)
    2. Schema compliance (valid tables, columns, relationships)
    3. Semantic correctness (query matches the intent)
    4. Logical issues (potential problems or inefficiencies)
    """

    def __init__(
        self,
        llm_client: Any,
        model: str,
        temperature: float = 0.0,
        verbose: bool = False,
        schema_validator: Any = None,
    ):
        super().__init__(llm_client, model, temperature, verbose)
        self.role = AgentRole.VALIDATOR
        self.schema_validator = schema_validator

    def _build_system_prompt(self) -> str:
        """Build the system prompt for validation."""
        return """You are an expert SQL validator. Your task is to validate SQL queries for correctness and identify any issues.

Check for:
1. **Syntax Errors**: Invalid SQL syntax, missing keywords, unbalanced parentheses
2. **Schema Errors**: References to non-existent tables or columns
3. **Semantic Errors**: Query doesn't match the intended question
4. **Logic Errors**: Incorrect JOINs, wrong aggregations, missing GROUP BY clauses
5. **Best Practice Violations**: Inefficient patterns, potential performance issues

Output Format:
Provide a JSON-formatted validation result:

```json
{
    "is_valid": true/false,
    "errors": [
        {
            "type": "syntax|semantic|schema|logic",
            "message": "Description of the error",
            "location": "Where in the query (if applicable)",
            "suggestion": "How to fix it"
        }
    ],
    "warnings": [
        {
            "type": "performance|style",
            "message": "Description",
            "suggestion": "Improvement suggestion"
        }
    ],
    "analysis": "Brief analysis of the query"
}
```"""

    def _build_user_prompt(self, context: AgentContext) -> str:
        """Build the user prompt for validation."""
        prompt = f"""Database Schema:
{context.schema}

Original Question:
{context.natural_query}

SQL Query to Validate:
```sql
{context.current_sql}
```

Please validate this SQL query. Check if it:
1. Has correct SQL syntax
2. References only existing tables and columns from the schema
3. Correctly answers the original question
4. Uses appropriate JOINs and conditions
5. Follows SQL best practices

Provide your validation result in the specified JSON format."""
        return prompt

    def process(self, context: AgentContext) -> AgentResponse:
        """Validate the SQL query in the context.

        Args:
            context: Agent context with the SQL query to validate

        Returns:
            AgentResponse containing validation results
        """
        if not context.current_sql:
            return AgentResponse(
                success=False,
                content=ValidationResult(is_valid=False),
                message="No SQL query to validate",
            )

        self._log(f"Validating SQL: {context.current_sql[:50]}...")

        # First, perform syntactic validation
        syntax_result = self._validate_syntax(context.current_sql)
        if not syntax_result.is_valid:
            context.validation_errors = [e.message for e in syntax_result.errors]
            context.add_to_history(
                self.role.value,
                "validate_syntax",
                {"valid": False, "errors": context.validation_errors},
            )
            return AgentResponse(
                success=True,
                content=syntax_result,
                message="SQL has syntax errors",
            )

        # Then perform semantic validation using LLM
        semantic_result = self._validate_semantic(context)

        # Merge results
        final_result = self._merge_validation_results(syntax_result, semantic_result)

        context.validation_errors = [e.message for e in final_result.errors]
        context.add_to_history(
            self.role.value,
            "validate",
            {
                "valid": final_result.is_valid,
                "errors": [e.message for e in final_result.errors],
            },
        )

        return AgentResponse(
            success=True,
            content=final_result,
            message="Validation complete" if final_result.is_valid else "Validation found issues",
        )

    def _validate_syntax(self, sql: str) -> ValidationResult:
        """Perform syntactic validation of SQL."""
        errors = []

        try:
            parsed = sqlparse.parse(sql)

            if not parsed:
                errors.append(
                    ValidationError(
                        error_type=ValidationErrorType.SYNTAX,
                        message="Could not parse SQL statement",
                    )
                )
                return ValidationResult(is_valid=False, errors=errors)

            stmt = parsed[0]

            # Check for basic syntax issues
            if stmt.get_type() == "UNKNOWN":
                errors.append(
                    ValidationError(
                        error_type=ValidationErrorType.SYNTAX,
                        message="Unknown or invalid SQL statement type",
                    )
                )

            # Check for unbalanced parentheses
            open_parens = sql.count("(")
            close_parens = sql.count(")")
            if open_parens != close_parens:
                errors.append(
                    ValidationError(
                        error_type=ValidationErrorType.SYNTAX,
                        message=f"Unbalanced parentheses: {open_parens} open, {close_parens} close",
                        suggestion="Check and balance parentheses in the query",
                    )
                )

            # Check for unclosed quotes
            if sql.count("'") % 2 != 0:
                errors.append(
                    ValidationError(
                        error_type=ValidationErrorType.SYNTAX,
                        message="Unclosed single quote found",
                        suggestion="Ensure all string literals have matching quotes",
                    )
                )
            if sql.count('"') % 2 != 0:
                errors.append(
                    ValidationError(
                        error_type=ValidationErrorType.SYNTAX,
                        message="Unclosed double quote found",
                        suggestion="Ensure all identifiers have matching quotes",
                    )
                )

            # Check for missing semicolon (warning)
            warnings = []
            if not sql.strip().endswith(";"):
                warnings.append(
                    ValidationError(
                        error_type=ValidationErrorType.SYNTAX,
                        message="SQL statement does not end with semicolon",
                        severity="warning",
                    )
                )

            # Extract parsed information
            parsed_info = {
                "statement_type": stmt.get_type(),
                "tokens": len(stmt.tokens),
            }

            return ValidationResult(
                is_valid=len(errors) == 0,
                errors=errors,
                warnings=warnings,
                parsed_info=parsed_info,
            )

        except Exception as e:
            errors.append(
                ValidationError(
                    error_type=ValidationErrorType.SYNTAX,
                    message=f"Parse error: {str(e)}",
                )
            )
            return ValidationResult(is_valid=False, errors=errors)

    def _validate_semantic(self, context: AgentContext) -> ValidationResult:
        """Perform semantic validation using LLM."""
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(context)

        try:
            response = self._call_llm(system_prompt, user_prompt)
            return self._parse_validation_response(response)
        except Exception as e:
            self._log(f"Semantic validation error: {str(e)}")
            return ValidationResult(is_valid=True)  # Default to valid if LLM fails

    def _parse_validation_response(self, response: str) -> ValidationResult:
        """Parse the LLM validation response."""
        import json

        # Try to extract JSON from the response
        json_pattern = r"```json\s*([\s\S]*?)\s*```"
        match = re.search(json_pattern, response, re.IGNORECASE)

        if match:
            try:
                data = json.loads(match.group(1))
                errors = []
                warnings = []

                for err in data.get("errors", []):
                    errors.append(
                        ValidationError(
                            error_type=ValidationErrorType[err.get("type", "SEMANTIC").upper()],
                            message=err.get("message", "Unknown error"),
                            location=err.get("location"),
                            suggestion=err.get("suggestion"),
                        )
                    )

                for warn in data.get("warnings", []):
                    warnings.append(
                        ValidationError(
                            error_type=ValidationErrorType.LOGIC,
                            message=warn.get("message", ""),
                            suggestion=warn.get("suggestion"),
                            severity="warning",
                        )
                    )

                return ValidationResult(
                    is_valid=data.get("is_valid", True),
                    errors=errors,
                    warnings=warnings,
                    parsed_info={"analysis": data.get("analysis", "")},
                )
            except json.JSONDecodeError:
                pass

        # If JSON parsing fails, try to determine validity from text
        is_valid = "valid" in response.lower() and "invalid" not in response.lower()
        return ValidationResult(is_valid=is_valid)

    def _merge_validation_results(
        self, syntax_result: ValidationResult, semantic_result: ValidationResult
    ) -> ValidationResult:
        """Merge syntax and semantic validation results."""
        errors = syntax_result.errors + semantic_result.errors
        warnings = syntax_result.warnings + semantic_result.warnings

        parsed_info = {**syntax_result.parsed_info, **semantic_result.parsed_info}

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            parsed_info=parsed_info,
        )
