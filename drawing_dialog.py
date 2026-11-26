"""Draw freehand on a photo with a mouse or touchpad."""

import tkinter as tk
from tkinter import simpledialog

import cv2

from photo_drawings import MAX_POINTS, MAX_STROKES, THICKNESS, Stroke, draw_strokes
from photo_messages import PALETTE, draw_message
from ui_controls import shortcut_button


class DrawingDialog(simpledialog.Dialog):
    background = "#202a39"
    foreground = "#f4f7fc"

    def __init__(self, parent, photo, strokes, message, photo_image):
        height, width = photo.shape[:2]
        limits = (min(850, parent.winfo_screenwidth() - 50), min(510, parent.winfo_screenheight() - 225))
        scale = min(1, limits[0] / width, limits[1] / height)
        self.width, self.height = max(1, int(width * scale)), max(1, int(height * scale))
        self.photo = cv2.resize(photo, (self.width, self.height), interpolation=cv2.INTER_AREA)
        self.strokes = strokes
        self.message = message
        self.photo_image = photo_image
        self.history = []
        self.points = None
        self.color = strokes[-1].color if strokes else PALETTE["Yellow"]
        self.thickness = strokes[-1].thickness if strokes else "Medium"
        self.redraw_job = None
        super().__init__(parent, title="Draw on Photo")

    def label(self, parent, text="", **options):
        return tk.Label(parent, text=text, bg=self.background, fg=self.foreground, **options)

    def body(self, panel):
        self.configure(bg=self.background)
        self.resizable(False, False)
        panel.configure(bg=self.background, padx=7)

        controls = tk.Frame(panel, bg=self.background)
        controls.pack(fill="x")
        self.color_label = self.label(controls, width=15, anchor="w")
        self.color_label.grid(row=0, column=0, sticky="w")
        swatches = tk.Frame(controls, bg=self.background)
        swatches.grid(row=0, column=1, sticky="w")
        self.swatches = {}
        for color in PALETTE.values():
            button = tk.Button(
                swatches, width=2, bg=color, activebackground=color,
                command=lambda color=color: self.set_color(color),
            )
            button.pack(side="left", padx=(0, 4))
            self.swatches[color] = button

        self.label(controls, "Thickness").grid(row=1, column=0, sticky="w")
        widths = tk.Frame(controls, bg=self.background)
        widths.grid(row=1, column=1, sticky="w", pady=(3, 5))
        self.width_buttons = {}
        for name, pixels in zip(THICKNESS, (1, 3, 6)):
            sample = tk.PhotoImage(master=self, width=20, height=10)
            top = (10 - pixels) // 2
            sample.put("#263649", to=(0, top, 20, top + pixels))
            button = tk.Button(
                widths, text=name, image=sample, compound="left", padx=5,
                command=lambda name=name: self.set_thickness(name),
            )
            button.sample = sample
            button.pack(side="left", padx=(0, 4))
            self.width_buttons[name] = button

        self.canvas = tk.Canvas(
            panel, width=self.width, height=self.height, bg="#141a24",
            highlightthickness=0, cursor="crosshair", takefocus=True,
        )
        self.canvas.pack()
        self.canvas_photo = self.canvas.create_image(0, 0, anchor="nw")
        self.canvas.bind("<ButtonPress-1>", self.start_stroke)
        self.canvas.bind("<B1-Motion>", self.extend_stroke)
        self.canvas.bind("<ButtonRelease-1>", self.finish_stroke)
        self.status = self.label(panel, "Drag on the picture to draw.", anchor="w")
        self.status.pack(fill="x", pady=(4, 0))
        self.set_color(self.color)
        self.set_thickness(self.thickness)
        self.ink_preview = draw_strokes(self.photo, self.strokes)
        self.redraw()
        return self.canvas

    def buttonbox(self):
        box = tk.Frame(self, bg=self.background, padx=12, pady=6)
        box.pack(fill="x")
        shortcut_button(tk, box, "Save Drawing", "Enter", self.ok, tone="primary").pack(side="left")
        self.undo_button = shortcut_button(tk, box, "Undo", "Ctrl+Z", self.undo)
        self.undo_button.pack(side="left", padx=6)
        self.clear_button = shortcut_button(tk, box, "Clear Drawing", None, self.clear, tone="remove")
        self.clear_button.pack(side="left")
        shortcut_button(tk, box, "Cancel", "Esc", self.cancel).pack(side="right")
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        self.bind("<Control-z>", self.undo_from_key)
        self.update_buttons()

    def set_color(self, color):
        self.color = color
        name = next(name for name, value in PALETTE.items() if value == color)
        self.color_label.configure(text=f"Color · {name}")
        for value, button in self.swatches.items():
            button.configure(relief="sunken" if color == value else "raised")

    def set_thickness(self, name):
        self.thickness = name
        for value, button in self.width_buttons.items():
            button.configure(relief="sunken" if name == value else "raised")

    def point(self, event):
        x = max(0, min(self.width - 1, event.x))
        y = max(0, min(self.height - 1, event.y))
        return round(x / max(1, self.width - 1), 5), round(y / max(1, self.height - 1), 5)

    def start_stroke(self, event):
        if len(self.strokes) >= MAX_STROKES:
            self.status.configure(text="Drawing is full. Undo a stroke or clear it to keep drawing.")
            return
        self.canvas.focus_set()
        self.points = [self.point(event)]
        self.stroke_color = self.color
        self.stroke_thickness = self.thickness
        self.queue_redraw()

    def extend_stroke(self, event):
        point = self.point(event)
        if self.points is not None and point != self.points[-1] and len(self.points) < MAX_POINTS:
            self.points.append(point)
            self.queue_redraw()

    def active_stroke(self):
        return Stroke(self.stroke_color, self.stroke_thickness, tuple(self.points))

    def finish_stroke(self, event):
        if self.points is not None:
            self.extend_stroke(event)
            stroke = self.active_stroke()
            self.points = None
            self.change_strokes((*self.strokes, stroke))

    def queue_redraw(self):
        if self.redraw_job is None:
            self.redraw_job = self.after(16, self.redraw)

    def redraw(self):
        self.redraw_job = None
        preview = self.ink_preview
        if self.points is not None:
            preview = draw_strokes(preview, (self.active_stroke(),))
        preview = draw_message(preview, self.message)
        self.canvas.image = self.photo_image(preview, self.width, self.height)
        self.canvas.itemconfigure(self.canvas_photo, image=self.canvas.image)

    def change_strokes(self, strokes):
        self.history.append(self.strokes)
        self.strokes = strokes
        self.refresh_drawing()

    def undo(self):
        if self.points is not None:
            self.points = None
            self.queue_redraw()
            return
        if self.history:
            self.strokes = self.history.pop()
            self.refresh_drawing()

    def undo_from_key(self, event):
        self.undo()
        return "break"

    def clear(self):
        if self.strokes:
            self.change_strokes(())
            self.status.configure(text="Drawing cleared in the preview. Save to keep this change.")

    def refresh_drawing(self):
        self.ink_preview = draw_strokes(self.photo, self.strokes)
        self.queue_redraw()
        self.update_buttons()
        self.status.configure(text="Drag on the picture to draw.")

    def update_buttons(self):
        self.undo_button.configure(state="normal" if self.history else "disabled")
        self.clear_button.configure(state="normal" if self.strokes else "disabled")

    def apply(self):
        self.result = self.strokes if self.points is None else (*self.strokes, self.active_stroke())

    def destroy(self):
        if self.redraw_job is not None:
            self.after_cancel(self.redraw_job)
            self.redraw_job = None
        super().destroy()
