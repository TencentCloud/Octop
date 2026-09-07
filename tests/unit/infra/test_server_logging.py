"""`_attach_harness_stderr_handler` 行为：WARNING+ 镜像到 stderr 且幂等。"""

import logging

from octop.infra.server import _attach_harness_stderr_handler


def _marked_handlers(logger: logging.Logger) -> list[logging.Handler]:
    return [
        h for h in logger.handlers if getattr(h, "_octop_harness_stderr", False)
    ]


def test_attach_harness_stderr_handler_adds_warning_handler_once():
    logger = logging.getLogger("harness_agent")
    saved = list(logger.handlers)
    try:
        _attach_harness_stderr_handler()
        marked = _marked_handlers(logger)
        assert len(marked) == 1
        assert marked[0].level == logging.WARNING

        # 重复调用不叠加 handler
        _attach_harness_stderr_handler()
        assert len(_marked_handlers(logger)) == 1
    finally:
        for handler in list(logger.handlers):
            if handler not in saved:
                logger.removeHandler(handler)


def test_attach_harness_stderr_handler_emits_warning_to_stderr(capsys):
    logger = logging.getLogger("harness_agent")
    saved = list(logger.handlers)
    try:
        _attach_harness_stderr_handler()
        logger.warning("测试警告 %s", "payload")
        err = capsys.readouterr().err
        assert "测试警告 payload" in err
        assert "harness_agent" in err
    finally:
        for handler in list(logger.handlers):
            if handler not in saved:
                logger.removeHandler(handler)
