"""Colour themes (dark + light) and the global stylesheet builder.

Custom-painted widgets (card delegate, graph, placeholders) read colours from
`current()`; everything standard is styled by `qss()`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    name: str
    dark: bool
    bg: str            # window background
    surface: str       # panels, cards, tiles
    surface2: str      # inputs, sunken areas
    border: str
    border_strong: str
    text: str
    text_dim: str
    text_faint: str
    accent: str
    accent_text: str
    card: str          # grid card background
    card_hover: str
    sel_bg: str        # selection tint
    thumb_bg: str      # thumbnail backdrop
    graph_bg: str
    node_bg: str
    node_focus_bg: str
    edge: str


THEMES: dict[str, Theme] = {
    "Midnight": Theme(
        name="Midnight", dark=True,
        bg="#16171b", surface="#22242a", surface2="#24262c",
        border="#2b2d34", border_strong="#30323a",
        text="#e7e8ec", text_dim="#9aa0ab", text_faint="#6b6f78",
        accent="#5b8cff", accent_text="#ffffff",
        card="#23252b", card_hover="#2c2f38", sel_bg="#2a3557",
        thumb_bg="#1a1b20", graph_bg="#16171b", node_bg="#2a2d34",
        node_focus_bg="#233056", edge="#5c606b",
    ),
    "Violet": Theme(
        name="Violet", dark=True,
        bg="#17151d", surface="#241f2e", surface2="#272130",
        border="#332b40", border_strong="#3d3350",
        text="#ece8f2", text_dim="#a79bb5", text_faint="#726781",
        accent="#a175f0", accent_text="#ffffff",
        card="#241f2e", card_hover="#2f2740", sel_bg="#3a2c55",
        thumb_bg="#1c1824", graph_bg="#17151d", node_bg="#2c2439",
        node_focus_bg="#3a2c55", edge="#6b5c80",
    ),
    "Daylight": Theme(
        name="Daylight", dark=False,
        bg="#f5f6f9", surface="#ffffff", surface2="#eef0f4",
        border="#e0e3e9", border_strong="#cdd2da",
        text="#1c2026", text_dim="#5a6472", text_faint="#98a0ac",
        accent="#2f6bff", accent_text="#ffffff",
        card="#ffffff", card_hover="#eef3fc", sel_bg="#d9e6ff",
        thumb_bg="#eef0f4", graph_bg="#f0f2f6", node_bg="#ffffff",
        node_focus_bg="#dbe7ff", edge="#aab0bc",
    ),
    "Sand": Theme(
        name="Sand", dark=False,
        bg="#f3efe7", surface="#fbf8f2", surface2="#ece7db",
        border="#ddd6c6", border_strong="#ccc3ad",
        text="#38332a", text_dim="#6b6350", text_faint="#a49a83",
        accent="#c07a2f", accent_text="#ffffff",
        card="#fbf8f2", card_hover="#f3ecdd", sel_bg="#efe0c6",
        thumb_bg="#ece7db", graph_bg="#efeae0", node_bg="#fbf8f2",
        node_focus_bg="#f0e1c5", edge="#b6ab90",
    ),
}

DEFAULT = "Midnight"
_current = THEMES[DEFAULT]


def current() -> Theme:
    return _current


def set_current(name: str) -> Theme:
    global _current
    _current = THEMES.get(name, THEMES[DEFAULT])
    return _current


def names() -> list[str]:
    return list(THEMES)


def qss(t: Theme) -> str:
    return f"""
* {{ font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 13px; }}
QMainWindow, QDialog {{ background: {t.bg}; }}
QWidget {{ background: {t.bg}; color: {t.text}; }}

QToolBar {{ background: {t.surface}; border: none; border-bottom: 1px solid {t.border};
    padding: 8px 10px; spacing: 8px; }}
QToolBar::separator {{ background: {t.border_strong}; width: 1px; margin: 4px 6px; }}
QToolBar QToolButton {{ padding: 7px 12px; border-radius: 8px; color: {t.text};
    font-weight: 500; }}
QToolBar QToolButton:hover {{ background: {t.surface2}; }}
QToolBar QToolButton:pressed {{ background: {t.border_strong}; }}

QLineEdit {{ background: {t.surface2}; border: 1px solid {t.border_strong};
    border-radius: 9px; padding: 7px 11px; color: {t.text};
    selection-background-color: {t.accent}; selection-color: {t.accent_text}; }}
QLineEdit:focus {{ border: 1px solid {t.accent}; }}
QComboBox {{ background: {t.surface2}; border: 1px solid {t.border_strong};
    border-radius: 9px; padding: 6px 11px; color: {t.text}; }}
QComboBox:hover {{ border: 1px solid {t.accent}; }}
QComboBox QAbstractItemView {{ background: {t.surface}; color: {t.text};
    border: 1px solid {t.border_strong}; border-radius: 8px;
    selection-background-color: {t.accent}; selection-color: {t.accent_text}; outline: none; }}
QSpinBox {{ background: {t.surface2}; border: 1px solid {t.border_strong};
    border-radius: 8px; padding: 4px 6px; color: {t.text}; }}

QPushButton {{ background: {t.surface2}; border: 1px solid {t.border_strong};
    border-radius: 9px; padding: 7px 13px; color: {t.text}; }}
QPushButton:hover {{ background: {t.card_hover}; border-color: {t.accent}; }}
QPushButton:pressed {{ background: {t.border_strong}; }}
QPushButton:checked {{ background: {t.accent}; border-color: {t.accent}; color: {t.accent_text}; }}
QPushButton:disabled {{ color: {t.text_faint}; background: {t.surface}; }}

QPushButton[chip="true"] {{ background: {t.surface2}; border: 1px solid {t.border};
    border-radius: 15px; padding: 6px 15px; color: {t.text_dim}; font-weight: 500; }}
QPushButton[chip="true"]:hover {{ background: {t.card_hover}; color: {t.text}; }}
QPushButton[chip="true"]:checked {{ background: {t.accent}; border-color: {t.accent};
    color: {t.accent_text}; }}

QListView {{ background: {t.bg}; border: none; }}
QListWidget {{ background: {t.surface2}; color: {t.text};
    border: 1px solid {t.border}; border-radius: 8px; }}
QListWidget::item {{ padding: 4px 6px; border-radius: 5px; }}
QListWidget::item:hover {{ background: {t.card_hover}; }}
QListWidget::item:selected {{ background: {t.sel_bg}; color: {t.text}; }}

QLabel {{ background: transparent; color: {t.text}; }}
QLabel[role="dim"] {{ color: {t.text_dim}; }}
QLabel[role="section"] {{ color: {t.text_dim}; font-size: 11px; font-weight: 700;
    letter-spacing: 1px; }}

QFrame[role="panel"] {{ background: {t.surface}; border-radius: 10px; }}

QSplitter::handle {{ background: {t.bg}; width: 2px; }}
QSplitter::handle:hover {{ background: {t.border_strong}; }}

QProgressBar {{ border: none; border-radius: 5px; background: {t.surface2};
    max-height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {t.accent}; border-radius: 5px; }}

QSlider::groove:horizontal {{ height: 4px; background: {t.border_strong}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {t.accent}; width: 12px; margin: -5px 0;
    border-radius: 6px; }}
QSlider::sub-page:horizontal {{ background: {t.accent}; border-radius: 2px; }}

QStatusBar {{ background: {t.surface}; color: {t.text_dim}; border-top: 1px solid {t.border}; }}
QStatusBar::item {{ border: none; }}
QToolTip {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border_strong};
    border-radius: 6px; padding: 5px 8px; }}

QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.border_strong}; border-radius: 5px; min-height: 36px; }}
QScrollBar::handle:vertical:hover {{ background: {t.accent}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t.border_strong}; border-radius: 5px; min-width: 36px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""
