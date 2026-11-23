import customtkinter as ctk
import time
import threading
import queue
import csv
import json
import ipaddress

from datetime import datetime
from collections import deque
from tkinter import filedialog, messagebox

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from monitor import NetworkMonitor, calculate_jitter_ewma


# ===================== THEME =====================

BG = "#0B1020"
SIDEBAR = "#0E1628"
PANEL = "#141E32"
PANEL_LIGHT = "#19263B"
BORDER = "#233149"

TEXT = "#E8EEF8"
MUTED = "#8D9BB3"

BLUE = "#4F8CFF"
CYAN = "#38C8E8"
PURPLE = "#A78BFA"
GREEN = "#36D399"
RED = "#F87171"
YELLOW = "#FBBF24"


class Dashboard:

    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("Network Monitor 4.2")
        self.root.geometry("1400x920")
        self.root.minsize(1120, 780)
        self.root.configure(fg_color=BG)

        self.monitor = NetworkMonitor()
        self.data_queue = queue.Queue()

        self.running = True
        self.monitoring_enabled = True

        self.shutdown_event = threading.Event()

        self.monitor_generation = 0
        self.ping_generation = 0

        self.start_time = time.time()

        self.speed_interval = 1.0
        self.metrics_interval = 0.5

        self.ping_warning_ms = 100.0
        self.loss_warning_percent = 5.0

        self.traffic_history = deque()

        self.successful_pings = deque(maxlen=10)
        self.ping_results = deque(maxlen=10)
        self.previous_successful_ping = None
        self.jitter_value = None

        self.last_speed_timestamp = time.monotonic()

        self.download_total = 0.0
        self.upload_total = 0.0

        self.current_download = 0.0
        self.current_upload = 0.0

        self.max_download = 0.0
        self.max_upload = 0.0

        self.download_sum = 0.0
        self.upload_sum = 0.0
        self.sample_count = 0
        self.observed_seconds = 0.0

        self.latest_ping = None
        self.latest_loss = None
        self.latest_status = "Checking"
        self.latest_ip = "Loading..."
        self.latest_interface = "Loading..."

        self.settings_window = None

        self.build_ui()

        self.root.after(100, self.process_queue)
        self.root.after(1000, self.update_dashboard)

        self.worker_threads = []
        workers = (
            self.background_speed_monitor,
            self.background_ping_monitor,
            self.background_connection_monitor,
            self.background_interface_monitor,
        )

        for worker in workers:
            thread = threading.Thread(
                target=worker,
                name=f"NetworkMonitor-{worker.__name__}",
                daemon=True,
            )
            self.worker_threads.append(thread)
            thread.start()

    # ===================== HELPERS =====================

    @staticmethod
    def shorten_text(value, max_length=24):
        value = str(value)

        if len(value) > max_length:
            return value[:max_length - 3] + "..."

        return value

    @staticmethod
    def safe_number(value, default=0.0):
        try:
            number = float(value)

            if number != number or number == float("inf"):
                return default

            return number

        except (TypeError, ValueError):
            return default

    # ===================== MAIN UI =====================

    def build_ui(self):
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(
            self.root,
            width=225,
            fg_color=SIDEBAR,
            corner_radius=0
        )
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)

        self.build_sidebar()

        self.content = ctk.CTkFrame(
            self.root,
            fg_color=BG,
            corner_radius=0
        )
        self.content.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=25,
            pady=20
        )

        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(4, weight=1)

        self.build_header()
        self.build_speed_cards()
        self.build_statistics()
        self.build_metrics()
        self.build_graph()
        self.build_footer()

    # ===================== SIDEBAR =====================

    def build_sidebar(self):
        brand = ctk.CTkFrame(
            self.sidebar,
            fg_color="transparent"
        )
        brand.pack(fill="x", padx=20, pady=(28, 35))

        ctk.CTkLabel(
            brand,
            text="◈",
            font=("Segoe UI", 32, "bold"),
            text_color=BLUE
        ).pack(side="left", padx=(0, 10))

        brand_text = ctk.CTkFrame(
            brand,
            fg_color="transparent"
        )
        brand_text.pack(side="left")

        ctk.CTkLabel(
            brand_text,
            text="NETWORK",
            font=("Segoe UI", 16, "bold"),
            text_color=TEXT
        ).pack(anchor="w")

        ctk.CTkLabel(
            brand_text,
            text="MONITOR",
            font=("Segoe UI", 11),
            text_color=MUTED
        ).pack(anchor="w")

        ctk.CTkLabel(
            self.sidebar,
            text="MENU",
            font=("Segoe UI", 10, "bold"),
            text_color="#5E6D86"
        ).pack(anchor="w", padx=25, pady=(0, 12))

        active = ctk.CTkFrame(
            self.sidebar,
            fg_color="#1B2A43",
            corner_radius=10,
            height=44
        )
        active.pack(fill="x", padx=14)
        active.pack_propagate(False)

        ctk.CTkLabel(
            active,
            text="▦     Dashboard",
            font=("Segoe UI", 13, "bold"),
            text_color="#75A8FF"
        ).pack(side="left", padx=15, pady=10)

        details = ctk.CTkFrame(
            self.sidebar,
            fg_color="#121D30",
            corner_radius=12,
            border_width=1,
            border_color=BORDER
        )
        details.pack(
            side="bottom",
            fill="x",
            padx=12,
            pady=(10, 18)
        )

        ctk.CTkLabel(
            details,
            text="CONNECTION DETAILS",
            font=("Segoe UI", 9, "bold"),
            text_color="#71819A"
        ).pack(anchor="w", padx=12, pady=(12, 10))

        self.ping_target_label = self.create_sidebar_detail(
            details, "Ping Target", self.monitor.ping_target
        )

        self.tcp_target_label = self.create_sidebar_detail(
            details, "TCP Check", "Port 53"
        )

        self.sidebar_jitter_label = self.create_sidebar_detail(
            details, "Jitter (Avg.)", "N/A"
        )

    def create_sidebar_detail(self, parent, title, initial):
        item = ctk.CTkFrame(
            parent,
            fg_color="transparent"
        )
        item.pack(fill="x", padx=12, pady=4)

        ctk.CTkLabel(
            item,
            text=title,
            font=("Segoe UI", 9),
            text_color=MUTED
        ).pack(anchor="w")

        value = ctk.CTkLabel(
            item,
            text=initial,
            font=("Segoe UI", 11, "bold"),
            text_color=TEXT,
            wraplength=165,
            justify="left",
            anchor="w"
        )
        value.pack(anchor="w", pady=(2, 0), fill="x")

        return value

    # ===================== HEADER =====================

    def build_header(self):
        header = ctk.CTkFrame(
            self.content,
            fg_color="transparent"
        )
        header.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 16)
        )
        header.grid_columnconfigure(0, weight=1)

        title_area = ctk.CTkFrame(
            header,
            fg_color="transparent"
        )
        title_area.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            title_area,
            text="Network Overview",
            font=("Segoe UI", 27, "bold"),
            text_color=TEXT
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_area,
            text="Monitor your network performance in real time.",
            font=("Segoe UI", 12),
            text_color=MUTED
        ).pack(anchor="w", pady=(4, 0))

        actions = ctk.CTkFrame(
            header,
            fg_color="transparent"
        )
        actions.grid(row=0, column=1, sticky="e")

        ctk.CTkButton(
            actions,
            text="↓  Export",
            width=105,
            height=36,
            corner_radius=9,
            fg_color="#1B2A43",
            hover_color="#263B5C",
            text_color=TEXT,
            font=("Segoe UI", 11, "bold"),
            command=self.export_report
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            actions,
            text="⚙  Settings",
            width=110,
            height=36,
            corner_radius=9,
            fg_color="#1B2A43",
            hover_color="#263B5C",
            text_color=TEXT,
            font=("Segoe UI", 11, "bold"),
            command=self.open_settings
        ).pack(side="left", padx=(0, 8))

        self.live_button = ctk.CTkButton(
            actions,
            text="●  LIVE",
            width=100,
            height=36,
            corner_radius=20,
            fg_color="#142C2A",
            hover_color="#1D403B",
            text_color=GREEN,
            font=("Segoe UI", 11, "bold"),
            command=self.toggle_monitoring
        )
        self.live_button.pack(side="left")

    # ===================== SPEED CARDS =====================

    def build_speed_cards(self):
        frame = ctk.CTkFrame(
            self.content,
            fg_color="transparent"
        )
        frame.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(0, 12)
        )
        frame.grid_columnconfigure((0, 1), weight=1)

        self.download_card = self.create_speed_card(
            frame, 0, "DOWNLOAD SPEED", "↓", BLUE
        )
        self.upload_card = self.create_speed_card(
            frame, 1, "UPLOAD SPEED", "↑", PURPLE
        )

    def create_speed_card(self, parent, column, title, symbol, accent):
        card = ctk.CTkFrame(
            parent,
            fg_color=PANEL,
            corner_radius=16,
            border_width=1,
            border_color=BORDER
        )
        card.grid(
            row=0,
            column=column,
            sticky="ew",
            padx=(0, 8) if column == 0 else (8, 0)
        )

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=(14, 3))

        ctk.CTkLabel(
            top,
            text=title,
            font=("Segoe UI", 11, "bold"),
            text_color=MUTED
        ).pack(side="left")

        ctk.CTkLabel(
            top,
            text=symbol,
            font=("Segoe UI", 22, "bold"),
            text_color=accent
        ).pack(side="right")

        value_row = ctk.CTkFrame(
            card,
            fg_color="transparent"
        )
        value_row.pack(anchor="w", padx=20, pady=(5, 15))

        value = ctk.CTkLabel(
            value_row,
            text="0.00",
            font=("Segoe UI", 32, "bold"),
            text_color=TEXT
        )
        value.pack(side="left", anchor="w")

        unit = ctk.CTkLabel(
            value_row,
            text="B/s",
            font=("Segoe UI", 14, "bold"),
            text_color=accent
        )
        unit.pack(side="left", anchor="w", padx=(8, 0))

        return {
            "card": card,
            "value": value,
            "unit": unit
        }

    # ===================== STATISTICS =====================

    def build_statistics(self):
        frame = ctk.CTkFrame(
            self.content,
            fg_color="transparent"
        )
        frame.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(0, 12)
        )
        frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.max_download_card = self.create_stat_card(
            frame, 0, "MAX DOWNLOAD", "0 B/s", BLUE
        )
        self.avg_download_card = self.create_stat_card(
            frame, 1, "AVG DOWNLOAD", "0 B/s", CYAN
        )
        self.max_upload_card = self.create_stat_card(
            frame, 2, "MAX UPLOAD", "0 B/s", PURPLE
        )
        self.avg_upload_card = self.create_stat_card(
            frame, 3, "AVG UPLOAD", "0 B/s", GREEN
        )

    def create_stat_card(self, parent, column, title, initial, accent):
        card = ctk.CTkFrame(
            parent,
            fg_color=PANEL_LIGHT,
            corner_radius=12,
            border_width=1,
            border_color=BORDER
        )
        card.grid(
            row=0,
            column=column,
            sticky="ew",
            padx=(0, 5) if column < 3 else (5, 0)
        )

        ctk.CTkLabel(
            card,
            text=title,
            font=("Segoe UI", 9, "bold"),
            text_color=MUTED
        ).pack(anchor="w", padx=11, pady=(10, 4))

        value = ctk.CTkLabel(
            card,
            text=initial,
            font=("Segoe UI", 15, "bold"),
            text_color=accent
        )
        value.pack(anchor="w", padx=11, pady=(0, 10))

        return value

    # ===================== METRICS =====================

    def build_metrics(self):
        frame = ctk.CTkFrame(
            self.content,
            fg_color="transparent"
        )
        frame.grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(0, 12)
        )
        frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.ping_card = self.create_metric_card(
            frame, 0, f"PING • {self.monitor.ping_target}", "N/A", YELLOW
        )
        self.loss_card = self.create_metric_card(
            frame, 1, "PACKET LOSS", "N/A", MUTED
        )
        self.status_card = self.create_metric_card(
            frame, 2, "CONNECTION (TCP)", "Checking", YELLOW
        )
        self.ip_card = self.create_metric_card(
            frame, 3, "LOCAL IP", "Loading...", CYAN
        )

    def create_metric_card(self, parent, column, title, initial, accent):
        card = ctk.CTkFrame(
            parent,
            fg_color=PANEL,
            corner_radius=13,
            border_width=1,
            border_color=BORDER
        )
        card.grid(
            row=0,
            column=column,
            sticky="ew",
            padx=(0, 5) if column < 3 else (5, 0)
        )

        ctk.CTkLabel(
            card,
            text=title,
            font=("Segoe UI", 9, "bold"),
            text_color=MUTED,
            wraplength=190,
            justify="left"
        ).pack(anchor="w", padx=12, pady=(11, 4))

        value = ctk.CTkLabel(
            card,
            text=initial,
            font=("Segoe UI", 16, "bold"),
            text_color=accent,
            wraplength=190,
            justify="left",
            anchor="w"
        )
        value.pack(anchor="w", padx=12, pady=(0, 11), fill="x")

        return {
            "card": card,
            "title": card.winfo_children()[0],
            "value": value
        }

    # ===================== GRAPH =====================

    def build_graph(self):
        self.graph_panel = ctk.CTkFrame(
            self.content,
            fg_color=PANEL,
            corner_radius=16,
            border_width=1,
            border_color=BORDER
        )
        self.graph_panel.grid(
            row=4,
            column=0,
            sticky="nsew",
            pady=(0, 12)
        )

        self.graph_panel.grid_rowconfigure(1, weight=1)
        self.graph_panel.grid_columnconfigure(0, weight=1)

        graph_header = ctk.CTkFrame(
            self.graph_panel,
            fg_color="transparent"
        )
        graph_header.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=18,
            pady=(13, 0)
        )

        ctk.CTkLabel(
            graph_header,
            text="Network Traffic",
            font=("Segoe UI", 15, "bold"),
            text_color=TEXT
        ).pack(side="left")

        ctk.CTkLabel(
            graph_header,
            text="LAST 60 SECONDS",
            font=("Segoe UI", 9, "bold"),
            text_color=CYAN
        ).pack(side="right")

        self.figure = Figure(
            figsize=(8, 3),
            dpi=100,
            facecolor=PANEL
        )

        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor(PANEL)

        self.ax.tick_params(
            axis="both",
            colors=MUTED,
            labelsize=8
        )

        for side in ("top", "right"):
            self.ax.spines[side].set_visible(False)

        for side in ("bottom", "left"):
            self.ax.spines[side].set_color(BORDER)

        self.ax.grid(
            True,
            color=BORDER,
            linestyle="--",
            linewidth=0.6,
            alpha=0.6
        )

        self.ax.set_ylabel("B/s", color=MUTED, fontsize=9)
        self.ax.set_xlabel("Time (seconds)", color=MUTED, fontsize=8)

        self.ax.set_xlim(-60, 0)
        self.ax.set_xticks([-60, -45, -30, -15, 0])
        self.ax.set_ylim(0, 1)

        self.download_line, = self.ax.plot(
            [],
            [],
            color=BLUE,
            linewidth=2,
            label="Download"
        )

        self.upload_line, = self.ax.plot(
            [],
            [],
            color=PURPLE,
            linewidth=2,
            label="Upload"
        )

        self.ax.legend(
            loc="upper left",
            facecolor=PANEL,
            edgecolor=BORDER,
            labelcolor=TEXT,
            fontsize=8
        )

        self.figure.tight_layout(pad=1.3)

        self.canvas = FigureCanvasTkAgg(
            self.figure,
            master=self.graph_panel
        )

        self.canvas.get_tk_widget().grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=10,
            pady=(0, 8)
        )

    # ===================== FOOTER =====================

    def build_footer(self):
        footer = ctk.CTkFrame(
            self.content,
            fg_color="transparent"
        )
        footer.grid(row=5, column=0, sticky="ew")
        footer.grid_columnconfigure((0, 1, 2), weight=1)

        self.uptime_label = self.create_footer_item(
            footer, 0, "SESSION UPTIME", "00:00:00"
        )

        self.interface_label = self.create_footer_item(
            footer, 1, "NETWORK INTERFACE", "Loading..."
        )

        self.total_label = self.create_footer_item(
            footer, 2, "TOTAL TRAFFIC", "0.00 MB"
        )

    def create_footer_item(self, parent, column, title, initial):
        frame = ctk.CTkFrame(
            parent,
            fg_color="transparent"
        )
        frame.grid(row=0, column=column, sticky="w")

        ctk.CTkLabel(
            frame,
            text=title,
            font=("Segoe UI", 9, "bold"),
            text_color="#65758E"
        ).pack(anchor="w")

        value = ctk.CTkLabel(
            frame,
            text=initial,
            font=("Segoe UI", 11, "bold"),
            text_color="#B6C4D9",
            wraplength=220,
            justify="left"
        )
        value.pack(anchor="w", pady=(3, 0))

        return value

    # ===================== SETTINGS =====================

    def open_settings(self):
        if self.settings_window is not None:
            try:
                if self.settings_window.winfo_exists():
                    self.settings_window.focus()
                    return
            except Exception:
                self.settings_window = None

        window = ctk.CTkToplevel(self.root)
        self.settings_window = window

        window.title("Network Monitor Settings")
        window.resizable(False, False)
        window.configure(fg_color=BG)
        window.transient(self.root)
        window.grab_set()

        available_height = max(360, window.winfo_screenheight() - 100)
        window.geometry(f"450x{min(650, available_height)}")

        content = ctk.CTkScrollableFrame(
            window,
            fg_color=BG,
            scrollbar_button_color=BLUE,
            scrollbar_button_hover_color="#3974D8"
        )
        content.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            content,
            text="Monitoring Settings",
            font=("Segoe UI", 22, "bold"),
            text_color=TEXT
        ).pack(anchor="w", padx=25, pady=(25, 5))

        ctk.CTkLabel(
            content,
            text="Configure network checks and warning thresholds.",
            font=("Segoe UI", 11),
            text_color=MUTED
        ).pack(anchor="w", padx=25, pady=(0, 20))

        ctk.CTkLabel(
            content,
            text="Ping target (IPv4 / IPv6)",
            font=("Segoe UI", 12, "bold"),
            text_color=TEXT
        ).pack(anchor="w", padx=25)

        target_entry = ctk.CTkEntry(
            content,
            width=375,
            height=38,
            fg_color=PANEL,
            border_color=BORDER,
            text_color=TEXT
        )
        target_entry.pack(padx=25, pady=(7, 5))
        target_entry.insert(0, self.monitor.ping_target)

        ctk.CTkLabel(
            content,
            text="Examples: 1.1.1.1  •  8.8.8.8  •  custom IP",
            font=("Segoe UI", 10),
            text_color=MUTED
        ).pack(anchor="w", padx=25, pady=(0, 15))

        ctk.CTkLabel(
            content,
            text="Speed update interval",
            font=("Segoe UI", 12, "bold"),
            text_color=TEXT
        ).pack(anchor="w", padx=25)

        interval_menu = ctk.CTkOptionMenu(
            content,
            values=["1 second", "2 seconds", "3 seconds"],
            width=375,
            height=36,
            fg_color=PANEL_LIGHT,
            button_color=BLUE,
            button_hover_color="#3974D8"
        )
        interval_menu.pack(padx=25, pady=(7, 15))

        interval_values = {
            1.0: "1 second",
            2.0: "2 seconds",
            3.0: "3 seconds"
        }

        interval_menu.set(
            interval_values.get(self.speed_interval, "1 second")
        )

        ctk.CTkLabel(
            content,
            text="High ping warning threshold (ms)",
            font=("Segoe UI", 12, "bold"),
            text_color=TEXT
        ).pack(anchor="w", padx=25)

        ping_entry = ctk.CTkEntry(
            content,
            width=375,
            height=36,
            fg_color=PANEL,
            border_color=BORDER
        )
        ping_entry.pack(padx=25, pady=(7, 15))
        ping_entry.insert(0, str(self.ping_warning_ms))

        ctk.CTkLabel(
            content,
            text="Packet loss warning threshold (%)",
            font=("Segoe UI", 12, "bold"),
            text_color=TEXT
        ).pack(anchor="w", padx=25)

        loss_entry = ctk.CTkEntry(
            content,
            width=375,
            height=36,
            fg_color=PANEL,
            border_color=BORDER
        )
        loss_entry.pack(padx=25, pady=(7, 20))
        loss_entry.insert(0, str(self.loss_warning_percent))

        buttons = ctk.CTkFrame(
            content,
            fg_color="transparent"
        )
        buttons.pack(fill="x", padx=25, pady=(0, 20))

        def close_settings():
            self.settings_window = None

            try:
                window.grab_release()
            except Exception:
                pass

            try:
                window.destroy()
            except Exception:
                pass

        def apply_settings():
            target = target_entry.get().strip()

            try:
                ipaddress.ip_address(target)
            except ValueError:
                messagebox.showerror(
                    "Invalid Ping Target",
                    "Enter a valid IPv4 or IPv6 address.",
                    parent=window
                )
                return

            try:
                ping_threshold = float(ping_entry.get())
                loss_threshold = float(loss_entry.get())

                if not 0 < ping_threshold <= 60000:
                    raise ValueError

                if not 0 <= loss_threshold <= 100:
                    raise ValueError

            except ValueError:
                messagebox.showerror(
                    "Invalid Threshold",
                    "Ping threshold must be greater than 0.\n"
                    "Packet loss threshold must be between 0 and 100.",
                    parent=window
                )
                return

            old_target = self.monitor.ping_target

            try:
                self.monitor.set_ping_target(target)
            except ValueError as error:
                messagebox.showerror(
                    "Invalid Ping Target",
                    str(error),
                    parent=window
                )
                return

            interval_map = {
                "1 second": 1.0,
                "2 seconds": 2.0,
                "3 seconds": 3.0
            }

            self.speed_interval = interval_map.get(
                interval_menu.get(), 1.0
            )

            self.ping_warning_ms = ping_threshold
            self.loss_warning_percent = loss_threshold

            if target != old_target:
                self.ping_generation += 1
                self.clear_queue()

                self.latest_ping = None
                self.latest_loss = None

                self.successful_pings.clear()
                self.ping_results.clear()
                self.previous_successful_ping = None
                self.jitter_value = None

            self.ping_target_label.configure(
                text=self.shorten_text(target, 25)
            )

            self.ping_card["title"].configure(
                text=f"PING • {self.shorten_text(target, 22)}"
            )

            if target != old_target:
                self.ping_card["value"].configure(
                    text="Checking...",
                    text_color=YELLOW
                )

                self.loss_card["value"].configure(
                    text="Checking...",
                    text_color=YELLOW
                )

                self.sidebar_jitter_label.configure(text="N/A")

            self.update_metric_cards()
            close_settings()

        ctk.CTkButton(
            buttons,
            text="Cancel",
            width=110,
            height=38,
            fg_color="#263149",
            hover_color="#35445F",
            command=close_settings
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            buttons,
            text="Apply Settings",
            width=140,
            height=38,
            fg_color=BLUE,
            hover_color="#3974D8",
            command=apply_settings
        ).pack(side="right")

        window.protocol("WM_DELETE_WINDOW", close_settings)

    # ===================== QUEUE HELPERS =====================

    def clear_queue(self):
        while True:
            try:
                self.data_queue.get_nowait()
            except queue.Empty:
                break

    # ===================== LIVE / PAUSE =====================

    def toggle_monitoring(self):
        self.monitoring_enabled = not self.monitoring_enabled
        self.monitor_generation += 1

        self.clear_queue()

        if self.monitoring_enabled:
            try:
                self.monitor.reset_speed_baseline()
                self.last_speed_timestamp = time.monotonic()
            except Exception as error:
                print("Speed baseline reset error:", error)

            self.live_button.configure(
                text="●  LIVE",
                fg_color="#142C2A",
                hover_color="#1D403B",
                text_color=GREEN
            )

        else:
            self.live_button.configure(
                text="●  PAUSED",
                fg_color="#3B3020",
                hover_color="#51402A",
                text_color=YELLOW
            )

    # ===================== BACKGROUND SPEED =====================

    def background_speed_monitor(self):
        while self.running and not self.shutdown_event.is_set():
            if not self.monitoring_enabled:
                self.shutdown_event.wait(0.2)
                continue

            generation = self.monitor_generation

            try:
                download, upload, downloaded_bytes, uploaded_bytes = (
                    self.monitor.get_speed_sample()
                )

                if (
                    self.running
                    and self.monitoring_enabled
                    and generation == self.monitor_generation
                ):
                    self.data_queue.put({
                        "type": "speed",
                        "generation": generation,
                        "download": max(
                            0.0, self.safe_number(download)
                        ),
                        "upload": max(
                            0.0, self.safe_number(upload)
                        ),
                        "downloaded_bytes": max(0, int(downloaded_bytes)),
                        "uploaded_bytes": max(0, int(uploaded_bytes)),
                        "timestamp": time.monotonic()
                    })

            except Exception as error:
                print("Speed monitor error:", error)

            self.shutdown_event.wait(self.speed_interval)

    # ===================== BACKGROUND METRICS =====================

    def _worker_wait(self, seconds):
        self.shutdown_event.wait(seconds)


    def _queue_metric(
        self,
        metric_type,
        generation,
        ping_generation=None,
        target=None,
        **values
    ):
        if not self.running or not self.monitoring_enabled:
            return

        if generation != self.monitor_generation:
            return

        payload = {
            "type": metric_type,
            "generation": generation,
            **values
        }

        if ping_generation is not None:
            payload["ping_generation"] = ping_generation
            payload["target"] = target

        self.data_queue.put(payload)

    def background_ping_monitor(self):
        while self.running and not self.shutdown_event.is_set():
            if not self.monitoring_enabled:
                self.shutdown_event.wait(0.2)
                continue

            generation = self.monitor_generation
            ping_generation = self.ping_generation
            target = self.monitor.ping_target

            try:
                value = self.monitor.get_ping(target)

                self._queue_metric(
                    "ping",
                    generation,
                    ping_generation,
                    target,
                    ping=value
                )

            except Exception as error:
                print("Ping monitor error:", error)

            self._worker_wait(5)

    def background_connection_monitor(self):
        while self.running and not self.shutdown_event.is_set():
            if not self.monitoring_enabled:
                self.shutdown_event.wait(0.2)
                continue

            generation = self.monitor_generation

            try:
                value = self.monitor.get_network_status()
                self._queue_metric(
                    "status",
                    generation,
                    status=value
                )

            except Exception as error:
                print("Connection monitor error:", error)

            self._worker_wait(3)

    def background_interface_monitor(self):
        while self.running and not self.shutdown_event.is_set():
            if not self.monitoring_enabled:
                self.shutdown_event.wait(0.2)
                continue

            generation = self.monitor_generation

            try:
                interface, local_ip = self.monitor.get_interface_info()

                self._queue_metric(
                    "interface",
                    generation,
                    interface=interface,
                    ip=local_ip
                )

            except Exception as error:
                print("Interface monitor error:", error)

            self._worker_wait(5)

    # ===================== JITTER =====================

    def update_jitter(self, ping):
        if ping is None:
            return

        ping = self.safe_number(ping, default=None)

        if ping is None:
            return

        self.jitter_value = calculate_jitter_ewma(
            self.jitter_value,
            self.previous_successful_ping,
            ping,
            alpha=0.25
        )

        self.previous_successful_ping = ping
        self.successful_pings.append(ping)

    # ===================== QUEUE PROCESSING =====================

    def process_queue(self):
        if not self.running:
            return

        while True:
            try:
                data = self.data_queue.get_nowait()
            except queue.Empty:
                break

            if not self.monitoring_enabled:
                continue

            if data.get("generation") != self.monitor_generation:
                continue

            if data["type"] == "speed":
                download = data["download"]
                upload = data["upload"]
                timestamp = data["timestamp"]

                self.download_total += data.get("downloaded_bytes", 0)
                self.upload_total += data.get("uploaded_bytes", 0)

                if self.last_speed_timestamp is not None:
                    sample_elapsed = timestamp - self.last_speed_timestamp

                    if 0 < sample_elapsed <= 10:
                        self.observed_seconds += sample_elapsed

                self.last_speed_timestamp = timestamp

                self.traffic_history.append(
                    (timestamp, download, upload)
                )

                self.prune_history(timestamp)

                self.current_download = download
                self.current_upload = upload

                self.max_download = max(
                    self.max_download, download
                )
                self.max_upload = max(
                    self.max_upload, upload
                )

                self.download_sum += download
                self.upload_sum += upload
                self.sample_count += 1

                self.set_speed_card(
                    self.download_card, download, BLUE
                )
                self.set_speed_card(
                    self.upload_card, upload, PURPLE
                )

                self.update_statistics()

            elif data["type"] == "ping":
                if (
                    data.get("ping_generation") != self.ping_generation
                    or data.get("target") != self.monitor.ping_target
                ):
                    continue

                self.latest_ping = data.get("ping")

                # Each individual ping contributes exactly one success/failure
                # sample to the same rolling window (last 10 probes).
                self.ping_results.append(self.latest_ping is not None)

                if self.latest_ping is not None:
                    self.update_jitter(self.latest_ping)
                else:
                    # A failed probe breaks the consecutive-sample chain.
                    # Do not calculate jitter across an outage or timeout.
                    self.previous_successful_ping = None
                    self.jitter_value = None
                    self.successful_pings.clear()

                if len(self.ping_results) == self.ping_results.maxlen:
                    lost = self.ping_results.count(False)
                    self.latest_loss = (
                        lost / len(self.ping_results)
                    ) * 100.0
                else:
                    # Do not claim 0% until a complete 10-probe window exists.
                    self.latest_loss = None

                self.update_metric_cards()

            elif data["type"] == "status":
                self.latest_status = str(
                    data.get("status", "Checking")
                )
                if self.latest_status.lower() == "disconnected":
                    # Clear the jitter baseline while the connection is down.
                    self.previous_successful_ping = None
                    self.jitter_value = None
                    self.successful_pings.clear()
                self.update_metric_cards()

            elif data["type"] == "interface":
                self.latest_ip = str(data.get("ip", "N/A"))
                self.latest_interface = str(
                    data.get("interface", "Unknown")
                )
                self.update_metric_cards()

        if self.running:
            self.root.after(100, self.process_queue)

    def prune_history(self, current_timestamp):
        cutoff = current_timestamp - 60

        while (
            self.traffic_history
            and self.traffic_history[0][0] < cutoff
        ):
            self.traffic_history.popleft()

    # ===================== METRIC CARDS =====================

    def update_metric_cards(self):
        if self.latest_ping is None:
            ping_text = "Timeout / N/A"
            ping_color = RED

        else:
            ping_text = (
                "<1 ms" if self.latest_ping < 1
                else f"{self.latest_ping:.0f} ms"
            )

            ping_color = (
                RED
                if self.latest_ping >= self.ping_warning_ms
                else GREEN
            )

        self.ping_card["value"].configure(
            text=ping_text,
            text_color=ping_color
        )

        if self.latest_loss is None:
            loss_text = "N/A"
            loss_color = MUTED

        else:
            loss_text = f"{self.latest_loss:.0f}%"

            if self.latest_loss > self.loss_warning_percent:
                loss_color = RED
            elif self.latest_loss > 0:
                loss_color = YELLOW
            else:
                loss_color = GREEN

        self.loss_card["value"].configure(
            text=loss_text,
            text_color=loss_color
        )

        if self.latest_status == "Connected":
            self.status_card["value"].configure(
                text="Online",
                text_color=GREEN
            )

        elif self.latest_status == "Disconnected":
            self.status_card["value"].configure(
                text="Offline",
                text_color=RED
            )

        else:
            self.status_card["value"].configure(
                text="Checking",
                text_color=YELLOW
            )

        self.ip_card["value"].configure(
            text=self.shorten_text(self.latest_ip, 22)
        )

        self.interface_label.configure(
            text=self.shorten_text(self.latest_interface, 30)
        )

        jitter_text = (
            f"{self.jitter_value:.2f} ms"
            if self.jitter_value is not None
            else "N/A"
        )

        self.sidebar_jitter_label.configure(text=jitter_text)

    # ===================== SPEED FORMATTING =====================

    @staticmethod
    def format_speed(speed):
        speed = max(0.0, float(speed))

        if speed >= 1024 * 1024:
            return f"{speed / (1024 * 1024):.2f} MB/s"

        if speed >= 1024:
            return f"{speed / 1024:.2f} KB/s"

        return f"{speed:.2f} B/s"

    def set_speed_card(self, card, speed, accent):
        speed = max(0.0, self.safe_number(speed))

        if speed >= 1024 * 1024:
            value = speed / (1024 * 1024)
            unit = "MB/s"

        elif speed >= 1024:
            value = speed / 1024
            unit = "KB/s"

        else:
            value = speed
            unit = "B/s"

        card["value"].configure(text=f"{value:.2f}")
        card["unit"].configure(
            text=unit,
            text_color=accent
        )

    # ===================== STATISTICS =====================

    def update_statistics(self):
        if self.sample_count == 0:
            return

        average_download = (
            self.download_total / self.observed_seconds
            if self.observed_seconds > 0 else 0.0
        )

        average_upload = (
            self.upload_total / self.observed_seconds
            if self.observed_seconds > 0 else 0.0
        )

        self.max_download_card.configure(
            text=self.format_speed(self.max_download)
        )
        self.avg_download_card.configure(
            text=self.format_speed(average_download)
        )
        self.max_upload_card.configure(
            text=self.format_speed(self.max_upload)
        )
        self.avg_upload_card.configure(
            text=self.format_speed(average_upload)
        )

    # ===================== GRAPH / DASHBOARD =====================

    def update_dashboard(self):
        if not self.running:
            return

        now = time.monotonic()
        self.prune_history(now)

        samples = list(self.traffic_history)

        x_values = [
            timestamp - now
            for timestamp, _, _ in samples
        ]

        download_values = [
            download
            for _, download, _ in samples
        ]

        upload_values = [
            upload
            for _, _, upload in samples
        ]

        maximum_speed = max(
            max(download_values, default=0),
            max(upload_values, default=0)
        )

        if maximum_speed >= 1024 * 1024:
            divisor = 1024 * 1024
            unit = "MB/s"

        elif maximum_speed >= 1024:
            divisor = 1024
            unit = "KB/s"

        else:
            divisor = 1
            unit = "B/s"

        self.download_line.set_data(
            x_values,
            [value / divisor for value in download_values]
        )

        self.upload_line.set_data(
            x_values,
            [value / divisor for value in upload_values]
        )

        self.ax.set_xlim(-60, 0)
        self.ax.set_ylabel(unit, color=MUTED, fontsize=9)

        graph_max = max(
            max(
                (value / divisor for value in download_values),
                default=0
            ),
            max(
                (value / divisor for value in upload_values),
                default=0
            ),
            1
        )

        self.ax.set_ylim(0, graph_max * 1.2)

        self.canvas.draw_idle()

        elapsed = int(time.time() - self.start_time)

        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60

        self.uptime_label.configure(
            text=f"{hours:02}:{minutes:02}:{seconds:02}"
        )

        total = self.download_total + self.upload_total

        self.total_label.configure(
            text=f"{total / (1024 * 1024):.2f} MB"
        )

        self.root.after(1000, self.update_dashboard)

    # ===================== EXPORT DATA =====================

    def build_export_data(self):
        elapsed = int(time.time() - self.start_time)

        average_download = (
            self.download_total / self.observed_seconds
            if self.observed_seconds > 0 else 0.0
        )

        average_upload = (
            self.upload_total / self.observed_seconds
            if self.observed_seconds > 0 else 0.0
        )

        now = time.monotonic()
        self.prune_history(now)

        history = []

        for timestamp, download, upload in self.traffic_history:
            history.append({
                "seconds_ago": round(max(0, now - timestamp), 2),
                "download_bytes_per_second": round(download, 2),
                "upload_bytes_per_second": round(upload, 2)
            })

        return {
            "project": "Network Monitor",
            "version": "4.2",
            "speed_unit": "bytes per second",
            "packet_loss_probe_count": self.monitor.PACKET_LOSS_PING_COUNT,
            "generated_at": datetime.now().isoformat(
                timespec="seconds"
            ),
            "session": {
                "uptime_seconds": elapsed,
                "uptime": (
                    f"{elapsed // 3600:02}:"
                    f"{(elapsed % 3600) // 60:02}:"
                    f"{elapsed % 60:02}"
                )
            },
            "connection": {
                "ping_target": self.monitor.ping_target,
                "ping_ms": self.latest_ping,
                "packet_loss_percent": self.latest_loss,
                "tcp_status": self.latest_status,
                "local_ip": self.latest_ip,
                "network_interface": self.latest_interface,
                "jitter_average_ms": (
                    round(self.jitter_value, 2)
                    if self.jitter_value is not None
                    else None
                ),
                "jitter_sample_count": len(self.successful_pings),
                "jitter_method": "EWMA",
                "jitter_alpha": 0.25
            },
            "speed": {
                "current_download_bytes_per_second": round(
                    self.current_download, 2
                ),
                "current_upload_bytes_per_second": round(
                    self.current_upload, 2
                ),
                "maximum_download_bytes_per_second": round(
                    self.max_download, 2
                ),
                "average_download_bytes_per_second": round(
                    average_download, 2
                ),
                "maximum_upload_bytes_per_second": round(
                    self.max_upload, 2
                ),
                "average_upload_bytes_per_second": round(
                    average_upload, 2
                ),
                "total_download_bytes": round(
                    self.download_total, 2
                ),
                "total_upload_bytes": round(
                    self.upload_total, 2
                )
            },
            "history_60_seconds": history
        }

    def export_report(self):
        filename = datetime.now().strftime(
            "network_report_%Y%m%d_%H%M%S"
        )

        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            initialfile=filename,
            filetypes=[
                ("CSV files", "*.csv"),
                ("JSON files", "*.json")
            ],
            title="Export Network Report"
        )

        if not filepath:
            return

        try:
            data = self.build_export_data()

            if filepath.lower().endswith(".json"):
                with open(
                    filepath,
                    "w",
                    encoding="utf-8"
                ) as file:
                    json.dump(
                        data,
                        file,
                        indent=4,
                        ensure_ascii=False
                    )

            else:
                if not filepath.lower().endswith(".csv"):
                    filepath += ".csv"

                with open(
                    filepath,
                    "w",
                    newline="",
                    encoding="utf-8-sig"
                ) as file:
                    writer = csv.writer(file)

                    writer.writerow(["NETWORK MONITOR REPORT"])
                    writer.writerow(["Version", data["version"]])
                    writer.writerow(["Generated", data["generated_at"]])
                    writer.writerow([])

                    writer.writerow(["SESSION"])
                    for key, value in data["session"].items():
                        writer.writerow([key, value])

                    writer.writerow([])
                    writer.writerow(["CONNECTION"])

                    for key, value in data["connection"].items():
                        writer.writerow([
                            key,
                            "N/A" if value is None else value
                        ])

                    writer.writerow([])
                    writer.writerow(["SPEED STATISTICS"])

                    for key, value in data["speed"].items():
                        writer.writerow([key, value])

                    writer.writerow([])
                    writer.writerow([
                        "SECONDS AGO",
                        "DOWNLOAD (BYTES/SEC)",
                        "UPLOAD (BYTES/SEC)"
                    ])

                    for sample in data["history_60_seconds"]:
                        writer.writerow([
                            sample["seconds_ago"],
                            sample["download_bytes_per_second"],
                            sample["upload_bytes_per_second"]
                        ])

            messagebox.showinfo(
                "Export Successful",
                "Network report exported successfully.",
                parent=self.root
            )

        except Exception as error:
            messagebox.showerror(
                "Export Failed",
                f"Could not export report:\n{error}",
                parent=self.root
            )

    # ===================== CLOSE =====================

    def close(self):
        if not self.running:
            return

        self.running = False
        self.monitoring_enabled = False
        self.shutdown_event.set()
        self.monitor_generation += 1
        self.clear_queue()

        if self.settings_window is not None:
            try:
                self.settings_window.destroy()
            except Exception:
                pass
            self.settings_window = None

        for thread in getattr(self, "worker_threads", []):
            if thread.is_alive():
                thread.join(timeout=0.2)

        try:
            self.root.destroy()
        except Exception:
            pass


    def run(self):
        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.close
        )
        self.root.mainloop()