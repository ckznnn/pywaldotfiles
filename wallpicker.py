#!/usr/bin/env python3
"""
wallpicker.py — Wayland-friendly wallpaper chooser + pywal invoker.

Features:
- Fixed square window (side = min(50% of screen width, 50% of screen height))
- Dynamic grid of thumbnails scaled so ALL fit in the window (no scrolling)
- Click a thumbnail -> runs `wal -i <image>`, `walcord`, sets wallpaper,
  updates Hyprland border color, and applies spicetify
- ESC closes, R refreshes
"""

import sys
import os
import math
import json
import subprocess
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QWidget, QGridLayout, QPushButton, QVBoxLayout
)
from PyQt6.QtGui import QPixmap, QIcon, QGuiApplication, QKeySequence, QShortcut
from PyQt6.QtCore import Qt, QSize

# ---- configuration ----
DEFAULT_DIR = "/home/harv/Wallpapers/"
SUPPORTED_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")
BORDER_COLOR = "color4"  # which pywal color to use for Hyprland border
# -----------------------


def find_images(folder):
    """Return a list of supported images in the folder."""
    p = Path(folder).expanduser()
    if not p.exists() or not p.is_dir():
        return []
    imgs = [str(f) for f in sorted(p.iterdir()) if f.suffix.lower() in SUPPORTED_EXTS]
    return imgs


def run_cmd(cmd):
    try:
        subprocess.run(cmd, check=True)
        return True
    except Exception:
        return False


def set_wallpaper_wayland(image_path):
    """Try several wallpaper setters until one succeeds."""
    if run_cmd(["swww", "img", image_path, "--output", "all"]):
        return True
    if run_cmd(["hyprpaper", "--set", image_path]):
        return True
    if run_cmd(["swaybg", "-i", image_path]):
        return True
    if run_cmd(["feh", "--bg-scale", image_path]):
        return True
    return False


def set_hyprland_border_from_wal():
    """Update Hyprland active border color based on pywal palette."""
    wal_colors = Path.home() / ".cache" / "wal" / "colors.json"
    if not wal_colors.exists():
        return

    try:
        with open(wal_colors) as f:
            data = json.load(f)

        # Pick one pywal color
        hexcol = data["colors"][BORDER_COLOR].lstrip("#")
        col = f"0x{hexcol.upper()}"

        subprocess.run(
            ["hyprctl", "keyword", "col.active_border", col],
            check=False
        )
    except Exception as e:
        print("Failed to set Hyprland border color:", e)


class WallPicker(QWidget):
    def __init__(self, image_dir):
        super().__init__()

        screen = QGuiApplication.primaryScreen()
        s = screen.size()
        side = int(min(s.width() * 0.5, s.height() * 0.5))

        self.setWindowTitle("WallPicker")
        self.setFixedSize(side, side)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        # add subtle outline to the main window
        self.setStyleSheet("background-color: #111; border: 2px solid #333; border-radius: 8px;")

        self_center_x = (s.width() - side) // 2
        self_center_y = (s.height() - side) // 2
        self.move(self_center_x, self_center_y)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(0)

        self.container = QWidget()
        vbox.addWidget(self.container)

        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.grid.setSpacing(4)

        self.image_dir = image_dir
        self.images = []
        self.populate()

    def clear_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def populate(self):
        self.images = find_images(self.image_dir)
        n = len(self.images)
        if n == 0:
            self.clear_grid()
            btn = QPushButton("No images found\n" + str(self.image_dir))
            btn.setEnabled(False)
            self.grid.addWidget(btn, 0, 0)
            return

        # calculate grid size
        cols = math.ceil(math.sqrt(n))
        rows = math.ceil(n / cols)

        self.clear_grid()

        # available area inside the window
        available_w = self.width() - (self.grid.contentsMargins().left() + self.grid.contentsMargins().right())
        available_h = self.height() - (self.grid.contentsMargins().top() + self.grid.contentsMargins().bottom())

        # size of each thumbnail so all fit
        thumb_side_w = (available_w - (cols - 1) * self.grid.spacing()) // cols
        thumb_side_h = (available_h - (rows - 1) * self.grid.spacing()) // rows
        thumb_side = min(thumb_side_w, thumb_side_h)

        for idx, imgpath in enumerate(self.images):
            row = idx // cols
            col = idx % cols

            btn = QPushButton()
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(os.path.basename(imgpath))

            pix = QPixmap(imgpath)
            if not pix.isNull():
                pix = pix.scaled(
                    thumb_side, thumb_side,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation
                ).copy(0, 0, thumb_side, thumb_side)

                icon = QIcon(pix)
                btn.setIcon(icon)
                btn.setIconSize(QSize(thumb_side, thumb_side))

            btn.setStyleSheet("""
                QPushButton {
                    border: 1px solid #444;
                    border-radius: 4px;
                    padding: 0px;
                    background-color: #222;
                }
                QPushButton:hover {
                    border: 1px solid #888;
                    background-color: #333;
                }
            """)

            btn.clicked.connect(lambda checked, p=imgpath: self.on_select(p))
            btn.setFixedSize(thumb_side, thumb_side)
            self.grid.addWidget(btn, row, col)

    def on_select(self, path):
        # Run pywal to generate colors
        subprocess.Popen(["wal", "-i", path])

        # Run walcord to update Discord (ignore if missing)
        try:
            subprocess.Popen(["walcord"])
        except FileNotFoundError:
            pass

        # Set wallpaper
        set_wallpaper_wayland(path)

        # Update Hyprland border color
        set_hyprland_border_from_wal()

        # Apply spicetify theme
        try:
            subprocess.Popen(["spicetify", "apply"])
        except FileNotFoundError:
            print("Spicetify not installed, skipping...")

    def refresh(self):
        self.populate()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Simple wallpaper chooser that also runs pywal -i <image>")
    parser.add_argument("folder", nargs="?", default=DEFAULT_DIR, help="folder containing wallpapers")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    w = WallPicker(args.folder)
    w.show()

    QShortcut(QKeySequence("Esc"), w, activated=w.close)
    QShortcut(QKeySequence("r"), w, activated=w.refresh)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
  
