# Installation Guide - Intel NUC Virtual Device Platform

## System Requirements

### Hardware Requirements
| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | Intel Core i5-1135G7 | Intel Core i7-1260P |
| **RAM** | 16GB DDR4 | 64GB DDR4 |
| **Storage** | 256GB NVMe | 1TB NVMe + 2TB SATA |
| **Network** | 1GbE | 2.5GbE |
| **USB** | USB 3.0 | USB 3.2 Gen 2 |

### Software Requirements
| Component | Version |
|-----------|---------|
| **Linux Kernel** | 5.15+ (6.2+ recommended) |
| **Distro** | Ubuntu 22.04 LTS, Debian 12, Fedora 38+ |
| **GCC** | 11.0+ |
| **Python** | 3.9+ |
| **Docker** | 24.0+ |
| **KVM/QEMU** | 8.0+ |

---

## Pre-Installation

### 1. BIOS Configuration

```bash
# Enter BIOS (Press F2 during boot)
# Configure the following settings:

# Enable Virtualization
Intel VT-x: Enabled
Intel VT-d: Enabled
Intel EPT: Enabled
SR-IOV: Enabled

# Enable Performance
Intel Turbo Boost: Enabled
Hyper-Threading: Enabled
CPU C-states: Enabled

# Power Settings
Wake on LAN: Enabled
Deep Sleep: Disabled
```

### 2. System Preparation

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install essential packages
sudo apt install -y \
    build-essential \
    linux-headers-$(uname -r) \
    git \
    wget \
    curl \
    vim \
    htop \
    net-tools \
    dkms \
    make \
    gcc \
    python3-pip

# Create workspace
mkdir -p ~/workspace/nuc-platform
cd ~/workspace/nuc-platform
```

---

## Installation Steps

### Step 1: Clone Repository

```bash
# Clone the main repository
git clone https://github.com/yourusername/intel-nuc-virtual-device-platform.git
cd intel-nuc-virtual-device-platform

# Checkout stable branch (if available)
git checkout stable
```

### Step 2: Install Dependencies

```bash
# Install system dependencies
sudo ./scripts/install-dependencies.sh

# Install Python packages
pip3 install -r requirements.txt

# Verify installations
python3 -c "import sys; print(f'Python {sys.version}')"
gcc --version
make --version
```

### Step 3: Configure Kernel

```bash
# Copy kernel configuration
sudo cp config/kernel-config /usr/src/linux/.config

# Build kernel modules
cd /usr/src/linux
sudo make olddefconfig
sudo make -j$(nproc)
sudo make modules_install
sudo make install

# Reboot with new kernel
sudo reboot
```

### Step 4: Build Kernel Modules

```bash
# Navigate to drivers directory
cd ~/workspace/nuc-platform/intel-nuc-virtual-device-platform/drivers

# Build all modules
make all

# Install modules
sudo make install

# Load modules
sudo make load

# Verify modules are loaded
lsmod | grep -E "virt|v4l2|tun|bridge"
```

### Step 5: Setup Device Manager

```bash
# Install device manager
sudo cp tools/device-manager.py /usr/local/bin/
sudo chmod +x /usr/local/bin/device-manager.py

# Create configuration directory
sudo mkdir -p /etc/virtual-devices

# Copy configurations
sudo cp config/* /etc/virtual-devices/

# Setup systemd service
sudo cp services/virtual-devices.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable virtual-devices
sudo systemctl start virtual-devices

# Check status
sudo systemctl status virtual-devices
```

### Step 6: Configure Network

```bash
# Apply network configuration
sudo cp config/network-config.yaml /etc/netplan/
sudo netplan apply

# Verify network
ip addr show
ip link show
ping -c 4 8.8.8.8
```

### Step 7: Configure USB

```bash
# Apply USB configuration
sudo cp config/usb-config.yaml /etc/usb/

# Start USB gadget
sudo systemctl start usb-gadget
sudo systemctl enable usb-gadget

# Verify USB
lsusb
dmesg | grep -i usb
```

### Step 8: Configure Audio

```bash
# Apply audio configuration
sudo cp config/audio-config.yaml /etc/pipewire/

# Restart audio services
systemctl --user restart pipewire
systemctl --user restart wireplumber

# Verify audio
pactl list short sinks
pactl list short sources
```

### Step 9: Setup Virtualization

```bash
# Install KVM/QEMU
sudo apt install -y qemu-kvm libvirt-daemon-system libvirt-clients virt-manager

# Add user to libvirt group
sudo usermod -aG libvirt $USER

# Enable services
sudo systemctl enable libvirtd
sudo systemctl start libvirtd

# Verify virtualization
sudo virsh list --all
sudo kvm-ok
```

### Step 10: Setup Container Runtime

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER

# Start Docker
sudo systemctl enable docker
sudo systemctl start docker

# Test Docker
docker run hello-world
```

---

## Post-Installation

### 1. Verify Installation

```bash
# Run verification script
./scripts/verify-installation.sh

# Expected output:
# ✅ Kernel modules loaded
# ✅ Device manager running
# ✅ Network configured
# ✅ USB configured
# ✅ Audio configured
# ✅ Virtualization working
# ✅ Container runtime working
```

### 2. Create Test Devices

```bash
# Create test network device
device-manager.py create network test-veth

# Create test serial device
device-manager.py create serial test-serial

# Create test disk
device-manager.py create disk test-disk 1024

# Create test camera
device-manager.py create camera test-cam

# List all devices
device-manager.py list
```

### 3. Run Tests

```bash
# Run all tests
make test

# Run specific test
./tests/integration/network-test.sh
./tests/integration/usb-test.sh
./tests/integration/serial-test.sh
./tests/integration/disk-test.sh
./tests/integration/camera-test.sh
./tests/integration/audio-test.sh
```

### 4. Setup Monitoring

```bash
# Install monitoring stack
./scripts/setup-monitoring.sh

# Access Grafana dashboard
# Open browser to http://localhost:3000
# Default credentials: admin/admin
```

---

## Troubleshooting Installation

### Common Issues

#### Issue 1: Kernel Module Compilation Fails
```bash
# Solution: Install correct headers
sudo apt install linux-headers-$(uname -r)
sudo apt install dkms
sudo dkms add .
sudo dkms build
sudo dkms install
```

#### Issue 2: Device Manager Permission Denied
```bash
# Solution: Fix permissions
sudo chmod 755 /usr/local/bin/device-manager.py
sudo chown root:root /usr/local/bin/device-manager.py
```

#### Issue 3: Network Not Working
```bash
# Solution: Restart network services
sudo systemctl restart networking
sudo systemctl restart systemd-networkd
sudo netplan apply
```

#### Issue 4: USB Gadget Not Detected
```bash
# Solution: Load USB gadget modules
sudo modprobe libcomposite
sudo modprobe g_serial
sudo modprobe g_ether
sudo modprobe g_mass_storage
```

#### Issue 5: Audio Not Working
```bash
# Solution: Restart audio services
systemctl --user restart pipewire
systemctl --user restart pipewire-pulse
systemctl --user restart wireplumber

# Check audio devices
aplay -l
arecord -l
```

---

## Uninstallation

### Complete Removal

```bash
# Stop services
sudo systemctl stop virtual-devices
sudo systemctl disable virtual-devices

# Remove kernel modules
sudo make unload
sudo make uninstall

# Remove device manager
sudo rm /usr/local/bin/device-manager.py

# Remove configurations
sudo rm -rf /etc/virtual-devices

# Remove systemd service
sudo rm /etc/systemd/system/virtual-devices.service
sudo systemctl daemon-reload

# Remove packages (optional)
sudo apt remove qemu-kvm libvirt-daemon-system virt-manager
sudo apt remove docker-ce docker-ce-cli containerd.io

# Remove repository
cd ~/workspace/nuc-platform
rm -rf intel-nuc-virtual-device-platform
```

---

## Upgrade Instructions

### Upgrading from Previous Version

```bash
# Backup current configuration
sudo cp -r /etc/virtual-devices /etc/virtual-devices.backup

# Stop services
sudo systemctl stop virtual-devices

# Pull latest code
cd ~/workspace/nuc-platform/intel-nuc-virtual-device-platform
git pull origin main

# Rebuild modules
make clean
make all
sudo make install

# Update configurations
sudo cp -r config/* /etc/virtual-devices/

# Restart services
sudo systemctl start virtual-devices

# Verify upgrade
device-manager.py --version
```

---

## Post-Installation Verification Checklist

- [ ] BIOS virtualization features enabled
- [ ] Kernel compiled with required modules
- [ ] Device manager installed and running
- [ ] Network interfaces visible (ip link)
- [ ] USB gadgets working (lsusb)
- [ ] Audio devices available (pactl)
- [ ] KVM/QEMU working (virsh)
- [ ] Docker running (docker ps)
- [ ] Virtual devices creatable (device-manager.py)
- [ ] Monitoring dashboard accessible

---

