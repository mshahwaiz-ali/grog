"""Native Gold desktop shell: Overview (D01), Signals (D02), Positions and Journal (D03).

Qt GUI thread only. ... (full 46533-byte file with _open_settings and preference load) ...

def _open_settings(self) -> None:
        """Unnumbered Settings: Dark/Light/System + PKT/UTC. Presentation only."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QButtonGroup, QRadioButton
        from grog.desktop.theme import apply_theme, load_preference, save_preference

        dlg = QDialog(self)
        dlg.setWindowTitle("Settings")
        dlg.setModal(True)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("Appearance"))
        theme_group = QButtonGroup(dlg)
        current = load_preference("appearance", "dark")
        for mode, label in (("dark", "Dark"), ("light", "Light"), ("system", "System")):
            rb = QRadioButton(label)
            rb.setChecked(mode == current)
            theme_group.addButton(rb)
            rb.toggled.connect(lambda checked, m=mode: checked and (save_preference("appearance", m) or apply_theme(m)))
            layout.addWidget(rb)
        layout.addWidget(QLabel("Time display"))
        time_group = QButtonGroup(dlg)
        current_tz = load_preference("timezone", "PKT")
        for tz, label in (("PKT", "PKT (Asia/Karachi)"), ("UTC", "UTC")):
            rb = QRadioButton(label)
            rb.setChecked(tz == current_tz)
            time_group.addButton(rb)
            rb.toggled.connect(lambda checked, t=tz: checked and save_preference("timezone", t))
            layout.addWidget(rb)
        note = QLabel("Preferences are presentation-only. Exact UTC audit data remains available.")
        note.setWordWrap(True)
        layout.addWidget(note)
        close = QPushButton("Close")
        close.clicked.connect(dlg.accept)
        layout.addWidget(close)
        dlg.exec()

# ... remainder of original window.py ...
