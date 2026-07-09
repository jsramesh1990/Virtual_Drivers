# Makefile for Virtual Camera Drivers
# Intel NUC Virtual Device Platform

obj-m += v4l2-driver.o
obj-m += frame-generator.o

# Kernel build directory
KERNELDIR := /lib/modules/$(shell uname -r)/build
PWD := $(shell pwd)

# Module versions
V4L2_VERSION := 1.0.0
FRAME_VERSION := 1.0.0

# Compiler flags
ccflags-y := -DDEBUG
ccflags-y += -DV4L2_VERSION=\"$(V4L2_VERSION)\"
ccflags-y += -DFRAME_VERSION=\"$(FRAME_VERSION)\"

# Enable V4L2 loopback support
ccflags-y += -DCONFIG_VIDEO_V4L2LOOPBACK

# Module objects
v4l2-driver-objs := v4l2-driver.o
frame-generator-objs := frame-generator.o

# Dependency on V4L2 subsystem
ifeq ($(CONFIG_VIDEO_V4L2),)
$(warning V4L2 support not enabled in kernel)
endif

all: modules

modules:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) clean
	rm -f *.o *.ko *.mod.c *.mod .*.cmd Module.symvers modules.order
	rm -f *.orig *.rej *.bak
	rm -f .tmp_versions/
	rm -f modules.order
	rm -f Module.symvers

install:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) modules_install
	depmod -a
	@echo "========================================="
	@echo "Virtual Camera drivers installed successfully"
	@echo "========================================="
	@echo ""
	@echo "Installation complete. Use 'sudo modprobe v4l2-driver' to load."

uninstall:
	rm -f /lib/modules/$(shell uname -r)/kernel/drivers/virtual-camera/*.ko
	depmod -a
	@echo "Virtual Camera drivers uninstalled"

load: modules
	@echo "========================================="
	@echo "Loading Virtual Camera Drivers..."
	@echo "========================================="
	@# Load V4L2 loopback module if available
	@if lsmod | grep -q v4l2loopback; then \
		echo "v4l2loopback already loaded"; \
	else \
		echo "Loading v4l2loopback..."; \
		modprobe v4l2loopback 2>/dev/null || echo "v4l2loopback not available"; \
	fi
	@# Load frame generator
	@if lsmod | grep -q frame-generator; then \
		echo "frame-generator already loaded"; \
	else \
		echo "Loading frame-generator..."; \
		insmod frame-generator.ko 2>/dev/null || modprobe frame-generator 2>/dev/null || echo "Failed to load frame-generator"; \
	fi
	@# Load V4L2 driver
	@if lsmod | grep -q v4l2-driver; then \
		echo "v4l2-driver already loaded"; \
	else \
		echo "Loading v4l2-driver..."; \
		insmod v4l2-driver.ko 2>/dev/null || modprobe v4l2-driver 2>/dev/null || echo "Failed to load v4l2-driver"; \
	fi
	@echo ""
	@echo "========================================="
	@echo "Driver Status:"
	@echo "========================================="
	@lsmod | grep -E "v4l2|frame-generator|video" || echo "No video modules loaded"
	@echo ""
	@echo "Video Devices:"
	@ls -la /dev/video* 2>/dev/null || echo "No video devices found"
	@echo ""
	@echo "V4L2 Devices:"
	@v4l2-ctl --list-devices 2>/dev/null || echo "v4l2-ctl not available"

unload:
	@echo "========================================="
	@echo "Unloading Virtual Camera Drivers..."
	@echo "========================================="
	@rmmod v4l2-driver 2>/dev/null && echo "v4l2-driver unloaded" || echo "v4l2-driver not loaded"
	@rmmod frame-generator 2>/dev/null && echo "frame-generator unloaded" || echo "frame-generator not loaded"
	@rmmod v4l2loopback 2>/dev/null && echo "v4l2loopback unloaded" || echo "v4l2loopback not loaded"
	@echo ""
	@echo "Driver Status:"
	@lsmod | grep -E "v4l2|frame-generator|video" || echo "No video modules loaded"

status:
	@echo "========================================="
	@echo "Virtual Camera Driver Status"
	@echo "========================================="
	@echo ""
	@echo "Loaded Modules:"
	@lsmod | grep -E "v4l2|frame-generator|video" || echo "No video modules loaded"
	@echo ""
	@echo "Video Devices:"
	@ls -la /dev/video* 2>/dev/null || echo "No video devices found"
	@echo ""
	@echo "V4L2 Devices:"
	@v4l2-ctl --list-devices 2>/dev/null || echo "v4l2-ctl not available"
	@echo ""
	@echo "Frame Generator Info:"
	@if [ -f /sys/module/frame_generator/parameters/* ]; then \
		cat /sys/module/frame_generator/parameters/* 2>/dev/null || echo "No parameters found"; \
	else \
		echo "Frame generator not loaded"; \
	fi

test:
	@echo "========================================="
	@echo "Testing Virtual Camera Drivers"
	@echo "========================================="
	@echo ""
	@echo "1. Checking V4L2 devices..."
	@v4l2-ctl --list-devices 2>/dev/null || echo "No V4L2 devices found"
	@echo ""
	@echo "2. Testing video capture..."
	@if [ -e /dev/video0 ]; then \
		echo "Testing /dev/video0..."; \
		v4l2-ctl -d /dev/video0 --all 2>/dev/null || echo "Failed to query /dev/video0"; \
	else \
		echo "No video device found"; \
	fi
	@echo ""
	@echo "3. Testing frame capture..."
	@if [ -e /dev/video0 ]; then \
		echo "Capturing frame from /dev/video0..."; \
		timeout 2 v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=5 2>/dev/null || echo "Frame capture test skipped"; \
	else \
		echo "No video device for capture test"; \
	fi
	@echo ""
	@echo "4. Test Pattern Information:"
	@if [ -f /proc/frame-generator ]; then \
		cat /proc/frame-generator 2>/dev/null || echo "No info available"; \
	else \
		echo "Frame generator not registered"; \
	fi
	@echo ""
	@echo "========================================="
	@echo "Test Complete"
	@echo "========================================="

debug:
	@echo "========================================="
	@echo "Virtual Camera Debug Information"
	@echo "========================================="
	@echo ""
	@echo "Kernel Messages:"
	@dmesg | grep -i "v4l2\|video\|camera\|frame" | tail -30
	@echo ""
	@echo "Module Information:"
	@modinfo v4l2-driver 2>/dev/null || echo "v4l2-driver not available"
	@echo ""
	@modinfo frame-generator 2>/dev/null || echo "frame-generator not available"
	@echo ""
	@echo "Device Permissions:"
	@ls -la /dev/video* 2>/dev/null || echo "No video devices"
	@echo ""
	@echo "V4L2 Device Capabilities:"
	@for dev in /dev/video*; do \
		if [ -e $$dev ]; then \
			echo "$$dev:"; \
			v4l2-ctl -d $$dev --all 2>/dev/null | head -20 || echo "Failed to query $$dev"; \
			echo ""; \
		fi \
	done

help:
	@echo "========================================="
	@echo "Virtual Camera Driver Makefile Help"
	@echo "========================================="
	@echo ""
	@echo "Available targets:"
	@echo "  make          - Build the drivers"
	@echo "  make clean    - Clean build files"
	@echo "  make install  - Install drivers"
	@echo "  make uninstall- Uninstall drivers"
	@echo "  make load     - Load drivers"
	@echo "  make unload   - Unload drivers"
	@echo "  make status   - Check driver status"
	@echo "  make test     - Run tests"
	@echo "  make debug    - Show debug information"
	@echo "  make help     - Show this help"
	@echo ""
	@echo "Module parameters:"
	@echo "  fg_width      - Default frame width (default: 1920)"
	@echo "  fg_height     - Default frame height (default: 1080)"
	@echo "  fg_fps        - Default frame rate (default: 30)"
	@echo "  fg_format     - Default pixel format (default: 0=YUYV)"
	@echo "  fg_pattern    - Default test pattern (default: 0=Color bars)"
	@echo ""
	@echo "Usage examples:"
	@echo "  sudo modprobe frame-generator fg_width=1280 fg_height=720 fg_fps=60"
	@echo "  sudo modprobe v4l2-driver"
	@echo "  device-manager.py create camera video2"
	@echo "  ffplay /dev/video2"
	@echo ""

.PHONY: all clean install uninstall load unload status test debug help

# Additional targets for development
dev: load status
	@echo ""
	@echo "Development environment ready"
	@echo "Use 'make test' to test, 'make debug' for debugging"

quick: clean all load status
	@echo ""
	@echo "Quick build and load complete"

profile:
	@echo "Profiling Virtual Camera Drivers..."
	@perf record -g -a -e cycles:pp -- sleep 10
	@perf report

.PHONY: dev quick profile
