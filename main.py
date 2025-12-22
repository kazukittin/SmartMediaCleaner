"""
main.py - SmartMediaCleaner
エントリーポイント
"""
import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

# スタイルシート
STYLESHEET = """
/* ===== ベース設定 ===== */
QMainWindow, QWidget {
    background-color: #1a1a1a;
    color: #e8e8e8;
    font-family: 'Segoe UI', 'Yu Gothic UI', sans-serif;
    font-size: 13px;
}

/* ===== ボタン (Fluent Style) ===== */
QPushButton {
    background-color: #2d2d2d;
    border: 1px solid #404040;
    padding: 8px 16px;
    border-radius: 6px;
    min-height: 20px;
}
QPushButton:hover {
    background-color: #3d3d3d;
    border-color: #0078d4;
}
QPushButton:pressed {
    background-color: #1a1a1a;
}
QPushButton:disabled {
    background-color: #252525;
    color: #666666;
    border-color: #333333;
}

/* プライマリボタン (アクセントカラー) */
QPushButton#primaryBtn, QPushButton[primary="true"] {
    background-color: #0078d4;
    border-color: #0078d4;
    color: white;
}
QPushButton#primaryBtn:hover, QPushButton[primary="true"]:hover {
    background-color: #1a86d9;
}
QPushButton#primaryBtn:pressed, QPushButton[primary="true"]:pressed {
    background-color: #006cbd;
}

/* 危険ボタン (削除系) */
QPushButton#dangerBtn, QPushButton[danger="true"] {
    background-color: #d41a1a;
    border-color: #d41a1a;
    color: white;
}
QPushButton#dangerBtn:hover, QPushButton[danger="true"]:hover {
    background-color: #e62929;
}

/* ===== プログレスバー ===== */
QProgressBar {
    border: none;
    border-radius: 4px;
    background-color: #2d2d2d;
    text-align: center;
    height: 8px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
        stop:0 #0078d4, stop:1 #00b4d8);
    border-radius: 4px;
}

/* ===== 入力フィールド ===== */
QTextEdit, QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #2d2d2d;
    border: 1px solid #404040;
    border-radius: 6px;
    padding: 6px;
    selection-background-color: #0078d4;
}
QTextEdit:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border-color: #0078d4;
}

/* ===== テーブル ===== */
QTableWidget {
    background-color: #1a1a1a;
    border: 1px solid #333333;
    border-radius: 8px;
    gridline-color: #333333;
}
QTableWidget::item {
    padding: 8px;
    border-bottom: 1px solid #2d2d2d;
}
QTableWidget::item:selected {
    background-color: rgba(0, 120, 212, 0.3);
}
QTableWidget::item:hover {
    background-color: #2d2d2d;
}
QHeaderView::section {
    background-color: #252525;
    border: none;
    border-bottom: 1px solid #404040;
    padding: 10px;
    font-weight: bold;
}

/* ===== グループボックス ===== */
QGroupBox {
    border: 1px solid #333333;
    border-radius: 8px;
    margin-top: 16px;
    padding: 16px;
    padding-top: 24px;
    background-color: rgba(45, 45, 45, 0.5);
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 8px;
    color: #0078d4;
    font-weight: bold;
}

/* ===== タブ ===== */
QTabWidget::pane {
    border: 1px solid #333333;
    border-radius: 8px;
    background-color: #1a1a1a;
    top: -1px;
}
QTabBar::tab {
    background-color: transparent;
    border: none;
    padding: 12px 24px;
    margin-right: 4px;
    border-radius: 6px 6px 0 0;
    color: #888888;
}
QTabBar::tab:hover {
    background-color: #2d2d2d;
    color: #e8e8e8;
}
QTabBar::tab:selected {
    background-color: #2d2d2d;
    color: #0078d4;
    font-weight: bold;
}

/* ===== スクロールバー ===== */
QScrollBar:vertical {
    background-color: transparent;
    width: 12px;
    margin: 4px;
}
QScrollBar::handle:vertical {
    background-color: #404040;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #505050;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
QScrollBar:horizontal {
    background-color: transparent;
    height: 12px;
    margin: 4px;
}
QScrollBar::handle:horizontal {
    background-color: #404040;
    border-radius: 4px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #505050;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0;
}

/* ===== スクロールエリア ===== */
QScrollArea {
    border: none;
    background-color: transparent;
}

/* ===== チェックボックス ===== */
QCheckBox {
    spacing: 8px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 2px solid #555555;
    background-color: #2d2d2d;
}
QCheckBox::indicator:hover {
    border-color: #0078d4;
}
QCheckBox::indicator:checked {
    background-color: #0078d4;
    border-color: #0078d4;
}

/* ===== スライダー ===== */
QSlider::groove:horizontal {
    height: 6px;
    background-color: #333333;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background-color: #0078d4;
    width: 18px;
    height: 18px;
    margin: -6px 0;
    border-radius: 9px;
}
QSlider::handle:horizontal:hover {
    background-color: #1a86d9;
}
QSlider::sub-page:horizontal {
    background-color: #0078d4;
    border-radius: 3px;
}

/* ===== ラベル ===== */
QLabel {
    color: #e8e8e8;
}
QLabel[heading="true"] {
    font-size: 18px;
    font-weight: bold;
    color: #ffffff;
}
QLabel[subtext="true"] {
    font-size: 11px;
    color: #888888;
}

/* ===== フレーム (カード) ===== */
QFrame {
    border-radius: 8px;
}
QFrame#card {
    background-color: #2d2d2d;
    border: 1px solid #333333;
    border-radius: 12px;
}
QFrame#card:hover {
    border-color: #0078d4;
    background-color: #353535;
}

/* ===== ツールチップ ===== */
QToolTip {
    background-color: #2d2d2d;
    color: #e8e8e8;
    border: 1px solid #404040;
    border-radius: 4px;
    padding: 6px;
}

/* ===== メッセージボックス ===== */
QMessageBox {
    background-color: #1a1a1a;
}
QMessageBox QLabel {
    color: #e8e8e8;
}
"""


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
