/*
 * frame-generator.c - Video Frame Generator for Virtual Camera
 * 
 * This module generates test patterns and video frames for virtual
 * camera devices on Intel NUC platforms.
 * 
 * Version: 1.0.0
 * Author: Intel NUC Virtual Device Platform Team
 * License: GPL v2
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/slab.h>
#include <linux/vmalloc.h>
#include <linux/sched.h>
#include <linux/delay.h>
#include <linux/timer.h>
#include <linux/workqueue.h>
#include <linux/kthread.h>
#include <linux/mutex.h>
#include <linux/spinlock.h>
#include <linux/random.h>
#include <linux/math64.h>
#include <linux/string.h>
#include <linux/fs.h>
#include <linux/uaccess.h>
#include <media/v4l2-device.h>
#include <media/v4l2-ioctl.h>
#include <media/videobuf2-vmalloc.h>

#define FRAME_GENERATOR_NAME "frame-generator"
#define FRAME_GENERATOR_VERSION "1.0.0"

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Intel NUC Virtual Device Platform Team");
MODULE_DESCRIPTION("Video Frame Generator for Virtual Camera");
MODULE_VERSION(FRAME_GENERATOR_VERSION);

/* Frame Generator Configuration */
#define MAX_WIDTH 3840
#define MAX_HEIGHT 2160
#define MIN_WIDTH 64
#define MIN_HEIGHT 64
#define DEFAULT_WIDTH 1920
#define DEFAULT_HEIGHT 1080
#define DEFAULT_FPS 30
#define MAX_FPS 120
#define MIN_FPS 1

/* Test Pattern Types */
enum test_pattern {
    PATTERN_COLOR_BARS = 0,
    PATTERN_SMPTE_BARS = 1,
    PATTERN_CHECKERBOARD = 2,
    PATTERN_GRADIENT = 3,
    PATTERN_MOVING_BAR = 4,
    PATTERN_NOISE = 5,
    PATTERN_COLOR_WHEEL = 6,
    PATTERN_TEXT = 7,
    PATTERN_CLOCK = 8,
    PATTERN_MOVIE = 9,
    PATTERN_MAX
};

/* Pixel Formats */
enum pixel_format {
    FORMAT_YUYV = 0,
    FORMAT_UYVY = 1,
    FORMAT_RGB24 = 2,
    FORMAT_RGB32 = 3,
    FORMAT_GREY = 4,
    FORMAT_YUV420 = 5,
    FORMAT_YVU420 = 6,
    FORMAT_MAX
};

/* Frame Generator Context */
struct frame_generator {
    struct mutex lock;
    spinlock_t slock;
    struct timer_list timer;
    struct work_struct work;
    struct task_struct *thread;
    wait_queue_head_t wait;
    
    /* Frame parameters */
    u32 width;
    u32 height;
    u32 fps;
    u32 format;
    u32 pattern;
    u32 frame_count;
    u32 bitrate;
    
    /* Frame buffer */
    void *buffer;
    u32 buffer_size;
    u32 frame_size;
    bool buffer_ready;
    
    /* Timing */
    ktime_t frame_time;
    u64 frame_interval_ns;
    u64 last_frame_time;
    
    /* Statistics */
    u64 frames_generated;
    u64 frames_dropped;
    u64 bytes_generated;
    u32 fps_actual;
    ktime_t start_time;
    
    /* Configuration */
    bool active;
    bool streaming;
    bool color;
    u8 brightness;
    u8 contrast;
    u8 saturation;
    u8 hue;
    
    /* Test pattern specific */
    u32 pattern_param1;
    u32 pattern_param2;
    u32 pattern_param3;
    char text[256];
    bool moving;
    u32 move_x;
    u32 move_y;
    u32 move_dx;
    u32 move_dy;
};

/* Global Frame Generator Instance */
static struct frame_generator *g_generator;
static struct class *fg_class;
static dev_t fg_devt;
static struct device *fg_device;

/* ==================== Frame Generation Functions ==================== */

/**
 * generate_color_bars - Generate color bars test pattern
 * @buf: Output buffer
 * @width: Image width
 * @height: Image height
 * @format: Pixel format
 */
static void generate_color_bars(void *buf, u32 width, u32 height, u32 format)
{
    u8 *p = buf;
    u32 x, y;
    u32 bar_width;
    u32 bars = 8;
    u32 colors[8][3] = {
        {255, 255, 255}, /* White */
        {255, 255, 0},   /* Yellow */
        {0, 255, 255},   /* Cyan */
        {0, 255, 0},     /* Green */
        {255, 0, 255},   /* Magenta */
        {255, 0, 0},     /* Red */
        {0, 0, 255},     /* Blue */
        {0, 0, 0}        /* Black */
    };
    
    bar_width = width / bars;
    
    for (y = 0; y < height; y++) {
        for (x = 0; x < width; x++) {
            u32 bar = x / bar_width;
            if (bar >= bars) bar = bars - 1;
            
            switch (format) {
                case FORMAT_RGB24: {
                    u32 pos = (y * width + x) * 3;
                    p[pos] = colors[bar][0];     /* R */
                    p[pos+1] = colors[bar][1];   /* G */
                    p[pos+2] = colors[bar][2];   /* B */
                    break;
                }
                case FORMAT_RGB32: {
                    u32 pos = (y * width + x) * 4;
                    p[pos] = colors[bar][0];     /* R */
                    p[pos+1] = colors[bar][1];   /* G */
                    p[pos+2] = colors[bar][2];   /* B */
                    p[pos+3] = 255;              /* A */
                    break;
                }
                case FORMAT_YUYV: {
                    u32 pos = (y * width + x) * 2;
                    u8 y_val = (u8)((0.299 * colors[bar][0] +
                                    0.587 * colors[bar][1] +
                                    0.114 * colors[bar][2]));
                    u8 u_val = (u8)((0.492 * (colors[bar][2] - y_val)) + 128);
                    u8 v_val = (u8)((0.877 * (colors[bar][0] - y_val)) + 128);
                    p[pos] = y_val;
                    p[pos+1] = (x % 2) ? u_val : v_val;
                    break;
                }
                case FORMAT_GREY: {
                    u32 pos = y * width + x;
                    u8 val = (u8)((0.299 * colors[bar][0] +
                                  0.587 * colors[bar][1] +
                                  0.114 * colors[bar][2]));
                    p[pos] = val;
                    break;
                }
                default:
                    break;
            }
        }
    }
}

/**
 * generate_smpte_bars - Generate SMPTE color bars
 * @buf: Output buffer
 * @width: Image width
 * @height: Image height
 * @format: Pixel format
 */
static void generate_smpte_bars(void *buf, u32 width, u32 height, u32 format)
{
    u8 *p = buf;
    u32 x, y;
    u32 bar_width;
    u32 i;
    
    /* SMPTE Color Bars - 7 bars */
    u32 smpte_colors[7][3] = {
        {191, 191, 191}, /* Gray 75% */
        {191, 191, 0},   /* Yellow */
        {0, 191, 191},   /* Cyan */
        {0, 191, 0},     /* Green */
        {191, 0, 191},   /* Magenta */
        {191, 0, 0},     /* Red */
        {0, 0, 191}      /* Blue */
    };
    
    /* Sub-bars for 75% color bars */
    u32 sub_colors[4][3] = {
        {191, 0, 0},     /* Red */
        {0, 191, 0},     /* Green */
        {0, 0, 191},     /* Blue */
        {0, 0, 0}        /* Black */
    };
    
    bar_width = width / 7;
    
    for (y = 0; y < height; y++) {
        for (x = 0; x < width; x++) {
            u32 bar = x / bar_width;
            u8 r, g, b;
            
            if (bar >= 7) bar = 6;
            
            /* Main bars */
            r = smpte_colors[bar][0];
            g = smpte_colors[bar][1];
            b = smpte_colors[bar][2];
            
            /* Add sub-bars in the last 25% of the image */
            if (y > height * 0.75) {
                u32 sub_bar = (x * 4) / width;
                if (sub_bar < 4) {
                    u32 factor = (height - y) / (height / 8);
                    r = (r * factor + sub_colors[sub_bar][0] * (8 - factor)) / 8;
                    g = (g * factor + sub_colors[sub_bar][1] * (8 - factor)) / 8;
                    b = (b * factor + sub_colors[sub_bar][2] * (8 - factor)) / 8;
                }
            }
            
            /* Convert to target format */
            switch (format) {
                case FORMAT_RGB24: {
                    u32 pos = (y * width + x) * 3;
                    p[pos] = r;
                    p[pos+1] = g;
                    p[pos+2] = b;
                    break;
                }
                case FORMAT_RGB32: {
                    u32 pos = (y * width + x) * 4;
                    p[pos] = r;
                    p[pos+1] = g;
                    p[pos+2] = b;
                    p[pos+3] = 255;
                    break;
                }
                case FORMAT_YUYV: {
                    u32 pos = (y * width + x) * 2;
                    u8 y_val = (u8)(0.299 * r + 0.587 * g + 0.114 * b);
                    u8 u_val = (u8)((b - y_val) * 0.492 + 128);
                    u8 v_val = (u8)((r - y_val) * 0.877 + 128);
                    p[pos] = y_val;
                    p[pos+1] = (x % 2) ? u_val : v_val;
                    break;
                }
                default:
                    break;
            }
        }
    }
}

/**
 * generate_checkerboard - Generate checkerboard pattern
 * @buf: Output buffer
 * @width: Image width
 * @height: Image height
 * @format: Pixel format
 * @size: Checker size
 */
static void generate_checkerboard(void *buf, u32 width, u32 height, 
                                  u32 format, u32 size)
{
    u8 *p = buf;
    u32 x, y;
    u32 cx, cy;
    bool color;
    
    if (size == 0) size = 16;
    
    for (y = 0; y < height; y++) {
        for (x = 0; x < width; x++) {
            cx = x / size;
            cy = y / size;
            color = ((cx + cy) % 2) == 0;
            
            u8 r = color ? 255 : 0;
            u8 g = color ? 255 : 0;
            u8 b = color ? 255 : 0;
            
            switch (format) {
                case FORMAT_RGB24: {
                    u32 pos = (y * width + x) * 3;
                    p[pos] = r;
                    p[pos+1] = g;
                    p[pos+2] = b;
                    break;
                }
                case FORMAT_YUYV: {
                    u32 pos = (y * width + x) * 2;
                    u8 y_val = (u8)(0.299 * r + 0.587 * g + 0.114 * b);
                    u8 u_val = (u8)((b - y_val) * 0.492 + 128);
                    u8 v_val = (u8)((r - y_val) * 0.877 + 128);
                    p[pos] = y_val;
                    p[pos+1] = (x % 2) ? u_val : v_val;
                    break;
                }
                default:
                    break;
            }
        }
    }
}

/**
 * generate_gradient - Generate gradient pattern
 * @buf: Output buffer
 * @width: Image width
 * @height: Image height
 * @format: Pixel format
 * @direction: 0=horizontal, 1=vertical, 2=diagonal
 */
static void generate_gradient(void *buf, u32 width, u32 height, 
                              u32 format, u32 direction)
{
    u8 *p = buf;
    u32 x, y;
    u8 val;
    
    for (y = 0; y < height; y++) {
        for (x = 0; x < width; x++) {
            switch (direction) {
                case 0: /* Horizontal */
                    val = (x * 255) / width;
                    break;
                case 1: /* Vertical */
                    val = (y * 255) / height;
                    break;
                case 2: /* Diagonal */
                default:
                    val = ((x + y) * 255) / (width + height);
                    break;
            }
            
            switch (format) {
                case FORMAT_RGB24: {
                    u32 pos = (y * width + x) * 3;
                    p[pos] = val;     /* R */
                    p[pos+1] = val;   /* G */
                    p[pos+2] = val;   /* B */
                    break;
                }
                case FORMAT_RGB32: {
                    u32 pos = (y * width + x) * 4;
                    p[pos] = val;     /* R */
                    p[pos+1] = val;   /* G */
                    p[pos+2] = val;   /* B */
                    p[pos+3] = 255;   /* A */
                    break;
                }
                case FORMAT_YUYV: {
                    u32 pos = (y * width + x) * 2;
                    p[pos] = val;     /* Y */
                    p[pos+1] = 128;   /* U/V */
                    break;
                }
                case FORMAT_GREY: {
                    u32 pos = y * width + x;
                    p[pos] = val;
                    break;
                }
                default:
                    break;
            }
        }
    }
}

/**
 * generate_noise - Generate random noise pattern
 * @buf: Output buffer
 * @width: Image width
 * @height: Image height
 * @format: Pixel format
 */
static void generate_noise(void *buf, u32 width, u32 height, u32 format)
{
    u8 *p = buf;
    u32 x, y;
    u8 r, g, b;
    
    for (y = 0; y < height; y++) {
        for (x = 0; x < width; x++) {
            r = get_random_u8();
            g = get_random_u8();
            b = get_random_u8();
            
            switch (format) {
                case FORMAT_RGB24: {
                    u32 pos = (y * width + x) * 3;
                    p[pos] = r;
                    p[pos+1] = g;
                    p[pos+2] = b;
                    break;
                }
                case FORMAT_YUYV: {
                    u32 pos = (y * width + x) * 2;
                    u8 y_val = (u8)(0.299 * r + 0.587 * g + 0.114 * b);
                    u8 u_val = (u8)((b - y_val) * 0.492 + 128);
                    u8 v_val = (u8)((r - y_val) * 0.877 + 128);
                    p[pos] = y_val;
                    p[pos+1] = (x % 2) ? u_val : v_val;
                    break;
                }
                default:
                    break;
            }
        }
    }
}

/**
 * generate_color_wheel - Generate color wheel pattern
 * @buf: Output buffer
 * @width: Image width
 * @height: Image height
 * @format: Pixel format
 */
static void generate_color_wheel(void *buf, u32 width, u32 height, u32 format)
{
    u8 *p = buf;
    u32 x, y;
    float cx = width / 2.0;
    float cy = height / 2.0;
    float radius = (width < height ? width : height) / 2.0;
    float angle, dist;
    u8 r, g, b;
    
    for (y = 0; y < height; y++) {
        for (x = 0; x < width; x++) {
            dist = sqrt(pow(x - cx, 2) + pow(y - cy, 2));
            if (dist > radius) {
                r = g = b = 0;
            } else {
                angle = atan2(y - cy, x - cx) * 180 / 3.14159;
                if (angle < 0) angle += 360;
                
                /* Convert angle to RGB */
                if (angle < 60) {
                    r = 255;
                    g = (u8)(255 * angle / 60);
                    b = 0;
                } else if (angle < 120) {
                    r = (u8)(255 * (120 - angle) / 60);
                    g = 255;
                    b = 0;
                } else if (angle < 180) {
                    r = 0;
                    g = 255;
                    b = (u8)(255 * (angle - 120) / 60);
                } else if (angle < 240) {
                    r = 0;
                    g = (u8)(255 * (240 - angle) / 60);
                    b = 255;
                } else if (angle < 300) {
                    r = (u8)(255 * (angle - 240) / 60);
                    g = 0;
                    b = 255;
                } else {
                    r = 255;
                    g = 0;
                    b = (u8)(255 * (360 - angle) / 60);
                }
                
                /* Apply brightness gradient from center */
                float brightness = 1.0 - (dist / radius);
                r = (u8)(r * brightness);
                g = (u8)(g * brightness);
                b = (u8)(b * brightness);
            }
            
            switch (format) {
                case FORMAT_RGB24: {
                    u32 pos = (y * width + x) * 3;
                    p[pos] = r;
                    p[pos+1] = g;
                    p[pos+2] = b;
                    break;
                }
                case FORMAT_YUYV: {
                    u32 pos = (y * width + x) * 2;
                    u8 y_val = (u8)(0.299 * r + 0.587 * g + 0.114 * b);
                    u8 u_val = (u8)((b - y_val) * 0.492 + 128);
                    u8 v_val = (u8)((r - y_val) * 0.877 + 128);
                    p[pos] = y_val;
                    p[pos+1] = (x % 2) ? u_val : v_val;
                    break;
                }
                default:
                    break;
            }
        }
    }
}

/**
 * generate_moving_bar - Generate moving bar pattern
 * @fg: Frame generator context
 * @buf: Output buffer
 * @width: Image width
 * @height: Image height
 * @format: Pixel format
 */
static void generate_moving_bar(struct frame_generator *fg, void *buf,
                                u32 width, u32 height, u32 format)
{
    u8 *p = buf;
    u32 x, y;
    u32 bar_width = 20;
    u32 bar_pos;
    
    bar_pos = (fg->frame_count * 5) % (width + bar_width);
    if (bar_pos > width) bar_pos = width;
    
    for (y = 0; y < height; y++) {
        for (x = 0; x < width; x++) {
            u8 r, g, b;
            if (x >= bar_pos && x < bar_pos + bar_width) {
                r = 255;
                g = 255;
                b = 255;
            } else {
                r = 0;
                g = 0;
                b = 0;
            }
            
            switch (format) {
                case FORMAT_RGB24: {
                    u32 pos = (y * width + x) * 3;
                    p[pos] = r;
                    p[pos+1] = g;
                    p[pos+2] = b;
                    break;
                }
                case FORMAT_YUYV: {
                    u32 pos = (y * width + x) * 2;
                    u8 y_val = (u8)(0.299 * r + 0.587 * g + 0.114 * b);
                    u8 u_val = (u8)((b - y_val) * 0.492 + 128);
                    u8 v_val = (u8)((r - y_val) * 0.877 + 128);
                    p[pos] = y_val;
                    p[pos+1] = (x % 2) ? u_val : v_val;
                    break;
                }
                default:
                    break;
            }
        }
    }
}

/**
 * generate_text_overlay - Add text overlay to frame
 * @buf: Frame buffer
 * @width: Image width
 * @height: Image height
 * @format: Pixel format
 * @text: Text string
 * @x: X position
 * @y: Y position
 */
static void generate_text_overlay(void *buf, u32 width, u32 height,
                                  u32 format, const char *text, u32 x, u32 y)
{
    /* Simple text overlay using bitmap font */
    /* This is a simplified implementation */
    u8 *p = buf;
    u32 i, j;
    u32 len = strlen(text);
    u32 char_width = 8;
    u32 char_height = 12;
    u32 char_spacing = 2;
    u8 r, g, b;
    
    /* Simple 8x12 font mapping for text overlay */
    r = 255;
    g = 255;
    b = 255;
    
    for (i = 0; i < len && i < 32; i++) {
        u32 cx = x + i * (char_width + char_spacing);
        u32 cy = y;
        
        for (j = 0; j < char_height && cy + j < height; j++) {
            u32 pos = (cy + j) * width * 3 + cx * 3;
            for (u32 k = 0; k < char_width && cx + k < width; k++) {
                p[pos + k * 3] = r;
                p[pos + k * 3 + 1] = g;
                p[pos + k * 3 + 2] = b;
            }
        }
    }
}

/**
 * generate_frame - Generate a single video frame
 * @fg: Frame generator context
 * @buf: Output buffer
 * @width: Image width
 * @height: Image height
 * @format: Pixel format
 * @pattern: Test pattern type
 */
static void generate_frame(struct frame_generator *fg, void *buf,
                          u32 width, u32 height, u32 format, u32 pattern)
{
    if (!buf || !fg) {
        return;
    }
    
    /* Clear buffer */
    memset(buf, 0, fg->frame_size);
    
    /* Generate pattern */
    switch (pattern) {
        case PATTERN_COLOR_BARS:
            generate_color_bars(buf, width, height, format);
            break;
            
        case PATTERN_SMPTE_BARS:
            generate_smpte_bars(buf, width, height, format);
            break;
            
        case PATTERN_CHECKERBOARD:
            generate_checkerboard(buf, width, height, format, 
                                 fg->pattern_param1);
            break;
            
        case PATTERN_GRADIENT:
            generate_gradient(buf, width, height, format,
                             fg->pattern_param1);
            break;
            
        case PATTERN_MOVING_BAR:
            generate_moving_bar(fg, buf, width, height, format);
            break;
            
        case PATTERN_NOISE:
            generate_noise(buf, width, height, format);
            break;
            
        case PATTERN_COLOR_WHEEL:
            generate_color_wheel(buf, width, height, format);
            break;
            
        case PATTERN_TEXT:
            generate_color_bars(buf, width, height, format);
            generate_text_overlay(buf, width, height, format,
                                 fg->text, 50, 50);
            break;
            
        case PATTERN_CLOCK:
            generate_color_bars(buf, width, height, format);
            /* Would generate clock overlay here */
            break;
            
        case PATTERN_MOVIE:
            /* For movie mode, generate sequential frames */
            generate_color_bars(buf, width, height, format);
            /* Overlay frame number */
            {
                char frame_str[32];
                snprintf(frame_str, sizeof(frame_str), "Frame: %llu",
                        fg->frames_generated);
                generate_text_overlay(buf, width, height, format,
                                     frame_str, 50, 100);
            }
            break;
            
        default:
            generate_color_bars(buf, width, height, format);
            break;
    }
    
    /* Apply brightness/contrast/saturation adjustments */
    if (fg->brightness != 128 || fg->contrast != 128 || 
        fg->saturation != 128) {
        /* Apply adjustments */
        /* Simplified: just adjust brightness */
        if (fg->brightness != 128) {
            u8 *p = buf;
            u32 size = fg->frame_size;
            s32 adjust = (s32)fg->brightness - 128;
            
            for (u32 i = 0; i < size; i++) {
                s32 val = (s32)p[i] + adjust;
                p[i] = (u8)clamp(val, 0, 255);
            }
        }
    }
}

/* ==================== Frame Generation Thread ==================== */

/**
 * frame_generator_thread - Main frame generation thread
 * @data: Frame generator context
 * 
 * Returns: 0 on success
 */
static int frame_generator_thread(void *data)
{
    struct frame_generator *fg = data;
    u64 frame_interval_ns;
    u32 frame_count = 0;
    ktime_t next_frame_time;
    s64 sleep_time;
    
    pr_info("%s: Frame generator thread started\n", FRAME_GENERATOR_NAME);
    
    frame_interval_ns = 1000000000ULL / fg->fps;
    next_frame_time = ktime_get();
    fg->start_time = next_frame_time;
    
    while (!kthread_should_stop() && fg->active) {
        void *frame_buf;
        
        /* Allocate frame buffer if needed */
        if (!fg->buffer_ready) {
            pr_err("%s: Buffer not ready\n", FRAME_GENERATOR_NAME);
            msleep(100);
            continue;
        }
        
        /* Get current time */
        ktime_t now = ktime_get();
        
        /* Wait for next frame time */
        if (ktime_after(next_frame_time, now)) {
            sleep_time = ktime_to_ns(ktime_sub(next_frame_time, now));
            if (sleep_time > 1000) {
                msleep(sleep_time / 1000000);
            }
            continue;
        }
        
        /* Generate frame */
        spin_lock(&fg->slock);
        frame_buf = fg->buffer;
        if (frame_buf) {
            generate_frame(fg, frame_buf, fg->width, fg->height,
                          fg->format, fg->pattern);
            
            /* Update statistics */
            fg->frames_generated++;
            fg->bytes_generated += fg->frame_size;
            fg->frame_count++;
            
            /* Update actual FPS */
            if (fg->frame_count % 30 == 0) {
                ktime_t elapsed = ktime_sub(now, fg->start_time);
                u64 elapsed_ms = ktime_to_ms(elapsed);
                if (elapsed_ms > 0) {
                    fg->fps_actual = (fg->frames_generated * 1000) / elapsed_ms;
                }
            }
            
            /* Wake up readers */
            wake_up_interruptible(&fg->wait);
        }
        spin_unlock(&fg->slock);
        
        /* Schedule next frame */
        next_frame_time = ktime_add_ns(next_frame_time, frame_interval_ns);
        
        /* Prevent falling behind */
        if (ktime_after(ktime_get(), next_frame_time)) {
            next_frame_time = ktime_add_ns(ktime_get(), frame_interval_ns);
            fg->frames_dropped++;
        }
        
        frame_count++;
    }
    
    pr_info("%s: Frame generator thread stopped\n", FRAME_GENERATOR_NAME);
    return 0;
}

/**
 * frame_generator_timer_callback - Timer callback for frame generation
 * @t: Timer structure
 */
static void frame_generator_timer_callback(struct timer_list *t)
{
    struct frame_generator *fg = from_timer(fg, t, timer);
    
    if (fg && fg->active) {
        schedule_work(&fg->work);
        mod_timer(&fg->timer, jiffies + HZ / fg->fps);
    }
}

/**
 * frame_generator_work_handler - Work handler for frame generation
 * @work: Work structure
 */
static void frame_generator_work_handler(struct work_struct *work)
{
    struct frame_generator *fg = container_of(work, struct frame_generator, work);
    
    if (fg && fg->active) {
        void *frame_buf;
        
        spin_lock(&fg->slock);
        frame_buf = fg->buffer;
        if (frame_buf) {
            generate_frame(fg, frame_buf, fg->width, fg->height,
                          fg->format, fg->pattern);
            fg->frames_generated++;
            wake_up_interruptible(&fg->wait);
        }
        spin_unlock(&fg->slock);
    }
}

/* ==================== Public API Functions ==================== */

/**
 * frame_generator_create - Create frame generator instance
 * @width: Frame width
 * @height: Frame height
 * @fps: Frames per second
 * @format: Pixel format
 * 
 * Returns: Frame generator context on success, NULL on error
 */
struct frame_generator *frame_generator_create(u32 width, u32 height,
                                               u32 fps, u32 format)
{
    struct frame_generator *fg;
    u32 frame_size;
    
    pr_info("%s: Creating frame generator (%ux%u @ %u fps)\n",
            FRAME_GENERATOR_NAME, width, height, fps);
    
    /* Validate parameters */
    if (width < MIN_WIDTH || width > MAX_WIDTH ||
        height < MIN_HEIGHT || height > MAX_HEIGHT ||
        fps < MIN_FPS || fps > MAX_FPS) {
        pr_err("%s: Invalid parameters\n", FRAME_GENERATOR_NAME);
        return NULL;
    }
    
    /* Allocate context */
    fg = kzalloc(sizeof(struct frame_generator), GFP_KERNEL);
    if (!fg) {
        pr_err("%s: Failed to allocate context\n", FRAME_GENERATOR_NAME);
        return NULL;
    }
    
    /* Initialize */
    fg->width = width;
    fg->height = height;
    fg->fps = fps;
    fg->format = format;
    fg->pattern = PATTERN_COLOR_BARS;
    fg->brightness = 128;
    fg->contrast = 128;
    fg->saturation = 128;
    fg->hue = 0;
    fg->active = false;
    fg->streaming = false;
    fg->frame_count = 0;
    fg->pattern_param1 = 16; /* Default checker size */
    fg->pattern_param2 = 0;
    fg->pattern_param3 = 0;
    fg->move_dx = 1;
    fg->move_dy = 1;
    
    /* Calculate frame size */
    switch (format) {
        case FORMAT_RGB24:
            frame_size = width * height * 3;
            break;
        case FORMAT_RGB32:
            frame_size = width * height * 4;
            break;
        case FORMAT_YUYV:
        case FORMAT_UYVY:
            frame_size = width * height * 2;
            break;
        case FORMAT_GREY:
            frame_size = width * height;
            break;
        case FORMAT_YUV420:
        case FORMAT_YVU420:
            frame_size = width * height * 3 / 2;
            break;
        default:
            frame_size = width * height * 2;
            break;
    }
    fg->frame_size = frame_size;
    fg->buffer_size = frame_size;
    
    /* Allocate frame buffer */
    fg->buffer = vmalloc(frame_size);
    if (!fg->buffer) {
        pr_err("%s: Failed to allocate frame buffer\n", FRAME_GENERATOR_NAME);
        kfree(fg);
        return NULL;
    }
    fg->buffer_ready = true;
    
    /* Initialize locks */
    mutex_init(&fg->lock);
    spin_lock_init(&fg->slock);
    init_waitqueue_head(&fg->wait);
    
    /* Initialize work and timer */
    INIT_WORK(&fg->work, frame_generator_work_handler);
    timer_setup(&fg->timer, frame_generator_timer_callback, 0);
    
    pr_info("%s: Frame generator created\n", FRAME_GENERATOR_NAME);
    return fg;
}
EXPORT_SYMBOL(frame_generator_create);

/**
 * frame_generator_destroy - Destroy frame generator
 * @fg: Frame generator context
 */
void frame_generator_destroy(struct frame_generator *fg)
{
    if (!fg) {
        return;
    }
    
    pr_info("%s: Destroying frame generator\n", FRAME_GENERATOR_NAME);
    
    /* Stop generation */
    fg->active = false;
    
    /* Stop thread if running */
    if (fg->thread) {
        kthread_stop(fg->thread);
        fg->thread = NULL;
    }
    
    /* Cancel timer */
    del_timer_sync(&fg->timer);
    cancel_work_sync(&fg->work);
    
    /* Free buffer */
    if (fg->buffer) {
        vfree(fg->buffer);
        fg->buffer = NULL;
    }
    
    /* Destroy locks */
    mutex_destroy(&fg->lock);
    spin_lock_destroy(&fg->slock);
    
    kfree(fg);
    pr_info("%s: Frame generator destroyed\n", FRAME_GENERATOR_NAME);
}
EXPORT_SYMBOL(frame_generator_destroy);

/**
 * frame_generator_start - Start frame generation
 * @fg: Frame generator context
 * 
 * Returns: 0 on success, negative on error
 */
int frame_generator_start(struct frame_generator *fg)
{
    if (!fg) {
        return -EINVAL;
    }
    
    mutex_lock(&fg->lock);
    
    if (fg->active) {
        mutex_unlock(&fg->lock);
        pr_warn("%s: Frame generator already active\n", FRAME_GENERATOR_NAME);
        return -EBUSY;
    }
    
    pr_info("%s: Starting frame generator\n", FRAME_GENERATOR_NAME);
    
    fg->active = true;
    fg->frames_generated = 0;
    fg->frames_dropped = 0;
    fg->fps_actual = 0;
    fg->frame_count = 0;
    
    /* Start generation thread */
    fg->thread = kthread_run(frame_generator_thread, fg, "frame-gen");
    if (IS_ERR(fg->thread)) {
        int err = PTR_ERR(fg->thread);
        fg->thread = NULL;
        fg->active = false;
        mutex_unlock(&fg->lock);
        pr_err("%s: Failed to start thread: %d\n", FRAME_GENERATOR_NAME, err);
        return err;
    }
    
    mutex_unlock(&fg->lock);
    pr_info("%s: Frame generator started\n", FRAME_GENERATOR_NAME);
    return 0;
}
EXPORT_SYMBOL(frame_generator_start);

/**
 * frame_generator_stop - Stop frame generation
 * @fg: Frame generator context
 */
void frame_generator_stop(struct frame_generator *fg)
{
    if (!fg || !fg->active) {
        return;
    }
    
    pr_info("%s: Stopping frame generator\n", FRAME_GENERATOR_NAME);
    
    mutex_lock(&fg->lock);
    fg->active = false;
    mutex_unlock(&fg->lock);
    
    /* Wait for thread to finish */
    if (fg->thread) {
        kthread_stop(fg->thread);
        fg->thread = NULL;
    }
    
    pr_info("%s: Frame generator stopped\n", FRAME_GENERATOR_NAME);
}
EXPORT_SYMBOL(frame_generator_stop);

/**
 * frame_generator_get_frame - Get current frame
 * @fg: Frame generator context
 * @buf: Output buffer
 * @size: Buffer size
 * 
 * Returns: Frame size on success, negative on error
 */
int frame_generator_get_frame(struct frame_generator *fg, void *buf, u32 size)
{
    u32 copy_size;
    unsigned long flags;
    int ret = 0;
    
    if (!fg || !buf) {
        return -EINVAL;
    }
    
    spin_lock_irqsave(&fg->slock, flags);
    
    if (!fg->buffer_ready || !fg->buffer) {
        spin_unlock_irqrestore(&fg->slock, flags);
        return -ENODATA;
    }
    
    copy_size = min(size, fg->frame_size);
    if (copy_size < fg->frame_size) {
        spin_unlock_irqrestore(&fg->slock, flags);
        return -ENOSPC;
    }
    
    memcpy(buf, fg->buffer, copy_size);
    ret = copy_size;
    
    spin_unlock_irqrestore(&fg->slock, flags);
    return ret;
}
EXPORT_SYMBOL(frame_generator_get_frame);

/**
 * frame_generator_set_pattern - Set test pattern
 * @fg: Frame generator context
 * @pattern: Test pattern type
 * @param1: Pattern parameter 1
 * @param2: Pattern parameter 2
 * @param3: Pattern parameter 3
 */
void frame_generator_set_pattern(struct frame_generator *fg, u32 pattern,
                                 u32 param1, u32 param2, u32 param3)
{
    if (!fg) {
        return;
    }
    
    mutex_lock(&fg->lock);
    fg->pattern = pattern % PATTERN_MAX;
    fg->pattern_param1 = param1;
    fg->pattern_param2 = param2;
    fg->pattern_param3 = param3;
    mutex_unlock(&fg->lock);
    
    pr_info("%s: Pattern set to %u (params: %u, %u, %u)\n",
            FRAME_GENERATOR_NAME, pattern, param1, param2, param3);
}
EXPORT_SYMBOL(frame_generator_set_pattern);

/**
 * frame_generator_set_text - Set text overlay
 * @fg: Frame generator context
 * @text: Text string
 */
void frame_generator_set_text(struct frame_generator *fg, const char *text)
{
    if (!fg || !text) {
        return;
    }
    
    mutex_lock(&fg->lock);
    strncpy(fg->text, text, sizeof(fg->text) - 1);
    fg->text[sizeof(fg->text) - 1] = '\0';
    mutex_unlock(&fg->lock);
}
EXPORT_SYMBOL(frame_generator_set_text);

/**
 * frame_generator_get_info - Get frame generator information
 * @fg: Frame generator context
 * @info: Output info structure
 */
void frame_generator_get_info(struct frame_generator *fg, 
                              struct frame_generator_info *info)
{
    if (!fg || !info) {
        return;
    }
    
    mutex_lock(&fg->lock);
    info->width = fg->width;
    info->height = fg->height;
    info->fps = fg->fps;
    info->fps_actual = fg->fps_actual;
    info->format = fg->format;
    info->pattern = fg->pattern;
    info->frames_generated = fg->frames_generated;
    info->frames_dropped = fg->frames_dropped;
    info->bytes_generated = fg->bytes_generated;
    info->active = fg->active;
    mutex_unlock(&fg->lock);
}
EXPORT_SYMBOL(frame_generator_get_info);

/* ==================== Module Initialization ==================== */

/**
 * fg_init - Module initialization
 */
static int __init fg_init(void)
{
    int err;
    
    pr_info("%s: Frame Generator v%s loading...\n", 
            FRAME_GENERATOR_NAME, FRAME_GENERATOR_VERSION);
    
    /* Create device class */
    fg_class = class_create(THIS_MODULE, FRAME_GENERATOR_NAME);
    if (IS_ERR(fg_class)) {
        pr_err("%s: Failed to create device class\n", FRAME_GENERATOR_NAME);
        return PTR_ERR(fg_class);
    }
    
    /* Allocate device number */
    err = alloc_chrdev_region(&fg_devt, 0, 1, FRAME_GENERATOR_NAME);
    if (err < 0) {
        pr_err("%s: Failed to allocate device number\n", FRAME_GENERATOR_NAME);
        class_destroy(fg_class);
        return err;
    }
    
    /* Create device */
    fg_device = device_create(fg_class, NULL, fg_devt, NULL,
                             FRAME_GENERATOR_NAME);
    if (IS_ERR(fg_device)) {
        pr_err("%s: Failed to create device\n", FRAME_GENERATOR_NAME);
        unregister_chrdev_region(fg_devt, 1);
        class_destroy(fg_class);
        return PTR_ERR(fg_device);
    }
    
    /* Create default frame generator */
    g_generator = frame_generator_create(DEFAULT_WIDTH, DEFAULT_HEIGHT,
                                        DEFAULT_FPS, FORMAT_YUYV);
    if (!g_generator) {
        pr_warn("%s: Failed to create default frame generator\n", 
                FRAME_GENERATOR_NAME);
    } else {
        /* Start generation by default */
        frame_generator_start(g_generator);
    }
    
    pr_info("%s: Driver loaded successfully\n", FRAME_GENERATOR_NAME);
    return 0;
}

/**
 * fg_exit - Module cleanup
 */
static void __exit fg_exit(void)
{
    pr_info("%s: Frame Generator unloading...\n", FRAME_GENERATOR_NAME);
    
    /* Destroy frame generator */
    if (g_generator) {
        frame_generator_destroy(g_generator);
        g_generator = NULL;
    }
    
    /* Destroy device */
    if (fg_device) {
        device_destroy(fg_class, fg_devt);
    }
    
    /* Unregister device */
    if (fg_devt) {
        unregister_chrdev_region(fg_devt, 1);
    }
    
    /* Destroy class */
    if (fg_class) {
        class_destroy(fg_class);
    }
    
    pr_info("%s: Driver unloaded\n", FRAME_GENERATOR_NAME);
}

module_init(fg_init);
module_exit(fg_exit);

/* ==================== Module Parameters ==================== */

static int fg_width = DEFAULT_WIDTH;
module_param(fg_width, int, 0644);
MODULE_PARM_DESC(fg_width, "Default frame width");

static int fg_height = DEFAULT_HEIGHT;
module_param(fg_height, int, 0644);
MODULE_PARM_DESC(fg_height, "Default frame height");

static int fg_fps = DEFAULT_FPS;
module_param(fg_fps, int, 0644);
MODULE_PARM_DESC(fg_fps, "Default frame rate");

static int fg_format = FORMAT_YUYV;
module_param(fg_format, int, 0644);
MODULE_PARM_DESC(fg_format, "Default pixel format (0=YUYV, 1=UYVY, 2=RGB24, 3=RGB32, 4=GREY, 5=YUV420, 6=YVU420)");

static int fg_pattern = PATTERN_COLOR_BARS;
module_param(fg_pattern, int, 0644);
MODULE_PARM_DESC(fg_pattern, "Default test pattern (0=Color bars, 1=SMPTE bars, 2=Checkerboard, 3=Gradient, 4=Moving bar, 5=Noise, 6=Color wheel, 7=Text, 8=Clock, 9=Movie)");

/* ==================== Debug Information ==================== */

/**
 * frame_generator_show_info - Show frame generator information
 */
void frame_generator_show_info(void)
{
    if (!g_generator) {
        pr_info("%s: No frame generator active\n", FRAME_GENERATOR_NAME);
        return;
    }
    
    pr_info("%s: Frame Generator Information:\n", FRAME_GENERATOR_NAME);
    pr_info("  Resolution: %ux%u\n", g_generator->width, g_generator->height);
    pr_info("  Format: %u\n", g_generator->format);
    pr_info("  FPS: %u (actual: %u)\n", g_generator->fps, g_generator->fps_actual);
    pr_info("  Pattern: %u\n", g_generator->pattern);
    pr_info("  Frames generated: %llu\n", g_generator->frames_generated);
    pr_info("  Frames dropped: %llu\n", g_generator->frames_dropped);
    pr_info("  Bytes generated: %llu\n", g_generator->bytes_generated);
    pr_info("  Active: %s\n", g_generator->active ? "Yes" : "No");
}
EXPORT_SYMBOL(frame_generator_show_info);

/* Export symbols for use by other modules */
EXPORT_SYMBOL(frame_generator_start);
EXPORT_SYMBOL(frame_generator_stop);
EXPORT_SYMBOL(frame_generator_get_frame);
EXPORT_SYMBOL(frame_generator_set_pattern);
EXPORT_SYMBOL(frame_generator_set_text);
EXPORT_SYMBOL(frame_generator_get_info);
EXPORT_SYMBOL(frame_generator_show_info);

/* ==================== Example Usage ==================== */

/*
 * Example usage:
 * 
 * 1. Create frame generator:
 *    struct frame_generator *fg = frame_generator_create(1920, 1080, 30, FORMAT_YUYV);
 * 
 * 2. Start generation:
 *    frame_generator_start(fg);
 * 
 * 3. Set test pattern:
 *    frame_generator_set_pattern(fg, PATTERN_COLOR_BARS, 0, 0, 0);
 * 
 * 4. Get frame:
 *    u8 *frame = kmalloc(fg->frame_size, GFP_KERNEL);
 *    int ret = frame_generator_get_frame(fg, frame, fg->frame_size);
 * 
 * 5. Set text overlay:
 *    frame_generator_set_text(fg, "Test Frame");
 * 
 * 6. Stop generation:
 *    frame_generator_stop(fg);
 * 
 * 7. Destroy:
 *    frame_generator_destroy(fg);
 */
