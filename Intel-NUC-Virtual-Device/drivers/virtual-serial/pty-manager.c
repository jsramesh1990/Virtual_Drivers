/*
 * pty-manager.c - Virtual Serial Port (PTY) Manager for Intel NUC
 * 
 * This driver implements pseudo-terminal management for virtual
 * serial devices on Intel NUC platforms.
 * 
 * Version: 1.0
 * Author: Virtual Device Platform Team
 * License: GPL v2
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/tty.h>
#include <linux/tty_driver.h>
#include <linux/tty_flip.h>
#include <linux/mutex.h>
#include <linux/slab.h>
#include <linux/fs.h>
#include <linux/device.h>

#define PTY_NAME "virt-pty"
#define PTY_VERSION "1.0.0"
#define PTY_MAJOR 0
#define PTY_MINOR 0
#define PTY_MAX_DEVICES 256

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Intel NUC Virtual Device Platform");
MODULE_DESCRIPTION("Virtual PTY Manager for Intel NUC");
MODULE_VERSION(PTY_VERSION);

/* PTY device structure */
struct pty_device {
    struct tty_port port;
    struct tty_struct *tty;
    struct pty_device *peer;
    char name[64];
    int minor;
    struct mutex lock;
    bool open;
    bool active;
    unsigned long flags;
    struct list_head list;
};

/* Global PTY list */
static LIST_HEAD(pty_list);
static DEFINE_MUTEX(pty_list_lock);
static int pty_count = 0;

/* Forward declarations */
static int pty_open(struct tty_struct *tty, struct file *filp);
static void pty_close(struct tty_struct *tty, struct file *filp);
static int pty_write(struct tty_struct *tty, const unsigned char *buf, int count);
static int pty_ioctl(struct tty_struct *tty, unsigned int cmd, unsigned long arg);
static int pty_install(struct tty_driver *driver, struct tty_struct *tty);
static void pty_cleanup(struct tty_struct *tty);

/* TTY operations */
static const struct tty_operations pty_ops = {
    .open = pty_open,
    .close = pty_close,
    .write = pty_write,
    .ioctl = pty_ioctl,
    .install = pty_install,
    .cleanup = pty_cleanup,
};

/* TTY port operations */
static const struct tty_port_operations pty_port_ops = {
    .activate = NULL,
    .shutdown = NULL,
};

/* TTY driver */
static struct tty_driver *pty_driver;

/* Open PTY */
static int pty_open(struct tty_struct *tty, struct file *filp)
{
    struct pty_device *pty = tty->driver_data;
    int err;
    
    pr_info("%s: Opening PTY device %s\n", PTY_NAME, pty->name);
    
    mutex_lock(&pty->lock);
    
    if (pty->open) {
        mutex_unlock(&pty->lock);
        return -EBUSY;
    }
    
    err = tty_port_open(&pty->port, tty, filp);
    if (err) {
        mutex_unlock(&pty->lock);
        return err;
    }
    
    pty->open = true;
    pty->active = true;
    pty->tty = tty;
    
    mutex_unlock(&pty->lock);
    return 0;
}

/* Close PTY */
static void pty_close(struct tty_struct *tty, struct file *filp)
{
    struct pty_device *pty = tty->driver_data;
    
    pr_info("%s: Closing PTY device %s\n", PTY_NAME, pty->name);
    
    mutex_lock(&pty->lock);
    pty->open = false;
    pty->active = false;
    pty->tty = NULL;
    tty_port_close(&pty->port, tty, filp);
    mutex_unlock(&pty->lock);
}

/* Write to PTY */
static int pty_write(struct tty_struct *tty, const unsigned char *buf, int count)
{
    struct pty_device *pty = tty->driver_data;
    struct pty_device *peer = pty->peer;
    int written = 0;
    
    if (!peer || !peer->open || !peer->tty) {
        return -ENODEV;
    }
    
    /* Forward data to peer */
    if (peer->tty->ops->receive_buf) {
        peer->tty->ops->receive_buf(peer->tty, buf, NULL, count);
        written = count;
    }
    
    return written;
}

/* PTY IOCTL */
static int pty_ioctl(struct tty_struct *tty, unsigned int cmd, unsigned long arg)
{
    struct pty_device *pty = tty->driver_data;
    
    switch (cmd) {
        case TIOCGETD:
            /* Get line discipline */
            if (put_user(N_TTY, (int __user *)arg)) {
                return -EFAULT;
            }
            return 0;
            
        case TIOCSCTTY:
            /* Set controlling terminal */
            return 0;
            
        default:
            return -ENOIOCTLCMD;
    }
}

/* PTY install */
static int pty_install(struct tty_driver *driver, struct tty_struct *tty)
{
    struct pty_device *pty = tty->driver_data;
    
    tty->port = &pty->port;
    return 0;
}

/* PTY cleanup */
static void pty_cleanup(struct tty_struct *tty)
{
    struct pty_device *pty = tty->driver_data;
    
    if (pty) {
        mutex_lock(&pty->lock);
        pty->active = false;
        pty->tty = NULL;
        mutex_unlock(&pty->lock);
    }
}

/* Create PTY pair */
struct pty_device *pty_create_pair(const char *name1, const char *name2)
{
    struct pty_device *pty1, *pty2;
    int err;
    char dev_name1[64], dev_name2[64];
    
    pr_info("%s: Creating PTY pair: %s <-> %s\n", PTY_NAME, name1, name2);
    
    /* Allocate PTY structures */
    pty1 = kzalloc(sizeof(struct pty_device), GFP_KERNEL);
    if (!pty1) {
        return ERR_PTR(-ENOMEM);
    }
    
    pty2 = kzalloc(sizeof(struct pty_device), GFP_KERNEL);
    if (!pty2) {
        kfree(pty1);
        return ERR_PTR(-ENOMEM);
    }
    
    /* Initialize PTY 1 */
    tty_port_init(&pty1->port);
    pty1->port.ops = &pty_port_ops;
    snprintf(pty1->name, sizeof(pty1->name), "%s", name1);
    pty1->minor = pty_count++;
    mutex_init(&pty1->lock);
    pty1->open = false;
    pty1->active = false;
    
    /* Initialize PTY 2 */
    tty_port_init(&pty2->port);
    pty2->port.ops = &pty_port_ops;
    snprintf(pty2->name, sizeof(pty2->name), "%s", name2);
    pty2->minor = pty_count++;
    mutex_init(&pty2->lock);
    pty2->open = false;
    pty2->active = false;
    
    /* Link peers */
    pty1->peer = pty2;
    pty2->peer = pty1;
    
    /* Create device files */
    snprintf(dev_name1, sizeof(dev_name1), "%s%d", "ttyV", pty1->minor);
    snprintf(dev_name2, sizeof(dev_name2), "%s%d", "ttyV", pty2->minor);
    
    /* Register with TTY core */
    err = tty_register_device(pty_driver, pty1->minor, NULL);
    if (err) {
        pr_err("Failed to register PTY device %s\n", dev_name1);
        kfree(pty1);
        kfree(pty2);
        return ERR_PTR(err);
    }
    
    err = tty_register_device(pty_driver, pty2->minor, NULL);
    if (err) {
        pr_err("Failed to register PTY device %s\n", dev_name2);
        tty_unregister_device(pty_driver, pty1->minor);
        kfree(pty1);
        kfree(pty2);
        return ERR_PTR(err);
    }
    
    /* Add to list */
    mutex_lock(&pty_list_lock);
    list_add(&pty1->list, &pty_list);
    list_add(&pty2->list, &pty_list);
    mutex_unlock(&pty_list_lock);
    
    pr_info("%s: PTY devices created: %s, %s\n", PTY_NAME, dev_name1, dev_name2);
    return pty1;
}
EXPORT_SYMBOL(pty_create_pair);

/* Destroy PTY pair */
void pty_destroy_pair(struct pty_device *pty1)
{
    struct pty_device *pty2 = pty1->peer;
    
    if (!pty2) {
        return;
    }
    
    pr_info("%s: Destroying PTY pair\n", PTY_NAME);
    
    /* Remove from list */
    mutex_lock(&pty_list_lock);
    list_del(&pty1->list);
    list_del(&pty2->list);
    mutex_unlock(&pty_list_lock);
    
    /* Unregister TTY devices */
    tty_unregister_device(pty_driver, pty1->minor);
    tty_unregister_device(pty_driver, pty2->minor);
    
    /* Free PTY structures */
    mutex_destroy(&pty1->lock);
    mutex_destroy(&pty2->lock);
    tty_port_destroy(&pty1->port);
    tty_port_destroy(&pty2->port);
    kfree(pty1);
    kfree(pty2);
    
    pr_info("%s: PTY pair destroyed\n", PTY_NAME);
}
EXPORT_SYMBOL(pty_destroy_pair);

/* Module initialization */
static int __init pty_init(void)
{
    int err;
    
    pr_info("%s: Virtual PTY Manager v%s loading...\n", 
            PTY_NAME, PTY_VERSION);
    
    /* Allocate TTY driver */
    pty_driver = tty_alloc_driver(PTY_MAX_DEVICES,
                                 TTY_DRIVER_DYNAMIC_DEV |
                                 TTY_DRIVER_REAL_RAW);
    if (IS_ERR(pty_driver)) {
        pr_err("Failed to allocate TTY driver\n");
        return PTR_ERR(pty_driver);
    }
    
    /* Initialize TTY driver */
    pty_driver->driver_name = "virt-pty";
    pty_driver->name = "ttyV";
    pty_driver->major = PTY_MAJOR;
    pty_driver->minor_start = PTY_MINOR;
    pty_driver->type = TTY_DRIVER_TYPE_SERIAL;
    pty_driver->subtype = SERIAL_TYPE_NORMAL;
    pty_driver->init_termios = tty_std_termios;
    pty_driver->init_termios.c_cflag = B9600 | CS8 | CREAD | HUPCL | CLOCAL;
    
    tty_set_operations(pty_driver, &pty_ops);
    
    /* Register TTY driver */
    err = tty_register_driver(pty_driver);
    if (err) {
        pr_err("Failed to register TTY driver\n");
        tty_driver_kref_put(pty_driver);
        return err;
    }
    
    pr_info("%s: Driver loaded successfully\n", PTY_NAME);
    return 0;
}

/* Module cleanup */
static void __exit pty_exit(void)
{
    struct pty_device *pty, *tmp;
    
    pr_info("%s: Virtual PTY Manager unloading...\n", PTY_NAME);
    
    /* Destroy all PTY devices */
    mutex_lock(&pty_list_lock);
    list_for_each_entry_safe(pty, tmp, &pty_list, list) {
        if (pty->peer) {
            pty_destroy_pair(pty);
        }
    }
    mutex_unlock(&pty_list_lock);
    
    /* Unregister TTY driver */
    tty_unregister_driver(pty_driver);
    tty_driver_kref_put(pty_driver);
    
    pr_info("%s: Driver unloaded\n", PTY_NAME);
}

module_init(pty_init);
module_exit(pty_exit);
