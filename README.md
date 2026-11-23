# Network Monitor v3.2

A real-time network monitoring application built with Python. Monitor your internet connection, network speed, latency, packet loss, and traffic statistics through a modern desktop dashboard.

## Overview

Network Monitor provides a visual overview of network performance with live statistics, graphical traffic monitoring, and configurable connection checks.

## Features

- **Real-Time Speed Monitoring** — Track download and upload speeds.
- **Network Traffic Graph** — Visualize network activity over the last 60 seconds.
- **Speed Statistics** — View current, maximum, and average speeds.
- **Ping Monitoring** — Measure network latency using a configurable IPv4 or IPv6 target.
- **Packet Loss Detection** — Monitor packet loss percentage.
- **Jitter Calculation** — Calculate average variation between consecutive successful ping measurements.
- **TCP Connectivity Check** — Check network connectivity independently of ICMP ping.
- **Network Interface Information** — Display the active network interface and local IP address.
- **Traffic Statistics** — Track total downloaded and uploaded data.
- **CSV and JSON Export** — Export monitoring reports.
- **Pause and Resume** — Temporarily pause and resume monitoring.
- **Customizable Settings** — Configure monitoring intervals and warning thresholds.
- **Modern Desktop Interface** — Dark-themed dashboard built with CustomTkinter.

## Screenshots

<!-- Add application screenshots here -->

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

1. Clone the repository:

```bash
git clone https://github.com/mrevan1002/Network-Monitor.git
```

2. Navigate to the project directory:

```bash
cd Network-Monitor
```

3. Install the dependencies:

```bash
pip install -r requirements.txt
```

4. Run the application:

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
├── .gitignore
└── LICENSE
```

## Configuration

The Settings panel allows you to configure:

- Ping target (IPv4 or IPv6)
- Speed monitoring interval
- High ping warning threshold
- Packet loss warning threshold

## Data Export

Network monitoring reports can be exported in:

- CSV format
- JSON format

Reports include connection information, speed statistics, session details, and recent traffic history.

## Notes

- Ping and packet loss measurements depend on the availability of the selected target.
- Some networks may block ICMP requests.
- TCP connectivity checks are performed separately from ICMP ping measurements.
- Network speed measurements represent the traffic observed by the computer.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Author

Developed as a Python network monitoring project.