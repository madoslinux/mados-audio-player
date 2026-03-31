"""
Playlist Window Module
======================

Separate window for playlist management.
"""

import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango

from translations import get_text
from playlist import format_time


class PlaylistWindow(Gtk.Window):
    """Separate window for playlist management."""

    def __init__(self, parent_app):
        super().__init__()
        self.parent_app = parent_app
        self.set_title(parent_app._t("playlist"))
        self.set_default_size(400, 500)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_transient_for(parent_app.window)
        
        # Import app constants
        from __init__ import __app_id__, __app_name__
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
        col.set_expand(True)
        
        renderer = Gtk.CellRendererText()
        renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
        col.pack_start(renderer, True)
        col.add_attribute(renderer, "text", 1)
        
        self.view.append_column(col)

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
        self.parent_app._marquee_text = "madOS Audio Player"
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
