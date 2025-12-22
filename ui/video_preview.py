"""
video_preview.py - SmartMediaCleaner Phase 4
動画プレビュー機能 (ホバー再生、シークバー)
"""
import cv2
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QSlider, QFrame
)
from PySide6.QtCore import Qt, Signal, QTimer, QSize
from PySide6.QtGui import QPixmap, QImage


class VideoPreviewWidget(QWidget):
    """
    動画プレビューウィジェット
    - ホバー時にフレーム送りでプレビュー
    - シークバーで任意位置へジャンプ
    """
    
    def __init__(self, video_path: str, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.cap = None
        self.frame_count = 0
        self.fps = 0
        self.current_frame = 0
        self.is_playing = False
        
        self._init_ui()
        self._init_video()
        
        # 再生タイマー (5fps = 200ms間隔)
        self.timer = QTimer()
        self.timer.timeout.connect(self._next_frame)
    
    def _init_ui(self):
        """UI初期化"""
        self.setFixedSize(320, 240)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # プレビュー画像
        self.preview_label = QLabel()
        self.preview_label.setFixedSize(320, 180)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("""
            background-color: #1a1a1a;
            border-radius: 8px;
        """)
        layout.addWidget(self.preview_label)
        
        # コントロールバー
        control_layout = QHBoxLayout()
        control_layout.setSpacing(8)
        
        # 再生/停止ボタン
        self.play_btn = QPushButton("▶")
        self.play_btn.setFixedSize(32, 32)
        self.play_btn.clicked.connect(self.toggle_play)
        control_layout.addWidget(self.play_btn)
        
        # シークバー
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setMinimum(0)
        self.seek_slider.valueChanged.connect(self._on_seek)
        control_layout.addWidget(self.seek_slider)
        
        # 時間表示
        self.time_label = QLabel("00:00")
        self.time_label.setFixedWidth(50)
        control_layout.addWidget(self.time_label)
        
        layout.addLayout(control_layout)
    
    def _init_video(self):
        """動画ファイルを開く"""
        try:
            self.cap = cv2.VideoCapture(self.video_path)
            if self.cap.isOpened():
                self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
                self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
                self.seek_slider.setMaximum(max(1, self.frame_count - 1))
                
                # 最初のフレームを表示
                self._show_frame(0)
        except Exception as e:
            print(f"Video open error: {e}")
    
    def _show_frame(self, frame_idx: int):
        """指定フレームを表示"""
        if not self.cap or not self.cap.isOpened():
            return
        
        try:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = self.cap.read()
            if ret and frame is not None:
                # BGR -> RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame_rgb.shape
                
                # QImageに変換
                bytes_per_line = ch * w
                q_img = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
                
                # ラベルサイズにスケール
                pixmap = QPixmap.fromImage(q_img).scaled(
                    self.preview_label.size(),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
                self.preview_label.setPixmap(pixmap)
                
                # 時間更新
                self.current_frame = frame_idx
                current_sec = frame_idx / self.fps if self.fps > 0 else 0
                self.time_label.setText(f"{int(current_sec//60):02d}:{int(current_sec%60):02d}")
        except Exception:
            pass
    
    def _next_frame(self):
        """次のフレームへ (自動再生用)"""
        next_idx = self.current_frame + int(self.fps / 5)  # 5fps相当でスキップ
        if next_idx >= self.frame_count:
            next_idx = 0  # ループ
        
        self.seek_slider.blockSignals(True)
        self.seek_slider.setValue(next_idx)
        self.seek_slider.blockSignals(False)
        self._show_frame(next_idx)
    
    def _on_seek(self, value):
        """シークバー操作"""
        self._show_frame(value)
    
    def toggle_play(self):
        """再生/停止切替"""
        if self.is_playing:
            self.stop_preview()
        else:
            self.start_preview()
    
    def start_preview(self):
        """プレビュー再生開始"""
        self.is_playing = True
        self.play_btn.setText("⏸")
        self.timer.start(200)  # 5fps
    
    def stop_preview(self):
        """プレビュー停止"""
        self.is_playing = False
        self.play_btn.setText("▶")
        self.timer.stop()
    
    def enterEvent(self, event):
        """マウスエンター時に再生開始"""
        self.start_preview()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """マウスリーブ時に停止"""
        self.stop_preview()
        super().leaveEvent(event)
    
    def closeEvent(self, event):
        """クリーンアップ"""
        self.timer.stop()
        if self.cap:
            self.cap.release()
        super().closeEvent(event)
    
    def __del__(self):
        """デストラクタ"""
        self.timer.stop()
        if self.cap:
            self.cap.release()


class VideoThumbnailWidget(QFrame):
    """
    動画サムネイルウィジェット (テーブル用)
    ホバーでプレビューポップアップ表示
    """
    clicked = Signal(str)
    
    def __init__(self, video_path: str, duration: float = None, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.duration = duration
        self.preview_popup = None
        
        self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(60)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        
        # サムネイル
        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(80, 45)
        self.thumb_label.setStyleSheet("background-color: #2d2d2d; border-radius: 4px;")
        self._load_thumbnail()
        layout.addWidget(self.thumb_label)
        
        # 情報
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        import os
        filename = os.path.basename(video_path)
        self.name_label = QLabel(filename)
        self.name_label.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(self.name_label)
        
        if duration:
            dur_str = f"{int(duration//60):02d}:{int(duration%60):02d}"
            self.dur_label = QLabel(f"⏱ {dur_str}")
            self.dur_label.setProperty("subtext", True)
            info_layout.addWidget(self.dur_label)
        
        layout.addLayout(info_layout, 1)
    
    def _load_thumbnail(self):
        """最初のフレームをサムネイルとして読み込み"""
        try:
            cap = cv2.VideoCapture(self.video_path)
            if cap.isOpened():
                ret, frame = cap.read()
                if ret:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    h, w, ch = frame_rgb.shape
                    q_img = QImage(frame_rgb.data, w, h, ch * w, QImage.Format_RGB888)
                    pixmap = QPixmap.fromImage(q_img).scaled(
                        self.thumb_label.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    self.thumb_label.setPixmap(pixmap)
            cap.release()
        except Exception:
            pass
    
    def enterEvent(self, event):
        """ホバー時にプレビューポップアップ"""
        if not self.preview_popup:
            self.preview_popup = VideoPreviewWidget(self.video_path)
            self.preview_popup.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        
        # ウィジェット右側に表示
        global_pos = self.mapToGlobal(self.rect().topRight())
        self.preview_popup.move(global_pos.x() + 10, global_pos.y())
        self.preview_popup.show()
        self.preview_popup.start_preview()
        
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """ホバー解除でポップアップ非表示"""
        if self.preview_popup:
            self.preview_popup.stop_preview()
            self.preview_popup.hide()
        super().leaveEvent(event)
    
    def mousePressEvent(self, event):
        self.clicked.emit(self.video_path)
        super().mousePressEvent(event)
