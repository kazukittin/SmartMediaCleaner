"""
db_manager.py - SmartMediaCleaner
SQLiteデータベースを管理するクラス
"""
import sqlite3
from typing import Optional, Dict


class DBManager:
    """
    SQLiteデータベースを管理するクラス。
    メディアファイルのメタデータ（ハッシュ値、ブレスコアなど）をキャッシュします。
    """

    # 現在のスキーマバージョン
    SCHEMA_VERSION = 2

    def __init__(self, db_path: str = "media_cache.db"):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self._init_db()

    def _init_db(self):
        """データベース接続とテーブル作成を行います。"""
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.cursor = self.conn.cursor()
            
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS media_cache (
                    file_path TEXT PRIMARY KEY,
                    last_modified REAL,
                    file_size INTEGER,
                    blur_score REAL,
                    phash TEXT,
                    video_hash TEXT,
                    face_count INTEGER,
                    video_duration REAL,
                    video_frame_hash TEXT
                )
            ''')
            self.conn.commit()
            
            self._migrate_schema()
            
        except sqlite3.Error as e:
            print(f"DB初期化エラー: {e}")

    def _migrate_schema(self):
        """既存テーブルに新しいカラムを追加 (マイグレーション)"""
        try:
            self.cursor.execute("PRAGMA table_info(media_cache)")
            columns = {row[1] for row in self.cursor.fetchall()}
            
            new_columns = [
                ("face_count", "INTEGER"),
                ("video_duration", "REAL"),
                ("video_frame_hash", "TEXT")
            ]
            
            for col_name, col_type in new_columns:
                if col_name not in columns:
                    self.cursor.execute(f"ALTER TABLE media_cache ADD COLUMN {col_name} {col_type}")
                    print(f"マイグレーション: {col_name} カラムを追加")
            
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"マイグレーションエラー: {e}")

    def get_cache(self, file_path: str) -> Optional[Dict]:
        """キャッシュ情報を取得"""
        try:
            query = """SELECT last_modified, file_size, blur_score, phash, video_hash,
                       face_count, video_duration, video_frame_hash 
                       FROM media_cache WHERE file_path = ?"""
            self.cursor.execute(query, (file_path,))
            row = self.cursor.fetchone()
            
            if row:
                return {
                    "last_modified": row[0],
                    "file_size": row[1],
                    "blur_score": row[2],
                    "phash": row[3],
                    "video_hash": row[4],
                    "face_count": row[5],
                    "video_duration": row[6],
                    "video_frame_hash": row[7]
                }
            return None
        except sqlite3.Error as e:
            print(f"キャッシュ取得エラー: {e}")
            return None

    def upsert_cache(self, file_path: str, last_modified: float, file_size: int, 
                     blur_score: Optional[float] = None, phash: Optional[str] = None, 
                     video_hash: Optional[str] = None, face_count: Optional[int] = None,
                     video_duration: Optional[float] = None, video_frame_hash: Optional[str] = None):
        """キャッシュ情報を挿入または更新"""
        try:
            query = '''
                INSERT OR REPLACE INTO media_cache 
                (file_path, last_modified, file_size, blur_score, phash, video_hash,
                 face_count, video_duration, video_frame_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            '''
            self.cursor.execute(query, (file_path, last_modified, file_size, blur_score, 
                                        phash, video_hash, face_count, video_duration, video_frame_hash))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"キャッシュ保存エラー: {e}")

    def is_cache_valid(self, file_path: str, current_mtime: float, current_size: int) -> bool:
        """キャッシュが有効かどうかを確認"""
        cache = self.get_cache(file_path)
        if not cache:
            return False
        return (abs(cache['last_modified'] - current_mtime) < 0.001 and 
                cache['file_size'] == current_size)

    def close(self):
        """データベース接続を閉じます。"""
        if self.conn:
            self.conn.close()
