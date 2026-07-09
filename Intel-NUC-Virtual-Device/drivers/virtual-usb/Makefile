# Makefile for Virtual USB Drivers
# Intel NUC Virtual Device Platform

obj-m += usb-gadget.o
obj-m += usb-redirect.o

# Kernel build directory
KERNELDIR := /lib/modules/$(shell uname -r)/build
PWD := $(shell pwd)

# Module versions
GADGET_VERSION := 1.0.0
REDIRECT_VERSION := 1.0.0

# Compiler flags
ccflags-y := -DDEBUG
ccflags-y += -DGADGET_VERSION=\"$(GADGET_VERSION)\"
ccflags-y += -DREDIRECT_VERSION=\"$(REDIRECT_VERSION)\"

# Module objects
usb-gadget-objs := usb-gadget.o
usb-redirect-objs := usb-redirect.o

# USB gadget configuration
CONFIG_USB_GADGET := y
CONFIG_USB_CONFIGFS := y

all: modules

modules:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) clean
	rm -f *.o *.ko *.mod.c *.mod .*.cmd Module.symvers modules.order
	rm -f *.orig *.rej

install:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) modules_install
	depmod -a
	@echo "USB drivers installed successfully"

uninstall:
	rm -f /lib/modules/$(shell uname -r)/kernel/drivers/virtual-usb/*.ko
	depmod -a
	@echo "USB drivers uninstalled"

load: modules
	@echo "Loading Virtual USB Drivers..."
	@# Load USB gadget module
	@modprobe libcomposite 2>/dev/null || true
	@modprobe usb-gadget 2>/dev/null || insmod usb-gadget.ko
	@# Load USB redirect module
	@modprobe usb-redirect 2>/dev/null || insmod usb-redirect.ko
	@echo "USB drivers loaded successfully"
	@lsmod | grep -E "usb-gadget|usb-redirect"

unload:
	@echo "Unloading Virtual USB Drivers..."
	@rmmod usb-redirect 2>/dev/null || true
	@rmmod usb-gadget 2>/dev/null || true
	@echo "USB drivers unloaded successfully"

status:
	@echo "USB Gadget Status:"
	@ls -la /sys/kernel/config/usb_gadget/ 2>/dev/null || echo "No USB gadgets configured"
	@echo ""
	@echo "USB Devices:"
	@lsusb
	@echo ""
	@echo "USB Modules:"
	@lsmod | grep -E "usb|gadget"

test:
	@echo "Testing Virtual USB Drivers..."
	@./test-scripts/test-usb-gadget.sh
	@./test-scripts/test-usb-redirect.sh
	@echo "All USB tests completed"

debug:
	@echo "Debugging Virtual USB Drivers..."
	@dmesg | grep -i "usb\|gadget" | tail -30
	@echo "---"
	@ls -la /dev/usb*
	@echo "---"
	@cat /proc/bus/usb/devices 2>/dev/null || echo "USB devices not available"

.PHONY: all clean install uninstall load unload status test debug
