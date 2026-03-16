"""
Album Art Module
================

Handles album art loading, caching, and display.
Supports multiple sources: embedded, iTunes API, MusicBrainz.
"""

import threading
import urllib.request
import urllib.parse
import json
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, GdkPixbuf, GLib, Gdk


class AlbumArtManager:
    """Manages album art loading and caching."""
    
    def __init__(self, parent_app):
        self.parent = parent_app
        self._album_pixbuf = None
        self._last_album_art_path = None
        
    def load_album_art(self, filepath, artist, title, album):
        """Load album art from various sources.
        
        Flow:
        1. Check cache by artist/album - if found, show it
        2. If not found, search iTunes
        3. Save metadata to SQLite (by filepath) AND album art (by artist/album)
        4. Update display with new metadata
        """
        def load():
            art_data = None
            source = ""
            
            _artist = artist
            _album = album
            
            # 1. Buscar carátula en cache (por artist/album)
            if _artist and _album:
                try:
                    cached_data, cached_source = self.parent.playlist._db.get_album_art(_artist, _album)
                    if cached_data:
                        art_data = cached_data
                        source = cached_source
                except Exception:
                    pass
            
            # 2. Si no hay cache, buscar en iTunes
            if not art_data and (_artist or title):
                try:
                    query = f"{_artist} {title}".strip()
                    url = f"https://itunes.apple.com/search?term={urllib.parse.quote(query)}&limit=1&entity=song"
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=5) as response:
                        data = json.loads(response.read().decode())
                        if data.get('results') and data['results'][0].get('artworkUrl100'):
                            itunes_result = data['results'][0]
                            art_url = itunes_result['artworkUrl100'].replace('100x100', '600x600')
                            
                            # Metadata de iTunes
                            itunes_artist = itunes_result.get("artistName", "")
                            itunes_album = itunes_result.get("collectionName", "")
                            itunes_title = itunes_result.get("trackName", "")
                            
                            # Descargar imagen
                            req = urllib.request.Request(art_url, headers={'User-Agent': 'Mozilla/5.0'})
                            with urllib.request.urlopen(req, timeout=5) as img_response:
                                art_data = img_response.read()
                                source = "itunes"
                            
                            # GUARDAR en SQLite: metadata por filepath
                            meta = {
                                "title": itunes_title or "",
                                "artist": itunes_artist or "",
                                "album": itunes_album or "",
                            }
                            try:
                                self.parent.playlist._db.set_track_metadata(filepath, meta)
                            except Exception:
                                pass
                            
                            # GUARDAR album art por artist/album
                            if itunes_artist and itunes_album:
                                try:
                                    self.parent.playlist._db.set_album_art(itunes_artist, itunes_album, art_data, source)
                                except Exception:
                                    pass
                                
                                # Actualizar display
                                GLib.idle_add(self._update_display_with_meta, meta)
                                
                                _artist = itunes_artist
                                _album = itunes_album
                except Exception:
                    pass
            
            # Mostrar carátula
            GLib.idle_add(self._update_ui, art_data)
        
        threading.Thread(target=load, daemon=True).start()
    
    def _update_display_with_meta(self, meta):
        """Update display with metadata from iTunes."""
        # Actualizar también el track en memoria
        current_track = self.parent.playlist.get_current_track()
        if current_track:
            if meta.get("title"):
                current_track.title = meta["title"]
            if meta.get("artist"):
                current_track.artist = meta["artist"]
            if meta.get("album"):
                current_track.album = meta["album"]
        
        self.parent._update_metadata_display(meta)
    
    def _update_ui(self, art_data):
        """Update UI with loaded album art."""
        if art_data:
            try:
                loader = GdkPixbuf.PixbufLoader()
                loader.write(art_data)
                loader.close()
                pixbuf = loader.get_pixbuf()
                if pixbuf:
                    self._album_pixbuf = pixbuf
                    self.parent._album_cover_centered.show()
                    self.parent._album_pixbuf = pixbuf
                    self.parent._album_cover_centered.queue_draw()
                    return
            except Exception:
                pass
        
        self.show_placeholder()
    
    def update_album_size(self, max_size=None):
        """Update album art size by triggering redraw."""
        if not self._album_pixbuf:
            return
        self.parent._album_cover_centered.queue_draw()
    
    def show_placeholder(self):
        """Show placeholder when no cover available."""
        self._album_pixbuf = None
        if hasattr(self.parent, '_album_pixbuf'):
            self.parent._album_pixbuf = None
        # Keep the widget visible but draw placeholder
        if not self.parent._album_cover_centered.get_visible():
            self.parent._album_cover_centered.show()
    
    def on_draw(self, widget, cr):
        """Draw album art with Cairo."""
        alloc = widget.get_allocation()
        width = alloc.width
        height = alloc.height
        
        if width <= 0 or height <= 0:
            return False
        
        # Fondo transparente
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        
        if self._album_pixbuf:
            orig_width = self._album_pixbuf.get_width()
            orig_height = self._album_pixbuf.get_height()
            
            scale_w = width / orig_width
            scale_h = height / orig_height
            scale = min(scale_w, scale_h)
            
            new_width = orig_width * scale
            new_height = orig_height * scale
            
            x = (width - new_width) / 2
            y = (height - new_height) / 2
            
            cr.save()
            cr.translate(x, y)
            cr.scale(scale, scale)
            Gdk.cairo_set_source_pixbuf(cr, self._album_pixbuf, 0, 0)
            cr.paint_with_alpha(0.5)
            cr.restore()
        else:
            # Dibujar placeholder
            self._draw_placeholder(cr, width, height)
        
        return False
    
    def _draw_placeholder(self, cr, width, height):
        """Draw placeholder when no album art."""
        size = min(width, height)
        if size <= 0:
            return
        
        x = (width - size) / 2
        y = (height - size) / 2
        
        # Fondo oscuro
        cr.set_source_rgba(0.12, 0.14, 0.18, 0.3)
        cr.rectangle(x, y, size, size)
        cr.fill()
        
        # Borde sutil
        cr.set_source_rgba(0.3, 0.35, 0.4, 0.2)
        cr.set_line_width(1)
        cr.rectangle(x + 0.5, y + 0.5, size - 1, size - 1)
        cr.stroke()
