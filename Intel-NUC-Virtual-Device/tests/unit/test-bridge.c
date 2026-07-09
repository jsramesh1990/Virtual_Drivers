/*
 * test-bridge.c - Unit tests for bridge driver
 *
 * This file contains unit tests for the bridge driver functionality
 * on Intel NUC platforms.
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
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <net/if.h>
#include <linux/if_bridge.h>
#include <linux/if_ether.h>
#include <arpa/inet.h>
#include <netinet/in.h>
#include <signal.h>
#include <time.h>
#include <pthread.h>

/* Colors for output */
#define COLOR_RESET   "\033[0m"
#define COLOR_RED     "\033[31m"
#define COLOR_GREEN   "\033[32m"
#define COLOR_YELLOW  "\033[33m"
#define COLOR_BLUE    "\033[34m"
#define COLOR_MAGENTA "\033[35m"
#define COLOR_CYAN    "\033[36m"

/* Test configuration */
#define TEST_BR_NAME "test-br0"
#define TEST_VETH1 "test-veth1"
#define TEST_VETH2 "test-veth2"
#define TEST_VETH3 "test-veth3"
#define TEST_IP_ADDR "10.0.1.1"
#define TEST_IP1 "10.0.1.2"
#define TEST_IP2 "10.0.1.3"
#define TEST_IP3 "10.0.1.4"
#define TEST_NETMASK "255.255.255.0"
#define TEST_TIMEOUT 5
#define MAX_PORTS 8

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

/* Function to check if interface exists */
int interface_exists(const char *name) {
    char cmd[256];
    snprintf(cmd, sizeof(cmd), "ip link show %s > /dev/null 2>&1", name);
    return run_command(cmd) == 0;
}

/* Function to get bridge ports */
int get_bridge_ports(const char *br_name, char ports[][IFNAMSIZ], int *count) {
    char cmd[256];
    FILE *fp;
    char line[256];
    int i = 0;
    
    snprintf(cmd, sizeof(cmd), "brctl show %s | grep -v 'bridge name' | awk '{print $1}'", br_name);
    fp = popen(cmd, "r");
    if (!fp) {
        return -1;
    }
    
    while (fgets(line, sizeof(line), fp) && i < MAX_PORTS) {
        line[strcspn(line, "\n")] = 0;
        if (strlen(line) > 0) {
            strncpy(ports[i], line, IFNAMSIZ - 1);
            ports[i][IFNAMSIZ - 1] = 0;
            i++;
        }
    }
    
    pclose(fp);
    *count = i;
    return 0;
}

/* ==================== Test Functions ==================== */

/* Test 1: Create bridge */
void test_create_bridge(void) {
    char cmd[256];
    int ret;
    
    printf("\n%s[TEST]%s Creating bridge...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Remove existing bridge */
    run_command("ip link set " TEST_BR_NAME " down 2>/dev/null");
    run_command("brctl delbr " TEST_BR_NAME " 2>/dev/null");
    
    /* Create bridge */
    snprintf(cmd, sizeof(cmd), "ip link add %s type bridge", TEST_BR_NAME);
    ret = run_command(cmd);
    
    if (ret == 0) {
        /* Set bridge up */
        snprintf(cmd, sizeof(cmd), "ip link set %s up", TEST_BR_NAME);
        ret = run_command(cmd);
        
        if (ret == 0) {
            if (interface_exists(TEST_BR_NAME)) {
                print_test_result("Create bridge", 1, 
                                "Bridge created successfully");
            } else {
                print_test_result("Create bridge", 0, 
                                "Bridge not found");
            }
        } else {
            print_test_result("Create bridge", 0, 
                            "Failed to bring bridge up");
        }
    } else {
        print_test_result("Create bridge", 0, 
                        "Failed to create bridge");
    }
    
    /* Cleanup */
    run_command("ip link set " TEST_BR_NAME " down 2>/dev/null");
    run_command("brctl delbr " TEST_BR_NAME " 2>/dev/null");
}

/* Test 2: Add ports to bridge */
void test_add_ports(void) {
    char cmd[256];
    int ret;
    char ports[MAX_PORTS][IFNAMSIZ];
    int count;
    
    printf("\n%s[TEST]%s Adding ports to bridge...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create bridge */
    run_command("ip link add " TEST_BR_NAME " type bridge");
    run_command("ip link set " TEST_BR_NAME " up");
    
    /* Create veth pairs */
    run_command("ip link add " TEST_VETH1 " type veth peer name " TEST_VETH1 "-peer");
    run_command("ip link add " TEST_VETH2 " type veth peer name " TEST_VETH2 "-peer");
    
    /* Add ports to bridge */
    snprintf(cmd, sizeof(cmd), "brctl addif %s %s", TEST_BR_NAME, TEST_VETH1);
    ret = run_command(cmd);
    
    if (ret == 0) {
        snprintf(cmd, sizeof(cmd), "brctl addif %s %s", TEST_BR_NAME, TEST_VETH2);
        ret = run_command(cmd);
        
        if (ret == 0) {
            /* Set ports up */
            run_command("ip link set " TEST_VETH1 " up");
            run_command("ip link set " TEST_VETH2 " up");
            
            /* Check ports */
            if (get_bridge_ports(TEST_BR_NAME, ports, &count) == 0) {
                if (count >= 2) {
                    print_test_result("Add ports to bridge", 1, 
                                    "Ports added successfully");
                } else {
                    print_test_result("Add ports to bridge", 0, 
                                    "Ports not added");
                }
            } else {
                print_test_result("Add ports to bridge", 0, 
                                "Failed to get bridge ports");
            }
        } else {
            print_test_result("Add ports to bridge", 0, 
                            "Failed to add second port");
        }
    } else {
        print_test_result("Add ports to bridge", 0, 
                        "Failed to add first port");
    }
    
    /* Cleanup */
    run_command("ip link delete " TEST_VETH1 " 2>/dev/null");
    run_command("ip link delete " TEST_VETH2 " 2>/dev/null");
    run_command("ip link set " TEST_BR_NAME " down 2>/dev/null");
    run_command("brctl delbr " TEST_BR_NAME " 2>/dev/null");
}

/* Test 3: Bridge IP assignment */
void test_bridge_ip(void) {
    char cmd[256];
    char ip[32];
    int ret;
    
    printf("\n%s[TEST]%s Assigning IP to bridge...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create bridge */
    run_command("ip link add " TEST_BR_NAME " type bridge");
    run_command("ip link set " TEST_BR_NAME " up");
    
    /* Assign IP */
    snprintf(cmd, sizeof(cmd), "ip addr add %s/24 dev %s", TEST_IP_ADDR, TEST_BR_NAME);
    ret = run_command(cmd);
    
    if (ret == 0) {
        /* Get IP */
        snprintf(cmd, sizeof(cmd), 
                "ip addr show %s | grep 'inet ' | awk '{print $2}' | cut -d/ -f1", 
                TEST_BR_NAME);
        FILE *fp = popen(cmd, "r");
        if (fp) {
            if (fgets(ip, sizeof(ip), fp)) {
                ip[strcspn(ip, "\n")] = 0;
                if (strcmp(ip, TEST_IP_ADDR) == 0) {
                    print_test_result("Bridge IP assignment", 1, 
                                    "IP assigned correctly");
                } else {
                    print_test_result("Bridge IP assignment", 0, 
                                    "IP mismatch");
                }
            } else {
                print_test_result("Bridge IP assignment", 0, 
                                "Failed to get IP");
            }
            pclose(fp);
        } else {
            print_test_result("Bridge IP assignment", 0, 
                            "Failed to run command");
        }
    } else {
        print_test_result("Bridge IP assignment", 0, 
                        "Failed to assign IP");
    }
    
    /* Cleanup */
    run_command("ip link set " TEST_BR_NAME " down 2>/dev/null");
    run_command("brctl delbr " TEST_BR_NAME " 2>/dev/null");
}

/* Test 4: Bridge STP */
void test_bridge_stp(void) {
    char cmd[256];
    int ret;
    
    printf("\n%s[TEST]%s Testing STP...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create bridge */
    run_command("ip link add " TEST_BR_NAME " type bridge");
    run_command("ip link set " TEST_BR_NAME " up");
    
    /* Enable STP */
    snprintf(cmd, sizeof(cmd), "brctl stp %s on", TEST_BR_NAME);
    ret = run_command(cmd);
    
    if (ret == 0) {
        /* Check STP status */
        snprintf(cmd, sizeof(cmd), 
                "brctl show %s | grep -q 'STP enabled'", TEST_BR_NAME);
        ret = run_command(cmd);
        
        if (ret == 0) {
            print_test_result("Bridge STP", 1, 
                            "STP enabled successfully");
        } else {
            print_test_result("Bridge STP", 0, 
                            "STP not enabled");
        }
    } else {
        print_test_result("Bridge STP", 0, 
                        "Failed to enable STP");
    }
    
    /* Cleanup */
    run_command("ip link set " TEST_BR_NAME " down 2>/dev/null");
    run_command("brctl delbr " TEST_BR_NAME " 2>/dev/null");
}

/* Test 5: Bridge forwarding */
void test_bridge_forwarding(void) {
    char cmd[256];
    int ret;
    
    printf("\n%s[TEST]%s Testing bridge forwarding...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create bridge */
    run_command("ip link add " TEST_BR_NAME " type bridge");
    run_command("ip link set " TEST_BR_NAME " up");
    
    /* Create veth pairs */
    run_command("ip link add " TEST_VETH1 " type veth peer name " TEST_VETH1 "-peer");
    run_command("ip link add " TEST_VETH2 " type veth peer name " TEST_VETH2 "-peer");
    
    /* Add ports to bridge */
    run_command("brctl addif " TEST_BR_NAME " " TEST_VETH1);
    run_command("brctl addif " TEST_BR_NAME " " TEST_VETH2);
    
    /* Set ports up */
    run_command("ip link set " TEST_VETH1 " up");
    run_command("ip link set " TEST_VETH2 " up");
    
    /* Assign IPs to peers */
    run_command("ip addr add " TEST_IP1 "/24 dev " TEST_VETH1 "-peer");
    run_command("ip addr add " TEST_IP2 "/24 dev " TEST_VETH2 "-peer");
    run_command("ip link set " TEST_VETH1 "-peer up");
    run_command("ip link set " TEST_VETH2 "-peer up");
    
    /* Assign IP to bridge */
    run_command("ip addr add " TEST_IP_ADDR "/24 dev " TEST_BR_NAME);
    
    /* Test connectivity through bridge */
    snprintf(cmd, sizeof(cmd), "ping -c 3 -W %d %s > /dev/null 2>&1", 
             TEST_TIMEOUT, TEST_IP2);
    ret = run_command(cmd);
    
    if (ret == 0) {
        print_test_result("Bridge forwarding", 1, 
                        "Forwarding works");
    } else {
        print_test_result("Bridge forwarding", 0, 
                        "Forwarding failed");
    }
    
    /* Cleanup */
    run_command("ip link delete " TEST_VETH1 " 2>/dev/null");
    run_command("ip link delete " TEST_VETH2 " 2>/dev/null");
    run_command("ip link set " TEST_BR_NAME " down 2>/dev/null");
    run_command("brctl delbr " TEST_BR_NAME " 2>/dev/null");
}

/* Test 6: Bridge VLAN filtering */
void test_bridge_vlan(void) {
    char cmd[256];
    int ret;
    
    printf("\n%s[TEST]%s Testing VLAN filtering...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create bridge with VLAN filtering */
    run_command("ip link add " TEST_BR_NAME " type bridge vlan_filtering 1");
    run_command("ip link set " TEST_BR_NAME " up");
    
    /* Create veth pair */
    run_command("ip link add " TEST_VETH1 " type veth peer name " TEST_VETH1 "-peer");
    run_command("brctl addif " TEST_BR_NAME " " TEST_VETH1);
    run_command("ip link set " TEST_VETH1 " up");
    
    /* Add VLAN */
    snprintf(cmd, sizeof(cmd), 
            "bridge vlan add dev %s vid 10", TEST_VETH1);
    ret = run_command(cmd);
    
    if (ret == 0) {
        /* Check VLAN */
        snprintf(cmd, sizeof(cmd), 
                "bridge vlan show | grep -q '%s.*10'", TEST_VETH1);
        ret = run_command(cmd);
        
        if (ret == 0) {
            print_test_result("Bridge VLAN filtering", 1, 
                            "VLAN added successfully");
        } else {
            print_test_result("Bridge VLAN filtering", 0, 
                            "VLAN not found");
        }
    } else {
        print_test_result("Bridge VLAN filtering", 0, 
                        "Failed to add VLAN");
    }
    
    /* Cleanup */
    run_command("ip link delete " TEST_VETH1 " 2>/dev/null");
    run_command("ip link set " TEST_BR_NAME " down 2>/dev/null");
    run_command("brctl delbr " TEST_BR_NAME " 2>/dev/null");
}

/* Test 7: Bridge performance */
void test_bridge_performance(void) {
    char cmd[256];
    int ret;
    double throughput = 0;
    char output[1024];
    FILE *fp;
    
    printf("\n%s[TEST]%s Testing bridge performance...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create bridge */
    run_command("ip link add " TEST_BR_NAME " type bridge");
    run_command("ip link set " TEST_BR_NAME " up");
    
    /* Create veth pairs */
    run_command("ip link add " TEST_VETH1 " type veth peer name " TEST_VETH1 "-peer");
    run_command("ip link add " TEST_VETH2 " type veth peer name " TEST_VETH2 "-peer");
    
    /* Add ports to bridge */
    run_command("brctl addif " TEST_BR_NAME " " TEST_VETH1);
    run_command("brctl addif " TEST_BR_NAME " " TEST_VETH2);
    
    /* Set ports up */
    run_command("ip link set " TEST_VETH1 " up");
    run_command("ip link set " TEST_VETH2 " up");
    
    /* Assign IPs to peers */
    run_command("ip addr add " TEST_IP1 "/24 dev " TEST_VETH1 "-peer");
    run_command("ip addr add " TEST_IP2 "/24 dev " TEST_VETH2 "-peer");
    run_command("ip link set " TEST_VETH1 "-peer up");
    run_command("ip link set " TEST_VETH2 "-peer up");
    
    /* Assign IP to bridge */
    run_command("ip addr add " TEST_IP_ADDR "/24 dev " TEST_BR_NAME);
    
    /* Run iperf test */
    snprintf(cmd, sizeof(cmd), 
            "iperf3 -c %s -t 3 -i 1 --json 2>/dev/null", TEST_IP2);
    fp = popen(cmd, "r");
    if (fp) {
        while (fgets(output, sizeof(output), fp)) {
            if (strstr(output, "bits_per_second")) {
                char *ptr = strstr(output, "bits_per_second");
                if (ptr) {
                    ptr = strchr(ptr, ':');
                    if (ptr) {
                        ptr++;
                        while (*ptr == ' ') ptr++;
                        throughput = atof(ptr);
                        break;
                    }
                }
            }
        }
        pclose(fp);
        
        if (throughput > 0) {
            double mbps = throughput / 1000000;
            printf("  Throughput: %.2f Mbps\n", mbps);
            if (mbps > 50) {
                print_test_result("Bridge performance", 1, 
                                "Good performance");
            } else {
                print_test_result("Bridge performance", 0, 
                                "Low performance");
            }
        } else {
            print_test_result("Bridge performance", 0, 
                            "Failed to get throughput");
        }
    } else {
        print_test_result("Bridge performance", 0, 
                        "Failed to run iperf");
    }
    
    /* Cleanup */
    run_command("ip link delete " TEST_VETH1 " 2>/dev/null");
    run_command("ip link delete " TEST_VETH2 " 2>/dev/null");
    run_command("ip link set " TEST_BR_NAME " down 2>/dev/null");
    run_command("brctl delbr " TEST_BR_NAME " 2>/dev/null");
}

/* Test 8: Bridge with multiple ports */
void test_bridge_multiport(void) {
    int i;
    char cmd[256];
    char ports[MAX_PORTS][IFNAMSIZ];
    int count;
    int success = 1;
    
    printf("\n%s[TEST]%s Testing bridge with multiple ports...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create bridge */
    run_command("ip link add " TEST_BR_NAME " type bridge");
    run_command("ip link set " TEST_BR_NAME " up");
    
    /* Create and add 4 ports */
    for (i = 1; i <= 4; i++) {
        char veth_name[32];
        snprintf(veth_name, sizeof(veth_name), "test-veth%d", i);
        
        snprintf(cmd, sizeof(cmd), "ip link add %s type veth peer name %s-peer", 
                 veth_name, veth_name);
        run_command(cmd);
        
        snprintf(cmd, sizeof(cmd), "brctl addif %s %s", TEST_BR_NAME, veth_name);
        if (run_command(cmd) != 0) {
            success = 0;
        }
        run_command("ip link set " veth_name " up");
    }
    
    if (success) {
        if (get_bridge_ports(TEST_BR_NAME, ports, &count) == 0 && count >= 4) {
            print_test_result("Bridge multiport", 1, 
                            "All ports added successfully");
        } else {
            print_test_result("Bridge multiport", 0, 
                            "Ports not added correctly");
        }
    } else {
        print_test_result("Bridge multiport", 0, 
                        "Failed to add ports");
    }
    
    /* Cleanup */
    for (i = 1; i <= 4; i++) {
        char veth_name[32];
        snprintf(veth_name, sizeof(veth_name), "test-veth%d", i);
        run_command("ip link delete " veth_name " 2>/dev/null");
    }
    run_command("ip link set " TEST_BR_NAME " down 2>/dev/null");
    run_command("brctl delbr " TEST_BR_NAME " 2>/dev/null");
}

/* ==================== Main Function ==================== */

int main(int argc, char *argv[]) {
    printf("\n%s========================================%s\n", COLOR_CYAN, COLOR_RESET);
    printf("%s   Bridge Driver Unit Tests%s\n", COLOR_CYAN, COLOR_RESET);
    printf("%s========================================%s\n", COLOR_CYAN, COLOR_RESET);
    
    /* Check if running as root */
    if (geteuid() != 0) {
        printf("%s[ERROR]%s These tests must be run as root\n", COLOR_RED, COLOR_RESET);
        return 1;
    }
    
    /* Run tests */
    test_create_bridge();
    test_add_ports();
    test_bridge_ip();
    test_bridge_stp();
    test_bridge_forwarding();
    test_bridge_vlan();
    test_bridge_performance();
    test_bridge_multiport();
    
    /* Print summary */
    printf("\n%s========================================%s\n", COLOR_CYAN, COLOR_RESET);
    printf("%s   Test Summary%s\n", COLOR_CYAN, COLOR_RESET);
    printf("%s========================================%s\n", COLOR_CYAN, COLOR_RESET);
    printf("Total Tests: %d\n", tests_total);
    printf("%sPassed: %d%s\n", COLOR_GREEN, tests_passed, COLOR_RESET);
    printf("%sFailed: %d%s\n", COLOR_RED, tests_failed, COLOR_RESET);
    
    if (tests_failed == 0) {
        printf("\n%s✓ All bridge tests passed!%s\n", COLOR_GREEN, COLOR_RESET);
        return 0;
    } else {
        printf("\n%s✗ Some bridge tests failed%s\n", COLOR_RED, COLOR_RESET);
        return 1;
    }
}
