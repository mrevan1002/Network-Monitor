
import platform
import re
import socket
import subprocess
import threading
import time
import ipaddress

import psutil


class NetworkMonitor:
    PING_HOSTS = ("1.1.1.1", "8.8.8.8")

    def __init__(self, ping_target="1.1.1.1"):
        self._lock = threading.RLock()
        self.ping_target = ping_target

        self.connection_targets = [
            ("1.1.1.1", 53),
            ("8.8.8.8", 53),
        ]

        self._previous_time = time.monotonic()
        self._previous_counters = self._read_network_counters()

    def set_ping_target(self, host):
        """Validate and update the ping target."""
        host = host.strip()

        try:
            ipaddress.ip_address(host)
        except ValueError as error:
            raise ValueError(
                "Enter a valid IPv4 or IPv6 address."
            ) from error

        with self._lock:
            self.ping_target = host

    def _get_ping_target(self, host=None):
        if host is not None:
            return host.strip()

        with self._lock:
            return self.ping_target

    @staticmethod
    def _read_network_counters():
        try:
            counters = psutil.net_io_counters(pernic=False)

            if counters is None:
                return 0, 0

            return counters.bytes_recv, counters.bytes_sent

        except (psutil.Error, OSError):
            return 0, 0

    def reset_speed_baseline(self):
        """Reset counters after monitoring resumes."""
        with self._lock:
            self._previous_time = time.monotonic()
            self._previous_counters = self._read_network_counters()

    def get_speed(self):
        """Return download and upload speed in bytes per second."""
        with self._lock:
            current_time = time.monotonic()
            current_counters = self._read_network_counters()

            elapsed = current_time - self._previous_time

            previous_recv, previous_sent = self._previous_counters
            current_recv, current_sent = current_counters

            self._previous_time = current_time
            self._previous_counters = current_counters

        if elapsed <= 0:
            return 0.0, 0.0

        download = max(0, current_recv - previous_recv)
        upload = max(0, current_sent - previous_sent)

        return download / elapsed, upload / elapsed

    @staticmethod
    def _valid_ip(host):
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            return False

    @staticmethod
    def _ping_command(host, count=1):
        system = platform.system().lower()

        if system == "windows":
            return ["ping", "-n", str(count), "-w", "2000", host]

        if system == "darwin":
            return ["ping", "-c", str(count), "-W", "2000", host]

        return ["ping", "-c", str(count), "-W", "2", host]

    @staticmethod
    def _run_ping(command, timeout):
        try:
            return subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                errors="replace",
            )
        except (subprocess.SubprocessError, OSError):
            return None

    @staticmethod
    def _parse_ping_time(output):
        # Windows may report: time<1ms
        if re.search(r"time\s*<\s*1\s*ms", output, re.IGNORECASE):
            return 0.5

        # Windows/Linux may report: time=12ms or time=12.34 ms
        # Decimal commas are also accepted.
        match = re.search(
            r"time\s*[=<]\s*(\d+(?:[.,]\d+)?)\s*ms",
            output,
            re.IGNORECASE,
        )

        if not match:
            return None

        try:
            return float(match.group(1).replace(",", "."))
        except ValueError:
            return None

    def get_ping(self, host=None):
        host = self._get_ping_target(host)

        if not self._valid_ip(host):
            return None

        result = self._run_ping(
            self._ping_command(host, count=1),
            timeout=4,
        )

        if result is None or result.returncode != 0:
            return None

        output = result.stdout + result.stderr
        return self._parse_ping_time(output)

    @staticmethod
    def _parse_packet_loss(output):
        # Works with Windows: (0% loss)
        # and Linux: 0% packet loss
        match = re.search(
            r"(\d+(?:[.,]\d+)?)%\s*(?:packet\s*)?loss",
            output,
            re.IGNORECASE,
        )

        if match:
            try:
                return float(match.group(1).replace(",", "."))
            except ValueError:
                return None

        # Fallback for Windows output:
        # Sent = 4, Received = 3, Lost = 1
        sent_match = re.search(
            r"Sent\s*=\s*(\d+)",
            output,
            re.IGNORECASE,
        )
        lost_match = re.search(
            r"Lost\s*=\s*(\d+)",
            output,
            re.IGNORECASE,
        )

        if sent_match and lost_match:
            sent = int(sent_match.group(1))
            lost = int(lost_match.group(1))

            if sent > 0:
                return (lost / sent) * 100

        return None

    def get_packet_loss(self, host=None):
        host = self._get_ping_target(host)

        if not self._valid_ip(host):
            return None

        result = self._run_ping(
            self._ping_command(host, count=4),
            timeout=11,
        )

        if result is None:
            return None

        output = result.stdout + result.stderr
        return self._parse_packet_loss(output)

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
            )

            preferred_names = (
                "wi-fi",
                "wifi",
                "wireless",
                "wlan",
                "ethernet",
            )

            for name, addresses in interfaces.items():
                if name not in stats or not stats[name].isup:
                    continue

                ipv4 = None

                for address in addresses:
                    if address.family == socket.AF_INET:
                        candidate = address.address

                        if (
                            not candidate.startswith("127.")
                            and candidate != "0.0.0.0"
                        ):
                            ipv4 = candidate
                            break

                if not ipv4:
                    continue

                lower_name = name.lower()

                if any(word in lower_name for word in excluded):
                    continue

                item = (name, ipv4)

                if any(
                    word in lower_name
                    for word in preferred_names
                ):
                    preferred.append(item)
                else:
                    fallback.append(item)

            if preferred:
                return preferred[0]

            if fallback:
                return fallback[0]

            return "Unknown", "N/A"

        except (psutil.Error, OSError):
            return "Unknown", "N/A"
