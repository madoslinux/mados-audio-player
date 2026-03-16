"""
Tests for track playback flow.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from .track_manager import TrackManager
    from .metadata_cache import MetadataCache
except ImportError:
    from track_manager import TrackManager
    from metadata_cache import MetadataCache
import tempfile


def test_metadata_cache():
    """Unit test for metadata cache."""
    print("=" * 50)
    print("TEST: MetadataCache")
    print("=" * 50)
    
    # Create temp DB
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    
    cache = MetadataCache(path)
    
    # Test set/get track metadata
    result = cache.set_track_metadata("/test/song.mp3", {
        "title": "Test Song",
        "artist": "Test Artist",
        "album": "Test Album",
    })
    assert result is True, "Failed to set track metadata"
    
    cached = cache.get_track_metadata("/test/song.mp3")
    assert cached is not None, "Failed to get track metadata"
    assert cached["title"] == "Test Song", f"Title mismatch: {cached['title']}"
    assert cached["artist"] == "Test Artist", f"Artist mismatch: {cached['artist']}"
    print("✓ Track metadata: SET and GET work")
    
    # Test album art
    result = cache.set_album_art("Artist", "Album", b"image_data", "test")
    assert result is True, "Failed to set album art"
    
    art_data, source = cache.get_album_art("Artist", "Album")
    assert art_data == b"image_data", f"Album art mismatch: {art_data}"
    print("✓ Album art: SET and GET work")
    
    # Test not found returns None
    assert cache.get_track_metadata("/nonexistent.mp3") is None
    assert cache.get_album_art("Unknown", "Unknown") == (None, None)
    print("✓ Not found returns None")
    
    cache.close()
    os.unlink(path)
    print("✓ All MetadataCache tests passed!\n")


def test_track_manager():
    """Unit test for track manager."""
    print("=" * 50)
    print("TEST: TrackManager")
    print("=" * 50)
    
    # Create temp DB
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    
    manager = TrackManager(path)
    
    # Test 1: Get metadata (cache miss)
    meta = manager.get_metadata("/new/song.mp3")
    assert meta is None, f"Should return None for new track, got: {meta}"
    print("✓ Cache miss returns None")
    
    # Test 2: Set metadata directly
    manager.cache.set_track_metadata("/new/song.mp3", {
        "title": "Cached Song",
        "artist": "Cached Artist",
        "album": "Cached Album",
    })
    
    # Test 3: Get metadata (cache hit)
    meta = manager.get_metadata("/new/song.mp3")
    assert meta is not None, "Should find cached track"
    assert meta["artist"] == "Cached Artist"
    print(f"✓ Cache hit: {meta}")
    
    # Test 4: Fetch from iTunes
    result = manager.fetch_and_cache_metadata("/test/itunes.mp3", "Akino Arai", "VOICES")
    assert result is not None, "iTunes fetch failed"
    assert result["artist"] == "Akino Arai"
    assert result["image_data"] is not None
    print(f"✓ iTunes fetch: {result['title']} - {result['artist']}")
    
    # Test 5: Verify cached after fetch
    meta = manager.get_metadata("/test/itunes.mp3")
    assert meta["artist"] == "Akino Arai"
    print(f"✓ Cached after fetch: {meta}")
    
    manager.close()
    os.unlink(path)
    print("✓ All TrackManager tests passed!\n")


def test_playback_flow():
    """Functional test: simulate full playback flow."""
    print("=" * 50)
    print("TEST: Playback Flow Simulation")
    print("=" * 50)
    
    # Create temp DB
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    
    manager = TrackManager(path)
    filepath = "/home/madkoding/Descargas/test_song.mp3"
    
    # STEP 1: Check if we have metadata in cache
    print("\n--- Step 1: Check cache ---")
    cached_meta = manager.get_metadata(filepath)
    print(f"  Cached metadata: {cached_meta}")
    
    # STEP 2: If no cached, use filename as fallback
    if not cached_meta:
        # Use filename as title (this is what the player does)
        title = os.path.splitext(os.path.basename(filepath))[0]
        print(f"  No cache, using filename as title: {title}")
        # In real app, this would be sent to mpv
    
    # STEP 3: After a while, try to fetch metadata
    # (This would happen in background after playing)
    print("\n--- Step 2: Background fetch ---")
    result = manager.fetch_and_cache_metadata(filepath, "Akino Arai", "VOICES")
    if result:
        print(f"  Fetched: {result['title']} - {result['artist']}")
        print(f"  Album art size: {len(result['image_data'])} bytes")
    else:
        print("  No results from iTunes")
    
    # STEP 4: Next time we play, we should get cached metadata
    print("\n--- Step 3: Next playback ---")
    cached_meta = manager.get_metadata(filepath)
    print(f"  Cached metadata: {cached_meta}")
    
    assert cached_meta is not None, "Should have cached metadata now"
    assert cached_meta["title"] == "VOICES"
    assert cached_meta["artist"] == "Akino Arai"
    print("✓ Playback flow works correctly!")
    
    manager.close()
    os.unlink(path)


if __name__ == "__main__":
    test_metadata_cache()
    test_track_manager()
    test_playback_flow()
    print("=" * 50)
    print("ALL TESTS PASSED!")
    print("=" * 50)