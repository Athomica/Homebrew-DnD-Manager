"""Main window for v3.1.

Top-level tabs:
1. Global Character List (Party / Mobs / NPCs)
2. Encounters
3. Global Lists
4. Combat & Change Log

The Scaling Modifiers panel appears as a dock/tab toggle in the
Developer view.
"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSpinBox, QFileDialog, QMessageBox, QStatusBar, QDialog,
    QPlainTextEdit, QDialogButtonBox, QDockWidget, QPushButton,
    QLineEdit, QFormLayout,
)

from state import StateManager, SAVES_DIR, AUTOSAVE_DIR
from ui.global_character_list_tab import GlobalCharacterListTab
from ui.encounter_tab import EncounterTab
from ui.lists_tab import GlobalListsTab
from ui.combat_log import CombatLogTab
from ui.components.scaling_modifiers import ScalingModifiersPanel


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DnD Manager v3.4")
        self.resize(1400, 900)
        self.setMinimumSize(900, 700)

        self._state = StateManager(self)

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        # Top status strip
        strip = QHBoxLayout()
        strip.setSpacing(12)
        strip.addWidget(QLabel("Total Turns:"))
        self._total_turn_label = QLabel("0")
        self._total_turn_label.setProperty("role", "big")
        strip.addWidget(self._total_turn_label)
        strip.addSpacing(20)
        self._campaign_label = QLabel("(no campaign loaded)")
        self._campaign_label.setProperty("role", "dim")
        strip.addWidget(self._campaign_label)
        strip.addStretch(1)
        self._view_chip = QLabel("DM view")
        self._view_chip.setProperty("role", "dim")
        strip.addWidget(self._view_chip)
        outer.addLayout(strip)

        # Main tabs
        self._tabs = QTabWidget()
        outer.addWidget(self._tabs, 1)

        self._gcl_tab = GlobalCharacterListTab(self._state)
        self._enc_tab = EncounterTab(self._state)
        self._lists_tab = GlobalListsTab(self._state)
        self._log_tab = CombatLogTab(self._state)
        self._tabs.addTab(self._gcl_tab, "Global Character List")
        self._tabs.addTab(self._enc_tab, "Encounters")
        self._tabs.addTab(self._lists_tab, "Equipment List")
        self._tabs.addTab(self._log_tab, "Combat && Change Log")

        # Scaling modifiers dock (developer view)
        self._modifier_dock = QDockWidget("Scaling Modifiers", self)
        self._modifier_dock.setAllowedAreas(
            Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.BottomDockWidgetArea)
        self._modifier_panel = ScalingModifiersPanel(self._state)
        self._modifier_panel.setMinimumWidth(560)
        self._modifier_dock.setWidget(self._modifier_panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self._modifier_dock)
        self._modifier_dock.setVisible(False)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("Ready")

        self._build_menus()

        self._state.log_appended.connect(self._refresh_total_turns)
        self._state.lists_changed.connect(self._refresh_campaign_label)
        self._state.encounter_changed.connect(self._refresh_total_turns_ignore)
        self._state.view_mode_changed.connect(self._refresh_view_mode)

        self._state.start_autosave()
        self._refresh_total_turns({})
        self._refresh_view_mode()

        # Crash recovery
        latest = self._state.latest_autosave()
        if latest is not None and latest.exists():
            try:
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

    def _refresh_total_turns_ignore(self) -> None:
        self._refresh_total_turns({})

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

        m_view = self.menuBar().addMenu("&View")
        a_dev = QAction("Toggle &Developer View", self)
        a_dev.setShortcut(QKeySequence("Ctrl+D"))
        a_dev.triggered.connect(self._state.toggle_developer_view)
        m_view.addAction(a_dev)

        m_help = self.menuBar().addMenu("&Help")
        a_about = QAction("&About", self)
        a_about.triggered.connect(self._on_about)
        a_changelog = QAction("&Changelog", self)
        a_changelog.triggered.connect(self._on_show_changelog)
        m_help.addAction(a_changelog)
        m_help.addAction(a_about)

    def _on_new(self) -> None:
        reply = QMessageBox.question(
            self, "New Campaign",
            "Discard current state and start fresh? (Last state is auto-backed-up.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            from models import AppState
            from state import BACKUP_DIR, serialize_app_state
            import json, time, traceback

            # Best-effort backup of the current state
            try:
                (BACKUP_DIR / f"backup_{int(time.time())}.json").write_text(
                    json.dumps(serialize_app_state(self._state.state, save_name="pre_new"),
                               indent=2))
            except Exception:
                # Backup is non-critical
                pass

            # Tear down the current GCL detail sheets before swapping state out
            # from under them - this prevents orphan CharacterSheet widgets
            # from receiving signals against state they no longer belong to.
            try:
                self._gcl_tab.tear_down_detail_sheets()
            except Exception:
                pass

            # Swap to a fresh state and reapply (empty) modifiers
            self._state.state = AppState()
            self._state._apply_modifiers_to_engine()
            self._state._current_save_path = None

            # Notify subscribers; each tab decides how to redraw
            self._state.lists_changed.emit()
            self._state.encounter_changed.emit()
            self._refresh_total_turns({})
            self._refresh_campaign_label()
            self.statusBar().showMessage("New campaign started", 3000)
        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            QMessageBox.critical(
                self, "New Campaign Failed",
                f"Could not start a new campaign:\n\n{exc}\n\n"
                f"Traceback:\n{tb[-1500:]}")

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

    def _on_campaign_settings(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Campaign Settings")
        v = QVBoxLayout(dlg)
        form = QFormLayout()
        name_in = QLineEdit(self._state.state.campaign_name)
        sess_in = QSpinBox()
        sess_in.setRange(0, 99999)
        sess_in.setValue(self._state.state.session_number)
        notes_in = QPlainTextEdit(self._state.state.campaign_notes)
        notes_in.setFixedHeight(120)
        form.addRow("Campaign Name:", name_in)
        form.addRow("Session #:", sess_in)
        form.addRow("Notes:", notes_in)
        v.addLayout(form)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        v.addWidget(bb)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._state.state.campaign_name = name_in.text()
            self._state.state.session_number = sess_in.value()
            self._state.state.campaign_notes = notes_in.toPlainText()
            self._refresh_campaign_label()

    def _on_about(self) -> None:
        QMessageBox.about(
            self, "About DnD Manager",
            "DnD Manager v3.4\n\n"
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
        edit = QPlainTextEdit(text)
        edit.setReadOnly(True)
        v.addWidget(edit)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        v.addWidget(bb)
        bb.rejected.connect(dlg.reject)
        bb.accepted.connect(dlg.accept)
        bb.button(QDialogButtonBox.StandardButton.Close).clicked.connect(dlg.accept)
        dlg.exec()

    def _refresh_total_turns(self, _entry: dict) -> None:
        self._total_turn_label.setText(str(self._state.state.total_turns))

    def _refresh_campaign_label(self) -> None:
        name = self._state.state.campaign_name or "(no campaign loaded)"
        sess = self._state.state.session_number
        self._campaign_label.setText(f"{name} — session {sess}")

    def _refresh_view_mode(self) -> None:
        is_dev = self._state.state.developer_view
        self._modifier_dock.setVisible(is_dev)
        self._view_chip.setText("Developer view" if is_dev else "DM view")
        self._view_chip.setStyleSheet(
            "color: #aa8f66; font-weight: bold;" if is_dev else "color: #888888;")

    def closeEvent(self, event) -> None:
        try:
            self._state.autosave()
            self._state.stop_autosave()
        except Exception:
            pass
        super().closeEvent(event)
