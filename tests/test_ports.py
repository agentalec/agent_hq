import sys
import types

import pytest

from engine.registry import _ADAPTERS, build_adapter

EXPECTED_PAIRS = {
    ("tracker", "github-issues"),
    ("messaging", "github-comment"),
    ("gate", "pr-review"),
    ("executor", "claude-code-headless"),
    ("agent-session", "claude-code-headless"),
    ("executor", "copilot-cli"),
    ("agent-session", "copilot-cli"),
}


def test_registry_keys_match_expected_pairs():
    """Locks the registry's key set so Tasks 8-11 naming drift fails here."""
    assert set(_ADAPTERS) == EXPECTED_PAIRS


def test_unknown_adapter_raises_and_lists_known_candidates():
    with pytest.raises(ValueError) as exc:
        build_adapter("tracker", "bogus", {})
    message = str(exc.value)
    assert "bogus" in message
    assert "github-issues" in message


def test_unknown_port_raises_with_no_known_candidates():
    with pytest.raises(ValueError) as exc:
        build_adapter("qa-env", "docker-compose", {})
    assert "none" in str(exc.value)


@pytest.mark.parametrize("port, adapter_name", sorted(EXPECTED_PAIRS))
def test_build_adapter_resolves_registered_import_path(monkeypatch, port, adapter_name):
    """The four future adapter modules don't exist yet (Tasks 8-11); fake
    each one in sys.modules to prove the (port, adapter_name) -> class
    lookup and construction path works ahead of them landing."""
    module_path, class_name = _ADAPTERS[(port, adapter_name)].split(":")

    class FakeAdapter:
        def __init__(self, settings):
            self.settings = settings

    fake_module = types.ModuleType(module_path)
    setattr(fake_module, class_name, FakeAdapter)
    monkeypatch.setitem(sys.modules, module_path, fake_module)

    instance = build_adapter(port, adapter_name, {"token": "x"})

    assert isinstance(instance, FakeAdapter)
    assert instance.settings == {"token": "x"}
