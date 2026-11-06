"""Isolated Qt Widgets foundation check, not the trading workstation.

Run headless with python -m grog.desktop.probe --smoke once the optional
PySide6-Essentials package is present. Without --smoke a small demonstration
window opens; it never reads market data, opens SQLite or creates trades.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gold native desktop UI foundation check")
    parser.add_argument(
        "--smoke", action="store_true", help="initialize and close a headless Qt window"
    )
    args = parser.parse_args(argv)
    if args.smoke:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    try:
        from PySide6.QtCore import qVersion
        from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget
    except ImportError:
        print(
            "Desktop foundation is unavailable: PySide6-Essentials is not installed. "
            "The existing Textual app is unaffected.",
            file=sys.stderr,
        )
        return 3

    application = QApplication.instance() or QApplication(["grog-desktop-probe"])
    window = QMainWindow()
    window.setWindowTitle("Gold | Desktop foundation (no market data)")
    window.resize(820, 500)
    center = QWidget()
    layout = QVBoxLayout(center)
    layout.setContentsMargins(44, 36, 44, 36)
    layout.setSpacing(18)
    heading = QLabel("GOLD / DESKTOP")
    heading.setObjectName("heading")
    layout.addWidget(heading)
    status = QLabel("DESKTOP FOUNDATION CHECK  /  OFFLINE  /  NO MARKET DATA")
    status.setObjectName("status")
    layout.addWidget(status)
    detail = QLabel(
        "Qt Widgets initialized. No replay is running, no signals are shown, "
        "and no journal or broker operations are available in this test window."
    )
    detail.setWordWrap(True)
    layout.addWidget(detail)
    layout.addStretch()
    window.setCentralWidget(center)
    window.setStyleSheet(
        "QMainWindow, QWidget { background: #0F141C; color: #E9EDF3; "
        "font-family: 'Noto Sans', 'DejaVu Sans'; font-size: 14px; } "
        "QLabel#heading { color: #E5BD74; font-size: 28px; font-weight: 700; } "
        "QLabel#status { color: #E5BD74; font-size: 11px; }"
    )
    window.show()
    if args.smoke:
        application.processEvents()
        visible = window.isVisible()
        window.close()
        if visible:
            print(f"Gold desktop Qt smoke PASS (Qt {qVersion()})")
            return 0
        print("Gold desktop Qt smoke FAILED: window not visible", file=sys.stderr)
        return 1
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
