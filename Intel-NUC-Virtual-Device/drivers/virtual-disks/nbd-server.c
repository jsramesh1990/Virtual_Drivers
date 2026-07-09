/*
 * nbd-server.c - Network Block Device (NBD) Server Driver for Intel NUC
 * 
 * This driver implements an NBD server for exporting block devices
 * over the network for virtualization and storage on Intel NUC platforms.
 * 
 * Version: 1.0.0
 * Author: Intel NUC Virtual Device Platform Team
 * License: GPL v2
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/fs.h>
#include <linux/blkdev.h>
#include <linux/genhd.h>
#include <linux/slab.h>
#include <linux/mutex.h>
#include <linux/sched.h>
#include <linux/delay.h>
#include <linux/timer.h>
#include <linux/workqueue.h>
#include <linux/socket.h>
#include <linux/in.h>
#include <linux/inet.h>
#include <linux/net.h>
#include <linux/tcp.h>
#include <linux/kthread.h>
#include <linux/completion.h>
#include <linux/uaccess.h>
#include <linux/string.h>
#include <linux/errno.h>
#include <linux/wait.h>
#include <linux/list.h>
#include <linux/spinlock.h>
#include <linux/random.h>
#include <linux/version.h>

#define NBD_DRIVER_NAME "virt-nbd"
#define NBD_VERSION "1.0.0"
#define NBD_MAX_DEVICES 16
#define NBD_DEFAULT_PORT 10809
#define NBD_BUFFER_SIZE 65536
#define NBD_TIMEOUT 30

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Intel NUC Virtual Device Platform");
MODULE_DESCRIPTION("Network Block Device Server for Intel NUC");
MODULE_VERSION(NBD_VERSION);

/* NBD Protocol Constants */
#define NBD_REQUEST_MAGIC 0x25609513
#define NBD_REPLY_MAGIC 0x67446698
#define NBD_CMD_READ 0
#define NBD_CMD_WRITE 1
#define NBD_CMD_DISC 2
#define NBD_CMD_FLUSH 3
#define NBD_CMD_TRIM 4
#define NBD_CMD_CACHE 5
#define NBD_CMD_WRITE_ZEROES 6
#define NBD_FLAG_HAS_FLAGS (1 << 0)
#define NBD_FLAG_READ_ONLY (1 << 1)
#define NBD_FLAG_SEND_FLUSH (1 << 2)
#define NBD_FLAG_SEND_FUA (1 << 3)
#define NBD_FLAG_ROTATIONAL (1 << 4)
#define NBD_FLAG_SEND_TRIM (1 << 5)
#define NBD_FLAG_SEND_WRITE_ZEROES (1 << 6)
#define NBD_FLAG_SEND_CACHE (1 << 7)
#define NBD_FLAG_CAN_MULTI_CONN (1 << 8)

/* NBD Request/Reply Structures */
struct nbd_request {
    __be32 magic;
    __be32 type;
    __be64 handle;
    __be64 from;
    __be32 len;
} __attribute__((packed));

struct nbd_reply {
    __be32 magic;
    __be32 error;
    __be64 handle;
} __attribute__((packed));

struct nbd_option {
    __be64 magic;
    __be32 option;
    __be32 length;
} __attribute__((packed));

/* NBD Device Structure */
struct nbd_device {
    struct gendisk *disk;
    struct request_queue *queue;
    struct block_device *bdev;
    struct socket *sock;
    struct task_struct *thread;
    struct mutex lock;
    struct completion completion;
    wait_queue_head_t wait;
    struct timer_list timer;
    struct list_head list;
    struct work_struct work;
    
    char name[64];
    char export_name[128];
    char backing_file[256];
    int minor;
    int port;
    bool active;
    bool readonly;
    bool connected;
    bool exporting;
    u64 size;
    u32 flags;
    u32 timeout;
    u32 max_connections;
    u32 current_connections;
    spinlock_t conn_lock;
};

/* NBD Connection Structure */
struct nbd_connection {
    struct nbd_device *dev;
    struct socket *sock;
    struct task_struct *thread;
    struct list_head list;
    struct mutex lock;
    bool active;
    u64 handle;
    spinlock_t handle_lock;
};

/* Global Variables */
static LIST_HEAD(nbd_devices);
static DEFINE_MUTEX(nbd_devices_lock);
static int nbd_major;
static struct class *nbd_class;
static struct workqueue_struct *nbd_wq;

/* Forward Declarations */
static int nbd_open(struct block_device *bdev, fmode_t mode);
static void nbd_release(struct gendisk *disk, fmode_t mode);
static int nbd_ioctl(struct block_device *bdev, fmode_t mode,
                     unsigned int cmd, unsigned long arg);
static void nbd_submit_bio(struct bio *bio);

/* Block Device Operations */
static const struct block_device_operations nbd_fops = {
    .owner = THIS_MODULE,
    .open = nbd_open,
    .release = nbd_release,
    .ioctl = nbd_ioctl,
};

/* Queue Operations */
static const struct blk_mq_ops nbd_mq_ops = {
    .queue_rq = nbd_submit_bio,
};

/* ==================== NBD Protocol Functions ==================== */

/**
 * nbd_send_reply - Send NBD reply to client
 * @conn: NBD connection
 * @handle: Request handle
 * @error: Error code (0 for success)
 * @data: Reply data (for READ commands)
 * @len: Length of data
 * 
 * Returns: 0 on success, negative on error
 */
static int nbd_send_reply(struct nbd_connection *conn, u64 handle,
                          int error, void *data, u32 len)
{
    struct nbd_reply reply;
    struct msghdr msg;
    struct kvec iov[2];
    int ret;
    int iovcnt = 1;
    struct socket *sock = conn->sock;
    
    if (!sock || !conn->active) {
        return -ENOTCONN;
    }
    
    /* Build reply header */
    reply.magic = cpu_to_be32(NBD_REPLY_MAGIC);
    reply.error = cpu_to_be32(error);
    reply.handle = cpu_to_be64(handle);
    
    /* Prepare message */
    memset(&msg, 0, sizeof(msg));
    iov[0].iov_base = &reply;
    iov[0].iov_len = sizeof(reply);
    
    if (data && len > 0 && error == 0) {
        iov[1].iov_base = data;
        iov[1].iov_len = len;
        iovcnt = 2;
    }
    
    /* Send reply */
    ret = kernel_sendmsg(sock, &msg, iov, iovcnt, 
                        sizeof(reply) + (data ? len : 0));
    if (ret < 0) {
        pr_err("%s: Failed to send reply: %d\n", 
               NBD_DRIVER_NAME, ret);
        return ret;
    }
    
    return 0;
}

/**
 * nbd_handle_request - Handle NBD client request
 * @conn: NBD connection
 * @req: NBD request structure
 * @data: Request data buffer
 * 
 * Returns: 0 on success, negative on error
 */
static int nbd_handle_request(struct nbd_connection *conn,
                              struct nbd_request *req, void *data)
{
    struct nbd_device *dev = conn->dev;
    struct block_device *bdev = dev->bdev;
    sector_t sector;
    u32 type;
    u32 len;
    u64 from;
    void *buf;
    int ret = 0;
    struct bio *bio;
    struct page *page;
    u64 handle;
    u32 error = 0;
    
    type = be32_to_cpu(req->type);
    handle = be64_to_cpu(req->handle);
    from = be64_to_cpu(req->from);
    len = be32_to_cpu(req->len);
    sector = from >> 9;
    
    pr_debug("%s: Request type=%u handle=%llu from=%llu len=%u\n",
             NBD_DRIVER_NAME, type, handle, from, len);
    
    switch (type) {
        case NBD_CMD_READ:
            /* Read from block device */
            buf = kmalloc(len, GFP_KERNEL);
            if (!buf) {
                error = -ENOMEM;
                break;
            }
            
            /* Perform read via bio */
            page = virt_to_page(buf);
            bio = bio_alloc(GFP_KERNEL, 1);
            if (!bio) {
                kfree(buf);
                error = -ENOMEM;
                break;
            }
            
            bio_set_dev(bio, bdev);
            bio->bi_iter.bi_sector = sector;
            bio_add_page(bio, page, len, 0);
            bio->bi_opf = REQ_OP_READ;
            
            ret = submit_bio_wait(bio);
            bio_put(bio);
            
            if (ret < 0) {
                error = -EIO;
                kfree(buf);
                break;
            }
            
            /* Send data to client */
            ret = nbd_send_reply(conn, handle, 0, buf, len);
            kfree(buf);
            break;
            
        case NBD_CMD_WRITE:
            /* Write to block device */
            buf = data;
            if (!buf) {
                error = -EINVAL;
                break;
            }
            
            /* Perform write via bio */
            page = virt_to_page(buf);
            bio = bio_alloc(GFP_KERNEL, 1);
            if (!bio) {
                error = -ENOMEM;
                break;
            }
            
            bio_set_dev(bio, bdev);
            bio->bi_iter.bi_sector = sector;
            bio_add_page(bio, page, len, 0);
            bio->bi_opf = REQ_OP_WRITE;
            
            ret = submit_bio_wait(bio);
            bio_put(bio);
            
            if (ret < 0) {
                error = -EIO;
                break;
            }
            
            /* Send success reply */
            ret = nbd_send_reply(conn, handle, 0, NULL, 0);
            break;
            
        case NBD_CMD_DISC:
            /* Disconnect */
            pr_info("%s: Client requested disconnect\n", NBD_DRIVER_NAME);
            conn->active = false;
            return -ESHUTDOWN;
            
        case NBD_CMD_FLUSH:
            /* Flush writes */
            ret = blkdev_issue_flush(bdev, GFP_KERNEL, NULL);
            error = ret < 0 ? -EIO : 0;
            nbd_send_reply(conn, handle, error, NULL, 0);
            break;
            
        case NBD_CMD_TRIM:
            /* Discard blocks */
            ret = blkdev_issue_discard(bdev, sector, len >> 9,
                                       GFP_KERNEL, 0);
            error = ret < 0 ? -EIO : 0;
            nbd_send_reply(conn, handle, error, NULL, 0);
            break;
            
        default:
            pr_warn("%s: Unknown NBD command %u\n", NBD_DRIVER_NAME, type);
            error = -EOPNOTSUPP;
            nbd_send_reply(conn, handle, error, NULL, 0);
            break;
    }
    
    return ret;
}

/**
 * nbd_server_thread - Main NBD server thread
 * @data: NBD device pointer
 * 
 * Returns: 0 on success, negative on error
 */
static int nbd_server_thread(void *data)
{
    struct nbd_device *dev = data;
    struct socket *sock = dev->sock;
    struct nbd_request req;
    struct msghdr msg;
    struct kvec iov;
    void *buf;
    int ret;
    struct nbd_connection *conn;
    int err;
    
    pr_info("%s: NBD server thread started for %s\n", 
            NBD_DRIVER_NAME, dev->name);
    
    conn = kzalloc(sizeof(struct nbd_connection), GFP_KERNEL);
    if (!conn) {
        pr_err("%s: Failed to allocate connection\n", NBD_DRIVER_NAME);
        return -ENOMEM;
    }
    
    conn->dev = dev;
    conn->sock = sock;
    conn->active = true;
    mutex_init(&conn->lock);
    spin_lock_init(&conn->handle_lock);
    
    /* Allocate buffer for data */
    buf = kmalloc(NBD_BUFFER_SIZE, GFP_KERNEL);
    if (!buf) {
        kfree(conn);
        pr_err("%s: Failed to allocate buffer\n", NBD_DRIVER_NAME);
        return -ENOMEM;
    }
    
    /* Send NBD handshake */
    if (dev->flags & NBD_FLAG_HAS_FLAGS) {
        u64 flags = cpu_to_be64(dev->flags);
        ret = kernel_sendmsg(sock, NULL, &(struct kvec){
            .iov_base = &flags,
            .iov_len = sizeof(flags)
        }, 1, sizeof(flags));
        if (ret < 0) {
            pr_err("%s: Failed to send flags: %d\n", 
                   NBD_DRIVER_NAME, ret);
            goto out;
        }
    }
    
    pr_info("%s: NBD server running on %s port %d\n",
            NBD_DRIVER_NAME, dev->name, dev->port);
    
    /* Main request loop */
    while (dev->active && conn->active && !kthread_should_stop()) {
        /* Receive request header */
        memset(&msg, 0, sizeof(msg));
        iov.iov_base = &req;
        iov.iov_len = sizeof(req);
        
        ret = kernel_recvmsg(sock, &msg, &iov, 1, sizeof(req), 0);
        if (ret < 0) {
            if (ret != -EAGAIN && ret != -EINTR) {
                pr_err("%s: Recv header error: %d\n", 
                       NBD_DRIVER_NAME, ret);
            }
            continue;
        }
        
        if (ret == 0) {
            pr_info("%s: Client disconnected\n", NBD_DRIVER_NAME);
            break;
        }
        
        /* Validate request */
        if (be32_to_cpu(req.magic) != NBD_REQUEST_MAGIC) {
            pr_err("%s: Invalid magic: 0x%x\n", 
                   NBD_DRIVER_NAME, be32_to_cpu(req.magic));
            break;
        }
        
        /* Handle request */
        err = nbd_handle_request(conn, &req, buf);
        if (err < 0) {
            if (err == -ESHUTDOWN) {
                break;
            }
            pr_err("%s: Request handling failed: %d\n", 
                   NBD_DRIVER_NAME, err);
        }
    }
    
out:
    kfree(buf);
    kfree(conn);
    
    pr_info("%s: NBD server thread stopped for %s\n", 
            NBD_DRIVER_NAME, dev->name);
    
    return 0;
}

/* ==================== Block Device Functions ==================== */

/**
 * nbd_open - Open NBD block device
 * @bdev: Block device
 * @mode: Open mode
 * 
 * Returns: 0 on success, negative on error
 */
static int nbd_open(struct block_device *bdev, fmode_t mode)
{
    struct nbd_device *dev = bdev->bd_disk->private_data;
    
    pr_debug("%s: Opening %s\n", NBD_DRIVER_NAME, dev->name);
    
    mutex_lock(&dev->lock);
    dev->active = true;
    mutex_unlock(&dev->lock);
    
    return 0;
}

/**
 * nbd_release - Release NBD block device
 * @disk: Gendisk
 * @mode: Open mode
 */
static void nbd_release(struct gendisk *disk, fmode_t mode)
{
    struct nbd_device *dev = disk->private_data;
    
    pr_debug("%s: Releasing %s\n", NBD_DRIVER_NAME, dev->name);
    
    mutex_lock(&dev->lock);
    dev->active = false;
    mutex_unlock(&dev->lock);
}

/**
 * nbd_ioctl - NBD device IOCTL handler
 * @bdev: Block device
 * @mode: File mode
 * @cmd: IOCTL command
 * @arg: IOCTL argument
 * 
 * Returns: 0 on success, negative on error
 */
static int nbd_ioctl(struct block_device *bdev, fmode_t mode,
                     unsigned int cmd, unsigned long arg)
{
    struct nbd_device *dev = bdev->bd_disk->private_data;
    int err = 0;
    struct sockaddr_in addr;
    struct socket *sock;
    int port;
    char __user *userp = (char __user *)arg;
    char name[64];
    u64 size;
    
    switch (cmd) {
        case NBD_SET_PORT:
            /* Set NBD server port */
            port = (int)arg;
            mutex_lock(&dev->lock);
            dev->port = port;
            mutex_unlock(&dev->lock);
            pr_info("%s: %s port set to %d\n", 
                    NBD_DRIVER_NAME, dev->name, port);
            break;
            
        case NBD_SET_SIZE:
            /* Set device size */
            size = (u64)arg;
            mutex_lock(&dev->lock);
            dev->size = size;
            set_capacity(dev->disk, size >> 9);
            mutex_unlock(&dev->lock);
            pr_info("%s: %s size set to %lld bytes\n", 
                    NBD_DRIVER_NAME, dev->name, size);
            break;
            
        case NBD_SET_SIZE_BLOCKS:
            /* Set device size in blocks */
            size = (u64)arg << 9;
            mutex_lock(&dev->lock);
            dev->size = size;
            set_capacity(dev->disk, (u64)arg);
            mutex_unlock(&dev->lock);
            pr_info("%s: %s size set to %lld blocks\n", 
                    NBD_DRIVER_NAME, dev->name, (u64)arg);
            break;
            
        case NBD_SET_BLKSIZE:
            /* Set block size (not implemented) */
            pr_warn("%s: Block size change not implemented\n", 
                    NBD_DRIVER_NAME);
            err = -EOPNOTSUPP;
            break;
            
        case NBD_SET_SOCK:
            /* Set socket from file descriptor */
            sock = sockfd_lookup((int)arg, &err);
            if (!sock) {
                pr_err("%s: Invalid socket FD\n", NBD_DRIVER_NAME);
                return -EBADF;
            }
            
            mutex_lock(&dev->lock);
            dev->sock = sock;
            dev->connected = true;
            mutex_unlock(&dev->lock);
            
            pr_info("%s: Socket attached to %s\n", 
                    NBD_DRIVER_NAME, dev->name);
            break;
            
        case NBD_SET_SOCK_ADDR:
            /* Set socket address */
            if (copy_from_user(&addr, userp, sizeof(addr))) {
                return -EFAULT;
            }
            
            port = ntohs(addr.sin_port);
            mutex_lock(&dev->lock);
            dev->port = port;
            mutex_unlock(&dev->lock);
            break;
            
        case NBD_DO_IT:
            /* Start NBD server */
            if (!dev->sock) {
                pr_err("%s: No socket for %s\n", 
                       NBD_DRIVER_NAME, dev->name);
                return -EINVAL;
            }
            
            if (dev->thread) {
                pr_err("%s: Server already running for %s\n", 
                       NBD_DRIVER_NAME, dev->name);
                return -EBUSY;
            }
            
            /* Create server thread */
            dev->thread = kthread_run(nbd_server_thread, dev, 
                                     "nbd-server-%d", dev->minor);
            if (IS_ERR(dev->thread)) {
                err = PTR_ERR(dev->thread);
                dev->thread = NULL;
                pr_err("%s: Failed to create thread: %d\n", 
                       NBD_DRIVER_NAME, err);
                return err;
            }
            
            dev->exporting = true;
            pr_info("%s: NBD server started for %s\n", 
                    NBD_DRIVER_NAME, dev->name);
            break;
            
        case NBD_CLEAR_SOCK:
            /* Clear socket and stop server */
            mutex_lock(&dev->lock);
            dev->exporting = false;
            dev->active = false;
            
            if (dev->sock) {
                sock_release(dev->sock);
                dev->sock = NULL;
            }
            
            if (dev->thread) {
                kthread_stop(dev->thread);
                dev->thread = NULL;
            }
            
            dev->connected = false;
            mutex_unlock(&dev->lock);
            
            pr_info("%s: NBD server stopped for %s\n", 
                    NBD_DRIVER_NAME, dev->name);
            break;
            
        case NBD_SET_FLAGS:
            /* Set NBD flags */
            mutex_lock(&dev->lock);
            dev->flags = (u32)arg;
            mutex_unlock(&dev->lock);
            pr_info("%s: %s flags set to 0x%x\n", 
                    NBD_DRIVER_NAME, dev->name, (u32)arg);
            break;
            
        case NBD_SET_READONLY:
            /* Set read-only mode */
            mutex_lock(&dev->lock);
            dev->readonly = true;
            mutex_unlock(&dev->lock);
            pr_info("%s: %s set to read-only\n", 
                    NBD_DRIVER_NAME, dev->name);
            break;
            
        default:
            pr_warn("%s: Unknown IOCTL %u\n", NBD_DRIVER_NAME, cmd);
            err = -ENOTTY;
            break;
    }
    
    return err;
}

/**
 * nbd_submit_bio - Submit bio to NBD device
 * @bio: BIO to submit
 */
static void nbd_submit_bio(struct bio *bio)
{
    struct nbd_device *dev = bio->bi_bdev->bd_disk->private_data;
    
    if (!dev || !dev->active || !dev->connected) {
        bio_io_error(bio);
        return;
    }
    
    /* For NBD, we handle I/O in the server thread */
    /* Here we just complete the bio */
    bio_endio(bio, 0);
}

/* ==================== Device Management Functions ==================== */

/**
 * nbd_create_device - Create an NBD device
 * @name: Device name
 * @size: Device size in bytes
 * @export_name: Export name
 * @port: NBD server port
 * 
 * Returns: nbd_device pointer on success, ERR_PTR on error
 */
struct nbd_device *nbd_create_device(const char *name, u64 size,
                                     const char *export_name, int port)
{
    struct nbd_device *dev;
    struct gendisk *disk;
    struct request_queue *q;
    int err;
    char disk_name[32];
    dev_t devt;
    
    pr_info("%s: Creating NBD device: %s (size=%lld)\n", 
            NBD_DRIVER_NAME, name, size);
    
    dev = kzalloc(sizeof(struct nbd_device), GFP_KERNEL);
    if (!dev) {
        return ERR_PTR(-ENOMEM);
    }
    
    /* Initialize device */
    strcpy(dev->name, name);
    if (export_name) {
        strcpy(dev->export_name, export_name);
    } else {
        sprintf(dev->export_name, "%s", name);
    }
    dev->size = size;
    dev->port = port ? port : NBD_DEFAULT_PORT;
    dev->active = false;
    dev->connected = false;
    dev->exporting = false;
    dev->readonly = false;
    dev->flags = NBD_FLAG_HAS_FLAGS | NBD_FLAG_SEND_FLUSH |
                 NBD_FLAG_SEND_TRIM | NBD_FLAG_CAN_MULTI_CONN;
    dev->timeout = NBD_TIMEOUT;
    dev->max_connections = 1;
    dev->current_connections = 0;
    
    mutex_init(&dev->lock);
    spin_lock_init(&dev->conn_lock);
    init_completion(&dev->completion);
    init_waitqueue_head(&dev->wait);
    setup_timer(&dev->timer, NULL, 0);
    INIT_LIST_HEAD(&dev->list);
    INIT_WORK(&dev->work, NULL);
    
    /* Create request queue */
    q = blk_mq_alloc_queue(&nbd_mq_ops, NULL, GFP_KERNEL);
    if (!q) {
        pr_err("%s: Failed to allocate request queue\n", NBD_DRIVER_NAME);
        kfree(dev);
        return ERR_PTR(-ENOMEM);
    }
    
    /* Set queue limits */
    blk_queue_logical_block_size(q, 512);
    blk_queue_physical_block_size(q, 512);
    blk_queue_io_min(q, 512);
    blk_queue_io_opt(q, 4096);
    blk_queue_max_hw_sectors(q, 1024);
    blk_queue_max_segments(q, 128);
    blk_queue_max_segment_size(q, 65536);
    
    /* Create gendisk */
    snprintf(disk_name, sizeof(disk_name), "nbd%d", nbd_major);
    devt = MKDEV(nbd_major, nbd_major);
    disk = alloc_disk(1);
    if (!disk) {
        pr_err("%s: Failed to allocate gendisk\n", NBD_DRIVER_NAME);
        blk_mq_free_queue(q);
        kfree(dev);
        return ERR_PTR(-ENOMEM);
    }
    
    disk->queue = q;
    disk->major = nbd_major;
    disk->first_minor = nbd_major;
    disk->fops = &nbd_fops;
    disk->private_data = dev;
    sprintf(disk->disk_name, disk_name);
    set_capacity(disk, size >> 9);
    
    dev->queue = q;
    dev->disk = disk;
    dev->bdev = bdget(devt);
    if (!dev->bdev) {
        pr_err("%s: Failed to get block device\n", NBD_DRIVER_NAME);
        put_disk(disk);
        blk_mq_free_queue(q);
        kfree(dev);
        return ERR_PTR(-ENOMEM);
    }
    
    /* Register disk */
    add_disk(disk);
    
    /* Create device file */
    dev->disk->devt = devt;
    device_create(nbd_class, NULL, devt, dev, "%s", disk_name);
    
    /* Add to global list */
    mutex_lock(&nbd_devices_lock);
    list_add(&dev->list, &nbd_devices);
    mutex_unlock(&nbd_devices_lock);
    
    pr_info("%s: NBD device %s created (major=%d, minor=%d)\n",
            NBD_DRIVER_NAME, name, nbd_major, nbd_major);
    
    return dev;
}
EXPORT_SYMBOL(nbd_create_device);

/**
 * nbd_delete_device - Delete an NBD device
 * @dev: NBD device to delete
 */
void nbd_delete_device(struct nbd_device *dev)
{
    if (!dev) {
        return;
    }
    
    pr_info("%s: Deleting NBD device: %s\n", 
            NBD_DRIVER_NAME, dev->name);
    
    /* Stop server if running */
    if (dev->exporting) {
        dev->active = false;
        if (dev->thread) {
            kthread_stop(dev->thread);
            dev->thread = NULL;
        }
        if (dev->sock) {
            sock_release(dev->sock);
            dev->sock = NULL;
        }
    }
    
    /* Remove from global list */
    mutex_lock(&nbd_devices_lock);
    list_del(&dev->list);
    mutex_unlock(&nbd_devices_lock);
    
    /* Unregister disk */
    del_gendisk(dev->disk);
    
    /* Destroy device */
    device_destroy(nbd_class, dev->disk->devt);
    
    /* Free resources */
    if (dev->bdev) {
        bdput(dev->bdev);
    }
    put_disk(dev->disk);
    blk_mq_free_queue(dev->queue);
    
    mutex_destroy(&dev->lock);
    spin_lock_destroy(&dev->conn_lock);
    
    kfree(dev);
    
    pr_info("%s: NBD device deleted\n", NBD_DRIVER_NAME);
}
EXPORT_SYMBOL(nbd_delete_device);

/**
 * nbd_export_device - Export a block device via NBD
 * @dev: NBD device
 * @bdev: Block device to export
 * @port: Port to listen on
 * @readonly: Read-only mode
 * 
 * Returns: 0 on success, negative on error
 */
int nbd_export_device(struct nbd_device *dev, struct block_device *bdev,
                      int port, bool readonly)
{
    int err;
    struct socket *sock;
    struct sockaddr_in addr;
    int ret;
    
    if (!dev || !bdev) {
        return -EINVAL;
    }
    
    pr_info("%s: Exporting device %s via NBD\n", 
            NBD_DRIVER_NAME, dev->name);
    
    /* Create socket */
    ret = sock_create_kern(&init_net, AF_INET, SOCK_STREAM, IPPROTO_TCP, &sock);
    if (ret < 0) {
        pr_err("%s: Failed to create socket: %d\n", 
               NBD_DRIVER_NAME, ret);
        return ret;
    }
    
    /* Set socket options */
    sock->sk->sk_rcvtimeo = HZ * dev->timeout;
    sock->sk->sk_sndtimeo = HZ * dev->timeout;
    
    /* Bind to port */
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port = htons(port ? port : dev->port);
    
    ret = kernel_bind(sock, (struct sockaddr *)&addr, sizeof(addr));
    if (ret < 0) {
        pr_err("%s: Failed to bind to port %d: %d\n", 
               NBD_DRIVER_NAME, dev->port, ret);
        sock_release(sock);
        return ret;
    }
    
    /* Listen for connections */
    ret = kernel_listen(sock, 1);
    if (ret < 0) {
        pr_err("%s: Failed to listen: %d\n", NBD_DRIVER_NAME, ret);
        sock_release(sock);
        return ret;
    }
    
    /* Set device properties */
    mutex_lock(&dev->lock);
    dev->bdev = bdev;
    dev->readonly = readonly;
    dev->size = bdev->bd_inode->i_size;
    dev->port = port ? port : dev->port;
    dev->sock = sock;
    dev->connected = true;
    dev->active = true;
    set_capacity(dev->disk, dev->size >> 9);
    mutex_unlock(&dev->lock);
    
    /* Start server thread */
    err = nbd_server_thread(dev);
    if (err < 0) {
        pr_err("%s: Server thread failed: %d\n", NBD_DRIVER_NAME, err);
        mutex_lock(&dev->lock);
        dev->active = false;
        dev->connected = false;
        if (dev->sock) {
            sock_release(dev->sock);
            dev->sock = NULL;
        }
        mutex_unlock(&dev->lock);
        return err;
    }
    
    pr_info("%s: Device %s exported via NBD on port %d\n",
            NBD_DRIVER_NAME, dev->name, dev->port);
    
    return 0;
}
EXPORT_SYMBOL(nbd_export_device);

/**
 * nbd_stop_export - Stop exporting an NBD device
 * @dev: NBD device
 */
void nbd_stop_export(struct nbd_device *dev)
{
    if (!dev) {
        return;
    }
    
    pr_info("%s: Stopping export for %s\n", 
            NBD_DRIVER_NAME, dev->name);
    
    mutex_lock(&dev->lock);
    dev->active = false;
    dev->exporting = false;
    dev->connected = false;
    
    if (dev->sock) {
        sock_release(dev->sock);
        dev->sock = NULL;
    }
    
    if (dev->thread) {
        kthread_stop(dev->thread);
        dev->thread = NULL;
    }
    mutex_unlock(&dev->lock);
    
    pr_info("%s: Export stopped for %s\n", 
            NBD_DRIVER_NAME, dev->name);
}
EXPORT_SYMBOL(nbd_stop_export);

/* ==================== Module Initialization ==================== */

/**
 * nbd_init - Module initialization
 */
static int __init nbd_init(void)
{
    int err;
    
    pr_info("%s: Network Block Device Server v%s loading...\n", 
            NBD_DRIVER_NAME, NBD_VERSION);
    
    /* Register block device major */
    err = register_blkdev(0, NBD_DRIVER_NAME);
    if (err < 0) {
        pr_err("%s: Failed to register block device: %d\n",
               NBD_DRIVER_NAME, err);
        return err;
    }
    nbd_major = err;
    
    /* Create device class */
    nbd_class = class_create(THIS_MODULE, NBD_DRIVER_NAME);
    if (IS_ERR(nbd_class)) {
        pr_err("%s: Failed to create device class\n", NBD_DRIVER_NAME);
        unregister_blkdev(nbd_major, NBD_DRIVER_NAME);
        return PTR_ERR(nbd_class);
    }
    
    /* Create workqueue */
    nbd_wq = create_singlethread_workqueue("nbd_wq");
    if (!nbd_wq) {
        pr_err("%s: Failed to create workqueue\n", NBD_DRIVER_NAME);
        class_destroy(nbd_class);
        unregister_blkdev(nbd_major, NBD_DRIVER_NAME);
        return -ENOMEM;
    }
    
    /* Create default NBD device */
    struct nbd_device *dev = nbd_create_device("nbd0", 0, "default", 
                                               NBD_DEFAULT_PORT);
    if (IS_ERR(dev)) {
        pr_warn("%s: Failed to create default NBD device\n", 
                NBD_DRIVER_NAME);
    }
    
    pr_info("%s: Driver loaded successfully (major=%d)\n", 
            NBD_DRIVER_NAME, nbd_major);
    
    return 0;
}

/**
 * nbd_exit - Module cleanup
 */
static void __exit nbd_exit(void)
{
    struct nbd_device *dev, *tmp;
    
    pr_info("%s: Network Block Device Server unloading...\n", 
            NBD_DRIVER_NAME);
    
    /* Delete all NBD devices */
    list_for_each_entry_safe(dev, tmp, &nbd_devices, list) {
        nbd_delete_device(dev);
    }
    
    /* Destroy workqueue */
    if (nbd_wq) {
        destroy_workqueue(nbd_wq);
    }
    
    /* Destroy device class */
    if (nbd_class) {
        class_destroy(nbd_class);
    }
    
    /* Unregister block device */
    if (nbd_major) {
        unregister_blkdev(nbd_major, NBD_DRIVER_NAME);
    }
    
    pr_info("%s: Driver unloaded\n", NBD_DRIVER_NAME);
}

module_init(nbd_init);
module_exit(nbd_exit);

/* ==================== Module Parameters ==================== */

static int nbd_port = NBD_DEFAULT_PORT;
module_param(nbd_port, int, 0644);
MODULE_PARM_DESC(nbd_port, "Default NBD server port");

static int nbd_timeout = NBD_TIMEOUT;
module_param(nbd_timeout, int, 0644);
MODULE_PARM_DESC(nbd_timeout, "NBD timeout in seconds");

static int nbd_max_devices = NBD_MAX_DEVICES;
module_param(nbd_max_devices, int, 0644);
MODULE_PARM_DESC(nbd_max_devices, "Maximum number of NBD devices");

/* ==================== Debug Information ==================== */

/**
 * nbd_show_info - Show NBD device information
 */
void nbd_show_info(void)
{
    struct nbd_device *dev;
    
    pr_info("%s: NBD Device Information:\n", NBD_DRIVER_NAME);
    pr_info("  Major: %d\n", nbd_major);
    pr_info("  Max Devices: %d\n", nbd_max_devices);
    pr_info("  Default Port: %d\n", nbd_port);
    pr_info("  Timeout: %d seconds\n", nbd_timeout);
    pr_info("  Active Devices:\n");
    
    list_for_each_entry(dev, &nbd_devices, list) {
        pr_info("    %s: minor=%d, size=%llu, port=%d, %s\n",
                dev->name, dev->minor, dev->size, dev->port,
                dev->active ? "active" : "inactive");
        pr_info("      Export: %s, %s, %s\n",
                dev->export_name,
                dev->readonly ? "read-only" : "read-write",
                dev->connected ? "connected" : "disconnected");
    }
}
EXPORT_SYMBOL(nbd_show_info);

/* ==================== Example Usage ==================== */

/*
 * Example usage:
 * 
 * 1. Create an NBD device:
 *    struct nbd_device *dev = nbd_create_device("nbd0", 1024*1024*1024,
 *                                               "export1", 10809);
 * 
 * 2. Export a block device:
 *    struct block_device *bdev = blkdev_get_by_path("/dev/sdb", FMODE_READ, NULL);
 *    nbd_export_device(dev, bdev, 10809, false);
 * 
 * 3. Client connection:
 *    nbd-client -N export1 localhost 10809 /dev/nbd0
 * 
 * 4. Mount exported device:
 *    mount /dev/nbd0 /mnt/nbd
 * 
 * 5. Stop export:
 *    nbd_stop_export(dev);
 * 
 * 6. Delete device:
 *    nbd_delete_device(dev);
 */

/* Export symbols for use by other modules */
EXPORT_SYMBOL(nbd_create_device);
EXPORT_SYMBOL(nbd_delete_device);
EXPORT_SYMBOL(nbd_export_device);
EXPORT_SYMBOL(nbd_stop_export);
EXPORT_SYMBOL(nbd_show_info);
