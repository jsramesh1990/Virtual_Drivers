#!/usr/bin/env python3
"""
network-throughput.py - Network Throughput Performance Test

This script measures network throughput, latency, and packet loss
for virtual network devices on Intel NUC platforms.
"""

import os
import sys
import time
import json
import socket
import threading
import argparse
import subprocess
import logging
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
import queue
import struct
import select

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Colors for output
COLORS = {
    'RESET': '\033[0m',
    'RED': '\033[31m',
    'GREEN': '\033[32m',
    'YELLOW': '\033[33m',
    'BLUE': '\033[34m',
    'MAGENTA': '\033[35m',
    'CYAN': '\033[36m'
}

# Constants
DEFAULT_PORT = 5201
DEFAULT_DURATION = 10
DEFAULT_INTERVAL = 1
PACKET_SIZE = 1472  # Max UDP packet size without fragmentation
TCP_BUFFER_SIZE = 65536

@dataclass
class NetworkStats:
    """Network performance statistics"""
    timestamp: float = 0.0
    bytes_sent: int = 0
    bytes_received: int = 0
    packets_sent: int = 0
    packets_received: int = 0
    packets_lost: int = 0
    min_latency: float = float('inf')
    max_latency: float = 0.0
    avg_latency: float = 0.0
    throughput: float = 0.0
    jitter: float = 0.0
    duration: float = 0.0

@dataclass
class NetworkTestResult:
    """Complete network test result"""
    test_type: str  # tcp, udp, icmp
    interface: str
    duration: float
    stats: NetworkStats
    details: Dict[str, Any] = field(default_factory=dict)

class NetworkTester:
    """Network performance testing engine"""
    
    def __init__(self):
        self.results = []
        self.running = False
        self.lock = threading.Lock()
        
    def tcp_throughput_test(self, host: str, port: int, duration: int, 
                           interface: str = None) -> NetworkTestResult:
        """Test TCP throughput using iperf3"""
        logger.info(f"Testing TCP throughput to {host}:{port}")
        
        start_time = time.time()
        stats = NetworkStats()
        
        # Build iperf3 command
        cmd = [
            'iperf3', '-c', host, '-p', str(port),
            '-t', str(duration), '-i', str(INTERVAL),
            '--json'
        ]
        
        if interface:
            cmd.extend(['--bind', interface])
        
        try:
            # Run iperf3
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=duration + 5
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                
                # Parse results
                if 'end' in data and 'sum_received' in data['end']:
                    received = data['end']['sum_received']
                    stats.bytes_received = received.get('bytes', 0)
                    stats.throughput = received.get('bits_per_second', 0) / 1000000  # Mbps
                    
                    if 'sender' in data['end']:
                        sender = data['end']['sender']
                        stats.bytes_sent = sender.get('bytes', 0)
                        stats.packets_sent = sender.get('packets', 0)
                    
                    # Calculate additional stats
                    stats.duration = duration
                    stats.min_latency = data.get('intervals', [{}])[0].get('sum', {}).get('min_rtt', 0)
                    stats.max_latency = data.get('intervals', [{}])[0].get('sum', {}).get('max_rtt', 0)
                    stats.avg_latency = data.get('intervals', [{}])[0].get('sum', {}).get('rtt', 0) / 1000
                    
            else:
                logger.error(f"iperf3 failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            logger.error("iperf3 timed out")
        except Exception as e:
            logger.error(f"TCP test failed: {e}")
        
        stats.timestamp = start_time
        stats.duration = time.time() - start_time
        
        result = NetworkTestResult(
            test_type='tcp',
            interface=interface or 'default',
            duration=stats.duration,
            stats=stats,
            details={'port': port, 'host': host}
        )
        
        self.results.append(result)
        return result
    
    def udp_throughput_test(self, host: str, port: int, duration: int,
                           interface: str = None) -> NetworkTestResult:
        """Test UDP throughput using iperf3"""
        logger.info(f"Testing UDP throughput to {host}:{port}")
        
        start_time = time.time()
        stats = NetworkStats()
        
        # Build iperf3 command for UDP
        cmd = [
            'iperf3', '-c', host, '-p', str(port),
            '-u', '-t', str(duration), '-i', str(INTERVAL),
            '-b', '0',  # Unlimited bandwidth
            '--json'
        ]
        
        if interface:
            cmd.extend(['--bind', interface])
        
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=duration + 5
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                
                if 'end' in data:
                    if 'sum_received' in data['end']:
                        received = data['end']['sum_received']
                        stats.bytes_received = received.get('bytes', 0)
                        stats.throughput = received.get('bits_per_second', 0) / 1000000
                        stats.packets_received = received.get('packets', 0)
                    
                    if 'sum_sent' in data['end']:
                        sent = data['end']['sum_sent']
                        stats.bytes_sent = sent.get('bytes', 0)
                        stats.packets_sent = sent.get('packets', 0)
                    
                    # Calculate packet loss
                    if stats.packets_sent > 0:
                        stats.packets_lost = stats.packets_sent - stats.packets_received
                        loss_percent = (stats.packets_lost / stats.packets_sent) * 100
                        logger.info(f"Packet loss: {loss_percent:.2f}%")
                    
                    # Jitter from intervals
                    if 'intervals' in data:
                        jitter_sum = 0
                        jitter_count = 0
                        for interval in data['intervals']:
                            if 'sum' in interval:
                                jitter = interval['sum'].get('jitter_ms', 0)
                                if jitter > 0:
                                    jitter_sum += jitter
                                    jitter_count += 1
                        if jitter_count > 0:
                            stats.jitter = jitter_sum / jitter_count
                    
            else:
                logger.error(f"iperf3 failed: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            logger.error("iperf3 timed out")
        except Exception as e:
            logger.error(f"UDP test failed: {e}")
        
        stats.timestamp = start_time
        stats.duration = time.time() - start_time
        
        result = NetworkTestResult(
            test_type='udp',
            interface=interface or 'default',
            duration=stats.duration,
            stats=stats,
            details={'port': port, 'host': host}
        )
        
        self.results.append(result)
        return result
    
    def icmp_latency_test(self, host: str, count: int = 10,
                         interface: str = None) -> NetworkTestResult:
        """Test ICMP latency using ping"""
        logger.info(f"Testing ICMP latency to {host}")
        
        start_time = time.time()
        stats = NetworkStats()
        latencies = []
        
        # Build ping command
        cmd = ['ping', '-c', str(count), '-i', '0.2']
        
        if interface:
            cmd.extend(['-I', interface])
        
        cmd.append(host)
        
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=count * 2 + 5
            )
            
            if result.returncode == 0:
                # Parse ping output
                for line in result.stdout.split('\n'):
                    if 'time=' in line:
                        # Extract latency
                        parts = line.split('time=')
                        if len(parts) > 1:
                            latency = parts[1].split(' ')[0]
                            try:
                                latencies.append(float(latency))
                            except ValueError:
                                pass
                    
                    # Parse packet loss
                    if 'packet loss' in line:
                        loss_str = line.split('packet loss')[0].strip().split()[-1]
                        if loss_str.endswith('%'):
                            try:
                                loss = float(loss_str[:-1])
                                if loss > 0:
                                    stats.packets_lost = int(count * loss / 100)
                            except ValueError:
                                pass
                
                # Calculate latency statistics
                if latencies:
                    stats.min_latency = min(latencies)
                    stats.max_latency = max(latencies)
                    stats.avg_latency = sum(latencies) / len(latencies)
                    
                    # Calculate jitter (std deviation)
                    if len(latencies) > 1:
                        mean = stats.avg_latency
                        variance = sum((l - mean) ** 2 for l in latencies) / len(latencies)
                        stats.jitter = variance ** 0.5
                    
                    stats.packets_received = len(latencies)
                    stats.packets_sent = count
                    
            else:
                logger.warning(f"Ping had non-zero exit code: {result.returncode}")
                
        except subprocess.TimeoutExpired:
            logger.error("Ping timed out")
        except Exception as e:
            logger.error(f"ICMP test failed: {e}")
        
        stats.timestamp = start_time
        stats.duration = time.time() - start_time
        
        result = NetworkTestResult(
            test_type='icmp',
            interface=interface or 'default',
            duration=stats.duration,
            stats=stats,
            details={'host': host, 'count': count}
        )
        
        self.results.append(result)
        return result
    
    def local_loopback_test(self, duration: int = 10) -> NetworkTestResult:
        """Test local loopback performance"""
        return self.tcp_throughput_test('127.0.0.1', DEFAULT_PORT, duration)
    
    def virtual_interface_test(self, interface: str, duration: int = 10) -> NetworkTestResult:
        """Test virtual interface performance"""
        # Get interface IP
        try:
            cmd = f"ip addr show {interface} | grep 'inet ' | awk '{{print $2}}' | cut -d/ -f1"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            ip = result.stdout.strip()
            
            if ip:
                logger.info(f"Testing interface {interface} ({ip})")
                return self.tcp_throughput_test(ip, DEFAULT_PORT, duration, interface)
            else:
                logger.error(f"No IP found for interface {interface}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to test interface {interface}: {e}")
            return None
    
    def multi_stream_test(self, host: str, port: int, streams: int = 4,
                          duration: int = 10) -> NetworkTestResult:
        """Test with multiple parallel streams"""
        logger.info(f"Testing with {streams} parallel streams")
        
        # Use iperf3 with parallel streams
        cmd = [
            'iperf3', '-c', host, '-p', str(port),
            '-P', str(streams), '-t', str(duration),
            '-i', str(INTERVAL), '--json'
        ]
        
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=duration + 10
            )
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                stats = NetworkStats()
                
                if 'end' in data and 'sum_received' in data['end']:
                    received = data['end']['sum_received']
                    stats.bytes_received = received.get('bytes', 0)
                    stats.throughput = received.get('bits_per_second', 0) / 1000000
                
                return NetworkTestResult(
                    test_type='multi_tcp',
                    interface='default',
                    duration=duration,
                    stats=stats,
                    details={'streams': streams, 'host': host, 'port': port}
                )
                
        except Exception as e:
            logger.error(f"Multi-stream test failed: {e}")
        
        return None
    
    def run_tests(self, host: str = None, interface: str = None,
                  duration: int = DEFAULT_DURATION, tests: List[str] = None) -> Dict:
        """Run comprehensive network tests"""
        if not tests:
            tests = ['tcp', 'udp', 'icmp']
        
        results = {}
        
        logger.info(f"Starting network tests (duration: {duration}s, interface: {interface or 'default'})")
        
        # TCP test
        if 'tcp' in tests:
            if host:
                result = self.tcp_throughput_test(host, DEFAULT_PORT, duration, interface)
            else:
                result = self.local_loopback_test(duration)
            results['tcp'] = result
        
        # UDP test
        if 'udp' in tests:
            if host:
                result = self.udp_throughput_test(host, DEFAULT_PORT, duration, interface)
            else:
                # Use localhost for UDP test
                result = self.udp_throughput_test('127.0.0.1', DEFAULT_PORT, duration, interface)
            results['udp'] = result
        
        # ICMP test
        if 'icmp' in tests:
            if host:
                result = self.icmp_latency_test(host, interface=interface)
            else:
                result = self.icmp_latency_test('127.0.0.1', interface=interface)
            results['icmp'] = result
        
        # Virtual interface test
        if interface:
            result = self.virtual_interface_test(interface, duration)
            if result:
                results['virtual_interface'] = result
        
        # Multi-stream test
        if 'multi' in tests:
            if host:
                result = self.multi_stream_test(host, DEFAULT_PORT, 4, duration)
                if result:
                    results['multi_stream'] = result
        
        return results

class NetworkPerfAnalyzer:
    """Network performance analyzer"""
    
    @staticmethod
    def analyze_results(results: Dict) -> Dict:
        """Analyze test results and generate report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'summary': {},
            'recommendations': []
        }
        
        for test_type, result in results.items():
            if not result:
                continue
                
            stats = result.stats
            report['summary'][test_type] = {
                'throughput_mbps': stats.throughput,
                'avg_latency_ms': stats.avg_latency,
                'packet_loss': stats.packets_lost,
                'jitter_ms': stats.jitter
            }
            
            # Generate recommendations
            if test_type == 'tcp':
                if stats.throughput < 100:
                    report['recommendations'].append(
                        f"TCP throughput ({stats.throughput:.2f} Mbps) is low. Check network "
                        "interface and ensure TCP offloading is enabled."
                    )
                    
            elif test_type == 'udp':
                if stats.packets_lost > 5:
                    report['recommendations'].append(
                        f"High UDP packet loss ({stats.packets_lost} packets lost). "
                        "Check network congestion or buffer sizes."
                    )
                    
            elif test_type == 'icmp':
                if stats.avg_latency > 50:
                    report['recommendations'].append(
                        f"High latency ({stats.avg_latency:.2f} ms). "
                        "Check network path and congestion."
                    )
                    
        return report

class NetworkTestCLI:
    """Command line interface for network tests"""
    
    def __init__(self):
        self.tester = NetworkTester()
        self.analyzer = NetworkPerfAnalyzer()
        
    def run(self, args):
        """Run network tests"""
        print(f"\n{COLORS['CYAN']}========================================")
        print(f"Network Throughput Performance Test")
        print(f"========================================{COLORS['RESET']}")
        print()
        
        # Build test list
        tests = ['tcp', 'udp', 'icmp']
        if args.all:
            tests = ['tcp', 'udp', 'icmp', 'multi']
        
        # Run tests
        results = self.tester.run_tests(
            host=args.host,
            interface=args.interface,
            duration=args.duration,
            tests=tests
        )
        
        # Display results
        self._display_results(results)
        
        # Analyze
        report = self.analyzer.analyze_results(results)
        
        # Save results
        if args.output:
            self._save_results(results, report, args.output)
        
        return results
    
    def _display_results(self, results: Dict):
        """Display test results"""
        print(f"\n{COLORS['CYAN']}=== Test Results ==={COLORS['RESET']}")
        print()
        
        for test_type, result in results.items():
            if not result:
                continue
                
            stats = result.stats
            
            print(f"{COLORS['YELLOW']}{test_type.upper()} Test:{COLORS['RESET']}")
            print(f"  Duration: {stats.duration:.2f}s")
            print(f"  Throughput: {stats.throughput:.2f} Mbps")
            
            if stats.avg_latency < float('inf'):
                print(f"  Average Latency: {stats.avg_latency:.2f} ms")
                print(f"  Min Latency: {stats.min_latency:.2f} ms")
                print(f"  Max Latency: {stats.max_latency:.2f} ms")
            
            if stats.packets_lost > 0:
                loss_percent = (stats.packets_lost / stats.packets_sent * 100) if stats.packets_sent > 0 else 0
                print(f"  Packet Loss: {loss_percent:.2f}% ({stats.packets_lost} packets)")
            
            if stats.jitter > 0:
                print(f"  Jitter: {stats.jitter:.2f} ms")
            
            print(f"  Bytes Sent: {stats.bytes_sent:,}")
            print(f"  Bytes Received: {stats.bytes_received:,}")
            print()
    
    def _save_results(self, results: Dict, report: Dict, filename: str):
        """Save results to file"""
        try:
            data = {
                'results': {
                    name: {
                        'test_type': r.test_type,
                        'interface': r.interface,
                        'duration': r.duration,
                        'stats': {
                            'throughput_mbps': r.stats.throughput,
                            'avg_latency_ms': r.stats.avg_latency,
                            'min_latency_ms': r.stats.min_latency,
                            'max_latency_ms': r.stats.max_latency,
                            'packet_loss': r.stats.packets_lost,
                            'jitter_ms': r.stats.jitter,
                            'bytes_sent': r.stats.bytes_sent,
                            'bytes_received': r.stats.bytes_received
                        }
                    }
                    for name, r in results.items() if r
                },
                'report': report
            }
            
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Results saved to {filename}")
            
        except Exception as e:
            logger.error(f"Failed to save results: {e}")

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Network Throughput Performance Test",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test localhost
  %(prog)s
  
  # Test remote host
  %(prog)s -H 192.168.1.100
  
  # Test specific interface
  %(prog)s -i eth0
  
  # All tests with 30 second duration
  %(prog)s -d 30 --all
  
  # Save results
  %(prog)s -o results.json
        """
    )
    
    parser.add_argument('-H', '--host',
                       help='Remote host to test')
    parser.add_argument('-i', '--interface',
                       help='Network interface to test')
    parser.add_argument('-d', '--duration',
                       type=int, default=DEFAULT_DURATION,
                       help=f'Test duration in seconds (default: {DEFAULT_DURATION})')
    parser.add_argument('-p', '--port',
                       type=int, default=DEFAULT_PORT,
                       help=f'Test port (default: {DEFAULT_PORT})')
    parser.add_argument('-o', '--output',
                       help='Output file for results')
    parser.add_argument('--all',
                       action='store_true',
                       help='Run all tests including multi-stream')
    parser.add_argument('-v', '--verbose',
                       action='store_true',
                       help='Enable verbose output')
    
    return parser.parse_args()

def main():
    """Main entry point"""
    args = parse_arguments()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    cli = NetworkTestCLI()
    try:
        results = cli.run(args)
        print(f"\n{COLORS['GREEN']}✓ Network tests completed{COLORS['RESET']}")
    except KeyboardInterrupt:
        print(f"\n{COLORS['YELLOW']}Tests interrupted by user{COLORS['RESET']}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Test failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
