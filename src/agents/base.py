"""Base agent class for SQL-of-Thought framework."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum


class AgentRole(Enum):
    """Agent roles in the SQL-of-Thought framework."""

    GENERATOR = "generator"
    VALIDATOR = "validator"
    CORRECTOR = "corrector"
    EXECUTOR = "executor"


@dataclass
class AgentResponse:
    """Response from an agent."""

    success: bool
    content: Any
    message: str = ""
    metadata: dict = field(default_factory=dict)
    reasoning: Optional[str] = None
    confidence: float = 1.0

    def __bool__(self) -> bool:
        return self.success


@dataclass
class AgentContext:
    """Context passed between agents."""

    natural_query: str
    schema: str
    current_sql: Optional[str] = None
    execution_result: Optional[Any] = None
    execution_error: Optional[str] = None
    validation_errors: list[str] = field(default_factory=list)
    iteration: int = 0
    history: list[dict] = field(default_factory=list)

    def add_to_history(self, agent_role: str, action: str, result: Any):
        """Add an entry to the history."""
        self.history.append(
            {
                "iteration": self.iteration,
                "agent": agent_role,
                "action": action,
                "result": result,
            }
        )


class BaseAgent(ABC):
    """Base class for all SQL-of-Thought agents."""

    def __init__(
        self,
        llm_client: Any,
        model: str,
        temperature: float = 0.0,
        verbose: bool = False,
    ):
        """Initialize the agent.

        Args:
            llm_client: The LLM client (OpenAI or Anthropic)
            model: Model name to use
            temperature: Sampling temperature
            verbose: Enable verbose output
        """
        self.llm_client = llm_client
        self.model = model
        self.temperature = temperature
        self.verbose = verbose
        self.role = AgentRole.GENERATOR  # Override in subclasses

    @abstractmethod
    def process(self, context: AgentContext) -> AgentResponse:
        """Process the context and return a response.

        Args:
            context: The current agent context

        Returns:
            AgentResponse with the result
        """
        pass

    def _build_system_prompt(self) -> str:
        """Build the system prompt for this agent."""
        return "You are a helpful SQL assistant."

    def _build_user_prompt(self, context: AgentContext) -> str:
        """Build the user prompt for this agent."""
        return context.natural_query

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Call the LLM and return the response."""
        # Detect client type and call appropriately
        if hasattr(self.llm_client, "chat") and hasattr(self.llm_client.chat, "completions"):
            # OpenAI client
            response = self.llm_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
            )
            return response.choices[0].message.content
        elif hasattr(self.llm_client, "messages"):
            # Anthropic client
            response = self.llm_client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=self.temperature,
            )
            return response.content[0].text
        else:
            raise ValueError("Unknown LLM client type")

    def _log(self, message: str):
        """Log a message if verbose mode is enabled."""
        if self.verbose:
            print(f"[{self.role.value.upper()}] {message}")
