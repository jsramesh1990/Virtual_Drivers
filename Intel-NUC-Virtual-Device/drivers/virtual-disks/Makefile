# Makefile for Virtual Disk Drivers
# Intel NUC Virtual Device Platform

obj-m += loop-device.o
obj-m += nbd-server.o

# Kernel build directory
KERNELDIR := /lib/modules/$(shell uname -r)/build
PWD := $(shell pwd)

# Module versions
LOOP_VERSION := 1.0.0
NBD_VERSION := 1.0.0

# Compiler flags
ccflags-y := -DDEBUG
ccflags-y += -DLOOP_VERSION=\"$(LOOP_VERSION)\"
ccflags-y += -DNBD_VERSION=\"$(NBD_VERSION)\"

# Module objects
loop-device-objs := loop-device.o
nbd-server-objs := nbd-server.o

all: modules

modules:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) clean
	rm -f *.o *.ko *.mod.c *.mod .*.cmd Module.symvers modules.order

install:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) modules_install
	depmod -a
	@echo "Disk drivers installed successfully"

uninstall:
	rm -f /lib/modules/$(shell uname -r)/kernel/drivers/virtual-disks/*.ko
	depmod -a
	@echo "Disk drivers uninstalled"

load: modules
	@echo "Loading Virtual Disk Drivers..."
	@modprobe loop-device 2>/dev/null || insmod loop-device.ko
	@modprobe nbd-server 2>/dev/null || insmod nbd-server.ko
	@echo "Disk drivers loaded successfully"
	@lsmod | grep -E "loop-device|nbd-server"
	@ls -la /dev/loop* 2>/dev/null || echo "No loop devices created yet"
	@ls -la /dev/nbd* 2>/dev/null || echo "No NBD devices created yet"

unload:
	@echo "Unloading Virtual Disk Drivers..."
	@rmmod nbd-server 2>/dev/null || true
	@rmmod loop-device 2>/dev/null || true
	@echo "Disk drivers unloaded successfully"

test:
	@echo "Testing Virtual Disk Drivers..."
	@./test-scripts/test-loop.sh
	@./test-scripts/test-nbd.sh
	@echo "All disk tests completed"

debug:
	@echo "Debugging Virtual Disk Drivers..."
	@dmesg | grep -i "loop\|nbd\|disk" | tail -30
	@echo "---"
	@df -h
	@echo "---"
	@losetup -a 2>/dev/null || echo "No loop devices in use"

.PHONY: all clean install uninstall load unload test debug
