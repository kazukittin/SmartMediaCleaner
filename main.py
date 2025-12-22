"""
main.py - SmartMediaCleaner Phase 2
GUIエントリーポイント (スキャン画面 + 結果画面の切り替え)
"""
import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QPushButton, QLabel, QFileDialog, 
    QProgressBar, QTextEdit, QDoubleSpinBox, QGroupBox,
    QStackedWidget, QCheckBox, QDialog, QDialogButtonBox
)
from PySide6.QtCore import QThread, Slot, Qt
from scanner import ScanWorker
from results_view import ResultsView



class SettingsDialog(QDialog):
    """スキャン設定ダイアログ"""
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("スキャン設定")
        self.settings = settings.copy()  # キャンセル時に影響しないようにコピー
        
        layout = QVBoxLayout(self)
        
        # 設定項目
        form_group = QGroupBox("基本設定")
        form_layout = QVBoxLayout()
        
        # ブレ判定
        blur_layout = QHBoxLayout()
        blur_layout.addWidget(QLabel("ブレ判定閾値:"))
        self.blur_spin = QDoubleSpinBox()
        self.blur_spin.setRange(0, 5000)
        self.blur_spin.setValue(self.settings.get("blur_threshold", 100.0))
        self.blur_spin.setToolTip("この値より低いスコアの画像をブレと判定")
        blur_layout.addWidget(self.blur_spin)
        form_layout.addLayout(blur_layout)
        
        # サブフォルダ
        self.subfolder_check = QCheckBox("サブフォルダを含める")
        self.subfolder_check.setChecked(self.settings.get("recursive", True))
        self.subfolder_check.setToolTip("サブフォルダ内のファイルも再帰的にスキャン")
        form_layout.addWidget(self.subfolder_check)
        
        form_group.setLayout(form_layout)
        layout.addWidget(form_group)
        
        # OK/Cancelボタン
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_settings(self):
        """設定値を取得"""
        return {
            "blur_threshold": self.blur_spin.value(),
            "recursive": self.subfolder_check.isChecked()
        }


class ScanPage(QWidget):
    """スキャン設定・実行画面"""
    
    scan_finished = Slot(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.layout = QVBoxLayout(self)
        
        # 1. フォルダ選択エリア
        folder_layout = QHBoxLayout()
        self.path_label = QLabel("フォルダが選択されていません")
        self.path_label.setWordWrap(True)
        self.select_btn = QPushButton("フォルダを選択")
        self.select_btn.clicked.connect(self.select_folder)
        
        folder_layout.addWidget(self.select_btn)
        folder_layout.addWidget(self.path_label, 1)
        self.layout.addLayout(folder_layout)

        # 2. 設定エリア (ボタンのみ)
        # 設定値の初期化
        self.settings = {
            "blur_threshold": 100.0,
            "recursive": True
        }
        
        settings_layout = QHBoxLayout()
        
        self.settings_btn = QPushButton("⚙ 設定")
        self.settings_btn.setFixedSize(100, 36)
        self.settings_btn.clicked.connect(self.open_settings_dialog)
        settings_layout.addWidget(self.settings_btn)
        
        settings_layout.addStretch()
        self.layout.addLayout(settings_layout)

        # 2.5 ガイド表示 (フォルダ未選択時)
        self.guide_widget = QWidget()
        guide_layout = QVBoxLayout(self.guide_widget)
        
        guide_title = QLabel("ステップ 1: スキャンするフォルダを選んでください")
        guide_title.setAlignment(Qt.AlignCenter)
        guide_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #0078d4; margin-bottom: 20px;")
        
        guide_desc = QLabel(
            "写真や動画が保存されているフォルダを選択すると、\n"
            "自動的にスキャンして不要なファイルを見つけ出します。\n\n"
            "• 📸 ピンボケ写真\n"
            "• 🖼 似ている写真 (連写など)\n"
            "• 🎥 全く同じ動画"
        )
        guide_desc.setAlignment(Qt.AlignCenter)
        guide_desc.setStyleSheet("font-size: 14px; line-height: 1.6; color: #cccccc;")
        
        guide_layout.addWidget(guide_title)
        guide_layout.addWidget(guide_desc)
        guide_layout.addStretch()
        
        self.layout.addWidget(self.guide_widget)

        # 3. 実行エリア
        self.run_btn = QPushButton("🚀 スキャン開始")
        self.run_btn.setEnabled(False)
        self.run_btn.hide()  # 最初は隠す
        self.run_btn.setStyleSheet("padding: 12px; font-size: 16px; font-weight: bold;")
        self.layout.addWidget(self.run_btn)

        self.progress_bar = QProgressBar()
        self.layout.addWidget(self.progress_bar)

        self.status_label = QLabel("待機中")
        self.layout.addWidget(self.status_label)

        # 4. ログ表示エリア
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(150)
        self.layout.addWidget(self.log_area)
        
        self.layout.addStretch()

        # 内部変数
        self.target_folder = ""
        self.thread = None
        self.worker = None

    @Slot()
    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "スキャンするフォルダを選択")
        if folder:
            self.target_folder = folder
            self.path_label.setText(folder)
            self.run_btn.setEnabled(True)
            self.status_label.setText("準備完了")
            self.guide_widget.hide()  # ガイドを非表示
            self.run_btn.show()       # 実行ボタンを表示


    @Slot()
    def open_settings_dialog(self):
        """設定ダイアログを開く"""
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == QDialog.Accepted:
            self.settings = dialog.get_settings()
            self.status_label.setText("設定を更新しました")

    def start_scan(self, on_finished_callback):
        """スキャンを開始"""
        if not self.target_folder:
            return

        self.run_btn.setEnabled(False)
        self.select_btn.setEnabled(False)
        self.log_area.clear()
        self.status_label.setText("スキャン初期化中...")

        # Workerスレッドのセットアップ
        self.thread = QThread()
        self.worker = ScanWorker(
            self.target_folder, 
            self.settings["blur_threshold"],
            recursive=self.settings["recursive"]
        )
        self.worker.moveToThread(self.thread)

        # シグナル接続
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(on_finished_callback)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.progress.connect(self.on_progress)
        self.worker.log.connect(self.on_log)

        # スレッド開始
        self.thread.start()

    @Slot(int, int, str)
    def on_progress(self, current, total, filename):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(f"処理中 ({current}/{total}): {filename}")

    @Slot(str)
    def on_log(self, message):
        self.log_area.append(f"[LOG] {message}")

    @Slot()
    def reset_ui(self):
        """UIをリセット (スキャン完了後)"""
        self.status_label.setText("スキャン完了")
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.run_btn.setEnabled(True)
        self.select_btn.setEnabled(True)

    def cleanup(self):
        """スレッドの終了処理"""
        try:
            if self.worker:
                self.worker.stop()
            if self.thread and self.thread.isRunning():
                self.thread.quit()
                self.thread.wait(2000)
                if self.thread.isRunning():
                    self.thread.terminate()
        except RuntimeError:
            # C++オブジェクトが既に削除されている場合は無視
            pass



class MainWindow(QMainWindow):
    """メインウィンドウ - スキャン画面と結果画面の切り替え"""
    
    def __init__(self):
        super().__init__()

        self.setWindowTitle("SmartMediaCleaner")
        self.resize(900, 700)
        
        # スタックウィジェットで画面切り替え
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        
        # スキャン画面
        self.scan_page = ScanPage()
        self.scan_page.run_btn.clicked.connect(self.start_scan)
        self.stack.addWidget(self.scan_page)
        
        # 結果画面
        self.results_view = ResultsView()
        self.results_view.back_requested.connect(self.show_scan_page)
        self.stack.addWidget(self.results_view)
        
        # 初期表示
        self.stack.setCurrentWidget(self.scan_page)

    @Slot()
    def start_scan(self):
        """スキャン開始"""
        self.scan_page.start_scan(self.on_scan_finished)

    @Slot(dict)
    def on_scan_finished(self, results):
        """スキャン完了時 - 結果画面に切り替え"""
        self.scan_page.reset_ui()
        
        # ログに結果サマリーを表示
        scanned = results.get("scanned_count", 0)
        blur_count = len(results.get("blur_images", []))
        sim_groups = len(results.get("similar_groups", {}))
        dup_videos = len(results.get("duplicate_videos", {}))
        
        self.scan_page.log_area.append(
            f"\n=== スキャン結果 ===\n"
            f"走査ファイル数: {scanned}\n"
            f"ブレ画像検出数: {blur_count}\n"
            f"類似画像グループ: {sim_groups}\n"
            f"重複動画グループ: {dup_videos}"
        )
        
        # 結果画面に切り替え
        self.results_view.load_results(results)
        self.stack.setCurrentWidget(self.results_view)

    @Slot()
    def show_scan_page(self):
        """スキャン画面に戻る"""
        self.stack.setCurrentWidget(self.scan_page)

    def closeEvent(self, event):
        """アプリ終了時のクリーンアップ"""
        self.scan_page.cleanup()
        event.accept()



def main():
    app = QApplication(sys.argv)
    
    # Modern Fluent Design風スタイルシート (Phase 4)
    app.setStyleSheet("""
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
    """)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
