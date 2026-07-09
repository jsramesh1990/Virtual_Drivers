#!/usr/bin/env python3
"""
usb-redirect-example.py - USB redirection example for virtual machines

This script demonstrates USB redirection using USB/IP for passing
USB devices to virtual machines.
"""

import os
import sys
import subprocess
import time
import json
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class USBDeviceType(Enum):
    """USB device types"""
    STORAGE = "storage"
    HID = "hid"
    VIDEO = "video"
    AUDIO = "audio"
    SERIAL = "serial"
    NETWORK = "network"
    OTHER = "other"

@dataclass
class USBDevice:
    """USB device information"""
    bus: int
    address: int
    vendor_id: str
    product_id: str
    name: str
    type: USBDeviceType
    path: str
    active: bool

class USBRedirectionManager:
    """Manage USB redirection to VMs"""
    
    def __init__(self):
        self.devices: List[USBDevice] = []
        self.redirected_devices: Dict[str, str] = {}  # device -> VM
        self.usbip_available = self._check_usbip()
        
    def _check_usbip(self) -> bool:
        """Check if USB/IP is available"""
        try:
            subprocess.run("which usbip", shell=True, capture_output=True, check=True)
            subprocess.run("which usbipd", shell=True, capture_output=True, check=True)
            return True
        except:
            logger.warning("USB/IP not installed. Install with: sudo apt install usbip")
            return False
    
    def _load_usbip_modules(self) -> bool:
        """Load USB/IP kernel modules"""
        try:
            subprocess.run("sudo modprobe usbip-core", shell=True, check=True)
            subprocess.run("sudo modprobe usbip-host", shell=True, check=True)
            subprocess.run("sudo modprobe vhci-hcd", shell=True, check=True)
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to load USB/IP modules: {e}")
            return False
    
    def list_usb_devices(self) -> List[USBDevice]:
        """List all USB devices connected to the system"""
        devices = []
        
        try:
            # Use lsusb to get device list
            result = subprocess.run(
                "lsusb -v 2>/dev/null | grep -E 'Bus|idVendor|idProduct|iProduct'",
                shell=True, capture_output=True, text=True
            )
            
            current_dev = {}
            for line in result.stdout.split('\n'):
                if 'Bus' in line:
                    if current_dev:
                        devices.append(self._parse_usb_device(current_dev))
                    current_dev = {}
                    
                    # Parse bus and address
                    parts = line.split()
                    if len(parts) >= 6:
                        current_dev['bus'] = parts[1]
                        current_dev['address'] = parts[3]
                
                elif 'idVendor' in line:
                    current_dev['vendor_id'] = line.split()[1]
                elif 'idProduct' in line:
                    current_dev['product_id'] = line.split()[1]
                elif 'iProduct' in line:
                    current_dev['name'] = ' '.join(line.split()[1:])
            
            if current_dev:
                devices.append(self._parse_usb_device(current_dev))
                
        except Exception as e:
            logger.error(f"Error listing USB devices: {e}")
        
        self.devices = devices
        return devices
    
    def _parse_usb_device(self, dev_info: Dict) -> USBDevice:
        """Parse USB device information"""
        vendor_id = dev_info.get('vendor_id', '0000')
        product_id = dev_info.get('product_id', '0000')
        name = dev_info.get('name', f'{vendor_id}:{product_id}')
        
        # Determine device type
        device_type = self._detect_device_type(vendor_id, product_id)
        
        return USBDevice(
            bus=int(dev_info.get('bus', 0)),
            address=int(dev_info.get('address', 0)),
            vendor_id=vendor_id,
            product_id=product_id,
            name=name,
            type=device_type,
            path=f"/dev/bus/usb/{dev_info.get('bus', 0)}/{dev_info.get('address', 0)}",
            active=True
        )
    
    def _detect_device_type(self, vendor_id: str, product_id: str) -> USBDeviceType:
        """Detect USB device type based on vendor/product IDs"""
        # Common vendor IDs
        storage_vendors = ['05e3', '0781', '090c', '0bda']
        hid_vendors = ['046d', '045e', '04b3', '04ca']
        video_vendors = ['046d', '0c45', '1bcf', '05a3']
        audio_vendors = ['0d8c', '041e', '0582', '1235']
        
        if vendor_id in storage_vendors:
            return USBDeviceType.STORAGE
        elif vendor_id in hid_vendors:
            return USBDeviceType.HID
        elif vendor_id in video_vendors:
            return USBDeviceType.VIDEO
        elif vendor_id in audio_vendors:
            return USBDeviceType.AUDIO
        else:
            return USBDeviceType.OTHER
    
    def start_usbip_server(self) -> bool:
        """Start USB/IP server"""
        if not self.usbip_available:
            return False
        
        try:
            subprocess.run("sudo usbipd -D", shell=True, check=True)
            logger.info("USB/IP server started")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start USB/IP server: {e}")
            return False
    
    def export_device(self, device: USBDevice) -> bool:
        """Export USB device via USB/IP"""
        if not self.usbip_available:
            return False
        
        if not self._load_usbip_modules():
            return False
        
        try:
            # Bind device to USB/IP
            busid = f"{device.bus}-{device.address}"
            cmd = f"sudo usbip bind -b {busid}"
            subprocess.run(cmd, shell=True, check=True)
            
            logger.info(f"Exported USB device: {device.name} ({busid})")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to export device: {e}")
            return False
    
    def import_device(self, device_id: str, vm_name: str) -> bool:
        """Import USB device to VM"""
        if not self.usbip_available:
            return False
        
        try:
            # Attach device to VM
            cmd = f"sudo usbip attach -r localhost -b {device_id}"
            subprocess.run(cmd, shell=True, check=True)
            
            self.redirected_devices[device_id] = vm_name
            logger.info(f"Device {device_id} redirected to {vm_name}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to import device: {e}")
            return False
    
    def detach_device(self, device_id: str) -> bool:
        """Detach USB device from VM"""
        try:
            cmd = f"sudo usbip detach -p 0 -b {device_id}"
            subprocess.run(cmd, shell=True, check=True)
            
            if device_id in self.redirected_devices:
                del self.redirected_devices[device_id]
            
            logger.info(f"Device {device_id} detached")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to detach device: {e}")
            return False
    
    def list_redirected_devices(self) -> Dict:
        """List redirected devices"""
        return self.redirected_devices
    
    def get_vm_devices(self, vm_name: str) -> List[str]:
        """Get devices redirected to a specific VM"""
        return [dev for dev, vm in self.redirected_devices.items() if vm == vm_name]
    
    def redirect_interactive(self):
        """Interactive USB redirection"""
        print("\n=== USB Redirection Interactive ===")
        
        # List available devices
        devices = self.list_usb_devices()
        if not devices:
            print("No USB devices found")
            return
        
        print("\nAvailable USB devices:")
        for i, dev in enumerate(devices):
            print(f"{i+1}. {dev.name} ({dev.vendor_id}:{dev.product_id})")
            print(f"   Bus: {dev.bus}, Address: {dev.address}")
            print(f"   Type: {dev.type.value}")
            print()
        
        # Select device
        while True:
            try:
                choice = int(input("Select device number (0 to exit): "))
                if choice == 0:
                    return
                if 1 <= choice <= len(devices):
                    device = devices[choice-1]
                    break
            except ValueError:
                pass
            print("Invalid choice")
        
        # Get VM name
        vm_name = input("Enter VM name: ")
        if not vm_name:
            vm_name = "vm1"
        
        # Export device
        if self.export_device(device):
            device_id = f"{device.bus}-{device.address}"
            if self.import_device(device_id, vm_name):
                print(f"\n✅ Device {device.name} redirected to {vm_name}")
            else:
                print(f"\n❌ Failed to import device")
        else:
            print(f"\n❌ Failed to export device")

class VMUSBManager:
    """Manage USB devices for virtual machines"""
    
    def __init__(self):
        self.vms: Dict[str, List[USBDevice]] = {}
        self.redirect = USBRedirectionManager()
    
    def add_vm(self, name: str):
        """Add a VM to the manager"""
        self.vms[name] = []
        logger.info(f"Added VM: {name}")
    
    def attach_usb_to_vm(self, vm_name: str, device: USBDevice) -> bool:
        """Attach USB device to VM"""
        if vm_name not in self.vms:
            logger.error(f"VM {vm_name} not found")
            return False
        
        # Export via USB/IP
        if self.redirect.export_device(device):
            device_id = f"{device.bus}-{device.address}"
            if self.redirect.import_device(device_id, vm_name):
                self.vms[vm_name].append(device)
                logger.info(f"Attached {device.name} to {vm_name}")
                return True
        
        return False
    
    def detach_usb_from_vm(self, vm_name: str, device_id: str) -> bool:
        """Detach USB device from VM"""
        if vm_name not in self.vms:
            logger.error(f"VM {vm_name} not found")
            return False
        
        if self.redirect.detach_device(device_id):
            # Remove from VM list
            self.vms[vm_name] = [
                dev for dev in self.vms[vm_name]
                if f"{dev.bus}-{dev.address}" != device_id
            ]
            logger.info(f"Detached device {device_id} from {vm_name}")
            return True
        
        return False
    
    def show_vm_devices(self, vm_name: str):
        """Show devices attached to VM"""
        if vm_name not in self.vms:
            logger.error(f"VM {vm_name} not found")
            return
        
        devices = self.vms[vm_name]
        if not devices:
            print(f"\nNo USB devices attached to {vm_name}")
            return
        
        print(f"\nUSB devices attached to {vm_name}:")
        for i, dev in enumerate(devices):
            print(f"{i+1}. {dev.name} ({dev.vendor_id}:{dev.product_id})")

def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage: usb-redirect-example.py <command>")
        print("  commands: list, redirect, vm-attach, vm-detach, status")
        sys.exit(1)
    
    command = sys.argv[1]
    manager = USBRedirectionManager()
    vm_manager = VMUSBManager()
    
    try:
        if command == "list":
            devices = manager.list_usb_devices()
            print("\nUSB Devices:")
            for dev in devices:
                print(f"  {dev.name} ({dev.vendor_id}:{dev.product_id})")
                print(f"    Bus: {dev.bus}, Address: {dev.address}")
                print(f"    Type: {dev.type.value}")
                print()
        
        elif command == "redirect":
            manager.redirect_interactive()
        
        elif command == "vm-attach":
            if len(sys.argv) < 4:
                print("Usage: usb-redirect-example.py vm-attach <vm_name> <device_id>")
                sys.exit(1)
            
            vm_name = sys.argv[2]
            device_id = sys.argv[3]
            
            # Find device
            devices = manager.list_usb_devices()
            for dev in devices:
                if f"{dev.bus}-{dev.address}" == device_id:
                    if vm_manager.attach_usb_to_vm(vm_name, dev):
                        print(f"✅ Device attached to {vm_name}")
                    else:
                        print(f"❌ Failed to attach device")
                    break
            else:
                print(f"❌ Device {device_id} not found")
        
        elif command == "vm-detach":
            if len(sys.argv) < 4:
                print("Usage: usb-redirect-example.py vm-detach <vm_name> <device_id>")
                sys.exit(1)
            
            vm_name = sys.argv[2]
            device_id = sys.argv[3]
            
            if vm_manager.detach_usb_from_vm(vm_name, device_id):
                print(f"✅ Device detached from {vm_name}")
            else:
                print(f"❌ Failed to detach device")
        
        elif command == "status":
            print("\nUSB Redirection Status:")
            print("========================")
            
            devices = manager.list_redirected_devices()
            if devices:
                print("\nRedirected Devices:")
                for dev_id, vm in devices.items():
                    print(f"  {dev_id} -> {vm}")
            else:
                print("\nNo redirected devices")
            
            print("\nVM USB Attachments:")
            for vm, devs in vm_manager.vms.items():
                if devs:
                    print(f"  {vm}:")
                    for dev in devs:
                        print(f"    {dev.name} ({dev.vendor_id}:{dev.product_id})")
        
        else:
            print(f"Unknown command: {command}")
            
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        logger.error(f"Error: {e}")

if __name__ == "__main__":
    main()
