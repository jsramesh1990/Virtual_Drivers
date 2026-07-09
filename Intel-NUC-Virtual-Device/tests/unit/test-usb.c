/*
 * test-usb.c - Unit tests for USB driver
 *
 * This file contains unit tests for the USB gadget and redirection
 * driver functionality on Intel NUC platforms.
 *
 * Version: 1.0.0
 * Author: Intel NUC Virtual Device Platform Team
 * License: GPL v2
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <dirent.h>
#include <signal.h>
#include <time.h>
#include <pthread.h>
#include <libusb-1.0/libusb.h>

/* Colors for output */
#define COLOR_RESET   "\033[0m"
#define COLOR_RED     "\033[31m"
#define COLOR_GREEN   "\033[32m"
#define COLOR_YELLOW  "\033[33m"
#define COLOR_BLUE    "\033[34m"
#define COLOR_MAGENTA "\033[35m"
#define COLOR_CYAN    "\033[36m"

/* Test configuration */
#define USB_GADGET_PATH "/sys/kernel/config/usb_gadget"
#define TEST_GADGET_NAME "test-gadget"
#define TEST_VENDOR_ID 0x1d6b
#define TEST_PRODUCT_ID 0x0104
#define TEST_SERIAL "1234567890"
#define TEST_MANUFACTURER "Test Manufacturer"
#define TEST_PRODUCT "Test Gadget"
#define TEST_TIMEOUT 5

/* Test counters */
static int tests_passed = 0;
static int tests_failed = 0;
static int tests_total = 0;

/* Function to print test result */
void print_test_result(const char *name, int passed, const char *message) {
    tests_total++;
    if (passed) {
        tests_passed++;
        printf("%s[PASS]%s %s - %s\n", COLOR_GREEN, COLOR_RESET, name, message);
    } else {
        tests_failed++;
        printf("%s[FAIL]%s %s - %s\n", COLOR_RED, COLOR_RESET, name, message);
    }
}

/* Function to run shell command */
int run_command(const char *cmd) {
    int ret = system(cmd);
    if (ret == -1) {
        printf("Failed to run command: %s\n", cmd);
        return -1;
    }
    return WEXITSTATUS(ret);
}

/* Function to check if directory exists */
int dir_exists(const char *path) {
    struct stat st;
    return stat(path, &st) == 0 && S_ISDIR(st.st_mode);
}

/* Function to check if file exists */
int file_exists(const char *path) {
    struct stat st;
    return stat(path, &st) == 0 && S_ISREG(st.st_mode);
}

/* Function to write to sysfs */
int write_sysfs(const char *path, const char *value) {
    FILE *fp = fopen(path, "w");
    if (!fp) {
        return -1;
    }
    fprintf(fp, "%s", value);
    fclose(fp);
    return 0;
}

/* Function to read from sysfs */
int read_sysfs(const char *path, char *buffer, size_t size) {
    FILE *fp = fopen(path, "r");
    if (!fp) {
        return -1;
    }
    if (fgets(buffer, size, fp) == NULL) {
        fclose(fp);
        return -1;
    }
    buffer[strcspn(buffer, "\n")] = 0;
    fclose(fp);
    return 0;
}

/* ==================== Test Functions ==================== */

/* Test 1: Check USB subsystem */
void test_usb_subsystem(void) {
    printf("\n%s[TEST]%s Checking USB subsystem...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Check if USB devices exist */
    int ret = run_command("lsusb > /dev/null 2>&1");
    if (ret == 0) {
        print_test_result("USB subsystem", 1, 
                        "USB subsystem available");
    } else {
        print_test_result("USB subsystem", 0, 
                        "USB subsystem not available");
    }
}

/* Test 2: Check configfs for USB gadget */
void test_configfs(void) {
    printf("\n%s[TEST]%s Checking configfs...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Check if configfs is mounted */
    if (dir_exists(USB_GADGET_PATH)) {
        print_test_result("Configfs", 1, 
                        "Configfs available");
    } else {
        /* Try to mount configfs */
        run_command("mount -t configfs none /sys/kernel/config 2>/dev/null");
        if (dir_exists(USB_GADGET_PATH)) {
            print_test_result("Configfs", 1, 
                            "Configfs mounted");
        } else {
            print_test_result("Configfs", 0, 
                            "Configfs not available");
        }
    }
}

/* Test 3: Create USB gadget */
void test_create_gadget(void) {
    char path[256];
    int ret;
    
    printf("\n%s[TEST]%s Creating USB gadget...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Remove existing test gadget */
    snprintf(path, sizeof(path), "%s/%s", USB_GADGET_PATH, TEST_GADGET_NAME);
    run_command("rm -rf " path " 2>/dev/null");
    
    /* Create gadget */
    snprintf(path, sizeof(path), "mkdir -p %s/%s", USB_GADGET_PATH, TEST_GADGET_NAME);
    ret = run_command(path);
    
    if (ret == 0) {
        snprintf(path, sizeof(path), "%s/%s", USB_GADGET_PATH, TEST_GADGET_NAME);
        if (dir_exists(path)) {
            print_test_result("Create gadget", 1, 
                            "Gadget created successfully");
        } else {
            print_test_result("Create gadget", 0, 
                            "Gadget not created");
        }
    } else {
        print_test_result("Create gadget", 0, 
                        "Failed to create gadget");
    }
    
    /* Cleanup */
    snprintf(path, sizeof(path), "rm -rf %s/%s", USB_GADGET_PATH, TEST_GADGET_NAME);
    run_command(path);
}

/* Test 4: Configure gadget IDs */
void test_gadget_ids(void) {
    char path[256];
    int ret;
    
    printf("\n%s[TEST]%s Configuring gadget IDs...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create gadget */
    snprintf(path, sizeof(path), "mkdir -p %s/%s", USB_GADGET_PATH, TEST_GADGET_NAME);
    run_command(path);
    
    /* Set vendor ID */
    snprintf(path, sizeof(path), "%s/%s/idVendor", USB_GADGET_PATH, TEST_GADGET_NAME);
    char vendor_str[32];
    snprintf(vendor_str, sizeof(vendor_str), "0x%04x", TEST_VENDOR_ID);
    ret = write_sysfs(path, vendor_str);
    
    if (ret == 0) {
        /* Set product ID */
        snprintf(path, sizeof(path), "%s/%s/idProduct", USB_GADGET_PATH, TEST_GADGET_NAME);
        char product_str[32];
        snprintf(product_str, sizeof(product_str), "0x%04x", TEST_PRODUCT_ID);
        ret = write_sysfs(path, product_str);
        
        if (ret == 0) {
            /* Verify IDs */
            char buffer[32];
            snprintf(path, sizeof(path), "%s/%s/idVendor", USB_GADGET_PATH, TEST_GADGET_NAME);
            if (read_sysfs(path, buffer, sizeof(buffer)) == 0) {
                int vendor = strtol(buffer, NULL, 16);
                if (vendor == TEST_VENDOR_ID) {
                    print_test_result("Gadget IDs", 1, 
                                    "IDs configured correctly");
                } else {
                    print_test_result("Gadget IDs", 0, 
                                    "Vendor ID mismatch");
                }
            } else {
                print_test_result("Gadget IDs", 0, 
                                "Failed to read IDs");
            }
        } else {
            print_test_result("Gadget IDs", 0, 
                            "Failed to set product ID");
        }
    } else {
        print_test_result("Gadget IDs", 0, 
                        "Failed to set vendor ID");
    }
    
    /* Cleanup */
    snprintf(path, sizeof(path), "rm -rf %s/%s", USB_GADGET_PATH, TEST_GADGET_NAME);
    run_command(path);
}

/* Test 5: Add gadget functions */
void test_gadget_functions(void) {
    char path[256];
    int ret;
    const char *functions[] = {"acm", "ecm", "mass_storage", "hid"};
    int i;
    int all_success = 1;
    
    printf("\n%s[TEST]%s Adding gadget functions...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create gadget */
    snprintf(path, sizeof(path), "mkdir -p %s/%s", USB_GADGET_PATH, TEST_GADGET_NAME);
    run_command(path);
    
    /* Add functions */
    for (i = 0; i < 4; i++) {
        snprintf(path, sizeof(path), 
                "mkdir -p %s/%s/functions/%s.usb0", 
                USB_GADGET_PATH, TEST_GADGET_NAME, functions[i]);
        ret = run_command(path);
        if (ret != 0) {
            all_success = 0;
        }
    }
    
    if (all_success) {
        /* Check if functions exist */
        int all_exist = 1;
        for (i = 0; i < 4; i++) {
            snprintf(path, sizeof(path), 
                    "%s/%s/functions/%s.usb0", 
                    USB_GADGET_PATH, TEST_GADGET_NAME, functions[i]);
            if (!dir_exists(path)) {
                all_exist = 0;
            }
        }
        
        if (all_exist) {
            print_test_result("Gadget functions", 1, 
                            "All functions added");
        } else {
            print_test_result("Gadget functions", 0, 
                            "Some functions missing");
        }
    } else {
        print_test_result("Gadget functions", 0, 
                        "Failed to add functions");
    }
    
    /* Cleanup */
    snprintf(path, sizeof(path), "rm -rf %s/%s", USB_GADGET_PATH, TEST_GADGET_NAME);
    run_command(path);
}

/* Test 6: Create gadget configuration */
void test_gadget_config(void) {
    char path[256];
    int ret;
    
    printf("\n%s[TEST]%s Creating gadget configuration...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create gadget */
    snprintf(path, sizeof(path), "mkdir -p %s/%s", USB_GADGET_PATH, TEST_GADGET_NAME);
    run_command(path);
    
    /* Create configuration */
    snprintf(path, sizeof(path), 
            "mkdir -p %s/%s/configs/c.1", 
            USB_GADGET_PATH, TEST_GADGET_NAME);
    ret = run_command(path);
    
    if (ret == 0) {
        /* Set max power */
        snprintf(path, sizeof(path), 
                "echo 500 > %s/%s/configs/c.1/MaxPower", 
                USB_GADGET_PATH, TEST_GADGET_NAME);
        ret = run_command(path);
        
        if (ret == 0) {
            /* Check if config exists */
            snprintf(path, sizeof(path), 
                    "%s/%s/configs/c.1", 
                    USB_GADGET_PATH, TEST_GADGET_NAME);
            if (dir_exists(path)) {
                print_test_result("Gadget configuration", 1, 
                                "Configuration created");
            } else {
                print_test_result("Gadget configuration", 0, 
                                "Configuration not found");
            }
        } else {
            print_test_result("Gadget configuration", 0, 
                            "Failed to set MaxPower");
        }
    } else {
        print_test_result("Gadget configuration", 0, 
                        "Failed to create config");
    }
    
    /* Cleanup */
    snprintf(path, sizeof(path), "rm -rf %s/%s", USB_GADGET_PATH, TEST_GADGET_NAME);
    run_command(path);
}

/* Test 7: Link functions to config */
void test_gadget_link(void) {
    char path[256];
    int ret;
    
    printf("\n%s[TEST]%s Linking functions to config...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create gadget */
    snprintf(path, sizeof(path), "mkdir -p %s/%s", USB_GADGET_PATH, TEST_GADGET_NAME);
    run_command(path);
    
    /* Create function */
    snprintf(path, sizeof(path), 
            "mkdir -p %s/%s/functions/acm.usb0", 
            USB_GADGET_PATH, TEST_GADGET_NAME);
    run_command(path);
    
    /* Create config */
    snprintf(path, sizeof(path), 
            "mkdir -p %s/%s/configs/c.1", 
            USB_GADGET_PATH, TEST_GADGET_NAME);
    run_command(path);
    
    /* Link function to config */
    snprintf(path, sizeof(path), 
            "ln -s %s/%s/functions/acm.usb0 %s/%s/configs/c.1/ 2>/dev/null", 
            USB_GADGET_PATH, TEST_GADGET_NAME,
            USB_GADGET_PATH, TEST_GADGET_NAME);
    ret = run_command(path);
    
    if (ret == 0 || ret == 2) { /* 2 = file exists */
        /* Check link */
        snprintf(path, sizeof(path), 
                "%s/%s/configs/c.1/acm.usb0", 
                USB_GADGET_PATH, TEST_GADGET_NAME);
        if (file_exists(path) || dir_exists(path)) {
            print_test_result("Gadget link", 1, 
                            "Function linked to config");
        } else {
            print_test_result("Gadget link", 0, 
                            "Link not created");
        }
    } else {
        print_test_result("Gadget link", 0, 
                        "Failed to link function");
    }
    
    /* Cleanup */
    snprintf(path, sizeof(path), "rm -rf %s/%s", USB_GADGET_PATH, TEST_GADGET_NAME);
    run_command(path);
}

/* Test 8: Enable gadget (UDC) */
void test_gadget_enable(void) {
    char path[256];
    char udc[64];
    int ret;
    
    printf("\n%s[TEST]%s Enabling gadget...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create gadget and functions */
    snprintf(path, sizeof(path), "mkdir -p %s/%s", USB_GADGET_PATH, TEST_GADGET_NAME);
    run_command(path);
    
    snprintf(path, sizeof(path), "mkdir -p %s/%s/functions/acm.usb0", 
             USB_GADGET_PATH, TEST_GADGET_NAME);
    run_command(path);
    
    snprintf(path, sizeof(path), "mkdir -p %s/%s/configs/c.1", 
             USB_GADGET_PATH, TEST_GADGET_NAME);
    run_command(path);
    
    /* Link function to config */
    snprintf(path, sizeof(path), 
            "ln -s %s/%s/functions/acm.usb0 %s/%s/configs/c.1/ 2>/dev/null", 
            USB_GADGET_PATH, TEST_GADGET_NAME,
            USB_GADGET_PATH, TEST_GADGET_NAME);
    run_command(path);
    
    /* Check for UDC */
    FILE *fp = popen("ls /sys/class/udc/ 2>/dev/null", "r");
    if (fp) {
        if (fgets(udc, sizeof(udc), fp)) {
            udc[strcspn(udc, "\n")] = 0;
            pclose(fp);
            
            /* Enable gadget */
            snprintf(path, sizeof(path), 
                    "echo %s > %s/%s/UDC", 
                    udc, USB_GADGET_PATH, TEST_GADGET_NAME);
            ret = run_command(path);
            
            if (ret == 0) {
                /* Check if enabled */
                snprintf(path, sizeof(path), 
                        "cat %s/%s/UDC", 
                        USB_GADGET_PATH, TEST_GADGET_NAME);
                char buffer[64];
                fp = popen(path, "r");
                if (fp) {
                    if (fgets(buffer, sizeof(buffer), fp)) {
                        buffer[strcspn(buffer, "\n")] = 0;
                        if (strlen(buffer) > 0) {
                            print_test_result("Enable gadget", 1, 
                                            "Gadget enabled");
                        } else {
                            print_test_result("Enable gadget", 0, 
                                            "Gadget not enabled");
                        }
                    } else {
                        print_test_result("Enable gadget", 0, 
                                        "Failed to read UDC");
                    }
                    pclose(fp);
                } else {
                    print_test_result("Enable gadget", 0, 
                                    "Failed to check UDC");
                }
            } else {
                print_test_result("Enable gadget", 0, 
                                "Failed to enable gadget");
            }
        } else {
            pclose(fp);
            print_test_result("Enable gadget", 0, 
                            "No UDC found");
        }
    } else {
        print_test_result("Enable gadget", 0, 
                        "Failed to list UDC");
    }
    
    /* Cleanup */
    snprintf(path, sizeof(path), "echo '' > %s/%s/UDC 2>/dev/null", 
             USB_GADGET_PATH, TEST_GADGET_NAME);
    run_command(path);
    snprintf(path, sizeof(path), "rm -rf %s/%s", USB_GADGET_PATH, TEST_GADGET_NAME);
    run_command(path);
}

/* Test 9: USB redirection */
void test_usb_redirect(void) {
    printf("\n%s[TEST]%s Testing USB redirection...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Check if usbip is installed */
    int ret = run_command("which usbip > /dev/null 2>&1");
    if (ret == 0) {
        /* Check usbipd */
        ret = run_command("pgrep usbipd > /dev/null 2>&1");
        if (ret == 0) {
            print_test_result("USB redirection", 1, 
                            "USB/IP running");
        } else {
            /* Try to start usbipd */
            run_command("usbipd -D 2>/dev/null");
            ret = run_command("pgrep usbipd > /dev/null 2>&1");
            if (ret == 0) {
                print_test_result("USB redirection", 1, 
                                "USB/IP started");
            } else {
                print_test_result("USB redirection", 0, 
                                "USB/IP not running");
            }
        }
    } else {
        print_test_result("USB redirection", 0, 
                        "usbip not installed");
    }
}

/* Test 10: USB device enumeration */
void test_usb_enumeration(void) {
    printf("\n%s[TEST]%s Testing USB enumeration...\n", COLOR_BLUE, COLOR_RESET);
    
    libusb_context *ctx = NULL;
    libusb_device **list = NULL;
    ssize_t count;
    int ret;
    
    /* Initialize libusb */
    ret = libusb_init(&ctx);
    if (ret < 0) {
        print_test_result("USB enumeration", 0, 
                        "Failed to initialize libusb");
        return;
    }
    
    /* Get device list */
    count = libusb_get_device_list(ctx, &list);
    if (count < 0) {
        print_test_result("USB enumeration", 0, 
                        "Failed to get device list");
        libusb_exit(ctx);
        return;
    }
    
    if (count > 0) {
        print_test_result("USB enumeration", 1, 
                        "Found USB devices");
        printf("  Number of devices: %ld\n", count);
        
        /* Print device info */
        for (ssize_t i = 0; i < count && i < 5; i++) {
            struct libusb_device_descriptor desc;
            libusb_get_device_descriptor(list[i], &desc);
            printf("  Device %ld: %04x:%04x\n", 
                   i, desc.idVendor, desc.idProduct);
        }
    } else {
        print_test_result("USB enumeration", 0, 
                        "No USB devices found");
    }
    
    libusb_free_device_list(list, 1);
    libusb_exit(ctx);
}

/* ==================== Main Function ==================== */

int main(int argc, char *argv[]) {
    printf("\n%s========================================%s\n", COLOR_CYAN, COLOR_RESET);
    printf("%s   USB Driver Unit Tests%s\n", COLOR_CYAN, COLOR_RESET);
    printf("%s========================================%s\n", COLOR_CYAN, COLOR_RESET);
    
    /* Check if running as root */
    if (geteuid() != 0) {
        printf("%s[ERROR]%s These tests must be run as root\n", COLOR_RED, COLOR_RESET);
        return 1;
    }
    
    /* Initialize libusb */
    libusb_init(NULL);
    
    /* Run tests */
    test_usb_subsystem();
    test_configfs();
    test_create_gadget();
    test_gadget_ids();
    test_gadget_functions();
    test_gadget_config();
    test_gadget_link();
    test_gadget_enable();
    test_usb_redirect();
    test_usb_enumeration();
    
    /* Print summary */
    printf("\n%s========================================%s\n", COLOR_CYAN, COLOR_RESET);
    printf("%s   Test Summary%s\n", COLOR_CYAN, COLOR_RESET);
    printf("%s========================================%s\n", COLOR_CYAN, COLOR_RESET);
    printf("Total Tests: %d\n", tests_total);
    printf("%sPassed: %d%s\n", COLOR_GREEN, tests_passed, COLOR_RESET);
    printf("%sFailed: %d%s\n", COLOR_RED, tests_failed, COLOR_RESET);
    
    if (tests_failed == 0) {
        printf("\n%s✓ All USB tests passed!%s\n", COLOR_GREEN, COLOR_RESET);
        return 0;
    } else {
        printf("\n%s✗ Some USB tests failed%s\n", COLOR_RED, COLOR_RESET);
        return 1;
    }
}
