"""
madOS Audio Player - Main Application Window
=============================================

Simplified GTK3 player with spectrum analyzer as background,
overlay controls on mouse hover, and separate playlist window.
"""

import os
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo, GdkPixbuf

from . import __app_id__, __app_name__, __version__
from .backend import MpvBackend
from .playlist import Playlist, Track, format_time, REPEAT_OFF, REPEAT_ALL, REPEAT_ONE
from .translations import (
    TRANSLATIONS,
    DEFAULT_LANGUAGE,
    get_text,
    detect_system_language,
)
from .theme import apply_theme, NORD
from .spectrum import SpectrumAnalyzer
from .playlist_window import PlaylistWindow
from .album_art import AlbumArtManager
from .track_manager import TrackManager



class AudioPlayerApp:
    UPDATE_INTERVAL_MS = 16

    def __init__(self, files=None):
        self.language = detect_system_language()
        self._seeking = False
        self._update_timer_id = None
        self._marquee_timer_id = None
        self._overlay_visible = True
        self._overlay_timeout_id = None
        self._menu_btn = None
        self._prev_btn = None
        self._play_btn = None
        self._next_btn = None
        self._album_pixbuf = None
        self._resize_timeout_id = None

        self.backend = MpvBackend()
        self.playlist = Playlist()
        self.spectrum = SpectrumAnalyzer()
        self.playlist_window = None
        self.album_art_manager = AlbumArtManager(self)
        
        # Usar el nuevo track manager para metadata
        from .metadata_cache import MetadataCache
        self.track_manager = TrackManager()

        apply_theme()

        self._build_window()
        self._build_ui()

        try:
            self.backend.start()
        except RuntimeError as e:
            self._show_error(str(e))

        self.spectrum.start()

        if files:
            self._add_files_to_playlist(files)
            if not self.playlist.is_empty:
                self.playlist.set_current(0)
                self._play_current()

        self._update_timer_id = GLib.timeout_add(self.UPDATE_INTERVAL_MS, self._on_update_tick)

        if not self.playlist.is_empty:
            self._refresh_playlist_view()

        self.window.show_all()
        self._update_status(self._t("ready"))

    def _t(self, key):
        return get_text(key, self.language)

    def _build_window(self):
        self.window = Gtk.Window()
        self.window.set_title(self._t("title"))
        self.window.set_default_size(800, 600)
        self.window.set_resizable(True)
        self.window.set_position(Gtk.WindowPosition.CENTER)
        self.window.set_wmclass(__app_id__, __app_name__)
        self.window.set_role(__app_id__)

        self.window.connect("delete-event", self._on_delete)
        self.window.connect("destroy", self._on_destroy)
        self.window.connect("motion-notify-event", self._on_mouse_motion)
        self.window.connect("leave-notify-event", self._on_mouse_leave)
        self.window.connect("configure-event", self._on_window_resize)

        self.window.drag_dest_set(
            Gtk.DestDefaults.ALL, [Gtk.TargetEntry.new("text/uri-list", 0, 0)], Gdk.DragAction.COPY
        )
        self.window.connect("drag-data-received", self._on_drag_data)

        screen = self.window.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.window.set_visual(visual)
        self.window.set_app_paintable(True)

    def _build_ui(self):
        main_overlay = Gtk.Overlay()
        self.window.add(main_overlay)

        bg_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        bg_box.set_homogeneous(False)
        main_overlay.add(bg_box)

        drawing_area = Gtk.DrawingArea()
        drawing_area.set_hexpand(True)
        drawing_area.set_vexpand(True)
        drawing_area.connect("draw", self._on_background_draw)
        bg_box.pack_start(drawing_area, True, True, 0)
        self._drawing_area = drawing_area

        self._controls_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._controls_container.set_halign(Gtk.Align.FILL)
        self._controls_container.set_hexpand(True)
        self._controls_container.set_margin_start(20)
        self._controls_container.set_margin_end(20)
        self._controls_container.set_margin_top(20)
        self._controls_container.set_margin_bottom(20)
        self._controls_container.set_app_paintable(True)
        self._controls_container.connect("draw", self._on_overlay_draw)
        main_overlay.add_overlay(self._controls_container)

        self._controls_container.pack_start(self._build_title_area(), False, False, 0)

        # Espacio entre info y album art
        spacer = Gtk.Box()
        spacer.set_size_request(-1, 10)
        self._controls_container.pack_start(spacer, False, False, 0)

        # Usar DrawingArea para el album art para control total del escalado
        self._album_cover_centered = Gtk.DrawingArea()
        self._album_cover_centered.set_size_request(50, 50)
        self._album_cover_centered.set_hexpand(True)
        self._album_cover_centered.set_vexpand(True)
        self._album_cover_centered.connect("draw", self.album_art_manager.on_draw)
        self._controls_container.pack_start(self._album_cover_centered, True, True, 0)

        self._player_controls = self._build_overlay_controls()
        self._controls_container.pack_start(self._player_controls, False, False, 0)

    def _build_title_area(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        
        # Fila 1: Tiempo + tiempo total (alineados horizontalmente)
        time_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        time_box.set_halign(Gtk.Align.START)
        
        self.time_label = Gtk.Label(label="0:00")
        self.time_label.get_style_context().add_class("time-display")
        self.time_label.set_valign(Gtk.Align.CENTER)
        time_box.pack_start(self.time_label, False, False, 0)

        self.time_total_label = Gtk.Label(label="/ 0:00")
        self.time_total_label.get_style_context().add_class("time-display")
        self.time_total_label.set_valign(Gtk.Align.CENTER)
        self.time_total_label.set_margin_top(3)
        time_box.pack_start(self.time_total_label, False, False, 0)
        
        box.pack_start(time_box, False, False, 0)

        # Fila 2: Título
        self.title_area = Gtk.DrawingArea()
        self.title_area.set_size_request(-1, 32)
        self.title_area.set_margin_start(2)
        self.title_area.set_margin_end(2)
        self.title_area.connect("draw", self._on_title_draw)
        box.pack_start(self.title_area, False, False, 0)

        # Fila 3: Artista
        self.artist_label = Gtk.Label(label="")
        self.artist_label.get_style_context().add_class("track-artist")
        self.artist_label.set_halign(Gtk.Align.START)
        self.artist_label.set_ellipsize(Pango.EllipsizeMode.END)
        box.pack_start(self.artist_label, False, False, 0)

        # Info de bitrate
        self.bitrate_label = Gtk.Label(label="")
        self.bitrate_label.get_style_context().add_class("info-label")
        self.bitrate_label.set_halign(Gtk.Align.START)
        box.pack_start(self.bitrate_label, False, False, 0)

        self._marquee_text = __app_name__
        self._marquee_offset = 0
        self._marquee_separator = "    ///    "
        self._tick_count = 0
        self._marquee_timer_id = GLib.timeout_add(16, self._on_marquee_tick)

        return box

    def _build_overlay_controls(self):
        self._controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._controls_box.set_halign(Gtk.Align.CENTER)
        self._controls_box.set_valign(Gtk.Align.END)
        self._controls_box.set_margin_bottom(10)

        menu_btn = Gtk.Button()
        menu_btn.add(Gtk.Label(label="\U000f035c"))
        menu_btn.set_relief(Gtk.ReliefStyle.NONE)
        menu_btn.get_style_context().add_class("icon-btn")
        menu_btn.connect("clicked", self._on_menu_clicked)
        self._menu_btn = menu_btn
        self._controls_box.pack_start(menu_btn, False, False, 0)

        prev_btn = Gtk.Button()
        prev_btn.add(Gtk.Label(label="\U000f04ae"))
        prev_btn.set_relief(Gtk.ReliefStyle.NONE)
        prev_btn.get_style_context().add_class("icon-btn")
        prev_btn.connect("clicked", self._on_prev_clicked)
        self._prev_btn = prev_btn
        self._controls_box.pack_start(prev_btn, False, False, 0)

        self.play_btn = Gtk.Button()
        self.play_btn.add(Gtk.Label(label="\U000f040a"))
        self.play_btn.set_relief(Gtk.ReliefStyle.NONE)
        self.play_btn.get_style_context().add_class("icon-btn")
        self.play_btn.connect("clicked", self._on_play_clicked)
        self._controls_box.pack_start(self.play_btn, False, False, 0)

        next_btn = Gtk.Button()
        next_btn.add(Gtk.Label(label="\U000f04ad"))
        next_btn.set_relief(Gtk.ReliefStyle.NONE)
        next_btn.get_style_context().add_class("icon-btn")
        next_btn.connect("clicked", self._on_next_clicked)
        self._next_btn = next_btn
        self._controls_box.pack_start(next_btn, False, False, 0)

        self.seek_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 0.5)
        self.seek_scale.set_draw_value(False)
        self.seek_scale.set_size_request(150, -1)
        self.seek_scale.get_style_context().add_class("seek-bar")
        self.seek_scale.connect("button-press-event", self._on_seek_start)
        self.seek_scale.connect("button-release-event", self._on_seek_end)
        self.seek_scale.connect("change-value", self._on_seek_change)
        self._controls_box.pack_start(self.seek_scale, False, False, 4)

        self.volume_icon = Gtk.Label(label="\U000f057e")
        self.volume_icon.set_valign(Gtk.Align.CENTER)
        self._controls_box.pack_start(self.volume_icon, False, False, 0)

        self.volume_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.volume_scale.set_value(100)
        self.volume_scale.set_draw_value(False)
        self.volume_scale.set_size_request(60, -1)
        self.volume_scale.get_style_context().add_class("volume-bar")
        self.volume_scale.connect("value-changed", self._on_volume_changed)
        self._controls_box.pack_start(self.volume_scale, False, False, 0)

        return self._controls_box

    def _on_menu_clicked(self, button):
        menu = Gtk.Menu()
        
        add_files_item = Gtk.MenuItem(label=self._t("add_files"))
        add_files_item.connect("activate", self._on_add_files_clicked)
        menu.append(add_files_item)

        add_folder_item = Gtk.MenuItem(label=self._t("add_folder"))
        add_folder_item.connect("activate", self._on_add_folder_clicked)
        menu.append(add_folder_item)

        menu.append(Gtk.SeparatorMenuItem())

        # Shuffle con estado actual
        shuffle_item = Gtk.CheckMenuItem(label=self._t("shuffle"))
        shuffle_item.set_active(self.playlist.shuffle)
        shuffle_item.connect("toggled", self._on_shuffle_toggled)
        menu.append(shuffle_item)

        repeat_item = Gtk.MenuItem(label=self._t("repeat"))
        repeat_submenu = Gtk.Menu()

        repeat_off_item = Gtk.RadioMenuItem.new_with_label(None, self._t("repeat_off"))
        repeat_off_item.connect("toggled", self._on_repeat_mode_toggled, REPEAT_OFF)
        repeat_submenu.append(repeat_off_item)

        repeat_all_item = Gtk.RadioMenuItem.new_with_label([repeat_off_item], self._t("repeat_all"))
        repeat_all_item.connect("toggled", self._on_repeat_mode_toggled, REPEAT_ALL)
        repeat_submenu.append(repeat_all_item)

        repeat_one_item = Gtk.RadioMenuItem.new_with_label([repeat_off_item], self._t("repeat_one"))
        repeat_one_item.connect("toggled", self._on_repeat_mode_toggled, REPEAT_ONE)
        repeat_submenu.append(repeat_one_item)
        
        # Establecer el estado actual del repeat
        if self.playlist.repeat_mode == REPEAT_OFF:
            repeat_off_item.set_active(True)
        elif self.playlist.repeat_mode == REPEAT_ALL:
            repeat_all_item.set_active(True)
        elif self.playlist.repeat_mode == REPEAT_ONE:
            repeat_one_item.set_active(True)

        repeat_item.set_submenu(repeat_submenu)
        menu.append(repeat_item)

        menu.append(Gtk.SeparatorMenuItem())

        playlist_item = Gtk.MenuItem(label=self._t("view_playlist"))
        playlist_item.connect("activate", self._on_view_playlist_clicked)
        menu.append(playlist_item)

        menu.show_all()
        menu.attach_to_widget(self._menu_btn, None)
        menu.popup(None, None, None, None, 0, Gtk.get_current_event_time())

    def _on_shuffle_toggled(self, item):
        self.playlist.toggle_shuffle()
        self._update_status(f"Shuffle: {'ON' if self.playlist.shuffle else 'OFF'}")

    def _cycle_repeat(self):
        mode = self.playlist.cycle_repeat()

    def _on_repeat_mode_toggled(self, item, mode):
        if item.get_active():
            self.playlist.repeat_mode = mode
            self.playlist._save_state()

    def _on_view_playlist_clicked(self, item):
        if self.playlist_window is None or not self.playlist_window.get_visible():
            self.playlist_window = PlaylistWindow(self)
            self.playlist_window.connect("destroy", lambda w: setattr(self, "playlist_window", None))
            self.playlist_window.show_all()
        else:
            self.playlist_window.present()

    def _on_play_clicked(self, button):
        if not self.backend.is_playing and not self.backend.is_paused:
            if self.playlist.current_index < 0 and not self.playlist.is_empty:
                self.playlist.set_current(0)
            self._play_current()
        else:
            self.backend.toggle_pause()
            if self.backend.is_paused:
                self.play_btn.get_child().set_text("\U000f040a")
                self._update_status(self._t("paused"))
            else:
                self.play_btn.get_child().set_text("\U000f03e4")
                self._update_status(self._t("playing"))

    def _on_prev_clicked(self, button):
        if self.backend.position > 3:
            self.backend.seek(0)
            return
        track = self.playlist.prev_track()
        if track:
            self._play_current()

    def _on_next_clicked(self, button):
        track = self.playlist.next_track()
        if track:
            self._play_current()
        else:
            self._on_stop_clicked(None)

    def _on_stop_clicked(self, button):
        self.backend.stop()
        self.play_btn.get_child().set_text("\U000f040a")
        self.time_label.set_text("0:00")
        self.seek_scale.set_value(0)
        self._update_status(self._t("stopped"))

    def _on_seek_start(self, widget, event):
        self._seeking = True

    def _on_seek_end(self, widget, event):
        self._seeking = False
        if self.backend.duration > 0:
            fraction = self.seek_scale.get_value() / 100.0
            target = fraction * self.backend.duration
            self.backend.seek(target)

    def _on_seek_change(self, widget, scroll_type, value):
        if self._seeking and self.backend.duration > 0:
            fraction = max(0.0, min(1.0, value / 100.0))
            pos = fraction * self.backend.duration
            self.time_label.set_text(format_time(pos))

    def _on_volume_changed(self, scale):
        vol = int(scale.get_value())
        self.backend.set_volume(vol)
        self._update_volume_icon(vol, self.backend.is_muted)

    def _update_volume_icon(self, volume, muted):
        if muted:
            self.volume_icon.set_text("\U000f0581")
        elif volume == 0:
            self.volume_icon.set_text("\U000f0e08")
        elif volume < 50:
            self.volume_icon.set_text("\U000f057f")
        else:
            self.volume_icon.set_text("\U000f057e")

    def _on_add_files_clicked(self, item):
        dialog = Gtk.FileChooserDialog(
            title=self._t("select_audio_files"),
            parent=self.window,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_buttons(
            self._t("cancel"), Gtk.ResponseType.CANCEL,
            self._t("open"), Gtk.ResponseType.OK,
        )
        dialog.set_select_multiple(True)

        audio_filter = Gtk.FileFilter()
        audio_filter.set_name(self._t("audio_files"))
        for ext in sorted(MpvBackend.AUDIO_EXTENSIONS):
            audio_filter.add_pattern(f"*{ext}")
        dialog.add_filter(audio_filter)

        all_filter = Gtk.FileFilter()
        all_filter.set_name(self._t("all_files"))
        all_filter.add_pattern("*")
        dialog.add_filter(all_filter)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            files = dialog.get_filenames()
            self._add_files_to_playlist(files)
        dialog.destroy()

    def _on_add_folder_clicked(self, item):
        dialog = Gtk.FileChooserDialog(
            title=self._t("select_folder"),
            parent=self.window,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
        )
        dialog.add_buttons(
            self._t("cancel"), Gtk.ResponseType.CANCEL,
            self._t("open"), Gtk.ResponseType.OK,
        )

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            folder = dialog.get_filename()
            if folder:
                count = self.playlist.add_directory(folder)
                self._refresh_playlist_view()
                self._update_status(f"{count} {self._t('tracks')}")
        dialog.destroy()

    def _add_files_to_playlist(self, filepaths):
        for fp in filepaths:
            if os.path.isdir(fp):
                self.playlist.add_directory(fp)
            elif os.path.isfile(fp) and MpvBackend.is_audio_file(fp):
                self.playlist.add_file(fp)
        self._refresh_playlist_view()

    def _refresh_playlist_view(self):
        if self.playlist_window and self.playlist_window.get_visible():
            self.playlist_window._refresh_view()

    def _update_playlist_highlight(self):
        if self.playlist_window and self.playlist_window.get_visible():
            self.playlist_window._refresh_view()

    def _on_drag_data(self, widget, drag_context, x, y, data, info, time):
        uris = data.get_uris()
        files = []
        for uri in uris:
            if uri.startswith("file://"):
                from urllib.parse import unquote
                path = unquote(uri[7:])
                files.append(path)
        if files:
            self._add_files_to_playlist(files)
            
            if not self.backend.is_playing and not self.playlist.is_empty:
                if self.playlist.current_index < 0:
                    self.playlist.set_current(0)
                self._play_current()

    def _play_current(self):
        track = self.playlist.get_current_track()
        if not track:
            return
        
        # Verificar que el archivo existe
        if not os.path.isfile(track.filepath):
            return
        
        # Reset flags for new track
        self._album_art_loaded = False
        if hasattr(self, 'album_art_manager'):
            self.album_art_manager.show_placeholder()
        self._album_cover_centered.queue_draw()
        
        # Usar track_manager para obtener metadata cacheada
        cached_meta = self.track_manager.get_metadata(track.filepath)
        
        if cached_meta:
            track.title = cached_meta.get("title", track.title)
            track.artist = cached_meta.get("artist", "")
            track.album = cached_meta.get("album", "")
            self.backend.metadata = cached_meta
        
        # Reproducir
        success = self.backend.play_file(track.filepath)
        
        if success:
            self.play_btn.get_child().set_text("\U000f03e4")
            self._update_track_display(track)
            self._update_playlist_highlight()
            self._update_status(self._t("playing"))
            
            # Cargar album art en background
            artist = cached_meta.get("artist") if cached_meta else ""
            title = cached_meta.get("title") if cached_meta else track.title
            album = cached_meta.get("album") if cached_meta else ""
            
            if artist or title:
                self.album_art_manager.load_album_art(track.filepath, artist, title, album)

    def _on_update_tick(self):
        if not self.backend.is_playing and not self.backend.is_paused:
            if self.backend.current_file and self.backend.is_track_finished():
                self._on_track_finished()
            return True

        self.backend.update_state()
        
        self.spectrum.update()
        if hasattr(self, '_drawing_area'):
            self._drawing_area.queue_draw()

        if not self._seeking and self.backend.duration > 0:
            fraction = (self.backend.position / self.backend.duration) * 100
            self.seek_scale.set_value(fraction)
            self.time_label.set_text(format_time(self.backend.position))
            self.time_total_label.set_text(f"/ {format_time(self.backend.duration)}")

        # Solo actualizar display - NO sobrescribir metadata con mpv
        meta = self.backend.get_formatted_metadata()
        current_track = self.playlist.get_current_track()
        
        # Mostrar metadata (preferir la cacheada, si no está usar mpv)
        if current_track:
            self._update_track_display(current_track)

        if current_track and self.backend.duration > 0:
            self.playlist.update_track_duration(current_track, self.backend.duration)
            self._update_playlist_highlight()

        info = self.backend.get_audio_info()
        if info.get("bitrate") or info.get("samplerate"):
            parts = []
            if info.get("bitrate"):
                parts.append(info["bitrate"])
            if info.get("samplerate"):
                parts.append(info["samplerate"])
            self.bitrate_label.set_text(" | ".join(parts))
        else:
            self.bitrate_label.set_text("")

        if self.backend.is_track_finished():
            self._on_track_finished()

        return True

    def _on_track_finished(self):
        self._album_art_loaded = False
        track = self.playlist.next_track()
        if track:
            self._play_current()
        else:
            self._on_stop_clicked(None)

    def _update_track_display(self, track):
        # Usar metadata DEL TRACK (preferir cache), no de mpv
        if track.artist or track.title:
            # Usar metadata cacheada del track
            meta = {
                "title": track.title or "",
                "artist": track.artist or "",
                "album": track.album or "",
            }
        else:
            # Fallback a mpv si el track no tiene metadata
            meta = self.backend.get_formatted_metadata()
        
        self._update_metadata_display(meta)
    
    def _update_metadata_display(self, meta):
        """Actualiza el display de metadata (título, artista, album)."""
        # Título
        title = meta.get("title") or ""
        if title and title != self._marquee_text:
            self._marquee_text = title
            self._marquee_offset = 0
        
        # Artista y Album
        artist = meta.get("artist") or ""
        album = meta.get("album") or ""
        
        if artist:
            self.artist_label.set_text(f"{artist}" + (f" — {album}" if album else ""))
        else:
            self.artist_label.set_text("")
    
    def _show_album_placeholder(self):
        """Muestra placeholder del album art."""
        self._album_pixbuf = None
        self.album_art_manager.show_placeholder()
    
    def _update_album_art_size(self, max_size=None):
        """Actualiza el tamaño del album art manteniendo proporción."""
        if not hasattr(self, '_album_pixbuf') or not self._album_pixbuf:
            return
        
        if hasattr(self, 'album_art_manager'):
            self.album_art_manager.update_album_size(max_size)
        self._album_cover_centered.queue_draw()

    def _on_album_draw(self, widget, cr):
        """Dibuja el album art escalado proporcionalmente."""
        alloc = widget.get_allocation()
        width = alloc.width
        height = alloc.height
        
        if width <= 0 or height <= 0:
            return False
        
        # Fondo transparente
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        
        if hasattr(self, '_album_pixbuf') and self._album_pixbuf:
            orig_width = self._album_pixbuf.get_width()
            orig_height = self._album_pixbuf.get_height()
            
            # Calcular escala manteniendo proporción
            scale_w = width / orig_width
            scale_h = height / orig_height
            scale = min(scale_w, scale_h)
            
            # Calcular nuevo tamaño
            new_width = orig_width * scale
            new_height = orig_height * scale
            
            # Centrar la imagen
            x = (width - new_width) / 2
            y = (height - new_height) / 2
            
            # Escalar y dibujar
            cr.save()
            cr.translate(x, y)
            cr.scale(scale, scale)
            Gdk.cairo_set_source_pixbuf(cr, self._album_pixbuf, 0, 0)
            cr.paint_with_alpha(0.5)
            cr.restore()
        else:
            # Dibujar placeholder
            self._draw_album_placeholder_cairo(cr, width, height)
        
        return False
    
    def _draw_album_placeholder_cairo(self, cr, width, height):
        """Dibuja el placeholder del album art."""
        size = min(width, height)
        if size <= 0:
            return
        
        # Centrar
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

    def _update_status(self, text):
        pass

    def _on_mouse_motion(self, widget, event):
        pass

    def _on_mouse_leave(self, widget, event):
        pass

    def _on_window_resize(self, widget, event):
        width = event.width
        height = event.height
        
        # Ajustar márgenes y controles inmediatamente (sin debounce)
        if hasattr(self, '_controls_container'):
            # Márgenes horizontales según ancho
            if width < 150:
                margin_h = 2
            elif width < 250:
                margin_h = 5
            elif width < 350:
                margin_h = 10
            elif width < 500:
                margin_h = 15
            else:
                margin_h = 20
            
            # Márgenes verticales según altura
            if height < 200:
                margin_v = 2
            elif height < 300:
                margin_v = 5
            elif height < 400:
                margin_v = 10
            else:
                margin_v = 15
            
            self._controls_container.set_margin_start(margin_h)
            self._controls_container.set_margin_end(margin_h)
            self._controls_container.set_margin_top(margin_v)
            self._controls_container.set_margin_bottom(margin_v)
        
        # Ajustar tipografía y controles según el ancho (inmediato)
        if width < 200:
            self.seek_scale.hide()
            self.volume_scale.hide()
            self.volume_icon.hide()
            self._title_font_size = 8
        elif width < 250:
            self.seek_scale.hide()
            self.volume_scale.hide()
            self.volume_icon.hide()
            self._title_font_size = 9
        elif width < 300:
            self.seek_scale.hide()
            self.volume_scale.hide()
            self.volume_icon.hide()
            self._title_font_size = 10
        elif width < 350:
            self.seek_scale.hide()
            self.volume_scale.hide()
            self.volume_icon.hide()
            self._title_font_size = 11
        elif width < 400:
            self.seek_scale.hide()
            self.volume_scale.hide()
            self.volume_icon.hide()
            self._title_font_size = 12
        elif width < 450:
            self.seek_scale.hide()
            self.volume_scale.show()
            self.volume_icon.show()
            self._title_font_size = 14
        elif width < 550:
            self.seek_scale.show()
            self.volume_scale.show()
            self.volume_icon.show()
            self._title_font_size = 16
        else:
            self.seek_scale.show()
            self.volume_scale.show()
            self.volume_icon.show()
            self._title_font_size = 20
            
        if hasattr(self, 'title_area'):
            self.title_area.queue_draw()
        
        # Cancelar timeout anterior del album art si existe
        if self._resize_timeout_id:
            GLib.source_remove(self._resize_timeout_id)
        
        # Programar actualización del album art después de 100ms para evitar lag
        self._resize_timeout_id = GLib.timeout_add(100, self._do_album_resize, width, height)
    
    def _do_album_resize(self, width, height):
        """Actualiza el tamaño del album art después del resize."""
        self._resize_timeout_id = None
        
        # Calcular tamaño máximo del album art (50% de la altura)
        max_album_size = int(height * 0.5)
        
        if hasattr(self, '_album_cover_centered'):
            # Establecer tamaño máximo - usar -1 para permitir reducción
            self._album_cover_centered.set_size_request(-1, -1)
            # Forzar redimensionamiento del album art
            if hasattr(self, '_album_pixbuf') and self._album_pixbuf:
                self._update_album_art_size(max_album_size)
            else:
                # Si no hay album art, actualizar placeholder
                self._show_album_placeholder()
        
        return False

    _title_font_size = 20

    def _show_overlay(self):
        self._overlay_visible = True
        self._player_controls.set_opacity(1)

    def _hide_overlay(self):
        self._overlay_visible = True
        self._player_controls.set_opacity(1)

    def _on_overlay_draw(self, widget, cr):
        alloc = widget.get_allocation()
        w = alloc.width
        h = alloc.height
        radius = 15
        cr.set_source_rgba(22 / 255, 26 / 255, 33 / 255, 0.5)
        cr.new_sub_path()
        cr.arc(w - radius, radius, radius, -1.5708, 0)
        cr.arc(w - radius, h - radius, radius, 0, 1.5708)
        cr.arc(radius, h - radius, radius, 1.5708, 3.14159)
        cr.arc(radius, radius, radius, 3.14159, 4.71239)
        cr.close_path()
        cr.fill()
        return False

    def _on_background_draw(self, widget, cr):
        alloc = widget.get_allocation()
        w = alloc.width
        h = alloc.height

        cr.set_source_rgb(22 / 255, 26 / 255, 33 / 255)
        cr.paint()

        bars = self.spectrum.bars
        if not bars or not self.spectrum.is_active:
            return False

        num_bars = len(bars)
        if num_bars == 0:
            return False

        padding_x = 10
        padding_bottom = 10
        usable_w = w - 2 * padding_x
        usable_h = h - padding_bottom - 50

        led_h = 3
        led_gap = 1
        led_step = led_h + led_gap

        total_bar_gap = num_bars - 1
        bar_gap = 2
        bar_w = max(2, (usable_w - total_bar_gap * bar_gap) / num_bars)

        max_segments = max(1, int(usable_h / led_step))

        colors_rgb = {
            "green": (163 / 255, 190 / 255, 140 / 255),
            "yellow": (235 / 255, 203 / 255, 139 / 255),
            "red": (191 / 255, 97 / 255, 106 / 255),
        }

        for i, bar_val in enumerate(bars):
            x = padding_x + i * (bar_w + bar_gap)
            active_segments = int(bar_val * max_segments)

            for seg in range(active_segments):
                y = h - padding_bottom - (seg + 1) * led_step

                ratio = seg / max(1, max_segments - 1)
                if ratio < 0.45:
                    r, g, b = colors_rgb["green"]
                elif ratio < 0.75:
                    r, g, b = colors_rgb["yellow"]
                else:
                    r, g, b = colors_rgb["red"]

                alpha = 0.4 + 0.4 * (seg / max(1, max_segments))
                cr.set_source_rgba(r, g, b, alpha)
                cr.rectangle(x, y, bar_w, led_h)
                cr.fill()

        peaks = self.spectrum.peaks
        for i, peak_val in enumerate(peaks):
            if peak_val <= 0:
                continue
            x = padding_x + i * (bar_w + bar_gap)
            peak_seg = int(peak_val * max_segments)
            if peak_seg >= max_segments:
                peak_seg = max_segments - 1
            y = h - padding_bottom - (peak_seg + 1) * led_step

            ratio = peak_seg / max(1, max_segments - 1)
            if ratio < 0.45:
                r, g, b = colors_rgb["green"]
            elif ratio < 0.75:
                r, g, b = colors_rgb["yellow"]
            else:
                r, g, b = colors_rgb["red"]

            cr.set_source_rgba(r, g, b, 0.8)
            cr.rectangle(x, y, bar_w, led_h)
            cr.fill()

        self.spectrum.update()
        return False

    def _on_marquee_tick(self):
        self._tick_count += 1
        if self._tick_count % 2 == 0:
            self._marquee_offset += 1
            self.title_area.queue_draw()
        return True

    def _on_title_draw(self, widget, cr):
        alloc = widget.get_allocation()
        width = alloc.width
        height = alloc.height

        layout = PangoCairo.create_layout(cr)
        font_size = getattr(self, '_title_font_size', 16)
        font_desc = Pango.FontDescription.from_string(f"Michroma {font_size}")
        layout.set_font_description(font_desc)

        text = self._marquee_text
        layout.set_text(text, -1)
        text_width, text_height = layout.get_pixel_size()

        r, g, b = 136 / 255, 192 / 255, 208 / 255
        # Center vertically with a slight offset for optical alignment
        y = (height - text_height) / 2 + 1

        if text_width <= width:
            cr.save()
            for alpha, spread in [(0.15, 6), (0.3, 3), (0.5, 1.5)]:
                cr.set_source_rgba(r, g, b, alpha)
                cr.move_to(spread * 0.3, y + spread * 0.15)
                PangoCairo.show_layout(cr, layout)
                cr.move_to(-spread * 0.3, y - spread * 0.15)
                PangoCairo.show_layout(cr, layout)
            cr.restore()
            cr.move_to(0, y)
            cr.set_source_rgb(r, g, b)
            PangoCairo.show_layout(cr, layout)
        else:
            full_text = text + self._marquee_separator + text
            layout.set_text(full_text, -1)
            full_width, _ = layout.get_pixel_size()
            cycle_width = full_width - text_width
            offset = self._marquee_offset % cycle_width if cycle_width > 0 else 0

            cr.rectangle(0, 0, width, height)
            cr.clip()

            cr.save()
            for alpha, spread in [(0.15, 6), (0.3, 3), (0.5, 1.5)]:
                cr.set_source_rgba(r, g, b, alpha)
                cr.move_to(-offset + spread * 0.3, y + spread * 0.15)
                PangoCairo.show_layout(cr, layout)
                cr.move_to(-offset - spread * 0.3, y - spread * 0.15)
                PangoCairo.show_layout(cr, layout)
            cr.restore()

            cr.move_to(-offset, y)
            cr.set_source_rgb(r, g, b)
            PangoCairo.show_layout(cr, layout)

    def _show_error(self, message):
        dialog = Gtk.MessageDialog(
            parent=self.window,
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            message_format=message,
        )
        dialog.run()
        dialog.destroy()

    def _on_delete(self, widget, event):
        self._cleanup()
        return False

    def _on_destroy(self, widget):
        self._cleanup()
        Gtk.main_quit()

    def _cleanup(self):
        # Detener timers primero
        if self._update_timer_id:
            GLib.source_remove(self._update_timer_id)
            self._update_timer_id = None
        if self._marquee_timer_id:
            GLib.source_remove(self._marquee_timer_id)
            self._marquee_timer_id = None
        if self._overlay_timeout_id:
            GLib.source_remove(self._overlay_timeout_id)
            self._overlay_timeout_id = None
        
        # Cerrar componentes que usan la database
        self.spectrum.stop()
        
        # Cerrar playlist (guarda estado en DB)
        self.playlist.close()
        
        # Limpiar backend
        self.backend.cleanup()
