class CoreFlowError(Exception):
    """Base exception for orchestrator failures."""


class AgentValidationError(CoreFlowError):
    """Raised when an agent receives invalid input or produces invalid output."""


class LLMGenerationError(CoreFlowError):
    """Raised when an LLM provider fails to return valid structured output."""


class FileSafetyError(CoreFlowError):
    """Raised when a file operation escapes the managed root."""
