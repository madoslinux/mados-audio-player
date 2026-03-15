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
from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo

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


class PlaylistWindow(Gtk.Window):
    """Separate window for playlist management."""

    def __init__(self, parent_app):
        super().__init__()
        self.parent_app = parent_app
        self.set_title(parent_app._t("playlist"))
        self.set_default_size(400, 500)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_transient_for(parent_app.window)
        self.set_wmclass(__app_id__, __app_name__)
        self.set_role(f"{__app_id__}_playlist")

        self._build_ui()
        self._refresh_view()

    def _build_ui(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(box)

        toolbar = Gtk.HeaderBar()
        toolbar.set_show_close_button(True)
        self.set_titlebar(toolbar)

        clear_btn = Gtk.Button()
        clear_btn.add(Gtk.Label(label="\U000f01b4"))
        clear_btn.set_tooltip_text(self.parent_app._t("clear_playlist"))
        clear_btn.connect("clicked", self._on_clear_clicked)
        toolbar.pack_start(clear_btn)

        box.pack_start(self._build_playlist_view(), True, True, 0)

    def _build_playlist_view(self):
        self.store = Gtk.ListStore(int, str, str, str)
        self.view = Gtk.TreeView(model=self.store)
        self.view.set_headers_visible(False)
        self.view.connect("row-activated", self._on_row_activated)
        self.view.connect("button-press-event", self._on_view_button_press)

        col = Gtk.TreeViewColumn()
        self.view.append_column(col)

        renderer = Gtk.CellRendererBox()
        renderer.set_orientation(Gtk.Orientation.HORIZONTAL)
        col.add_attribute(renderer, "text", 1)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.view)

        return scroll

    def _on_view_button_press(self, view, event):
        if event.button == 3:
            path = view.get_path_at_pos(int(event.x), int(event.y))
            if path:
                self._show_context_menu(path[0], int(event.x), int(event.y))
                return True
        return False

    def _show_context_menu(self, path, x, y):
        menu = Gtk.Menu()
        remove_item = Gtk.MenuItem(label=self.parent_app._t("remove"))
        remove_item.connect("activate", self._on_remove_track, path.get_indices()[0])
        menu.append(remove_item)
        menu.attach_to_widget(self.view, None)
        menu.popup(None, None, None, None, 3, Gtk.get_current_event_time())

    def _on_remove_track(self, item, index):
        self.parent_app.playlist.remove_index(index)
        self._refresh_view()

    def _on_row_activated(self, treeview, path, column):
        index = path.get_indices()[0]
        self.parent_app.playlist.set_current(index)
        self.parent_app._play_current()
        self.parent_app._update_playlist_highlight()

    def _on_clear_clicked(self, button):
        self.parent_app.backend.stop()
        self.parent_app.playlist.clear()
        self._refresh_view()
        self.parent_app._marquee_text = __app_name__
        self.parent_app._marquee_offset = 0
        self.parent_app.title_area.queue_draw()
        self.parent_app.artist_label.set_text("")
        self.parent_app._update_status(self.parent_app._t("ready"))

    def _refresh_view(self):
        self.store.clear()
        for i, track in enumerate(self.parent_app.playlist.tracks):
            is_current = i == self.parent_app.playlist.current_index
            name = f"▶ {track.display_name()}" if is_current else track.display_name()
            dur = format_time(track.duration) if track.duration > 0 else ""
            self.store.append([i + 1, name, dur, track.filepath])

    def remove_track(self, index):
        self.parent_app.playlist.remove_index(index)
        self._refresh_view()


class AudioPlayerApp:
    UPDATE_INTERVAL_MS = 250

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

        self.backend = MpvBackend()
        self.playlist = Playlist()
        self.spectrum = SpectrumAnalyzer()
        self.playlist_window = None

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

        drawing_area = Gtk.DrawingArea()
        drawing_area.connect("draw", self._on_background_draw)
        main_overlay.add(drawing_area)

        self._controls_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._controls_container.set_margin_start(20)
        self._controls_container.set_margin_end(20)
        self._controls_container.set_margin_top(20)
        self._controls_container.set_margin_bottom(20)
        self._controls_container.set_app_paintable(True)
        self._controls_container.connect("draw", self._on_overlay_draw)
        main_overlay.add_overlay(self._controls_container)

        self._controls_container.pack_start(self._build_title_area(), False, False, 0)

        self._controls_container.pack_start(Gtk.Box(), True, True, 0)

        self._player_controls = self._build_overlay_controls()
        self._controls_container.pack_start(self._player_controls, False, False, 0)

    def _build_title_area(self):
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)

        self.time_label = Gtk.Label(label="0:00")
        self.time_label.get_style_context().add_class("time-display")
        self.time_label.set_halign(Gtk.Align.START)
        box.pack_start(self.time_label, False, False, 4)

        box.pack_start(Gtk.Box(), True, True, 0)

        self.title_area = Gtk.DrawingArea()
        self.title_area.set_size_request(-1, 40)
        self.title_area.set_margin_start(8)
        self.title_area.set_margin_end(8)
        self.title_area.connect("draw", self._on_title_draw)
        box.pack_start(self.title_area, True, True, 0)

        box.pack_start(Gtk.Box(), True, True, 0)

        self.artist_label = Gtk.Label(label="")
        self.artist_label.get_style_context().add_class("track-artist")
        self.artist_label.set_halign(Gtk.Align.END)
        self.artist_label.set_ellipsize(Pango.EllipsizeMode.END)
        box.pack_start(self.artist_label, False, False, 4)

        self._marquee_text = __app_name__
        self._marquee_offset = 0
        self._marquee_separator = "    ///    "
        self._tick_count = 0
        self._marquee_timer_id = GLib.timeout_add(33, self._on_marquee_tick)

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

    def _build_hamburger_menu(self):
        menu = Gtk.Menu()

        add_files_item = Gtk.MenuItem(label=self._t("add_files"))
        add_files_item.connect("activate", self._on_add_files_clicked)
        menu.append(add_files_item)

        add_folder_item = Gtk.MenuItem(label=self._t("add_folder"))
        add_folder_item.connect("activate", self._on_add_folder_clicked)
        menu.append(add_folder_item)

        menu.append(Gtk.SeparatorMenuItem())

        shuffle_item = Gtk.CheckMenuItem(label=self._t("shuffle"))
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

        repeat_item.set_submenu(repeat_submenu)
        menu.append(repeat_item)

        menu.append(Gtk.SeparatorMenuItem())

        playlist_item = Gtk.MenuItem(label=self._t("view_playlist"))
        playlist_item.connect("activate", self._on_view_playlist_clicked)
        menu.append(playlist_item)

        return menu

    def _on_menu_clicked(self, button):
        if hasattr(self, '_menu_popover') and self._menu_popover:
            self._menu_popover.popdown()
            self._menu_popover = None
            return
        
        self._menu_popover = Gtk.Popover()
        self._menu_popover.set_relative_to(button)
        
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        vbox.set_size_request(180, -1)
        
        add_files_btn = Gtk.ModelButton(label=self._t("add_files"))
        add_files_btn.connect("clicked", lambda b: (self._menu_popover.popdown(), self._on_add_files_clicked(None)))
        vbox.pack_start(add_files_btn, False, False, 0)
        
        add_folder_btn = Gtk.ModelButton(label=self._t("add_folder"))
        add_folder_btn.connect("clicked", lambda b: (self._menu_popover.popdown(), self._on_add_folder_clicked(None)))
        vbox.pack_start(add_folder_btn, False, False, 0)
        
        vbox.pack_start(Gtk.Separator(), False, False, 4)
        
        shuffle_btn = Gtk.ModelButton(label=self._t("shuffle"))
        shuffle_btn.connect("clicked", lambda b: (self._menu_popover.popdown(), self._on_shuffle_toggled(None)))
        vbox.pack_start(shuffle_btn, False, False, 0)
        
        repeat_btn = Gtk.ModelButton(label=self._t("repeat"))
        repeat_btn.connect("clicked", lambda b: (self._menu_popover.popdown(), self._cycle_repeat()))
        vbox.pack_start(repeat_btn, False, False, 0)
        
        vbox.pack_start(Gtk.Separator(), False, False, 4)
        
        playlist_btn = Gtk.ModelButton(label=self._t("view_playlist"))
        playlist_btn.connect("clicked", lambda b: (self._menu_popover.popdown(), self._on_view_playlist_clicked(None)))
        vbox.pack_start(playlist_btn, False, False, 0)
        
        self._menu_popover.add(vbox)
        self._menu_popover.show_all()
        self._menu_popover.popup()

    def _on_shuffle_toggled(self, item):
        self.playlist.toggle_shuffle()

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
        success = self.backend.play_file(track.filepath)
        if success:
            self.play_btn.get_child().set_text("\U000f03e4")
            self._update_track_display(track)
            self._update_playlist_highlight()
            self._update_status(self._t("playing"))

    def _on_update_tick(self):
        if not self.backend.is_playing and not self.backend.is_paused:
            if self.backend.current_file and self.backend.is_track_finished():
                self._on_track_finished()
            return True

        self.backend.update_state()

        if not self._seeking and self.backend.duration > 0:
            fraction = (self.backend.position / self.backend.duration) * 100
            self.seek_scale.set_value(fraction)
            self.time_label.set_text(format_time(self.backend.position))

        meta = self.backend.get_formatted_metadata()
        current_track = self.playlist.get_current_track()
        if current_track and meta.get("title"):
            self.playlist.update_track_metadata(current_track, meta)
            self._update_track_display(current_track)

        if current_track and self.backend.duration > 0:
            self.playlist.update_track_duration(current_track, self.backend.duration)
            self._update_playlist_highlight()

        if self.backend.is_track_finished():
            self._on_track_finished()

        return True

    def _on_track_finished(self):
        track = self.playlist.next_track()
        if track:
            self._play_current()
        else:
            self._on_stop_clicked(None)

    def _update_track_display(self, track):
        new_text = track.title or self._t("unknown_title")
        if new_text != self._marquee_text:
            self._marquee_text = new_text
            self._marquee_offset = 0
        if track.artist:
            self.artist_label.set_text(f"{track.artist}" + (f" — {track.album}" if track.album else ""))
        else:
            self.artist_label.set_text("")

    def _update_status(self, text):
        pass

    def _on_mouse_motion(self, widget, event):
        self._show_overlay()

    def _on_mouse_leave(self, widget, event):
        self._hide_overlay()

    def _show_overlay(self):
        self._overlay_visible = True
        self._player_controls.set_opacity(1)

    def _hide_overlay(self):
        self._overlay_visible = False
        self._player_controls.set_opacity(0)

    def _on_overlay_draw(self, widget, cr):
        alloc = widget.get_allocation()
        w = alloc.width
        h = alloc.height
        cr.set_source_rgba(22 / 255, 26 / 255, 33 / 255, 0.7)
        cr.paint()
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

                alpha = 0.06 + 0.08 * (seg / max(1, max_segments))
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

            cr.set_source_rgba(r, g, b, 0.2)
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
        font_desc = Pango.FontDescription.from_string("Doto 20")
        layout.set_font_description(font_desc)

        text = self._marquee_text
        layout.set_text(text, -1)
        text_width, text_height = layout.get_pixel_size()

        r, g, b = 136 / 255, 192 / 255, 208 / 255
        y = (height - text_height) / 2

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
        if self._update_timer_id:
            GLib.source_remove(self._update_timer_id)
            self._update_timer_id = None
        if self._marquee_timer_id:
            GLib.source_remove(self._marquee_timer_id)
            self._marquee_timer_id = None
        if self._overlay_timeout_id:
            GLib.source_remove(self._overlay_timeout_id)
        self.spectrum.stop()
        self.playlist.close()
        self.backend.cleanup()
