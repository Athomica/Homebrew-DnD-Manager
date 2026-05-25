"""Theme and stylesheet for DnDManager v3.1.

v3.1 Section 1.1: more generous spacing throughout. Sections breathe;
nothing should feel like a spreadsheet.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QApplication


COLORS = {
    # Backgrounds (monochrome dark)
    "bg_base":     "#1a1a1a",
    "bg_section":  "#212121",
    "bg_raised":   "#2a2a2a",
    "border":      "#333333",

    # Text
    "text":        "#fafafa",
    "text_dim":    "#888888",

    # Accents
    "accent_gold": "#aa8f66",
    "accent_red":  "#f72c25",
    "accent_wine": "#471323",

    # Vital bar fills (dedicated)
    "vital_hp":      "#d81159",
    "vital_stamina": "#44af69",
    "vital_mana":    "#33658a",
}


FONT_STACK = '"Inter", "Segoe UI", "Noto Sans", "DejaVu Sans", sans-serif'
MONO_STACK = '"JetBrains Mono", "Fira Code", monospace'


def build_stylesheet() -> str:
    c = COLORS
    return f"""
        QWidget {{
            background-color: {c['bg_base']};
            color: {c['text']};
            font-family: {FONT_STACK};
            font-size: 13px;
        }}
        QMainWindow, QDialog {{
            background-color: {c['bg_base']};
        }}

        QGroupBox {{
            background-color: {c['bg_section']};
            border: 1px solid {c['border']};
            border-radius: 6px;
            margin-top: 18px;
            padding: 16px 12px 12px 12px;
            font-weight: bold;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 12px;
            top: -2px;
            padding: 0 8px;
            color: {c['accent_gold']};
            font-size: 15px;
            font-weight: bold;
        }}

        QLabel {{
            background-color: transparent;
        }}
        QLabel[role="header"] {{
            color: {c['accent_gold']};
            font-size: 15px;
            font-weight: bold;
        }}
        QLabel[role="dim"] {{
            color: {c['text_dim']};
            font-size: 11px;
        }}
        QLabel[role="big"] {{
            color: {c['text']};
            font-size: 20px;
            font-weight: bold;
        }}
        QLabel[role="critical"] {{
            color: {c['accent_red']};
            font-weight: bold;
        }}
        QLabel[role="warning"] {{
            color: {c['accent_red']};
            font-weight: bold;
        }}
        QLabel[role="vital_low"] {{
            color: {c['accent_red']};
            font-weight: bold;
        }}
        QLabel[role="vital_mid"] {{
            font-weight: bold;
        }}

        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {{
            background-color: {c['bg_base']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 4px;
            padding: 5px 8px;
            selection-background-color: {c['accent_wine']};
        }}
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
        QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 1px solid {c['accent_gold']};
        }}
        QComboBox QAbstractItemView {{
            background-color: {c['bg_section']};
            color: {c['text']};
            border: 1px solid {c['border']};
            selection-background-color: {c['accent_wine']};
            padding: 4px;
        }}
        QSpinBox::up-button, QSpinBox::down-button,
        QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
            background-color: {c['bg_section']};
            border: none;
            width: 16px;
        }}

        QPushButton {{
            background-color: {c['bg_section']};
            color: {c['text']};
            border: 1px solid {c['border']};
            border-radius: 4px;
            padding: 6px 14px;
        }}
        QPushButton:hover {{
            background-color: {c['bg_raised']};
        }}
        QPushButton:pressed {{
            background-color: {c['bg_base']};
        }}
        QPushButton:disabled {{
            color: {c['text_dim']};
        }}
        QPushButton[role="danger"] {{
            background-color: {c['accent_red']};
            color: white;
            border: none;
        }}
        QPushButton[role="danger"]:hover {{
            background-color: #d4231e;
        }}
        QPushButton[role="primary"] {{
            background-color: {c['accent_wine']};
            color: white;
            border: none;
        }}
        QPushButton[role="primary"]:hover {{
            background-color: #5e1a30;
        }}

        QListWidget, QTreeWidget, QTableWidget {{
            background-color: {c['bg_base']};
            border: 1px solid {c['border']};
            border-radius: 4px;
            alternate-background-color: {c['bg_section']};
        }}
        QListWidget::item, QTreeWidget::item, QTableWidget::item {{
            padding: 4px;
        }}
        QListWidget::item:selected, QTreeWidget::item:selected,
        QTableWidget::item:selected {{
            background-color: {c['accent_wine']};
            color: white;
        }}
        QHeaderView::section {{
            background-color: {c['bg_section']};
            color: {c['accent_gold']};
            border: 1px solid {c['border']};
            padding: 6px;
            font-weight: bold;
        }}

        QTabWidget::pane {{
            background-color: {c['bg_base']};
            border: 1px solid {c['border']};
            border-radius: 4px;
            top: -1px;
        }}
        QTabBar::tab {{
            background-color: {c['bg_base']};
            color: {c['text_dim']};
            padding: 8px 16px;
            margin-right: 2px;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }}
        QTabBar::tab:selected {{
            background-color: {c['bg_section']};
            color: {c['text']};
            border-bottom: 2px solid {c['accent_gold']};
        }}
        QTabBar::tab:hover:!selected {{
            background-color: {c['bg_raised']};
            color: {c['text']};
        }}

        QProgressBar {{
            background-color: {c['bg_base']};
            border: 1px solid {c['border']};
            border-radius: 4px;
            text-align: center;
            color: {c['text']};
            height: 22px;
        }}
        QProgressBar[vital="hp"]::chunk {{
            background-color: {c['vital_hp']};
            border-radius: 3px;
        }}
        QProgressBar[vital="stamina"]::chunk {{
            background-color: {c['vital_stamina']};
            border-radius: 3px;
        }}
        QProgressBar[vital="mana"]::chunk {{
            background-color: {c['vital_mana']};
            border-radius: 3px;
        }}

        QScrollBar:vertical {{
            background-color: {c['bg_base']};
            width: 10px;
            margin: 0;
            border: none;
        }}
        QScrollBar::handle:vertical {{
            background-color: {c['bg_raised']};
            border-radius: 5px;
            min-height: 30px;
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            background: none;
            height: 0;
        }}
        QScrollBar:horizontal {{
            background-color: {c['bg_base']};
            height: 10px;
            margin: 0;
            border: none;
        }}
        QScrollBar::handle:horizontal {{
            background-color: {c['bg_raised']};
            border-radius: 5px;
            min-width: 30px;
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            background: none;
            width: 0;
        }}

        QToolTip {{
            background-color: {c['bg_section']};
            color: {c['text']};
            border: 1px solid {c['accent_gold']};
            padding: 6px;
        }}

        QMenuBar {{
            background-color: {c['bg_base']};
            color: {c['text']};
            border-bottom: 1px solid {c['border']};
        }}
        QMenuBar::item {{
            padding: 6px 12px;
        }}
        QMenuBar::item:selected {{
            background-color: {c['bg_raised']};
        }}
        QMenu {{
            background-color: {c['bg_section']};
            color: {c['text']};
            border: 1px solid {c['border']};
            padding: 4px;
        }}
        QMenu::item {{
            padding: 6px 20px;
        }}
        QMenu::item:selected {{
            background-color: {c['accent_wine']};
            color: white;
        }}

        QSplitter::handle {{
            background-color: {c['border']};
        }}
        QSplitter::handle:hover {{
            background-color: {c['accent_gold']};
        }}

        QCheckBox {{
            spacing: 8px;
        }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border: 1px solid {c['border']};
            background-color: {c['bg_base']};
            border-radius: 3px;
        }}
        QCheckBox::indicator:checked {{
            background-color: {c['accent_wine']};
            border: 1px solid {c['accent_gold']};
        }}
        QRadioButton {{
            spacing: 8px;
        }}
        QRadioButton::indicator {{
            width: 16px;
            height: 16px;
            border: 1px solid {c['border']};
            background-color: {c['bg_base']};
            border-radius: 8px;
        }}
        QRadioButton::indicator:checked {{
            background-color: {c['accent_wine']};
            border: 1px solid {c['accent_gold']};
        }}

        QStatusBar {{
            background-color: {c['bg_section']};
            color: {c['text_dim']};
            border-top: 1px solid {c['border']};
        }}

        QDockWidget {{
            color: {c['text']};
        }}
        QDockWidget::title {{
            background-color: {c['bg_section']};
            color: {c['accent_gold']};
            padding: 6px;
            font-weight: bold;
        }}
    """


def apply_theme(app: QApplication) -> None:
    app.setStyleSheet(build_stylesheet())
