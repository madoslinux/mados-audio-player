"""
Metadata Cache Module
=====================

Handles SQLite caching for track metadata and album art.
"""

import sqlite3
import os
import time


class MetadataCache:
    """SQLite-based cache for metadata and album art."""
    
    def __init__(self, db_path=None):
        self.db_path = db_path or self._default_db_path()
        self._conn = None
        self._connect()
        self._init_schema()
    
    def _default_db_path(self):
        base = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        return os.path.join(base, "mados-audio-player", "playlists.db")
    
    def _connect(self):
        self._conn = sqlite3.connect(self.db_path, timeout=5, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
    
    def _init_schema(self):
        # Ensure tables exist
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS track_metadata (
                filepath TEXT PRIMARY KEY,
                title TEXT,
                artist TEXT,
                album TEXT,
                duration REAL,
                updated_at REAL NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS album_art (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artist TEXT NOT NULL,
                album TEXT NOT NULL,
                image_data BLOB NOT NULL,
                source TEXT,
                updated_at REAL NOT NULL,
                UNIQUE(artist, album)
            )
        """)
        self._conn.commit()
    
    # --- Track Metadata (by filepath) ---
    
    def get_track_metadata(self, filepath):
        """Get cached metadata for a track filepath."""
        try:
            row = self._conn.execute(
                "SELECT title, artist, album, duration FROM track_metadata WHERE filepath = ?",
                (filepath,)
            ).fetchone()
            if row:
                return {
                    "title": row["title"],
                    "artist": row["artist"],
                    "album": row["album"],
                    "duration": row["duration"],
                }
        except Exception:
            pass
        return None
    
    def set_track_metadata(self, filepath, metadata):
        """Cache metadata for a track filepath."""
        try:
            self._conn.execute(
                """INSERT OR REPLACE INTO track_metadata
                   (filepath, title, artist, album, duration, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    filepath,
                    metadata.get("title", ""),
                    metadata.get("artist", ""),
                    metadata.get("album", ""),
                    metadata.get("duration", 0.0),
                    time.time(),
                )
            )
            self._conn.commit()
            return True
        except Exception:
            return False
    
    # --- Album Art (by artist/album) ---
    
    def get_album_art(self, artist, album):
        """Get cached album art by artist/album."""
        try:
            row = self._conn.execute(
                "SELECT image_data, source FROM album_art WHERE artist = ? AND album = ?",
                (artist, album)
            ).fetchone()
            if row:
                return row["image_data"], row["source"]
        except Exception:
            pass
        return None, None
    
    def set_album_art(self, artist, album, image_data, source="itunes"):
        """Cache album art by artist/album."""
        try:
            self._conn.execute(
                """INSERT OR REPLACE INTO album_art
                   (artist, album, image_data, source, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (artist, album, image_data, source, time.time())
            )
            self._conn.commit()
            return True
        except Exception:
            return False
    
    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


def test_cache():
    """Test the metadata cache."""
    import tempfile
    
    # Create temp DB
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    
    cache = MetadataCache(path)
    
    # Test set/get track metadata
    cache.set_track_metadata("/test/song.mp3", {
        "title": "Test Song",
        "artist": "Test Artist",
        "album": "Test Album",
    })
    
    result = cache.get_track_metadata("/test/song.mp3")
    assert result is not None, "Should find cached track"
    assert result["title"] == "Test Song", f"Title mismatch: {result['title']}"
    print(f"✓ Track metadata: {result}")
    
    # Test set/get album art
    cache.set_album_art("Test Artist", "Test Album", b"fake_image_data", "test")
    
    art_data, source = cache.get_album_art("Test Artist", "Test Album")
    assert art_data == b"fake_image_data", "Album art mismatch"
    print(f"✓ Album art: {source}")
    
    # Test not found
    assert cache.get_track_metadata("/nonexistent.mp3") is None
    assert cache.get_album_art("Unknown", "Unknown") == (None, None)
    print("✓ Not found returns None")
    
    cache.close()
    os.unlink(path)
    print("\nAll tests passed!")


if __name__ == "__main__":
    test_cache()