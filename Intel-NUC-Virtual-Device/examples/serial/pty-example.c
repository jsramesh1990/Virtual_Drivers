/*
 * pty-example.c - PTY communication example
 * 
 * This example demonstrates pseudo-terminal communication
 * between two virtual serial ports.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <termios.h>
#include <pthread.h>
#include <signal.h>
#include <time.h>

#define BUFFER_SIZE 1024
#define SERIAL_SPEED B115200
#define TEST_DATA "Hello from virtual serial port!\n"

/* Global variables */
static volatile int running = 1;

/* Signal handler */
void signal_handler(int sig) {
    running = 0;
}

/* Open serial port */
int open_serial_port(const char *port) {
    int fd;
    struct termios options;
    
    fd = open(port, O_RDWR | O_NOCTTY | O_NDELAY);
    if (fd < 0) {
        perror("Failed to open serial port");
        return -1;
    }
    
    /* Get current options */
    if (tcgetattr(fd, &options) != 0) {
        perror("Failed to get serial port options");
        close(fd);
        return -1;
    }
    
    /* Set baud rate */
    cfsetispeed(&options, SERIAL_SPEED);
    cfsetospeed(&options, SERIAL_SPEED);
    
    /* Set options */
    options.c_cflag |= (CLOCAL | CREAD);
    options.c_cflag &= ~PARENB;
    options.c_cflag &= ~CSTOPB;
    options.c_cflag &= ~CSIZE;
    options.c_cflag |= CS8;
    options.c_lflag &= ~(ICANON | ECHO | ECHOE | ISIG);
    options.c_iflag &= ~(IXON | IXOFF | IXANY);
    options.c_oflag &= ~OPOST;
    
    /* Set read timeout */
    options.c_cc[VMIN] = 0;
    options.c_cc[VTIME] = 10;
    
    /* Apply options */
    if (tcsetattr(fd, TCSANOW, &options) != 0) {
        perror("Failed to set serial port options");
        close(fd);
        return -1;
    }
    
    return fd;
}

/* Reader thread function */
void *reader_thread(void *arg) {
    int fd = *(int *)arg;
    char buffer[BUFFER_SIZE];
    ssize_t bytes_read;
    
    printf("[Reader] Starting reader thread\n");
    
    while (running) {
        bytes_read = read(fd, buffer, sizeof(buffer) - 1);
        if (bytes_read > 0) {
            buffer[bytes_read] = '\0';
            printf("[Reader] Received: %s", buffer);
        } else if (bytes_read < 0 && errno != EAGAIN) {
            perror("[Reader] Read error");
            break;
        }
        
        usleep(10000); /* 10ms */
    }
    
    printf("[Reader] Reader thread stopping\n");
    return NULL;
}

/* Writer thread function */
void *writer_thread(void *arg) {
    int fd = *(int *)arg;
    char buffer[BUFFER_SIZE];
    ssize_t bytes_written;
    int counter = 0;
    
    printf("[Writer] Starting writer thread\n");
    
    while (running) {
        /* Prepare test data */
        snprintf(buffer, sizeof(buffer), 
                "[Writer] Message #%d: %s", 
                counter++, TEST_DATA);
        
        bytes_written = write(fd, buffer, strlen(buffer));
        if (bytes_written < 0) {
            perror("[Writer] Write error");
            break;
        }
        
        printf("[Writer] Sent: %s", buffer);
        
        /* Wait before next message */
        sleep(2);
    }
    
    printf("[Writer] Writer thread stopping\n");
    return NULL;
}

/* Main function */
int main(int argc, char *argv[]) {
    pthread_t reader, writer;
    int fd1, fd2;
    int ret;
    
    printf("========================================\n");
    printf("PTY Communication Example\n");
    printf("========================================\n\n");
    
    /* Check arguments */
    if (argc < 3) {
        fprintf(stderr, "Usage: %s <port1> <port2>\n", argv[0]);
        fprintf(stderr, "Example: %s /dev/ttyV0 /dev/ttyV1\n", argv[0]);
        return 1;
    }
    
    /* Set signal handler */
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    printf("Opening serial ports...\n");
    
    /* Open first serial port */
    fd1 = open_serial_port(argv[1]);
    if (fd1 < 0) {
        fprintf(stderr, "Failed to open %s\n", argv[1]);
        return 1;
    }
    printf("✓ Opened %s (fd: %d)\n", argv[1], fd1);
    
    /* Open second serial port */
    fd2 = open_serial_port(argv[2]);
    if (fd2 < 0) {
        fprintf(stderr, "Failed to open %s\n", argv[2]);
        close(fd1);
        return 1;
    }
    printf("✓ Opened %s (fd: %d)\n", argv[2], fd2);
    
    printf("\nStarting communication threads...\n");
    
    /* Create reader thread on first port */
    ret = pthread_create(&reader, NULL, reader_thread, &fd1);
    if (ret != 0) {
        perror("Failed to create reader thread");
        close(fd1);
        close(fd2);
        return 1;
    }
    
    /* Create writer thread on second port */
    ret = pthread_create(&writer, NULL, writer_thread, &fd2);
    if (ret != 0) {
        perror("Failed to create writer thread");
        pthread_cancel(reader);
        close(fd1);
        close(fd2);
        return 1;
    }
    
    printf("\nCommunication started!\n");
    printf("Press Ctrl+C to stop\n\n");
    
    /* Wait for threads to finish */
    pthread_join(reader, NULL);
    pthread_join(writer, NULL);
    
    printf("\nCleaning up...\n");
    
    /* Close ports */
    close(fd1);
    close(fd2);
    
    printf("Ports closed\n");
    printf("Program completed\n");
    
    return 0;
}
