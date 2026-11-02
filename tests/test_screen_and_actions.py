import pytest
from screeninfo.common import ScreenInfoError

from handcursor import actions
from handcursor.actions import Action, DryRunActions, SystemActions, parse_action, perform
from handcursor.config import DEFAULT_APPS, Config, ConfigError
from handcursor.gestures import Pose
from handcursor.launcher import window_position, window_size
from handcursor.screen import Rect, ScreenSelection, Workspace

LAPTOP = Rect(0, 0, 1920, 1080)
ABOVE = Rect(954, -1085, 1920, 1080)
PORTRAIT = Rect(-1080, -1000, 1080, 1920)


def test_workspace_bounds_span_every_monitor():
    assert Workspace([LAPTOP, ABOVE]).bounds == Rect(0, -1085, 2874, 2165)


def test_snap_leaves_points_on_a_monitor_alone():
    assert Workspace([LAPTOP, ABOVE]).snap(100, 100) == (100, 100)


def test_snap_moves_gap_points_to_the_nearest_monitor():
    workspace = Workspace([LAPTOP, ABOVE])
    assert workspace.snap(2500, 900) == (1919, 900)
    assert workspace.snap(2800, 100) == (2800, -6)
    assert workspace.snap(800, -500) == (954, -500)


def test_monitor_at():
    workspace = Workspace([LAPTOP, ABOVE, PORTRAIT])
    assert workspace.monitor_at(1000, 500) is LAPTOP
    assert workspace.monitor_at(-5, 800) is PORTRAIT
    assert workspace.monitor_at(3000, 500) is ABOVE  # In a gap, so the nearest.


def test_selection_cycles_all_then_each_monitor():
    screens = ScreenSelection("all", lambda: [LAPTOP, ABOVE])
    assert screens.workspace.monitors == (LAPTOP, ABOVE)
    screens.next()
    assert screens.selection == 0 and screens.workspace.monitors == (LAPTOP,)
    screens.next()
    assert screens.selection == 1 and screens.label == "screen 1"
    screens.next()
    assert screens.selection == "all" and screens.label == "all screens"


def test_selection_rejects_a_missing_monitor():
    with pytest.raises(ConfigError):
        ScreenSelection(5, lambda: [LAPTOP])


def test_refresh_picks_up_a_monitor_being_rotated():
    current = [LAPTOP, Rect(1920, 0, 1920, 1080)]
    screens = ScreenSelection(1, lambda: current)
    assert screens.refresh() is False
    current = [LAPTOP, Rect(1920, 0, 1080, 1920)]
    assert screens.refresh() is True
    assert screens.workspace.bounds == Rect(1920, 0, 1080, 1920)


def test_refresh_falls_back_to_all_when_the_chosen_monitor_is_unplugged():
    current = [LAPTOP, ABOVE]
    screens = ScreenSelection(1, lambda: current)
    current = [LAPTOP]
    assert screens.refresh() is True
    assert screens.selection == "all"


def test_refresh_ignores_a_moment_with_no_monitors():
    results = [[LAPTOP], [], ScreenInfoError("reconfiguring")]

    def lister():
        result = results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    screens = ScreenSelection("all", lister)
    assert screens.refresh() is False
    assert screens.refresh() is False
    assert screens.monitors == [LAPTOP]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("open:notepad", Action("open", "notepad")),
        ("open:ms-settings:", Action("open", "ms-settings:")),
        ("open:https://example.com/a?b=c", Action("open", "https://example.com/a?b=c")),
        ("keys:<cmd>+d", Action("keys", "<cmd>+d")),
        ("launcher", Action("launcher")),
        ("none", Action("none")),
    ],
)
def test_parse_action(text, expected):
    assert parse_action(text) == expected


@pytest.mark.parametrize("text", ["", "open:", "run:notepad", "notepad", "keys:<nosuchkey>+d"])
def test_parse_action_rejects_bad_text(text):
    with pytest.raises(ConfigError):
        parse_action(text)


def test_all_default_apps_are_valid():
    for _, action in DEFAULT_APPS:
        parse_action(action)


def test_bad_app_is_caught_at_startup_not_when_used():
    with pytest.raises(ConfigError):
        SystemActions(Config(apps=(("Broken", "launch:thing"),)))


def test_gesture_runs_its_bound_action(monkeypatch):
    opened = []
    monkeypatch.setattr(actions, "open_target", opened.append)
    SystemActions(Config(ring_pinch_action="open:notepad", pinky_pinch_action="none")).run(Pose.RING_PINCH)
    assert opened == ["notepad"]


def test_none_action_does_nothing(monkeypatch):
    monkeypatch.setattr(actions, "open_target", lambda _: pytest.fail("should not open"))
    SystemActions(Config(pinky_pinch_action="none")).run(Pose.PINKY_PINCH)


def test_failing_action_is_reported_not_raised(monkeypatch, capsys):
    def fail(_):
        raise OSError("not found")

    monkeypatch.setattr(actions, "open_target", fail)
    perform(Action("open", "nosuchapp"))
    assert "nosuchapp" in capsys.readouterr().out


def test_dry_run_prints_instead_of_performing(monkeypatch, capsys):
    monkeypatch.setattr(actions, "open_target", lambda _: pytest.fail("should not open"))
    dry = DryRunActions(Config(ring_pinch_action="open:notepad"))
    dry.run(Pose.RING_PINCH)
    dry.run(Pose.PINKY_PINCH)
    out = capsys.readouterr().out
    assert "open notepad" in out and "keys <cmd>+<tab>" in out


def test_launcher_stays_on_its_monitor():
    size = window_size(10)
    monitor = Rect(-966, -1080, 1920, 1080)
    assert window_position(monitor, (-966, -1080), size) == (-966, -1080)
    x, y = window_position(monitor, (953, -1), size)
    assert x + size[0] == 954 and y + size[1] == 0
