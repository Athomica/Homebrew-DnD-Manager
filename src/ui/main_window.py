"""Main window: top-level tabs, menu bar, status bar, total turn counter."""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSpinBox, QFileDialog, QMessageBox, QStatusBar, QInputDialog, QDialog,
    QPlainTextEdit, QDialogButtonBox,
)

from state import StateManager, SAVES_DIR, AUTOSAVE_DIR
from ui.party_tab import CharacterGroupTab
from ui.lists_tab import GlobalListsTab
from ui.combat_log import CombatLogTab


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DnD Manager v3")
        self.resize(1280, 800)
        self.setMinimumSize(900, 700)

        self._state = StateManager(self)

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # Top status strip: total turns + last DICE
        strip = QHBoxLayout()
        strip.addWidget(QLabel("Total Turns:"))
        self._total_turn_label = QLabel("0")
        self._total_turn_label.setProperty("role", "big")
        strip.addWidget(self._total_turn_label)
        strip.addSpacing(20)
        self._campaign_label = QLabel("(no campaign loaded)")
        self._campaign_label.setProperty("role", "dim")
        strip.addWidget(self._campaign_label)
        strip.addStretch(1)
        outer.addLayout(strip)

        # Main tabs
        self._tabs = QTabWidget()
        outer.addWidget(self._tabs, 1)

        self._party_tab = CharacterGroupTab(self._state, "party")
        self._encounter_tab = CharacterGroupTab(self._state, "mob")
        self._npc_tab = CharacterGroupTab(self._state, "npc")
        self._lists_tab = GlobalListsTab(self._state)
        self._log_tab = CombatLogTab(self._state)

        self._tabs.addTab(self._party_tab, "Party")
        self._tabs.addTab(self._encounter_tab, "Encounters")
        self._tabs.addTab(self._npc_tab, "NPCs")
        self._tabs.addTab(self._lists_tab, "Global Lists")
        self._tabs.addTab(self._log_tab, "Combat && Change Log")

        # Status bar
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")

        self._build_menus()

        self._state.log_appended.connect(self._refresh_total_turns)
        self._state.lists_changed.connect(self._refresh_campaign_label)
        self._state.character_changed.connect(lambda _id: self._refresh_total_turns({}))

        self._state.start_autosave()
        self._refresh_total_turns({})

        # Crash recovery prompt
        latest = self._state.latest_autosave()
        if latest is not None and latest.exists():
            try:
                QMessageBox  # noqa - just to ensure import
                reply = QMessageBox.question(
                    self, "Restore?",
                    f"An auto-save was found at\n{latest}\nLoad it?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._state.load_from(latest)
                    self.statusBar().showMessage(f"Loaded autosave {latest.name}", 4000)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Menus
    # ------------------------------------------------------------------
    def _build_menus(self) -> None:
        m_file = self.menuBar().addMenu("&File")
        a_new = QAction("&New", self)
        a_new.setShortcut(QKeySequence("Ctrl+N"))
        a_new.triggered.connect(self._on_new)
        a_open = QAction("&Open…", self)
        a_open.setShortcut(QKeySequence("Ctrl+O"))
        a_open.triggered.connect(self._on_open)
        a_save = QAction("&Save", self)
        a_save.setShortcut(QKeySequence("Ctrl+S"))
        a_save.triggered.connect(self._on_save)
        a_save_as = QAction("Save &As…", self)
        a_save_as.setShortcut(QKeySequence("Ctrl+Shift+S"))
        a_save_as.triggered.connect(self._on_save_as)
        a_export = QAction("&Export JSON…", self)
        a_export.triggered.connect(self._on_export)
        a_quit = QAction("&Quit", self)
        a_quit.setShortcut(QKeySequence("Ctrl+Q"))
        a_quit.triggered.connect(self.close)

        m_file.addAction(a_new)
        m_file.addAction(a_open)
        m_file.addSeparator()
        m_file.addAction(a_save)
        m_file.addAction(a_save_as)
        m_file.addAction(a_export)
        m_file.addSeparator()
        m_file.addAction(a_quit)

        m_edit = self.menuBar().addMenu("&Edit")
        a_campaign = QAction("&Campaign Settings…", self)
        a_campaign.triggered.connect(self._on_campaign_settings)
        m_edit.addAction(a_campaign)

        m_help = self.menuBar().addMenu("&Help")
        a_about = QAction("&About", self)
        a_about.triggered.connect(self._on_about)
        a_changelog = QAction("&Changelog", self)
        a_changelog.triggered.connect(self._on_show_changelog)
        m_help.addAction(a_changelog)
        m_help.addAction(a_about)

    # ------------------------------------------------------------------
    # File actions
    # ------------------------------------------------------------------
    def _on_new(self) -> None:
        reply = QMessageBox.question(
            self, "New Campaign",
            "Discard current state and start fresh? (Last state is auto-backed-up.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            from models import AppState
            from state import BACKUP_DIR
            import json, time
            try:
                from state import serialize_app_state
                (BACKUP_DIR / f"backup_{int(time.time())}.json").write_text(
                    json.dumps(serialize_app_state(self._state.state, save_name="pre_new"),
                               indent=2))
            except OSError:
                pass
            self._state.state = AppState()
            self._state.lists_changed.emit()
            self._refresh_total_turns({})
            self.statusBar().showMessage("New campaign started", 3000)

    def _on_open(self) -> None:
        SAVES_DIR.mkdir(parents=True, exist_ok=True)
        path_s, _ = QFileDialog.getOpenFileName(
            self, "Open Save", str(SAVES_DIR), "JSON saves (*.json)")
        if not path_s:
            return
        try:
            self._state.load_from(Path(path_s))
            self.statusBar().showMessage(f"Loaded {Path(path_s).name}", 4000)
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", str(exc))

    def _on_save(self) -> None:
        if self._state.save_current():
            self.statusBar().showMessage("Saved.", 2000)
        else:
            self._on_save_as()

    def _on_save_as(self) -> None:
        SAVES_DIR.mkdir(parents=True, exist_ok=True)
        path_s, _ = QFileDialog.getSaveFileName(
            self, "Save As", str(SAVES_DIR / "campaign.json"),
            "JSON saves (*.json)")
        if not path_s:
            return
        path = Path(path_s)
        if path.suffix != ".json":
            path = path.with_suffix(".json")
        try:
            self._state.save_to(path)
            self.statusBar().showMessage(f"Saved to {path.name}", 3000)
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def _on_export(self) -> None:
        path_s, _ = QFileDialog.getSaveFileName(
            self, "Export JSON", "campaign_export.json", "JSON (*.json)")
        if not path_s:
            return
        try:
            self._state.save_to(Path(path_s), save_name="export")
            self.statusBar().showMessage("Exported", 3000)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    # ------------------------------------------------------------------
    # Campaign settings
    # ------------------------------------------------------------------
    def _on_campaign_settings(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Campaign Settings")
        v = QVBoxLayout(dlg)
        from PyQt6.QtWidgets import QLineEdit, QFormLayout
        form = QFormLayout()
        name_in = QLineEdit(self._state.state.campaign_name)
        sess_in = QSpinBox(); sess_in.setRange(0, 99999)
        sess_in.setValue(self._state.state.session_number)
        notes_in = QPlainTextEdit(self._state.state.campaign_notes)
        notes_in.setFixedHeight(120)
        form.addRow("Campaign Name:", name_in)
        form.addRow("Session #:", sess_in)
        form.addRow("Notes:", notes_in)
        v.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        v.addWidget(bb)
        bb.accepted.connect(dlg.accept); bb.rejected.connect(dlg.reject)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._state.state.campaign_name = name_in.text()
            self._state.state.session_number = sess_in.value()
            self._state.state.campaign_notes = notes_in.toPlainText()
            self._refresh_campaign_label()

    # ------------------------------------------------------------------
    # About / Changelog
    # ------------------------------------------------------------------
    def _on_about(self) -> None:
        QMessageBox.about(
            self, "About DnD Manager",
            "DnD Manager v3\n\n"
            "A solo Dungeon Master's tool for a homebrew dark-fantasy TTRPG.\n\n"
            "Targets KDE Plasma on Wayland (X11 fallback) on Linux.\n"
            "No dice rolling, no networking, no AI."
        )

    def _on_show_changelog(self) -> None:
        try:
            base = Path(__file__).resolve().parent.parent.parent
            for candidate in (base / "CHANGELOG.md", base.parent / "CHANGELOG.md"):
                if candidate.exists():
                    text = candidate.read_text()
                    break
            else:
                text = "(no CHANGELOG.md bundled)"
        except OSError:
            text = "(could not read changelog)"
        dlg = QDialog(self)
        dlg.setWindowTitle("Changelog")
        dlg.resize(700, 500)
        v = QVBoxLayout(dlg)
        edit = QPlainTextEdit(text); edit.setReadOnly(True)
        v.addWidget(edit)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        v.addWidget(bb)
        bb.rejected.connect(dlg.reject); bb.accepted.connect(dlg.accept)
        bb.button(QDialogButtonBox.StandardButton.Close).clicked.connect(dlg.accept)
        dlg.exec()

    # ------------------------------------------------------------------
    # Status updates
    # ------------------------------------------------------------------
    def _refresh_total_turns(self, _entry: dict) -> None:
        self._total_turn_label.setText(str(self._state.state.total_turns))

    def _refresh_campaign_label(self) -> None:
        name = self._state.state.campaign_name or "(no campaign loaded)"
        sess = self._state.state.session_number
        self._campaign_label.setText(f"{name} — session {sess}")

    # ------------------------------------------------------------------
    # Window lifecycle
    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:
        try:
            self._state.autosave()
            self._state.stop_autosave()
        except Exception:
            pass
        super().closeEvent(event)
