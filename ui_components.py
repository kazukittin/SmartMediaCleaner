"""
ui_components.py - SmartMediaCleaner Phase 2
カスタムUIウィジェット群
"""
import os
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem,
    QFrame, QPushButton, QSizePolicy, QScrollArea
)
from PySide6.QtCore import Qt, Signal, QThread, QObject, QRectF, QPointF
from PySide6.QtGui import QPixmap, QImage, QPainter, QWheelEvent, QMouseEvent, QKeyEvent

# サムネイルサイズ定数
THUMBNAIL_SIZE = 200


class ThumbnailLoader(QObject):
    """
    サムネイル画像を非同期で読み込むワーカー
    """
    loaded = Signal(str, QPixmap)  # file_path, pixmap
    finished = Signal()  # 完了シグナル

    def __init__(self, file_paths: list):
        super().__init__()
        self.file_paths = file_paths
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):
        """ファイルリストを順番に読み込み、シグナルを発行"""
        for path in self.file_paths:
            if not self._is_running:
                break
            try:
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    # サムネイルサイズにリサイズ (アスペクト比維持)
                    scaled = pixmap.scaled(
                        THUMBNAIL_SIZE, THUMBNAIL_SIZE,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                    self.loaded.emit(path, scaled)
            except Exception:
                pass  # 読み込み失敗は無視
        
        # 完了シグナルを発行
        self.finished.emit()


class ThumbnailWidget(QFrame):
    """
    サムネイル表示ウィジェット
    - 画像サムネイル
    - ファイル名
    - チェックボックス (削除対象選択)
    - ブレスコア表示 (オプション)
    - 顔検出数表示 (Phase 3)
    """
    checked_changed = Signal(str, bool)  # file_path, is_checked
    clicked = Signal(str)  # file_path (画像クリック時)
    
    def __init__(self, file_path: str, blur_score: float = None, face_count: int = None, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.blur_score = blur_score
        self.face_count = face_count
        
        self.setFrameStyle(QFrame.Box | QFrame.Plain)
        self.setLineWidth(1)
        self.setFixedSize(THUMBNAIL_SIZE + 20, THUMBNAIL_SIZE + 60)
        self.setFocusPolicy(Qt.StrongFocus)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)
        
        # サムネイル画像ラベル (プレースホルダー)
        self.image_label = QLabel()
        self.image_label.setFixedSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #2a2a2a; border: 1px solid #444;")
        self.image_label.setText("読込中...")
        self.image_label.mousePressEvent = self._on_image_click
        layout.addWidget(self.image_label)
        
        # ファイル名 (省略表示)
        filename = os.path.basename(file_path)
        if len(filename) > 20:
            filename = filename[:17] + "..."
        self.name_label = QLabel(filename)
        self.name_label.setToolTip(file_path)
        self.name_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.name_label)
        
        # 下部: チェックボックス + スコア + 顔数
        bottom_layout = QHBoxLayout()
        self.checkbox = QCheckBox("削除")
        self.checkbox.stateChanged.connect(self._on_check_changed)
        bottom_layout.addWidget(self.checkbox)
        
        if blur_score is not None:
            score_label = QLabel(f"ブレ:{blur_score:.0f}")
            score_label.setStyleSheet("color: #ff6b6b; font-size: 10px;")
            bottom_layout.addWidget(score_label)
        
        # 顔検出数バッジ (Phase 3)
        if face_count is not None and face_count > 0:
            face_label = QLabel(f"👤{face_count}")
            face_label.setStyleSheet("color: #4fc3f7; font-size: 10px;")
            face_label.setToolTip(f"検出された顔の数: {face_count}")
            bottom_layout.addWidget(face_label)
        
        bottom_layout.addStretch()
        layout.addLayout(bottom_layout)
    
    def set_pixmap(self, pixmap: QPixmap):
        """サムネイル画像をセット"""
        self.image_label.setPixmap(pixmap)
        self.image_label.setText("")
    
    def is_checked(self) -> bool:
        return self.checkbox.isChecked()
    
    def set_checked(self, checked: bool):
        self.checkbox.setChecked(checked)
    
    def _on_check_changed(self, state):
        # PySide6では state は Qt.CheckState enum または int
        # bool変換で確実に True/False を取得
        is_checked = self.checkbox.isChecked()
        self.checked_changed.emit(self.file_path, is_checked)
    
    def _on_image_click(self, event):
        self.clicked.emit(self.file_path)
    
    def keyPressEvent(self, event: QKeyEvent):
        """キーボード操作: Spaceでチェック切替"""
        if event.key() == Qt.Key_Space:
            self.checkbox.setChecked(not self.checkbox.isChecked())
        else:
            super().keyPressEvent(event)
    
    def focusInEvent(self, event):
        """フォーカス時のスタイル"""
        self.setStyleSheet("ThumbnailWidget { border: 2px solid #4a9eff; }")
        super().focusInEvent(event)
    
    def focusOutEvent(self, event):
        """フォーカス解除時のスタイル"""
        self.setStyleSheet("")
        super().focusOutEvent(event)


class SyncGraphicsView(QGraphicsView):
    """
    同期可能なQGraphicsView
    ズームとパンを他のビューと連動させる
    """
    sync_transform = Signal(float, QPointF)  # scale, center_point
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        self._zoom_factor = 1.0
        self._is_syncing = False  # 無限ループ防止フラグ
    
    def wheelEvent(self, event: QWheelEvent):
        """マウスホイールでズーム"""
        if self._is_syncing:
            return
            
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor
        
        if event.angleDelta().y() > 0:
            factor = zoom_in_factor
        else:
            factor = zoom_out_factor
        
        self._zoom_factor *= factor
        # ズーム範囲制限
        self._zoom_factor = max(0.1, min(10.0, self._zoom_factor))
        
        self.setTransform(self.transform().scale(factor, factor))
        
        # 同期シグナル発行
        center = self.mapToScene(self.viewport().rect().center())
        self.sync_transform.emit(self._zoom_factor, center)
    
    def apply_sync(self, zoom: float, center: QPointF):
        """他のビューからの同期を適用"""
        self._is_syncing = True
        
        # ズームレベルを合わせる
        current_zoom = self._zoom_factor
        if abs(zoom - current_zoom) > 0.001:
            factor = zoom / current_zoom
            self._zoom_factor = zoom
            self.setTransform(self.transform().scale(factor, factor))
        
        # 中心位置を合わせる
        self.centerOn(center)
        
        self._is_syncing = False
    
    def scrollContentsBy(self, dx, dy):
        """スクロール時にも同期"""
        super().scrollContentsBy(dx, dy)
        if not self._is_syncing:
            center = self.mapToScene(self.viewport().rect().center())
            self.sync_transform.emit(self._zoom_factor, center)


class SyncImageWidget(QWidget):
    """
    2枚の画像を並べて同期ズーム・スクロールで比較するウィジェット
    Phase 4: EXIF表示、ヒストグラム、ピーキング機能追加
    """
    select_left = Signal(str)   # 左画像を選択(削除対象に)
    select_right = Signal(str)  # 右画像を選択(削除対象に)
    close_requested = Signal()  # 閉じるボタン
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.left_path = ""
        self.right_path = ""
        self.display_mode = "normal"  # normal, histogram, peaking
        
        layout = QVBoxLayout(self)
        
        # ヘッダー (閉じるボタン + モード切替)
        header = QHBoxLayout()
        header.addWidget(QLabel("🔍 Pro比較モード"))
        header.addStretch()
        
        # 表示モード切替ボタン
        self.mode_normal_btn = QPushButton("📷 通常")
        self.mode_normal_btn.setCheckable(True)
        self.mode_normal_btn.setChecked(True)
        self.mode_normal_btn.clicked.connect(lambda: self._set_mode("normal"))
        header.addWidget(self.mode_normal_btn)
        
        self.mode_hist_btn = QPushButton("📊 ヒストグラム")
        self.mode_hist_btn.setCheckable(True)
        self.mode_hist_btn.clicked.connect(lambda: self._set_mode("histogram"))
        header.addWidget(self.mode_hist_btn)
        
        self.mode_peak_btn = QPushButton("🔴 ピーキング")
        self.mode_peak_btn.setCheckable(True)
        self.mode_peak_btn.clicked.connect(lambda: self._set_mode("peaking"))
        header.addWidget(self.mode_peak_btn)
        
        close_btn = QPushButton("✕ 閉じる")
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)
        layout.addLayout(header)
        
        # 画像表示エリア
        images_layout = QHBoxLayout()
        
        # 左画像
        left_container = QVBoxLayout()
        self.left_view = SyncGraphicsView()
        self.left_scene = QGraphicsScene()
        self.left_view.setScene(self.left_scene)
        self.left_item = None
        left_container.addWidget(self.left_view)
        
        self.left_label = QLabel()
        self.left_label.setAlignment(Qt.AlignCenter)
        self.left_label.setWordWrap(True)
        self.left_label.setMaximumHeight(100)
        left_container.addWidget(self.left_label)
        
        self.left_btn = QPushButton("← こちらを削除対象に")
        self.left_btn.setProperty("danger", True)
        self.left_btn.clicked.connect(lambda: self.select_left.emit(self.left_path))
        left_container.addWidget(self.left_btn)
        
        images_layout.addLayout(left_container)
        
        # 右画像
        right_container = QVBoxLayout()
        self.right_view = SyncGraphicsView()
        self.right_scene = QGraphicsScene()
        self.right_view.setScene(self.right_scene)
        self.right_item = None
        right_container.addWidget(self.right_view)
        
        self.right_label = QLabel()
        self.right_label.setAlignment(Qt.AlignCenter)
        self.right_label.setWordWrap(True)
        self.right_label.setMaximumHeight(100)
        right_container.addWidget(self.right_label)
        
        self.right_btn = QPushButton("こちらを削除対象に →")
        self.right_btn.setProperty("danger", True)
        self.right_btn.clicked.connect(lambda: self.select_right.emit(self.right_path))
        right_container.addWidget(self.right_btn)
        
        images_layout.addLayout(right_container)
        layout.addLayout(images_layout)
        
        # 同期接続
        self.left_view.sync_transform.connect(self._sync_to_right)
        self.right_view.sync_transform.connect(self._sync_to_left)
    
    def _set_mode(self, mode: str):
        """表示モード切替"""
        self.display_mode = mode
        self.mode_normal_btn.setChecked(mode == "normal")
        self.mode_hist_btn.setChecked(mode == "histogram")
        self.mode_peak_btn.setChecked(mode == "peaking")
        self._refresh_images()
    
    def set_images(self, left_path: str, right_path: str):
        """比較する2枚の画像をセット"""
        self.left_path = left_path
        self.right_path = right_path
        self._refresh_images()
        self._update_labels()
    
    def _refresh_images(self):
        """現在のモードで画像を更新"""
        for path, scene, view, attr_name in [
            (self.left_path, self.left_scene, self.left_view, "left_item"),
            (self.right_path, self.right_scene, self.right_view, "right_item")
        ]:
            scene.clear()
            if not path:
                continue
            
            pixmap = self._get_display_pixmap(path)
            if not pixmap.isNull():
                item = QGraphicsPixmapItem(pixmap)
                scene.addItem(item)
                view.fitInView(item, Qt.KeepAspectRatio)
                setattr(self, attr_name, item)
    
    def _get_display_pixmap(self, path: str) -> QPixmap:
        """モードに応じた画像を取得"""
        if self.display_mode == "normal":
            return QPixmap(path)
        elif self.display_mode == "peaking":
            return self._create_peaking_image(path)
        elif self.display_mode == "histogram":
            return self._create_histogram_image(path)
        return QPixmap(path)
    
    def _create_peaking_image(self, path: str) -> QPixmap:
        """エッジ強調 (ピーキング) 画像を作成"""
        try:
            import cv2
            import numpy as np
            
            with open(path, "rb") as f:
                data = np.frombuffer(f.read(), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if img is None:
                return QPixmap(path)
            
            # グレースケール変換してエッジ検出
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            
            # 元画像にエッジを赤でオーバーレイ
            overlay = img.copy()
            overlay[edges > 0] = [0, 0, 255]  # 赤色
            
            # 少し透過させてブレンド
            result = cv2.addWeighted(img, 0.7, overlay, 0.3, 0)
            
            # QPixmapに変換
            h, w, ch = result.shape
            result_rgb = cv2.cvtColor(result, cv2.COLOR_BGR2RGB)
            q_img = QImage(result_rgb.data, w, h, ch * w, QImage.Format_RGB888)
            return QPixmap.fromImage(q_img)
        except Exception:
            return QPixmap(path)
    
    def _create_histogram_image(self, path: str) -> QPixmap:
        """ヒストグラム付き画像を作成"""
        try:
            import cv2
            import numpy as np
            
            with open(path, "rb") as f:
                data = np.frombuffer(f.read(), dtype=np.uint8)
            img = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if img is None:
                return QPixmap(path)
            
            h, w = img.shape[:2]
            
            # ヒストグラム計算 (RGB各チャンネル)
            hist_h = 100
            hist_img = np.zeros((hist_h, w, 3), dtype=np.uint8)
            
            colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
            for i, col in enumerate(colors):
                hist = cv2.calcHist([img], [i], None, [256], [0, 256])
                cv2.normalize(hist, hist, 0, hist_h, cv2.NORM_MINMAX)
                for x in range(256):
                    x_pos = int(x * w / 256)
                    cv2.line(hist_img, (x_pos, hist_h), (x_pos, hist_h - int(hist[x])), col, 1)
            
            # 元画像の下にヒストグラムを結合
            combined = np.vstack([img, hist_img])
            
            # QPixmapに変換
            ch, cw = combined.shape[:2]
            combined_rgb = cv2.cvtColor(combined, cv2.COLOR_BGR2RGB)
            q_img = QImage(combined_rgb.data, cw, ch, 3 * cw, QImage.Format_RGB888)
            return QPixmap.fromImage(q_img)
        except Exception:
            return QPixmap(path)
    
    def _update_labels(self):
        """ファイル情報 + EXIF をラベルに表示"""
        for path, label in [(self.left_path, self.left_label), 
                            (self.right_path, self.right_label)]:
            if path and os.path.exists(path):
                info_lines = [os.path.basename(path)]
                
                # サイズ
                size = os.path.getsize(path)
                info_lines.append(f"📁 {self._format_size(size)}")
                
                # EXIF情報
                exif = self._get_exif(path)
                if exif:
                    info_lines.append(exif)
                
                label.setText("\n".join(info_lines))
            else:
                label.setText("")
    
    def _get_exif(self, path: str) -> str:
        """EXIF情報を取得"""
        try:
            from PIL import Image
            from PIL.ExifTags import TAGS
            
            img = Image.open(path)
            exif_data = img._getexif()
            if not exif_data:
                return ""
            
            info = []
            tag_names = {
                "DateTimeOriginal": "📅",
                "ISOSpeedRatings": "ISO",
                "ExposureTime": "⏱",
                "FNumber": "F"
            }
            
            for tag_id, value in exif_data.items():
                tag = TAGS.get(tag_id, tag_id)
                if tag in tag_names:
                    if tag == "ExposureTime" and isinstance(value, tuple):
                        value = f"{value[0]}/{value[1]}s"
                    elif tag == "FNumber" and isinstance(value, tuple):
                        value = f"{value[0]/value[1]:.1f}"
                    info.append(f"{tag_names[tag]} {value}")
            
            return " | ".join(info[:4]) if info else ""
        except Exception:
            return ""
    
    def _format_size(self, size: int) -> str:
        """ファイルサイズを読みやすい形式に"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def _sync_to_right(self, zoom: float, center: QPointF):
        """左から右へ同期"""
        self.right_view.apply_sync(zoom, center)
    
    def _sync_to_left(self, zoom: float, center: QPointF):
        """右から左へ同期"""
        self.left_view.apply_sync(zoom, center)


class FlowLayout(QVBoxLayout):
    """
    疑似フローレイアウト
    QScrollArea内で使用し、ウィジェットを横に並べて折り返す
    (PySide6にはFlowLayoutがないため、QHBoxLayoutを複数段使用)
    """
    def __init__(self, parent=None, items_per_row=4):
        super().__init__(parent)
        self.items_per_row = items_per_row
        self.current_row = None
        self.current_count = 0
        self.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._start_new_row()
    
    def _start_new_row(self):
        self.current_row = QHBoxLayout()
        self.current_row.setSpacing(10)
        self.current_row.setAlignment(Qt.AlignLeft)
        self.addLayout(self.current_row)
        self.current_count = 0
    
    def add_widget(self, widget):
        if self.current_count >= self.items_per_row:
            # 前の行にストレッチを追加
            if self.current_row:
                self.current_row.addStretch()
            self._start_new_row()
        self.current_row.addWidget(widget)
        self.current_count += 1
    
    def finalize(self):
        """最後の行にストレッチを追加してレイアウトを完成"""
        if self.current_row:
            self.current_row.addStretch()
        # 垂直方向にもストレッチを追加して下部の余白を確保
        self.addStretch()
