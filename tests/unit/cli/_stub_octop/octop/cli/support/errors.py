class OctopError(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def fail_octop(exc):
    raise SystemExit(str(exc))
