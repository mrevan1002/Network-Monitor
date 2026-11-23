
import platform
import re
import socket
import subprocess
import time
import ipaddress

import psutil


class NetworkMonitor:

    PING_HOSTS = ("1.1.1.1", "8.8.8.8")

    def __init__(self, ping_target="1.1.1.1"):
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

        self.ping_target = host

    @staticmethod
    def _read_network_counters():
        counters = psutil.net_io_counters(pernic=False)

        if counters is None:
            return 0, 0

        return counters.bytes_recv, counters.bytes_sent

    def reset_speed_baseline(self):
        """Reset counters after monitoring resumes."""
        self._previous_time = time.monotonic()
        self._previous_counters = self._read_network_counters()

    def get_speed(self):
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

    def get_ping(self, host=None):
        host = host or self.ping_target

        try:
            ipaddress.ip_address(host)
        except ValueError:
            return None

        if platform.system().lower() == "windows":
            command = ["ping", "-n", "1", "-w", "2000", host]
        else:
            command = ["ping", "-c", "1", "-W", "2", host]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
                errors="replace",
            )

            output = result.stdout + result.stderr

            if result.returncode != 0:
                return None

            if re.search(
                r"time\s*<\s*1\s*ms",
                output,
                re.IGNORECASE,
            ):
                return 0.5

            match = re.search(
                r"time\s*[=<]\s*(\d+(?:\.\d+)?)\s*ms",
                output,
                re.IGNORECASE,
            )

            if match:
                return float(match.group(1))

            return None

        except (subprocess.SubprocessError, OSError):
            return None

    def get_packet_loss(self, host=None):
        host = host or self.ping_target

        try:
            ipaddress.ip_address(host)
        except ValueError:
            return None

        if platform.system().lower() == "windows":
            command = ["ping", "-n", "4", "-w", "2000", host]
        else:
            command = ["ping", "-c", "4", "-W", "2", host]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                errors="replace",
            )

            output = result.stdout + result.stderr

            patterns = [
                r"\((\d+(?:\.\d+)?)%\s*loss\)",
                r"(\d+(?:\.\d+)?)%\s*(?:packet\s*)?loss",
            ]

            for pattern in patterns:
                match = re.search(
                    pattern,
                    output,
                    re.IGNORECASE,
                )

                if match:
                    return float(match.group(1))

            match = re.search(
                r"Lost\s*=\s*(\d+)",
                output,
                re.IGNORECASE,
            )

            if match:
                return float(int(match.group(1)) * 25)

            return None

        except (subprocess.SubprocessError, OSError):
            return None

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

        except Exception:
            return "Unknown", "N/A"
