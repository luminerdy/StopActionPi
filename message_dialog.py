"""The photo-message editor used from the studio's review controls."""

import tkinter as tk
from tkinter import simpledialog

from photo_messages import MAX_SECONDS, MAX_TEXT, PALETTE, STYLES, PhotoMessage, contrast, draw_message
from ui_controls import shortcut_button


class MessageDialog(simpledialog.Dialog):
    background = "#202a39"
    foreground = "#f4f7fc"

    def __init__(self, parent, photo, message, photo_image):
        self.photo = photo
        self.original = message
        self.initial = message or PhotoMessage()
        self.photo_image = photo_image
        self.preview_job = None
        self.colors = {"text_color": self.initial.text_color, "background": self.initial.background}
        self.swatches = {}
        self.color_labels = {}
        super().__init__(parent, title="Edit Message" if message else "Add Message")

    def label(self, parent, text="", **options):
        return tk.Label(parent, text=text, bg=self.background, fg=self.foreground, **options)

    def body(self, panel):
        self.configure(bg=self.background)
        panel.configure(bg=self.background, padx=8)
        self.preview = self.label(panel)
        self.preview.pack()
        self.message = tk.Text(
            panel, height=3, width=44, wrap="word", padx=7, pady=5, undo=True,
            font=("TkDefaultFont", 12), bg="#141a24", fg=self.foreground, insertbackground=self.foreground,
        )
        self.message.pack(fill="x", pady=(5, 3))
        self.message.insert("1.0", self.initial.text)
        self.message.mark_set("insert", "end-1c")
        self.message.edit_modified(False)
        self.message.bind("<<Modified>>", self.text_changed)
        self.message.bind("<Control-Return>", self.save_from_text)

        settings = tk.Frame(panel, bg=self.background)
        settings.pack(fill="x", pady=3)
        self.label(settings, "Show for").pack(side="left")
        self.seconds = tk.StringVar(master=self, value=str(self.initial.seconds))
        tk.Spinbox(settings, from_=1, to=MAX_SECONDS, textvariable=self.seconds, width=4).pack(side="left", padx=4)
        self.label(settings, "seconds").pack(side="left")
        self.position = tk.StringVar(master=self, value=self.initial.position)
        for position in ("Bottom", "Top"):
            tk.Radiobutton(
                settings, text=position, value=position, variable=self.position, command=self.queue_preview,
                bg=self.background, fg=self.foreground, activebackground=self.background,
                activeforeground=self.foreground, selectcolor="#141a24",
            ).pack(side="right")

        palette = tk.Frame(panel, bg=self.background)
        palette.pack(fill="x", pady=(3, 0))
        self.label(palette, "Styles").grid(row=0, column=0, sticky="w", padx=(0, 5))
        styles = tk.Frame(palette, bg=self.background)
        styles.grid(row=0, column=1, sticky="w")
        for name, (ink, paper) in STYLES.items():
            tk.Button(
                styles, text=name, bg=paper, fg=ink, activebackground=paper, activeforeground=ink,
                command=lambda name=name: self.set_style(name),
            ).pack(side="left", padx=(0, 4))
        for row, (field, title) in enumerate((("text_color", "Text Color"), ("background", "Background Color")), 1):
            self.label(palette, title).grid(row=row, column=0, sticky="w", pady=2)
            swatch_row = tk.Frame(palette, bg=self.background)
            swatch_row.grid(row=row, column=1, sticky="w", pady=2)
            self.swatches[field] = {}
            for name, color in PALETTE.items():
                button = tk.Button(
                    swatch_row, width=2, bg=color, activebackground=color,
                    command=lambda field=field, color=color: self.set_color(field, color),
                )
                button.pack(side="left", padx=(0, 3))
                self.swatches[field][color] = button
            label = self.label(swatch_row, width=9, anchor="w")
            label.pack(side="left")
            self.color_labels[field] = label

        hint_row = tk.Frame(panel, bg=self.background)
        hint_row.pack(fill="x")
        self.hint = self.label(hint_row)
        self.hint.pack(side="left")
        self.fix_color = shortcut_button(tk, hint_row, "", None, self.improve_contrast)
        self.fix_color.pack(side="right")
        self.status = self.label(panel, anchor="w")
        self.status.pack(fill="x")
        self.refresh_colors()
        self.refresh_preview()
        return self.message

    def buttonbox(self):
        box = tk.Frame(self, bg=self.background, padx=12, pady=6)
        box.pack(fill="x")
        shortcut_button(tk, box, "Save Message", None, self.ok, tone="primary").pack(side="left")
        if self.original is not None:
            shortcut_button(tk, box, "Remove Message", None, self.remove, tone="remove").pack(side="left", padx=7)
        shortcut_button(tk, box, "Cancel", "Esc", self.cancel).pack(side="right")
        self.bind("<Control-Return>", self.ok)
        self.bind("<Escape>", self.cancel)

    def text_changed(self, event):
        if self.message.edit_modified():
            self.message.edit_modified(False)
            self.queue_preview()

    def queue_preview(self):
        if self.preview_job is not None:
            self.after_cancel(self.preview_job)
        self.preview_job = self.after(45, self.refresh_preview)

    def current_text(self):
        return self.message.get("1.0", "end-1c").strip()

    def refresh_preview(self):
        self.preview_job = None
        text = self.current_text()
        preview = PhotoMessage(text[:MAX_TEXT], position=self.position.get(), **self.colors)
        self.preview.image = self.photo_image(draw_message(self.photo, preview), 430, 230)
        self.preview.configure(image=self.preview.image)
        self.status.configure(text=f"{len(text)} / {MAX_TEXT} characters")

    def set_style(self, name):
        self.colors["text_color"], self.colors["background"] = STYLES[name]
        self.refresh_colors()
        self.queue_preview()

    def set_color(self, field, color):
        self.colors[field] = color
        self.refresh_colors()
        self.queue_preview()

    def refresh_colors(self):
        for field, value in self.colors.items():
            for name, color in PALETTE.items():
                self.swatches[field][color].configure(relief="sunken" if color == value else "raised")
                if color == value:
                    self.color_labels[field].configure(text=name)
        paper = self.colors["background"]
        low_contrast = contrast(self.colors["text_color"], paper) < 4.5
        self.recommended = max(("Black", "White"), key=lambda name: contrast(PALETTE[name], paper))
        self.hint.configure(text="Hard to read?" if low_contrast else "")
        self.fix_color.configure(
            text=f"Use {self.recommended} Text" if low_contrast else "", state="normal" if low_contrast else "disabled",
            width=14, bg="#29374b" if low_contrast else self.background,
        )

    def improve_contrast(self):
        self.set_color("text_color", PALETTE[self.recommended])

    def save_from_text(self, event):
        self.ok()
        return "break"

    def validate(self):
        try:
            seconds = int(self.seconds.get())
        except ValueError:
            self.status.configure(text=f"Enter a whole number from 1 to {MAX_SECONDS}.")
            return False
        message = PhotoMessage(self.current_text(), seconds, self.position.get(), **self.colors)
        try:
            message.validate()
        except ValueError as error:
            self.status.configure(text=str(error))
            return False
        self.result = (message,)
        return True

    def remove(self):
        self.result = (None,)
        self.cancel()

    def destroy(self):
        if self.preview_job is not None:
            self.after_cancel(self.preview_job)
            self.preview_job = None
        super().destroy()
