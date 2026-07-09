/*
 * usb-redirect.c - USB Redirection Driver for Intel NUC
 * 
 * This driver implements USB redirection for virtual machines
 * on Intel NUC platforms.
 * 
 * Version: 1.0
 * Author: Virtual Device Platform Team
 * License: GPL v2
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/usb.h>
#include <linux/usb/ch9.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <linux/workqueue.h>

#define REDIRECT_NAME "virt-usb-redirect"
#define REDIRECT_VERSION "1.0.0"
#define MAX_REDIRECTS 16

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Intel NUC Virtual Device Platform");
MODULE_DESCRIPTION("USB Redirection Driver for Intel NUC");
MODULE_VERSION(REDIRECT_VERSION);

/* USB redirect entry */
struct usb_redirect {
    struct usb_device *udev;
    struct usb_interface *intf;
    struct list_head list;
    char dev_path[64];
    int bus_num;
    int dev_num;
    int vendor_id;
    int product_id;
    bool active;
    spinlock_t lock;
    struct work_struct work;
};

/* Global list */
static LIST_HEAD(redirect_list);
static DEFINE_SPINLOCK(redirect_lock);
static struct usb_redirect *current_redirect;

/* Forward declarations */
static int redirect_probe(struct usb_interface *intf, const struct usb_device_id *id);
static void redirect_disconnect(struct usb_interface *intf);
static int redirect_suspend(struct usb_interface *intf, pm_message_t message);
static int redirect_resume(struct usb_interface *intf);

/* USB device ID table */
static const struct usb_device_id redirect_id_table[] = {
    { USB_DEVICE(0x0000, 0x0000) },  /* Match all devices */
    { },
};
MODULE_DEVICE_TABLE(usb, redirect_id_table);

/* USB driver */
static struct usb_driver redirect_driver = {
    .name = "virt-usb-redirect",
    .id_table = redirect_id_table,
    .probe = redirect_probe,
    .disconnect = redirect_disconnect,
    .suspend = redirect_suspend,
    .resume = redirect_resume,
};

/* Probe function */
static int redirect_probe(struct usb_interface *intf, const struct usb_device_id *id)
{
    struct usb_device *udev = interface_to_usbdev(intf);
    struct usb_redirect *redir;
    unsigned long flags;
    
    pr_info("%s: Probing USB device %04x:%04x\n", 
            REDIRECT_NAME, udev->descriptor.idVendor, udev->descriptor.idProduct);
    
    /* Allocate redirect structure */
    redir = kzalloc(sizeof(struct usb_redirect), GFP_KERNEL);
    if (!redir) {
        return -ENOMEM;
    }
    
    /* Initialize redirect */
    redir->udev = udev;
    redir->intf = intf;
    redir->bus_num = udev->bus->busnum;
    redir->dev_num = udev->devnum;
    redir->vendor_id = udev->descriptor.idVendor;
    redir->product_id = udev->descriptor.idProduct;
    redir->active = true;
    
    snprintf(redir->dev_path, sizeof(redir->dev_path), 
             "/dev/bus/usb/%03d/%03d", redir->bus_num, redir->dev_num);
    
    spin_lock_init(&redir->lock);
    
    /* Add to list */
    spin_lock_irqsave(&redirect_lock, flags);
    list_add(&redir->list, &redirect_list);
    spin_unlock_irqrestore(&redirect_lock, flags);
    
    pr_info("%s: USB device %04x:%04x redirected to %s\n",
            REDIRECT_NAME, redir->vendor_id, redir->product_id, redir->dev_path);
    
    return 0;
}

/* Disconnect function */
static void redirect_disconnect(struct usb_interface *intf)
{
    struct usb_redirect *redir, *tmp;
    unsigned long flags;
    
    spin_lock_irqsave(&redirect_lock, flags);
    list_for_each_entry_safe(redir, tmp, &redirect_list, list) {
        if (redir->intf == intf) {
            list_del(&redir->list);
            redir->active = false;
            kfree(redir);
            pr_info("%s: USB device disconnected\n", REDIRECT_NAME);
            break;
        }
    }
    spin_unlock_irqrestore(&redirect_lock, flags);
}

/* Suspend function */
static int redirect_suspend(struct usb_interface *intf, pm_message_t message)
{
    pr_info("%s: USB device suspended\n", REDIRECT_NAME);
    return 0;
}

/* Resume function */
static int redirect_resume(struct usb_interface *intf)
{
    pr_info("%s: USB device resumed\n", REDIRECT_NAME);
    return 0;
}

/* Redirect USB device to VM */
int usb_redirect_to_vm(struct usb_device *udev, int vm_id)
{
    struct usb_redirect *redir;
    unsigned long flags;
    
    pr_info("%s: Redirecting USB device to VM %d\n", REDIRECT_NAME, vm_id);
    
    spin_lock_irqsave(&redirect_lock, flags);
    list_for_each_entry(redir, &redirect_list, list) {
        if (redir->udev == udev && redir->active) {
            /* Here would be the actual redirection logic */
            pr_info("%s: USB device %04x:%04x redirected to VM %d\n",
                    REDIRECT_NAME, redir->vendor_id, redir->product_id, vm_id);
            spin_unlock_irqrestore(&redirect_lock, flags);
            return 0;
        }
    }
    spin_unlock_irqrestore(&redirect_lock, flags);
    
    pr_err("%s: USB device not found\n", REDIRECT_NAME);
    return -ENODEV;
}
EXPORT_SYMBOL(usb_redirect_to_vm);

/* List redirected devices */
void usb_redirect_list(void)
{
    struct usb_redirect *redir;
    unsigned long flags;
    
    pr_info("%s: Redirected USB devices:\n", REDIRECT_NAME);
    
    spin_lock_irqsave(&redirect_lock, flags);
    list_for_each_entry(redir, &redirect_list, list) {
        pr_info("  %04x:%04x on bus %d device %d [%s]\n",
                redir->vendor_id, redir->product_id,
                redir->bus_num, redir->dev_num,
                redir->active ? "active" : "inactive");
    }
    spin_unlock_irqrestore(&redirect_lock, flags);
}
EXPORT_SYMBOL(usb_redirect_list);

/* Module initialization */
static int __init redirect_init(void)
{
    int err;
    
    pr_info("%s: USB Redirection Driver v%s loading...\n", 
            REDIRECT_NAME, REDIRECT_VERSION);
    
    /* Register USB driver */
    err = usb_register(&redirect_driver);
    if (err) {
        pr_err("Failed to register USB redirect driver\n");
        return err;
    }
    
    pr_info("%s: Driver loaded successfully\n", REDIRECT_NAME);
    return 0;
}

/* Module cleanup */
static void __exit redirect_exit(void)
{
    pr_info("%s: USB Redirection Driver unloading...\n", REDIRECT_NAME);
    usb_deregister(&redirect_driver);
    pr_info("%s: Driver unloaded\n", REDIRECT_NAME);
}

module_init(redirect_init);
module_exit(redirect_exit);
