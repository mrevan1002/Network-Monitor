# Network Monitor v3.2

A real-time network monitoring application built with Python. Monitor your internet connection, network speed, latency, packet loss, and network traffic through a modern desktop dashboard.

## Overview

Network Monitor is a desktop application designed to provide real-time insights into network performance.

It combines live network statistics, graphical traffic visualization, connectivity checks, and configurable monitoring settings in a clean, dark-themed interface.

## Features

- **Real-Time Speed Monitoring** — Track download and upload speeds.
- **Network Traffic Graph** — Visualize network activity over the last 60 seconds.
- **Speed Statistics** — View current, maximum, and average speeds.
- **Ping Monitoring** — Measure network latency using configurable IPv4 or IPv6 targets.
- **Packet Loss Detection** — Monitor packet loss percentage.
- **Jitter Calculation** — Calculate latency variation between consecutive successful ping measurements.
- **TCP Connectivity Check** — Verify network connectivity independently of ICMP ping.
- **Network Interface Information** — Display the active network interface and local IP address.
- **Traffic Statistics** — Track total downloaded and uploaded data.
- **CSV and JSON Export** — Export network monitoring reports.
- **Pause and Resume** — Temporarily pause and resume monitoring.
- **Customizable Settings** — Configure monitoring intervals and warning thresholds.
- **Modern Desktop Interface** — Dark-themed dashboard built with CustomTkinter.

## Screenshots

<!-- Add application screenshots here -->

<!-- Example:
![Network Monitor Dashboard](screenshots/dashboard.png)
-->

## Technologies Used

- Python
- CustomTkinter
- Matplotlib
- psutil
- Socket
- Threading

## Requirements

- Python 3.10 or newer
- Windows, Linux, or macOS
- Internet connection for network checks

## Installation

**1. Clone the repository**

```bash
git clone https://github.com/mrevan1002/Network-Monitor.git
```

**2. Navigate to the project directory**

```bash
cd Network-Monitor
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

**4. Run the application**

```bash
python main.py
```

## Project Structure

```text
Network-Monitor/
│
├── main.py
├── dashboard.py
├── monitor.py
├── requirements.txt
├── README.md
├── LICENSE
└── .gitignore
```

## Configuration

The Settings panel provides options to configure:

- Ping target (IPv4 or IPv6)
- Speed monitoring interval
- High ping warning threshold
- Packet loss warning threshold

## Data Export

Network monitoring reports can be exported in:

- CSV format
- JSON format

Reports include connection information, speed statistics, session details, and recent traffic history.

## Technical Notes

- Ping and packet loss measurements depend on the availability of the selected target.
- Some networks may block ICMP requests.
- TCP connectivity checks are performed separately from ICMP ping measurements.
- Network speed measurements represent traffic observed by the computer.
- Network monitoring results may vary depending on the operating system and network environment.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Author

Developed as a Python network monitoring project.

**GitHub:** [@mrevan1002](https://github.com/mrevan1002)
