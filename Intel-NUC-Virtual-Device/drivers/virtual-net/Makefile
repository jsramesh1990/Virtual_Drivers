# Makefile for Virtual Network Drivers
# Intel NUC Virtual Device Platform

obj-m += veth-driver.o
obj-m += bridge-driver.o
obj-m += tap-driver.o

# Kernel build directory
KERNELDIR := /lib/modules/$(shell uname -r)/build
PWD := $(shell pwd)

# Module versions
VETH_VERSION := 1.0.0
BRIDGE_VERSION := 1.0.0
TAP_VERSION := 1.0.0

# Compiler flags
ccflags-y := -DDEBUG
ccflags-y += -DVETH_VERSION=\"$(VETH_VERSION)\"
ccflags-y += -DBRIDGE_VERSION=\"$(BRIDGE_VERSION)\"
ccflags-y += -DTAP_VERSION=\"$(TAP_VERSION)\"

# Module parameters
veth-driver-objs := veth-driver.o
bridge-driver-objs := bridge-driver.o
tap-driver-objs := tap-driver.o

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
	rm -f /lib/modules/$(shell uname -r)/kernel/drivers/virtual-net/*.ko
	depmod -a

load: modules
	@echo "Loading Virtual Network Drivers..."
	@modprobe veth-driver || insmod veth-driver.ko
	@modprobe bridge-driver || insmod bridge-driver.ko
	@modprobe tap-driver || insmod tap-driver.ko
	@echo "Drivers loaded successfully"
	@lsmod | grep -E "veth|bridge|tap"

unload:
	@echo "Unloading Virtual Network Drivers..."
	@rmmod veth-driver 2>/dev/null || true
	@rmmod bridge-driver 2>/dev/null || true
	@rmmod tap-driver 2>/dev/null || true
	@echo "Drivers unloaded successfully"

test:
	@echo "Testing Virtual Network Drivers..."
	@./test-scripts/test-veth.sh
	@./test-scripts/test-bridge.sh
	@./test-scripts/test-tap.sh
	@echo "All tests completed"

debug:
	@echo "Debugging Virtual Network Drivers..."
	@dmesg | tail -50
	@echo "---"
	@ip link show
	@echo "---"
	@brctl show

.PHONY: all clean install uninstall load unload test debug
