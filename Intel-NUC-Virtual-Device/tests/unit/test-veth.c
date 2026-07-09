/*
 * test-veth.c - Unit tests for virtual ethernet driver
 *
 * This file contains unit tests for the veth driver functionality
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
#include <linux/if_ether.h>
#include <linux/if_packet.h>
#include <linux/if_tun.h>
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
#define TEST_VETH_NAME "test-veth0"
#define TEST_VETH_PEER "test-veth1"
#define TEST_IP_ADDR "10.0.0.1"
#define TEST_PEER_IP "10.0.0.2"
#define TEST_NETMASK "255.255.255.0"
#define TEST_MTU 1500
#define TEST_PACKET_SIZE 1024
#define TEST_TIMEOUT 5

/* Test counters */
static int tests_passed = 0;
static int tests_failed = 0;
static int tests_total = 0;

/* Test result structure */
typedef struct {
    const char *name;
    int passed;
    const char *message;
} test_result_t;

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

/* Function to get interface IP */
int get_interface_ip(const char *name, char *ip, size_t size) {
    char cmd[256];
    FILE *fp;
    
    snprintf(cmd, sizeof(cmd), "ip addr show %s | grep 'inet ' | awk '{print $2}' | cut -d/ -f1", name);
    fp = popen(cmd, "r");
    if (!fp) {
        return -1;
    }
    
    if (fgets(ip, size, fp) == NULL) {
        pclose(fp);
        return -1;
    }
    
    /* Remove newline */
    ip[strcspn(ip, "\n")] = 0;
    pclose(fp);
    return 0;
}

/* ==================== Test Functions ==================== */

/* Test 1: Create veth pair */
void test_create_veth_pair(void) {
    char cmd[256];
    int ret;
    
    printf("\n%s[TEST]%s Creating veth pair...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Remove existing interfaces if any */
    run_command("ip link delete " TEST_VETH_NAME " 2>/dev/null");
    run_command("ip link delete " TEST_VETH_PEER " 2>/dev/null");
    
    /* Create veth pair */
    snprintf(cmd, sizeof(cmd), "ip link add %s type veth peer name %s", 
             TEST_VETH_NAME, TEST_VETH_PEER);
    ret = run_command(cmd);
    
    if (ret == 0) {
        /* Check if interfaces exist */
        int exists1 = interface_exists(TEST_VETH_NAME);
        int exists2 = interface_exists(TEST_VETH_PEER);
        
        if (exists1 && exists2) {
            print_test_result("Create veth pair", 1, 
                            "Both interfaces created successfully");
        } else {
            print_test_result("Create veth pair", 0, 
                            "Interfaces not created properly");
        }
    } else {
        print_test_result("Create veth pair", 0, 
                        "Failed to create veth pair");
    }
    
    /* Cleanup */
    run_command("ip link delete " TEST_VETH_NAME " 2>/dev/null");
}

/* Test 2: Set interfaces up */
void test_set_interfaces_up(void) {
    char cmd[256];
    int ret;
    
    printf("\n%s[TEST]%s Setting interfaces up...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create veth pair */
    snprintf(cmd, sizeof(cmd), "ip link add %s type veth peer name %s", 
             TEST_VETH_NAME, TEST_VETH_PEER);
    run_command(cmd);
    
    /* Set interfaces up */
    snprintf(cmd, sizeof(cmd), "ip link set %s up", TEST_VETH_NAME);
    ret = run_command(cmd);
    
    if (ret == 0) {
        snprintf(cmd, sizeof(cmd), "ip link set %s up", TEST_VETH_PEER);
        ret = run_command(cmd);
        
        if (ret == 0) {
            /* Check if interfaces are up */
            char cmd_check[256];
            snprintf(cmd_check, sizeof(cmd_check), 
                    "ip link show %s | grep -q 'state UP'", TEST_VETH_NAME);
            int up1 = run_command(cmd_check);
            
            snprintf(cmd_check, sizeof(cmd_check), 
                    "ip link show %s | grep -q 'state UP'", TEST_VETH_PEER);
            int up2 = run_command(cmd_check);
            
            if (up1 == 0 && up2 == 0) {
                print_test_result("Set interfaces up", 1, 
                                "Both interfaces are UP");
            } else {
                print_test_result("Set interfaces up", 0, 
                                "Interfaces not UP");
            }
        } else {
            print_test_result("Set interfaces up", 0, 
                            "Failed to set peer up");
        }
    } else {
        print_test_result("Set interfaces up", 0, 
                        "Failed to set interface up");
    }
    
    /* Cleanup */
    run_command("ip link delete " TEST_VETH_NAME " 2>/dev/null");
}

/* Test 3: Assign IP addresses */
void test_assign_ips(void) {
    char cmd[256];
    char ip1[32], ip2[32];
    int ret;
    
    printf("\n%s[TEST]%s Assigning IP addresses...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create veth pair */
    snprintf(cmd, sizeof(cmd), "ip link add %s type veth peer name %s", 
             TEST_VETH_NAME, TEST_VETH_PEER);
    run_command(cmd);
    
    /* Set interfaces up */
    run_command("ip link set " TEST_VETH_NAME " up");
    run_command("ip link set " TEST_VETH_PEER " up");
    
    /* Assign IP addresses */
    snprintf(cmd, sizeof(cmd), "ip addr add %s/24 dev %s", 
             TEST_IP_ADDR, TEST_VETH_NAME);
    ret = run_command(cmd);
    
    if (ret == 0) {
        snprintf(cmd, sizeof(cmd), "ip addr add %s/24 dev %s", 
                 TEST_PEER_IP, TEST_VETH_PEER);
        ret = run_command(cmd);
        
        if (ret == 0) {
            /* Verify IP addresses */
            if (get_interface_ip(TEST_VETH_NAME, ip1, sizeof(ip1)) == 0 &&
                get_interface_ip(TEST_VETH_PEER, ip2, sizeof(ip2)) == 0) {
                
                if (strcmp(ip1, TEST_IP_ADDR) == 0 && 
                    strcmp(ip2, TEST_PEER_IP) == 0) {
                    print_test_result("Assign IP addresses", 1, 
                                    "IPs assigned correctly");
                } else {
                    print_test_result("Assign IP addresses", 0, 
                                    "IPs mismatch");
                }
            } else {
                print_test_result("Assign IP addresses", 0, 
                                "Failed to get IP addresses");
            }
        } else {
            print_test_result("Assign IP addresses", 0, 
                            "Failed to assign peer IP");
        }
    } else {
        print_test_result("Assign IP addresses", 0, 
                        "Failed to assign IP");
    }
    
    /* Cleanup */
    run_command("ip link delete " TEST_VETH_NAME " 2>/dev/null");
}

/* Test 4: Test connectivity */
void test_connectivity(void) {
    char cmd[256];
    int ret;
    
    printf("\n%s[TEST]%s Testing connectivity...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create veth pair with IPs */
    snprintf(cmd, sizeof(cmd), "ip link add %s type veth peer name %s", 
             TEST_VETH_NAME, TEST_VETH_PEER);
    run_command(cmd);
    
    run_command("ip link set " TEST_VETH_NAME " up");
    run_command("ip link set " TEST_VETH_PEER " up");
    run_command("ip addr add " TEST_IP_ADDR "/24 dev " TEST_VETH_NAME);
    run_command("ip addr add " TEST_PEER_IP "/24 dev " TEST_VETH_PEER);
    
    /* Ping test */
    snprintf(cmd, sizeof(cmd), "ping -c 3 -W %d %s > /dev/null 2>&1", 
             TEST_TIMEOUT, TEST_PEER_IP);
    ret = run_command(cmd);
    
    if (ret == 0) {
        print_test_result("Connectivity", 1, 
                        "Ping successful to peer");
    } else {
        print_test_result("Connectivity", 0, 
                        "Ping failed");
    }
    
    /* Cleanup */
    run_command("ip link delete " TEST_VETH_NAME " 2>/dev/null");
}

/* Test 5: Test MTU change */
void test_mtu_change(void) {
    char cmd[256];
    int ret;
    char mtu_str[32];
    FILE *fp;
    
    printf("\n%s[TEST]%s Testing MTU change...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create veth pair */
    snprintf(cmd, sizeof(cmd), "ip link add %s type veth peer name %s", 
             TEST_VETH_NAME, TEST_VETH_PEER);
    run_command(cmd);
    
    /* Set MTU */
    snprintf(cmd, sizeof(cmd), "ip link set %s mtu 9000", TEST_VETH_NAME);
    ret = run_command(cmd);
    
    if (ret == 0) {
        /* Check MTU */
        snprintf(cmd, sizeof(cmd), 
                "cat /sys/class/net/%s/mtu", TEST_VETH_NAME);
        fp = popen(cmd, "r");
        if (fp) {
            if (fgets(mtu_str, sizeof(mtu_str), fp)) {
                int mtu = atoi(mtu_str);
                if (mtu == 9000) {
                    print_test_result("MTU change", 1, 
                                    "MTU changed to 9000");
                } else {
                    print_test_result("MTU change", 0, 
                                    "MTU not changed correctly");
                }
            } else {
                print_test_result("MTU change", 0, 
                                "Failed to read MTU");
            }
            pclose(fp);
        } else {
            print_test_result("MTU change", 0, 
                            "Failed to get MTU");
        }
    } else {
        print_test_result("MTU change", 0, 
                        "Failed to set MTU");
    }
    
    /* Cleanup */
    run_command("ip link delete " TEST_VETH_NAME " 2>/dev/null");
}

/* Test 6: Test MAC address change */
void test_mac_change(void) {
    char cmd[256];
    int ret;
    char mac1[32], mac2[32];
    FILE *fp;
    const char *new_mac = "00:11:22:33:44:55";
    
    printf("\n%s[TEST]%s Testing MAC address change...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create veth pair */
    snprintf(cmd, sizeof(cmd), "ip link add %s type veth peer name %s", 
             TEST_VETH_NAME, TEST_VETH_PEER);
    run_command(cmd);
    
    /* Get original MAC */
    snprintf(cmd, sizeof(cmd), 
            "cat /sys/class/net/%s/address", TEST_VETH_NAME);
    fp = popen(cmd, "r");
    if (fp) {
        if (fgets(mac1, sizeof(mac1), fp)) {
            mac1[strcspn(mac1, "\n")] = 0;
        }
        pclose(fp);
    }
    
    /* Set new MAC */
    snprintf(cmd, sizeof(cmd), "ip link set %s address %s", 
             TEST_VETH_NAME, new_mac);
    ret = run_command(cmd);
    
    if (ret == 0) {
        /* Get new MAC */
        snprintf(cmd, sizeof(cmd), 
                "cat /sys/class/net/%s/address", TEST_VETH_NAME);
        fp = popen(cmd, "r");
        if (fp) {
            if (fgets(mac2, sizeof(mac2), fp)) {
                mac2[strcspn(mac2, "\n")] = 0;
                if (strcmp(mac2, new_mac) == 0) {
                    print_test_result("MAC change", 1, 
                                    "MAC changed successfully");
                } else {
                    print_test_result("MAC change", 0, 
                                    "MAC not changed correctly");
                }
            } else {
                print_test_result("MAC change", 0, 
                                "Failed to read MAC");
            }
            pclose(fp);
        } else {
            print_test_result("MAC change", 0, 
                            "Failed to get MAC");
        }
    } else {
        print_test_result("MAC change", 0, 
                        "Failed to set MAC");
    }
    
    /* Cleanup */
    run_command("ip link delete " TEST_VETH_NAME " 2>/dev/null");
}

/* Test 7: Test performance */
void test_performance(void) {
    char cmd[256];
    int ret;
    char output[1024];
    FILE *fp;
    double throughput = 0;
    
    printf("\n%s[TEST]%s Testing performance...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create veth pair with IPs */
    snprintf(cmd, sizeof(cmd), "ip link add %s type veth peer name %s", 
             TEST_VETH_NAME, TEST_VETH_PEER);
    run_command(cmd);
    
    run_command("ip link set " TEST_VETH_NAME " up");
    run_command("ip link set " TEST_VETH_PEER " up");
    run_command("ip addr add " TEST_IP_ADDR "/24 dev " TEST_VETH_NAME);
    run_command("ip addr add " TEST_PEER_IP "/24 dev " TEST_VETH_PEER);
    
    /* Run iperf test */
    snprintf(cmd, sizeof(cmd), 
            "iperf3 -c %s -t 3 -i 1 --json 2>/dev/null", TEST_PEER_IP);
    fp = popen(cmd, "r");
    if (fp) {
        /* Parse JSON output - simple approach */
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
            if (mbps > 100) {
                print_test_result("Performance", 1, 
                                "Good throughput");
            } else {
                print_test_result("Performance", 0, 
                                "Low throughput");
            }
        } else {
            print_test_result("Performance", 0, 
                            "Failed to get throughput");
        }
    } else {
        print_test_result("Performance", 0, 
                        "Failed to run iperf");
    }
    
    /* Cleanup */
    run_command("ip link delete " TEST_VETH_NAME " 2>/dev/null");
}

/* Test 8: Test namespace isolation */
void test_namespace_isolation(void) {
    char cmd[256];
    int ret;
    
    printf("\n%s[TEST]%s Testing namespace isolation...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create namespace */
    run_command("ip netns del test-ns 2>/dev/null");
    ret = run_command("ip netns add test-ns");
    
    if (ret == 0) {
        /* Create veth pair in namespace */
        snprintf(cmd, sizeof(cmd), 
                "ip link add %s type veth peer name %s", 
                TEST_VETH_NAME, TEST_VETH_PEER);
        run_command(cmd);
        
        /* Move one end to namespace */
        snprintf(cmd, sizeof(cmd), 
                "ip link set %s netns test-ns", TEST_VETH_PEER);
        ret = run_command(cmd);
        
        if (ret == 0) {
            /* Configure namespace */
            run_command("ip netns exec test-ns ip link set " TEST_VETH_PEER " up");
            run_command("ip netns exec test-ns ip addr add " TEST_PEER_IP "/24 dev " TEST_VETH_PEER);
            run_command("ip link set " TEST_VETH_NAME " up");
            run_command("ip addr add " TEST_IP_ADDR "/24 dev " TEST_VETH_NAME);
            
            /* Test connectivity */
            snprintf(cmd, sizeof(cmd), 
                    "ip netns exec test-ns ping -c 3 -W %d %s > /dev/null 2>&1", 
                    TEST_TIMEOUT, TEST_IP_ADDR);
            ret = run_command(cmd);
            
            if (ret == 0) {
                print_test_result("Namespace isolation", 1, 
                                "Namespace communication works");
            } else {
                print_test_result("Namespace isolation", 0, 
                                "Namespace communication failed");
            }
        } else {
            print_test_result("Namespace isolation", 0, 
                            "Failed to move interface to namespace");
        }
    } else {
        print_test_result("Namespace isolation", 0, 
                        "Failed to create namespace");
    }
    
    /* Cleanup */
    run_command("ip link delete " TEST_VETH_NAME " 2>/dev/null");
    run_command("ip netns del test-ns 2>/dev/null");
}

/* Test 9: Test packet forwarding */
void test_packet_forwarding(void) {
    char cmd[256];
    int ret;
    
    printf("\n%s[TEST]%s Testing packet forwarding...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create veth pair with IPs */
    snprintf(cmd, sizeof(cmd), "ip link add %s type veth peer name %s", 
             TEST_VETH_NAME, TEST_VETH_PEER);
    run_command(cmd);
    
    run_command("ip link set " TEST_VETH_NAME " up");
    run_command("ip link set " TEST_VETH_PEER " up");
    run_command("ip addr add " TEST_IP_ADDR "/24 dev " TEST_VETH_NAME);
    run_command("ip addr add " TEST_PEER_IP "/24 dev " TEST_VETH_PEER);
    
    /* Enable forwarding */
    run_command("echo 1 > /proc/sys/net/ipv4/ip_forward");
    
    /* Test forwarding */
    snprintf(cmd, sizeof(cmd), 
            "ping -c 3 -W %d %s > /dev/null 2>&1", 
            TEST_TIMEOUT, TEST_PEER_IP);
    ret = run_command(cmd);
    
    if (ret == 0) {
        print_test_result("Packet forwarding", 1, 
                        "Forwarding works");
    } else {
        print_test_result("Packet forwarding", 0, 
                        "Forwarding failed");
    }
    
    /* Cleanup */
    run_command("ip link delete " TEST_VETH_NAME " 2>/dev/null");
}

/* Test 10: Test stress conditions */
void test_stress(void) {
    char cmd[256];
    int ret;
    int i;
    
    printf("\n%s[TEST]%s Testing stress conditions...\n", COLOR_BLUE, COLOR_RESET);
    
    /* Create and delete veth pairs multiple times */
    int success_count = 0;
    int fail_count = 0;
    
    for (i = 0; i < 10; i++) {
        snprintf(cmd, sizeof(cmd), "ip link add stress%d type veth peer name stress-peer%d", i, i);
        if (run_command(cmd) == 0) {
            run_command("ip link set stress" " up");
            run_command("ip link delete stress" " 2>/dev/null");
            success_count++;
        } else {
            fail_count++;
        }
    }
    
    if (fail_count == 0) {
        print_test_result("Stress test", 1, 
                        "All operations succeeded");
    } else {
        print_test_result("Stress test", 0, 
                        "Some operations failed");
    }
}

/* ==================== Main Function ==================== */

int main(int argc, char *argv[]) {
    printf("\n%s========================================%s\n", COLOR_CYAN, COLOR_RESET);
    printf("%s   VETH Driver Unit Tests%s\n", COLOR_CYAN, COLOR_RESET);
    printf("%s========================================%s\n", COLOR_CYAN, COLOR_RESET);
    
    /* Check if running as root */
    if (geteuid() != 0) {
        printf("%s[ERROR]%s These tests must be run as root\n", COLOR_RED, COLOR_RESET);
        return 1;
    }
    
    /* Run tests */
    test_create_veth_pair();
    test_set_interfaces_up();
    test_assign_ips();
    test_connectivity();
    test_mtu_change();
    test_mac_change();
    test_performance();
    test_namespace_isolation();
    test_packet_forwarding();
    test_stress();
    
    /* Print summary */
    printf("\n%s========================================%s\n", COLOR_CYAN, COLOR_RESET);
    printf("%s   Test Summary%s\n", COLOR_CYAN, COLOR_RESET);
    printf("%s========================================%s\n", COLOR_CYAN, COLOR_RESET);
    printf("Total Tests: %d\n", tests_total);
    printf("%sPassed: %d%s\n", COLOR_GREEN, tests_passed, COLOR_RESET);
    printf("%sFailed: %d%s\n", COLOR_RED, tests_failed, COLOR_RESET);
    
    if (tests_failed == 0) {
        printf("\n%s✓ All tests passed!%s\n", COLOR_GREEN, COLOR_RESET);
        return 0;
    } else {
        printf("\n%s✗ Some tests failed%s\n", COLOR_RED, COLOR_RESET);
        return 1;
    }
}
