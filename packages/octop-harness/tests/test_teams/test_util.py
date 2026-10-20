from octop_harness.teams.util import clamp_peer_invoke_mode, parse_peer_invoke_mode, parse_team_peers


def test_parse_peer_invoke_mode_accepts_known_values() -> None:
    assert parse_peer_invoke_mode("sync") == "sync"
    assert parse_peer_invoke_mode("async") == "async"
    assert parse_peer_invoke_mode("both") == "both"
    assert parse_peer_invoke_mode(None) is None
    assert parse_peer_invoke_mode("maybe") is None


def test_clamp_peer_invoke_mode_never_gains_async() -> None:
    assert clamp_peer_invoke_mode("async", "sync") == "sync"
    assert clamp_peer_invoke_mode("both", "sync") == "sync"
    assert clamp_peer_invoke_mode("sync", "async") == "sync"
    assert clamp_peer_invoke_mode("both", "async") == "async"
    assert clamp_peer_invoke_mode("async", "both") == "async"
    assert clamp_peer_invoke_mode(None, "both") == "both"


def test_parse_team_peers_empty_means_hide_everyone() -> None:
    assert parse_team_peers(None) is None
    assert parse_team_peers("") == ()
    assert parse_team_peers("   ") == ()
    assert parse_team_peers([]) == ()
    assert parse_team_peers("@analyst") == ("analyst",)
    assert parse_team_peers(["@a", " b ", ""]) == ("a", "b")
