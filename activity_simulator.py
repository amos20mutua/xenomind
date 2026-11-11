from __future__ import annotations

import time
import uuid
from datetime import datetime
from math import cos, pi, sin, sqrt
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from simulation_core import (
    SCENARIOS,
    ScenarioEngine,
    SimulationEvent,
    append_event,
    control_event,
)


BG = "#05080f"
PANEL = "#0b111c"
PANEL_LIGHT = "#121d2b"
SURFACE = "#070d16"
BORDER = "#1b2b3c"
TEXT = "#e7f5ff"
MUTED = "#71869b"
ACCENT = "#69ffe2"
BLUE = "#78baff"
DANGER = "#ff718e"
PURPLE = "#d184ff"


class ActivitySimulator(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("XENOMIND // Neural Interface")
        self.geometry("1440x920")
        self.minsize(1120, 720)
        self.configure(background=BG)
        self.protocol("WM_DELETE_WINDOW", self._close)

        self.state = "READY"
        self.session_id: str | None = None
        self.scenario_name = ""
        self.engine: ScenarioEngine | None = None
        self.output_path: Path | None = None
        self.sequence = 0
        self.event_count = 0
        self.elapsed = 0.0
        self.duration_seconds = 0.0
        self.event_interval = 0.0
        self.next_event_in = 0.0
        self.events_since_break = 0
        self.break_after = 0
        self.break_duration = 0.0
        self.break_remaining = 0.0
        self.last_tick = time.monotonic()
        self._neural_phase = 0.0
        self._activity_level = 0.0
        self._configure_styles()
        self._build_ui()
        self._refresh_state()
        self.after(70, self._animate_neural_core)
        self.after(200, self._tick)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure(
            "Inset.TFrame",
            background=SURFACE,
            relief="flat",
        )
        style.configure(
            "TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10)
        )
        style.configure(
            "Panel.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 10)
        )
        style.configure(
            "Inset.TLabel", background=SURFACE, foreground=TEXT, font=("Segoe UI", 10)
        )
        style.configure(
            "Title.TLabel",
            background=BG,
            foreground=TEXT,
            font=("Segoe UI", 25, "bold"),
        )
        style.configure(
            "Eyebrow.TLabel",
            background=BG,
            foreground=ACCENT,
            font=("Segoe UI", 9, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background=BG,
            foreground=MUTED,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Section.TLabel",
            background=PANEL,
            foreground=TEXT,
            font=("Segoe UI", 12, "bold"),
        )
        style.configure(
            "Muted.TLabel",
            background=PANEL,
            foreground=MUTED,
            font=("Segoe UI", 9),
        )
        style.configure(
            "SidebarMuted.TLabel",
            background=PANEL,
            foreground=MUTED,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Status.TLabel",
            background="#142a2a",
            foreground=ACCENT,
            font=("Segoe UI", 9, "bold"),
            padding=(11, 7),
        )
        style.configure("TButton", font=("Segoe UI", 9, "bold"), padding=(10, 8))
        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#071711",
            borderwidth=0,
            padding=(13, 9),
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#83f0d0"), ("disabled", "#315348")],
            foreground=[("disabled", "#97afa8")],
        )
        style.configure(
            "Secondary.TButton",
            background=PANEL_LIGHT,
            foreground=TEXT,
            borderwidth=0,
        )
        style.map("Secondary.TButton", background=[("active", "#24344c")])
        style.configure(
            "Danger.TButton",
            background="#38212a",
            foreground="#ffaaaa",
            borderwidth=0,
        )
        style.map("Danger.TButton", background=[("active", "#4b2934")])
        style.configure(
            "TEntry",
            fieldbackground=SURFACE,
            foreground=TEXT,
            insertcolor=TEXT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=(8, 7),
        )
        style.configure(
            "TSpinbox",
            fieldbackground=SURFACE,
            foreground=TEXT,
            arrowcolor=MUTED,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=(6, 5),
        )
        style.configure(
            "TCombobox",
            fieldbackground=SURFACE,
            background=SURFACE,
            foreground=TEXT,
            arrowcolor=MUTED,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=(7, 6),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", SURFACE)],
            foreground=[("readonly", TEXT)],
            selectbackground=[("readonly", SURFACE)],
            selectforeground=[("readonly", TEXT)],
        )
        style.configure(
            "Treeview",
            background=PANEL,
            fieldbackground=PANEL,
            foreground=TEXT,
            rowheight=42,
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background=PANEL,
            foreground=MUTED,
            relief="flat",
            font=("Segoe UI", 8, "bold"),
            padding=(8, 10),
        )
        style.map(
            "Treeview",
            background=[("selected", "#20334b")],
            foreground=[("selected", TEXT)],
        )
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor=SURFACE,
            background=ACCENT,
            bordercolor=SURFACE,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            thickness=5,
        )

    def _build_ui(self) -> None:
        page = ttk.Frame(self, padding=(26, 22))
        page.pack(fill="both", expand=True)
        page.columnconfigure(1, weight=1)
        page.rowconfigure(1, weight=1)

        header = ttk.Frame(page)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 24))
        brand = ttk.Frame(header)
        brand.pack(side="left")
        brand_mark = tk.Canvas(
            brand, width=38, height=38, background=BG, highlightthickness=0
        )
        brand_mark.pack(side="left", padx=(0, 11))
        brand_mark.create_rectangle(2, 2, 36, 36, fill="#17312e", outline="")
        brand_mark.create_line(11, 19, 17, 25, fill=ACCENT, width=2)
        brand_mark.create_line(17, 25, 28, 12, fill=ACCENT, width=2)
        brand_copy = ttk.Frame(brand)
        brand_copy.pack(side="left")
        ttk.Label(brand_copy, text="X E N O M I N D", style="Eyebrow.TLabel").pack(
            anchor="w"
        )
        ttk.Label(
            brand_copy,
            text="Neural interface",
            style="Panel.TLabel",
            font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", pady=(1, 0))
        header_right = ttk.Frame(header)
        header_right.pack(side="right")
        ttk.Label(
            header_right,
            text="ISOLATED SIGNAL",
            style="SidebarMuted.TLabel",
            padding=(0, 0, 12, 0),
        ).pack(side="left")
        self.header_status = ttk.Label(
            header_right,
            text="READY",
            style="Status.TLabel",
        )
        self.header_status.pack(side="left")

        content = ttk.Frame(page)
        content.grid(row=1, column=0, columnspan=2, sticky="nsew")
        content.columnconfigure(0, weight=0)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        settings = ttk.Frame(content, style="Panel.TFrame", padding=20)
        settings.grid(row=0, column=0, sticky="nsw", padx=(0, 20))
        settings.configure(width=300)
        settings.grid_propagate(False)
        self._build_settings(settings)

        dashboard = ttk.Frame(content)
        dashboard.grid(row=0, column=1, sticky="nsew")
        dashboard.columnconfigure(0, weight=1)
        dashboard.rowconfigure(4, weight=1)
        self._build_dashboard(dashboard)

    def _build_settings(self, parent: ttk.Frame) -> None:
        heading = ttk.Frame(parent, style="Panel.TFrame")
        heading.pack(fill="x")
        ttk.Label(
            heading,
            text="CORE CONFIGURATION",
            style="SidebarMuted.TLabel",
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w", pady=(1, 6))
        ttk.Label(
            heading, text="Shape a signal", style="Section.TLabel"
        ).pack(
            anchor="w", pady=(0, 18)
        )

        form_frame = ttk.Frame(parent, style="Panel.TFrame")
        form_frame.pack(fill="both", expand=True, pady=(0, 12))
        form_canvas = tk.Canvas(
            form_frame,
            background=PANEL,
            highlightthickness=0,
            borderwidth=0,
        )
        form_scrollbar = ttk.Scrollbar(
            form_frame, orient="vertical", command=form_canvas.yview
        )
        form_canvas.configure(yscrollcommand=form_scrollbar.set)
        form_canvas.pack(side="left", fill="both", expand=True)
        form_scrollbar.pack(side="right", fill="y")
        body = ttk.Frame(form_canvas, style="Panel.TFrame")
        body_window = form_canvas.create_window(
            (0, 0), window=body, anchor="nw"
        )
        body.bind(
            "<Configure>",
            lambda _event: form_canvas.configure(
                scrollregion=form_canvas.bbox("all")
            ),
        )
        form_canvas.bind(
            "<Configure>",
            lambda event: form_canvas.itemconfigure(
                body_window, width=event.width
            ),
        )

        self.scenario_var = tk.StringVar(value="First Contact")
        self.duration_var = tk.StringVar(value="1")
        self.interval_var = tk.StringVar(value="3")
        self.break_after_var = tk.StringVar(value="5")
        self.break_duration_var = tk.StringVar(value="10")
        self.seed_var = tk.StringVar(value="42")
        self.path_var = tk.StringVar(
            value=str(
                Path.cwd()
                / f"synthetic-run-{datetime.now().strftime('%Y%m%d-%H%M%S')}.jsonl"
            )
        )

        self._field_label(body, "NEURAL PROTOCOL")
        ttk.Combobox(
            body,
            textvariable=self.scenario_var,
            values=tuple(SCENARIOS),
            state="readonly",
        ).pack(fill="x", pady=(6, 16))

        self._field_label(body, "CORE CYCLE")
        duration_row = ttk.Frame(body, style="Panel.TFrame")
        duration_row.pack(fill="x", pady=(6, 16))
        ttk.Spinbox(
            duration_row, from_=1, to=120, textvariable=self.duration_var, width=8
        ).pack(side="left")
        ttk.Label(duration_row, text="minutes", style="SidebarMuted.TLabel").pack(
            side="left", padx=(9, 0)
        )

        self._field_label(body, "PULSE INTERVAL")
        interval_row = ttk.Frame(body, style="Panel.TFrame")
        interval_row.pack(fill="x", pady=(6, 16))
        ttk.Spinbox(
            interval_row, from_=1, to=60, textvariable=self.interval_var, width=8
        ).pack(side="left")
        ttk.Label(
            interval_row, text="seconds", style="SidebarMuted.TLabel"
        ).pack(side="left", padx=(9, 0))

        ttk.Separator(body).pack(fill="x", pady=(1, 16))
        ttk.Label(body, text="Quiet intervals", style="Panel.TLabel").pack(
            anchor="w", pady=(0, 4)
        )
        self._field_label(body, "Rest every N pulses (0 disables)")
        ttk.Spinbox(
            body, from_=0, to=50, textvariable=self.break_after_var, width=8
        ).pack(anchor="w", pady=(6, 12))

        self._field_label(body, "REST DURATION")
        break_row = ttk.Frame(body, style="Panel.TFrame")
        break_row.pack(fill="x", pady=(6, 13))
        ttk.Spinbox(
            break_row,
            from_=1,
            to=300,
            textvariable=self.break_duration_var,
            width=8,
        ).pack(side="left")
        ttk.Label(
            break_row, text="seconds", style="SidebarMuted.TLabel"
        ).pack(side="left", padx=(9, 0))

        self._field_label(body, "REPLAY SIGNATURE")
        ttk.Spinbox(
            body,
            from_=0,
            to=2147483647,
            textvariable=self.seed_var,
            width=14,
        ).pack(anchor="w", pady=(6, 5))
        ttk.Label(
            body,
            text="Reuse a signature to replay the same signal sequence.",
            style="SidebarMuted.TLabel",
            wraplength=250,
        ).pack(anchor="w", pady=(0, 14))

        ttk.Separator(body).pack(fill="x", pady=(1, 14))
        self._field_label(body, "SIGNAL TRACE")
        output_row = ttk.Frame(body, style="Panel.TFrame")
        output_row.pack(fill="x", pady=(6, 0))
        ttk.Entry(output_row, textvariable=self.path_var).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(
            output_row, text="...", style="Secondary.TButton", command=self._browse
        ).pack(side="left", padx=(6, 0))

        ttk.Label(
            body,
            text="A contained intelligence",
            style="Panel.TLabel",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", pady=(20, 4))
        ttk.Label(
            body,
            text="An artful neural visualization. Synthetic signals only; no external control.",
            style="SidebarMuted.TLabel",
            wraplength=252,
            justify="left",
        ).pack(anchor="w")

        controls = ttk.Frame(parent, style="Panel.TFrame")
        controls.pack(side="bottom", fill="x", pady=(16, 0))
        self.start_button = ttk.Button(
            controls,
            text="Awaken the core",
            style="Accent.TButton",
            command=self._start_or_resume,
        )
        self.start_button.pack(fill="x", pady=(0, 7))
        button_row = ttk.Frame(controls, style="Panel.TFrame")
        button_row.pack(fill="x")
        self.pause_button = ttk.Button(
            button_row,
            text="Suspend",
            style="Secondary.TButton",
            command=self._pause,
        )
        self.pause_button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.stop_button = ttk.Button(
            button_row,
            text="Dissolve",
            style="Danger.TButton",
            command=self._stop,
        )
        self.stop_button.pack(side="left", fill="x", expand=True, padx=(4, 0))

    def _field_label(self, parent: ttk.Frame, text: str) -> None:
        ttk.Label(
            parent,
            text=text,
            style="SidebarMuted.TLabel",
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w")

    def _build_dashboard(self, parent: ttk.Frame) -> None:
        intro = ttk.Frame(parent)
        intro.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 19))
        intro.columnconfigure(0, weight=1)
        ttk.Label(intro, text="COGNITIVE INTERFACE  /  FORM UNKNOWN", style="Eyebrow.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 5)
        )
        ttk.Label(intro, text="A mind, from elsewhere.", style="Title.TLabel").grid(
            row=1, column=0, sticky="w"
        )
        ttk.Label(
            intro,
            text="An alien neural lattice, waking inside a synthetic signal field.",
            style="Subtitle.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(5, 0))
        ttk.Label(
            intro,
            text="LOCAL  /  SYNTHETIC  /  CONTAINED",
            style="SidebarMuted.TLabel",
            font=("Segoe UI", 8, "bold"),
        ).grid(row=1, column=1, rowspan=2, sticky="e", padx=(10, 0))

        status_panel = ttk.Frame(parent, style="Panel.TFrame", padding=(18, 15))
        status_panel.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        status_panel.columnconfigure(0, weight=1)
        state_line = ttk.Frame(status_panel, style="Panel.TFrame")
        state_line.grid(row=0, column=0, sticky="ew")
        state_line.columnconfigure(1, weight=1)
        self.state_dot = tk.Canvas(
            state_line, width=12, height=12, background=PANEL, highlightthickness=0
        )
        self.state_dot.grid(row=0, column=0, padx=(0, 9))
        self.state_dot_id = self.state_dot.create_oval(
            2, 2, 10, 10, fill=MUTED, outline=""
        )
        self.status_var = tk.StringVar(value="READY")
        self.state_detail_var = tk.StringVar(value="Ready when you are.")
        ttk.Label(
            state_line, textvariable=self.status_var, style="Panel.TLabel",
            font=("Segoe UI", 11, "bold")
        ).grid(row=0, column=1, sticky="w")
        ttk.Label(
            state_line, textvariable=self.state_detail_var, style="Muted.TLabel"
        ).grid(row=0, column=2, sticky="e")
        self.progress = ttk.Progressbar(
            status_panel, mode="determinate", maximum=100, value=0
        )
        self.progress.grid(row=1, column=0, sticky="ew", pady=(12, 0))

        neural_panel = ttk.Frame(parent, style="Panel.TFrame", padding=1)
        neural_panel.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(0, 12))
        self.neural_canvas = tk.Canvas(
            neural_panel,
            height=330,
            background="#060a12",
            highlightthickness=0,
            borderwidth=0,
        )
        self.neural_canvas.pack(fill="both", expand=True)
        self.neural_canvas.bind("<Configure>", self._draw_neural_core)

        stats = ttk.Frame(parent)
        stats.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 13))
        for column in range(3):
            stats.columnconfigure(column, weight=1)
        self.timer_var = tk.StringVar(value="00:00")
        self.count_var = tk.StringVar(value="0")
        self.scenario_stat_var = tk.StringVar(value="First Contact")
        self._stat_card(stats, 0, "CORE UPTIME", self.timer_var, ACCENT)
        self._stat_card(stats, 1, "SYNAPTIC IMPULSES", self.count_var, BLUE)
        self._stat_card(stats, 2, "NEURAL PROTOCOL", self.scenario_stat_var, PURPLE)

        feed = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        feed.grid(row=4, column=0, sticky="nsew", padx=(0, 12))
        feed.columnconfigure(0, weight=1)
        feed.rowconfigure(1, weight=1)
        feed_header = ttk.Frame(feed, style="Panel.TFrame")
        feed_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 9))
        ttk.Label(feed_header, text="Neural transmissions", style="Section.TLabel").pack(
            side="left"
        )
        self.feed_count_label = ttk.Label(
            feed_header, text="0 SIGNALS", style="Muted.TLabel"
        )
        self.feed_count_label.pack(side="right")
        columns = ("time", "event", "application", "details")
        self.feed = ttk.Treeview(feed, columns=columns, show="headings", height=12)
        self.feed.heading("time", text="LOCAL TIME")
        self.feed.heading("event", text="IMPULSE")
        self.feed.heading("application", text="ORIGIN NODE")
        self.feed.heading("details", text="TRANSMISSION")
        self.feed.column("time", width=72, minwidth=72, stretch=False)
        self.feed.column("event", width=125, minwidth=105, stretch=False)
        self.feed.column("application", width=160, minwidth=135, stretch=False)
        self.feed.column("details", width=300, minwidth=160, stretch=True)
        scroll = ttk.Scrollbar(feed, orient="vertical", command=self.feed.yview)
        self.feed.configure(yscrollcommand=scroll.set)
        self.feed.grid(row=1, column=0, sticky="nsew")
        scroll.grid(row=1, column=1, sticky="ns")
        self.feed.tag_configure("control", foreground=BLUE)
        self.feed.tag_configure("pointer", foreground=ACCENT)
        self.feed.tag_configure("file", foreground=PURPLE)
        self.feed.tag_configure("empty", foreground=MUTED)
        self.feed.insert(
            "",
            "end",
            values=("--:--", "AWAITING", "CORE", "No synthetic signals received."),
            tags=("empty",),
        )

        preview = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        preview.grid(row=4, column=1, sticky="nsew")
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(3, weight=1)
        preview_header = ttk.Frame(preview, style="Panel.TFrame")
        preview_header.grid(row=0, column=0, sticky="ew", pady=(0, 15))
        ttk.Label(
            preview_header, text="Synaptic readout", style="Section.TLabel"
        ).pack(side="left")
        ttk.Label(
            preview_header, text="SIGNAL / LOCAL", style="Status.TLabel"
        ).pack(side="right")
        self.application_var = tk.StringVar(value="DORMANT")
        self.location_var = tk.StringVar(value="/CORE/WAITING")
        ttk.Label(
            preview,
            text="ACTIVE NODE",
            style="Muted.TLabel",
            font=("Segoe UI", 8, "bold"),
        ).grid(row=1, column=0, sticky="w")
        ttk.Label(
            preview,
            textvariable=self.application_var,
            style="Panel.TLabel",
            font=("Segoe UI", 12, "bold"),
        ).grid(row=2, column=0, sticky="w", pady=(3, 10))
        ttk.Label(
            preview, textvariable=self.location_var, style="Muted.TLabel"
        ).grid(row=3, column=0, sticky="nw", pady=(0, 12))
        ttk.Label(
            preview,
            text="LAST TRANSMISSION",
            style="Muted.TLabel",
            font=("Segoe UI", 8, "bold"),
        ).grid(row=4, column=0, sticky="w", pady=(0, 6))
        self.preview = tk.Text(
            preview,
            height=4,
            wrap="word",
            background=SURFACE,
            foreground="#bdc9db",
            insertbackground=TEXT,
            relief="flat",
            padx=12,
            pady=11,
            font=("Consolas", 10),
            highlightthickness=1,
            highlightbackground=BORDER,
        )
        self.preview.grid(row=5, column=0, sticky="nsew")
        self.preview.insert("1.0", "Awaiting the first neural transmission...")
        self.preview.configure(state="disabled")
        ttk.Label(
            preview,
            text="Purely synthetic. No external input, process control, or network activity.",
            style="Muted.TLabel",
            wraplength=300,
            justify="left",
        ).grid(row=6, column=0, sticky="w", pady=(12, 0))

    def _draw_neural_core(self, _event: tk.Event | None = None) -> None:
        canvas = self.neural_canvas
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width < 100 or height < 100:
            return

        canvas.delete("all")
        phase = self._neural_phase
        activity = self._activity_level
        center_x = width * 0.5
        center_y = height * 0.51
        radius_x = min(width * 0.205, height * 0.54)
        radius_y = min(height * 0.40, width * 0.19)

        for index in range(90):
            x = (index * 127 + 41) % width
            y = (index * 71 + 19) % height
            shimmer = (sin(phase * 1.7 + index * 2.4) + 1) / 2
            if shimmer > 0.88:
                canvas.create_oval(
                    x, y, x + 2, y + 2, fill="#496d80", outline=""
                )

        canvas.create_text(
            20, 18, anchor="nw", text="NEURAL LATTICE  /  FORM 09",
            fill=ACCENT, font=("Consolas", 9, "bold"),
        )
        canvas.create_text(
            width - 20, 18, anchor="ne", text="BIO-SYNTHETIC  •  ISOLATED",
            fill=MUTED, font=("Consolas", 8),
        )
        canvas.create_oval(
            center_x - radius_x * 1.38,
            center_y - radius_y * 1.28,
            center_x + radius_x * 1.38,
            center_y + radius_y * 1.28,
            outline="#142b3a",
            width=1,
            dash=(2, 7),
        )
        canvas.create_oval(
            center_x - radius_x * 1.22,
            center_y - radius_y * 1.12,
            center_x + radius_x * 1.22,
            center_y + radius_y * 1.12,
            outline="#183342",
            width=1,
        )
        for tick in range(48):
            angle = tick * pi / 24
            inner = radius_x * 1.25
            outer = radius_x * (1.29 if tick % 4 == 0 else 1.27)
            canvas.create_line(
                center_x + cos(angle) * inner,
                center_y + sin(angle) * inner * radius_y / radius_x,
                center_x + cos(angle) * outer,
                center_y + sin(angle) * outer * radius_y / radius_x,
                fill="#315263" if tick % 4 == 0 else "#1a3442",
                width=1,
            )

        outline_points = []
        for step in range(97):
            angle = step * 2 * pi / 96
            organic = 1 + 0.035 * cos(angle * 11) + 0.018 * sin(angle * 7)
            outline_points.extend(
                (
                    center_x + sin(angle) * radius_x * organic,
                    center_y + cos(angle) * radius_y * organic,
                )
            )
        canvas.create_polygon(
            *outline_points, fill="#091522", outline="#43b9c9", width=2,
            smooth=True,
        )

        for side in (-1, 1):
            for fold in range(4):
                points = []
                base_x = side * (0.18 + fold * 0.13)
                for step in range(17):
                    vertical = -0.65 + step * 0.081
                    bend = sin(step * 0.43 + fold * 1.7) * 0.065
                    normalized_x = base_x + side * bend
                    points.extend(
                        (
                            center_x + normalized_x * radius_x,
                            center_y + vertical * radius_y,
                        )
                    )
                canvas.create_line(
                    *points,
                    fill="#173745",
                    width=1,
                    smooth=True,
                    splinesteps=18,
                )

        nodes = []
        for row in range(7):
            normalized_y = -0.78 + row * 0.26
            for column in range(7):
                normalized_x = -0.78 + column * 0.26 + (row % 2) * 0.025
                if normalized_x**2 + normalized_y**2 * 1.25 < 0.78:
                    nodes.append(
                        (
                            center_x + normalized_x * radius_x,
                            center_y + normalized_y * radius_y,
                            normalized_x,
                            normalized_y,
                        )
                    )

        for index, (x1, y1, nx1, ny1) in enumerate(nodes):
            for other_x, other_y, nx2, ny2 in nodes[index + 1 :]:
                distance = sqrt((nx1 - nx2) ** 2 + (ny1 - ny2) ** 2)
                if distance <= 0.39:
                    canvas.create_line(
                        x1, y1, other_x, other_y,
                        fill="#1c5260" if activity > 0.15 else "#163745",
                        width=1,
                    )

        for index, node in enumerate(nodes):
            x, y = node[:2]
            pulse = (sin(phase * 2.2 + index * 0.73) + 1) / 2
            lit = pulse > 0.82 or activity > 0.45 and pulse > 0.48
            color = ACCENT if lit else "#3d9aa8" if pulse > 0.5 else "#245360"
            radius = 2.3 + pulse * 1.7 + activity * pulse * 1.5
            canvas.create_oval(
                x - radius - 3,
                y - radius - 3,
                x + radius + 3,
                y + radius + 3,
                outline="#174c56" if lit else "",
                width=1,
            )
            canvas.create_oval(
                x - radius, y - radius, x + radius, y + radius,
                fill=color, outline="",
            )

        fissure = []
        for step in range(19):
            vertical = -0.9 + step * 0.1
            fissure.extend(
                (
                    center_x + sin(step * 0.8 + phase * 0.18) * radius_x * 0.035,
                    center_y + vertical * radius_y,
                )
            )
        canvas.create_line(
            *fissure, fill="#6fffe2", width=2, smooth=True, splinesteps=18
        )
        core_radius = 13 + activity * 8 + sin(phase * 2) * 2
        canvas.create_oval(
            center_x - core_radius * 2.2,
            center_y - core_radius * 2.2,
            center_x + core_radius * 2.2,
            center_y + core_radius * 2.2,
            outline="#185164",
            width=1,
        )
        canvas.create_oval(
            center_x - core_radius,
            center_y - core_radius,
            center_x + core_radius,
            center_y + core_radius,
            fill="#10303b",
            outline=ACCENT,
            width=2,
        )
        canvas.create_oval(
            center_x - 4, center_y - 4, center_x + 4, center_y + 4,
            fill="#eafffb", outline="",
        )

        rail_y = center_y - 34
        for side, anchor, label_x in (
            (-1, "w", 24),
            (1, "e", width - 24),
        ):
            canvas.create_text(
                label_x, rail_y, anchor=anchor, text="CORTEX / 01",
                fill="#8db2c0", font=("Consolas", 8, "bold"),
            )
            canvas.create_text(
                label_x, rail_y + 21, anchor=anchor, text="SYNAPTIC FIELD",
                fill=MUTED, font=("Consolas", 7),
            )
            bar_width = 92
            bar_x = label_x if side < 0 else label_x - bar_width
            bar_y = rail_y + 42
            canvas.create_rectangle(
                bar_x, bar_y, bar_x + bar_width, bar_y + 3,
                fill="#152938", outline="",
            )
            signal_width = bar_width * (0.12 + activity * 0.78)
            canvas.create_rectangle(
                bar_x, bar_y, bar_x + signal_width, bar_y + 3,
                fill=ACCENT if activity > 0.2 else "#3a93a3", outline="",
            )

        canvas.create_text(
            20, height - 18, anchor="sw",
            text="THOUGHTFORM: SYNTHETIC  /  NO EXTERNAL INPUT",
            fill="#526b7e", font=("Consolas", 8),
        )
        canvas.create_text(
            width - 20, height - 18, anchor="se",
            text=f"COHERENCE {int(72 + sin(phase) * 8 + activity * 16):02d}.{int((phase * 17) % 10)}%",
            fill="#86b8c5", font=("Consolas", 8),
        )

    def _animate_neural_core(self) -> None:
        self._neural_phase += 0.045
        self._activity_level = max(0.0, self._activity_level - 0.018)
        self._draw_neural_core()
        if self.winfo_exists():
            self.after(70, self._animate_neural_core)

    def _stat_card(
        self,
        parent: ttk.Frame,
        column: int,
        title: str,
        value: tk.StringVar,
        color: str,
    ) -> None:
        card = ttk.Frame(parent, style="Panel.TFrame", padding=(15, 13))
        card.grid(
            row=0,
            column=column,
            sticky="ew",
            padx=(0 if column == 0 else 6, 6),
        )
        tk.Frame(card, background=color, height=2).pack(fill="x", pady=(0, 10))
        ttk.Label(card, text=title, style="Muted.TLabel").pack(anchor="w")
        ttk.Label(
            card,
            textvariable=value,
            style="Panel.TLabel",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", pady=(5, 0))

    def _browse(self) -> None:
        chosen = filedialog.asksaveasfilename(
            title="Choose synthetic signal trace",
            defaultextension=".jsonl",
            filetypes=(("JSON Lines", "*.jsonl"), ("All files", "*.*")),
            initialfile=Path(self.path_var.get()).name,
        )
        if chosen:
            self.path_var.set(chosen)

    def _read_settings(self) -> tuple[int, int, int, int, int, str, Path] | None:
        try:
            duration = int(self.duration_var.get())
            interval = int(self.interval_var.get())
            break_after = int(self.break_after_var.get())
            break_duration = int(self.break_duration_var.get())
            seed = int(self.seed_var.get())
        except ValueError:
            messagebox.showerror("Invalid settings", "Enter whole numbers for settings.")
            return None

        valid = (
            1 <= duration <= 120
            and 1 <= interval <= 60
            and 0 <= break_after <= 50
            and 1 <= break_duration <= 300
            and 0 <= seed <= 2147483647
            and self.scenario_var.get() in SCENARIOS
            and bool(self.path_var.get().strip())
        )
        if not valid:
            messagebox.showerror(
                "Invalid settings",
                "Check the allowed ranges and choose an output file path.",
            )
            return None

        return (
            duration,
            interval,
            break_after,
            break_duration,
            seed,
            self.scenario_var.get(),
            Path(self.path_var.get().strip()),
        )

    def _start_or_resume(self) -> None:
        if self.state == "PAUSED":
            self.last_tick = time.monotonic()
            self._record_control(
                "session_resumed", "Restored the synthetic neural flow."
            )
            if self.state != "ERROR":
                self._set_state("BREAK" if self.break_remaining > 0 else "RUNNING")
            return

        settings = self._read_settings()
        if settings is None:
            return
        (
            duration,
            interval,
            self.break_after,
            break_duration,
            seed,
            self.scenario_name,
            self.output_path,
        ) = settings
        self.engine = ScenarioEngine(self.scenario_name, seed)
        self.session_id = str(uuid.uuid4())
        self.sequence = 0
        self.event_count = 0
        self.elapsed = 0.0
        self.duration_seconds = duration * 60
        self.event_interval = float(interval)
        self.next_event_in = self.event_interval
        self.events_since_break = 0
        self.break_duration = float(break_duration)
        self.break_remaining = 0.0
        self.timer_var.set("00:00")
        self.count_var.set("0")
        self.scenario_stat_var.set(self.scenario_name)
        self.progress.configure(value=0)
        self.feed_count_label.configure(text="0 SIGNALS")
        self._activity_level = 0.0
        for item in self.feed.get_children():
            self.feed.delete(item)
        self.application_var.set("DORMANT")
        self.location_var.set("/CORE/WAITING")
        self._set_preview("Awaiting the first neural transmission...")
        self.last_tick = time.monotonic()
        self._set_state("RUNNING")
        self._record_control(
            "session_started",
            f"Initialized the synthetic {self.scenario_name} neural sequence.",
        )

    def _pause(self) -> None:
        if self.state not in ("RUNNING", "BREAK"):
            return
        self._set_state("PAUSED")
        self._record_control("session_paused", "Suspended the synthetic neural flow.")

    def _stop(self) -> None:
        if self.state not in ("RUNNING", "BREAK", "PAUSED"):
            return
        self._record_control("session_stopped", "Stopped the in-app simulation.")
        if self.state != "ERROR":
            self._set_state("STOPPED")

    def _record_control(self, event_type: str, details: str) -> None:
        if self.session_id is None:
            return
        self._record(
            control_event(
                self.scenario_name,
                self.session_id,
                self.sequence,
                event_type,
                details,
            )
        )

    def _record(self, event: SimulationEvent) -> bool:
        if self.output_path is None:
            self._fail("Choose an output path before starting a session.")
            return False
        try:
            append_event(self.output_path, event)
        except OSError as error:
            self._fail(f"Could not write the synthetic event log:\n{error}")
            return False

        self.sequence += 1
        self.event_count += 1
        timestamp = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
        row = self.feed.insert(
            "",
            0,
            values=(
                timestamp.astimezone().strftime("%H:%M:%S"),
                event.event_type.replace("_", " ").upper(),
                event.application,
                event.details,
            ),
            tags=(self._event_tag(event),),
        )
        rows = self.feed.get_children()
        for old_row in rows[200:]:
            self.feed.delete(old_row)
        self.feed.see(row)
        self.count_var.set(str(self.event_count))
        self.feed_count_label.configure(text=f"{self.event_count} SIGNALS")
        self._activity_level = 1.0
        self._update_preview(event)
        return True

    @staticmethod
    def _event_tag(event: SimulationEvent) -> str:
        if event.application == "Xenomind Core":
            return "control"
        if event.event_type == "neural_firing":
            return "pointer"
        if event.event_type in ("memory_recall", "dream_fragment", "lattice_scan"):
            return "file"
        return "normal"

    def _update_preview(self, event: SimulationEvent) -> None:
        if event.application != "Xenomind Core":
            self.application_var.set(event.application)
        if event.location is not None:
            self.location_var.set(event.location)
        self._set_preview(event.preview_text or event.details)

    def _set_preview(self, text: str) -> None:
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")

    def _tick(self) -> None:
        now = time.monotonic()
        if self.state in ("RUNNING", "BREAK"):
            delta = max(0.0, now - self.last_tick)
            self.elapsed = min(self.duration_seconds, self.elapsed + delta)
            if self.elapsed >= self.duration_seconds:
                self._record_control(
                    "session_completed", "Completed the configured neural cycle."
                )
                if self.state != "ERROR":
                    self._set_state("COMPLETE")
            elif self.state == "BREAK":
                self.break_remaining = max(0.0, self.break_remaining - delta)
                if self.break_remaining == 0:
                    self._record_control(
                        "idle_break_completed", "Completed the configured idle break."
                    )
                    if self.state != "ERROR":
                        self._set_state("RUNNING")
            else:
                self.next_event_in -= delta
                if self.next_event_in <= 0:
                    self._emit_scenario_event()
                    self.next_event_in = self.event_interval
                    if self.state == "RUNNING" and self.break_after:
                        self.events_since_break += 1
                        if self.events_since_break >= self.break_after:
                            self.events_since_break = 0
                            self.break_remaining = self.break_duration
                            self._set_state("BREAK")
                            self._record_control(
                                "idle_break_started",
                                f"Started a {int(self.break_duration)} second idle break.",
                            )
            self._update_timer()
            self._update_progress()
        self.last_tick = now
        self.after(200, self._tick)

    def _emit_scenario_event(self) -> None:
        if self.engine is None or self.session_id is None:
            self._fail("The scenario engine was not initialized.")
            return
        event = self.engine.next_event(self.session_id, self.sequence)
        self._record(event)

    def _update_timer(self) -> None:
        total_seconds = int(self.elapsed)
        minutes, seconds = divmod(total_seconds, 60)
        self.timer_var.set(f"{minutes:02d}:{seconds:02d}")

    def _update_progress(self) -> None:
        if self.duration_seconds <= 0:
            percentage = 0
        else:
            percentage = min(100, self.elapsed / self.duration_seconds * 100)
        self.progress.configure(value=percentage)
        remaining = max(0, int(self.duration_seconds - self.elapsed))
        minutes, seconds = divmod(remaining, 60)
        if self.state == "BREAK":
            break_seconds = max(0, int(self.break_remaining))
            self.state_detail_var.set(
                f"Quiet interval - {break_seconds // 60:02d}:{break_seconds % 60:02d} remaining"
            )
        elif self.state == "RUNNING":
            self.state_detail_var.set(
                f"{self.scenario_name}  /  {minutes:02d}:{seconds:02d} remaining"
            )
        elif self.state == "PAUSED":
            self.state_detail_var.set("Neural activity suspended")
        elif self.state == "COMPLETE":
            self.state_detail_var.set("Core cycle complete - synthetic trace saved")
        elif self.state == "STOPPED":
            self.state_detail_var.set("Core dissolved - synthetic trace saved")
        elif self.state == "ERROR":
            self.state_detail_var.set("Signal fault - core halted")
        else:
            self.state_detail_var.set("Core dormant - awaiting activation")

    def _set_state(self, state: str) -> None:
        self.state = state
        self._refresh_state()

    def _refresh_state(self) -> None:
        labels = {
            "READY": "DORMANT",
            "RUNNING": "AWAKE",
            "BREAK": "QUIET",
            "PAUSED": "SUSPENDED",
            "STOPPED": "DISSOLVED",
            "COMPLETE": "CYCLE COMPLETE",
            "ERROR": "SIGNAL FAULT",
        }
        colors = {
            "READY": MUTED,
            "RUNNING": ACCENT,
            "BREAK": BLUE,
            "PAUSED": BLUE,
            "STOPPED": MUTED,
            "COMPLETE": ACCENT,
            "ERROR": DANGER,
        }
        label = labels.get(self.state, self.state)
        self.status_var.set(label)
        self.header_status.configure(text=label)
        color = colors.get(self.state, TEXT)
        status_background = {
            "READY": "#202938",
            "RUNNING": "#142a2a",
            "BREAK": "#1b2940",
            "PAUSED": "#1b2940",
            "STOPPED": "#202938",
            "COMPLETE": "#142a2a",
            "ERROR": "#38212a",
        }.get(self.state, PANEL_LIGHT)
        ttk.Style(self).configure(
            "Status.TLabel",
            background=status_background,
            foreground=color,
            font=("Segoe UI", 9, "bold"),
            padding=(11, 7),
        )
        self.state_dot.itemconfigure(self.state_dot_id, fill=color)
        self.progress.configure(
            style="Horizontal.TProgressbar"
            if self.state != "ERROR"
            else "Error.Horizontal.TProgressbar"
        )
        ttk.Style(self).configure(
            "Error.Horizontal.TProgressbar",
            troughcolor=SURFACE,
            background=DANGER,
            bordercolor=SURFACE,
            lightcolor=DANGER,
            darkcolor=DANGER,
            thickness=5,
        )
        if self.state in ("READY", "RUNNING", "BREAK", "PAUSED"):
            self._update_progress()
        self.start_button.configure(
            text="Reawaken the core" if self.state == "PAUSED" else "Awaken the core",
            state="normal",
        )
        self.pause_button.configure(
            state="normal" if self.state in ("RUNNING", "BREAK") else "disabled"
        )
        self.stop_button.configure(
            state="normal" if self.state in ("RUNNING", "BREAK", "PAUSED") else "disabled"
        )

    def _fail(self, message: str) -> None:
        self._set_state("ERROR")
        messagebox.showerror("Simulation error", message)

    def _close(self) -> None:
        if self.state in ("RUNNING", "BREAK", "PAUSED"):
            self._stop()
        self.destroy()


if __name__ == "__main__":
    ActivitySimulator().mainloop()
