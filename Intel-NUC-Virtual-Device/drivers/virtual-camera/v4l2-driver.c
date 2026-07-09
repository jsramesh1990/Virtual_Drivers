/*
 * v4l2-driver.c - V4L2 Virtual Camera Driver for Intel NUC
 * 
 * This driver implements a virtual V4L2 camera device for video
 * simulation on Intel NUC platforms.
 * 
 * Version: 1.0
 * Author: Virtual Device Platform Team
 * License: GPL v2
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/fs.h>
#include <linux/vmalloc.h>
#include <linux/slab.h>
#include <linux/videodev2.h>
#include <media/v4l2-device.h>
#include <media/v4l2-ioctl.h>
#include <media/v4l2-fh.h>
#include <media/videobuf2-vmalloc.h>
#include <media/v4l2-ctrls.h>
#include <media/v4l2-event.h>

#define V4L2_NAME "virt-cam"
#define V4L2_VERSION "1.0.0"
#define V4L2_MAX_WIDTH 3840
#define V4L2_MAX_HEIGHT 2160
#define V4L2_MIN_WIDTH 64
#define V4L2_MIN_HEIGHT 64

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Intel NUC Virtual Device Platform");
MODULE_DESCRIPTION("V4L2 Virtual Camera Driver for Intel NUC");
MODULE_VERSION(V4L2_VERSION);

/* Video format structure */
struct vcam_format {
    u32 pixelformat;
    u32 width;
    u32 height;
    u32 bytesperline;
    u32 sizeimage;
    int bpp;
};

/* Camera device structure */
struct vcam_device {
    struct v4l2_device v4l2_dev;
    struct video_device *vdev;
    struct vb2_queue queue;
    struct mutex lock;
    spinlock_t slock;
    struct vcam_format format;
    void *buffer;
    int buffer_size;
    int fps;
    bool streaming;
    struct list_head list;
};

/* Global list */
static LIST_HEAD(vcam_devices);
static DEFINE_MUTEX(vcam_lock);

/* Forward declarations */
static int vcam_querycap(struct file *file, void *priv,
                         struct v4l2_capability *cap);
static int vcam_enum_fmt(struct file *file, void *priv,
                         struct v4l2_fmtdesc *f);
static int vcam_g_fmt(struct file *file, void *priv,
                      struct v4l2_format *f);
static int vcam_s_fmt(struct file *file, void *priv,
                      struct v4l2_format *f);
static int vcam_reqbufs(struct file *file, void *priv,
                        struct v4l2_requestbuffers *rb);
static int vcam_qbuf(struct file *file, void *priv,
                     struct v4l2_buffer *b);
static int vcam_dqbuf(struct file *file, void *priv,
                      struct v4l2_buffer *b);
static int vcam_streamon(struct file *file, void *priv,
                         enum v4l2_buf_type type);
static int vcam_streamoff(struct file *file, void *priv,
                          enum v4l2_buf_type type);

/* V4L2 IOCTL operations */
static const struct v4l2_ioctl_ops vcam_ioctl_ops = {
    .vidioc_querycap = vcam_querycap,
    .vidioc_enum_fmt_vid_cap = vcam_enum_fmt,
    .vidioc_g_fmt_vid_cap = vcam_g_fmt,
    .vidioc_s_fmt_vid_cap = vcam_s_fmt,
    .vidioc_reqbufs = vcam_reqbufs,
    .vidioc_querybuf = NULL,
    .vidioc_qbuf = vcam_qbuf,
    .vidioc_dqbuf = vcam_dqbuf,
    .vidioc_streamon = vcam_streamon,
    .vidioc_streamoff = vcam_streamoff,
};

/* Video buffer operations */
static int vcam_queue_setup(struct vb2_queue *q,
                           unsigned int *nbuffers,
                           unsigned int *nplanes,
                           unsigned int sizes[],
                           struct device *alloc_devs[]);
static void vcam_buf_queue(struct vb2_buffer *vb);
static int vcam_start_streaming(struct vb2_queue *q, unsigned int count);
static void vcam_stop_streaming(struct vb2_queue *q);

/* VB2 queue operations */
static const struct vb2_ops vcam_vb2_ops = {
    .queue_setup = vcam_queue_setup,
    .buf_queue = vcam_buf_queue,
    .start_streaming = vcam_start_streaming,
    .stop_streaming = vcam_stop_streaming,
};

/* File operations */
static const struct v4l2_file_operations vcam_fops = {
    .owner = THIS_MODULE,
    .open = v4l2_fh_open,
    .release = v4l2_fh_release,
    .unlocked_ioctl = video_ioctl2,
    .mmap = vb2_fop_mmap,
    .poll = vb2_fop_poll,
};

/* Video device template */
static const struct video_device vcam_vdev_template = {
    .name = V4L2_NAME,
    .fops = &vcam_fops,
    .ioctl_ops = &vcam_ioctl_ops,
    .release = video_device_release_empty,
    .device_caps = V4L2_CAP_VIDEO_CAPTURE | V4L2_CAP_STREAMING |
                   V4L2_CAP_READWRITE,
};

/* Supported formats */
static const struct vcam_format vcam_formats[] = {
    { V4L2_PIX_FMT_YUYV, 1920, 1080, 3840, 4147200, 2 },
    { V4L2_PIX_FMT_RGB24, 1920, 1080, 5760, 6220800, 3 },
    { V4L2_PIX_FMT_RGB32, 1920, 1080, 7680, 8294400, 4 },
    { V4L2_PIX_FMT_GREY, 1920, 1080, 1920, 2073600, 1 },
};

/* Query capability */
static int vcam_querycap(struct file *file, void *priv,
                         struct v4l2_capability *cap)
{
    strcpy(cap->driver, V4L2_NAME);
    strcpy(cap->card, "Virtual Camera");
    snprintf(cap->bus_info, sizeof(cap->bus_info),
             "platform:%s", V4L2_NAME);
    cap->device_caps = V4L2_CAP_VIDEO_CAPTURE | V4L2_CAP_STREAMING |
                       V4L2_CAP_READWRITE;
    cap->capabilities = cap->device_caps | V4L2_CAP_DEVICE_CAPS;
    
    return 0;
}

/* Enumerate formats */
static int vcam_enum_fmt(struct file *file, void *priv,
                         struct v4l2_fmtdesc *f)
{
    if (f->index >= ARRAY_SIZE(vcam_formats)) {
        return -EINVAL;
    }
    
    f->pixelformat = vcam_formats[f->index].pixelformat;
    f->type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    sprintf(f->description, "Virtual Format %d", f->index);
    
    return 0;
}

/* Get format */
static int vcam_g_fmt(struct file *file, void *priv,
                      struct v4l2_format *f)
{
    struct vcam_device *vcam = video_drvdata(file);
    struct vcam_format *fmt = &vcam->format;
    
    if (f->type != V4L2_BUF_TYPE_VIDEO_CAPTURE) {
        return -EINVAL;
    }
    
    f->fmt.pix.width = fmt->width;
    f->fmt.pix.height = fmt->height;
    f->fmt.pix.pixelformat = fmt->pixelformat;
    f->fmt.pix.bytesperline = fmt->bytesperline;
    f->fmt.pix.sizeimage = fmt->sizeimage;
    f->fmt.pix.field = V4L2_FIELD_NONE;
    
    return 0;
}

/* Set format */
static int vcam_s_fmt(struct file *file, void *priv,
                      struct v4l2_format *f)
{
    struct vcam_device *vcam = video_drvdata(file);
    struct vcam_format *fmt = &vcam->format;
    int i;
    
    if (f->type != V4L2_BUF_TYPE_VIDEO_CAPTURE) {
        return -EINVAL;
    }
    
    if (vcam->streaming) {
        return -EBUSY;
    }
    
    /* Find matching format */
    for (i = 0; i < ARRAY_SIZE(vcam_formats); i++) {
        if (vcam_formats[i].pixelformat == f->fmt.pix.pixelformat) {
            fmt->pixelformat = vcam_formats[i].pixelformat;
            fmt->bpp = vcam_formats[i].bpp;
            break;
        }
    }
    
    if (i == ARRAY_SIZE(vcam_formats)) {
        return -EINVAL;
    }
    
    /* Adjust width/height */
    fmt->width = clamp(f->fmt.pix.width, V4L2_MIN_WIDTH, V4L2_MAX_WIDTH);
    fmt->height = clamp(f->fmt.pix.height, V4L2_MIN_HEIGHT, V4L2_MAX_HEIGHT);
    
    /* Calculate bytes per line and image size */
    fmt->bytesperline = fmt->width * fmt->bpp;
    fmt->sizeimage = fmt->bytesperline * fmt->height;
    
    /* Update buffer */
    if (vcam->buffer) {
        vfree(vcam->buffer);
    }
    vcam->buffer = vmalloc(fmt->sizeimage);
    if (!vcam->buffer) {
        return -ENOMEM;
    }
    vcam->buffer_size = fmt->sizeimage;
    
    /* Return current format */
    f->fmt.pix.width = fmt->width;
    f->fmt.pix.height = fmt->height;
    f->fmt.pix.pixelformat = fmt->pixelformat;
    f->fmt.pix.bytesperline = fmt->bytesperline;
    f->fmt.pix.sizeimage = fmt->sizeimage;
    f->fmt.pix.field = V4L2_FIELD_NONE;
    
    return 0;
}

/* Request buffers */
static int vcam_reqbufs(struct file *file, void *priv,
                        struct v4l2_requestbuffers *rb)
{
    struct vcam_device *vcam = video_drvdata(file);
    int ret;
    
    if (rb->type != V4L2_BUF_TYPE_VIDEO_CAPTURE) {
        return -EINVAL;
    }
    
    if (vcam->streaming) {
        return -EBUSY;
    }
    
    ret = vb2_reqbufs(&vcam->queue, rb);
    if (ret < 0) {
        return ret;
    }
    
    return 0;
}

/* Queue buffer */
static int vcam_qbuf(struct file *file, void *priv,
                     struct v4l2_buffer *b)
{
    struct vcam_device *vcam = video_drvdata(file);
    
    return vb2_qbuf(&vcam->queue, b);
}

/* Dequeue buffer */
static int vcam_dqbuf(struct file *file, void *priv,
                      struct v4l2_buffer *b)
{
    struct vcam_device *vcam = video_drvdata(file);
    
    return vb2_dqbuf(&vcam->queue, b, file->f_flags & O_NONBLOCK);
}

/* Stream on */
static int vcam_streamon(struct file *file, void *priv,
                         enum v4l2_buf_type type)
{
    struct vcam_device *vcam = video_drvdata(file);
    int ret;
    
    if (type != V4L2_BUF_TYPE_VIDEO_CAPTURE) {
        return -EINVAL;
    }
    
    ret = vb2_streamon(&vcam->queue, type);
    if (ret < 0) {
        return ret;
    }
    
    vcam->streaming = true;
    return 0;
}

/* Stream off */
static int vcam_streamoff(struct file *file, void *priv,
                          enum v4l2_buf_type type)
{
    struct vcam_device *vcam = video_drvdata(file);
    
    if (type != V4L2_BUF_TYPE_VIDEO_CAPTURE) {
        return -EINVAL;
    }
    
    vcam->streaming = false;
    return vb2_streamoff(&vcam->queue, type);
}

/* VB2 queue setup */
static int vcam_queue_setup(struct vb2_queue *q,
                           unsigned int *nbuffers,
                           unsigned int *nplanes,
                           unsigned int sizes[],
                           struct device *alloc_devs[])
{
    struct vcam_device *vcam = vb2_get_drv_priv(q);
    struct vcam_format *fmt = &vcam->format;
    
    if (*nplanes) {
        if (sizes[0] < fmt->sizeimage) {
            return -EINVAL;
        }
    } else {
        sizes[0] = fmt->sizeimage;
    }
    
    *nbuffers = clamp(*nbuffers, 2U, 32U);
    *nplanes = 1;
    
    return 0;
}

/* VB2 buffer queue */
static void vcam_buf_queue(struct vb2_buffer *vb)
{
    struct vcam_device *vcam = vb2_get_drv_priv(vb->vb2_queue);
    struct vcam_format *fmt = &vcam->format;
    void *ptr = vb2_plane_vaddr(vb, 0);
    
    /* Generate test pattern */
    memset(ptr, 0x80, fmt->sizeimage);  /* Gray pattern */
    
    /* Fill with test pattern */
    vcam_generate_test_pattern(ptr, fmt->width, fmt->height,
                               fmt->pixelformat);
    
    vb2_set_plane_payload(vb, 0, fmt->sizeimage);
    vb2_buffer_done(vb, VB2_BUF_STATE_DONE);
}

/* VB2 start streaming */
static int vcam_start_streaming(struct vb2_queue *q, unsigned int count)
{
    struct vcam_device *vcam = vb2_get_drv_priv(q);
    
    vcam->streaming = true;
    return 0;
}

/* VB2 stop streaming */
static void vcam_stop_streaming(struct vb2_queue *q)
{
    struct vcam_device *vcam = vb2_get_drv_priv(q);
    
    vcam->streaming = false;
}

/* Generate test pattern */
void vcam_generate_test_pattern(void *ptr, int width, int height,
                                u32 pixelformat)
{
    int x, y;
    u8 *p = ptr;
    int bpp = 2; /* Default for YUYV */
    int line_width = width * bpp;
    
    switch (pixelformat) {
        case V4L2_PIX_FMT_YUYV:
            /* Generate color bars */
            for (y = 0; y < height; y++) {
                for (x = 0; x < width; x++) {
                    int pos = y * line_width + x * bpp;
                    
                    /* Y = luma, U = blue difference, V = red difference */
                    p[pos] = (y * 255) / height;  /* Y */
                    p[pos + 1] = (x * 255) / width; /* U */
                    p[pos + 2] = 128; /* V */
                }
            }
            break;
            
        case V4L2_PIX_FMT_RGB24:
            for (y = 0; y < height; y++) {
                for (x = 0; x < width; x++) {
                    int pos = y * line_width + x * 3;
                    p[pos] = (x * 255) / width;     /* R */
                    p[pos + 1] = (y * 255) / height; /* G */
                    p[pos + 2] = ((x + y) * 255) / (width + height); /* B */
                }
            }
            break;
            
        default:
            break;
    }
}
EXPORT_SYMBOL(vcam_generate_test_pattern);

/* Module initialization */
static int __init vcam_init(void)
{
    struct vcam_device *vcam;
    int ret;
    
    pr_info("%s: V4L2 Virtual Camera v%s loading...\n", 
            V4L2_NAME, V4L2_VERSION);
    
    /* Allocate device */
    vcam = kzalloc(sizeof(*vcam), GFP_KERNEL);
    if (!vcam) {
        return -ENOMEM;
    }
    
    /* Initialize */
    mutex_init(&vcam->lock);
    spin_lock_init(&vcam->slock);
    
    /* Set default format */
    vcam->format = vcam_formats[0];
    vcam->format.width = 1920;
    vcam->format.height = 1080;
    vcam->format.bytesperline = 1920 * 2;
    vcam->format.sizeimage = 1920 * 1080 * 2;
    vcam->fps = 30;
    vcam->streaming = false;
    
    /* Allocate buffer */
    vcam->buffer = vmalloc(vcam->format.sizeimage);
    if (!vcam->buffer) {
        kfree(vcam);
        return -ENOMEM;
    }
    vcam->buffer_size = vcam->format.sizeimage;
    
    /* Initialize V4L2 device */
    ret = v4l2_device_register(NULL, &vcam->v4l2_dev);
    if (ret < 0) {
        vfree(vcam->buffer);
        kfree(vcam);
        return ret;
    }
    
    /* Initialize VB2 queue */
    memset(&vcam->queue, 0, sizeof(vcam->queue));
    vcam->queue.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
    vcam->queue.io_modes = VB2_MMAP | VB2_USERPTR | VB2_READ;
    vcam->queue.drv_priv = vcam;
    vcam->queue.buf_struct_size = sizeof(struct vb2_buffer);
    vcam->queue.ops = &vcam_vb2_ops;
    vcam->queue.mem_ops = &vb2_vmalloc_memops;
    vcam->queue.timestamp_flags = V4L2_BUF_FLAG_TIMESTAMP_MONOTONIC;
    ret = vb2_queue_init(&vcam->queue);
    if (ret < 0) {
        v4l2_device_unregister(&vcam->v4l2_dev);
        vfree(vcam->buffer);
        kfree(vcam);
        return ret;
    }
    
    /* Allocate video device */
    vcam->vdev = video_device_alloc();
    if (!vcam->vdev) {
        vb2_queue_release(&vcam->queue);
        v4l2_device_unregister(&vcam->v4l2_dev);
        vfree(vcam->buffer);
        kfree(vcam);
        return -ENOMEM;
    }
    
    *vcam->vdev = vcam_vdev_template;
    vcam->vdev->v4l2_dev = &vcam->v4l2_dev;
    vcam->vdev->queue = &vcam->queue;
    vcam->vdev->lock = &vcam->lock;
    video_set_drvdata(vcam->vdev, vcam);
    
    /* Register video device */
    ret = video_register_device(vcam->vdev, VFL_TYPE_VIDEO, -1);
    if (ret < 0) {
        video_device_release(vcam->vdev);
        vb2_queue_release(&vcam->queue);
        v4l2_device_unregister(&vcam->v4l2_dev);
        vfree(vcam->buffer);
        kfree(vcam);
        return ret;
    }
    
    /* Add to global list */
    mutex_lock(&vcam_lock);
    list_add(&vcam->list, &vcam_devices);
    mutex_unlock(&vcam_lock);
    
    pr_info("%s: Virtual camera device registered: %s\n", 
            V4L2_NAME, video_device_node_name(vcam->vdev));
    pr_info("%s: Driver loaded successfully\n", V4L2_NAME);
    
    return 0;
}

/* Module cleanup */
static void __exit vcam_exit(void)
{
    struct vcam_device *vcam, *tmp;
    
    pr_info("%s: V4L2 Virtual Camera unloading...\n", V4L2_NAME);
    
    /* Remove all devices */
    list_for_each_entry_safe(vcam, tmp, &vcam_devices, list) {
        list_del(&vcam->list);
        
        video_unregister_device(vcam->vdev);
        video_device_release(vcam->vdev);
        vb2_queue_release(&vcam->queue);
        v4l2_device_unregister(&vcam->v4l2_dev);
        
        if (vcam->buffer) {
            vfree(vcam->buffer);
        }
        
        mutex_destroy(&vcam->lock);
        kfree(vcam);
    }
    
    pr_info("%s: Driver unloaded\n", V4L2_NAME);
}

module_init(vcam_init);
module_exit(vcam_exit);
