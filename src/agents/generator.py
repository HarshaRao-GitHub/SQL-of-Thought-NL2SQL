"""Query Generation Agent for SQL-of-Thought framework.

This agent is responsible for generating the initial SQL query from
natural language input, following the methodology described in the
SQL-of-Thought paper (arXiv:2509.00581).
"""

import re
from typing import Any

from src.agents.base import BaseAgent, AgentContext, AgentResponse, AgentRole


class QueryGeneratorAgent(BaseAgent):
    """Agent that generates SQL queries from natural language.

    The Query Generation Agent is the first step in the SQL-of-Thought pipeline.
    It takes a natural language question and the database schema, then produces
    an initial SQL query using chain-of-thought reasoning.
    """

    def __init__(
        self,
        llm_client: Any,
        model: str,
        temperature: float = 0.0,
        verbose: bool = False,
    ):
        super().__init__(llm_client, model, temperature, verbose)
        self.role = AgentRole.GENERATOR

    def _build_system_prompt(self) -> str:
        """Build the system prompt for SQL generation."""
        return """You are an expert SQL query generator. Your task is to convert natural language questions into accurate SQL queries.

Follow these principles:
1. Carefully analyze the database schema provided
2. Understand the user's intent from their natural language question
3. Use proper SQL syntax and best practices
4. Consider edge cases and potential ambiguities
5. Use appropriate JOINs when data spans multiple tables
6. Apply proper filtering, grouping, and ordering as needed

Think step by step:
1. Identify the relevant tables and columns
2. Determine the required operations (SELECT, JOIN, WHERE, GROUP BY, etc.)
3. Consider any aggregations or calculations needed
4. Build the query incrementally

Output Format:
Provide your reasoning first, then output the final SQL query wrapped in ```sql``` code blocks.

Example:
Reasoning: The user wants to find all customers who made purchases over $100. I need to join the customers table with the orders table and filter by amount.

```sql
SELECT c.customer_name, o.order_total
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
WHERE o.order_total > 100;
```"""

    def _build_user_prompt(self, context: AgentContext) -> str:
        """Build the user prompt with schema and question."""
        prompt = f"""Database Schema:
{context.schema}

Natural Language Question:
{context.natural_query}

Generate the SQL query to answer this question. Think step by step and explain your reasoning before providing the final query."""
        return prompt

    def process(self, context: AgentContext) -> AgentResponse:
        """Generate an SQL query from the natural language input.

        Args:
            context: Agent context with schema and natural query

        Returns:
            AgentResponse containing the generated SQL query
        """
        self._log(f"Generating SQL for: {context.natural_query[:50]}...")

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(context)

        try:
            response = self._call_llm(system_prompt, user_prompt)

            # Extract SQL from response
            sql_query = self._extract_sql(response)

            if not sql_query:
                return AgentResponse(
                    success=False,
                    content=None,
                    message="Failed to extract SQL from LLM response",
                    reasoning=response,
                )

            # Extract reasoning if present
            reasoning = self._extract_reasoning(response)

            self._log(f"Generated SQL: {sql_query[:100]}...")

            context.current_sql = sql_query
            context.add_to_history(
                self.role.value,
                "generate",
                {"sql": sql_query, "reasoning": reasoning},
            )

            return AgentResponse(
                success=True,
                content=sql_query,
                message="SQL query generated successfully",
                reasoning=reasoning,
                metadata={"raw_response": response},
            )

        except Exception as e:
            self._log(f"Error generating SQL: {str(e)}")
            return AgentResponse(
                success=False,
                content=None,
                message=f"Error generating SQL: {str(e)}",
            )

    def _extract_sql(self, response: str) -> str | None:
        """Extract SQL query from LLM response.

        Looks for SQL in code blocks or attempts to identify SQL statements.
        """
        # Try to find SQL in code blocks
        sql_block_pattern = r"```sql\s*([\s\S]*?)\s*```"
        matches = re.findall(sql_block_pattern, response, re.IGNORECASE)
        if matches:
            return matches[-1].strip()  # Return the last SQL block

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
        sql_keywords = [
            "SELECT",
            "FROM",
            "WHERE",
            "JOIN",
            "INSERT",
            "UPDATE",
            "DELETE",
            "CREATE",
            "DROP",
            "ALTER",
        ]
        text_upper = text.upper()
        return any(keyword in text_upper for keyword in sql_keywords)

    def _extract_reasoning(self, response: str) -> str | None:
        """Extract reasoning from the response."""
        # Try to find reasoning before the SQL block
        sql_block_pattern = r"```sql"
        match = re.search(sql_block_pattern, response, re.IGNORECASE)
        if match:
            reasoning = response[: match.start()].strip()
            if reasoning:
                return reasoning

        # Look for explicit reasoning markers
        reasoning_patterns = [
            r"Reasoning:\s*([\s\S]*?)(?=```|SQL:|Query:)",
            r"Thought process:\s*([\s\S]*?)(?=```|SQL:|Query:)",
            r"Analysis:\s*([\s\S]*?)(?=```|SQL:|Query:)",
        ]
        for pattern in reasoning_patterns:
            match = re.search(pattern, response, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None
