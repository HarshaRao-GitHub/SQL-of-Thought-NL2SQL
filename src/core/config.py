"""Configuration management for SQL-of-Thought framework."""

import os
from dataclasses import dataclass, field
from typing import Optional, Literal
from pathlib import Path


@dataclass
class LLMConfig:
    """Configuration for LLM providers."""

    provider: Literal["openai", "anthropic"] = "openai"
    model: str = "gpt-4-turbo-preview"
    temperature: float = 0.0
    max_tokens: int = 4096
    api_key: Optional[str] = None

    def __post_init__(self):
        if self.api_key is None:
            if self.provider == "openai":
                self.api_key = os.getenv("OPENAI_API_KEY")
            elif self.provider == "anthropic":
                self.api_key = os.getenv("ANTHROPIC_API_KEY")


@dataclass
class AgentConfig:
    """Configuration for individual agents."""

    # Query Generation Agent
    generator_model: Optional[str] = None
    generator_temperature: float = 0.0

    # Validation Agent
    validator_model: Optional[str] = None
    validator_temperature: float = 0.0

    # Error Correction Agent
    corrector_model: Optional[str] = None
    corrector_temperature: float = 0.1

    # Iteration settings
    max_correction_iterations: int = 3
    enable_execution_validation: bool = True


@dataclass
class DatabaseConfig:
    """Configuration for database connections."""

    dialect: Literal["sqlite", "postgresql", "mysql"] = "sqlite"
    database: str = ":memory:"
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None

    def get_connection_string(self) -> str:
        """Generate SQLAlchemy connection string."""
        if self.dialect == "sqlite":
            return f"sqlite:///{self.database}"

        auth = ""
        if self.username:
            auth = self.username
            if self.password:
                auth += f":{self.password}"
            auth += "@"

        host_port = self.host or "localhost"
        if self.port:
            host_port += f":{self.port}"

        return f"{self.dialect}://{auth}{host_port}/{self.database}"


@dataclass
class Config:
    """Main configuration for SQL-of-Thought framework."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    agents: AgentConfig = field(default_factory=AgentConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)

    # Logging and debugging
    verbose: bool = False
    log_level: str = "INFO"
    save_history: bool = True
    history_path: Path = field(default_factory=lambda: Path("./sot_history"))

    @classmethod
    def from_env(cls) -> "Config":
        """Create configuration from environment variables."""
        llm_config = LLMConfig(
            provider=os.getenv("SOT_LLM_PROVIDER", "openai"),
            model=os.getenv("SOT_LLM_MODEL", "gpt-4-turbo-preview"),
            temperature=float(os.getenv("SOT_LLM_TEMPERATURE", "0.0")),
        )

        agent_config = AgentConfig(
            max_correction_iterations=int(os.getenv("SOT_MAX_ITERATIONS", "3")),
        )

        db_config = DatabaseConfig(
            dialect=os.getenv("SOT_DB_DIALECT", "sqlite"),
            database=os.getenv("SOT_DB_DATABASE", ":memory:"),
            host=os.getenv("SOT_DB_HOST"),
            port=int(os.getenv("SOT_DB_PORT")) if os.getenv("SOT_DB_PORT") else None,
            username=os.getenv("SOT_DB_USERNAME"),
            password=os.getenv("SOT_DB_PASSWORD"),
        )

        return cls(
            llm=llm_config,
            agents=agent_config,
            database=db_config,
            verbose=os.getenv("SOT_VERBOSE", "false").lower() == "true",
        )

    @classmethod
    def default(cls) -> "Config":
        """Create default configuration."""
        return cls()
