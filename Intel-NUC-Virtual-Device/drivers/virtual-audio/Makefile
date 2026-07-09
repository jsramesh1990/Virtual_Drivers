# Makefile for Virtual Audio Drivers
# Intel NUC Virtual Device Platform

obj-m += pipewire-module.o
obj-m += alsa-interface.o

# Kernel build directory
KERNELDIR := /lib/modules/$(shell uname -r)/build
PWD := $(shell pwd)

# Module versions
PIPEWIRE_VERSION := 1.0.0
ALSA_VERSION := 1.0.0

# Compiler flags
ccflags-y := -DDEBUG
ccflags-y += -DPIPEWIRE_VERSION=\"$(PIPEWIRE_VERSION)\"
ccflags-y += -DALSA_VERSION=\"$(ALSA_VERSION)\"

# Module objects
pipewire-module-objs := pipewire-module.o
alsa-interface-objs := alsa-interface.o

# Audio subsystem configuration
CONFIG_SND := y
CONFIG_SND_ALOOP := y
CONFIG_SND_DUMMY := y

all: modules

modules:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) modules

clean:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) clean
	rm -f *.o *.ko *.mod.c *.mod .*.cmd Module.symvers modules.order

install:
	$(MAKE) -C $(KERNELDIR) M=$(PWD) modules_install
	depmod -a
	@echo "Audio drivers installed successfully"

uninstall:
	rm -f /lib/modules/$(shell uname -r)/kernel/drivers/virtual-audio/*.ko
	depmod -a
	@echo "Audio drivers uninstalled"

load: modules
	@echo "Loading Virtual Audio Drivers..."
	@modprobe snd-aloop 2>/dev/null || modprobe snd_aloop
	@modprobe snd-dummy 2>/dev/null || modprobe snd_dummy
	@modprobe pipewire-module 2>/dev/null || insmod pipewire-module.ko
	@modprobe alsa-interface 2>/dev/null || insmod alsa-interface.ko
	@echo "Audio drivers loaded successfully"
	@lsmod | grep -E "snd|pipewire|alsa-interface"
	@aplay -l 2>/dev/null || echo "No ALSA devices found"

unload:
	@echo "Unloading Virtual Audio Drivers..."
	@rmmod alsa-interface 2>/dev/null || true
	@rmmod pipewire-module 2>/dev/null || true
	@rmmod snd-dummy 2>/dev/null || true
	@rmmod snd-aloop 2>/dev/null || true
	@echo "Audio drivers unloaded successfully"

test:
	@echo "Testing Virtual Audio Drivers..."
	@./test-scripts/test-pipewire.sh
	@./test-scripts/test-alsa.sh
	@echo "All audio tests completed"

debug:
	@echo "Debugging Virtual Audio Drivers..."
	@dmesg | grep -i "audio\|snd\|pipewire" | tail -30
	@echo "---"
	@aplay -l
	@echo "---"
	@arecord -l
	@echo "---"
	@pactl list short sinks 2>/dev/null || echo "PulseAudio not running"

.PHONY: all clean install uninstall load unload test debug
