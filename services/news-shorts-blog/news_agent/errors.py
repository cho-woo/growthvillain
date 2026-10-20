"""User-facing errors whose messages never contain file or credential contents."""


class ConfigurationError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


class AgentAlreadyRunning(ValueError):
    pass
