class ErrorCode:
    AGENT_NOT_FOUND = 'agent_not_found'


class OctopError(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code
