# Makefile for Virtual Serial Drivers
# Intel NUC Virtual Device Platform

obj-m += pty-manager.o
obj-m += socat-bridge.o

# Kernel build directory
KERNELDIR := /lib/modules/$(shell uname -r)/build
PWD := $(shell pwd)

# Module versions
PTY_VERSION := 1.0.0
BRIDGE_VERSION := 1.0.0

# Compiler flags
ccflags-y := -DDEBUG
ccflags-y += -DPTY_VERSION=\"$(PTY_VERSION)\"
ccflags-y += -DBRIDGE_VERSION=\"$(BRIDGE_VERSION)\"

# Module objects
pty-manager-objs := pty-manager.o
socat-bridge-objs := socat-bridge.o

all: modules

modules:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) clean
	rm -f *.o *.ko *.mod.c *.mod .*.cmd Module.symvers modules.order

install:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) modules_install
	depmod -a

uninstall:
	rm -f /lib/modules/$(shell uname -r)/kernel/drivers/virtual-serial/*.ko
	depmod -a

load: modules
	@echo "Loading Virtual Serial Drivers..."
	@modprobe pty-manager || insmod pty-manager.ko
	@modprobe socat-bridge || insmod socat-bridge.ko
	@echo "Drivers loaded successfully"
	@ls -la /dev/ttyV*
	@ls -la /dev/serial-bridge*

unload:
	@echo "Unloading Virtual Serial Drivers..."
	@rmmod socat-bridge 2>/dev/null || true
	@rmmod pty-manager 2>/dev/null || true
	@echo "Drivers unloaded successfully"

test:
	@echo "Testing Virtual Serial Drivers..."
	@./test-scripts/test-pty.sh
	@./test-scripts/test-bridge.sh
	@echo "All tests completed"

debug:
	@echo "Debugging Virtual Serial Drivers..."
	@dmesg | tail -50
	@echo "---"
	@ls -la /dev/ttyV*
	@echo "---"
	@ls -la /dev/serial-bridge*

.PHONY: all clean install uninstall load unload test debug
