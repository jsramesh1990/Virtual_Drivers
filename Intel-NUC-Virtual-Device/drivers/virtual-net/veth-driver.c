/*
 * veth-driver.c - Virtual Ethernet Driver for Intel NUC
 * 
 * This driver implements virtual ethernet pairs (veth) for container
 * and VM networking on Intel NUC platforms.
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
#include <linux/if_arp.h>
#include <linux/rtnetlink.h>
#include <linux/stat.h>
#include <linux/ethtool.h>
#include <linux/u64_stats_sync.h>

#define DRIVER_NAME "virt-net-driver"
#define DRIVER_VERSION "1.0.0"
#define DRIVER_AUTHOR "Intel NUC Virtual Device Platform"

MODULE_LICENSE("GPL");
MODULE_AUTHOR(DRIVER_AUTHOR);
MODULE_DESCRIPTION("Virtual Ethernet Driver for Intel NUC");
MODULE_VERSION(DRIVER_VERSION);

/* Per-device private data structure */
struct virt_net_priv {
    struct net_device *dev;
    struct net_device *peer;
    spinlock_t lock;
    struct u64_stats_sync stats_sync;
    
    /* Statistics */
    u64 rx_packets;
    u64 tx_packets;
    u64 rx_bytes;
    u64 tx_bytes;
    u64 rx_errors;
    u64 tx_errors;
    u64 rx_dropped;
    u64 tx_dropped;
    
    /* Features */
    u32 features;
    int mtu;
    bool up;
    bool peer_up;
};

/* Forward declarations */
static int virt_net_open(struct net_device *dev);
static int virt_net_close(struct net_device *dev);
static int virt_net_xmit(struct sk_buff *skb, struct net_device *dev);
static void virt_net_stats(struct net_device *dev, struct rtnl_link_stats64 *stats);
static int virt_net_change_mtu(struct net_device *dev, int new_mtu);
static int virt_net_set_mac_address(struct net_device *dev, void *addr);
static int virt_net_ioctl(struct net_device *dev, struct ifreq *ifr, int cmd);

/* Network device operations */
static const struct net_device_ops virt_net_ops = {
    .ndo_open = virt_net_open,
    .ndo_stop = virt_net_close,
    .ndo_start_xmit = virt_net_xmit,
    .ndo_get_stats64 = virt_net_stats,
    .ndo_change_mtu = virt_net_change_mtu,
    .ndo_set_mac_address = virt_net_set_mac_address,
    .ndo_do_ioctl = virt_net_ioctl,
};

/* Open the device */
static int virt_net_open(struct net_device *dev)
{
    struct virt_net_priv *priv = netdev_priv(dev);
    unsigned long flags;
    
    spin_lock_irqsave(&priv->lock, flags);
    priv->up = true;
    netif_start_queue(dev);
    spin_unlock_irqrestore(&priv->lock, flags);
    
    pr_info("%s: Device opened\n", dev->name);
    return 0;
}

/* Close the device */
static int virt_net_close(struct net_device *dev)
{
    struct virt_net_priv *priv = netdev_priv(dev);
    unsigned long flags;
    
    spin_lock_irqsave(&priv->lock, flags);
    priv->up = false;
    netif_stop_queue(dev);
    spin_unlock_irqrestore(&priv->lock, flags);
    
    pr_info("%s: Device closed\n", dev->name);
    return 0;
}

/* Transmit packet */
static int virt_net_xmit(struct sk_buff *skb, struct net_device *dev)
{
    struct virt_net_priv *priv = netdev_priv(dev);
    struct net_device *peer;
    unsigned long flags;
    int len = skb->len;
    
    spin_lock_irqsave(&priv->lock, flags);
    
    peer = priv->peer;
    if (!peer || !priv->up) {
        spin_unlock_irqrestore(&priv->lock, flags);
        priv->tx_dropped++;
        dev_kfree_skb(skb);
        return NETDEV_TX_OK;
    }
    
    /* Update statistics */
    u64_stats_update_begin(&priv->stats_sync);
    priv->tx_packets++;
    priv->tx_bytes += len;
    u64_stats_update_end(&priv->stats_sync);
    
    /* Forward to peer device */
    skb->dev = peer;
    skb->protocol = eth_type_trans(skb, peer);
    skb->pkt_type = PACKET_HOST;
    
    /* Queue for transmission */
    if (netif_rx(skb) == NET_RX_SUCCESS) {
        spin_unlock_irqrestore(&priv->lock, flags);
        return NETDEV_TX_OK;
    }
    
    spin_unlock_irqrestore(&priv->lock, flags);
    priv->tx_dropped++;
    return NETDEV_TX_OK;
}

/* Get statistics */
static void virt_net_stats(struct net_device *dev, struct rtnl_link_stats64 *stats)
{
    struct virt_net_priv *priv = netdev_priv(dev);
    unsigned int start;
    
    do {
        start = u64_stats_fetch_begin(&priv->stats_sync);
        stats->rx_packets = priv->rx_packets;
        stats->tx_packets = priv->tx_packets;
        stats->rx_bytes = priv->rx_bytes;
        stats->tx_bytes = priv->tx_bytes;
        stats->rx_errors = priv->rx_errors;
        stats->tx_errors = priv->tx_errors;
        stats->rx_dropped = priv->rx_dropped;
        stats->tx_dropped = priv->tx_dropped;
    } while (u64_stats_fetch_retry(&priv->stats_sync, start));
}

/* Change MTU */
static int virt_net_change_mtu(struct net_device *dev, int new_mtu)
{
    struct virt_net_priv *priv = netdev_priv(dev);
    
    if (new_mtu < 68 || new_mtu > 65536) {
        pr_err("%s: Invalid MTU %d\n", dev->name, new_mtu);
        return -EINVAL;
    }
    
    priv->mtu = new_mtu;
    dev->mtu = new_mtu;
    
    pr_info("%s: MTU changed to %d\n", dev->name, new_mtu);
    return 0;
}

/* Set MAC address */
static int virt_net_set_mac_address(struct net_device *dev, void *addr)
{
    struct sockaddr *sa = addr;
    
    if (!is_valid_ether_addr(sa->sa_data)) {
        pr_err("%s: Invalid MAC address\n", dev->name);
        return -EADDRNOTAVAIL;
    }
    
    memcpy(dev->dev_addr, sa->sa_data, ETH_ALEN);
    pr_info("%s: MAC address changed to %pM\n", dev->name, dev->dev_addr);
    return 0;
}

/* IOCTL handler */
static int virt_net_ioctl(struct net_device *dev, struct ifreq *ifr, int cmd)
{
    struct virt_net_priv *priv = netdev_priv(dev);
    struct ifreq ifrr;
    int err = 0;
    
    switch (cmd) {
        case SIOCDEVPRIVATE:
            /* Get peer information */
            if (copy_from_user(&ifrr, ifr->ifr_data, sizeof(ifrr))) {
                return -EFAULT;
            }
            
            if (strlen(priv->peer->name) < sizeof(ifrr.ifr_name)) {
                strcpy(ifrr.ifr_name, priv->peer->name);
                if (copy_to_user(ifr->ifr_data, &ifrr, sizeof(ifrr))) {
                    return -EFAULT;
                }
            }
            break;
            
        default:
            err = -EOPNOTSUPP;
            break;
    }
    
    return err;
}

/* Module initialization */
static int __init virt_net_init(void)
{
    struct net_device *dev1, *dev2;
    struct virt_net_priv *priv1, *priv2;
    int err;
    
    pr_info("%s: Virtual Network Driver v%s loading...\n", 
            DRIVER_NAME, DRIVER_VERSION);
    
    /* Allocate first device */
    dev1 = alloc_netdev(sizeof(struct virt_net_priv), "veth%d",
                        NET_NAME_UNKNOWN, ether_setup);
    if (!dev1) {
        pr_err("Failed to allocate first device\n");
        return -ENOMEM;
    }
    
    /* Allocate second device */
    dev2 = alloc_netdev(sizeof(struct virt_net_priv), "veth%d",
                        NET_NAME_UNKNOWN, ether_setup);
    if (!dev2) {
        pr_err("Failed to allocate second device\n");
        free_netdev(dev1);
        return -ENOMEM;
    }
    
    /* Initialize private data */
    priv1 = netdev_priv(dev1);
    priv2 = netdev_priv(dev2);
    
    priv1->dev = dev1;
    priv1->peer = dev2;
    priv2->dev = dev2;
    priv2->peer = dev1;
    
    priv1->mtu = 1500;
    priv2->mtu = 1500;
    priv1->up = false;
    priv2->up = false;
    
    spin_lock_init(&priv1->lock);
    spin_lock_init(&priv2->lock);
    u64_stats_init(&priv1->stats_sync);
    u64_stats_init(&priv2->stats_sync);
    
    /* Set device operations */
    dev1->netdev_ops = &virt_net_ops;
    dev2->netdev_ops = &virt_net_ops;
    
    dev1->features |= NETIF_F_LLTX | NETIF_F_SG | NETIF_F_FRAGLIST;
    dev2->features |= NETIF_F_LLTX | NETIF_F_SG | NETIF_F_FRAGLIST;
    
    dev1->hw_features |= dev1->features;
    dev2->hw_features |= dev2->features;
    
    /* Set random MAC addresses */
    eth_hw_addr_random(dev1);
    eth_hw_addr_random(dev2);
    
    /* Register devices */
    err = register_netdev(dev1);
    if (err) {
        pr_err("Failed to register first device\n");
        free_netdev(dev1);
        free_netdev(dev2);
        return err;
    }
    
    err = register_netdev(dev2);
    if (err) {
        pr_err("Failed to register second device\n");
        unregister_netdev(dev1);
        free_netdev(dev1);
        free_netdev(dev2);
        return err;
    }
    
    pr_info("Virtual network devices registered: %s <-> %s\n",
            dev1->name, dev2->name);
    pr_info("%s: Driver loaded successfully\n", DRIVER_NAME);
    
    return 0;
}

/* Module cleanup */
static void __exit virt_net_exit(void)
{
    pr_info("%s: Virtual Network Driver unloading...\n", DRIVER_NAME);
    pr_info("%s: Driver unloaded\n", DRIVER_NAME);
}

module_init(virt_net_init);
module_exit(virt_net_exit);

/* Module parameters */
module_param_named(debug, debug, int, 0644);
MODULE_PARM_DESC(debug, "Enable debug output (0=off, 1=on)");
