# AGENTS.md - madOS Audio Player

## Project Overview

madOS Audio Player is a Winamp-inspired GTK3 audio player for Linux with mpv backend. Written in Python, it supports playback of common audio formats (MP3, FLAC, OGG, WAV, AAC, OPUS) through mpv/ffmpeg.

## Build, Lint, and Test Commands

### Running the Application
```bash
python -m mados_audio_player
# or
./mados-audio-player
```

### Running Tests
```bash
# Run all tests (uses custom test runner with assertions)
python test_flow.py

# Run specific test function
python -c "from test_flow import test_metadata_cache; test_metadata_cache()"
python -c "from test_flow import test_track_manager; test_track_manager()"
python -c "from test_flow import test_playback_flow; test_playback_flow()"

# Also works from track_manager module
python track_manager.py
```

### Development Commands
```bash
# Check syntax
python -m py_compile <file>.py

# Import check
python -c "from module import *"
```

## Code Style Guidelines

### Imports
- Use relative imports for intra-package imports: `from .module import Class`
- Use absolute imports for standard library and external packages: `import os`, `from gi.repository import Gtk`
- Group imports: standard library first, then third-party, then local packages
- One import per line
```python
import os
import sys

import gi
from gi.repository import Gtk, Gdk, GLib

from .backend import MpvBackend
from .playlist import Playlist
```

### Naming Conventions
- **Classes**: PascalCase (e.g., `AudioPlayerApp`, `MetadataCache`)
- **Functions/methods**: snake_case (e.g., `get_metadata`, `_build_window`)
- **Private methods**: prefix with underscore (e.g., `_on_update_tick`)
- **Constants**: SCREAMING_SNAKE_CASE (e.g., `REPEAT_OFF`, `DEFAULT_LANGUAGE`)
- **Module names**: snake_case (e.g., `track_manager`, `metadata_cache`)

### Type Annotations
- Use type hints for function parameters and return types where beneficial
- Common types: `str`, `int`, `bool`, `Optional[T]`, `Dict[str, Any]`
```python
def get_metadata(self, filepath: str) -> Optional[Dict[str, Any]]:
```

### Docstrings
- Use docstrings for public classes and functions
- Follow Google-style or simple description format
```python
def get_metadata(self, filepath):
    """Get metadata for a track.
    
    First checks cache, then fetches from iTunes if not cached.
    
    Args:
        filepath: Path to the audio file
        
    Returns:
        dict with title, artist, album keys
    """
```

### Error Handling
- Use specific exception types: `RuntimeError`, `ValueError`, `TypeError`
- Wrap potentially failing operations in try/except for graceful degradation
```python
try:
    self.backend.start()
except RuntimeError as e:
    self._show_error(str(e))
```

### Code Organization
- Maximum line length: ~100 characters (soft limit, use judgment)
- One class per file preferred (except small related classes)
- Private methods after public methods
- Constants defined at class level in UPPER_SNAKE_CASE
- Instance variables initialized in `__init__`

### GTK-Specific Patterns
- Use GLib.timeout_add for timed updates
- Use GObject signals for events where appropriate
- Set widget properties via setter methods: `window.set_title()`, `window.set_default_size()`
- Use CSS for theming via `apply_theme()` function

### Testing Patterns
- Use simple assert statements (no pytest framework)
- Create temporary files/databases with tempfile module
- Clean up resources in finally blocks or after tests
- Test functions prefixed with `test_`
```python
def test_metadata_cache():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(path)
    
    cache = MetadataCache(path)
    # ... tests ...
    
    cache.close()
    os.unlink(path)
```

### Database
- Uses SQLite for metadata caching (via sqlite3)
- Database path configurable via `MetadataCache(db_path)`
- Tables: `track_metadata`, `album_art`

### Module Structure
- `app.py` - Main GTK3 application window
- `backend.py` - mpv JSON IPC backend
- `playlist.py` - Playlist management and track data
- `track_manager.py` - Orchestrates metadata fetching/caching
- `metadata_cache.py` - SQLite cache for track metadata
- `metadata_fetcher.py` - iTunes API integration
- `album_art.py` - Album art display management
- `theme.py` - Nord color theme CSS
- `spectrum.py` - Audio spectrum analyzer
- `playlist_window.py` - Separate playlist window
- `translations.py` - i18n strings

### Common Patterns
- Always close database connections: `cache.close()`
- Check for null/none before using cached data
- Use filename as fallback title when metadata unavailable