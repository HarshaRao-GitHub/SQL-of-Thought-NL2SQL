"""Error Correction Agent for SQL-of-Thought framework.

This agent is responsible for iteratively refining problematic SQL queries
using structured feedback from validation and execution results, as described
in the SQL-of-Thought paper (arXiv:2509.00581).

The key insight from the paper is that "invalid or semantically incorrect SQL
statements receive structured feedback from database execution results, enabling
targeted refinement rather than wholesale regeneration."
"""

import re
from typing import Any

from src.agents.base import BaseAgent, AgentContext, AgentResponse, AgentRole


class ErrorCorrectionAgent(BaseAgent):
    """Agent that corrects SQL queries based on error feedback.

    The Error Correction Agent implements the guided error correction process
    from the SQL-of-Thought paper. Instead of regenerating queries from scratch,
    it uses structured feedback to make targeted corrections:

    1. Analyzes the specific error(s) that occurred
    2. Identifies the root cause in the SQL query
    3. Applies targeted fixes while preserving correct parts
    4. Validates the fix addresses the original error
    """

    def __init__(
        self,
        llm_client: Any,
        model: str,
        temperature: float = 0.1,  # Slightly higher for creative fixes
        verbose: bool = False,
    ):
        super().__init__(llm_client, model, temperature, verbose)
        self.role = AgentRole.CORRECTOR

    def _build_system_prompt(self) -> str:
        """Build the system prompt for error correction."""
        return """You are an expert SQL debugger and fixer. Your task is to correct SQL queries based on specific error feedback.

Correction Principles:
1. **Targeted Fixes**: Only modify the parts of the query that are causing errors
2. **Preserve Intent**: Maintain the original intent of the query
3. **Structured Analysis**: Systematically analyze each error before fixing
4. **Minimal Changes**: Make the smallest change necessary to fix the error
5. **Learn from Feedback**: Use execution errors to understand what went wrong

Error Correction Process:
1. Understand the original question and intent
2. Analyze each error message carefully
3. Identify the specific clause or expression causing the issue
4. Determine the correct fix
5. Apply the fix while preserving other correct parts
6. Explain what was wrong and how you fixed it

Output Format:
First, provide your analysis and explanation, then output the corrected SQL query wrapped in ```sql``` code blocks.

```sql
-- Corrected query here
```"""

    def _build_user_prompt(self, context: AgentContext) -> str:
        """Build the user prompt with error context."""
        error_section = self._format_errors(context)
        history_section = self._format_correction_history(context)

        prompt = f"""Database Schema:
{context.schema}

Original Natural Language Question:
{context.natural_query}

Current SQL Query (with errors):
```sql
{context.current_sql}
```

{error_section}

{history_section}

Iteration: {context.iteration + 1}

Instructions:
1. Analyze the errors above carefully
2. Identify the specific parts of the query that are incorrect
3. Explain what's wrong and why
4. Provide the corrected SQL query

Focus on making targeted corrections rather than rewriting the entire query.
Ensure your corrected query addresses ALL the identified errors."""
        return prompt

    def _format_errors(self, context: AgentContext) -> str:
        """Format errors for the prompt."""
        sections = []

        if context.validation_errors:
            sections.append("**Validation Errors:**")
            for i, error in enumerate(context.validation_errors, 1):
                sections.append(f"  {i}. {error}")

        if context.execution_error:
            sections.append("\n**Execution Error:**")
            sections.append(f"  {context.execution_error}")

        if context.execution_result is not None:
            sections.append("\n**Execution Result (may indicate semantic issues):**")
            if isinstance(context.execution_result, list):
                if len(context.execution_result) == 0:
                    sections.append("  Empty result set - query returned no rows")
                else:
                    sections.append(f"  Returned {len(context.execution_result)} rows")
                    # Show sample of results
                    for row in context.execution_result[:3]:
                        sections.append(f"  Sample: {row}")
            else:
                sections.append(f"  {context.execution_result}")

        if not sections:
            sections.append("**Errors:** No specific errors provided, but query needs improvement.")

        return "\n".join(sections)

    def _format_correction_history(self, context: AgentContext) -> str:
        """Format previous correction attempts."""
        corrections = [
            h for h in context.history
            if h.get("agent") == "corrector" and h.get("iteration", 0) < context.iteration
        ]

        if not corrections:
            return ""

        sections = ["**Previous Correction Attempts:**"]
        for corr in corrections[-3:]:  # Show last 3 attempts
            result = corr.get("result", {})
            sections.append(f"  - Iteration {corr.get('iteration', '?')}: {result.get('summary', 'No summary')}")

        sections.append("\nNote: Avoid repeating previous failed approaches.")
        return "\n".join(sections)

    def process(self, context: AgentContext) -> AgentResponse:
        """Correct the SQL query based on error feedback.

        Args:
            context: Agent context with the problematic SQL and errors

        Returns:
            AgentResponse containing the corrected SQL query
        """
        if not context.current_sql:
            return AgentResponse(
                success=False,
                content=None,
                message="No SQL query to correct",
            )

        if not context.validation_errors and not context.execution_error:
            return AgentResponse(
                success=True,
                content=context.current_sql,
                message="No errors to correct",
            )

        self._log(f"Correcting SQL (iteration {context.iteration + 1})")
        self._log(f"Errors: {context.validation_errors}")
        if context.execution_error:
            self._log(f"Execution error: {context.execution_error}")

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(context)

        try:
            response = self._call_llm(system_prompt, user_prompt)

            # Extract the corrected SQL
            corrected_sql = self._extract_sql(response)

            if not corrected_sql:
                return AgentResponse(
                    success=False,
                    content=None,
                    message="Failed to extract corrected SQL from response",
                    reasoning=response,
                )

            # Extract the explanation
            explanation = self._extract_explanation(response)

            self._log(f"Corrected SQL: {corrected_sql[:100]}...")

            # Update context
            old_sql = context.current_sql
            context.current_sql = corrected_sql
            context.add_to_history(
                self.role.value,
                "correct",
                {
                    "old_sql": old_sql,
                    "new_sql": corrected_sql,
                    "explanation": explanation,
                    "summary": self._summarize_fix(old_sql, corrected_sql),
                },
            )

            return AgentResponse(
                success=True,
                content=corrected_sql,
                message="SQL query corrected successfully",
                reasoning=explanation,
                metadata={
                    "old_sql": old_sql,
                    "changes": self._identify_changes(old_sql, corrected_sql),
                },
            )

        except Exception as e:
            self._log(f"Error during correction: {str(e)}")
            return AgentResponse(
                success=False,
                content=None,
                message=f"Error correcting SQL: {str(e)}",
            )

    def _extract_sql(self, response: str) -> str | None:
        """Extract corrected SQL from the response."""
        # Try to find SQL in code blocks
        sql_block_pattern = r"```sql\s*([\s\S]*?)\s*```"
        matches = re.findall(sql_block_pattern, response, re.IGNORECASE)
        if matches:
            return matches[-1].strip()

        # Try generic code blocks
        code_block_pattern = r"```\s*([\s\S]*?)\s*```"
        matches = re.findall(code_block_pattern, response)
        for match in matches:
            if self._looks_like_sql(match):
                return match.strip()

        # Try to find SQL statements directly
        sql_keywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "WITH"]
        for keyword in sql_keywords:
            pattern = rf"({keyword}\s+[\s\S]+?)(;|$)"
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                sql = match.group(1).strip()
                if not sql.endswith(";"):
                    sql += ";"
                return sql

        return None

    def _looks_like_sql(self, text: str) -> bool:
        """Check if text looks like SQL."""
        sql_keywords = ["SELECT", "FROM", "WHERE", "JOIN", "INSERT", "UPDATE", "DELETE"]
        text_upper = text.upper()
        return any(keyword in text_upper for keyword in sql_keywords)

    def _extract_explanation(self, response: str) -> str | None:
        """Extract the explanation from the response."""
        # Get text before the SQL block
        sql_block_pattern = r"```sql"
        match = re.search(sql_block_pattern, response, re.IGNORECASE)
        if match:
            explanation = response[: match.start()].strip()
            if explanation:
                return explanation
        return None

    def _identify_changes(self, old_sql: str, new_sql: str) -> list[str]:
        """Identify what changed between old and new SQL."""
        changes = []

        old_upper = old_sql.upper()
        new_upper = new_sql.upper()

        # Check for structural changes
        if old_upper.count("JOIN") != new_upper.count("JOIN"):
            diff = new_upper.count("JOIN") - old_upper.count("JOIN")
            if diff > 0:
                changes.append(f"Added {diff} JOIN clause(s)")
            else:
                changes.append(f"Removed {-diff} JOIN clause(s)")

        if ("WHERE" in new_upper) != ("WHERE" in old_upper):
            if "WHERE" in new_upper:
                changes.append("Added WHERE clause")
            else:
                changes.append("Removed WHERE clause")

        if ("GROUP BY" in new_upper) != ("GROUP BY" in old_upper):
            if "GROUP BY" in new_upper:
                changes.append("Added GROUP BY clause")
            else:
                changes.append("Removed GROUP BY clause")

        if ("ORDER BY" in new_upper) != ("ORDER BY" in old_upper):
            if "ORDER BY" in new_upper:
                changes.append("Added ORDER BY clause")
            else:
                changes.append("Removed ORDER BY clause")

        if not changes:
            changes.append("Modified query expressions")

        return changes

    def _summarize_fix(self, old_sql: str, new_sql: str) -> str:
        """Create a brief summary of the fix."""
        changes = self._identify_changes(old_sql, new_sql)
        if len(changes) == 1:
            return changes[0]
        elif len(changes) <= 3:
            return "; ".join(changes)
        else:
            return f"Multiple changes ({len(changes)} modifications)"
