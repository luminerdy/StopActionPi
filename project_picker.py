"""Choose the movie folder when the desktop app starts."""

import tkinter as tk
from tkinter import filedialog, simpledialog
from pathlib import Path


class ProjectPicker:
    def __init__(self, root, projects):
        self.root = root
        self.projects = projects
        self.folder = None
        self.done = tk.BooleanVar(master=root, value=False)
        self.recent = sorted(
            (path for path in projects.iterdir() if path.is_dir() and not path.name.startswith(".")),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

        root.title("StopActionPi")
        root.geometry(f"{min(680, root.winfo_screenwidth() - 36)}x{min(490, root.winfo_screenheight() - 76)}")
        root.protocol("WM_DELETE_WINDOW", self.finish)

        self.body = tk.Frame(root, padx=22, pady=18, bg="#202a39")
        self.body.pack(fill="both", expand=True)
        tk.Label(self.body, text="StopActionPi", font=("TkDefaultFont", 24, "bold"),
                 bg="#202a39", fg="#f4f7fc").pack(anchor="w")
        tk.Label(self.body, text="Choose a movie to continue or start a new one.",
                 font=("TkDefaultFont", 12), bg="#202a39", fg="#bdcbe0").pack(anchor="w", pady=(4, 12))

        actions = tk.Frame(self.body, bg="#202a39")
        actions.pack(fill="x", pady=(0, 12))
        for label, command in (("N  New Movie", self.new_movie), ("O  Open Folder", self.open_folder)):
            tk.Button(actions, text=label, command=command, padx=12, pady=6,
                      font=("TkDefaultFont", 13, "bold")).pack(side="left", padx=(0, 8))

        tk.Label(self.body, text="Recent projects", font=("TkDefaultFont", 13, "bold"),
                 bg="#202a39", fg="#f4f7fc").pack(anchor="w", pady=(0, 4))
        recent_area = tk.Frame(self.body, bg="#202a39")
        recent_area.pack(fill="both", expand=True)
        scrollbar = tk.Scrollbar(recent_area, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        self.listbox = tk.Listbox(recent_area, height=6, exportselection=False,
                                  font=("TkDefaultFont", 13), yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", expand=True, fill="both")
        scrollbar.configure(command=self.listbox.yview)
        for path in self.recent:
            self.listbox.insert("end", path.name)
        if self.recent:
            self.listbox.selection_set(0)
            self.listbox.activate(0)
        self.listbox.bind("<Double-Button-1>", lambda event: self.continue_movie())

        footer = tk.Frame(self.body, bg="#202a39")
        footer.pack(fill="x", pady=(10, 0))
        tk.Button(footer, text="Enter  Continue", command=self.continue_movie,
                  state="normal" if self.recent else "disabled").pack(side="left")
        tk.Button(footer, text="Esc  Quit", command=self.finish).pack(side="right")
        self.status = tk.Label(self.body, text="Use the arrow keys to choose a recent project."
                               if self.recent else "Press N to make your first movie.",
                               anchor="w", bg="#202a39", fg="#bdcbe0", wraplength=500)
        self.status.pack(fill="x", pady=(6, 0))

        self.key_binding = root.bind("<KeyPress>", self.key_pressed)
        self.listbox.focus_set()

    def choose(self):
        self.root.wait_variable(self.done)
        self.root.unbind("<KeyPress>", self.key_binding)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self.body.destroy()
        return self.folder

    def finish(self, folder=None):
        self.folder = folder
        self.done.set(True)

    def continue_movie(self):
        selection = self.listbox.curselection()
        if selection:
            folder = self.recent[selection[0]]
            if folder.is_dir():
                self.finish(folder)
            else:
                self.status.configure(text="That project moved. Use Open Folder to find it.")
        elif not self.recent:
            self.new_movie()

    def new_movie(self):
        name = simpledialog.askstring("New Movie", "Give your movie a name.", parent=self.root)
        if name is None:
            return
        name = name.strip()
        if not name or name.startswith(".") or any(char in '/\\:*?\"<>|' or ord(char) < 32 for char in name):
            self.status.configure(text="Use a movie name with letters, numbers, or spaces.")
            return
        folder = self.projects / name
        try:
            folder.mkdir()
        except FileExistsError:
            self.status.configure(text="That movie name is already in use. Choose a new name or open its folder.")
        except OSError:
            self.status.configure(text="Could not create the movie folder. Try a shorter name or check available space.")
        else:
            self.finish(folder)

    def open_folder(self):
        folder = filedialog.askdirectory(title="Open a Movie Folder", parent=self.root,
                                          initialdir=self.projects, mustexist=True)
        if folder:
            self.finish(Path(folder))

    def key_pressed(self, event):
        action = {
            "n": self.new_movie, "o": self.open_folder, "return": self.continue_movie,
            "kp_enter": self.continue_movie, "escape": self.finish,
        }.get(event.keysym.lower())
        if action is not None:
            action()
            return "break"
