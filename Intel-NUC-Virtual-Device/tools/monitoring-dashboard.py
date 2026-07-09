#!/usr/bin/env python3
"""
monitoring-dashboard.py - Real-time Monitoring Dashboard for Virtual Devices

This tool provides a comprehensive real-time monitoring dashboard for all
virtual devices on Intel NUC platforms with web-based and terminal interfaces.

Version: 1.0.0
Author: Intel NUC Virtual Device Platform Team
License: GPL v2
"""

import os
import sys
import json
import time
import threading
import logging
import argparse
import signal
import socket
import psutil
import curses
import datetime
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict, deque
from pathlib import Path
import subprocess
import re

# Try to import web dependencies
try:
    from flask import Flask, render_template, jsonify, request
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

try:
    import plotly
    import plotly.graph_objs as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Colors for output
COLORS = {
    'RESET': '\033[0m',
    'RED': '\033[31m',
    'GREEN': '\033[32m',
    'YELLOW': '\033[33m',
    'BLUE': '\033[34m',
    'MAGENTA': '\033[35m',
    'CYAN': '\033[36m',
    'WHITE': '\033[37m',
    'BOLD': '\033[1m'
}

# Constants
HISTORY_SIZE = 1000
DEFAULT_INTERVAL = 2
MAX_DEVICES = 100

# ==================== Data Classes ====================

@dataclass
class DeviceMetric:
    """Device metric data"""
    timestamp: float
    value: float
    unit: str
    label: str

@dataclass
class SystemMetric:
    """System metric data"""
    timestamp: float
    cpu_percent: float
    memory_percent: float
    disk_usage: float
    network_rx: float
    network_tx: float
    temperature: float

@dataclass
class NetworkStats:
    """Network statistics"""
    rx_bytes: int
    tx_bytes: int
    rx_packets: int
    tx_packets: int
    rx_errors: int
    tx_errors: int
    rx_dropped: int
    tx_dropped: int

@dataclass
class DeviceStats:
    """Device statistics"""
    name: str
    type: str
    status: str
    uptime: float
    metrics: Dict[str, List[DeviceMetric]] = field(default_factory=dict)

# ==================== Data Collector ====================

class DataCollector:
    """Collect system and device data"""
    
    def __init__(self):
        self.system_metrics = deque(maxlen=HISTORY_SIZE)
        self.device_stats: Dict[str, DeviceStats] = {}
        self.lock = threading.Lock()
        self.running = False
        self.collector_thread = None
        self.interval = DEFAULT_INTERVAL
        
        # Network interfaces to monitor
        self.net_interfaces = []
        self._discover_interfaces()
    
    def _discover_interfaces(self):
        """Discover network interfaces"""
        try:
            with open('/proc/net/dev', 'r') as f:
                lines = f.readlines()
                for line in lines[2:]:  # Skip header
                    parts = line.split(':')
                    if len(parts) >= 2:
                        iface = parts[0].strip()
                        if iface not in ['lo']:  # Skip loopback
                            self.net_interfaces.append(iface)
        except:
            pass
    
    def start(self, interval: int = DEFAULT_INTERVAL):
        """Start data collection"""
        self.running = True
        self.interval = interval
        self.collector_thread = threading.Thread(target=self._collect_loop)
        self.collector_thread.daemon = True
        self.collector_thread.start()
        logger.info(f"Data collector started (interval: {interval}s)")
    
    def stop(self):
        """Stop data collection"""
        self.running = False
        if self.collector_thread:
            self.collector_thread.join(timeout=2)
        logger.info("Data collector stopped")
    
    def _collect_loop(self):
        """Main collection loop"""
        while self.running:
            try:
                self._collect_system_metrics()
                self._collect_device_metrics()
                time.sleep(self.interval)
            except Exception as e:
                logger.error(f"Collection error: {e}")
    
    def _collect_system_metrics(self):
        """Collect system metrics"""
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # Memory
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Disk
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            
            # Network
            net_io = psutil.net_io_counters()
            rx = net_io.bytes_recv
            tx = net_io.bytes_sent
            
            # Temperature (if available)
            temp = self._get_cpu_temperature()
            
            metric = SystemMetric(
                timestamp=time.time(),
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                disk_usage=disk_percent,
                network_rx=rx,
                network_tx=tx,
                temperature=temp
            )
            
            with self.lock:
                self.system_metrics.append(metric)
                
        except Exception as e:
            logger.error(f"System metrics collection error: {e}")
    
    def _get_cpu_temperature(self) -> float:
        """Get CPU temperature"""
        try:
            # Try thermal zone
            zones = Path('/sys/class/thermal/thermal_zone*/temp')
            temps = []
            for zone in zones.glob('*'):
                try:
                    with open(zone, 'r') as f:
                        temp = int(f.read().strip()) / 1000.0
                        temps.append(temp)
                except:
                    pass
            
            if temps:
                return max(temps)
            
            # Try lm-sensors
            result = subprocess.run(
                ['sensors', '-u'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'temp1_input' in line:
                        temp = float(line.split(':')[1].strip())
                        return temp
            
            return 0.0
            
        except:
            return 0.0
    
    def _collect_device_metrics(self):
        """Collect device metrics"""
        # Network devices
        for iface in self.net_interfaces:
            self._collect_network_stats(iface)
        
        # Disk devices
        self._collect_disk_stats()
        
        # USB devices
        self._collect_usb_stats()
    
    def _collect_network_stats(self, iface: str):
        """Collect network interface statistics"""
        try:
            stats_path = f'/sys/class/net/{iface}/statistics'
            if not os.path.exists(stats_path):
                return
            
            stats = {}
            for stat_file in ['rx_bytes', 'tx_bytes', 'rx_packets', 'tx_packets',
                             'rx_errors', 'tx_errors', 'rx_dropped', 'tx_dropped']:
                path = f"{stats_path}/{stat_file}"
                if os.path.exists(path):
                    with open(path, 'r') as f:
                        stats[stat_file] = int(f.read().strip())
            
            with self.lock:
                if iface not in self.device_stats:
                    self.device_stats[iface] = DeviceStats(
                        name=iface,
                        type='network',
                        status='running',
                        uptime=0
                    )
                
                dev_stats = self.device_stats[iface]
                
                # Update metrics
                for key, value in stats.items():
                    metric = DeviceMetric(
                        timestamp=time.time(),
                        value=value,
                        unit='bytes' if 'bytes' in key else 'packets',
                        label=key
                    )
                    if key not in dev_stats.metrics:
                        dev_stats.metrics[key] = []
                    dev_stats.metrics[key].append(metric)
                    
        except Exception as e:
            pass
    
    def _collect_disk_stats(self):
        """Collect disk statistics"""
        try:
            for disk in psutil.disk_io_counters(perdisk=True):
                if disk not in self.device_stats:
                    self.device_stats[disk] = DeviceStats(
                        name=disk,
                        type='disk',
                        status='running',
                        uptime=0
                    )
                
                stats = psutil.disk_io_counters(perdisk=True)[disk]
                dev_stats = self.device_stats[disk]
                
                # Add metrics
                metrics = {
                    'read_bytes': stats.read_bytes,
                    'write_bytes': stats.write_bytes,
                    'read_count': stats.read_count,
                    'write_count': stats.write_count
                }
                
                for key, value in metrics.items():
                    metric = DeviceMetric(
                        timestamp=time.time(),
                        value=value,
                        unit='bytes' if 'bytes' in key else 'ops',
                        label=key
                    )
                    if key not in dev_stats.metrics:
                        dev_stats.metrics[key] = []
                    dev_stats.metrics[key].append(metric)
                    
        except Exception as e:
            pass
    
    def _collect_usb_stats(self):
        """Collect USB statistics"""
        try:
            # Get USB devices
            result = subprocess.run(
                ['lsusb'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if not line:
                        continue
                    
                    # Parse USB device info
                    parts = line.split()
                    if len(parts) >= 6:
                        bus = parts[1]
                        device = parts[3][:-1]  # Remove ':'
                        vendor = parts[5]
                        product = ' '.join(parts[6:])
                        
                        name = f"usb_{bus}_{device}"
                        
                        with self.lock:
                            if name not in self.device_stats:
                                self.device_stats[name] = DeviceStats(
                                    name=name,
                                    type='usb',
                                    status='connected',
                                    uptime=0
                                )
                            
                            # Update device info
                            dev_stats = self.device_stats[name]
                            dev_stats.metadata = {
                                'bus': bus,
                                'device': device,
                                'vendor': vendor,
                                'product': product
                            }
                            
        except Exception as e:
            pass
    
    def get_system_metrics(self, last_n: int = None) -> List[SystemMetric]:
        """Get system metrics"""
        with self.lock:
            metrics = list(self.system_metrics)
            if last_n:
                return metrics[-last_n:]
            return metrics
    
    def get_device_stats(self, name: str = None) -> Dict[str, DeviceStats]:
        """Get device statistics"""
        with self.lock:
            if name:
                return {name: self.device_stats.get(name, None)}
            return dict(self.device_stats)
    
    def get_summary(self) -> Dict:
        """Get summary statistics"""
        with self.lock:
            summary = {
                'timestamp': time.time(),
                'system': {},
                'devices': {}
            }
            
            # System summary
            if self.system_metrics:
                latest = self.system_metrics[-1]
                summary['system'] = {
                    'cpu': latest.cpu_percent,
                    'memory': latest.memory_percent,
                    'disk': latest.disk_usage,
                    'temperature': latest.temperature
                }
            
            # Device summary
            for name, stats in self.device_stats.items():
                if name not in summary['devices']:
                    summary['devices'][name] = {
                        'type': stats.type,
                        'status': stats.status
                    }
            
            return summary

# ==================== Terminal Dashboard ====================

class TerminalDashboard:
    """Terminal-based monitoring dashboard"""
    
    def __init__(self, collector: DataCollector):
        self.collector = collector
        self.running = False
        self.stdscr = None
        self.refresh_rate = 1
        
        # Display state
        self.current_view = 'summary'
        self.selected_device = None
        self.scroll_offset = 0
        self.device_list_offset = 0
    
    def start(self):
        """Start terminal dashboard"""
        try:
            self.stdscr = curses.initscr()
            curses.cbreak()
            curses.noecho()
            curses.curs_set(0)
            self.stdscr.timeout(100)
            
            # Enable colors
            curses.start_color()
            curses.use_default_colors()
            
            # Define color pairs
            curses.init_pair(1, curses.COLOR_GREEN, -1)
            curses.init_pair(2, curses.COLOR_RED, -1)
            curses.init_pair(3, curses.COLOR_YELLOW, -1)
            curses.init_pair(4, curses.COLOR_BLUE, -1)
            curses.init_pair(5, curses.COLOR_CYAN, -1)
            curses.init_pair(6, curses.COLOR_MAGENTA, -1)
            curses.init_pair(7, curses.COLOR_WHITE, -1)
            
            self.running = True
            self._main_loop()
            
        except KeyboardInterrupt:
            pass
        finally:
            self._cleanup()
    
    def _cleanup(self):
        """Cleanup curses"""
        if self.stdscr:
            curses.nocbreak()
            self.stdscr.keypad(False)
            curses.echo()
            curses.endwin()
    
    def _main_loop(self):
        """Main dashboard loop"""
        while self.running:
            # Clear screen
            self.stdscr.clear()
            
            # Draw dashboard
            self._draw_header()
            self._draw_system_info()
            self._draw_devices()
            self._draw_footer()
            
            # Refresh
            self.stdscr.refresh()
            
            # Handle input
            try:
                key = self.stdscr.getch()
                self._handle_input(key)
            except:
                pass
            
            time.sleep(self.refresh_rate)
    
    def _draw_header(self):
        """Draw dashboard header"""
        height, width = self.stdscr.getmaxyx()
        
        # Title
        title = " Intel NUC Virtual Device Monitor "
        self.stdscr.attron(curses.A_BOLD)
        self.stdscr.attron(curses.color_pair(5))
        self.stdscr.addstr(0, 0, "=" * width)
        self.stdscr.addstr(0, (width - len(title)) // 2, title)
        self.stdscr.addstr(1, 0, "=" * width)
        self.stdscr.attroff(curses.color_pair(5))
        self.stdscr.attroff(curses.A_BOLD)
        
        # Time
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.stdscr.addstr(0, width - len(current_time) - 2, current_time)
        
        # View indicator
        view_text = f" View: {self.current_view.upper()} "
        self.stdscr.addstr(1, width - len(view_text) - 2, view_text)
    
    def _draw_system_info(self):
        """Draw system information"""
        height, width = self.stdscr.getmaxyx()
        
        # Get system metrics
        metrics = self.collector.get_system_metrics(last_n=1)
        if not metrics:
            return
        
        latest = metrics[-1]
        
        # Draw system info box
        box_y = 3
        box_height = 5
        box_width = min(50, width - 4)
        
        # Box border
        self.stdscr.attron(curses.color_pair(4))
        self.stdscr.addstr(box_y, 2, "┌" + "─" * (box_width - 2) + "┐")
        self.stdscr.addstr(box_y + box_height - 1, 2, "└" + "─" * (box_width - 2) + "┘")
        self.stdscr.attroff(curses.color_pair(4))
        
        # Labels
        self.stdscr.addstr(box_y, 4, "System Status")
        
        # CPU
        cpu_color = curses.color_pair(1) if latest.cpu_percent < 50 else curses.color_pair(2)
        self.stdscr.addstr(box_y + 1, 4, f"CPU:     {latest.cpu_percent:6.1f}%")
        self._draw_bar(box_y + 1, 20, box_width - 24, latest.cpu_percent / 100, cpu_color)
        
        # Memory
        mem_color = curses.color_pair(1) if latest.memory_percent < 50 else curses.color_pair(2)
        self.stdscr.addstr(box_y + 2, 4, f"Memory:  {latest.memory_percent:6.1f}%")
        self._draw_bar(box_y + 2, 20, box_width - 24, latest.memory_percent / 100, mem_color)
        
        # Disk
        disk_color = curses.color_pair(1) if latest.disk_usage < 50 else curses.color_pair(2)
        self.stdscr.addstr(box_y + 3, 4, f"Disk:    {latest.disk_usage:6.1f}%")
        self._draw_bar(box_y + 3, 20, box_width - 24, latest.disk_usage / 100, disk_color)
        
        # Temperature
        if latest.temperature > 0:
            temp_color = curses.color_pair(1) if latest.temperature < 60 else curses.color_pair(2)
            self.stdscr.addstr(box_y + 4, 4, f"Temp:    {latest.temperature:6.1f}°C")
    
    def _draw_bar(self, y: int, x: int, width: int, ratio: float, color: int):
        """Draw a progress bar"""
        if width <= 0:
            return
        
        filled = int(width * min(max(ratio, 0), 1))
        bar = "█" * filled + "░" * (width - filled)
        
        self.stdscr.attron(color)
        self.stdscr.addstr(y, x, bar)
        self.stdscr.attroff(color)
    
    def _draw_devices(self):
        """Draw device list"""
        height, width = self.stdscr.getmaxyx()
        
        # Get device stats
        devices = self.collector.get_device_stats()
        
        if not devices:
            self.stdscr.addstr(10, 4, "No devices detected")
            return
        
        # Device list box
        start_y = 10
        max_devices = min(len(devices), height - start_y - 4)
        
        self.stdscr.attron(curses.color_pair(4))
        self.stdscr.addstr(start_y - 1, 2, "┌" + "─" * (width - 4) + "┐")
        self.stdscr.addstr(start_y + max_devices + 1, 2, "└" + "─" * (width - 4) + "┘")
        self.stdscr.attroff(curses.color_pair(4))
        
        # Header
        self.stdscr.attron(curses.A_BOLD)
        self.stdscr.addstr(start_y - 1, 4, " Devices ")
        self.stdscr.addstr(start_y - 1, 20, "Type")
        self.stdscr.addstr(start_y - 1, 35, "Status")
        self.stdscr.addstr(start_y - 1, 45, "Metrics")
        self.stdscr.attroff(curses.A_BOLD)
        
        # Device list
        y = start_y
        for name, stats in list(devices.items())[:max_devices]:
            # Select color based on status
            if stats.status == 'running' or stats.status == 'connected':
                color = curses.color_pair(1)  # Green
            elif stats.status == 'stopped' or stats.status == 'disconnected':
                color = curses.color_pair(2)  # Red
            else:
                color = curses.color_pair(3)  # Yellow
            
            self.stdscr.attron(color)
            display_name = name[:15] + "..." if len(name) > 18 else name
            self.stdscr.addstr(y, 4, display_name)
            self.stdscr.addstr(y, 22, stats.type)
            self.stdscr.addstr(y, 37, stats.status)
            
            # Show metrics summary
            metric_summary = ""
            if 'rx_bytes' in stats.metrics and stats.metrics['rx_bytes']:
                latest = stats.metrics['rx_bytes'][-1]
                metric_summary = f"RX: {self._format_bytes(latest.value)}"
            
            if 'tx_bytes' in stats.metrics and stats.metrics['tx_bytes']:
                latest = stats.metrics['tx_bytes'][-1]
                if metric_summary:
                    metric_summary += f" TX: {self._format_bytes(latest.value)}"
            
            self.stdscr.addstr(y, 47, metric_summary[:width - 50])
            
            self.stdscr.attroff(color)
            y += 1
    
    def _format_bytes(self, bytes_val: int) -> str:
        """Format bytes to human readable"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024.0
        return f"{bytes_val:.1f} PB"
    
    def _draw_footer(self):
        """Draw footer with controls"""
        height, width = self.stdscr.getmaxyx()
        
        self.stdscr.attron(curses.color_pair(7))
        self.stdscr.addstr(height - 1, 0, "=" * width)
        self.stdscr.addstr(height - 1, 2, "ESC: Exit  |  r: Refresh  |  q: Quit")
        self.stdscr.attroff(curses.color_pair(7))
    
    def _handle_input(self, key):
        """Handle keyboard input"""
        if key == 27:  # ESC
            self.running = False
        elif key == ord('q') or key == ord('Q'):
            self.running = False
        elif key == ord('r') or key == ord('R'):
            pass  # Refresh
        elif key == ord('1'):
            self.current_view = 'summary'
        elif key == ord('2'):
            self.current_view = 'devices'
        elif key == curses.KEY_UP:
            self.scroll_offset = max(0, self.scroll_offset - 1)
        elif key == curses.KEY_DOWN:
            self.scroll_offset += 1

# ==================== Web Dashboard ====================

class WebDashboard:
    """Web-based monitoring dashboard"""
    
    def __init__(self, collector: DataCollector, host: str = '0.0.0.0', port: int = 5000):
        self.collector = collector
        self.host = host
        self.port = port
        self.app = None
        self.running = False
    
    def start(self):
        """Start web dashboard"""
        if not FLASK_AVAILABLE:
            logger.error("Flask not installed. Install with: pip install flask")
            return
        
        self.app = Flask(__name__)
        self._setup_routes()
        
        logger.info(f"Starting web dashboard on http://{self.host}:{self.port}")
        self.running = True
        self.app.run(host=self.host, port=self.port, debug=False, threaded=True)
    
    def _setup_routes(self):
        """Setup Flask routes"""
        
        @self.app.route('/')
        def index():
            return render_template_string(HTML_TEMPLATE)
        
        @self.app.route('/api/summary')
        def api_summary():
            return jsonify(self.collector.get_summary())
        
        @self.app.route('/api/system')
        def api_system():
            metrics = self.collector.get_system_metrics(last_n=100)
            data = {
                'timestamps': [m.timestamp for m in metrics],
                'cpu': [m.cpu_percent for m in metrics],
                'memory': [m.memory_percent for m in metrics],
                'disk': [m.disk_usage for m in metrics],
                'temperature': [m.temperature for m in metrics]
            }
            return jsonify(data)
        
        @self.app.route('/api/devices')
        def api_devices():
            devices = self.collector.get_device_stats()
            data = {}
            for name, stats in devices.items():
                data[name] = {
                    'type': stats.type,
                    'status': stats.status,
                    'metrics': {
                        key: [(m.timestamp, m.value) for m in vals[-50:]]
                        for key, vals in stats.metrics.items()
                    }
                }
            return jsonify(data)

# HTML template for web dashboard
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Intel NUC Virtual Device Monitor</title>
    <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #1a1a2e;
            color: #eee;
            margin: 0;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        .header {
            background: linear-gradient(135deg, #16213e, #0f3460);
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        .header h1 {
            margin: 0;
            color: #e94560;
            font-weight: 300;
        }
        .header .subtitle {
            color: #8899aa;
            font-size: 14px;
            margin-top: 5px;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .card {
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            border-left: 4px solid #e94560;
        }
        .card .title {
            color: #8899aa;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 10px;
        }
        .card .value {
            font-size: 28px;
            font-weight: 300;
            color: #eee;
        }
        .card .unit {
            font-size: 14px;
            color: #8899aa;
            margin-left: 5px;
        }
        .chart-container {
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }
        .device-table {
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            overflow-x: auto;
        }
        .device-table table {
            width: 100%;
            border-collapse: collapse;
        }
        .device-table th {
            text-align: left;
            padding: 10px;
            color: #8899aa;
            font-weight: 300;
            border-bottom: 1px solid #2a3a5e;
        }
        .device-table td {
            padding: 10px;
            border-bottom: 1px solid #1a2a4e;
        }
        .status-running {
            color: #4caf50;
        }
        .status-stopped {
            color: #f44336;
        }
        .status-unknown {
            color: #ff9800;
        }
        .refresh-btn {
            background: #e94560;
            color: white;
            border: none;
            padding: 8px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            float: right;
        }
        .refresh-btn:hover {
            background: #c73652;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🖥️ Intel NUC Virtual Device Monitor</h1>
            <div class="subtitle">Real-time monitoring dashboard for virtual devices</div>
            <button class="refresh-btn" onclick="refreshData()">Refresh</button>
        </div>
        
        <div class="grid" id="system-grid">
            <!-- System stats will be inserted here -->
        </div>
        
        <div class="chart-container">
            <div id="system-chart" style="height: 300px;"></div>
        </div>
        
        <div class="device-table">
            <h3>Virtual Devices</h3>
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Type</th>
                        <th>Status</th>
                        <th>Metrics</th>
                    </tr>
                </thead>
                <tbody id="device-table-body">
                    <!-- Device rows will be inserted here -->
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
        var refreshInterval = 5000; // milliseconds
        var chartData = null;
        
        function refreshData() {
            // Get system summary
            $.getJSON('/api/summary', function(data) {
                updateSystemGrid(data);
            });
            
            // Get system metrics for chart
            $.getJSON('/api/system', function(data) {
                updateSystemChart(data);
            });
            
            // Get device list
            $.getJSON('/api/devices', function(data) {
                updateDeviceTable(data);
            });
        }
        
        function updateSystemGrid(data) {
            if (!data || !data.system) return;
            
            var sys = data.system;
            var grid = $('#system-grid');
            grid.empty();
            
            var items = [
                { label: 'CPU Usage', value: sys.cpu, unit: '%', color: '#4caf50' },
                { label: 'Memory Usage', value: sys.memory, unit: '%', color: '#2196f3' },
                { label: 'Disk Usage', value: sys.disk, unit: '%', color: '#ff9800' },
                { label: 'Temperature', value: sys.temperature || 0, unit: '°C', color: '#f44336' }
            ];
            
            items.forEach(function(item) {
                var card = $('<div class="card"></div>');
                card.css('border-left-color', item.color);
                card.html(`
                    <div class="title">${item.label}</div>
                    <div class="value">${item.value.toFixed(1)}<span class="unit">${item.unit}</span></div>
                `);
                grid.append(card);
            });
            
            // Device count
            var deviceCount = Object.keys(data.devices || {}).length;
            var card = $('<div class="card"></div>');
            card.css('border-left-color', '#9c27b0');
            card.html(`
                <div class="title">Devices</div>
                <div class="value">${deviceCount}<span class="unit">active</span></div>
            `);
            grid.append(card);
        }
        
        function updateSystemChart(data) {
            var trace1 = {
                x: data.timestamps.map(function(ts) { return new Date(ts * 1000); }),
                y: data.cpu,
                name: 'CPU',
                type: 'scatter',
                line: { color: '#4caf50' }
            };
            
            var trace2 = {
                x: data.timestamps.map(function(ts) { return new Date(ts * 1000); }),
                y: data.memory,
                name: 'Memory',
                type: 'scatter',
                line: { color: '#2196f3' }
            };
            
            var trace3 = {
                x: data.timestamps.map(function(ts) { return new Date(ts * 1000); }),
                y: data.disk,
                name: 'Disk',
                type: 'scatter',
                line: { color: '#ff9800' }
            };
            
            var layout = {
                title: 'System Resources',
                xaxis: { title: 'Time' },
                yaxis: { title: 'Usage (%)', range: [0, 100] },
                paper_bgcolor: 'rgba(0,0,0,0)',
                plot_bgcolor: 'rgba(0,0,0,0)',
                font: { color: '#eee' },
                legend: { orientation: 'h', y: 1.1 }
            };
            
            Plotly.newPlot('system-chart', [trace1, trace2, trace3], layout);
        }
        
        function updateDeviceTable(data) {
            var tbody = $('#device-table-body');
            tbody.empty();
            
            if (!data || Object.keys(data).length === 0) {
                tbody.html('<tr><td colspan="4">No devices found</td></tr>');
                return;
            }
            
            Object.keys(data).forEach(function(name) {
                var dev = data[name];
                var statusClass = 'status-' + (dev.status || 'unknown');
                
                // Get metrics summary
                var metrics = '';
                if (dev.metrics && dev.metrics.rx_bytes) {
                    var last = dev.metrics.rx_bytes[dev.metrics.rx_bytes.length - 1];
                    if (last) {
                        metrics += 'RX: ' + formatBytes(last[1]);
                    }
                }
                if (dev.metrics && dev.metrics.tx_bytes) {
                    var last = dev.metrics.tx_bytes[dev.metrics.tx_bytes.length - 1];
                    if (last) {
                        if (metrics) metrics += ' ';
                        metrics += 'TX: ' + formatBytes(last[1]);
                    }
                }
                
                var row = $('<tr></tr>');
                row.html(`
                    <td><strong>${name}</strong></td>
                    <td>${dev.type || 'unknown'}</td>
                    <td><span class="${statusClass}">${dev.status || 'unknown'}</span></td>
                    <td>${metrics}</td>
                `);
                tbody.append(row);
            });
        }
        
        function formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            var k = 1024;
            var sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
            var i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
        }
        
        // Initial load
        refreshData();
        
        // Auto-refresh
        setInterval(refreshData, refreshInterval);
    </script>
</body>
</html>
"""

# ==================== Command Line Interface ====================

class MonitoringCLI:
    """Command line interface for monitoring dashboard"""
    
    def __init__(self):
        self.collector = DataCollector()
        self.dashboard = None
        self.web_dashboard = None
    
    def run(self, args):
        """Run monitoring"""
        if args.command == 'terminal':
            self._run_terminal(args)
        elif args.command == 'web':
            self._run_web(args)
        elif args.command == 'dump':
            self._dump_data(args)
        else:
            print(f"Unknown command: {args.command}")
    
    def _run_terminal(self, args):
        """Run terminal dashboard"""
        self.collector.start(args.interval)
        dashboard = TerminalDashboard(self.collector)
        try:
            dashboard.start()
        finally:
            self.collector.stop()
    
    def _run_web(self, args):
        """Run web dashboard"""
        self.collector.start(args.interval)
        web = WebDashboard(self.collector, args.host, args.port)
        try:
            web.start()
        finally:
            self.collector.stop()
    
    def _dump_data(self, args):
        """Dump data to file"""
        self.collector.start(args.interval)
        time.sleep(args.duration)
        self.collector.stop()
        
        data = {
            'system': self.collector.get_system_metrics(),
            'devices': self.collector.get_device_stats()
        }
        
        with open(args.output, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.info(f"Data dumped to {args.output}")

def create_parser():
    """Create argument parser"""
    parser = argparse.ArgumentParser(
        description="Monitoring Dashboard for Virtual Devices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run terminal dashboard
  monitoring-dashboard.py terminal

  # Run web dashboard
  monitoring-dashboard.py web --port 8080

  # Dump data to file
  monitoring-dashboard.py dump --output data.json --duration 60
        """
    )
    
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose output')
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Terminal dashboard
    terminal_parser = subparsers.add_parser('terminal', help='Run terminal dashboard')
    terminal_parser.add_argument('-i', '--interval', type=int, default=DEFAULT_INTERVAL,
                                help=f'Update interval in seconds (default: {DEFAULT_INTERVAL})')
    
    # Web dashboard
    web_parser = subparsers.add_parser('web', help='Run web dashboard')
    web_parser.add_argument('-H', '--host', default='0.0.0.0',
                           help='Host to bind to (default: 0.0.0.0)')
    web_parser.add_argument('-p', '--port', type=int, default=5000,
                           help='Port to bind to (default: 5000)')
    web_parser.add_argument('-i', '--interval', type=int, default=DEFAULT_INTERVAL,
                           help=f'Update interval in seconds (default: {DEFAULT_INTERVAL})')
    
    # Dump command
    dump_parser = subparsers.add_parser('dump', help='Dump data to file')
    dump_parser.add_argument('-o', '--output', default='monitoring_data.json',
                            help='Output file (default: monitoring_data.json)')
    dump_parser.add_argument('-i', '--interval', type=int, default=DEFAULT_INTERVAL,
                            help=f'Update interval in seconds (default: {DEFAULT_INTERVAL})')
    dump_parser.add_argument('-d', '--duration', type=int, default=60,
                            help='Duration in seconds (default: 60)')
    
    return parser

def main():
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if not args.command:
        parser.print_help()
        return
    
    cli = MonitoringCLI()
    try:
        cli.run(args)
    except KeyboardInterrupt:
        print(f"\n{COLORS['YELLOW']}Monitoring stopped{COLORS['RESET']}")
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
