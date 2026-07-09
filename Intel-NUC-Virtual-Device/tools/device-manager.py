#!/usr/bin/env python3
"""
device-manager.py - Virtual Device Manager for Intel NUC

This tool provides comprehensive management of virtual devices including
creation, deletion, monitoring, and configuration of all virtual device types.

Version: 1.0.0
Author: Intel NUC Virtual Device Platform Team
License: GPL v2
"""

import os
import sys
import json
import time
import yaml
import logging
import subprocess
import argparse
import threading
import signal
import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import queue
import shutil
import tempfile

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
    'CYAN': '\033[36m'
}

# Configuration
CONFIG_DIR = "/etc/virtual-devices"
STATE_FILE = f"{CONFIG_DIR}/state.json"
LOG_DIR = "/var/log/virtual-devices"
DEVICE_BASE = "/dev"
SYSFS_BASE = "/sys"

# Create directories if they don't exist
os.makedirs(CONFIG_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# ==================== Data Classes ====================

class DeviceType(Enum):
    """Virtual device types"""
    NETWORK = "network"
    USB = "usb"
    SERIAL = "serial"
    DISK = "disk"
    CAMERA = "camera"
    AUDIO = "audio"

class DeviceStatus(Enum):
    """Device status"""
    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    DELETED = "deleted"

@dataclass
class DeviceConfig:
    """Device configuration"""
    name: str
    type: DeviceType
    status: DeviceStatus
    created: str
    path: Optional[str] = None
    options: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class DeviceStats:
    """Device statistics"""
    device_name: str
    type: str
    status: str
    uptime: float
    rx_bytes: int = 0
    tx_bytes: int = 0
    rx_packets: int = 0
    tx_packets: int = 0
    errors: int = 0
    drops: int = 0

# ==================== Base Device Manager ====================

class DeviceManager:
    """Base device manager class"""
    
    def __init__(self):
        self.devices: Dict[str, DeviceConfig] = {}
        self.stats: Dict[str, DeviceStats] = {}
        self.lock = threading.Lock()
        self.running = False
        self.monitor_thread = None
        self.event_queue = queue.Queue()
        
        # Load state
        self._load_state()
        
        # Start monitor
        self._start_monitor()
    
    def _load_state(self):
        """Load device state from file"""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    data = json.load(f)
                    for name, info in data.items():
                        info['type'] = DeviceType(info['type'])
                        info['status'] = DeviceStatus(info['status'])
                        self.devices[name] = DeviceConfig(**info)
                logger.info(f"Loaded {len(self.devices)} devices from state file")
            except Exception as e:
                logger.error(f"Failed to load state: {e}")
    
    def _save_state(self):
        """Save device state to file"""
        try:
            data = {}
            for name, dev in self.devices.items():
                data[name] = asdict(dev)
                data[name]['type'] = dev.type.value
                data[name]['status'] = dev.status.value
            
            with open(STATE_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
    
    def _start_monitor(self):
        """Start device monitoring thread"""
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        logger.info("Device monitor started")
    
    def _monitor_loop(self):
        """Monitor device status"""
        while self.running:
            try:
                with self.lock:
                    for name, dev in self.devices.items():
                        self._update_stats(name, dev)
                time.sleep(5)
            except Exception as e:
                logger.error(f"Monitor error: {e}")
    
    def _update_stats(self, name: str, dev: DeviceConfig):
        """Update device statistics"""
        # Override in subclasses
        pass
    
    def create_device(self, dev_type: DeviceType, name: str, 
                     options: Dict = None) -> bool:
        """Create a virtual device"""
        with self.lock:
            if name in self.devices:
                logger.error(f"Device {name} already exists")
                return False
            
            dev = DeviceConfig(
                name=name,
                type=dev_type,
                status=DeviceStatus.CREATED,
                created=datetime.now().isoformat(),
                options=options or {}
            )
            
            self.devices[name] = dev
            self._save_state()
            
            logger.info(f"Device {name} created ({dev_type.value})")
            return True
    
    def delete_device(self, name: str) -> bool:
        """Delete a virtual device"""
        with self.lock:
            if name not in self.devices:
                logger.error(f"Device {name} not found")
                return False
            
            dev = self.devices[name]
            dev.status = DeviceStatus.DELETED
            del self.devices[name]
            self._save_state()
            
            logger.info(f"Device {name} deleted")
            return True
    
    def get_device(self, name: str) -> Optional[DeviceConfig]:
        """Get device configuration"""
        return self.devices.get(name)
    
    def list_devices(self) -> List[DeviceConfig]:
        """List all devices"""
        return list(self.devices.values())
    
    def get_stats(self, name: str) -> Optional[DeviceStats]:
        """Get device statistics"""
        return self.stats.get(name)
    
    def stop(self):
        """Stop device manager"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        logger.info("Device manager stopped")

# ==================== Network Device Manager ====================

class NetworkDeviceManager(DeviceManager):
    """Network device manager"""
    
    def create_veth(self, name: str, peer: str, ips: List[str] = None) -> bool:
        """Create veth pair"""
        logger.info(f"Creating veth pair: {name} <-> {peer}")
        
        try:
            # Create veth
            cmd = f"ip link add {name} type veth peer name {peer}"
            subprocess.run(cmd, shell=True, check=True)
            
            # Bring up interfaces
            subprocess.run(f"ip link set {name} up", shell=True, check=True)
            subprocess.run(f"ip link set {peer} up", shell=True, check=True)
            
            # Assign IPs
            if ips:
                for i, ip in enumerate(ips):
                    dev = name if i == 0 else peer
                    subprocess.run(f"ip addr add {ip} dev {dev}", shell=True, check=True)
            
            # Create device config
            options = {'peer': peer, 'ips': ips or []}
            self.create_device(DeviceType.NETWORK, name, options)
            
            # Create peer device config
            peer_options = {'peer': name, 'ips': ips and [ips[1]] if len(ips) > 1 else []}
            self.create_device(DeviceType.NETWORK, peer, peer_options)
            
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create veth: {e}")
            return False
    
    def create_bridge(self, name: str, interfaces: List[str] = None) -> bool:
        """Create bridge interface"""
        logger.info(f"Creating bridge: {name}")
        
        try:
            # Create bridge
            subprocess.run(f"ip link add {name} type bridge", shell=True, check=True)
            subprocess.run(f"ip link set {name} up", shell=True, check=True)
            
            # Add interfaces
            if interfaces:
                for iface in interfaces:
                    subprocess.run(f"brctl addif {name} {iface}", shell=True, check=True)
                    subprocess.run(f"ip link set {iface} up", shell=True, check=True)
            
            options = {'interfaces': interfaces or []}
            return self.create_device(DeviceType.NETWORK, name, options)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create bridge: {e}")
            return False
    
    def create_tap(self, name: str, user: str = None) -> bool:
        """Create TAP interface"""
        logger.info(f"Creating TAP: {name}")
        
        try:
            cmd = f"ip tuntap add {name} mode tap"
            if user:
                cmd += f" user {user}"
            subprocess.run(cmd, shell=True, check=True)
            subprocess.run(f"ip link set {name} up", shell=True, check=True)
            
            options = {'user': user}
            return self.create_device(DeviceType.NETWORK, name, options)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create TAP: {e}")
            return False
    
    def create_vlan(self, name: str, parent: str, vlan_id: int) -> bool:
        """Create VLAN interface"""
        logger.info(f"Creating VLAN: {name} (parent: {parent}, VLAN: {vlan_id})")
        
        try:
            cmd = f"ip link add link {parent} name {name} type vlan id {vlan_id}"
            subprocess.run(cmd, shell=True, check=True)
            subprocess.run(f"ip link set {name} up", shell=True, check=True)
            
            options = {'parent': parent, 'vlan_id': vlan_id}
            return self.create_device(DeviceType.NETWORK, name, options)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create VLAN: {e}")
            return False
    
    def create_macvlan(self, name: str, parent: str, mode: str = 'bridge') -> bool:
        """Create MACVLAN interface"""
        logger.info(f"Creating MACVLAN: {name} (parent: {parent}, mode: {mode})")
        
        try:
            cmd = f"ip link add {name} link {parent} type macvlan mode {mode}"
            subprocess.run(cmd, shell=True, check=True)
            subprocess.run(f"ip link set {name} up", shell=True, check=True)
            
            options = {'parent': parent, 'mode': mode}
            return self.create_device(DeviceType.NETWORK, name, options)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create MACVLAN: {e}")
            return False
    
    def create_bond(self, name: str, interfaces: List[str], mode: str = 'active-backup') -> bool:
        """Create bonding interface"""
        logger.info(f"Creating bond: {name} (interfaces: {interfaces}, mode: {mode})")
        
        try:
            # Load bonding module
            subprocess.run("modprobe bonding", shell=True, check=True)
            
            # Create bond
            subprocess.run(f"ip link add {name} type bond mode {mode} miimon 100", 
                          shell=True, check=True)
            subprocess.run(f"ip link set {name} up", shell=True, check=True)
            
            # Add interfaces
            for iface in interfaces:
                subprocess.run(f"ip link set {iface} down", shell=True, check=True)
                subprocess.run(f"ip link set {iface} master {name}", shell=True, check=True)
                subprocess.run(f"ip link set {iface} up", shell=True, check=True)
            
            options = {'interfaces': interfaces, 'mode': mode}
            return self.create_device(DeviceType.NETWORK, name, options)
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create bond: {e}")
            return False
    
    def _update_stats(self, name: str, dev: DeviceConfig):
        """Update network device statistics"""
        if dev.type != DeviceType.NETWORK:
            return
        
        try:
            # Get stats from /sys/class/net
            base_path = f"/sys/class/net/{name}/statistics"
            
            stats = DeviceStats(
                device_name=name,
                type='network',
                status=dev.status.value,
                uptime=time.time() - os.path.getctime(f"/sys/class/net/{name}")
            )
            
            for stat_file in ['rx_bytes', 'tx_bytes', 'rx_packets', 'tx_packets', 
                             'rx_errors', 'tx_errors', 'rx_dropped', 'tx_dropped']:
                path = f"{base_path}/{stat_file}"
                if os.path.exists(path):
                    with open(path, 'r') as f:
                        value = int(f.read().strip())
                        setattr(stats, stat_file.replace('-', '_'), value)
            
            self.stats[name] = stats
            
        except Exception as e:
            pass
    
    def delete_network_device(self, name: str) -> bool:
        """Delete network device"""
        dev = self.get_device(name)
        if not dev or dev.type != DeviceType.NETWORK:
            return False
        
        try:
            subprocess.run(f"ip link delete {name}", shell=True, check=True)
            return self.delete_device(name)
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to delete network device: {e}")
            return False

# ==================== USB Device Manager ====================

class USBDeviceManager(DeviceManager):
    """USB device manager"""
    
    def __init__(self):
        super().__init__()
        self.configfs_base = "/sys/kernel/config/usb_gadget"
        self._check_configfs()
    
    def _check_configfs(self):
        """Check if configfs is available"""
        if not os.path.exists(self.configfs_base):
            logger.warning("ConfigFS not mounted. Trying to mount...")
            try:
                subprocess.run("mount -t configfs none /sys/kernel/config", 
                             shell=True, check=True)
            except:
                logger.error("Failed to mount configfs")
    
    def create_gadget(self, name: str, vendor_id: int, product_id: int,
                     manufacturer: str = "Intel NUC",
                     product: str = "Virtual USB Gadget",
                     serial: str = None) -> bool:
        """Create USB gadget"""
        logger.info(f"Creating USB gadget: {name}")
        
        if not serial:
            serial = f"{name}-{int(time.time())}"
        
        gadget_path = f"{self.configfs_base}/{name}"
        
        try:
            # Create gadget directory
            os.makedirs(gadget_path, exist_ok=True)
            
            # Set IDs
            with open(f"{gadget_path}/idVendor", 'w') as f:
                f.write(f"0x{vendor_id:04x}")
            with open(f"{gadget_path}/idProduct", 'w') as f:
                f.write(f"0x{product_id:04x}")
            
            # Set strings
            strings_path = f"{gadget_path}/strings/0x409"
            os.makedirs(strings_path, exist_ok=True)
            
            with open(f"{strings_path}/serialnumber", 'w') as f:
                f.write(serial)
            with open(f"{strings_path}/manufacturer", 'w') as f:
                f.write(manufacturer)
            with open(f"{strings_path}/product", 'w') as f:
                f.write(product)
            
            options = {
                'vendor_id': vendor_id,
                'product_id': product_id,
                'manufacturer': manufacturer,
                'product': product,
                'serial': serial
            }
            
            return self.create_device(DeviceType.USB, name, options)
            
        except Exception as e:
            logger.error(f"Failed to create USB gadget: {e}")
            return False
    
    def add_gadget_function(self, gadget_name: str, function_type: str) -> bool:
        """Add function to USB gadget"""
        logger.info(f"Adding function {function_type} to {gadget_name}")
        
        gadget_path = f"{self.configfs_base}/{gadget_name}"
        func_path = f"{gadget_path}/functions/{function_type}.usb0"
        
        try:
            os.makedirs(func_path, exist_ok=True)
            
            # Update device config
            dev = self.get_device(gadget_name)
            if dev and dev.type == DeviceType.USB:
                if 'functions' not in dev.options:
                    dev.options['functions'] = []
                dev.options['functions'].append(function_type)
                self._save_state()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to add function: {e}")
            return False
    
    def add_gadget_config(self, gadget_name: str, config_name: str = 'c.1') -> bool:
        """Add configuration to USB gadget"""
        logger.info(f"Adding config {config_name} to {gadget_name}")
        
        gadget_path = f"{self.configfs_base}/{gadget_name}"
        config_path = f"{gadget_path}/configs/{config_name}"
        
        try:
            os.makedirs(config_path, exist_ok=True)
            
            # Set MaxPower
            with open(f"{config_path}/MaxPower", 'w') as f:
                f.write("500")
            
            # Add strings
            strings_path = f"{config_path}/strings/0x409"
            os.makedirs(strings_path, exist_ok=True)
            with open(f"{strings_path}/configuration", 'w') as f:
                f.write(f"Config for {gadget_name}")
            
            # Link functions
            func_path = f"{gadget_path}/functions"
            if os.path.exists(func_path):
                for func in os.listdir(func_path):
                    if func.endswith('.usb0'):
                        src = f"{func_path}/{func}"
                        dst = f"{config_path}/{func}"
                        os.symlink(src, dst)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to add config: {e}")
            return False
    
    def enable_gadget(self, name: str) -> bool:
        """Enable USB gadget"""
        logger.info(f"Enabling USB gadget: {name}")
        
        gadget_path = f"{self.configfs_base}/{name}"
        
        try:
            # Find UDC
            udc_path = "/sys/class/udc"
            if not os.path.exists(udc_path):
                logger.error("No UDC found")
                return False
            
            udcs = os.listdir(udc_path)
            if not udcs:
                logger.error("No UDC available")
                return False
            
            udc = udcs[0]
            with open(f"{gadget_path}/UDC", 'w') as f:
                f.write(udc)
            
            # Update status
            dev = self.get_device(name)
            if dev:
                dev.status = DeviceStatus.RUNNING
                self._save_state()
            
            logger.info(f"Gadget {name} enabled on {udc}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to enable gadget: {e}")
            return False
    
    def disable_gadget(self, name: str) -> bool:
        """Disable USB gadget"""
        logger.info(f"Disabling USB gadget: {name}")
        
        gadget_path = f"{self.configfs_base}/{name}"
        
        try:
            with open(f"{gadget_path}/UDC", 'w') as f:
                f.write("")
            
            # Update status
            dev = self.get_device(name)
            if dev:
                dev.status = DeviceStatus.STOPPED
                self._save_state()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to disable gadget: {e}")
            return False
    
    def delete_gadget(self, name: str) -> bool:
        """Delete USB gadget"""
        logger.info(f"Deleting USB gadget: {name}")
        
        # Disable first
        self.disable_gadget(name)
        
        gadget_path = f"{self.configfs_base}/{name}"
        
        try:
            # Remove config links
            config_path = f"{gadget_path}/configs"
            if os.path.exists(config_path):
                for config in os.listdir(config_path):
                    config_dir = f"{config_path}/{config}"
                    if os.path.isdir(config_dir):
                        for func in os.listdir(config_dir):
                            if func.endswith('.usb0'):
                                os.unlink(f"{config_dir}/{func}")
            
            # Remove configs
            for config in os.listdir(config_path):
                shutil.rmtree(f"{config_path}/{config}")
            
            # Remove functions
            func_path = f"{gadget_path}/functions"
            if os.path.exists(func_path):
                for func in os.listdir(func_path):
                    shutil.rmtree(f"{func_path}/{func}")
            
            # Remove strings
            strings_path = f"{gadget_path}/strings"
            if os.path.exists(strings_path):
                for lang in os.listdir(strings_path):
                    shutil.rmtree(f"{strings_path}/{lang}")
            
            # Remove gadget
            shutil.rmtree(gadget_path)
            
            return self.delete_device(name)
            
        except Exception as e:
            logger.error(f"Failed to delete gadget: {e}")
            return False

# ==================== Serial Device Manager ====================

class SerialDeviceManager(DeviceManager):
    """Serial device manager"""
    
    def create_pty_pair(self, name: str, peer: str = None) -> bool:
        """Create PTY pair"""
        logger.info(f"Creating PTY pair: {name} <-> {peer or f'{name}-peer'}")
        
        if not peer:
            peer = f"{name}-peer"
        
        try:
            # Create PTY pair with socat
            cmd = f"socat -d -d PTY,link=/dev/{name},raw,echo=0 PTY,link=/dev/{peer},raw,echo=0 &"
            subprocess.Popen(cmd, shell=True)
            time.sleep(1)
            
            options = {'peer': peer}
            self.create_device(DeviceType.SERIAL, name, options)
            
            peer_options = {'peer': name}
            self.create_device(DeviceType.SERIAL, peer, peer_options)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create PTY pair: {e}")
            return False
    
    def create_serial_bridge(self, name: str, port1: str, port2: str) -> bool:
        """Create serial bridge between two ports"""
        logger.info(f"Creating serial bridge: {name} ({port1} <-> {port2})")
        
        try:
            cmd = f"socat -d -d PTY,link=/dev/{port1},raw,echo=0 PTY,link=/dev/{port2},raw,echo=0 &"
            subprocess.Popen(cmd, shell=True)
            time.sleep(1)
            
            options = {'port1': port1, 'port2': port2}
            return self.create_device(DeviceType.SERIAL, name, options)
            
        except Exception as e:
            logger.error(f"Failed to create serial bridge: {e}")
            return False
    
    def create_tcp_bridge(self, name: str, port: int, serial_port: str) -> bool:
        """Create TCP to serial bridge"""
        logger.info(f"Creating TCP bridge: {name} (port {port} <-> {serial_port})")
        
        try:
            cmd = f"socat TCP-LISTEN:{port},reuseaddr,fork PTY,link=/dev/{serial_port},raw,echo=0 &"
            subprocess.Popen(cmd, shell=True)
            time.sleep(1)
            
            options = {'port': port, 'serial_port': serial_port}
            return self.create_device(DeviceType.SERIAL, name, options)
            
        except Exception as e:
            logger.error(f"Failed to create TCP bridge: {e}")
            return False

# ==================== Disk Device Manager ====================

class DiskDeviceManager(DeviceManager):
    """Disk device manager"""
    
    def __init__(self):
        super().__init__()
        self.image_dir = "/opt/virtual-devices/images"
        os.makedirs(self.image_dir, exist_ok=True)
    
    def create_loop_device(self, name: str, size_mb: int, 
                          fs_type: str = 'ext4') -> bool:
        """Create loop device with disk image"""
        logger.info(f"Creating loop device: {name} ({size_mb}MB)")
        
        image_path = f"{self.image_dir}/{name}.img"
        
        try:
            # Create image
            subprocess.run(f"dd if=/dev/zero of={image_path} bs=1M count={size_mb}", 
                          shell=True, check=True)
            
            # Setup loop device
            result = subprocess.run(f"losetup -f --show {image_path}", 
                                  shell=True, capture_output=True, text=True)
            loop_dev = result.stdout.strip()
            
            # Format
            subprocess.run(f"mkfs.{fs_type} {loop_dev} -F", 
                          shell=True, check=True)
            
            # Create mount point
            mount_point = f"/mnt/{name}"
            os.makedirs(mount_point, exist_ok=True)
            
            options = {
                'image_path': image_path,
                'loop_dev': loop_dev,
                'size_mb': size_mb,
                'fs_type': fs_type,
                'mount_point': mount_point
            }
            
            return self.create_device(DeviceType.DISK, name, options)
            
        except Exception as e:
            logger.error(f"Failed to create loop device: {e}")
            return False
    
    def mount_disk(self, name: str) -> bool:
        """Mount disk device"""
        dev = self.get_device(name)
        if not dev or dev.type != DeviceType.DISK:
            return False
        
        try:
            mount_point = dev.options.get('mount_point')
            loop_dev = dev.options.get('loop_dev')
            
            if not mount_point or not loop_dev:
                logger.error("Missing mount point or loop device")
                return False
            
            os.makedirs(mount_point, exist_ok=True)
            subprocess.run(f"mount {loop_dev} {mount_point}", shell=True, check=True)
            
            dev.status = DeviceStatus.RUNNING
            self._save_state()
            
            logger.info(f"Disk {name} mounted at {mount_point}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to mount disk: {e}")
            return False
    
    def unmount_disk(self, name: str) -> bool:
        """Unmount disk device"""
        dev = self.get_device(name)
        if not dev or dev.type != DeviceType.DISK:
            return False
        
        try:
            mount_point = dev.options.get('mount_point')
            if not mount_point:
                return False
            
            subprocess.run(f"umount {mount_point}", shell=True, check=True)
            
            dev.status = DeviceStatus.STOPPED
            self._save_state()
            
            logger.info(f"Disk {name} unmounted")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unmount disk: {e}")
            return False
    
    def delete_disk(self, name: str) -> bool:
        """Delete disk device"""
        dev = self.get_device(name)
        if not dev or dev.type != DeviceType.DISK:
            return False
        
        try:
            # Unmount if mounted
            if dev.status == DeviceStatus.RUNNING:
                self.unmount_disk(name)
            
            # Detach loop device
            loop_dev = dev.options.get('loop_dev')
            if loop_dev:
                subprocess.run(f"losetup -d {loop_dev}", shell=True, check=True)
            
            # Remove image
            image_path = dev.options.get('image_path')
            if image_path and os.path.exists(image_path):
                os.remove(image_path)
            
            # Remove mount point
            mount_point = dev.options.get('mount_point')
            if mount_point and os.path.exists(mount_point):
                os.rmdir(mount_point)
            
            return self.delete_device(name)
            
        except Exception as e:
            logger.error(f"Failed to delete disk: {e}")
            return False

# ==================== Camera Device Manager ====================

class CameraDeviceManager(DeviceManager):
    """Camera device manager"""
    
    def __init__(self):
        super().__init__()
        self._load_v4l2_modules()
    
    def _load_v4l2_modules(self):
        """Load V4L2 modules"""
        try:
            subprocess.run("modprobe v4l2loopback", shell=True, check=True)
            logger.info("V4L2 loopback module loaded")
        except:
            logger.warning("Failed to load v4l2loopback module")
    
    def create_camera(self, name: str, width: int = 1920, height: int = 1080,
                     fps: int = 30, format: str = 'YUYV') -> bool:
        """Create virtual camera device"""
        logger.info(f"Creating camera: {name} ({width}x{height} @ {fps}fps)")
        
        try:
            # Use v4l2loopback to create device
            cmd = f"modprobe v4l2loopback devices=1 video_nr=2 card_label={name} exclusive_caps=1"
            subprocess.run(cmd, shell=True, check=True)
            
            options = {
                'width': width,
                'height': height,
                'fps': fps,
                'format': format,
                'device': f"/dev/video2"
            }
            
            return self.create_device(DeviceType.CAMERA, name, options)
            
        except Exception as e:
            logger.error(f"Failed to create camera: {e}")
            return False
    
    def start_stream(self, name: str) -> bool:
        """Start camera stream"""
        dev = self.get_device(name)
        if not dev or dev.type != DeviceType.CAMERA:
            return False
        
        try:
            # Start frame generator
            cmd = f"modprobe frame-generator fg_width={dev.options['width']} " \
                  f"fg_height={dev.options['height']} fg_fps={dev.options['fps']}"
            subprocess.run(cmd, shell=True, check=True)
            
            dev.status = DeviceStatus.RUNNING
            self._save_state()
            
            logger.info(f"Camera {name} stream started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start camera stream: {e}")
            return False
    
    def stop_stream(self, name: str) -> bool:
        """Stop camera stream"""
        dev = self.get_device(name)
        if not dev or dev.type != DeviceType.CAMERA:
            return False
        
        try:
            subprocess.run("rmmod frame-generator", shell=True, check=True)
            
            dev.status = DeviceStatus.STOPPED
            self._save_state()
            
            logger.info(f"Camera {name} stream stopped")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop camera stream: {e}")
            return False

# ==================== Audio Device Manager ====================

class AudioDeviceManager(DeviceManager):
    """Audio device manager"""
    
    def create_virtual_mic(self, name: str, description: str = None) -> bool:
        """Create virtual microphone"""
        logger.info(f"Creating virtual microphone: {name}")
        
        try:
            if not description:
                description = f"Virtual Microphone {name}"
            
            cmd = f"pactl load-module module-null-source source_name={name} " \
                  f"source_properties=device.description='{description}'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                options = {'description': description}
                return self.create_device(DeviceType.AUDIO, name, options)
            else:
                logger.error(f"Failed to create virtual mic: {result.stderr}")
                return False
            
        except Exception as e:
            logger.error(f"Failed to create virtual mic: {e}")
            return False
    
    def create_virtual_speaker(self, name: str, description: str = None) -> bool:
        """Create virtual speaker"""
        logger.info(f"Creating virtual speaker: {name}")
        
        try:
            if not description:
                description = f"Virtual Speaker {name}"
            
            cmd = f"pactl load-module module-null-sink sink_name={name} " \
                  f"sink_properties=device.description='{description}'"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                options = {'description': description}
                return self.create_device(DeviceType.AUDIO, name, options)
            else:
                logger.error(f"Failed to create virtual speaker: {result.stderr}")
                return False
            
        except Exception as e:
            logger.error(f"Failed to create virtual speaker: {e}")
            return False
    
    def create_loopback(self, source: str, sink: str, name: str = None) -> bool:
        """Create audio loopback"""
        if not name:
            name = f"loopback_{source}_{sink}"
        
        logger.info(f"Creating audio loopback: {source} -> {sink}")
        
        try:
            cmd = f"pactl load-module module-loopback source={source} sink={sink}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                options = {'source': source, 'sink': sink}
                return self.create_device(DeviceType.AUDIO, name, options)
            else:
                logger.error(f"Failed to create loopback: {result.stderr}")
                return False
            
        except Exception as e:
            logger.error(f"Failed to create loopback: {e}")
            return False

# ==================== Main CLI ====================

class DeviceManagerCLI:
    """Command line interface for device manager"""
    
    def __init__(self):
        self.network_mgr = NetworkDeviceManager()
        self.usb_mgr = USBDeviceManager()
        self.serial_mgr = SerialDeviceManager()
        self.disk_mgr = DiskDeviceManager()
        self.camera_mgr = CameraDeviceManager()
        self.audio_mgr = AudioDeviceManager()
        
        # Register signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, sig, frame):
        print(f"\n{COLORS['YELLOW']}Shutting down...{COLORS['RESET']}")
        sys.exit(0)
    
    def run(self, args):
        """Run command"""
        if args.command == 'create':
            self._create_device(args)
        elif args.command == 'delete':
            self._delete_device(args)
        elif args.command == 'list':
            self._list_devices(args)
        elif args.command == 'status':
            self._show_status(args)
        elif args.command == 'start':
            self._start_device(args)
        elif args.command == 'stop':
            self._stop_device(args)
        elif args.command == 'info':
            self._show_info(args)
        elif args.command == 'monitor':
            self._monitor_devices(args)
        else:
            print(f"Unknown command: {args.command}")
    
    def _create_device(self, args):
        """Create device"""
        if args.type == 'veth':
            ips = args.ips.split(',') if args.ips else []
            self.network_mgr.create_veth(args.name, args.peer or f"{args.name}-peer", ips)
        elif args.type == 'bridge':
            interfaces = args.interfaces.split(',') if args.interfaces else []
            self.network_mgr.create_bridge(args.name, interfaces)
        elif args.type == 'tap':
            self.network_mgr.create_tap(args.name, args.user)
        elif args.type == 'vlan':
            self.network_mgr.create_vlan(args.name, args.parent, args.vlan_id)
        elif args.type == 'macvlan':
            self.network_mgr.create_macvlan(args.name, args.parent, args.mode)
        elif args.type == 'bond':
            interfaces = args.interfaces.split(',')
            self.network_mgr.create_bond(args.name, interfaces, args.mode)
        elif args.type == 'usb-gadget':
            self.usb_mgr.create_gadget(args.name, args.vendor, args.product,
                                       args.manufacturer, args.product_name, args.serial)
        elif args.type == 'pty':
            self.serial_mgr.create_pty_pair(args.name, args.peer)
        elif args.type == 'serial-bridge':
            self.serial_mgr.create_serial_bridge(args.name, args.port1, args.port2)
        elif args.type == 'tcp-bridge':
            self.serial_mgr.create_tcp_bridge(args.name, args.port, args.serial_port)
        elif args.type == 'disk':
            self.disk_mgr.create_loop_device(args.name, args.size, args.fs_type)
        elif args.type == 'camera':
            self.camera_mgr.create_camera(args.name, args.width, args.height, args.fps, args.format)
        elif args.type == 'audio-mic':
            self.audio_mgr.create_virtual_mic(args.name, args.description)
        elif args.type == 'audio-speaker':
            self.audio_mgr.create_virtual_speaker(args.name, args.description)
        elif args.type == 'audio-loopback':
            self.audio_mgr.create_loopback(args.source, args.sink, args.name)
        else:
            print(f"Unknown device type: {args.type}")
    
    def _delete_device(self, args):
        """Delete device"""
        # Try each manager
        if self.network_mgr.delete_network_device(args.name):
            return
        if self.usb_mgr.delete_gadget(args.name):
            return
        if self.disk_mgr.delete_disk(args.name):
            return
        if self.serial_mgr.delete_device(args.name):
            return
        if self.camera_mgr.delete_device(args.name):
            return
        if self.audio_mgr.delete_device(args.name):
            return
        
        print(f"Device {args.name} not found or could not be deleted")
    
    def _list_devices(self, args):
        """List devices"""
        devices = []
        devices.extend(self.network_mgr.list_devices())
        devices.extend(self.usb_mgr.list_devices())
        devices.extend(self.serial_mgr.list_devices())
        devices.extend(self.disk_mgr.list_devices())
        devices.extend(self.camera_mgr.list_devices())
        devices.extend(self.audio_mgr.list_devices())
        
        if not devices:
            print("No devices found")
            return
        
        print(f"\n{COLORS['CYAN']}{'Name':<20} {'Type':<12} {'Status':<12} {'Path':<20}{COLORS['RESET']}")
        print("-" * 70)
        
        for dev in devices:
            color = COLORS['GREEN'] if dev.status == DeviceStatus.RUNNING else COLORS['YELLOW']
            print(f"{dev.name:<20} {dev.type.value:<12} "
                  f"{color}{dev.status.value}{COLORS['RESET']:<12} "
                  f"{dev.path or '':<20}")
    
    def _show_status(self, args):
        """Show device status"""
        # Show all status
        self._list_devices(args)
        
        # Show statistics for running devices
        print(f"\n{COLORS['CYAN']}Statistics:{COLORS['RESET']}")
        print("-" * 70)
        
        for mgr in [self.network_mgr, self.disk_mgr]:
            for name, stats in mgr.stats.items():
                if stats.status == 'running':
                    print(f"{COLORS['GREEN']}{name}{COLORS['RESET']}:")
                    print(f"  Uptime: {stats.uptime:.0f}s")
                    if hasattr(stats, 'rx_bytes'):
                        print(f"  RX: {stats.rx_bytes:,} bytes")
                        print(f"  TX: {stats.tx_bytes:,} bytes")
                    print()
    
    def _start_device(self, args):
        """Start device"""
        # Check device type and start
        dev = self.network_mgr.get_device(args.name)
        if dev:
            print(f"Device {args.name} is a network device. Use 'ip link set {args.name} up'")
            return
        
        dev = self.usb_mgr.get_device(args.name)
        if dev:
            self.usb_mgr.enable_gadget(args.name)
            return
        
        dev = self.disk_mgr.get_device(args.name)
        if dev:
            self.disk_mgr.mount_disk(args.name)
            return
        
        dev = self.camera_mgr.get_device(args.name)
        if dev:
            self.camera_mgr.start_stream(args.name)
            return
        
        print(f"Device {args.name} not found or cannot be started")
    
    def _stop_device(self, args):
        """Stop device"""
        dev = self.usb_mgr.get_device(args.name)
        if dev:
            self.usb_mgr.disable_gadget(args.name)
            return
        
        dev = self.disk_mgr.get_device(args.name)
        if dev:
            self.disk_mgr.unmount_disk(args.name)
            return
        
        dev = self.camera_mgr.get_device(args.name)
        if dev:
            self.camera_mgr.stop_stream(args.name)
            return
        
        print(f"Device {args.name} not found or cannot be stopped")
    
    def _show_info(self, args):
        """Show device info"""
        dev = None
        for mgr in [self.network_mgr, self.usb_mgr, self.serial_mgr, 
                   self.disk_mgr, self.camera_mgr, self.audio_mgr]:
            dev = mgr.get_device(args.name)
            if dev:
                break
        
        if not dev:
            print(f"Device {args.name} not found")
            return
        
        print(f"\n{COLORS['CYAN']}Device Information:{COLORS['RESET']}")
        print(f"  Name: {dev.name}")
        print(f"  Type: {dev.type.value}")
        print(f"  Status: {dev.status.value}")
        print(f"  Created: {dev.created}")
        print(f"  Path: {dev.path or 'N/A'}")
        if dev.options:
            print(f"  Options:")
            for key, value in dev.options.items():
                print(f"    {key}: {value}")
        if dev.metadata:
            print(f"  Metadata:")
            for key, value in dev.metadata.items():
                print(f"    {key}: {value}")
    
    def _monitor_devices(self, args):
        """Monitor devices in real-time"""
        print(f"\n{COLORS['CYAN']}Monitoring devices (Ctrl+C to stop){COLORS['RESET']}")
        print("-" * 70)
        
        try:
            while True:
                os.system('clear')
                self._list_devices(args)
                self._show_status(args)
                time.sleep(args.interval or 2)
        except KeyboardInterrupt:
            pass

# ==================== Main Entry Point ====================

def create_parser():
    """Create argument parser"""
    parser = argparse.ArgumentParser(
        description="Virtual Device Manager for Intel NUC",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create veth pair
  device-manager.py create veth veth0 --ips 10.0.0.1/24,10.0.0.2/24

  # Create bridge
  device-manager.py create bridge br0 --interfaces eth0,veth0

  # Create USB gadget
  device-manager.py create usb-gadget gadget1 --vendor 0x1d6b --product 0x0104

  # Create loop device
  device-manager.py create disk disk0 --size 1024

  # Create virtual camera
  device-manager.py create camera cam0 --width 1920 --height 1080 --fps 30

  # List all devices
  device-manager.py list

  # Monitor devices
  device-manager.py monitor --interval 5

  # Show device info
  device-manager.py info disk0
        """
    )
    
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose output')
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Create command
    create_parser = subparsers.add_parser('create', help='Create device')
    create_parser.add_argument('type', 
                               choices=['veth', 'bridge', 'tap', 'vlan', 'macvlan', 'bond',
                                       'usb-gadget', 'pty', 'serial-bridge', 'tcp-bridge',
                                       'disk', 'camera', 'audio-mic', 'audio-speaker', 
                                       'audio-loopback'],
                               help='Device type')
    create_parser.add_argument('name', help='Device name')
    
    # Network options
    create_parser.add_argument('--peer', help='Peer interface name (for veth/pty)')
    create_parser.add_argument('--ips', help='IP addresses (comma-separated)')
    create_parser.add_argument('--interfaces', help='Interfaces (comma-separated)')
    create_parser.add_argument('--parent', help='Parent interface')
    create_parser.add_argument('--vlan-id', type=int, help='VLAN ID')
    create_parser.add_argument('--mode', default='bridge', help='Mode (bridge, private, vepa)')
    create_parser.add_argument('--user', help='User for TAP')
    
    # USB options
    create_parser.add_argument('--vendor', type=int, default=0x1d6b, help='Vendor ID')
    create_parser.add_argument('--product', type=int, default=0x0104, help='Product ID')
    create_parser.add_argument('--manufacturer', default='Intel NUC', help='Manufacturer')
    create_parser.add_argument('--product-name', default='Virtual USB Gadget', help='Product name')
    create_parser.add_argument('--serial', help='Serial number')
    
    # Serial options
    create_parser.add_argument('--port1', help='First serial port')
    create_parser.add_argument('--port2', help='Second serial port')
    create_parser.add_argument('--port', type=int, help='TCP port')
    create_parser.add_argument('--serial-port', help='Serial port for TCP bridge')
    
    # Disk options
    create_parser.add_argument('--size', type=int, default=100, help='Size in MB')
    create_parser.add_argument('--fs-type', default='ext4', help='Filesystem type')
    
    # Camera options
    create_parser.add_argument('--width', type=int, default=1920, help='Frame width')
    create_parser.add_argument('--height', type=int, default=1080, help='Frame height')
    create_parser.add_argument('--fps', type=int, default=30, help='Frame rate')
    create_parser.add_argument('--format', default='YUYV', help='Pixel format')
    
    # Audio options
    create_parser.add_argument('--description', help='Device description')
    create_parser.add_argument('--source', help='Source for loopback')
    create_parser.add_argument('--sink', help='Sink for loopback')
    
    # Delete command
    delete_parser = subparsers.add_parser('delete', help='Delete device')
    delete_parser.add_argument('name', help='Device name')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List devices')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show status')
    
    # Start command
    start_parser = subparsers.add_parser('start', help='Start device')
    start_parser.add_argument('name', help='Device name')
    
    # Stop command
    stop_parser = subparsers.add_parser('stop', help='Stop device')
    stop_parser.add_argument('name', help='Device name')
    
    # Info command
    info_parser = subparsers.add_parser('info', help='Show device info')
    info_parser.add_argument('name', help='Device name')
    
    # Monitor command
    monitor_parser = subparsers.add_parser('monitor', help='Monitor devices')
    monitor_parser.add_argument('--interval', type=int, default=2,
                               help='Update interval in seconds')
    
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
    
    cli = DeviceManagerCLI()
    cli.run(args)

if __name__ == "__main__":
    main()
