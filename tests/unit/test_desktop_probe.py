"""The native probe's help path does not require an installed Qt runtime."""

from __future__ import annotations

import pytest

from grog.desktop.probe import main


def test_probe_help_requires_no_qt(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "--smoke" in capsys.readouterr().out
