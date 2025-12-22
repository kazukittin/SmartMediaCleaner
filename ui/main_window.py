"""
main_window.py - SmartMediaCleaner
統合されたメインウィンドウ (スキャン + 結果表示)
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, 
    QHBoxLayout, QPushButton, QLabel, QFileDialog, 
    QProgressBar, QDoubleSpinBox, QGroupBox,
    QCheckBox, QDialog, QDialogButtonBox
)
from PySide6.QtCore import QThread, Slot, Qt
from core.scanner import ScanWorker
from .results_view import ResultsView


class SettingsDialog(QDialog):
    """スキャン設定ダイアログ"""
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("スキャン設定")
        self.settings = settings.copy()
        
        layout = QVBoxLayout(self)
        
        form_group = QGroupBox("基本設定")
        form_layout = QVBoxLayout()
        
        # ブレ判定閾値
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
        
        # 表示設定
        display_group = QGroupBox("表示設定")
        display_layout = QVBoxLayout()
        
        # 並び順
        sort_layout = QHBoxLayout()
        sort_layout.addWidget(QLabel("ブレ画像の並び順:"))
        self.sort_asc_check = QCheckBox("ブレ順 (い度い順)")
        self.sort_asc_check.setChecked(self.settings.get("blur_sort_asc", True))
        sort_layout.addWidget(self.sort_asc_check)
        display_layout.addLayout(sort_layout)
        
        display_group.setLayout(display_layout)
        layout.addWidget(display_group)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_settings(self):
        return {
            "blur_threshold": self.blur_spin.value(),
            "recursive": self.subfolder_check.isChecked(),
            "blur_sort_asc": self.sort_asc_check.isChecked()
        }


class MainWindow(QMainWindow):
    """統合メインウィンドウ - スキャン操作と結果表示が一体化"""
    
    def __init__(self):
        super().__init__()

        self.setWindowTitle("SmartMediaCleaner")
        self.resize(1000, 750)
        
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        
        # ヘッダー: パス表示 + ボタン (右上)
        header_layout = QHBoxLayout()
        
        self.path_label = QLabel("フォルダが選択されていません")
        self.path_label.setWordWrap(True)
        self.path_label.setStyleSheet("color: #888888;")
        header_layout.addWidget(self.path_label, 1)
        
        self.run_btn = QPushButton("🚀 スキャン開始")
        self.run_btn.setEnabled(False)
        self.run_btn.clicked.connect(self.start_scan)
        header_layout.addWidget(self.run_btn)
        
        self.select_btn = QPushButton("📁 フォルダを選択")
        self.select_btn.clicked.connect(self.select_folder)
        header_layout.addWidget(self.select_btn)
        
        self.settings_btn = QPushButton("⚙ 設定")
        self.settings_btn.clicked.connect(self.open_settings_dialog)
        header_layout.addWidget(self.settings_btn)
        
        main_layout.addLayout(header_layout)

        # 設定値
        self.settings = {
            "blur_threshold": 100.0,
            "recursive": True,
            "blur_sort_asc": True
        }

        # ステータス + プログレスバー
        status_layout = QHBoxLayout()
        self.status_label = QLabel("待機中")
        self.status_label.setStyleSheet("font-size: 14px; color: #aaaaaa;")
        status_layout.addWidget(self.status_label)
        
        self.progress_bar = QProgressBar()
        status_layout.addWidget(self.progress_bar, 1)
        main_layout.addLayout(status_layout)

        # 結果表示 (タブ: ブレ画像, 類似画像, 重複動画, ログ)
        self.results_view = ResultsView()
        main_layout.addWidget(self.results_view, 1)  # stretch=1

        # 内部状態
        self.target_folder = ""
        self.thread = None
        self.worker = None

    @Slot()
    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "スキャンするフォルダを選択")
        if folder:
            self.target_folder = folder
            self.path_label.setText(folder)
            self.path_label.setStyleSheet("color: #e8e8e8;")
            self.run_btn.setEnabled(True)
            self.status_label.setText("準備完了")

    @Slot()
    def open_settings_dialog(self):
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec() == QDialog.Accepted:
            self.settings = dialog.get_settings()
            self.status_label.setText("設定を更新しました")

    @Slot()
    def start_scan(self):
        if not self.target_folder:
            return

        self.run_btn.setEnabled(False)
        self.select_btn.setEnabled(False)
        self.results_view.log_area.clear()
        self.status_label.setText("スキャン初期化中...")
        
        # ログタブに切り替え
        self.results_view.tabs.setCurrentWidget(self.results_view.log_tab)

        self.thread = QThread()
        self.worker = ScanWorker(
            self.target_folder, 
            self.settings["blur_threshold"],
            recursive=self.settings["recursive"]
        )
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_scan_finished)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.worker.progress.connect(self.on_progress)
        self.worker.log.connect(self.on_log)

        self.thread.start()

    @Slot(int, int, str)
    def on_progress(self, current, total, filename):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(f"処理中 ({current}/{total}): {filename}")

    @Slot(str)
    def on_log(self, message):
        self.results_view.append_log(f"[LOG] {message}")

    @Slot(dict)
    def on_scan_finished(self, results):
        self.status_label.setText("スキャン完了")
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.run_btn.setEnabled(True)
        self.select_btn.setEnabled(True)
        
        scanned = results.get("scanned_count", 0)
        blur_count = len(results.get("blur_images", []))
        sim_groups = len(results.get("similar_groups", {}))
        dup_videos = len(results.get("duplicate_videos", {}))
        
        self.results_view.append_log(
            f"\n=== スキャン結果 ===\n"
            f"走査ファイル数: {scanned}\n"
            f"ブレ画像検出数: {blur_count}\n"
            f"類似画像グループ: {sim_groups}\n"
            f"重複動画グループ: {dup_videos}"
        )
        
        # 結果を読み込み、ソート適用、ブレ画像タブに切り替え
        self.results_view.load_results(results)
        self.results_view._set_blur_sort(ascending=self.settings.get("blur_sort_asc", True))
        self.results_view.tabs.setCurrentIndex(0)

    def cleanup(self):
        try:
            if self.worker:
                self.worker.stop()
            if self.thread and self.thread.isRunning():
                self.thread.quit()
                self.thread.wait(2000)
                if self.thread.isRunning():
                    self.thread.terminate()
        except RuntimeError:
            pass

    def closeEvent(self, event):
        self.cleanup()
        event.accept()
