"""
results_view.py - SmartMediaCleaner Phase 2
スキャン結果表示画面 (タブ構成)
"""
import os
from pathlib import Path
from send2trash import send2trash
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QScrollArea,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QCheckBox,
    QHeaderView, QMessageBox, QFrame, QStackedWidget, QSizePolicy,
    QAbstractItemView, QSlider, QListView, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, Signal, Slot, QThread, QSize
from PySide6.QtGui import QPixmap, QIcon

from ui_components import (
    ThumbnailWidget, SyncImageWidget, ThumbnailLoader, FlowLayout, THUMBNAIL_SIZE
)

class ResultsView(QWidget):
    """
    スキャン結果を表示するメイン画面
    - ブレ画像タブ
    - 類似画像タブ
    - 重複動画タブ
    - 下部アクションバー
    """
    back_requested = Signal()  # スキャン画面に戻る

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scan_results = {}
        self.thumbnail_widgets = {}  # path -> ThumbnailWidget
        self.selected_files = set()  # 削除対象に選択されたファイルパス
        
        # サムネイルローダー
        self.loader_thread = None
        self.loader = None
        
        self._init_ui()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # ヘッダー
        header = QHBoxLayout()
        back_btn = QPushButton("← スキャン画面に戻る")
        back_btn.clicked.connect(self.back_requested.emit)
        header.addWidget(back_btn)
        header.addStretch()
        layout.addLayout(header)

        # サマリーバナー
        self.summary_banner = QFrame()
        self.summary_banner.setStyleSheet("background-color: #0078d4; border-radius: 8px; margin: 10px 0;")
        self.summary_banner.hide()
        banner_layout = QHBoxLayout(self.summary_banner)
        
        icon_label = QLabel("✨")
        icon_label.setStyleSheet("font-size: 24px;")
        banner_layout.addWidget(icon_label)
        
        self.summary_text = QLabel("スキャン完了！")
        self.summary_text.setStyleSheet("font-weight: bold; color: white; font-size: 14px;")
        banner_layout.addWidget(self.summary_text)
        
        banner_layout.addStretch()
        layout.addWidget(self.summary_banner)

        
        # メインコンテンツ (タブ or 比較モード)
        self.content_stack = QStackedWidget()
        
        # タブウィジェット
        self.tabs = QTabWidget()
        self.blur_tab = self._create_blur_tab()
        self.similar_tab = self._create_similar_tab()
        self.video_tab = self._create_video_tab()
        
        self.tabs.addTab(self.blur_tab, "ブレ画像")
        self.tabs.addTab(self.similar_tab, "類似画像")
        self.tabs.addTab(self.video_tab, "重複動画")
        
        self.content_stack.addWidget(self.tabs)
        
        # 比較モードウィジェット
        self.compare_widget = SyncImageWidget()
        self.compare_widget.close_requested.connect(self._close_compare_mode)
        self.compare_widget.select_left.connect(self._add_to_delete)
        self.compare_widget.select_right.connect(self._add_to_delete)
        self.content_stack.addWidget(self.compare_widget)
        
        layout.addWidget(self.content_stack)
        
        # 下部アクションバー
        self.action_bar = self._create_action_bar()
        layout.addWidget(self.action_bar)
    
    def _create_blur_tab(self) -> QWidget:
        """
        ブレ画像タブ (仮想スクロール対応)
        Phase 5: QListWidget で大規模対応
        """
        container = QWidget()
        layout = QVBoxLayout(container)
        
        # ソート切替コントロール
        sort_layout = QHBoxLayout()
        sort_layout.addWidget(QLabel("🔄 並び順:"))
        
        self.blur_sort_asc_btn = QPushButton("ブレ小→大 ▲")
        self.blur_sort_asc_btn.setCheckable(True)
        self.blur_sort_asc_btn.setChecked(True)
        self.blur_sort_asc_btn.clicked.connect(lambda: self._set_blur_sort(ascending=True))
        sort_layout.addWidget(self.blur_sort_asc_btn)
        
        self.blur_sort_desc_btn = QPushButton("ブレ大→小 ▼")
        self.blur_sort_desc_btn.setCheckable(True)
        self.blur_sort_desc_btn.clicked.connect(lambda: self._set_blur_sort(ascending=False))
        sort_layout.addWidget(self.blur_sort_desc_btn)
        
        sort_layout.addStretch()
        layout.addLayout(sort_layout)
        
        # QListWidget (仮想スクロール対応)
        self.blur_list = QListWidget()
        self.blur_list.setViewMode(QListWidget.IconMode)
        self.blur_list.setIconSize(QSize(THUMBNAIL_SIZE, THUMBNAIL_SIZE))
        self.blur_list.setSpacing(10)
        self.blur_list.setResizeMode(QListWidget.Adjust)
        self.blur_list.setSelectionMode(QListWidget.MultiSelection)
        self.blur_list.setUniformItemSizes(True)  # パフォーマンス向上
        self.blur_list.setMovement(QListWidget.Static)
        self.blur_list.setFlow(QListWidget.LeftToRight)
        self.blur_list.setWrapping(True)
        self.blur_list.itemSelectionChanged.connect(self._on_blur_list_selection_changed)
        self.blur_list.itemDoubleClicked.connect(self._on_blur_item_double_clicked)
        
        layout.addWidget(self.blur_list)
        return container
    
    def _create_similar_tab(self) -> QWidget:
        """類似画像タブ (グループ表示 + 閾値スライダー)"""
        container = QWidget()
        layout = QVBoxLayout(container)
        
        # Phase 4: 類似度閾値スライダー
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(QLabel("🎚️ 類似度閾値:"))
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setMinimum(0)
        self.threshold_slider.setMaximum(20)
        self.threshold_slider.setValue(0)  # 0 = 完全一致のみ
        self.threshold_slider.setTickInterval(5)
        self.threshold_slider.setTickPosition(QSlider.TicksBelow)
        self.threshold_slider.valueChanged.connect(self._on_threshold_changed)
        threshold_layout.addWidget(self.threshold_slider, 1)
        
        self.threshold_label = QLabel("0 (完全一致)")
        self.threshold_label.setFixedWidth(100)
        threshold_layout.addWidget(self.threshold_label)
        layout.addLayout(threshold_layout)
        
        # スクロールエリア
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        self.similar_content = QWidget()
        self.similar_layout = QVBoxLayout(self.similar_content)
        scroll.setWidget(self.similar_content)
        
        layout.addWidget(scroll)
        return container
    
    def _create_video_tab(self) -> QWidget:
        """重複動画タブ (テーブル表示)"""
        container = QWidget()
        layout = QVBoxLayout(container)
        
        self.video_table = QTableWidget()
        self.video_table.setColumnCount(4)
        self.video_table.setHorizontalHeaderLabels(["選択", "ファイル名", "サイズ", "パス"])
        self.video_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.video_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.video_table.setAlternatingRowColors(True)
        
        layout.addWidget(self.video_table)
        return container
    
    def _create_action_bar(self) -> QFrame:
        """下部アクションバー"""
        bar = QFrame()
        bar.setFrameStyle(QFrame.StyledPanel)
        bar.setStyleSheet("background-color: #2a2a2a; padding: 10px;")
        
        layout = QHBoxLayout(bar)
        
        # ステータス
        self.status_label = QLabel("選択中: 0枚 / 合計サイズ: 0 B")
        layout.addWidget(self.status_label)
        
        layout.addStretch()
        
        # 全選択/解除
        self.select_all_btn = QPushButton("すべて選択")
        self.select_all_btn.clicked.connect(self._select_all)
        layout.addWidget(self.select_all_btn)
        
        self.deselect_all_btn = QPushButton("すべて解除")
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        layout.addWidget(self.deselect_all_btn)
        
        # 削除ボタン
        self.delete_btn = QPushButton("🗑 選択したファイルをゴミ箱へ移動")
        self.delete_btn.setStyleSheet("background-color: #c0392b; color: white; padding: 8px 16px;")
        self.delete_btn.clicked.connect(self._delete_selected)
        layout.addWidget(self.delete_btn)
        
        return bar
    
    def load_results(self, results: dict):
        """スキャン結果を読み込んで表示"""
        self.scan_results = results
        self.selected_files.clear()
        self.thumbnail_widgets.clear()
        
        # 既存のローダーを停止
        self._stop_loader()
        
        # 各タブをクリア
        self.blur_list.clear()
        self._clear_layout(self.similar_layout)
        self.video_table.setRowCount(0)
        
        # サマリーバナー更新
        self._update_summary_banner(results)

        
        # 画像パスを収集
        all_image_paths = []
        
        # メタデータ取得用
        image_metadata = results.get("image_metadata", {})
        
        # ブレ画像タブ (Phase 5: QListWidget で仮想スクロール対応)
        blur_images = results.get("blur_images", [])
        
        # データを正規化してソート用リストを作成
        normalized_blur = []
        for item in blur_images:
            if isinstance(item, tuple) and len(item) >= 3:
                path, blur_score, face_count = item[0], item[1], item[2]
            elif isinstance(item, (list, tuple)) and len(item) >= 1:
                path = item[0]
                meta = image_metadata.get(path, {})
                blur_score = meta.get("blur_score", 0)
                face_count = meta.get("face_count", 0)
            elif isinstance(item, str):
                path = item
                meta = image_metadata.get(path, {})
                blur_score = meta.get("blur_score", 0)
                face_count = meta.get("face_count", 0)
            else:
                continue
            normalized_blur.append((path, blur_score or 0, face_count or 0))
        
        # ブレスコア昇順でソート (スコアが低い=ブレが酷い を先頭に)
        normalized_blur.sort(key=lambda x: x[1])
        
        # ブレ画像データを保存 (選択時の参照用)
        self.blur_items_data = {}
        
        for path, blur_score, face_count in normalized_blur:
            # QListWidgetItem を作成
            item = QListWidgetItem()
            basename = os.path.basename(path)
            label = f"{basename}\nブレ:{int(blur_score)}"
            if face_count > 0:
                label += f" 👤{face_count}"
            item.setText(label)
            item.setData(Qt.UserRole, path)  # パスをデータとして保存
            item.setSizeHint(QSize(THUMBNAIL_SIZE + 20, THUMBNAIL_SIZE + 50))
            
            self.blur_list.addItem(item)
            self.blur_items_data[path] = {"blur_score": blur_score, "face_count": face_count}
            all_image_paths.append(path)
        
        # 類似画像タブ (Phase 3形式: phash -> [(path, blur_score, face_count, size), ...])
        similar_groups = results.get("similar_groups", {})
        for group_hash, group_items in similar_groups.items():
            group_widget = self._create_group_widget(group_hash, group_items, image_metadata)
            self.similar_layout.addWidget(group_widget)
            # パスを抽出
            for item in group_items:
                if isinstance(item, tuple):
                    all_image_paths.append(item[0])
                else:
                    all_image_paths.append(item)
        self.similar_layout.addStretch()
        
        # 重複動画タブ (Phase 3形式: key -> [(path, duration), ...])
        dup_videos = results.get("duplicate_videos", {})
        row = 0
        for group_hash, group_items in dup_videos.items():
            for item in group_items:
                # Phase 3形式かPhase 1形式か判定
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    path, duration = item[0], item[1]
                elif isinstance(item, (list, tuple)) and len(item) == 1:
                    path = item[0]
                    duration = None
                elif isinstance(item, str):
                    path = item
                    duration = None
                else:
                    continue
                
                self.video_table.insertRow(row)
                
                # チェックボックス
                checkbox = QCheckBox()
                checkbox.stateChanged.connect(
                    lambda state, p=path, cb=checkbox: self._on_video_check_changed(p, cb.isChecked())
                )
                self.video_table.setCellWidget(row, 0, checkbox)
                
                # ファイル情報
                filename = os.path.basename(path)
                size = os.path.getsize(path) if os.path.exists(path) else 0
                size_str = self._format_size(size)
                
                # 長さ情報 (Phase 3)
                if duration is not None:
                    duration_str = f"{duration:.1f}秒"
                    filename = f"{filename} ({duration_str})"
                
                self.video_table.setItem(row, 1, QTableWidgetItem(filename))
                self.video_table.setItem(row, 2, QTableWidgetItem(size_str))
                self.video_table.setItem(row, 3, QTableWidgetItem(path))
                
                row += 1
        
        # タブタイトル更新
        blur_count = len(blur_images)
        self.tabs.setTabText(0, f"ブレ画像 ({blur_count})")
        self.tabs.setTabText(1, f"類似画像 ({len(similar_groups)}グループ)")
        self.tabs.setTabText(2, f"重複動画 ({len(dup_videos)}グループ)")
        
        # 非同期サムネイル読み込み開始
        if all_image_paths:
            self._start_thumbnail_loading(all_image_paths)
        
        self._update_status()
    
    def _create_group_widget(self, group_hash: str, group_items: list, image_metadata: dict = None) -> QWidget:
        """
        類似画像グループを表示するウィジェット
        Phase 3: スマートセレクト機能付き
        """
        group = QFrame()
        group.setFrameStyle(QFrame.Box)
        group.setStyleSheet("border: 1px solid #444; padding: 5px; margin: 5px;")
        
        layout = QVBoxLayout(group)
        
        # データ形式を正規化
        normalized_items = []
        for item in group_items:
            if isinstance(item, (list, tuple)) and len(item) >= 4:
                # Phase 3形式: (path, blur_score, face_count, size)
                path, blur_score, face_count, size = item[0], item[1], item[2], item[3]
                normalized_items.append((path, blur_score or 0, face_count or 0, size))
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                # 2要素の場合: (path, something) - pathとmetadataから取得
                path = item[0]
                if isinstance(path, str):
                    meta = image_metadata.get(path, {}) if image_metadata else {}
                    normalized_items.append((path, meta.get("blur_score", 0), meta.get("face_count", 0), meta.get("size", 0)))
            elif isinstance(item, str):
                # Phase 1形式: pathのみ
                path = item
                meta = image_metadata.get(path, {}) if image_metadata else {}
                normalized_items.append((path, meta.get("blur_score", 0), meta.get("face_count", 0), meta.get("size", 0)))
        
        # ベストショットを選択 (削除しない1枚)
        best_path = self._select_best_shot(normalized_items)
        
        # グループヘッダー
        header = QLabel(f"グループ: {group_hash[:8]}... ({len(normalized_items)}枚)")
        header.setStyleSheet("font-weight: bold; border: none;")
        layout.addWidget(header)
        
        # サムネイル横並び (スクロール可能)
        scroll = QScrollArea()
        scroll.setFixedHeight(THUMBNAIL_SIZE + 80)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        
        thumb_container = QWidget()
        thumb_layout = QHBoxLayout(thumb_container)
        thumb_layout.setSpacing(10)
        
        for path, blur_score, face_count, size in normalized_items:
            widget = ThumbnailWidget(path, blur_score=blur_score, face_count=face_count)
            widget.checked_changed.connect(self._on_check_changed)
            widget.clicked.connect(self._on_thumbnail_clicked)
            thumb_layout.addWidget(widget)
            self.thumbnail_widgets[path] = widget
            
            # スマートセレクト: ベストショット以外は削除候補にチェック
            if path != best_path:
                widget.set_checked(True)
                self.selected_files.add(path)
        
        thumb_layout.addStretch()
        scroll.setWidget(thumb_container)
        layout.addWidget(scroll)
        
        return group
    
    def _select_best_shot(self, items: list) -> str:
        """
        類似画像グループから「残すべき1枚」を選択する
        
        Args:
            items: [(path, blur_score, face_count, size), ...]
            
        Returns:
            残すべき画像のパス
        
        優先順位:
        1. 顔の数 (多い方が優先)
        2. ブレの少なさ (blur_score が高い方が鮮明)
        3. ファイルサイズ (大きい方が高画質)
        """
        if not items:
            return ""
        
        # ソート: 顔数降順 → blur_score降順 → サイズ降順
        sorted_items = sorted(
            items,
            key=lambda x: (x[2], x[1], x[3]),  # face_count, blur_score, size
            reverse=True
        )
        
        return sorted_items[0][0]  # ベストショットのパスを返す
    
    def _start_thumbnail_loading(self, paths: list):
        """
        サムネイルの非同期読み込みを開始
        Phase 5: 表示範囲のみ読み込み (遅延描画)
        """
        # 既存ローダー停止
        self._stop_loader()
        
        # 全パスを保存
        self.pending_thumbnail_paths = list(paths)
        self.loaded_thumbnails = set()
        
        # 最初のバッチを読み込み (可視範囲 + 余裕)
        initial_batch = paths[:50] if len(paths) > 50 else paths
        self._load_thumbnail_batch(initial_batch)
        
        # スクロールイベントで追加読み込み
        self.blur_list.verticalScrollBar().valueChanged.connect(self._on_blur_scroll)
    
    def _on_blur_scroll(self):
        """スクロール時に可視範囲のサムネイルを読み込み"""
        if not hasattr(self, 'pending_thumbnail_paths'):
            return
        
        # 可視範囲のアイテムを取得
        visible_rect = self.blur_list.viewport().rect()
        to_load = []
        
        for i in range(self.blur_list.count()):
            item = self.blur_list.item(i)
            item_rect = self.blur_list.visualItemRect(item)
            
            if visible_rect.intersects(item_rect):
                path = item.data(Qt.UserRole)
                if path and path not in self.loaded_thumbnails:
                    to_load.append(path)
        
        # バッチ読み込み
        if to_load:
            self._load_thumbnail_batch(to_load[:20])  # 最大20件ずつ
    
    def _load_thumbnail_batch(self, paths: list):
        """サムネイルをバッチで読み込み"""
        if not paths:
            return
        
        # 読み込み済みを除外
        paths_to_load = [p for p in paths if p not in self.loaded_thumbnails]
        if not paths_to_load:
            return
        
        # 読み込み済みとしてマーク
        for p in paths_to_load:
            self.loaded_thumbnails.add(p)
        
        # ローダーを開始
        self.loader_thread = QThread(self)  # 親をセットしてクラッシュ防止
        self.loader = ThumbnailLoader(paths_to_load)
        self.loader.moveToThread(self.loader_thread)
        
        # シグナル接続
        self.loader_thread.started.connect(self.loader.run)
        self.loader.loaded.connect(self._on_thumbnail_loaded)
        
        # スレッド終了処理
        self.loader.finished.connect(self.loader_thread.quit)
        self.loader.finished.connect(self.loader.deleteLater)
        self.loader_thread.finished.connect(self._on_loader_finished)
        
        self.loader_thread.start()
    
    def _on_loader_finished(self):
        """ローダースレッド完了時"""
        self.loader = None
        self.loader_thread = None
    
    def _stop_loader(self):
        """サムネイルローダーを停止"""
        if self.loader:
            self.loader.stop()
        if self.loader_thread and self.loader_thread.isRunning():
            self.loader_thread.quit()
            self.loader_thread.wait(3000)  # 最大3秒待機
            if self.loader_thread and self.loader_thread.isRunning():
                self.loader_thread.terminate()  # 強制終了
    
    @Slot(str, QPixmap)
    def _on_thumbnail_loaded(self, path: str, pixmap: QPixmap):
        """サムネイル読み込み完了時"""
        # ThumbnailWidget (類似画像タブ用)
        if path in self.thumbnail_widgets:
            self.thumbnail_widgets[path].set_pixmap(pixmap)
        
        # QListWidget (ブレ画像タブ用)
        for i in range(self.blur_list.count()):
            item = self.blur_list.item(i)
            if item and item.data(Qt.UserRole) == path:
                # アイコンとして設定
                item.setIcon(QIcon(pixmap))
                break
    
    def _on_check_changed(self, path: str, checked: bool):
        """チェックボックス変更時"""
        if checked:
            self.selected_files.add(path)
        else:
            self.selected_files.discard(path)
        self._update_status()
    
    def _on_video_check_changed(self, path: str, checked: bool):
        """動画テーブルのチェックボックス変更時"""
        if checked:
            self.selected_files.add(path)
        else:
            self.selected_files.discard(path)
        self._update_status()
    
    def _on_blur_list_selection_changed(self):
        """ブレ画像リストの選択変更時"""
        # 選択されたアイテムのパスを取得
        for item in self.blur_list.selectedItems():
            path = item.data(Qt.UserRole)
            if path:
                self.selected_files.add(path)
        
        # 選択解除されたアイテムを削除
        selected_paths = {item.data(Qt.UserRole) for item in self.blur_list.selectedItems()}
        blur_paths = {self.blur_list.item(i).data(Qt.UserRole) for i in range(self.blur_list.count())}
        for path in blur_paths - selected_paths:
            self.selected_files.discard(path)
        
        self._update_status()
    
    def _on_blur_item_double_clicked(self, item):
        """ブレ画像リストのダブルクリック時"""
        path = item.data(Qt.UserRole)
        if path:
            # 隣の画像と比較モードへ
            row = self.blur_list.row(item)
            if row + 1 < self.blur_list.count():
                next_path = self.blur_list.item(row + 1).data(Qt.UserRole)
                self._open_compare_mode(path, next_path)
            elif row > 0:
                prev_path = self.blur_list.item(row - 1).data(Qt.UserRole)
                self._open_compare_mode(prev_path, path)
    
    def _set_blur_sort(self, ascending: bool):
        """ブレ画像のソート順を切り替え"""
        self.blur_sort_asc_btn.setChecked(ascending)
        self.blur_sort_desc_btn.setChecked(not ascending)
        
        if not hasattr(self, 'blur_items_data') or not self.blur_items_data:
            return
        
        # ソートを実行
        items_with_score = [
            (path, data.get("blur_score", 0), data.get("face_count", 0))
            for path, data in self.blur_items_data.items()
        ]
        items_with_score.sort(key=lambda x: x[1], reverse=not ascending)
        
        # リストを再構築
        self.blur_list.clear()
        for path, blur_score, face_count in items_with_score:
            item = QListWidgetItem()
            basename = os.path.basename(path)
            label = f"{basename}\nブレ:{int(blur_score)}"
            if face_count > 0:
                label += f" 👤{face_count}"
            item.setText(label)
            item.setData(Qt.UserRole, path)
            item.setSizeHint(QSize(THUMBNAIL_SIZE + 20, THUMBNAIL_SIZE + 50))
            self.blur_list.addItem(item)
        
        # サムネイル再読み込み
        paths = [path for path, _, _ in items_with_score]
        self._start_thumbnail_loading(paths)
    
    def _on_thumbnail_clicked(self, path: str):
        """サムネイルクリック時 - 比較モードを開く"""
        # 同じグループ内の別の画像を探す
        similar_groups = self.scan_results.get("similar_groups", {})
        for group_hash, paths in similar_groups.items():
            if path in paths:
                # 同グループ内で別の画像を選ぶ
                other_paths = [p for p in paths if p != path]
                if other_paths:
                    self._open_compare_mode(path, other_paths[0])
                    return
        
        # 類似グループにない場合はブレ画像タブから
        blur_images = self.scan_results.get("blur_images", [])
        if path in blur_images:
            idx = blur_images.index(path)
            if idx + 1 < len(blur_images):
                self._open_compare_mode(path, blur_images[idx + 1])
            elif idx > 0:
                self._open_compare_mode(blur_images[idx - 1], path)
    
    def _open_compare_mode(self, left_path: str, right_path: str):
        """比較モードを開く"""
        # メタデータからブレスコアを取得
        image_metadata = self.scan_results.get("image_metadata", {})
        
        left_meta = image_metadata.get(left_path, {})
        right_meta = image_metadata.get(right_path, {})
        
        left_blur = left_meta.get("blur_score")
        right_blur = right_meta.get("blur_score")
        
        self.compare_widget.set_images(left_path, right_path, left_blur, right_blur)
        self.content_stack.setCurrentWidget(self.compare_widget)
    
    def _close_compare_mode(self):
        """比較モードを閉じる"""
        self.content_stack.setCurrentWidget(self.tabs)
    
    def _add_to_delete(self, path: str):
        """削除対象に追加"""
        if path in self.thumbnail_widgets:
            self.thumbnail_widgets[path].set_checked(True)
        self.selected_files.add(path)
        self._update_status()
    
    def _select_all(self):
        """すべて選択"""
        for path, widget in self.thumbnail_widgets.items():
            widget.set_checked(True)
            self.selected_files.add(path)
        
        # 動画テーブル
        for row in range(self.video_table.rowCount()):
            checkbox = self.video_table.cellWidget(row, 0)
            if checkbox:
                checkbox.setChecked(True)
        
        self._update_status()
    
    def _deselect_all(self):
        """すべて解除"""
        for path, widget in self.thumbnail_widgets.items():
            widget.set_checked(False)
        
        for row in range(self.video_table.rowCount()):
            checkbox = self.video_table.cellWidget(row, 0)
            if checkbox:
                checkbox.setChecked(False)
        
        self.selected_files.clear()
        self._update_status()
    
    def _update_status(self):
        """ステータスバー更新"""
        count = len(self.selected_files)
        total_size = 0
        for path in self.selected_files:
            if os.path.exists(path):
                total_size += os.path.getsize(path)
        
        size_str = self._format_size(total_size)
        self.status_label.setText(f"選択中: {count}枚 / 合計サイズ: {size_str}")
    
    def _delete_selected(self):
        """選択ファイルをゴミ箱へ移動"""
        if not self.selected_files:
            QMessageBox.information(self, "情報", "ファイルが選択されていません。")
            return
        
        count = len(self.selected_files)
        reply = QMessageBox.question(
            self, "確認",
            f"{count}個のファイルをゴミ箱へ移動しますか？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        success = 0
        failed = 0
        deleted_paths = []
        
        for path in list(self.selected_files):
            try:
                # Windowsパスを正規化 (スラッシュの混在を解消)
                normalized_path = os.path.normpath(path)
                send2trash(normalized_path)
                success += 1
                deleted_paths.append(path)
                
                # サムネイルウィジェットから削除
                if path in self.thumbnail_widgets:
                    widget = self.thumbnail_widgets.pop(path)
                    widget.deleteLater()
                self.selected_files.discard(path)
            except Exception as e:
                failed += 1
                print(f"削除エラー: {path} - {e}")
        
        # 動画テーブルから削除されたファイルを除去
        self._remove_from_video_table(deleted_paths)
        
        # 類似画像グループの空グループを削除
        self._cleanup_empty_groups()
        
        self._update_status()
        QMessageBox.information(
            self, "完了",
            f"ゴミ箱へ移動: {success}個\n失敗: {failed}個"
        )
    
    def _remove_from_video_table(self, deleted_paths: list):
        """動画テーブルから削除されたパスの行を除去"""
        rows_to_remove = []
        for row in range(self.video_table.rowCount()):
            path_item = self.video_table.item(row, 3)
            if path_item and path_item.text() in deleted_paths:
                rows_to_remove.append(row)
        
        # 後ろから削除 (インデックスずれ防止)
        for row in reversed(rows_to_remove):
            self.video_table.removeRow(row)
    
    def _cleanup_empty_groups(self):
        """類似画像タブの空グループ (1枚以下) を削除"""
        # similar_layoutから子ウィジェットを走査
        widgets_to_remove = []
        for i in range(self.similar_layout.count()):
            item = self.similar_layout.itemAt(i)
            if item and item.widget():
                group_widget = item.widget()
                # グループ内のサムネイル数をカウント
                remaining_count = self._count_group_thumbnails(group_widget)
                if remaining_count <= 1:
                    widgets_to_remove.append(group_widget)
        
        # 削除
        for widget in widgets_to_remove:
            widget.deleteLater()
    
    def _count_group_thumbnails(self, group_widget) -> int:
        """グループウィジェット内の残りサムネイル数をカウント"""
        count = 0
        # QFrameの中のQScrollAreaを探す
        for child in group_widget.findChildren(ThumbnailWidget):
            if child.isVisible() and child.file_path in self.thumbnail_widgets:
                count += 1
        return count
    
    def _format_size(self, size: int) -> str:
        """ファイルサイズを読みやすい形式に"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    
    def _clear_layout(self, layout):
        """レイアウト内のウィジェットをクリア"""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())
    
    def closeEvent(self, event):
        """クローズ時にローダーを停止"""
        self._stop_loader()
        super().closeEvent(event)
    
    def _update_summary_banner(self, results):
        """スキャン結果サマリーを表示"""
        blur_count = len(results.get("blur_images", []))
        sim_groups = len(results.get("similar_groups", {}))
        dup_videos = len(results.get("duplicate_videos", {}))
        
        # 簡易的な削減可能サイズ計算 (正確ではないが目安として)
        # ブレ画像: 全て
        # 類似画像: 各グループ - 1枚
        # 動画: 各グループ - 1つ
        
        # メタデータを活用
        meta = results.get("image_metadata", {})
        total_savable = 0
        
        # ブレ画像のサイズ
        for item in results.get("blur_images", []):
            path = item[0] if isinstance(item, (list, tuple)) else item
            total_savable += meta.get(path, {}).get("size", 0)
            
        # 類似画像の削減候補サイズ
        for group in results.get("similar_groups", {}).values():
             for i, item in enumerate(group):
                 if i > 0: # 1枚残す前提
                    path = item[0] if isinstance(item, (list, tuple)) else item
                    total_savable += meta.get(path, {}).get("size", 0)

        size_str = self._format_size(total_savable)
        
        if total_savable > 0:
            self.summary_text.setText(
                f"スキャン完了！ 不要なファイルを削除して、最大 {size_str} の空き容量を確保できます。\n"
                f"• ブレ画像: {blur_count}枚  • 類似グループ: {sim_groups}  • 重複動画: {dup_videos}"
            )
            self.summary_banner.show()
        else:
            self.summary_text.setText("問題は見つかりませんでした！ ライブラリはきれいです。")
            self.summary_banner.show()

    def _on_threshold_changed(self, value: int):
        """類似度閾値スライダー変更時"""
        if value == 0:
            self.threshold_label.setText("0 (完全一致)")
        else:
            self.threshold_label.setText(f"{value} (類似)")
        
        # 再グルーピング
        self._recalculate_groups(value)
    
    def _recalculate_groups(self, threshold: int):
        """pHashのハミング距離に基づいて類似画像を再グルーピング"""
        if not self.scan_results:
            return
        
        image_metadata = self.scan_results.get("image_metadata", {})
        
        # pHashを持つ画像を収集
        images_with_phash = []
        for path, meta in image_metadata.items():
            if os.path.exists(path):
                # DBからpHashを取得する必要があるが、ここでは簡易実装
                images_with_phash.append((path, meta))
        
        if threshold == 0:
            # 完全一致モード: 元のグルーピングを復元
            original_groups = self.scan_results.get("similar_groups", {})
            self._rebuild_similar_groups(original_groups, image_metadata)
        else:
            # ハミング距離によるグルーピング
            try:
                import imagehash
                from PIL import Image
                
                # pHashを計算しながらグルーピング
                phash_map = {}
                for path, meta in images_with_phash:
                    try:
                        img = Image.open(path)
                        phash = imagehash.phash(img)
                        phash_map[path] = (phash, meta)
                    except:
                        pass
                
                # ハミング距離でグルーピング
                grouped = {}
                used = set()
                
                paths = list(phash_map.keys())
                for i, p1 in enumerate(paths):
                    if p1 in used:
                        continue
                    
                    group = [(p1, phash_map[p1][1].get("blur_score", 0),
                             phash_map[p1][1].get("face_count", 0),
                             phash_map[p1][1].get("size", 0))]
                    used.add(p1)
                    
                    for p2 in paths[i+1:]:
                        if p2 in used:
                            continue
                        
                        # ハミング距離計算
                        dist = phash_map[p1][0] - phash_map[p2][0]
                        if dist <= threshold:
                            group.append((p2, phash_map[p2][1].get("blur_score", 0),
                                         phash_map[p2][1].get("face_count", 0),
                                         phash_map[p2][1].get("size", 0)))
                            used.add(p2)
                    
                    if len(group) > 1:
                        group_key = f"group_{i}"
                        grouped[group_key] = group
                
                self._rebuild_similar_groups(grouped, image_metadata)
                
            except ImportError:
                pass
    
    def _rebuild_similar_groups(self, groups: dict, image_metadata: dict):
        """類似画像グループを再構築"""
        # 既存のサムネイルウィジェットをクリア (similar_tab分のみ)
        similar_widgets = []
        for path in list(self.thumbnail_widgets.keys()):
            # 画像がsimilar_groupsに含まれているかチェック
            widget = self.thumbnail_widgets.get(path)
            if widget and hasattr(widget, 'parent') and widget.parent():
                parent = widget.parent()
                while parent:
                    if parent == self.similar_content:
                        similar_widgets.append(path)
                        break
                    parent = parent.parent() if hasattr(parent, 'parent') else None
        
        # similar_layoutをクリア
        self._clear_layout(self.similar_layout)
        
        # ウィジェット参照を削除
        for path in similar_widgets:
            if path in self.thumbnail_widgets:
                del self.thumbnail_widgets[path]
        
        self.selected_files.clear()
        
        # 新しいグループを構築
        all_image_paths = []
        for group_hash, group_items in groups.items():
            group_widget = self._create_group_widget(group_hash, group_items, image_metadata)
            self.similar_layout.addWidget(group_widget)
            
            for item in group_items:
                if isinstance(item, tuple):
                    all_image_paths.append(item[0])
                else:
                    all_image_paths.append(item)
        
        self.similar_layout.addStretch()
        
        # タブタイトル更新
        self.tabs.setTabText(1, f"類似画像 ({len(groups)}グループ)")
        
        # サムネイル再読み込み
        if all_image_paths:
            self._start_thumbnail_loading(all_image_paths)
        
        self._update_status()
