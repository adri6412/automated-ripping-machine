"""Dark, touch-friendly stylesheet."""

ACCENT = "#4f8cff"
OK = "#33c27f"
WARN = "#f2b33d"
ERR = "#ef5b5b"
BG = "#0f1218"
CARD = "#181d26"
CARD2 = "#202634"
TEXT = "#e8ecf3"
MUTED = "#8b94a7"

STYLESHEET = f"""
* {{ font-family: "Segoe UI", "Inter", "Noto Sans", sans-serif; color: {TEXT}; }}
QMainWindow, QWidget#root {{ background: {BG}; }}
QDialog {{ background: {BG}; }}
QLabel {{ background: transparent; }}
QLabel#h1 {{ font-size: 40px; font-weight: 600; }}
QLabel#h2 {{ font-size: 26px; font-weight: 600; }}
QLabel#h3 {{ font-size: 19px; font-weight: 600; }}
QLabel#muted {{ color: {MUTED}; font-size: 17px; }}
QLabel#body {{ font-size: 17px; }}
QLabel#brand {{ font-size: 20px; font-weight: 700; letter-spacing: 2px; }}
QLabel#clock {{ font-size: 20px; color: {MUTED}; }}
QLabel#badge {{ background: {CARD2}; border-radius: 12px; padding: 4px 14px; font-size: 15px;
               font-weight: 600; }}
QLabel#badgeAccent {{ background: {ACCENT}; border-radius: 12px; padding: 4px 14px; font-size: 15px;
                     font-weight: 700; color: white; }}
QLabel#chipOk {{ background: rgba(51,194,127,0.15); color: {OK}; border-radius: 10px;
                padding: 4px 12px; font-size: 14px; }}
QLabel#chipErr {{ background: rgba(239,91,91,0.15); color: {ERR}; border-radius: 10px;
                 padding: 4px 12px; font-size: 14px; }}
QLabel#chipWarn {{ background: rgba(242,179,61,0.15); color: {WARN}; border-radius: 10px;
                  padding: 4px 12px; font-size: 14px; }}
QLabel#bigIconOk {{ font-size: 110px; color: {OK}; }}
QLabel#bigIconErr {{ font-size: 110px; color: {ERR}; }}
QFrame#card {{ background: {CARD}; border-radius: 18px; }}
QFrame#header {{ background: {CARD}; border-bottom: 1px solid #252c3a; }}

QPushButton {{ background: {CARD2}; border: 1px solid #2c3446; border-radius: 14px;
              padding: 14px 26px; font-size: 18px; font-weight: 600; min-height: 28px; }}
QPushButton:hover {{ background: #2a3244; }}
QPushButton:pressed {{ background: #333d53; }}
QPushButton:disabled {{ color: #5a6275; background: #161a22; border-color: #1f2430; }}
QPushButton#primary {{ background: {ACCENT}; border: none; color: white; font-size: 22px;
                      padding: 18px 40px; }}
QPushButton#primary:hover {{ background: #6a9dff; }}
QPushButton#primary:disabled {{ background: #22304d; color: #6f7b94; }}
QPushButton#danger {{ background: transparent; border: 1px solid {ERR}; color: {ERR}; }}
QPushButton#danger:hover {{ background: rgba(239,91,91,0.12); }}
QPushButton#flat {{ background: transparent; border: none; padding: 8px 14px; font-size: 17px;
                   color: {MUTED}; }}
QPushButton#flat:hover {{ color: {TEXT}; }}

QFrame#option {{ border-radius: 16px; background: {CARD}; border: 2px solid #252c3a; }}
QFrame#option:hover {{ border-color: #3a4560; }}
QFrame#option[checked="true"] {{ border: 2px solid {ACCENT}; background: #18233a; }}
QFrame#option[enabled_="false"] {{ background: #12161d; }}
QLabel#optionDisabled {{ color: #5a6275; font-size: 17px; }}

QProgressBar {{ background: {CARD2}; border: none; border-radius: 12px; height: 26px;
               text-align: center; font-size: 15px; font-weight: 600; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                       stop:0 {ACCENT}, stop:1 #7aa7ff); border-radius: 12px; }}
QProgressBar#thin {{ height: 6px; border-radius: 3px; }}
QProgressBar#thin::chunk {{ border-radius: 3px; }}

QPlainTextEdit, QListWidget {{ background: #0b0e13; border: 1px solid #222937; border-radius: 12px;
                              font-family: "Cascadia Mono", "Consolas", monospace; font-size: 13px;
                              color: #b9c2d3; padding: 8px; }}
QListWidget#history {{ font-family: "Segoe UI", sans-serif; font-size: 16px; color: {TEXT}; }}
QListWidget#history::item {{ padding: 8px; border-bottom: 1px solid #1c2230; }}

QLineEdit, QSpinBox, QComboBox {{ background: {CARD2}; border: 1px solid #2c3446; border-radius: 10px;
                                  padding: 8px 12px; font-size: 16px; min-height: 26px; }}
QComboBox QAbstractItemView {{ background: {CARD2}; selection-background-color: {ACCENT}; }}
QCheckBox {{ font-size: 16px; spacing: 10px; }}
QCheckBox::indicator {{ width: 22px; height: 22px; border-radius: 6px; border: 1px solid #3a4560;
                        background: {CARD2}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QDialog QLabel {{ font-size: 16px; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 12px 22px; font-size: 17px;
               border-bottom: 3px solid transparent; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 3px solid {ACCENT}; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: #2c3446; border-radius: 5px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QMessageBox QLabel {{ font-size: 17px; }}
"""
