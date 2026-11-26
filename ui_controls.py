"""Native Tk buttons with visible keyboard shortcuts and rows that can wrap."""

import cv2
import numpy as np


PALETTES = {
    "normal": ("#29374b", "#f4f7fc", "#3b4c64", "#41536c"),
    "primary": ("#82edcf", "#142a27", "#a7f5e0", "#64c9af"),
    "remove": ("#56313d", "#fff0f1", "#704353", "#754653"),
}


def key_badge(tk, parent, key, background, foreground):
    def color(hex_value):
        rgb = [int(hex_value[index:index + 2], 16) for index in (1, 3, 5)]
        return (*reversed(rgb), 255)

    font, scale = cv2.FONT_HERSHEY_SIMPLEX, .49
    arrow = key in ("←", "→")
    text_width, text_height = (12, 10) if arrow else cv2.getTextSize(key, font, scale, 1)[0]
    height, width = 22, max(23, text_width + 11)
    badge = np.zeros((height, width, 4), np.uint8)
    fill = color(background)
    cv2.rectangle(badge, (3, 0), (width - 4, height - 1), fill, -1)
    cv2.rectangle(badge, (0, 3), (width - 1, height - 4), fill, -1)
    for x in (3, width - 4):
        for y in (3, height - 4):
            cv2.circle(badge, (x, y), 3, fill, -1)
    ink = color(foreground)
    if arrow:
        left, right = (5, height // 2), (width - 6, height // 2)
        start, end = (right, left) if key == "←" else (left, right)
        cv2.arrowedLine(badge, start, end, ink, 1, cv2.LINE_AA, tipLength=.42)
    else:
        cv2.putText(badge, key, ((width - text_width) // 2, (height + text_height) // 2),
                    font, scale, ink, 1, cv2.LINE_AA)
    _, encoded = cv2.imencode(".png", badge)
    return tk.PhotoImage(master=parent, data=encoded.tobytes(), format="png")


def set_button_label(button, label):
    text = f"{label}  " if button.cget("image") else label
    if button.cget("text") != text:
        button.configure(text=text)


def shortcut_button(tk, parent, label, key, command, *, tone="normal", space_action=None, large=False):
    background, foreground, hover, badge_background = PALETTES[tone]
    button = tk.Button(
        parent, command=command, compound="right", bd=0, relief="flat", takefocus=True,
        bg=background, fg=foreground, activebackground=hover, activeforeground=foreground,
        disabledforeground="#a2afc0", highlightthickness=1, highlightcolor="#82edcf",
        highlightbackground=parent.cget("bg"), padx=11, pady=8 if large else 6,
        font=("TkDefaultFont", 13 if large else 10, "bold"),
    )
    if key:
        button.key_badge = key_badge(tk, parent, key, badge_background, foreground)
        button.configure(image=button.key_badge)
    set_button_label(button, label)

    def enter(event):
        button.invoke()
        return "break"

    button.bind("<Return>", enter)
    button.bind("<KP_Enter>", enter)
    if space_action is not None:
        button.bind("<space>", space_action)
    return button


def choose_movie_speed(tk, parent, current):
    from tkinter import simpledialog

    minimum, maximum = 2, 32

    class SpeedDialog(simpledialog.Dialog):
        background = "#202a39"

        def body(self, panel):
            self.configure(bg=self.background)
            panel.configure(bg=self.background, padx=17, pady=12)
            self.speed = tk.IntVar(master=self, value=max(minimum, min(maximum, current)))
            self.readout = tk.StringVar(master=self)
            self.update_readout()
            tk.Label(panel, textvariable=self.readout, bg=self.background, fg="#f4f7fc",
                     font=("TkDefaultFont", 16, "bold")).pack()
            tk.Label(panel, text="Use the arrow keys or drag to change the speed.",
                     bg=self.background, fg="#bdcbe0").pack(pady=(4, 7))
            scale = tk.Scale(panel, from_=minimum, to=maximum, resolution=1, orient="horizontal",
                             tickinterval=6, showvalue=False, length=300, variable=self.speed,
                             command=self.update_readout, bg=self.background, fg="#f4f7fc",
                             troughcolor="#141a24", activebackground="#82edcf", highlightthickness=0)
            scale.pack(fill="x")
            labels = tk.Frame(panel, bg=self.background)
            labels.pack(fill="x")
            for text, side in (("Slower", "left"), ("Faster", "right")):
                tk.Label(labels, text=text, bg=self.background, fg="#bdcbe0").pack(side=side)
            return scale

        def update_readout(self, value=None):
            self.readout.set(f"{self.speed.get()} photos per second")

        def buttonbox(self):
            box = tk.Frame(self, bg=self.background)
            box.pack(fill="x", padx=17, pady=(0, 12))
            shortcut_button(tk, box, "Use Speed", "Enter", self.ok, tone="primary").pack(side="left")
            shortcut_button(tk, box, "Cancel", "Esc", self.cancel).pack(side="right")
            self.bind("<Return>", self.ok)
            self.bind("<KP_Enter>", self.ok)
            self.bind("<Escape>", self.cancel)

        def apply(self):
            self.result = self.speed.get()

    return SpeedDialog(parent, title="Movie Speed").result


class ButtonRow:
    def __init__(self, tk, parent, background):
        self.frame = tk.Frame(parent, bg=background, height=1)
        self.buttons = ()
        self.previous_layout = None
        self.frame.bind("<Configure>", self.arrange)

    def show(self, buttons):
        buttons = tuple(buttons)
        for button in self.buttons:
            if button not in buttons:
                button.place_forget()
        self.buttons = buttons
        self.arrange()

    def repaint(self):
        for button in self.buttons:
            # Tk schedules a display pass even if the background color stays the same.
            button.configure(background=button.cget("background"))

    def arrange(self, event=None):
        width = self.frame.winfo_width()
        if width <= 1:
            width = min(1014, self.frame.winfo_screenwidth() - 76)
        layout = (width, tuple((button, button.winfo_reqwidth(), button.winfo_reqheight()) for button in self.buttons))
        if layout == self.previous_layout:
            return
        self.previous_layout = layout
        x = y = line_height = 0
        for button, requested_width, height in layout[1]:
            if x and x + requested_width > width:
                x, y, line_height = 0, y + line_height + 6, 0
            button.place(x=x, y=y, width=min(requested_width, width), height=height)
            x += requested_width + 7
            line_height = max(line_height, height)
        self.frame.configure(height=max(1, y + line_height))
