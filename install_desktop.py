"""Install StopActionPi in the app menu, on the desktop, and at desktop startup."""

import os
from pathlib import Path
import shutil
import subprocess
import sys


MANAGED = "# Managed by StopActionPi install_desktop.py"


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
    project = Path(__file__).resolve().parent
    script = project / "stop_motion.py"
    if not script.is_file():
        raise FileNotFoundError(script)
    environment_python = project / ".venv" / "bin" / "python"
    python = environment_python if environment_python.is_file() else Path(sys.executable)
    data = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    desktop_icon = desktop_directory() / "stopactionpi.desktop"
    launchers = (data / "applications" / "stopactionpi.desktop", config / "autostart" / "stopactionpi.desktop", desktop_icon)
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
"""
    for launcher in launchers:
        if launcher.is_symlink() or (launcher.exists() and not launcher.read_text(encoding="utf-8").startswith(MANAGED)):
            raise ValueError(f"An existing launcher needs review: {launcher}")
    for launcher in launchers:
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text(content, encoding="utf-8")
        if launcher == desktop_icon:
            launcher.chmod(0o755)
        print(launcher)


if __name__ == "__main__":
    install_desktop()
