/*
 * tap-driver.c - TAP/TUN Network Driver for Intel NUC
 * 
 * This driver implements TAP/TUN interfaces for virtual machine
 * and VPN networking on Intel NUC platforms.
 * 
 * Version: 1.0
 * Author: Virtual Device Platform Team
 * License: GPL v2
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/netdevice.h>
#include <linux/etherdevice.h>
#include <linux/skbuff.h>
#include <linux/if_tun.h>
#include <linux/fs.h>
#include <linux/miscdevice.h>
#include <linux/uaccess.h>
#include <linux/poll.h>
#include <linux/sched.h>
#include <linux/wait.h>
#include <linux/file.h>

#define TAP_NAME "virt-tap"
#define TAP_VERSION "1.0.0"
#define TAP_DEV_MINOR 255
#define TAP_DEVICES 16

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Intel NUC Virtual Device Platform");
MODULE_DESCRIPTION("TAP/TUN Driver for Intel NUC");
MODULE_VERSION(TAP_VERSION);

/* TAP private data */
struct tap_device {
    struct net_device *dev;
    struct miscdevice misc;
    struct list_head list;
    wait_queue_head_t read_wait;
    struct sk_buff_head queue;
    int flags;  /* TAP/TUN flags */
    int opened;
    spinlock_t lock;
    char name[IFNAMSIZ];
};

/* Global list of TAP devices */
static LIST_HEAD(tap_devices);
static DEFINE_SPINLOCK(tap_list_lock);

/* Forward declarations */
static int tap_open(struct inode *inode, struct file *file);
static int tap_release(struct inode *inode, struct file *file);
static ssize_t tap_read(struct file *file, char __user *buf, 
                        size_t count, loff_t *ppos);
static ssize_t tap_write(struct file *file, const char __user *buf, 
                         size_t count, loff_t *ppos);
static unsigned int tap_poll(struct file *file, poll_table *wait);

/* File operations */
static const struct file_operations tap_fops = {
    .owner = THIS_MODULE,
    .open = tap_open,
    .release = tap_release,
    .read = tap_read,
    .write = tap_write,
    .poll = tap_poll,
    .llseek = no_llseek,
};

/* Network device operations */
static const struct net_device_ops tap_netdev_ops = {
    .ndo_open = NULL,
    .ndo_stop = NULL,
    .ndo_start_xmit = NULL,
};

/* TAP open handler */
static int tap_open(struct inode *inode, struct file *file)
{
    struct tap_device *tap = container_of(inode->i_cdev, struct tap_device, misc.this_device);
    unsigned long flags;
    
    spin_lock_irqsave(&tap->lock, flags);
    tap->opened = 1;
    spin_unlock_irqrestore(&tap->lock, flags);
    
    file->private_data = tap;
    
    pr_info("%s: Device opened\n", tap->name);
    return 0;
}

/* TAP release handler */
static int tap_release(struct inode *inode, struct file *file)
{
    struct tap_device *tap = file->private_data;
    unsigned long flags;
    
    spin_lock_irqsave(&tap->lock, flags);
    tap->opened = 0;
    spin_unlock_irqrestore(&tap->lock, flags);
    
    /* Flush pending packets */
    skb_queue_purge(&tap->queue);
    
    pr_info("%s: Device closed\n", tap->name);
    return 0;
}

/* TAP read handler */
static ssize_t tap_read(struct file *file, char __user *buf, 
                        size_t count, loff_t *ppos)
{
    struct tap_device *tap = file->private_data;
    struct sk_buff *skb;
    int len;
    
    if (count < sizeof(struct tun_pi)) {
        return -EINVAL;
    }
    
    /* Wait for packet */
    if (skb_queue_empty(&tap->queue)) {
        if (file->f_flags & O_NONBLOCK) {
            return -EAGAIN;
        }
        
        if (wait_event_interruptible(tap->read_wait, 
                                     !skb_queue_empty(&tap->queue))) {
            return -ERESTARTSYS;
        }
    }
    
    /* Get packet from queue */
    skb = skb_dequeue(&tap->queue);
    if (!skb) {
        return -EAGAIN;
    }
    
    len = min(count, (size_t)skb->len);
    
    /* Copy packet to userspace */
    if (copy_to_user(buf, skb->data, len)) {
        dev_kfree_skb(skb);
        return -EFAULT;
    }
    
    dev_kfree_skb(skb);
    return len;
}

/* TAP write handler */
static ssize_t tap_write(struct file *file, const char __user *buf,
                         size_t count, loff_t *ppos)
{
    struct tap_device *tap = file->private_data;
    struct sk_buff *skb;
    int err;
    
    if (!tap->dev) {
        return -ENODEV;
    }
    
    /* Allocate skb */
    skb = alloc_skb(count, GFP_KERNEL);
    if (!skb) {
        return -ENOMEM;
    }
    
    /* Copy data from userspace */
    if (copy_from_user(skb_put(skb, count), buf, count)) {
        dev_kfree_skb(skb);
        return -EFAULT;
    }
    
    /* Set device and forward */
    skb->dev = tap->dev;
    skb->protocol = eth_type_trans(skb, tap->dev);
    skb->pkt_type = PACKET_HOST;
    
    err = netif_rx(skb);
    if (err != NET_RX_SUCCESS) {
        dev_kfree_skb(skb);
        return -EIO;
    }
    
    return count;
}

/* TAP poll handler */
static unsigned int tap_poll(struct file *file, poll_table *wait)
{
    struct tap_device *tap = file->private_data;
    unsigned int mask = 0;
    
    poll_wait(file, &tap->read_wait, wait);
    
    if (!skb_queue_empty(&tap->queue)) {
        mask |= POLLIN | POLLRDNORM;
    }
    
    if (tap->opened) {
        mask |= POLLOUT | POLLWRNORM;
    }
    
    return mask;
}

/* Network device xmit for TAP */
static netdev_tx_t tap_xmit(struct sk_buff *skb, struct net_device *dev)
{
    struct tap_device *tap = netdev_priv(dev);
    
    /* Queue packet for userspace */
    skb_queue_tail(&tap->queue, skb);
    wake_up_interruptible(&tap->read_wait);
    
    return NETDEV_TX_OK;
}

/* Create TAP device */
static struct tap_device *tap_create(const char *name, int flags)
{
    struct net_device *dev;
    struct tap_device *tap;
    int err;
    
    /* Allocate net device */
    dev = alloc_netdev(sizeof(struct tap_device), name,
                       NET_NAME_UNKNOWN, ether_setup);
    if (!dev) {
        pr_err("Failed to allocate TAP device\n");
        return ERR_PTR(-ENOMEM);
    }
    
    /* Initialize TAP device */
    tap = netdev_priv(dev);
    tap->dev = dev;
    tap->flags = flags;
    tap->opened = 0;
    
    spin_lock_init(&tap->lock);
    skb_queue_head_init(&tap->queue);
    init_waitqueue_head(&tap->read_wait);
    
    strcpy(tap->name, dev->name);
    
    /* Set network device ops */
    dev->netdev_ops = &tap_netdev_ops;
    dev->header_ops = &eth_header_ops;
    
    /* Set features */
    dev->features |= NETIF_F_LLTX | NETIF_F_SG | NETIF_F_FRAGLIST;
    dev->priv_flags |= IFF_TAP;
    
    /* Set random MAC */
    eth_hw_addr_random(dev);
    
    /* Register network device */
    err = register_netdev(dev);
    if (err) {
        pr_err("Failed to register TAP device\n");
        free_netdev(dev);
        return ERR_PTR(err);
    }
    
    /* Add to global list */
    spin_lock(&tap_list_lock);
    list_add(&tap->list, &tap_devices);
    spin_unlock(&tap_list_lock);
    
    pr_info("TAP device created: %s\n", dev->name);
    return tap;
}

/* Module initialization */
static int __init tap_init(void)
{
    pr_info("%s: TAP/TUN Driver v%s loading...\n", 
            TAP_NAME, TAP_VERSION);
    
    /* Register as misc device */
    /* ... Additional initialization ... */
    
    pr_info("%s: Driver loaded successfully\n", TAP_NAME);
    return 0;
}

/* Module cleanup */
static void __exit tap_exit(void)
{
    struct tap_device *tap, *tmp;
    
    pr_info("%s: TAP/TUN Driver unloading...\n", TAP_NAME);
    
    /* Remove all TAP devices */
    list_for_each_entry_safe(tap, tmp, &tap_devices, list) {
        list_del(&tap->list);
        unregister_netdev(tap->dev);
        free_netdev(tap->dev);
        pr_info("TAP device removed: %s\n", tap->name);
    }
    
    pr_info("%s: Driver unloaded\n", TAP_NAME);
}

module_init(tap_init);
module_exit(tap_exit);
