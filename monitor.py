

"""Network measurement helpers for Network Monitor 4.1."""

import ipaddress
import platform
import re
import socket
import subprocess
import threading
import time

import psutil


def calculate_jitter_ewma(
    previous_jitter,
    previous_ping,
    current_ping,
    alpha=0.25,
):
    """Calculate jitter using exponentially weighted moving average."""
    if previous_ping is None or current_ping is None:
        return previous_jitter

    try:
        delta = abs(float(current_ping) - float(previous_ping))
        alpha = float(alpha)
    except (TypeError, ValueError):
        return previous_jitter

    if not 0.0 < alpha <= 1.0:
        raise ValueError("alpha must be in the range (0, 1].")

    if previous_jitter is None:
        return delta

    return (
        alpha * delta
        + (1.0 - alpha) * float(previous_jitter)
    )


class NetworkMonitor:
    """Collect network speed, latency and packet-loss data."""

    CONNECTION_TARGETS = (
        ("1.1.1.1", 53),
        ("8.8.8.8", 53),
    )

    PACKET_LOSS_PING_COUNT = 10

    def __init__(self, ping_target="1.1.1.1"):
        self._lock = threading.RLock()
        self._ping_target = self._validate_ip(ping_target)

        self.connection_targets = list(self.CONNECTION_TARGETS)

        self._previous_time = time.monotonic()
        self._previous_counters = self._read_network_counters()

    @staticmethod
    def _validate_ip(host):
        if not isinstance(host, str) or not host.strip():
            raise ValueError("Enter a valid IPv4 or IPv6 address.")

        host = host.strip()

        try:
            ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError(
                "Enter a valid IPv4 or IPv6 address."
            ) from exc

        return host

    @property
    def ping_target(self):
        with self._lock:
            return self._ping_target

    def set_ping_target(self, host):
        host = self._validate_ip(host)

        with self._lock:
            self._ping_target = host

    def _get_ping_target(self, host=None):
        if host is not None:
            return self._validate_ip(host)

        return self.ping_target

    @staticmethod
    def _read_network_counters():
        try:
            counters = psutil.net_io_counters(pernic=False)

            if counters is None:
                return 0, 0

            return (
                int(counters.bytes_recv),
                int(counters.bytes_sent),
            )

        except (psutil.Error, OSError):
            return 0, 0

    def reset_speed_baseline(self):
        """Reset network traffic measurement baseline."""
        with self._lock:
            self._previous_time = time.monotonic()
            self._previous_counters = self._read_network_counters()

    def get_speed_sample(self):
        """Return download/upload speeds in bytes per second."""
        with self._lock:
            current_time = time.monotonic()

            current_recv, current_sent = (
                self._read_network_counters()
            )

            previous_recv, previous_sent = self._previous_counters

            elapsed = current_time - self._previous_time

            self._previous_time = current_time
            self._previous_counters = (
                current_recv,
                current_sent,
            )

        received = max(0, current_recv - previous_recv)
        sent = max(0, current_sent - previous_sent)

        if elapsed <= 0:
            return 0.0, 0.0, received, sent

        download = received / elapsed
        upload = sent / elapsed

        return download, upload, received, sent

    def get_speed(self):
        """Backward-compatible speed-only API."""
        download, upload, _, _ = self.get_speed_sample()

        return download, upload

    @staticmethod
    def _ping_command(host, count=1):
        system = platform.system().lower()

        if system == "windows":
            return [
                "ping",
                "-n",
                str(count),
                "-w",
                "2000",
                host,
            ]

        if system == "darwin":
            return [
                "ping",
                "-c",
                str(count),
                "-W",
                "2000",
                host,
            ]

        return [
            "ping",
            "-c",
            str(count),
            "-W",
            "2",
            host,
        ]

    @staticmethod
    def _run_ping(command, timeout):
        try:
            options = {}
            if platform.system().lower() == "windows":
                options["creationflags"] = getattr(
                    subprocess, "CREATE_NO_WINDOW", 0
                )

            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                errors="replace",
                **options,
            )

        except (subprocess.SubprocessError, OSError):
            return None

    @staticmethod
    def _parse_ping_time(output):
        if re.search(
            r"time\s*<\s*1\s*ms",
            output,
            re.IGNORECASE,
        ):
            return 0.5

        match = re.search(
            r"time\s*[=<]\s*(\d+(?:[.,]\d+)?)\s*ms",
            output,
            re.IGNORECASE,
        )

        if not match:
            return None

        try:
            return float(
                match.group(1).replace(",", ".")
            )

        except ValueError:
            return None

    def get_ping(self, host=None):
        try:
            host = self._get_ping_target(host)
        except ValueError:
            return None

        result = self._run_ping(
            self._ping_command(host),
            timeout=4,
        )

        if result is None:
            return None

        return self._parse_ping_time(
            result.stdout + result.stderr
        )

    @staticmethod
    def _parse_packet_loss(output):
        match = re.search(
            r"(\d+(?:[.,]\d+)?)%\s*(?:packet\s*)?loss",
            output,
            re.IGNORECASE,
        )

        if match:
            try:
                value = float(
                    match.group(1).replace(",", ".")
                )

                return min(100.0, max(0.0, value))

            except ValueError:
                return None

        sent = re.search(
            r"Sent\s*=\s*(\d+)",
            output,
            re.IGNORECASE,
        )

        lost = re.search(
            r"Lost\s*=\s*(\d+)",
            output,
            re.IGNORECASE,
        )

        if sent and lost:
            sent_count = int(sent.group(1))
            lost_count = int(lost.group(1))

            if sent_count > 0:
                return min(
                    100.0,
                    max(
                        0.0,
                        lost_count / sent_count * 100,
                    ),
                )

        return None

    def get_packet_loss(self, host=None):
        try:
            host = self._get_ping_target(host)
        except ValueError:
            return None

        count = self.PACKET_LOSS_PING_COUNT

        result = self._run_ping(
            self._ping_command(host, count=count),
            timeout=(count * 2) + 4,
        )

        if result is None:
            return None

        return self._parse_packet_loss(
            result.stdout + result.stderr
        )

    def get_network_status(self):
        for host, port in self.connection_targets:
            try:
                with socket.create_connection(
                    (host, port),
                    timeout=1.5,
                ):
                    return "Connected"

            except OSError:
                continue

        return "Disconnected"

    def get_interface_info(self):
        """Return a likely active physical interface and IPv4."""
        try:
            interfaces = psutil.net_if_addrs()
            stats = psutil.net_if_stats()

            preferred = []
            fallback = []

            excluded = (
                "virtual",
                "vpn",
                "loopback",
                "vmware",
                "vbox",
                "hyper-v",
                "bluetooth",
                "docker",
                "wsl",
                "tunnel",
            )

            preferred_names = (
                "wi-fi",
                "wifi",
                "wireless",
                "wlan",
                "ethernet",
            )

            for name, addresses in interfaces.items():
                stat = stats.get(name)

                if stat is None or not stat.isup:
                    continue

                ipv4 = next(
                    (
                        address.address
                        for address in addresses
                        if address.family == socket.AF_INET
                        and not address.address.startswith("127.")
                        and address.address != "0.0.0.0"
                    ),
                    None,
                )

                if not ipv4:
                    continue

                lower = name.lower()

                if any(
                    word in lower
                    for word in excluded
                ):
                    continue

                item = (name, ipv4)

                if any(
                    word in lower
                    for word in preferred_names
                ):
                    preferred.append(item)
                else:
                    fallback.append(item)

            if preferred:
                return preferred[0]

            if fallback:
                return fallback[0]

        except (psutil.Error, OSError):
            pass

        return "Unknown", "N/A"

