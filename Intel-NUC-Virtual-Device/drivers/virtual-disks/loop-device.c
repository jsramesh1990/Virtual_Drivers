/*
 * loop-device.c - Virtual Loop Device Driver for Intel NUC
 * 
 * This driver implements loop devices for mounting disk images
 * as block devices on Intel NUC platforms.
 * 
 * Version: 1.0
 * Author: Virtual Device Platform Team
 * License: GPL v2
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/fs.h>
#include <linux/blkdev.h>
#include <linux/genhd.h>
#include <linux/buffer_head.h>
#include <linux/file.h>
#include <linux/namei.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <linux/mutex.h>

#define LOOP_NAME "virt-loop"
#define LOOP_VERSION "1.0.0"
#define LOOP_MAX_DEVICES 256

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Intel NUC Virtual Device Platform");
MODULE_DESCRIPTION("Virtual Loop Device Driver for Intel NUC");
MODULE_VERSION(LOOP_VERSION);

/* Loop device structure */
struct loop_device {
    struct gendisk *disk;
    struct block_device *bdev;
    struct file *file;
    struct mutex lock;
    char filename[256];
    int minor;
    int blocksize;
    sector_t size;
    bool active;
    bool read_only;
    bool use_dio;
    struct list_head list;
};

/* Global list */
static LIST_HEAD(loop_devices);
static DEFINE_MUTEX(loop_lock);

/* Forward declarations */
static int loop_open(struct block_device *bdev, fmode_t mode);
static void loop_release(struct gendisk *disk, fmode_t mode);
static int loop_ioctl(struct block_device *bdev, fmode_t mode,
                     unsigned int cmd, unsigned long arg);
static void loop_submit_bio(struct bio *bio);

/* Block device operations */
static const struct block_device_operations loop_fops = {
    .owner = THIS_MODULE,
    .open = loop_open,
    .release = loop_release,
    .ioctl = loop_ioctl,
};

/* Queue operations */
static const struct blk_mq_ops loop_mq_ops = {
    .queue_rq = loop_submit_bio,
};

/* Open loop device */
static int loop_open(struct block_device *bdev, fmode_t mode)
{
    struct loop_device *loop = bdev->bd_disk->private_data;
    
    pr_info("%s: Opening loop device %s\n", LOOP_NAME, loop->disk->disk_name);
    
    mutex_lock(&loop->lock);
    loop->active = true;
    mutex_unlock(&loop->lock);
    
    return 0;
}

/* Release loop device */
static void loop_release(struct gendisk *disk, fmode_t mode)
{
    struct loop_device *loop = disk->private_data;
    
    pr_info("%s: Releasing loop device %s\n", LOOP_NAME, disk->disk_name);
    
    mutex_lock(&loop->lock);
    loop->active = false;
    mutex_unlock(&loop->lock);
}

/* Loop IOCTL */
static int loop_ioctl(struct block_device *bdev, fmode_t mode,
                     unsigned int cmd, unsigned long arg)
{
    struct loop_device *loop = bdev->bd_disk->private_data;
    struct file *file;
    char __user *userp = (char __user *)arg;
    char filename[256];
    int err = 0;
    
    switch (cmd) {
        case LOOP_SET_FD:
            /* Set file descriptor */
            file = fget((int)arg);
            if (!file) {
                return -EBADF;
            }
            
            mutex_lock(&loop->lock);
            if (loop->file) {
                fput(loop->file);
            }
            loop->file = file;
            loop->bdev = bdev;
            
            /* Get file size */
            loop->size = vfs_llseek(file, 0, SEEK_END);
            vfs_llseek(file, 0, SEEK_SET);
            
            set_capacity(loop->disk, loop->size >> 9);
            mutex_unlock(&loop->lock);
            
            pr_info("%s: Loop device %s attached to file (size %lld)\n",
                    LOOP_NAME, loop->disk->disk_name, loop->size);
            break;
            
        case LOOP_CLR_FD:
            /* Clear file descriptor */
            mutex_lock(&loop->lock);
            if (loop->file) {
                fput(loop->file);
                loop->file = NULL;
                loop->bdev = NULL;
                loop->size = 0;
                set_capacity(loop->disk, 0);
            }
            mutex_unlock(&loop->lock);
            break;
            
        case LOOP_SET_STATUS:
            /* Set loop status */
            /* ... */
            break;
            
        default:
            err = -ENOTTY;
            break;
    }
    
    return err;
}

/* Submit bio for loop device */
static void loop_submit_bio(struct bio *bio)
{
    struct loop_device *loop = bio->bi_bdev->bd_disk->private_data;
    struct file *file = loop->file;
    struct bio_vec bvec;
    struct bvec_iter iter;
    loff_t pos = bio->bi_iter.bi_sector << 9;
    int ret;
    
    if (!file || !loop->active) {
        bio_io_error(bio);
        return;
    }
    
    /* Process each segment */
    bio_for_each_segment(bvec, bio, iter) {
        void *buf = bvec_kmap_irq(&bvec, &flags);
        
        if (bio_data_dir(bio) == READ) {
            /* Read from file */
            ret = vfs_read(file, buf, bvec.bv_len, &pos);
        } else {
            /* Write to file */
            ret = vfs_write(file, buf, bvec.bv_len, &pos);
        }
        
        bvec_kunmap_irq(buf, &flags);
        
        if (ret != bvec.bv_len) {
            bio_io_error(bio);
            return;
        }
    }
    
    bio_endio(bio, 0);
}

/* Create loop device */
struct loop_device *loop_create(int minor, const char *filename, int blocksize)
{
    struct loop_device *loop;
    struct gendisk *disk;
    struct request_queue *q;
    int err;
    char name[16];
    
    pr_info("%s: Creating loop device (minor %d, file %s)\n",
            LOOP_NAME, minor, filename);
    
    if (minor < 0 || minor >= LOOP_MAX_DEVICES) {
        pr_err("Invalid minor number\n");
        return ERR_PTR(-EINVAL);
    }
    
    loop = kzalloc(sizeof(struct loop_device), GFP_KERNEL);
    if (!loop) {
        return ERR_PTR(-ENOMEM);
    }
    
    /* Initialize loop device */
    loop->minor = minor;
    loop->blocksize = blocksize ? blocksize : 512;
    loop->active = false;
    loop->read_only = false;
    loop->use_dio = false;
    strcpy(loop->filename, filename);
    mutex_init(&loop->lock);
    
    /* Create request queue */
    q = blk_mq_alloc_queue(&loop_mq_ops, NULL, GFP_KERNEL);
    if (!q) {
        pr_err("Failed to allocate request queue\n");
        kfree(loop);
        return ERR_PTR(-ENOMEM);
    }
    
    /* Create gendisk */
    snprintf(name, sizeof(name), "loop%d", minor);
    disk = alloc_disk(1);
    if (!disk) {
        pr_err("Failed to allocate gendisk\n");
        blk_mq_free_queue(q);
        kfree(loop);
        return ERR_PTR(-ENOMEM);
    }
    
    disk->queue = q;
    disk->major = LOOP_MAJOR;
    disk->first_minor = minor;
    disk->fops = &loop_fops;
    disk->private_data = loop;
    strcpy(disk->disk_name, name);
    
    set_capacity(disk, 0);
    
    loop->disk = disk;
    
    /* Add to list */
    mutex_lock(&loop_lock);
    list_add(&loop->list, &loop_devices);
    mutex_unlock(&loop_lock);
    
    /* Register disk */
    add_disk(disk);
    
    pr_info("%s: Loop device %s created\n", LOOP_NAME, name);
    return loop;
}
EXPORT_SYMBOL(loop_create);

/* Delete loop device */
void loop_delete(struct loop_device *loop)
{
    if (!loop) {
        return;
    }
    
    pr_info("%s: Deleting loop device %s\n", LOOP_NAME, loop->disk->disk_name);
    
    mutex_lock(&loop->lock);
    loop->active = false;
    mutex_unlock(&loop->lock);
    
    /* Remove from list */
    mutex_lock(&loop_lock);
    list_del(&loop->list);
    mutex_unlock(&loop_lock);
    
    /* Clean up */
    if (loop->file) {
        fput(loop->file);
        loop->file = NULL;
    }
    
    /* Unregister disk */
    del_gendisk(loop->disk);
    
    /* Free resources */
    blk_mq_free_queue(loop->disk->queue);
    put_disk(loop->disk);
    mutex_destroy(&loop->lock);
    kfree(loop);
    
    pr_info("%s: Loop device deleted\n", LOOP_NAME);
}
EXPORT_SYMBOL(loop_delete);

/* Module initialization */
static int __init loop_init(void)
{
    pr_info("%s: Virtual Loop Driver v%s loading...\n", 
            LOOP_NAME, LOOP_VERSION);
    
    /* Register major */
    register_blkdev(LOOP_MAJOR, "loop");
    
    pr_info("%s: Driver loaded successfully\n", LOOP_NAME);
    return 0;
}

/* Module cleanup */
static void __exit loop_exit(void)
{
    struct loop_device *loop, *tmp;
    
    pr_info("%s: Virtual Loop Driver unloading...\n", LOOP_NAME);
    
    /* Delete all loop devices */
    list_for_each_entry_safe(loop, tmp, &loop_devices, list) {
        loop_delete(loop);
    }
    
    /* Unregister major */
    unregister_blkdev(LOOP_MAJOR, "loop");
    
    pr_info("%s: Driver unloaded\n", LOOP_NAME);
}

module_init(loop_init);
module_exit(loop_exit);
