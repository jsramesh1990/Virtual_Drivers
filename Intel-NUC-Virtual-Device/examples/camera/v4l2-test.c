/*
 * v4l2-test.c - V4L2 Virtual Camera Test Application
 * 
 * This application tests V4L2 virtual camera devices by capturing
 * and displaying video frames on Intel NUC platforms.
 * 
 * Version: 1.0.0
 * Author: Intel NUC Virtual Device Platform Team
 * License: GPL v2
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/select.h>
#include <sys/time.h>
#include <sys/types.h>
#include <linux/videodev2.h>
#include <linux/v4l2-subdev.h>
#include <libv4l2.h>
#include <signal.h>
#include <time.h>

#define CLEAR(x) memset(&(x), 0, sizeof(x))
#define MAX_BUFFERS 4
#define DEFAULT_DEVICE "/dev/video0"
#define DEFAULT_WIDTH 640
#define DEFAULT_HEIGHT 480
#define DEFAULT_FPS 30

/* Colors for output */
#define COLOR_RESET   "\033[0m"
#define COLOR_RED     "\033[31m"
#define COLOR_GREEN   "\033[32m"
#define COLOR_YELLOW  "\033[33m"
#define COLOR_BLUE    "\033[34m"
#define COLOR_MAGENTA "\033[35m"
#define COLOR_CYAN    "\033[36m"

/* Global variables */
static int running = 1;
static int fd = -1;
static struct v4l2_buffer *buffers;
static unsigned int n_buffers = 0;
static unsigned int frame_count = 0;
static struct timeval start_time;

/* Signal handler */
void signal_handler(int sig) {
    printf("\n%s[INFO]%s Stopping capture...\n", COLOR_YELLOW, COLOR_RESET);
    running = 0;
}

/* Error handling function */
static void errno_exit(const char *s) {
    fprintf(stderr, "%s[ERROR]%s %s: %s\n", 
            COLOR_RED, COLOR_RESET, s, strerror(errno));
    exit(EXIT_FAILURE);
}

/* Helper function for ioctl with retry */
static int xioctl(int fd, int request, void *arg) {
    int r;
    
    do {
        r = v4l2_ioctl(fd, request, arg);
    } while (r == -1 && errno == EINTR);
    
    return r;
}

/* Print V4L2 capabilities */
static void print_capabilities(struct v4l2_capability *cap) {
    printf("%s[INFO]%s V4L2 Device Capabilities:\n", COLOR_CYAN, COLOR_RESET);
    printf("  Driver: %s\n", cap->driver);
    printf("  Card: %s\n", cap->card);
    printf("  Bus: %s\n", cap->bus_info);
    printf("  Version: %u.%u.%u\n",
           (cap->version >> 16) & 0xFF,
           (cap->version >> 8) & 0xFF,
           cap->version & 0xFF);
    printf("  Capabilities: 0x%08x\n", cap->capabilities);
    
    if (cap->capabilities & V4L2_CAP_VIDEO_CAPTURE)
        printf("    ✓ Video Capture\n");
    if (cap->capabilities & V4L2_CAP_VIDEO_OUTPUT)
        printf("    ✓ Video Output\n");
    if (cap->capabilities & V4L2_CAP_VIDEO_OVERLAY)
        printf("    ✓ Video Overlay\n");
    if (cap->capabilities & V4L2_CAP_VBI_CAPTURE)
        printf("    ✓ VBI Capture\n");
    if (cap->capabilities & V4L2_CAP_STREAMING)
        printf("    ✓ Streaming\n");
    if (cap->capabilities & V4L2_CAP_READWRITE)
        printf("    ✓ Read/Write\n");
    if (cap->capabilities & V4L2_CAP_EXT_PIX_FORMAT)
        printf("    ✓ Extended Pixel Format\n");
}

/* Print supported formats */
static void print_supported_formats(int fd) {
    struct v4l2_fmtdesc fmtdesc;
    struct v4l2_frmsizeenum frmsize;
    int i, j;
    
    printf("\n%s[INFO]%s Supported Formats:\n", COLOR_CYAN, COLOR_RESET);
    
    CLEAR(fmtdesc);
    fmtdesc.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    
    for (i = 0; ; i++) {
        fmtdesc.index = i;
        if (xioctl(fd, VIDIOC_ENUM_FMT, &fmtdesc) < 0)
            break;
        
        printf("  %2d: %s (0x%08x) - %s\n",
               i, fmtdesc.description, fmtdesc.pixelformat,
               fmtdesc.flags & V4L2_FMT_FLAG_COMPRESSED ? "Compressed" : "Raw");
        
        /* Print supported resolutions */
        CLEAR(frmsize);
        frmsize.pixel_format = fmtdesc.pixelformat;
        
        for (j = 0; ; j++) {
            frmsize.index = j;
            if (xioctl(fd, VIDIOC_ENUM_FRAMESIZES, &frmsize) < 0)
                break;
            
            if (frmsize.type == V4L2_FRMSIZE_TYPE_DISCRETE) {
                printf("    - %dx%d\n",
                       frmsize.discrete.width,
                       frmsize.discrete.height);
            } else if (frmsize.type == V4L2_FRMSIZE_TYPE_STEPWISE) {
                printf("    - %dx%d to %dx%d step %dx%d\n",
                       frmsize.stepwise.min_width,
                       frmsize.stepwise.min_height,
                       frmsize.stepwise.max_width,
                       frmsize.stepwise.max_height,
                       frmsize.stepwise.step_width,
                       frmsize.stepwise.step_height);
                break;
            }
        }
    }
}

/* Initialize device */
static int init_device(int width, int height, int format, int fps) {
    struct v4l2_capability cap;
    struct v4l2_format fmt;
    struct v4l2_frmivalenum frmival;
    struct v4l2_streamparm parm;
    int ret;
    
    /* Get capabilities */
    CLEAR(cap);
    ret = xioctl(fd, VIDIOC_QUERYCAP, &cap);
    if (ret < 0) {
        if (errno == EINVAL) {
            fprintf(stderr, "%s[ERROR]%s Not a V4L2 device\n", 
                    COLOR_RED, COLOR_RESET);
            return -1;
        }
        errno_exit("VIDIOC_QUERYCAP");
    }
    
    /* Check capabilities */
    if (!(cap.capabilities & V4L2_CAP_VIDEO_CAPTURE)) {
        fprintf(stderr, "%s[ERROR]%s Device does not support video capture\n",
                COLOR_RED, COLOR_RESET);
        return -1;
    }
    
    if (!(cap.capabilities & V4L2_CAP_STREAMING)) {
        fprintf(stderr, "%s[ERROR]%s Device does not support streaming I/O\n",
                COLOR_RED, COLOR_RESET);
        return -1;
    }
    
    /* Print capabilities */
    print_capabilities(&cap);
    
    /* Print supported formats */
    print_supported_formats(fd);
    
    /* Set format */
    CLEAR(fmt);
    fmt.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    fmt.fmt.pix.width = width;
    fmt.fmt.pix.height = height;
    fmt.fmt.pix.pixelformat = format;
    fmt.fmt.pix.field = V4L2_FIELD_INTERLACED;
    
    ret = xioctl(fd, VIDIOC_S_FMT, &fmt);
    if (ret < 0) {
        fprintf(stderr, "%s[ERROR]%s Failed to set format: %s\n",
                COLOR_RED, COLOR_RESET, strerror(errno));
        return -1;
    }
    
    printf("\n%s[INFO]%s Format set to: %dx%d, format: 0x%08x\n",
           COLOR_GREEN, COLOR_RESET,
           fmt.fmt.pix.width, fmt.fmt.pix.height,
           fmt.fmt.pix.pixelformat);
    
    /* Set frame rate */
    CLEAR(parm);
    parm.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    parm.parm.capture.timeperframe.numerator = 1;
    parm.parm.capture.timeperframe.denominator = fps;
    
    ret = xioctl(fd, VIDIOC_S_PARM, &parm);
    if (ret < 0) {
        fprintf(stderr, "%s[WARN]%s Failed to set frame rate: %s\n",
                COLOR_YELLOW, COLOR_RESET, strerror(errno));
        /* Continue anyway */
    } else {
        printf("%s[INFO]%s Frame rate set to: %d/%d fps\n",
               COLOR_GREEN, COLOR_RESET,
               parm.parm.capture.timeperframe.denominator /
               parm.parm.capture.timeperframe.numerator);
    }
    
    return 0;
}

/* Initialize memory mapped I/O */
static int init_mmap(void) {
    struct v4l2_requestbuffers reqbuf;
    struct v4l2_buffer buf;
    int i;
    
    CLEAR(reqbuf);
    reqbuf.count = MAX_BUFFERS;
    reqbuf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    reqbuf.memory = V4L2_MEMORY_MMAP;
    
    if (xioctl(fd, VIDIOC_REQBUFS, &reqbuf) < 0) {
        if (errno == EINVAL) {
            fprintf(stderr, "%s[ERROR]%s Device does not support memory mapping\n",
                    COLOR_RED, COLOR_RESET);
            return -1;
        }
        errno_exit("VIDIOC_REQBUFS");
    }
    
    if (reqbuf.count < 2) {
        fprintf(stderr, "%s[ERROR]%s Insufficient buffer memory\n",
                COLOR_RED, COLOR_RESET);
        return -1;
    }
    
    buffers = calloc(reqbuf.count, sizeof(struct v4l2_buffer));
    if (!buffers) {
        fprintf(stderr, "%s[ERROR]%s Out of memory\n",
                COLOR_RED, COLOR_RESET);
        return -1;
    }
    
    n_buffers = reqbuf.count;
    
    for (i = 0; i < reqbuf.count; i++) {
        CLEAR(buf);
        buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        buf.memory = V4L2_MEMORY_MMAP;
        buf.index = i;
        
        if (xioctl(fd, VIDIOC_QUERYBUF, &buf) < 0)
            errno_exit("VIDIOC_QUERYBUF");
        
        buffers[i].length = buf.length;
        buffers[i].start = mmap(NULL, buf.length,
                               PROT_READ | PROT_WRITE,
                               MAP_SHARED, fd, buf.m.offset);
        
        if (buffers[i].start == MAP_FAILED)
            errno_exit("mmap");
        
        printf("%s[INFO]%s Mapped buffer %d: %zu bytes at %p\n",
               COLOR_GREEN, COLOR_RESET, i, 
               buffers[i].length, buffers[i].start);
    }
    
    /* Queue all buffers */
    for (i = 0; i < n_buffers; i++) {
        CLEAR(buf);
        buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        buf.memory = V4L2_MEMORY_MMAP;
        buf.index = i;
        
        if (xioctl(fd, VIDIOC_QBUF, &buf) < 0)
            errno_exit("VIDIOC_QBUF");
    }
    
    return 0;
}

/* Start capture */
static int start_capture(void) {
    enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    
    if (xioctl(fd, VIDIOC_STREAMON, &type) < 0)
        errno_exit("VIDIOC_STREAMON");
    
    printf("%s[INFO]%s Capture started\n", COLOR_GREEN, COLOR_RESET);
    return 0;
}

/* Stop capture */
static int stop_capture(void) {
    enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    
    if (xioctl(fd, VIDIOC_STREAMOFF, &type) < 0)
        errno_exit("VIDIOC_STREAMOFF");
    
    printf("%s[INFO]%s Capture stopped\n", COLOR_YELLOW, COLOR_RESET);
    return 0;
}

/* Capture a frame */
static int capture_frame(void) {
    struct v4l2_buffer buf;
    struct timeval current_time;
    double elapsed;
    int ret;
    
    CLEAR(buf);
    buf.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    buf.memory = V4L2_MEMORY_MMAP;
    
    /* Dequeue buffer */
    ret = xioctl(fd, VIDIOC_DQBUF, &buf);
    if (ret < 0) {
        if (errno == EAGAIN) {
            /* No frame available */
            return 0;
        }
        errno_exit("VIDIOC_DQBUF");
    }
    
    frame_count++;
    
    /* Get current time for FPS calculation */
    gettimeofday(&current_time, NULL);
    
    if (frame_count == 1) {
        start_time = current_time;
    }
    
    /* Calculate FPS */
    elapsed = (current_time.tv_sec - start_time.tv_sec) +
              (current_time.tv_usec - start_time.tv_usec) / 1000000.0;
    
    if (elapsed > 0) {
        double fps = frame_count / elapsed;
        printf("\r%s[INFO]%s Frame %u captured (%zu bytes) - FPS: %.2f",
               COLOR_CYAN, COLOR_RESET,
               frame_count, buffers[buf.index].length, fps);
        fflush(stdout);
    }
    
    /* Process frame here if needed */
    // process_frame(buffers[buf.index].start, buffers[buf.index].length);
    
    /* Requeue buffer */
    if (xioctl(fd, VIDIOC_QBUF, &buf) < 0)
        errno_exit("VIDIOC_QBUF");
    
    return 0;
}

/* Save frame to PPM file */
static void save_frame_to_ppm(void *data, int width, int height, int format) {
    char filename[256];
    FILE *fp;
    int i, j;
    unsigned char *p = (unsigned char *)data;
    
    static int file_counter = 0;
    
    if (format != V4L2_PIX_FMT_RGB24 && format != V4L2_PIX_FMT_RGB32) {
        printf("%s[WARN]%s Can only save RGB24/RGB32 frames\n",
               COLOR_YELLOW, COLOR_RESET);
        return;
    }
    
    snprintf(filename, sizeof(filename), "frame_%04d.ppm", file_counter++);
    
    fp = fopen(filename, "w");
    if (!fp) {
        perror("fopen");
        return;
    }
    
    fprintf(fp, "P6\n%d %d\n255\n", width, height);
    
    if (format == V4L2_PIX_FMT_RGB24) {
        fwrite(data, width * height * 3, 1, fp);
    } else { /* RGB32 */
        for (i = 0; i < height; i++) {
            for (j = 0; j < width; j++) {
                unsigned char *pixel = p + (i * width + j) * 4;
                fwrite(pixel, 3, 1, fp);
            }
        }
    }
    
    fclose(fp);
    printf("\n%s[INFO]%s Frame saved to %s\n", 
           COLOR_GREEN, COLOR_RESET, filename);
}

/* Print usage */
static void print_usage(const char *program) {
    printf("Usage: %s [options]\n", program);
    printf("Options:\n");
    printf("  -d <device>   Video device (default: %s)\n", DEFAULT_DEVICE);
    printf("  -w <width>    Frame width (default: %d)\n", DEFAULT_WIDTH);
    printf("  -h <height>   Frame height (default: %d)\n", DEFAULT_HEIGHT);
    printf("  -f <format>   Pixel format (YUYV, RGB24, GREY)\n");
    printf("  -r <fps>      Frame rate (default: %d)\n", DEFAULT_FPS);
    printf("  -c <count>    Number of frames to capture (0=infinite)\n");
    printf("  -s            Save captured frames to PPM files\n");
    printf("  -l            List supported formats\n");
    printf("  -q            Quiet mode\n");
    printf("  -h            Show this help\n");
}

/* Parse pixel format string */
static int parse_format(const char *fmt_str) {
    if (strcmp(fmt_str, "YUYV") == 0)
        return V4L2_PIX_FMT_YUYV;
    if (strcmp(fmt_str, "RGB24") == 0)
        return V4L2_PIX_FMT_RGB24;
    if (strcmp(fmt_str, "RGB32") == 0)
        return V4L2_PIX_FMT_RGB32;
    if (strcmp(fmt_str, "GREY") == 0)
        return V4L2_PIX_FMT_GREY;
    if (strcmp(fmt_str, "MJPG") == 0)
        return V4L2_PIX_FMT_MJPEG;
    
    fprintf(stderr, "%s[ERROR]%s Unknown format: %s\n",
            COLOR_RED, COLOR_RESET, fmt_str);
    return 0;
}

/* Main function */
int main(int argc, char *argv[]) {
    char device[256] = DEFAULT_DEVICE;
    int width = DEFAULT_WIDTH;
    int height = DEFAULT_HEIGHT;
    int format = V4L2_PIX_FMT_YUYV;
    int fps = DEFAULT_FPS;
    int frame_count_max = 0;  /* 0 = infinite */
    int save_frames = 0;
    int quiet = 0;
    int list_only = 0;
    int opt;
    int ret;
    
    printf("========================================\n");
    printf("V4L2 Virtual Camera Test Application\n");
    printf("Version: 1.0.0\n");
    printf("========================================\n\n");
    
    /* Parse command line arguments */
    while ((opt = getopt(argc, argv, "d:w:h:f:r:c:slqh")) != -1) {
        switch (opt) {
            case 'd':
                strncpy(device, optarg, sizeof(device) - 1);
                device[sizeof(device) - 1] = '\0';
                break;
                
            case 'w':
                width = atoi(optarg);
                if (width < 64 || width > 4096) {
                    fprintf(stderr, "%s[ERROR]%s Invalid width: %d\n",
                            COLOR_RED, COLOR_RESET, width);
                    return 1;
                }
                break;
                
            case 'h':
                height = atoi(optarg);
                if (height < 64 || height > 4096) {
                    fprintf(stderr, "%s[ERROR]%s Invalid height: %d\n",
                            COLOR_RED, COLOR_RESET, height);
                    return 1;
                }
                break;
                
            case 'f':
                format = parse_format(optarg);
                if (format == 0) {
                    return 1;
                }
                break;
                
            case 'r':
                fps = atoi(optarg);
                if (fps < 1 || fps > 120) {
                    fprintf(stderr, "%s[ERROR]%s Invalid FPS: %d\n",
                            COLOR_RED, COLOR_RESET, fps);
                    return 1;
                }
                break;
                
            case 'c':
                frame_count_max = atoi(optarg);
                if (frame_count_max < 0) {
                    fprintf(stderr, "%s[ERROR]%s Invalid frame count\n",
                            COLOR_RED, COLOR_RESET);
                    return 1;
                }
                break;
                
            case 's':
                save_frames = 1;
                break;
                
            case 'l':
                list_only = 1;
                break;
                
            case 'q':
                quiet = 1;
                break;
                
            case 'h':
            default:
                print_usage(argv[0]);
                return 0;
        }
    }
    
    /* Set signal handler */
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
    
    /* Open device */
    printf("%s[INFO]%s Opening device: %s\n", 
           COLOR_BLUE, COLOR_RESET, device);
    
    fd = v4l2_open(device, O_RDWR | O_NONBLOCK, 0);
    if (fd < 0) {
        fprintf(stderr, "%s[ERROR]%s Failed to open device: %s\n",
                COLOR_RED, COLOR_RESET, strerror(errno));
        return 1;
    }
    
    printf("%s[INFO]%s Device opened successfully\n", 
           COLOR_GREEN, COLOR_RESET);
    
    /* List formats and exit if requested */
    if (list_only) {
        print_supported_formats(fd);
        v4l2_close(fd);
        return 0;
    }
    
    /* Initialize device */
    ret = init_device(width, height, format, fps);
    if (ret < 0) {
        v4l2_close(fd);
        return 1;
    }
    
    /* Initialize memory mapping */
    ret = init_mmap();
    if (ret < 0) {
        v4l2_close(fd);
        return 1;
    }
    
    /* Start capture */
    ret = start_capture();
    if (ret < 0) {
        v4l2_close(fd);
        return 1;
    }
    
    printf("\n%s[INFO]%s Capturing frames... (Press Ctrl+C to stop)\n\n",
           COLOR_GREEN, COLOR_RESET);
    
    /* Capture loop */
    while (running) {
        ret = capture_frame();
        if (ret < 0) {
            break;
        }
        
        if (frame_count_max > 0 && frame_count >= frame_count_max) {
            printf("\n%s[INFO]%s Reached maximum frame count (%d)\n",
                   COLOR_YELLOW, COLOR_RESET, frame_count_max);
            break;
        }
        
        /* Save frame if requested and frame count is multiple of 10 */
        if (save_frames && frame_count % 10 == 0) {
            save_frame_to_ppm(buffers[0].start, width, height, format);
        }
    }
    
    printf("\n");
    
    /* Stop capture */
    stop_capture();
    
    /* Clean up */
    for (unsigned int i = 0; i < n_buffers; i++) {
        if (buffers[i].start)
            munmap(buffers[i].start, buffers[i].length);
    }
    
    free(buffers);
    
    /* Close device */
    v4l2_close(fd);
    
    printf("\n%s[INFO]%s Captured %u frames total\n",
           COLOR_CYAN, COLOR_RESET, frame_count);
    
    printf("%s[INFO]%s Test completed\n", COLOR_GREEN, COLOR_RESET);
    
    return 0;
}
