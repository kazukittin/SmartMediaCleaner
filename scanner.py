import os
import cv2
import imagehash
from PIL import Image
import xxhash
import hashlib
import numpy as np
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QThread
from typing import List, Dict, Set, Tuple, Optional
from db_manager import DBManager

# システムフォルダや除外すべき拡張子
EXCLUDED_DIRS = {'.git', 'System Volume Information', '$RECYCLE.BIN', '__pycache__'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv'}

# 顔検出用カスケード分類器のパス
FACE_CASCADE_PATH = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'


class ScanWorker(QObject):
    """
    スキャン処理をバックグラウンドで実行するワーカークラス。
    Phase 5: 大規模対応（4万ファイル対応）
    """
    progress = Signal(int, int, str)  # current, total, filename
    finished = Signal(dict)           # results
    log = Signal(str)                 # log messages

    def __init__(self, folder_path: str, blur_threshold: float = 100.0, recursive: bool = True):
        super().__init__()
        self.folder_path = folder_path
        self.blur_threshold = blur_threshold
        self.recursive = recursive
        self.db = DBManager()
        self._is_running = True
        
        # 顔検出用カスケード分類器の初期化
        self.face_cascade = cv2.CascadeClassifier(FACE_CASCADE_PATH)

    def stop(self):
        self._is_running = False

    def run(self):
        """スキャン処理のメインループ"""
        self.log.emit("スキャンを開始します...")
        
        # 1. ファイルリストの収集
        files_to_scan = []
        
        if self.recursive:
            # サブフォルダを含めて再帰スキャン
            for root, dirs, files in os.walk(self.folder_path):
                # 除外ディレクトリのフィルタリング
                dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS]
                
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext in IMAGE_EXTENSIONS or ext in VIDEO_EXTENSIONS:
                        files_to_scan.append(os.path.join(root, file))
        else:
            # 直下のみスキャン
            for file in os.listdir(self.folder_path):
                filepath = os.path.join(self.folder_path, file)
                if os.path.isfile(filepath):
                    ext = os.path.splitext(file)[1].lower()
                    if ext in IMAGE_EXTENSIONS or ext in VIDEO_EXTENSIONS:
                        files_to_scan.append(filepath)

        total_files = len(files_to_scan)
        self.log.emit(f"対象ファイル数: {total_files}")
        
        results = {
            "scanned_count": 0,
            "blur_images": [],       # [(path, blur_score, face_count), ...]
            "similar_groups": {},    # phash -> [(path, blur_score, face_count, size), ...]
            "duplicate_videos": {},  # key -> [(path, duration), ...]
            "image_metadata": {}     # path -> {blur_score, face_count, size}
        }

        # 類似画像グルーピング用の一時辞書
        phash_map: Dict[str, List[Tuple[str, float, int, int]]] = {}  # phash -> [(path, blur, faces, size), ...]
        # 動画グルーピング: (duration_bucket, frame_hash) -> [(path, duration), ...]
        video_content_map: Dict[Tuple[int, str], List[Tuple[str, float]]] = {}

        processed_count = 0
        
        for file_path in files_to_scan:
            if not self._is_running:
                break

            processed_count += 1
            self.progress.emit(processed_count, total_files, os.path.basename(file_path))

            try:
                stat = os.stat(file_path)
                mtime = stat.st_mtime
                size = stat.st_size

                # キャッシュ確認
                cached_data = self.db.get_cache(file_path)
                
                # キャッシュが有効ならそれを使う
                if self.db.is_cache_valid(file_path, mtime, size):
                    phash = cached_data.get('phash')
                    video_hash = cached_data.get('video_hash')
                    blur_score = cached_data.get('blur_score')
                    face_count = cached_data.get('face_count')
                    video_duration = cached_data.get('video_duration')
                    video_frame_hash = cached_data.get('video_frame_hash')
                else:
                    # 新規計算
                    phash = None
                    video_hash = None
                    blur_score = None
                    face_count = None
                    video_duration = None
                    video_frame_hash = None
                    
                    if file_path.lower().endswith(tuple(IMAGE_EXTENSIONS)):
                        blur_score = self._calculate_blur_score(file_path)
                        phash = self._calculate_phash(file_path)
                        face_count = self._detect_faces(file_path)
                    elif file_path.lower().endswith(tuple(VIDEO_EXTENSIONS)):
                        video_hash = self._calculate_video_hash(file_path, size)
                        video_duration, video_frame_hash = self._analyze_video_content(file_path)

                    # DB更新
                    self.db.upsert_cache(file_path, mtime, size, blur_score, phash, video_hash,
                                         face_count, video_duration, video_frame_hash)

                # 結果の集計
                if blur_score is not None:
                    results["image_metadata"][file_path] = {
                        "blur_score": blur_score,
                        "face_count": face_count or 0,
                        "size": size
                    }
                    if blur_score < self.blur_threshold:
                        results["blur_images"].append((file_path, blur_score, face_count or 0))
                
                if phash:
                    if phash not in phash_map:
                        phash_map[phash] = []
                    phash_map[phash].append((file_path, blur_score or 0, face_count or 0, size))
                
                # 動画の内容一致判定 (duration bucket + frame hash)
                if video_duration is not None and video_frame_hash:
                    # 1秒単位でグループ化
                    duration_bucket = int(video_duration)
                    key = (duration_bucket, video_frame_hash)
                    if key not in video_content_map:
                        video_content_map[key] = []
                    video_content_map[key].append((file_path, video_duration))

            except Exception as e:
                self.log.emit(f"エラー ({os.path.basename(file_path)}): {str(e)}")
        
        # 重複のみ抽出してresultsに格納
        for k, v in phash_map.items():
            if len(v) > 1:
                results["similar_groups"][k] = v
        
        # 動画: 内容一致で重複判定
        for key, v in video_content_map.items():
            if len(v) > 1:
                # キーをstring化
                group_key = f"duration_{key[0]}s_{key[1][:8]}"
                results["duplicate_videos"][group_key] = v
        
        results["scanned_count"] = processed_count
        self.db.close()
        self.finished.emit(results)

    def _calculate_blur_score(self, image_path: str) -> float:
        """
        ラプラシアンフィルタによるブレスコア計算。
        値が小さいほどブレている可能性が高い。
        """
        try:
            img = self._load_image_cv2(image_path, grayscale=True)
            if img is None:
                return 1000.0
            return cv2.Laplacian(img, cv2.CV_64F).var()
        except Exception:
            return 1000.0

    def _calculate_phash(self, image_path: str) -> str:
        """
        ImageHashによる知覚ハッシュ計算
        """
        try:
            img = Image.open(image_path)
            return str(imagehash.phash(img))
        except Exception:
            return ""

    def _detect_faces(self, image_path: str) -> int:
        """
        OpenCV Haar Cascadeによる顔検出
        高速化のため480px幅に縮小して処理
        """
        try:
            img = self._load_image_cv2(image_path, grayscale=True)
            if img is None:
                return 0
            
            # 高速化: 480px幅に縮小
            height, width = img.shape[:2]
            if width > 480:
                scale = 480 / width
                img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
            
            # 顔検出
            faces = self.face_cascade.detectMultiScale(
                img,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30)
            )
            
            return len(faces)
        except Exception:
            return 0

    def _calculate_video_hash(self, video_path: str, file_size: int) -> str:
        """
        動画ハッシュ: ファイルサイズ + 先頭64KBのMD5
        (Phase 1互換)
        """
        try:
            chunk_size = 64 * 1024
            hasher = hashlib.md5()
            hasher.update(str(file_size).encode('utf-8'))
            
            with open(video_path, 'rb') as f:
                buf = f.read(chunk_size)
                hasher.update(buf)
            
            return hasher.hexdigest()
        except Exception:
            return str(file_size)

    def _analyze_video_content(self, video_path: str) -> Tuple[Optional[float], Optional[str]]:
        """
        動画の内容分析: 長さ(秒)と中間フレームのpHashを取得
        """
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return None, None
            
            # 動画の長さを取得
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            
            if fps <= 0 or frame_count <= 0:
                cap.release()
                return None, None
            
            duration = frame_count / fps
            
            # 中間フレームを取得
            middle_frame_idx = int(frame_count / 2)
            cap.set(cv2.CAP_PROP_POS_FRAMES, middle_frame_idx)
            ret, frame = cap.read()
            cap.release()
            
            if not ret or frame is None:
                return duration, None
            
            # フレームをPIL Imageに変換してpHash計算
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(frame_rgb)
            frame_hash = str(imagehash.phash(pil_image))
            
            return duration, frame_hash
            
        except Exception as e:
            return None, None

    def _load_image_cv2(self, image_path: str, grayscale: bool = False) -> Optional[np.ndarray]:
        """
        OpenCVで画像を読み込む (日本語パス対応)
        """
        try:
            with open(image_path, "rb") as stream:
                bytes_data = bytearray(stream.read())
            numpyarray = np.asarray(bytes_data, dtype=np.uint8)
            flag = cv2.IMREAD_GRAYSCALE if grayscale else cv2.IMREAD_COLOR
            img = cv2.imdecode(numpyarray, flag)
            return img
        except Exception:
            return None


def select_best_shot(group_items: List[Tuple[str, float, int, int]]) -> str:
    """
    類似画像グループから「残すべき1枚」を選択する
    
    Args:
        group_items: [(path, blur_score, face_count, file_size), ...]
        
    Returns:
        残すべき画像のパス
    
    優先順位:
    1. 顔の数 (多い方が優先)
    2. ブレの少なさ (blur_score が高い方が鮮明)
    3. ファイルサイズ (大きい方が高画質)
    """
    if not group_items:
        return ""
    
    # ソート: 顔数降順 → blur_score降順 → サイズ降順
    sorted_items = sorted(
        group_items,
        key=lambda x: (x[2], x[1], x[3]),  # face_count, blur_score, size
        reverse=True
    )
    
    return sorted_items[0][0]  # ベストショットのパスを返す
