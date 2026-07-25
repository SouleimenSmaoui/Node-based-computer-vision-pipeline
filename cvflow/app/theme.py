"""Dark theme, category colours, and wire/type colours (docs/05 §6).

Palette is the near-Nuke default from the design doc; category colours are the
Okabe-Ito colourblind-safe set so a red/green-blind user still reads the graph.
Status is *also* encoded by badge glyph in the node items — never colour alone.
"""

from __future__ import annotations

from PySide6 import QtGui, QtWidgets

# ---- surfaces (docs/05 §6) -------------------------------------------------
SURFACE = "#2b2b2b"
PANEL = "#3c3f41"
PANEL_HI = "#4b4f51"
TEXT = "#d8d8d8"
TEXT_DIM = "#9a9a9a"
ACCENT = "#4a9eff"
VIEWER_BG = "#202020"   # neutral grey surround — never pure black/white
GRID = "#323232"
NODE_BODY = "#454749"
NODE_SELECTED = ACCENT

# ---- Okabe-Ito category tints ---------------------------------------------
_OKABE_ITO = [
    "#E69F00", "#56B4E9", "#009E73", "#F0E442",
    "#0072B2", "#D55E00", "#CC79A7", "#999999",
]

# Stable, meaningful assignments for the built-in categories; anything else
# falls back to a hash into the palette so new packs still get a colour.
_CATEGORY_COLORS = {
    "Input / Output": "#0072B2",
    "Color": "#009E73",
    "Filtering": "#56B4E9",
    "Edges": "#E69F00",
    "Threshold": "#CC79A7",
    "Morphology": "#D55E00",
    "Geometry": "#F0E442",
    "Analysis": "#999999",
    "Draw": "#CC79A7",
    "Misc": "#999999",
}


def category_color(category: str) -> QtGui.QColor:
    hexv = _CATEGORY_COLORS.get(category)
    if hexv is None:
        hexv = _OKABE_ITO[hash(category) % len(_OKABE_ITO)]
    return QtGui.QColor(hexv)


# ---- wire colours by data kind (docs/05 §2.2) -----------------------------
_KIND_COLORS = {
    "image": "#e8e8e8",     # white
    "contours": "#ff8c1a",  # orange (geometry)
    "number": "#9a9a9a",    # grey (scalar)
    "text": "#b48ead",      # muted magenta
    "any": "#7f7f7f",
}


def kind_color(kind: str) -> QtGui.QColor:
    return QtGui.QColor(_KIND_COLORS.get(kind, "#7f7f7f"))


# ---- status colours (paired with glyphs in items.py) ----------------------
STATUS_COLORS = {
    "idle": "#7f7f7f",
    "running": ACCENT,
    "ok": "#3fb950",
    "cached": "#5a8f5a",
    "warning": "#e3b341",
    "error": "#f85149",
    "blocked": "#8b5a5a",
    "skipped": "#6a6a6a",
}


def apply_dark_theme(app: QtWidgets.QApplication) -> None:
    app.setStyle("Fusion")
    app.setStyleSheet(_QSS)

    pal = QtGui.QPalette()
    c = QtGui.QColor
    pal.setColor(QtGui.QPalette.ColorRole.Window, c(SURFACE))
    pal.setColor(QtGui.QPalette.ColorRole.WindowText, c(TEXT))
    pal.setColor(QtGui.QPalette.ColorRole.Base, c("#333537"))
    pal.setColor(QtGui.QPalette.ColorRole.AlternateBase, c(PANEL))
    pal.setColor(QtGui.QPalette.ColorRole.Text, c(TEXT))
    pal.setColor(QtGui.QPalette.ColorRole.Button, c(PANEL))
    pal.setColor(QtGui.QPalette.ColorRole.ButtonText, c(TEXT))
    pal.setColor(QtGui.QPalette.ColorRole.Highlight, c(ACCENT))
    pal.setColor(QtGui.QPalette.ColorRole.HighlightedText, c("#ffffff"))
    pal.setColor(QtGui.QPalette.ColorRole.ToolTipBase, c(PANEL))
    pal.setColor(QtGui.QPalette.ColorRole.ToolTipText, c(TEXT))
    disabled = QtGui.QPalette.ColorGroup.Disabled
    pal.setColor(disabled, QtGui.QPalette.ColorRole.Text, c(TEXT_DIM))
    pal.setColor(disabled, QtGui.QPalette.ColorRole.ButtonText, c(TEXT_DIM))
    app.setPalette(pal)


_QSS = f"""
QWidget {{ color: {TEXT}; font-size: 12px; }}
QMainWindow, QDialog {{ background: {SURFACE}; }}
QDockWidget {{ titlebar-close-icon: none; color: {TEXT}; }}
QDockWidget::title {{
    background: {PANEL}; padding: 4px 8px; border: none;
}}
QToolBar {{ background: {SURFACE}; border: none; spacing: 4px; padding: 3px; }}
QToolButton {{ background: transparent; padding: 4px 8px; border-radius: 4px; }}
QToolButton:hover {{ background: {PANEL_HI}; }}
QToolButton:pressed, QToolButton:checked {{ background: {ACCENT}; color: white; }}
QMenuBar {{ background: {SURFACE}; }}
QMenuBar::item:selected {{ background: {PANEL_HI}; }}
QMenu {{ background: {PANEL}; border: 1px solid #555; }}
QMenu::item:selected {{ background: {ACCENT}; }}
QStatusBar {{ background: {PANEL}; color: {TEXT_DIM}; }}
QTabWidget::pane {{ border: 1px solid #555; }}
QTabBar::tab {{
    background: {PANEL}; padding: 5px 12px; border: 1px solid #555;
    border-bottom: none;
}}
QTabBar::tab:selected {{ background: {SURFACE}; color: {ACCENT}; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: #333537; border: 1px solid #555; border-radius: 3px; padding: 2px 4px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox QAbstractItemView {{ background: {PANEL}; selection-background-color: {ACCENT}; }}
QPushButton {{
    background: {PANEL}; border: 1px solid #555; border-radius: 4px; padding: 4px 12px;
}}
QPushButton:hover {{ background: {PANEL_HI}; }}
QPushButton:pressed {{ background: {ACCENT}; }}
QSlider::groove:horizontal {{ height: 4px; background: #2a2a2a; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: #d8d8d8; width: 12px; margin: -5px 0; border-radius: 6px;
}}
QHeaderView::section {{
    background: {PANEL}; color: {TEXT}; padding: 3px 6px; border: none;
    border-right: 1px solid #555;
}}
QTreeView, QTableView, QListView {{
    background: #303233; alternate-background-color: #343637; border: 1px solid #555;
}}
QTreeView::item:selected, QTableView::item:selected, QListView::item:selected {{
    background: {ACCENT};
}}
QScrollBar:vertical {{ background: {SURFACE}; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{ background: #555; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: #6a6a6a; }}
QScrollBar:horizontal {{ background: {SURFACE}; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{ background: #555; border-radius: 5px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QToolTip {{ background: {PANEL}; color: {TEXT}; border: 1px solid {ACCENT}; }}
"""
