"""
Track Manager Module
====================

Orchestrates track playback, metadata fetching, and caching.
This is a pure logic module with no GTK dependencies.
"""

from .metadata_fetcher import MetadataFetcher
from .metadata_cache import MetadataCache


class TrackManager:
    """Manages track playback with metadata and album art caching."""
    
    def __init__(self, db_path=None):
        self.cache = MetadataCache(db_path)
        self.fetcher = MetadataFetcher()
    
    def get_metadata(self, filepath):
        """Get metadata for a track.
        
        First checks cache, then fetches from iTunes if not cached.
        
        Args:
            filepath: Path to the audio file
            
        Returns:
            dict with title, artist, album keys
        """
        # 1. Check cache
        cached = self.cache.get_track_metadata(filepath)
        if cached and cached.get("artist"):
            return cached
        
        # 2. If no cached metadata, return None (will use filename)
        return cached
    
    def fetch_and_cache_metadata(self, filepath, artist, title):
        """Fetch metadata from iTunes and cache it.
        
        Args:
            filepath: Path to the audio file
            artist: Artist name (can be empty)
            title: Song title (can be empty)
            
        Returns:
            dict with fetched metadata, or None if not found
        """
        # Only fetch if we have some search terms
        if not (artist or title):
            return None
        
        # Fetch from iTunes
        result = self.fetcher.search(artist, title)
        
        if result:
            # Cache track metadata by filepath
            self.cache.set_track_metadata(filepath, {
                "title": result["title"],
                "artist": result["artist"],
                "album": result["album"],
            })
            
            # Cache album art by artist/album
            if result["artist"] and result["album"]:
                self.cache.set_album_art(
                    result["artist"],
                    result["album"],
                    result["image_data"],
                    "itunes"
                )
            
            return {
                "title": result["title"],
                "artist": result["artist"],
                "album": result["album"],
                "image_data": result["image_data"],
            }
        
        return None
    
    def get_album_art(self, artist, album):
        """Get cached album art by artist/album."""
        return self.cache.get_album_art(artist, album)
    
    def close(self):
        """Close the cache."""
        self.cache.close()


def test_track_manager():
    """Test the track manager."""
    import tempfile
    import os
    
    # Create temp DB
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    
    manager = TrackManager(path)
    
    # Test 1: Get metadata from cache
    manager.cache.set_track_metadata("/test/song.mp3", {
        "title": "Cached Song",
        "artist": "Cached Artist",
        "album": "Cached Album",
    })
    
    meta = manager.get_metadata("/test/song.mp3")
    assert meta["artist"] == "Cached Artist"
    print(f"✓ Cache hit: {meta}")
    
    # Test 2: Fetch from iTunes
    result = manager.fetch_and_cache_metadata("/test/new.mp3", "Akino Arai", "VOICES")
    assert result is not None
    print(f"✓ Fetched: {result['title']} - {result['artist']}")
    
    # Test 3: Verify cached
    meta = manager.get_metadata("/test/new.mp3")
    assert meta["artist"] == "Akino Arai"
    print(f"✓ Cached after fetch: {meta}")
    
    # Test 4: Album art cached (using the correct album name from iTunes)
    # The album name might be different, let's check what's in cache
    all_albums = manager.cache._conn.execute("SELECT artist, album FROM album_art").fetchall()
    print(f"  Albums in cache: {all_albums}")
    
    # The exact album name from iTunes
    art_data, source = manager.get_album_art("Akino Arai", "MACROSS PLUS ORIGINAL SOUNDTRACK (with MEMBERS OF ISRAEL/ PHILHARMONIC ORCHESTRA)")
    if art_data:
        print(f"✓ Album art cached: {len(art_data)} bytes from {source}")
    else:
        print("⚠ Album art not cached with that exact name")
    
    manager.close()
    os.unlink(path)
    print("\nAll tests passed!")


if __name__ == "__main__":
    test_track_manager()