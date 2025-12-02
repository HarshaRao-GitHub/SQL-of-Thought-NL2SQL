"""
SQL-of-Thought: Multi-agentic Text-to-SQL with Guided Error Correction

Based on the research paper arXiv:2509.00581 by Chaturvedi, Chadha, and Bindschaedler.

This framework implements a multi-agent system for converting natural language
queries into SQL statements with automated error detection and correction.
"""

__version__ = "1.0.0"
__author__ = "SQL-of-Thought Team"

from src.core.orchestrator import SQLOfThought
from src.core.config import Config

__all__ = ["SQLOfThought", "Config"]
