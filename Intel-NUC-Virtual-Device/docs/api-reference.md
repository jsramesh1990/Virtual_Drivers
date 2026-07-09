# API Reference - Intel NUC Virtual Device Platform

## Overview

This document provides comprehensive API documentation for the Intel NUC Virtual Device Platform, covering the device manager, kernel modules, and management interfaces.

---

## Device Manager API (Python)

### Class: VirtualDeviceManager

The main class for managing virtual devices.

#### Methods

##### `__init__(self)`
Initialize the device manager.

```python
manager = VirtualDeviceManager()
```

##### `create_network_device(name: str, dev_type: str = "veth") -> bool`
Create a virtual network interface.

**Parameters:**
- `name` (str): Device name
- `dev_type` (str): Type of network device (veth, bridge, tap, macvlan)

**Returns:** `bool` - True if successful

**Example:**
```python
manager.create_network_device("veth0", "veth")
manager.create_network_device("br0", "bridge")
```

##### `create_serial_device(name: str) -> bool`
Create a virtual serial port (PTY).

**Parameters:**
- `name` (str): Device name

**Returns:** `bool` - True if successful

**Example:**
```python
manager.create_serial_device("ttyV0")
```

##### `create_disk_device(name: str, size_mb: int = 100) -> bool`
Create a virtual disk device.

**Parameters:**
- `name` (str): Device name
- `size_mb` (int): Size in MB (default: 100)

**Returns:** `bool` - True if successful

**Example:**
```python
manager.create_disk_device("disk0", 1024)
```

##### `create_camera_device(name: str = "video2") -> bool`
Create a virtual camera device.

**Parameters:**
- `name` (str): Device name (default: video2)

**Returns:** `bool` - True if successful

**Example:**
```python
manager.create_camera_device("video2")
```

##### `create_audio_device(name: str) -> bool`
Create a virtual audio device.

**Parameters:**
- `name` (str): Device name

**Returns:** `bool` - True if successful

**Example:**
```python
manager.create_audio_device("virtual-speaker")
```

##### `list_devices() -> None`
List all virtual devices.

**Example:**
```python
manager.list_devices()
```

##### `remove_device(name: str) -> bool`
Remove a virtual device.

**Parameters:**
- `name` (str): Device name to remove

**Returns:** `bool` - True if successful

**Example:**
```python
manager.remove_device("veth0")
```

##### `get_device_status(name: str) -> Dict`
Get status of a specific device.

**Parameters:**
- `name` (str): Device name

**Returns:** `Dict` - Device status information

**Example:**
```python
status = manager.get_device_status("veth0")
print(status)
```

---

### Class: PerformanceMonitor

Monitor system and device performance.

#### Methods

##### `check_cpu() -> str`
Get CPU usage information.

**Returns:** `str` - CPU status

**Example:**
```python
cpu_info = PerformanceMonitor.check_cpu()
```

##### `check_memory() -> str`
Get memory usage information.

**Returns:** `str` - Memory status

**Example:**
```python
mem_info = PerformanceMonitor.check_memory()
```

##### `check_network(name: str) -> str`
Get network device statistics.

**Parameters:**
- `name` (str): Network interface name

**Returns:** `str` - Network statistics

**Example:**
```python
net_stats = PerformanceMonitor.check_network("eth0")
```

---

## Kernel Module API (C)

### Network Driver API

#### Data Structures

```c
struct virt_net_priv {
    struct net_device *dev;
    struct net_device *peer;
    spinlock_t lock;
};
```

#### Functions

##### `virt_net_open(struct net_device *dev)`
Open the virtual network device.

**Parameters:**
- `dev` - Network device structure

**Returns:** `int` - 0 on success, negative on error

##### `virt_net_close(struct net_device *dev)`
Close the virtual network device.

**Parameters:**
- `dev` - Network device structure

**Returns:** `int` - 0 on success, negative on error

##### `virt_net_xmit(struct sk_buff *skb, struct net_device *dev)`
Transmit packet through virtual network device.

**Parameters:**
- `skb` - Socket buffer
- `dev` - Network device structure

**Returns:** `int` - NETDEV_TX_OK on success

##### `virt_net_init(void)`
Initialize the virtual network driver.

**Returns:** `int` - 0 on success, negative on error

##### `virt_net_exit(void)`
Clean up the virtual network driver.

---

### V4L2 Camera Driver API

#### Data Structures

```c
struct vcam_device {
    struct v4l2_device v4l2_dev;
    struct video_device *vdev;
    struct vb2_queue queue;
    struct mutex lock;
    spinlock_t slock;
    void *buffer;
    int buffer_size;
};
```

#### Functions

##### `vcam_init(void)`
Initialize the virtual camera driver.

**Returns:** `int` - 0 on success, negative on error

##### `vcam_exit(void)`
Clean up the virtual camera driver.

##### `vcam_queue_setup(struct vb2_queue *q, unsigned int *nbuffers, ...)`
Set up the video buffer queue.

**Parameters:**
- `q` - VB2 queue
- `nbuffers` - Number of buffers

**Returns:** `int` - 0 on success, negative on error

##### `vcam_buf_queue(struct vb2_buffer *vb)`
Queue a video buffer.

**Parameters:**
- `vb` - VB2 buffer

---

### USB Gadget API

#### Data Structures

```c
struct usb_gadget_device {
    struct usb_gadget *gadget;
    struct usb_configuration *config;
    struct usb_function *function;
    struct list_head list;
};
```

#### Functions

##### `usb_gadget_init(void)`
Initialize USB gadget support.

**Returns:** `int` - 0 on success, negative on error

##### `usb_gadget_exit(void)`
Clean up USB gadget support.

##### `usb_gadget_create(const char *name, int vendor, int product)`
Create a USB gadget device.

**Parameters:**
- `name` - Device name
- `vendor` - Vendor ID
- `product` - Product ID

**Returns:** `struct usb_gadget_device*` - Pointer to gadget device

---

## System Call Interface

### ioctl Commands

#### Network Device ioctls

```c
#define VIRT_NET_GET_PEER   _IOR('V', 0, struct ifreq *)
#define VIRT_NET_SET_PEER   _IOW('V', 1, struct ifreq *)
#define VIRT_NET_SET_MTU    _IOW('V', 2, int)
#define VIRT_NET_GET_STATS  _IOR('V', 3, struct rtnl_link_stats64 *)
```

**Usage Examples:**

```c
// Get peer interface
struct ifreq ifr;
strcpy(ifr.ifr_name, "veth0");
ioctl(sock, VIRT_NET_GET_PEER, &ifr);

// Set MTU
int mtu = 9000;
ioctl(sock, VIRT_NET_SET_MTU, &mtu);
```

#### USB ioctls

```c
#define USB_GADGET_CREATE   _IOW('U', 0, struct usb_gadget_info *)
#define USB_GADGET_REMOVE   _IOW('U', 1, int)
#define USB_GADGET_ENABLE   _IO('U', 2)
#define USB_GADGET_DISABLE  _IO('U', 3)
```

**Usage Examples:**

```c
// Create gadget
struct usb_gadget_info info = {
    .name = "g1",
    .vendor_id = 0x1234,
    .product_id = 0x5678
};
ioctl(fd, USB_GADGET_CREATE, &info);
```

#### V4L2 ioctls

```c
#define V4L2_LOOPBACK_CREATE  _IOW('V', 0, struct v4l2_loopback_info *)
#define V4L2_LOOPBACK_DESTROY _IOW('V', 1, int)
#define V4L2_LOOPBACK_SET_FMT  _IOW('V', 2, struct v4l2_format *)
```

**Usage Examples:**

```c
// Create loopback device
struct v4l2_loopback_info info = {
    .device_number = 2,
    .card_label = "Virtual Camera"
};
ioctl(fd, V4L2_LOOPBACK_CREATE, &info);
```

---

## Configuration File API

### YAML Configuration Format

#### Network Configuration

```yaml
network:
  interfaces:
    - name: eth0
      type: physical
      speed: 2500
      duplex: full
      mtu: 1500
      state: up
```

#### USB Configuration

```yaml
usb:
  controllers:
    - name: xhci_hcd
      type: xhci
      ports: 10
      speed: super
  
  gadgets:
    - name: g1
      enabled: true
      functions:
        - type: acm
          name: "ttyGS0"
```

#### Audio Configuration

```yaml
audio_system:
  primary: pipewire
  
alsa:
  cards:
    - name: "HDA Intel PCH"
      driver: "snd_hda_intel"
      index: 0
      enabled: true
```

---

## Event System API

### Event Types

```c
enum virt_dev_event_type {
    VIRT_DEV_EVENT_CREATE,
    VIRT_DEV_EVENT_REMOVE,
    VIRT_DEV_EVENT_STATE_CHANGE,
    VIRT_DEV_EVENT_ERROR,
    VIRT_DEV_EVENT_MONITOR
};
```

### Event Data Structure

```c
struct virt_dev_event {
    enum virt_dev_event_type type;
    char device_name[64];
    char device_type[32];
    int status;
    union {
        struct create_event create;
        struct error_event error;
        struct state_event state;
    } data;
};
```

### Event Callbacks

```c
void register_event_handler(void (*handler)(struct virt_dev_event *));
void unregister_event_handler(void (*handler)(struct virt_dev_event *));
```

**Usage Example:**

```c
void handle_event(struct virt_dev_event *event) {
    printf("Event type: %d, Device: %s\n", 
           event->type, event->device_name);
}

register_event_handler(handle_event);
```

---

## Command Line Interface

### device-manager.py

```bash
# Create device
device-manager.py create network veth0
device-manager.py create serial ttyV0
device-manager.py create disk disk0 1024
device-manager.py create camera video2

# List devices
device-manager.py list

# Remove device
device-manager.py remove veth0

# Monitor device
device-manager.py monitor veth0
device-manager.py monitor cpu
device-manager.py monitor memory
```

### Module Management

```bash
# Load module
insmod /lib/modules/$(uname -r)/kernel/drivers/virtual-net/virt-net.ko

# List loaded modules
lsmod | grep virt

# Remove module
rmmod virt-net
```

---

## Python Integration API

### DeviceManager Module

```python
from device_manager import VirtualDeviceManager, PerformanceMonitor

# Create manager
manager = VirtualDeviceManager()

# Create devices
manager.create_network_device("veth0")
manager.create_serial_device("ttyV0")

# Get status
status = manager.get_device_status("veth0")
print(f"Device: {status['name']}, Status: {status['status']}")

# List all
manager.list_devices()
```

### Monitoring Module

```python
from monitoring import DeviceMonitor

monitor = DeviceMonitor()

# Start monitoring
monitor.start(interval=5)  # 5 second interval

# Get metrics
metrics = monitor.get_metrics()
print(f"CPU: {metrics['cpu']}%")
print(f"Memory: {metrics['memory']}%")
print(f"Network: {metrics['network']}")

# Stop monitoring
monitor.stop()
```

---

## Error Codes

| Code | Description | Solution |
|------|-------------|----------|
| EPERM (1) | Operation not permitted | Check permissions |
| ENOENT (2) | No such device | Create device first |
| EINVAL (22) | Invalid argument | Check parameters |
| ENOMEM (12) | Out of memory | Free resources |
| EBUSY (16) | Device busy | Wait and retry |
| ENODEV (19) | No such device | Load kernel module |
| EIO (5) | I/O error | Check hardware |

---

## Return Values

### Success Codes
- `0`: Success
- `>0`: Success with additional information
- `1`: Success but device already exists
- `2`: Success but device in degraded state

### Error Codes
- `-1`: General error
- `-2`: Invalid parameters
- `-3`: Permission denied
- `-4`: Device not found
- `-5`: Device already exists
- `-6`: Resource unavailable
- `-7`: Operation timeout

---

## Example Applications

### Custom Device Manager

```python
#!/usr/bin/env python3

import sys
from device_manager import VirtualDeviceManager

class CustomDeviceManager:
    def __init__(self):
        self.manager = VirtualDeviceManager()
    
    def create_devices(self, count=10):
        """Create multiple virtual devices"""
        for i in range(count):
            name = f"veth{i}"
            self.manager.create_network_device(name)
            print(f"Created {name}")
    
    def cleanup(self):
        """Clean up all devices"""
        devices = self.manager.list_devices()
        for device in devices:
            self.manager.remove_device(device['name'])
            print(f"Removed {device['name']}")

if __name__ == "__main__":
    cdm = CustomDeviceManager()
    cdm.create_devices(5)
    cdm.cleanup()
```

### Performance Monitor

```python
#!/usr/bin/env python3

import time
from device_manager import PerformanceMonitor

def monitor_loop():
    while True:
        cpu = PerformanceMonitor.check_cpu()
        memory = PerformanceMonitor.check_memory()
        network = PerformanceMonitor.check_network("eth0")
        
        print(f"CPU: {cpu}")
        print(f"Memory: {memory}")
        print(f"Network: {network}")
        print("---")
        
        time.sleep(5)

if __name__ == "__main__":
    try:
        monitor_loop()
    except KeyboardInterrupt:
        print("Monitoring stopped")
```

---

## API Versioning

### Version Information

```python
from device_manager import get_version

version = get_version()
print(f"API Version: {version['api']}")
print(f"Kernel Version: {version['kernel']}")
print(f"Driver Version: {version['driver']}")
```

### Compatibility Matrix

| API Version | Driver Version | Kernel Version | Notes |
|-------------|----------------|----------------|-------|
| 1.0.0 | 1.0.0 | 5.15+ | Initial release |
| 1.1.0 | 1.1.0 | 6.2+ | Added USB support |
| 2.0.0 | 2.0.0 | 6.2+ | Complete rewrite |

---

## Deprecation Policy

### Deprecation Process
1. Feature marked as deprecated in documentation
2. Warning messages added to code
3. Feature remains for 2 major releases
4. Feature removed in major version bump

### Current Deprecations

| Feature | Deprecated In | Removal In | Replacement |
|---------|---------------|------------|-------------|
| `create_serial_device()` | 2.0.0 | 3.0.0 | `create_device("serial", name)` |
| `check_network()` | 1.1.0 | 2.0.0 | `get_network_stats()` |
| Old config format | 1.0.0 | 2.0.0 | YAML format |

---

## Best Practices

### Error Handling
```python
try:
    manager.create_network_device("veth0")
except DeviceCreationError as e:
    print(f"Failed to create device: {e}")
    # Handle error appropriately
```

### Resource Cleanup
```python
devices = manager.list_devices()
for device in devices:
    if device['type'] == 'veth':
        manager.remove_device(device['name'])
```

### Performance Optimization
```python
# Batch operations
with manager.batch_operations():
    for i in range(10):
        manager.create_network_device(f"veth{i}")
```

---

## API Documentation Generation

### Generate HTML Documentation
```bash
./scripts/generate-api-docs.py --format html
```

### Generate PDF Documentation
```bash
./scripts/generate-api-docs.py --format pdf
```

### Generate Man Pages
```bash
./scripts/generate-api-docs.py --format man
```

---

## Support and Resources

### API Support
- Email: api-support@nuc-platform.example.com
- Issue Tracker: https://github.com/yourusername/intel-nuc-virtual-device-platform/issues

### API References
- Python Docs: https://docs.python.org/3/
- Linux Kernel API: https://www.kernel.org/doc/html/latest/
- V4L2 API: https://www.kernel.org/doc/html/latest/media/
```

---

