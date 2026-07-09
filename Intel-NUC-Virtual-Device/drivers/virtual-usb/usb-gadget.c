/*
 * usb-gadget.c - USB Gadget Driver for Intel NUC
 * 
 * This driver implements USB gadget functionality for device
 * emulation on Intel NUC platforms.
 * 
 * Version: 1.0
 * Author: Virtual Device Platform Team
 * License: GPL v2
 */

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/usb/gadget.h>
#include <linux/usb/ch9.h>
#include <linux/configfs.h>
#include <linux/device.h>
#include <linux/slab.h>

#define GADGET_NAME "virt-usb-gadget"
#define GADGET_VERSION "1.0.0"
#define MAX_GADGETS 8

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Intel NUC Virtual Device Platform");
MODULE_DESCRIPTION("USB Gadget Driver for Intel NUC");
MODULE_VERSION(GADGET_VERSION);

/* USB gadget structure */
struct virt_gadget {
    struct usb_gadget *gadget;
    struct usb_composite_dev *cdev;
    struct usb_configuration *config;
    struct usb_function *function;
    struct list_head list;
    char name[32];
    int vendor_id;
    int product_id;
    bool active;
};

/* USB gadget function structure */
struct virt_gadget_function {
    struct usb_function function;
    struct virt_gadget *gadget;
    struct usb_ep *ep;
    int (*setup)(struct usb_function *f, const struct usb_ctrlrequest *ctrl);
    void (*bind)(struct usb_function *f, struct usb_configuration *c);
    void (*unbind)(struct usb_function *f);
};

/* Global list */
static LIST_HEAD(virt_gadgets);
static DEFINE_SPINLOCK(gadget_lock);

/* Forward declarations */
static int gadget_bind(struct usb_gadget *gadget, struct usb_gadget_driver *driver);
static void gadget_unbind(struct usb_gadget *gadget);
static void gadget_disconnect(struct usb_gadget *gadget);
static int gadget_setup(struct usb_gadget *gadget, const struct usb_ctrlrequest *ctrl);

/* USB gadget driver */
static struct usb_gadget_driver virt_gadget_driver = {
    .function = "Virtual Gadget",
    .bind = gadget_bind,
    .unbind = gadget_unbind,
    .disconnect = gadget_disconnect,
    .setup = gadget_setup,
    .max_speed = USB_SPEED_SUPER,
    .driver = {
        .name = "virt-gadget",
        .owner = THIS_MODULE,
    },
};

/* Bind gadget */
static int gadget_bind(struct usb_gadget *gadget, struct usb_gadget_driver *driver)
{
    struct virt_gadget *vg;
    int err;
    
    pr_info("%s: Binding gadget\n", GADGET_NAME);
    
    /* Allocate gadget structure */
    vg = kzalloc(sizeof(struct virt_gadget), GFP_KERNEL);
    if (!vg) {
        return -ENOMEM;
    }
    
    vg->gadget = gadget;
    vg->active = true;
    
    spin_lock(&gadget_lock);
    list_add(&vg->list, &virt_gadgets);
    spin_unlock(&gadget_lock);
    
    pr_info("%s: Gadget bound successfully\n", GADGET_NAME);
    return 0;
}

/* Unbind gadget */
static void gadget_unbind(struct usb_gadget *gadget)
{
    struct virt_gadget *vg, *tmp;
    
    spin_lock(&gadget_lock);
    list_for_each_entry_safe(vg, tmp, &virt_gadgets, list) {
        if (vg->gadget == gadget) {
            list_del(&vg->list);
            kfree(vg);
            break;
        }
    }
    spin_unlock(&gadget_lock);
    
    pr_info("%s: Gadget unbound\n", GADGET_NAME);
}

/* Disconnect handler */
static void gadget_disconnect(struct usb_gadget *gadget)
{
    pr_info("%s: Gadget disconnected\n", GADGET_NAME);
}

/* Setup request handler */
static int gadget_setup(struct usb_gadget *gadget, const struct usb_ctrlrequest *ctrl)
{
    pr_info("%s: Setup request: bRequest=0x%02x wValue=0x%04x\n",
            GADGET_NAME, ctrl->bRequest, le16_to_cpu(ctrl->wValue));
    
    return -EOPNOTSUPP;
}

/* Create USB gadget function */
static struct usb_function *create_gadget_function(const char *name, int vendor_id, int product_id)
{
    struct usb_function *function;
    struct virt_gadget_function *vgf;
    int err;
    
    vgf = kzalloc(sizeof(struct virt_gadget_function), GFP_KERNEL);
    if (!vgf) {
        return ERR_PTR(-ENOMEM);
    }
    
    strcpy(vgf->function.name, name);
    vgf->function.strings = NULL;
    vgf->function.fs_descriptors = NULL;
    vgf->function.hs_descriptors = NULL;
    vgf->function.ss_descriptors = NULL;
    
    /* Bind function */
    err = usb_add_function(NULL, &vgf->function);
    if (err) {
        kfree(vgf);
        return ERR_PTR(err);
    }
    
    return &vgf->function;
}

/* Module initialization */
static int __init gadget_init(void)
{
    int err;
    
    pr_info("%s: USB Gadget Driver v%s loading...\n", 
            GADGET_NAME, GADGET_VERSION);
    
    /* Register gadget driver */
    err = usb_gadget_register_driver(&virt_gadget_driver);
    if (err) {
        pr_err("Failed to register USB gadget driver\n");
        return err;
    }
    
    pr_info("%s: Driver loaded successfully\n", GADGET_NAME);
    return 0;
}

/* Module cleanup */
static void __exit gadget_exit(void)
{
    pr_info("%s: USB Gadget Driver unloading...\n", GADGET_NAME);
    usb_gadget_unregister_driver(&virt_gadget_driver);
    pr_info("%s: Driver unloaded\n", GADGET_NAME);
}

module_init(gadget_init);
module_exit(gadget_exit);

/* Module parameters */
module_param_named(vendor_id, vendor_id, int, 0644);
MODULE_PARM_DESC(vendor_id, "Default vendor ID");
module_param_named(product_id, product_id, int, 0644);
MODULE_PARM_DESC(product_id, "Default product ID");
