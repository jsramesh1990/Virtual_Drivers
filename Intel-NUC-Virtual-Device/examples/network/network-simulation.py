#!/usr/bin/env python3
"""
network-simulation.py - Network simulation using virtual interfaces

This script creates a virtual network topology with multiple
namespaces, veth pairs, and bridges for testing and simulation.
"""

import os
import sys
import subprocess
import time
import threading
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NodeType(Enum):
    """Node types in network simulation"""
    ROUTER = "router"
    SWITCH = "switch"
    HOST = "host"
    SERVER = "server"
    CLIENT = "client"

@dataclass
class NetworkNode:
    """Network node configuration"""
    name: str
    type: NodeType
    namespace: str
    interfaces: List[str]
    ip_addresses: List[str]
    routes: List[str]

@dataclass
class Link:
    """Network link between nodes"""
    node1: str
    node2: str
    type: str  # veth, bridge, etc.
    ip1: str
    ip2: str

class NetworkSimulator:
    """Network simulation engine"""
    
    def __init__(self):
        self.nodes: Dict[str, NetworkNode] = {}
        self.links: List[Link] = []
        self.namespaces: set = set()
        self.bridges: set = set()
        
    def create_namespace(self, name: str) -> bool:
        """Create a network namespace"""
        try:
            subprocess.run(f"sudo ip netns add {name}", shell=True, check=True)
            self.namespaces.add(name)
            logger.info(f"Created namespace: {name}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create namespace {name}: {e}")
            return False
    
    def delete_namespace(self, name: str) -> bool:
        """Delete a network namespace"""
        try:
            subprocess.run(f"sudo ip netns del {name}", shell=True, check=True)
            self.namespaces.discard(name)
            logger.info(f"Deleted namespace: {name}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to delete namespace {name}: {e}")
            return False
    
    def create_veth_pair(self, name1: str, name2: str, ns1: str, ns2: str,
                        ip1: str, ip2: str) -> bool:
        """Create veth pair between two namespaces"""
        try:
            # Create veth pair
            subprocess.run(f"sudo ip link add {name1} type veth peer name {name2}", 
                          shell=True, check=True)
            
            # Move interfaces to namespaces
            subprocess.run(f"sudo ip link set {name1} netns {ns1}", shell=True, check=True)
            subprocess.run(f"sudo ip link set {name2} netns {ns2}", shell=True, check=True)
            
            # Configure IP addresses
            subprocess.run(f"sudo ip netns exec {ns1} ip addr add {ip1} dev {name1}", 
                          shell=True, check=True)
            subprocess.run(f"sudo ip netns exec {ns2} ip addr add {ip2} dev {name2}", 
                          shell=True, check=True)
            
            # Bring interfaces up
            subprocess.run(f"sudo ip netns exec {ns1} ip link set {name1} up", 
                          shell=True, check=True)
            subprocess.run(f"sudo ip netns exec {ns2} ip link set {name2} up", 
                          shell=True, check=True)
            
            logger.info(f"Created veth pair: {name1} ({ns1}) <-> {name2} ({ns2})")
            logger.info(f"  IPs: {ip1} <-> {ip2}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create veth pair: {e}")
            return False
    
    def create_bridge(self, name: str, ns: str, ip: str) -> bool:
        """Create a bridge in a namespace"""
        try:
            # Create bridge
            subprocess.run(f"sudo ip netns exec {ns} ip link add {name} type bridge", 
                          shell=True, check=True)
            
            # Assign IP
            subprocess.run(f"sudo ip netns exec {ns} ip addr add {ip} dev {name}", 
                          shell=True, check=True)
            
            # Bring bridge up
            subprocess.run(f"sudo ip netns exec {ns} ip link set {name} up", 
                          shell=True, check=True)
            
            self.bridges.add(f"{ns}:{name}")
            logger.info(f"Created bridge: {name} in {ns} with IP {ip}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to create bridge: {e}")
            return False
    
    def attach_to_bridge(self, ns: str, bridge: str, interface: str) -> bool:
        """Attach interface to bridge"""
        try:
            subprocess.run(f"sudo ip netns exec {ns} ip link set {interface} down", 
                          shell=True, check=True)
            subprocess.run(f"sudo ip netns exec {ns} ip link set {interface} master {bridge}", 
                          shell=True, check=True)
            subprocess.run(f"sudo ip netns exec {ns} ip link set {interface} up", 
                          shell=True, check=True)
            logger.info(f"Attached {interface} to bridge {bridge} in {ns}")
            return True
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to attach to bridge: {e}")
            return False
    
    def create_topology_1(self):
        """Create simple star topology"""
        logger.info("Creating star topology...")
        
        # Create namespaces
        namespaces = ["router", "host1", "host2", "host3"]
        for ns in namespaces:
            self.create_namespace(ns)
        
        # Create bridges in router
        self.create_bridge("br0", "router", "10.0.0.1/24")
        self.create_bridge("br1", "router", "10.0.1.1/24")
        self.create_bridge("br2", "router", "10.0.2.1/24")
        
        # Connect hosts to router
        for i, host in enumerate(["host1", "host2", "host3"]):
            veth1 = f"veth-{host}"
            veth2 = f"veth-r{i}"
            ip1 = f"10.0.{i}.2/24"
            ip2 = f"10.0.{i}.1/24"
            
            self.create_veth_pair(veth1, veth2, host, "router", ip1, ip2)
            
            # Attach router side to bridge
            self.attach_to_bridge("router", f"br{i}", veth2)
            
            # Enable IP forwarding on router
            subprocess.run(f"sudo ip netns exec router sysctl -w net.ipv4.ip_forward=1",
                          shell=True, check=True)
        
        # Add default routes on hosts
        for i, host in enumerate(["host1", "host2", "host3"]):
            subprocess.run(f"sudo ip netns exec {host} ip route add default via 10.0.{i}.1",
                          shell=True, check=True)
        
        logger.info("Star topology created successfully")
        self.show_topology()
    
    def create_topology_2(self):
        """Create mesh topology"""
        logger.info("Creating mesh topology...")
        
        # Create namespaces
        nodes = ["node1", "node2", "node3", "node4"]
        for ns in nodes:
            self.create_namespace(ns)
        
        # Create full mesh connections
        for i, ns1 in enumerate(nodes):
            for ns2 in nodes[i+1:]:
                veth1 = f"veth-{ns1}-{ns2}"
                veth2 = f"veth-{ns2}-{ns1}"
                ip1 = f"10.0.{i}.{j+1}/24"
                ip2 = f"10.0.{j+1}.{i+1}/24"
                
                self.create_veth_pair(veth1, veth2, ns1, ns2, ip1, ip2)
        
        # Add routes
        for ns in nodes:
            subprocess.run(f"sudo ip netns exec {ns} sysctl -w net.ipv4.ip_forward=1",
                          shell=True, check=True)
        
        logger.info("Mesh topology created successfully")
        self.show_topology()
    
    def create_topology_3(self):
        """Create hybrid topology with VMs and containers"""
        logger.info("Creating hybrid topology...")
        
        # Create namespaces
        namespaces = ["switch", "vm1", "vm2", "container1", "container2"]
        for ns in namespaces:
            self.create_namespace(ns)
        
        # Create main switch
        self.create_bridge("br0", "switch", "172.16.0.1/16")
        
        # Connect VMs
        for i, vm in enumerate(["vm1", "vm2"]):
            veth1 = f"veth-{vm}"
            veth2 = f"veth-s{i}"
            ip1 = f"172.16.{i+1}.2/16"
            ip2 = f"172.16.{i+1}.1/16"
            
            self.create_veth_pair(veth1, veth2, vm, "switch", ip1, ip2)
            self.attach_to_bridge("switch", "br0", veth2)
        
        # Connect containers
        for i, container in enumerate(["container1", "container2"]):
            veth1 = f"veth-{container}"
            veth2 = f"veth-s{i+2}"
            ip1 = f"172.16.{i+3}.2/16"
            ip2 = f"172.16.{i+3}.1/16"
            
            self.create_veth_pair(veth1, veth2, container, "switch", ip1, ip2)
            self.attach_to_bridge("switch", "br0", veth2)
        
        # Enable IP forwarding on switch
        subprocess.run(f"sudo ip netns exec switch sysctl -w net.ipv4.ip_forward=1",
                      shell=True, check=True)
        
        # Add routes
        for ns in ["vm1", "vm2", "container1", "container2"]:
            subprocess.run(f"sudo ip netns exec {ns} ip route add default via 172.16.0.1",
                          shell=True, check=True)
        
        logger.info("Hybrid topology created successfully")
        self.show_topology()
    
    def show_topology(self):
        """Display current topology"""
        logger.info("\n=== Network Topology ===")
        
        # Show namespaces
        logger.info("\nNamespaces:")
        for ns in self.namespaces:
            logger.info(f"  {ns}")
            # Show interfaces in namespace
            result = subprocess.run(f"sudo ip netns exec {ns} ip addr show",
                                  shell=True, capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if 'inet ' in line or 'link/ether' in line:
                    logger.info(f"    {line.strip()}")
        
        # Show bridges
        logger.info("\nBridges:")
        for bridge in self.bridges:
            ns, br = bridge.split(':')
            logger.info(f"  {br} in {ns}")
    
    def test_connectivity(self, ns1: str, ns2: str, ip: str):
        """Test connectivity between namespaces"""
        try:
            result = subprocess.run(
                f"sudo ip netns exec {ns1} ping -c 3 {ip}",
                shell=True, capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                logger.info(f"✓ Connectivity: {ns1} -> {ns2} ({ip})")
                return True
            else:
                logger.error(f"✗ Connectivity: {ns1} -> {ns2} ({ip}) failed")
                return False
        except subprocess.TimeoutExpired:
            logger.error(f"✗ Timeout: {ns1} -> {ns2} ({ip})")
            return False
    
    def run_tests(self):
        """Run connectivity tests"""
        logger.info("\n=== Running Connectivity Tests ===")
        
        if len(self.namespaces) >= 2:
            ns_list = list(self.namespaces)
            for i, ns1 in enumerate(ns_list):
                for ns2 in ns_list[i+1:]:
                    # Get IP of ns2
                    result = subprocess.run(
                        f"sudo ip netns exec {ns2} ip addr show | grep 'inet ' | head -1 | awk '{{print $2}}' | cut -d/ -f1",
                        shell=True, capture_output=True, text=True
                    )
                    ip = result.stdout.strip()
                    if ip:
                        self.test_connectivity(ns1, ns2, ip)
    
    def cleanup(self):
        """Clean up all resources"""
        logger.info("Cleaning up...")
        
        # Delete all namespaces
        for ns in list(self.namespaces):
            self.delete_namespace(ns)
        
        # Clear sets
        self.namespaces.clear()
        self.bridges.clear()
        self.nodes.clear()
        self.links.clear()
        
        logger.info("Cleanup complete")

def main():
    """Main function"""
    sim = NetworkSimulator()
    
    if len(sys.argv) < 2:
        print("Usage: network-simulation.py <topology>")
        print("  topologies: star, mesh, hybrid")
        print("  commands: test, cleanup")
        sys.exit(1)
    
    command = sys.argv[1]
    
    try:
        if command == "star":
            sim.create_topology_1()
        elif command == "mesh":
            sim.create_topology_2()
        elif command == "hybrid":
            sim.create_topology_3()
        elif command == "test":
            sim.run_tests()
        elif command == "cleanup":
            sim.cleanup()
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)
        
        # Keep topology running if requested
        if command in ["star", "mesh", "hybrid"]:
            print("\nTopology created. Press Ctrl+C to clean up...")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nCleaning up...")
                sim.cleanup()
    
    except Exception as e:
        logger.error(f"Error: {e}")
        sim.cleanup()
        sys.exit(1)

if __name__ == "__main__":
    main()
