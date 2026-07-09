/*
 * socat-bridge.c - Virtual Serial Bridge via Socat
 * 
 * This driver implements a bridge between virtual serial ports
 * using socat-like functionality for device communication.
 * 
 * Version: 1.0
 * Author: Virtual Device Platform Team
 * License: GPL v2
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/fs.h>
#include <linux/uaccess.h>
#include <linux/slab.h>
#include <linux/timer.h>
#include <linux/workqueue.h>
#include <linux/device.h>
#include <linux/miscdevice.h>

#define BRIDGE_NAME "virt-serial-bridge"
#define BRIDGE_VERSION "1.0.0"
#define BRIDGE_BUFFER_SIZE 4096

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Intel NUC Virtual Device Platform");
MODULE_DESCRIPTION("Virtual Serial Bridge for Intel NUC");
MODULE_VERSION(BRIDGE_VERSION);

/* Bridge structure */
struct serial_bridge {
    struct miscdevice misc;
    struct list_head list;
    char name[64];
    char port1[64];
    char port2[64];
    int fd1, fd2;
    struct workqueue_struct *wq;
    struct work_struct work;
    struct timer_list timer;
    unsigned char buffer[BRIDGE_BUFFER_SIZE];
    int buffer_len;
    bool active;
    spinlock_t lock;
};

/* Global list */
static LIST_HEAD(bridge_list);
static DEFINE_SPINLOCK(bridge_lock);

/* Bridge file operations */
static int bridge_open(struct inode *inode, struct file *file);
static int bridge_release(struct inode *inode, struct file *file);
static ssize_t bridge_read(struct file *file, char __user *buf, 
                          size_t count, loff_t *ppos);
static ssize_t bridge_write(struct file *file, const char __user *buf,
                           size_t count, loff_t *ppos);

static const struct file_operations bridge_fops = {
    .owner = THIS_MODULE,
    .open = bridge_open,
    .release = bridge_release,
    .read = bridge_read,
    .write = bridge_write,
};

/* Bridge open */
static int bridge_open(struct inode *inode, struct file *file)
{
    struct serial_bridge *bridge = container_of(inode->i_cdev, 
                                               struct serial_bridge, 
                                               misc.this_device);
    
    file->private_data = bridge;
    pr_info("%s: Bridge %s opened\n", BRIDGE_NAME, bridge->name);
    return 0;
}

/* Bridge release */
static int bridge_release(struct inode *inode, struct file *file)
{
    struct serial_bridge *bridge = file->private_data;
    
    pr_info("%s: Bridge %s closed\n", BRIDGE_NAME, bridge->name);
    return 0;
}

/* Bridge read */
static ssize_t bridge_read(struct file *file, char __user *buf,
                          size_t count, loff_t *ppos)
{
    struct serial_bridge *bridge = file->private_data;
    unsigned long flags;
    int len;
    
    spin_lock_irqsave(&bridge->lock, flags);
    len = min(count, (size_t)bridge->buffer_len);
    
    if (len > 0) {
        if (copy_to_user(buf, bridge->buffer, len)) {
            spin_unlock_irqrestore(&bridge->lock, flags);
            return -EFAULT;
        }
        memmove(bridge->buffer, bridge->buffer + len, 
                bridge->buffer_len - len);
        bridge->buffer_len -= len;
    }
    spin_unlock_irqrestore(&bridge->lock, flags);
    
    return len;
}

/* Bridge write */
static ssize_t bridge_write(struct file *file, const char __user *buf,
                           size_t count, loff_t *ppos)
{
    struct serial_bridge *bridge = file->private_data;
    unsigned long flags;
    
    spin_lock_irqsave(&bridge->lock, flags);
    
    if (bridge->buffer_len + count > BRIDGE_BUFFER_SIZE) {
        spin_unlock_irqrestore(&bridge->lock, flags);
        return -ENOSPC;
    }
    
    if (copy_from_user(bridge->buffer + bridge->buffer_len, buf, count)) {
        spin_unlock_irqrestore(&bridge->lock, flags);
        return -EFAULT;
    }
    
    bridge->buffer_len += count;
    spin_unlock_irqrestore(&bridge->lock, flags);
    
    return count;
}

/* Create serial bridge */
struct serial_bridge *create_serial_bridge(const char *name, 
                                           const char *port1, 
                                           const char *port2)
{
    struct serial_bridge *bridge;
    int err;
    
    pr_info("%s: Creating serial bridge: %s <-> %s\n", 
            BRIDGE_NAME, port1, port2);
    
    bridge = kzalloc(sizeof(struct serial_bridge), GFP_KERNEL);
    if (!bridge) {
        return ERR_PTR(-ENOMEM);
    }
    
    strcpy(bridge->name, name);
    strcpy(bridge->port1, port1);
    strcpy(bridge->port2, port2);
    bridge->active = true;
    bridge->buffer_len = 0;
    
    spin_lock_init(&bridge->lock);
    
    /* Initialize workqueue */
    bridge->wq = create_singlethread_workqueue("bridge_wq");
    if (!bridge->wq) {
        kfree(bridge);
        return ERR_PTR(-ENOMEM);
    }
    
    /* Initialize misc device */
    bridge->misc.minor = MISC_DYNAMIC_MINOR;
    bridge->misc.name = name;
    bridge->misc.fops = &bridge_fops;
    
    err = misc_register(&bridge->misc);
    if (err) {
        destroy_workqueue(bridge->wq);
        kfree(bridge);
        return ERR_PTR(err);
    }
    
    /* Add to global list */
    spin_lock(&bridge_lock);
    list_add(&bridge->list, &bridge_list);
    spin_unlock(&bridge_lock);
    
    pr_info("%s: Serial bridge %s created (minor %d)\n", 
            BRIDGE_NAME, name, bridge->misc.minor);
    
    return bridge;
}
EXPORT_SYMBOL(create_serial_bridge);

/* Destroy serial bridge */
void destroy_serial_bridge(struct serial_bridge *bridge)
{
    if (!bridge) {
        return;
    }
    
    pr_info("%s: Destroying serial bridge %s\n", BRIDGE_NAME, bridge->name);
    
    bridge->active = false;
    
    /* Remove from list */
    spin_lock(&bridge_lock);
    list_del(&bridge->list);
    spin_unlock(&bridge_lock);
    
    /* Unregister misc device */
    misc_deregister(&bridge->misc);
    
    /* Clean up workqueue */
    flush_workqueue(bridge->wq);
    destroy_workqueue(bridge->wq);
    
    kfree(bridge);
    pr_info("%s: Serial bridge destroyed\n", BRIDGE_NAME);
}
EXPORT_SYMBOL(destroy_serial_bridge);

/* Module initialization */
static int __init bridge_init(void)
{
    pr_info("%s: Virtual Serial Bridge v%s loading...\n", 
            BRIDGE_NAME, BRIDGE_VERSION);
    
    /* Create default bridge */
    create_serial_bridge("serial-bridge0", "/dev/ttyS0", "/dev/ttyS1");
    
    pr_info("%s: Driver loaded successfully\n", BRIDGE_NAME);
    return 0;
}

/* Module cleanup */
static void __exit bridge_exit(void)
{
    struct serial_bridge *bridge, *tmp;
    
    pr_info("%s: Virtual Serial Bridge unloading...\n", BRIDGE_NAME);
    
    /* Destroy all bridges */
    list_for_each_entry_safe(bridge, tmp, &bridge_list, list) {
        destroy_serial_bridge(bridge);
    }
    
    pr_info("%s: Driver unloaded\n", BRIDGE_NAME);
}

module_init(bridge_init);
module_exit(bridge_exit);
