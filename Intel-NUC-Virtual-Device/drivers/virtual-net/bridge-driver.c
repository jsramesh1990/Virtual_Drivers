/*
 * bridge-driver.c - Virtual Bridge Driver for Intel NUC
 * 
 * This driver implements software bridging for connecting multiple
 * virtual and physical network interfaces.
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
#include <linux/if_bridge.h>
#include <linux/rtnetlink.h>
#include <linux/if_vlan.h>
#include <linux/filter.h>

#define BRIDGE_NAME "virt-bridge"
#define BRIDGE_VERSION "1.0.0"
#define MAX_PORTS 32

MODULE_LICENSE("GPL");
MODULE_AUTHOR("Intel NUC Virtual Device Platform");
MODULE_DESCRIPTION("Virtual Bridge Driver for Intel NUC");
MODULE_VERSION(BRIDGE_VERSION);

/* Bridge port structure */
struct bridge_port {
    struct net_device *dev;
    struct bridge_port *next;
    int port_num;
    bool enabled;
    bool learning;
    bool forwarding;
    u8 mac_addr[ETH_ALEN];
    struct list_head list;
};

/* Bridge private data */
struct bridge_priv {
    struct net_device *dev;
    struct bridge_port *ports[MAX_PORTS];
    int num_ports;
    spinlock_t lock;
    bool stp_enabled;
    bool vlan_filtering;
    int forward_delay;
    u64 rx_packets;
    u64 tx_packets;
    u64 rx_bytes;
    u64 tx_bytes;
    struct list_head port_list;
};

/* Forward declarations */
static int bridge_open(struct net_device *dev);
static int bridge_close(struct net_device *dev);
static int bridge_xmit(struct sk_buff *skb, struct net_device *dev);
static int bridge_add_port(struct net_device *bridge, struct net_device *port);
static int bridge_remove_port(struct net_device *bridge, struct net_device *port);
static int bridge_ioctl(struct net_device *dev, struct ifreq *ifr, int cmd);

/* Network device operations */
static const struct net_device_ops bridge_ops = {
    .ndo_open = bridge_open,
    .ndo_stop = bridge_close,
    .ndo_start_xmit = bridge_xmit,
    .ndo_do_ioctl = bridge_ioctl,
};

/* Initialize bridge */
static int bridge_open(struct net_device *dev)
{
    struct bridge_priv *priv = netdev_priv(dev);
    unsigned long flags;
    
    spin_lock_irqsave(&priv->lock, flags);
    netif_start_queue(dev);
    spin_unlock_irqrestore(&priv->lock, flags);
    
    pr_info("%s: Bridge opened\n", dev->name);
    return 0;
}

/* Close bridge */
static int bridge_close(struct net_device *dev)
{
    struct bridge_priv *priv = netdev_priv(dev);
    unsigned long flags;
    
    spin_lock_irqsave(&priv->lock, flags);
    netif_stop_queue(dev);
    spin_unlock_irqrestore(&priv->lock, flags);
    
    pr_info("%s: Bridge closed\n", dev->name);
    return 0;
}

/* Bridge transmit handler */
static int bridge_xmit(struct sk_buff *skb, struct net_device *dev)
{
    struct bridge_priv *priv = netdev_priv(dev);
    struct bridge_port *port;
    unsigned long flags;
    int i;
    bool forwarded = false;
    
    spin_lock_irqsave(&priv->lock, flags);
    
    /* Update statistics */
    priv->tx_packets++;
    priv->tx_bytes += skb->len;
    
    /* Forward to all ports except incoming */
    for (i = 0; i < MAX_PORTS && i < priv->num_ports; i++) {
        port = priv->ports[i];
        if (!port || !port->enabled || !port->forwarding)
            continue;
        
        if (port->dev == skb->dev)
            continue;
        
        /* Clone and forward */
        struct sk_buff *clone = skb_clone(skb, GFP_ATOMIC);
        if (clone) {
            clone->dev = port->dev;
            clone->protocol = eth_type_trans(clone, port->dev);
            netif_rx(clone);
            forwarded = true;
        }
    }
    
    spin_unlock_irqrestore(&priv->lock, flags);
    
    if (!forwarded) {
        priv->rx_dropped++;
    }
    
    dev_kfree_skb(skb);
    return NETDEV_TX_OK;
}

/* Add port to bridge */
static int bridge_add_port(struct net_device *bridge, struct net_device *port)
{
    struct bridge_priv *priv = netdev_priv(bridge);
    struct bridge_port *new_port;
    unsigned long flags;
    int i;
    
    if (!bridge || !port) {
        pr_err("Invalid bridge or port device\n");
        return -EINVAL;
    }
    
    spin_lock_irqsave(&priv->lock, flags);
    
    /* Check if already added */
    for (i = 0; i < MAX_PORTS && i < priv->num_ports; i++) {
        if (priv->ports[i] && priv->ports[i]->dev == port) {
            spin_unlock_irqrestore(&priv->lock, flags);
            pr_warn("%s: Port %s already added to bridge\n", 
                    bridge->name, port->name);
            return -EEXIST;
        }
    }
    
    if (priv->num_ports >= MAX_PORTS) {
        spin_unlock_irqrestore(&priv->lock, flags);
        pr_err("%s: Maximum ports reached\n", bridge->name);
        return -ENOSPC;
    }
    
    /* Allocate and initialize port */
    new_port = kzalloc(sizeof(struct bridge_port), GFP_ATOMIC);
    if (!new_port) {
        spin_unlock_irqrestore(&priv->lock, flags);
        return -ENOMEM;
    }
    
    new_port->dev = port;
    new_port->port_num = priv->num_ports;
    new_port->enabled = true;
    new_port->learning = true;
    new_port->forwarding = true;
    memcpy(new_port->mac_addr, port->dev_addr, ETH_ALEN);
    
    priv->ports[priv->num_ports] = new_port;
    priv->num_ports++;
    
    spin_unlock_irqrestore(&priv->lock, flags);
    
    pr_info("%s: Port %s added to bridge %s\n", 
            bridge->name, port->name, bridge->name);
    return 0;
}

/* Remove port from bridge */
static int bridge_remove_port(struct net_device *bridge, struct net_device *port)
{
    struct bridge_priv *priv = netdev_priv(bridge);
    unsigned long flags;
    int i;
    
    spin_lock_irqsave(&priv->lock, flags);
    
    for (i = 0; i < MAX_PORTS && i < priv->num_ports; i++) {
        if (priv->ports[i] && priv->ports[i]->dev == port) {
            kfree(priv->ports[i]);
            priv->ports[i] = NULL;
            priv->num_ports--;
            
            spin_unlock_irqrestore(&priv->lock, flags);
            pr_info("%s: Port %s removed from bridge %s\n", 
                    bridge->name, port->name, bridge->name);
            return 0;
        }
    }
    
    spin_unlock_irqrestore(&priv->lock, flags);
    pr_warn("%s: Port %s not found in bridge %s\n", 
            bridge->name, port->name, bridge->name);
    return -ENOENT;
}

/* Bridge IOCTL handler */
static int bridge_ioctl(struct net_device *dev, struct ifreq *ifr, int cmd)
{
    struct bridge_priv *priv = netdev_priv(dev);
    struct ifbrreq brreq;
    int err = 0;
    
    if (copy_from_user(&brreq, ifr->ifr_data, sizeof(brreq))) {
        return -EFAULT;
    }
    
    switch (cmd) {
        case SIOCBRADDIF:
            /* Add interface to bridge */
            err = bridge_add_port(dev, __dev_get_by_name(&init_net, brreq.ifr_name));
            break;
            
        case SIOCBRDELIF:
            /* Remove interface from bridge */
            err = bridge_remove_port(dev, __dev_get_by_name(&init_net, brreq.ifr_name));
            break;
            
        case SIOCGIFBR:
            /* Get bridge information */
            brreq.ifr_count = priv->num_ports;
            if (copy_to_user(ifr->ifr_data, &brreq, sizeof(brreq))) {
                return -EFAULT;
            }
            break;
            
        case SIOCSIFBR:
            /* Set bridge configuration */
            priv->forward_delay = brreq.ifr_forward_delay;
            priv->stp_enabled = brreq.ifr_stp_enabled;
            priv->vlan_filtering = brreq.ifr_vlan_filtering;
            break;
            
        default:
            err = -EOPNOTSUPP;
            break;
    }
    
    return err;
}

/* Module initialization */
static int __init bridge_init(void)
{
    struct net_device *dev;
    struct bridge_priv *priv;
    int err;
    
    pr_info("%s: Virtual Bridge Driver v%s loading...\n", 
            BRIDGE_NAME, BRIDGE_VERSION);
    
    /* Allocate bridge device */
    dev = alloc_netdev(sizeof(struct bridge_priv), "br%d",
                       NET_NAME_UNKNOWN, ether_setup);
    if (!dev) {
        pr_err("Failed to allocate bridge device\n");
        return -ENOMEM;
    }
    
    /* Initialize private data */
    priv = netdev_priv(dev);
    priv->dev = dev;
    priv->num_ports = 0;
    priv->forward_delay = 15;  /* 15 seconds */
    priv->stp_enabled = false;
    priv->vlan_filtering = false;
    
    spin_lock_init(&priv->lock);
    INIT_LIST_HEAD(&priv->port_list);
    
    /* Set device operations */
    dev->netdev_ops = &bridge_ops;
    dev->features |= NETIF_F_LLTX | NETIF_F_HW_VLAN_CTAG_FILTER;
    dev->flags |= IFF_BROADCAST | IFF_MULTICAST;
    
    /* Set random MAC address */
    eth_hw_addr_random(dev);
    
    /* Register device */
    err = register_netdev(dev);
    if (err) {
        pr_err("Failed to register bridge device\n");
        free_netdev(dev);
        return err;
    }
    
    pr_info("Virtual bridge device registered: %s\n", dev->name);
    pr_info("%s: Driver loaded successfully\n", BRIDGE_NAME);
    
    return 0;
}

/* Module cleanup */
static void __exit bridge_exit(void)
{
    pr_info("%s: Virtual Bridge Driver unloading...\n", BRIDGE_NAME);
    pr_info("%s: Driver unloaded\n", BRIDGE_NAME);
}

module_init(bridge_init);
module_exit(bridge_exit);
