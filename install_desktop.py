"""Install StopActionPi in the app menu, on the desktop, and at desktop startup."""

import os
from pathlib import Path
import shutil
import subprocess
import sys


MANAGED = "# Managed by StopActionPi install_desktop.py"
APP_ENTRY = "stopactionpi.desktop"
OPEN_URI = "stopactionpi://open"
URI_TYPE = "x-scheme-handler/stopactionpi"


def desktop_arg(path):
    # The Desktop Entry specification escapes backslashes in both strings and Exec arguments.
    value = str(path).replace("%", "%%")
    for character in ('\\', '"', '`', '$'):
        value = value.replace(character, "\\" + character)
    return '"' + value.replace("\\", "\\\\") + '"'


def desktop_directory():
    home = Path.home()
    if shutil.which("xdg-user-dir"):
        configured = subprocess.check_output(["xdg-user-dir", "DESKTOP"], text=True).rstrip("\n")
        directory = Path(configured)
        if directory.is_absolute() and directory != home:
            return directory
    return home / "Desktop"


def install_desktop():
    if not shutil.which("gio"):
        raise ValueError("The desktop shortcut needs Gio. Install it with sudo apt install libglib2.0-bin.")
    project = Path(__file__).resolve().parent
    script = project / "stop_motion.py"
    if not script.is_file():
        raise FileNotFoundError(script)
    environment_python = project / ".venv" / "bin" / "python"
    python = environment_python if environment_python.is_file() else Path(sys.executable)
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    desktop_icon = desktop_directory() / APP_ENTRY
    app_launchers = (data / "applications" / APP_ENTRY, config / "autostart" / APP_ENTRY)
    working_directory = str(project).replace("\\", "\\\\")
    content = f"""{MANAGED}
[Desktop Entry]
Type=Application
Name=StopActionPi
Comment=Make a stop motion movie
Exec={desktop_arg(python)} {desktop_arg(script)}
Path={working_directory}
Icon=camera-photo
Terminal=false
Categories=AudioVideo;Video;
MimeType={URI_TYPE};
"""
    # PCManFM opens links through the app's URI handler without treating them as executable files.
    desktop_link = f"""{MANAGED}
[Desktop Entry]
Type=Link
Name=StopActionPi
Comment=Make a stop motion movie
Icon=camera-photo
URL={OPEN_URI}
"""
    for launcher in (*app_launchers, desktop_icon):
        if launcher.is_symlink() or (launcher.exists() and not launcher.read_text(encoding="utf-8").startswith(MANAGED)):
            raise ValueError(f"An existing launcher needs review: {launcher}")
    for launcher in app_launchers:
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text(content, encoding="utf-8")
        print(launcher)
    subprocess.run(["gio", "mime", URI_TYPE, APP_ENTRY], check=True)
    desktop_icon.parent.mkdir(parents=True, exist_ok=True)
    desktop_icon.write_text(desktop_link, encoding="utf-8")
    desktop_icon.chmod(0o644)
    print(desktop_icon)


if __name__ == "__main__":
    install_desktop()
