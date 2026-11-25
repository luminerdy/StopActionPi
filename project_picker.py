"""Choose the movie folder when the desktop app starts."""

import tkinter as tk
from tkinter import filedialog, simpledialog
from pathlib import Path

from ui_controls import shortcut_button


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
        rows = min(len(self.recent), 6)
        width = min(680, root.winfo_screenwidth() - 36)
        height = min(245 + rows * 30, root.winfo_screenheight() - 76)
        root.geometry(f"{width}x{height}")
        root.protocol("WM_DELETE_WINDOW", self.finish)

        self.body = tk.Frame(root, padx=22, pady=18, bg="#202a39")
        self.body.pack(fill="both", expand=True)
        tk.Label(self.body, text="StopActionPi", font=("TkDefaultFont", 24, "bold"),
                 bg="#202a39", fg="#f4f7fc").pack(anchor="w")
        tk.Label(self.body, text="Pick the movie you want to keep working on." if self.recent else "Ready to make your first movie?",
                 font=("TkDefaultFont", 12), bg="#202a39", fg="#bdcbe0").pack(anchor="w", pady=(4, 12))

        self.listbox = None
        if self.recent:
            tk.Label(self.body, text="Recent Movies", font=("TkDefaultFont", 13, "bold"),
                     bg="#202a39", fg="#f4f7fc").pack(anchor="w", pady=(0, 4))
            recent_area = tk.Frame(self.body, bg="#202a39")
            recent_area.pack(fill="both", expand=True)
            scrollbar = tk.Scrollbar(recent_area, orient="vertical")
            if len(self.recent) > rows:
                scrollbar.pack(side="right", fill="y")
            self.listbox = tk.Listbox(recent_area, height=rows, exportselection=False, bg="#141a24", fg="#f4f7fc",
                                      selectbackground="#82edcf", selectforeground="#142a27", activestyle="none",
                                      font=("TkDefaultFont", 13), yscrollcommand=scrollbar.set)
            self.listbox.pack(side="left", expand=True, fill="both")
            scrollbar.configure(command=self.listbox.yview)
            for path in self.recent:
                self.listbox.insert("end", path.name)
            self.listbox.selection_set(0)
            self.listbox.activate(0)
            self.listbox.bind("<Double-Button-1>", lambda event: self.continue_movie())

        self.status = tk.Label(self.body, anchor="w", bg="#202a39", fg="#bdcbe0", wraplength=width - 48)
        self.status.pack(fill="x", pady=(5, 4))
        if self.listbox is not None:
            self.continue_button = shortcut_button(tk, self.body, "Continue Selected Movie", "Enter",
                                                   self.continue_movie, tone="primary", large=True)
            self.continue_button.pack(fill="x")
            self.listbox.bind("<<ListboxSelect>>", self.selection_changed)
            self.selection_changed()

        footer = tk.Frame(self.body, bg="#202a39")
        footer.pack(fill="x", pady=(10, 0))
        self.new_button = shortcut_button(tk, footer, "New Movie", "N", self.new_movie,
                                          tone="normal" if self.recent else "primary", large=not self.recent)
        self.new_button.pack(side="left", padx=(0, 8))
        shortcut_button(tk, footer, "Open Movie Folder", "O", self.open_folder).pack(side="left")
        shortcut_button(tk, footer, "Quit", "Esc", self.finish).pack(side="right")

        self.key_binding = root.bind("<KeyPress>", self.key_pressed)
        (self.listbox if self.listbox is not None else self.new_button).focus_set()

    def choose(self):
        self.root.wait_variable(self.done)
        self.root.unbind("<KeyPress>", self.key_binding)
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self.body.destroy()
        self.root.focus_set()
        return self.folder

    def finish(self, folder=None):
        self.folder = folder
        self.done.set(True)

    def selection_changed(self, event=None):
        selection = self.listbox.curselection()
        self.continue_button.configure(state="normal" if selection else "disabled")
        self.status.configure(text=f"Selected movie: {self.recent[selection[0]].name}" if selection else "Pick a movie from the list.")

    def continue_movie(self):
        if self.listbox is None:
            self.new_movie()
            return
        selection = self.listbox.curselection()
        if selection:
            folder = self.recent[selection[0]]
            if folder.is_dir():
                self.finish(folder)
            else:
                self.status.configure(text="That movie moved. Use Open Movie Folder to find it.")

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
