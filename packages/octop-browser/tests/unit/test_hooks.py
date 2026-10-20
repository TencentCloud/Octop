import pytest

from octop_browser.hooks import HooksMixin
from octop_browser.models import ActionMetrics


class FakeSession(HooksMixin):
    pass


@pytest.fixture()
def sess():
    return FakeSession()


def make_metrics(action: str = "click") -> ActionMetrics:
    return ActionMetrics(
        action=action, duration_ms=50, dom_nodes_scanned=10, estimated_tokens=30
    )


async def test_before_action_fires(sess):
    events = []

    @sess.on("before_action")
    async def _handler(event):
        events.append(event)

    await sess._fire("before_action", {"action": "click", "params": {}})
    assert len(events) == 1


async def test_after_action_fires(sess):
    events = []

    @sess.on("after_action")
    async def _handler(event):
        events.append(event.action)

    m = make_metrics()
    await sess._fire("after_action", m)
    assert events == ["click"]


async def test_multiple_handlers_all_fire(sess):
    count = []

    @sess.on("before_action")
    async def _h1(e):
        count.append(1)

    @sess.on("before_action")
    async def _h2(e):
        count.append(2)

    await sess._fire("before_action", {})
    assert count == [1, 2]


async def test_unregistered_event_is_noop(sess):
    # firing an event with no handlers should not raise
    await sess._fire("page_navigated", {})


async def test_decorator_returns_callback(sess):
    @sess.on("before_action")
    async def handler(e): ...  # pylint: disable=multiple-statements

    assert callable(handler)
