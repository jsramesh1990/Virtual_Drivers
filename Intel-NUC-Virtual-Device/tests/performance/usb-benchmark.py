#!/usr/bin/env python3
"""
usb-benchmark.py - USB Device Performance Benchmark

This script measures USB device performance including read/write
speeds, latency, and IOPS for virtual USB devices on Intel NUC platforms.
"""

import os
import sys
import time
import json
import threading
import argparse
import subprocess
import logging
import tempfile
import shutil
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import struct
import fcntl
import array

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
BLOCK_SIZE = 4096
DEFAULT_SIZE_MB = 100
TEST_FILE_PATTERN = "usb_test_*.dat"

@dataclass
class USBStats:
    """USB performance statistics"""
    read_speed_mb_s: float = 0.0
    write_speed_mb_s: float = 0.0
    read_latency_ms: float = 0.0
    write_latency_ms: float = 0.0
    read_iops: float = 0.0
    write_iops: float = 0.0
    total_bytes: int = 0
    duration: float = 0.0
    block_size: int = 0

@dataclass
class USBTestResult:
    """Complete USB test result"""
    device: str
    mount_point: str
    stats: USBStats
    details: Dict[str, Any] = field(default_factory=dict)

class USBBenchmark:
    """USB performance benchmark"""
    
    def __init__(self):
        self.results = []
        self.lock = threading.Lock()
        self.temp_files = []
        
    def find_usb_devices(self) -> List[str]:
        """Find USB devices mounted on the system"""
        devices = []
        
        try:
            # Find USB devices using lsusb
            result = subprocess.run(
                "lsusb", shell=True, capture_output=True, text=True
            )
            logger.info(f"USB devices found:\n{result.stdout}")
            
            # Find mounted USB devices
            result = subprocess.run(
                "mount | grep -E '/dev/sd[b-z]|/dev/loop' | awk '{print $1}'",
                shell=True, capture_output=True, text=True
            )
            devices = result.stdout.strip().split('\n')
            devices = [d for d in devices if d]
            
            # Also check USB gadget devices
            if os.path.exists('/dev/ttyGS0'):
                devices.append('/dev/ttyGS0')
            
            # Check mass storage gadgets
            for dev in ['/dev/sda', '/dev/sdb', '/dev/sdc', '/dev/sdd']:
                if os.path.exists(dev):
                    devices.append(dev)
                    
        except Exception as e:
            logger.error(f"Failed to find USB devices: {e}")
        
        return devices
    
    def find_mount_point(self, device: str) -> Optional[str]:
        """Find mount point for a device"""
        try:
            result = subprocess.run(
                f"mount | grep {device} | awk '{{print $3}}'",
                shell=True, capture_output=True, text=True
            )
            mount_point = result.stdout.strip()
            return mount_point if mount_point else None
            
        except Exception as e:
            logger.error(f"Failed to find mount point for {device}: {e}")
            return None
    
    def test_read_speed(self, device: str, mount_point: str, 
                        size_mb: int = DEFAULT_SIZE_MB,
                        block_size: int = BLOCK_SIZE) -> float:
        """Test USB read speed"""
        logger.info(f"Testing read speed on {device} ({size_mb}MB)")
        
        # Create test file if not exists
        test_file = os.path.join(mount_point, "test_read.dat")
        
        try:
            # Write test data
            with open(test_file, 'wb') as f:
                f.write(os.urandom(size_mb * 1024 * 1024))
            
            # Ensure data is written
            os.sync()
            time.sleep(1)
            
            # Clear cache
            subprocess.run('echo 3 > /proc/sys/vm/drop_caches', shell=True)
            time.sleep(1)
            
            # Measure read speed
            start_time = time.time()
            
            with open(test_file, 'rb') as f:
                while True:
                    data = f.read(block_size * 1024)
                    if not data:
                        break
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Calculate speed
            speed_mb_s = size_mb / duration
            
            # Cleanup
            os.remove(test_file)
            
            return speed_mb_s
            
        except Exception as e:
            logger.error(f"Read test failed: {e}")
            return 0.0
    
    def test_write_speed(self, mount_point: str, size_mb: int = DEFAULT_SIZE_MB,
                        block_size: int = BLOCK_SIZE) -> float:
        """Test USB write speed"""
        logger.info(f"Testing write speed on {mount_point} ({size_mb}MB)")
        
        test_file = os.path.join(mount_point, "test_write.dat")
        
        try:
            # Generate test data
            data = os.urandom(block_size * 1024)
            data_size = len(data)
            
            # Write test
            start_time = time.time()
            written = 0
            
            with open(test_file, 'wb') as f:
                while written < size_mb * 1024 * 1024:
                    f.write(data)
                    written += data_size
            
            # Ensure data is written
            os.fsync(f.fileno())
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Calculate speed
            speed_mb_s = size_mb / duration
            
            # Cleanup
            os.remove(test_file)
            
            return speed_mb_s
            
        except Exception as e:
            logger.error(f"Write test failed: {e}")
            return 0.0
    
    def test_iops(self, mount_point: str, size_mb: int = DEFAULT_SIZE_MB,
                  block_size: int = 4096) -> Tuple[float, float]:
        """Test USB IOPS (read and write)"""
        logger.info(f"Testing IOPS on {mount_point}")
        
        test_file = os.path.join(mount_point, "test_iops.dat")
        
        try:
            # Prepare test data
            data = os.urandom(block_size)
            num_blocks = (size_mb * 1024 * 1024) // block_size
            
            # Write IOPS test
            start_time = time.time()
            
            with open(test_file, 'wb') as f:
                for _ in range(num_blocks):
                    f.write(data)
            
            os.fsync(f.fileno())
            
            end_time = time.time()
            write_duration = end_time - start_time
            write_iops = num_blocks / write_duration
            
            # Read IOPS test
            # Clear cache
            subprocess.run('echo 3 > /proc/sys/vm/drop_caches', shell=True)
            time.sleep(1)
            
            start_time = time.time()
            
            with open(test_file, 'rb') as f:
                while True:
                    chunk = f.read(block_size)
                    if not chunk:
                        break
            
            end_time = time.time()
            read_duration = end_time - start_time
            read_iops = num_blocks / read_duration
            
            # Cleanup
            os.remove(test_file)
            
            return read_iops, write_iops
            
        except Exception as e:
            logger.error(f"IOPS test failed: {e}")
            return 0.0, 0.0
    
    def test_latency(self, mount_point: str, samples: int = 100) -> Tuple[float, float]:
        """Test USB latency (read and write)"""
        logger.info(f"Testing latency on {mount_point} ({samples} samples)")
        
        test_file = os.path.join(mount_point, "test_latency.dat")
        block_size = 512
        
        read_latencies = []
        write_latencies = []
        
        try:
            # Prepare test data
            data = os.urandom(block_size)
            
            with open(test_file, 'wb') as f:
                # Write latency test
                for _ in range(samples):
                    start_time = time.perf_counter()
                    f.write(data)
                    os.fsync(f.fileno())
                    end_time = time.perf_counter()
                    write_latencies.append((end_time - start_time) * 1000)  # ms
                
                # Read latency test
                f.seek(0)
                for _ in range(samples):
                    start_time = time.perf_counter()
                    f.read(block_size)
                    end_time = time.perf_counter()
                    read_latencies.append((end_time - start_time) * 1000)  # ms
            
            # Cleanup
            os.remove(test_file)
            
            # Calculate averages
            avg_read_latency = sum(read_latencies) / len(read_latencies) if read_latencies else 0
            avg_write_latency = sum(write_latencies) / len(write_latencies) if write_latencies else 0
            
            return avg_read_latency, avg_write_latency
            
        except Exception as e:
            logger.error(f"Latency test failed: {e}")
            return 0.0, 0.0
    
    def run_benchmark(self, device: str = None, mount_point: str = None,
                      size_mb: int = DEFAULT_SIZE_MB) -> USBTestResult:
        """Run complete USB benchmark"""
        logger.info(f"Starting USB benchmark (size: {size_mb}MB)")
        
        # Find USB device if not specified
        if not device:
            devices = self.find_usb_devices()
            if not devices:
                logger.error("No USB devices found")
                return None
            device = devices[0]
            logger.info(f"Using USB device: {device}")
        
        # Find mount point if not specified
        if not mount_point:
            mount_point = self.find_mount_point(device)
            if not mount_point:
                # Create temporary mount point
                mount_point = tempfile.mkdtemp(prefix="usb_test_")
                logger.info(f"Created temporary mount point: {mount_point}")
                # Try to mount
                try:
                    subprocess.run(f"mount {device} {mount_point}", shell=True, check=True)
                except:
                    logger.error(f"Failed to mount {device}")
                    return None
        
        # Run tests
        stats = USBStats()
        stats.block_size = BLOCK_SIZE
        
        # Read speed
        logger.info("Testing read speed...")
        stats.read_speed_mb_s = self.test_read_speed(device, mount_point, size_mb)
        
        # Write speed
        logger.info("Testing write speed...")
        stats.write_speed_mb_s = self.test_write_speed(mount_point, size_mb)
        
        # IOPS
        logger.info("Testing IOPS...")
        stats.read_iops, stats.write_iops = self.test_iops(mount_point, size_mb)
        
        # Latency
        logger.info("Testing latency...")
        stats.read_latency_ms, stats.write_latency_ms = self.test_latency(mount_point)
        
        # Create result
        result = USBTestResult(
            device=device,
            mount_point=mount_point,
            stats=stats,
            details={
                'size_mb': size_mb,
                'block_size': BLOCK_SIZE
            }
        )
        
        self.results.append(result)
        return result
    
    def run_gadget_benchmark(self) -> Optional[USBTestResult]:
        """Benchmark USB gadget device"""
        logger.info("Testing USB gadget performance")
        
        # Check for gadget mass storage
        gadget_devices = ['/dev/sda', '/dev/sdb', '/dev/sdc']
        
        for dev in gadget_devices:
            if os.path.exists(dev):
                logger.info(f"Found USB gadget device: {dev}")
                return self.run_benchmark(dev)
        
        logger.warning("No USB gadget devices found")
        return None
    
    def run_loopback_benchmark(self, size_mb: int = 10) -> USBTestResult:
        """Benchmark USB loopback (RAM disk) for comparison"""
        logger.info("Running loopback benchmark for comparison")
        
        # Create RAM disk
        mount_point = "/mnt/usb_ramdisk"
        os.makedirs(mount_point, exist_ok=True)
        
        try:
            # Mount tmpfs
            subprocess.run(f"mount -t tmpfs -o size={size_mb}M tmpfs {mount_point}", 
                          shell=True, check=True)
            
            # Run benchmark
            result = self.run_benchmark(device="tmpfs", mount_point=mount_point, size_mb=size_mb)
            
            # Cleanup
            subprocess.run(f"umount {mount_point}", shell=True)
            
            return result
            
        except Exception as e:
            logger.error(f"Loopback benchmark failed: {e}")
            return None

class USBAnalyzer:
    """USB benchmark analyzer"""
    
    @staticmethod
    def analyze_results(results: List[USBTestResult]) -> Dict:
        """Analyze benchmark results"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'devices': [],
            'summary': {
                'best_read_speed': 0.0,
                'best_write_speed': 0.0,
                'best_read_iops': 0.0,
                'best_write_iops': 0.0
            },
            'recommendations': []
        }
        
        for result in results:
            if not result:
                continue
                
            stats = result.stats
            device_info = {
                'device': result.device,
                'mount_point': result.mount_point,
                'read_speed_mb_s': stats.read_speed_mb_s,
                'write_speed_mb_s': stats.write_speed_mb_s,
                'read_iops': stats.read_iops,
                'write_iops': stats.write_iops,
                'read_latency_ms': stats.read_latency_ms,
                'write_latency_ms': stats.write_latency_ms
            }
            report['devices'].append(device_info)
            
            # Update summary
            if stats.read_speed_mb_s > report['summary']['best_read_speed']:
                report['summary']['best_read_speed'] = stats.read_speed_mb_s
            if stats.write_speed_mb_s > report['summary']['best_write_speed']:
                report['summary']['best_write_speed'] = stats.write_speed_mb_s
            if stats.read_iops > report['summary']['best_read_iops']:
                report['summary']['best_read_iops'] = stats.read_iops
            if stats.write_iops > report['summary']['best_write_iops']:
                report['summary']['best_write_iops'] = stats.write_iops
            
            # Generate recommendations
            if stats.read_speed_mb_s < 10:
                report['recommendations'].append(
                    f"USB device {result.device} has low read speed ({stats.read_speed_mb_s:.2f} MB/s). "
                    "Consider using USB 3.0 or faster device."
                )
            
            if stats.write_speed_mb_s < 5:
                report['recommendations'].append(
                    f"USB device {result.device} has low write speed ({stats.write_speed_mb_s:.2f} MB/s). "
                    "This may impact virtual device performance."
                )
            
            if stats.read_latency_ms > 10:
                report['recommendations'].append(
                    f"High read latency ({stats.read_latency_ms:.2f} ms) on {result.device}. "
                    "May affect real-time applications."
                )
        
        return report

class USBTestCLI:
    """Command line interface for USB benchmarks"""
    
    def __init__(self):
        self.benchmark = USBBenchmark()
        self.analyzer = USBAnalyzer()
        
    def run(self, args):
        """Run USB benchmark"""
        print(f"\n{COLORS['CYAN']}========================================")
        print(f"USB Performance Benchmark")
        print(f"========================================{COLORS['RESET']}")
        print()
        
        results = []
        
        # List devices
        if args.list:
            devices = self.benchmark.find_usb_devices()
            print(f"{COLORS['YELLOW']}USB Devices:{COLORS['RESET']}")
            for dev in devices:
                mount = self.benchmark.find_mount_point(dev)
                print(f"  {dev} -> {mount or 'not mounted'}")
            return
        
        # Run benchmark
        if args.device:
            result = self.benchmark.run_benchmark(device=args.device, size_mb=args.size)
            if result:
                results.append(result)
        
        if args.gadget:
            result = self.benchmark.run_gadget_benchmark()
            if result:
                results.append(result)
        
        if args.loopback:
            result = self.benchmark.run_loopback_benchmark(args.size)
            if result:
                results.append(result)
        
        if not results:
            # Auto-detect and run
            devices = self.benchmark.find_usb_devices()
            for dev in devices:
                result = self.benchmark.run_benchmark(device=dev, size_mb=args.size)
                if result:
                    results.append(result)
        
        # Display results
        self._display_results(results)
        
        # Analyze
        report = self.analyzer.analyze_results(results)
        
        # Save results
        if args.output:
            self._save_results(results, report, args.output)
        
        return results
    
    def _display_results(self, results: List[USBTestResult]):
        """Display benchmark results"""
        print(f"\n{COLORS['CYAN']}=== Benchmark Results ==={COLORS['RESET']}")
        print()
        
        for result in results:
            if not result:
                continue
                
            stats = result.stats
            
            print(f"{COLORS['YELLOW']}Device: {result.device}{COLORS['RESET']}")
            print(f"  Mount Point: {result.mount_point}")
            print(f"  Read Speed: {stats.read_speed_mb_s:.2f} MB/s")
            print(f"  Write Speed: {stats.write_speed_mb_s:.2f} MB/s")
            print(f"  Read IOPS: {stats.read_iops:.2f}")
            print(f"  Write IOPS: {stats.write_iops:.2f}")
            print(f"  Read Latency: {stats.read_latency_ms:.2f} ms")
            print(f"  Write Latency: {stats.write_latency_ms:.2f} ms")
            print(f"  Block Size: {stats.block_size} bytes")
            print()
    
    def _save_results(self, results: List[USBTestResult], report: Dict, filename: str):
        """Save results to file"""
        try:
            data = {
                'results': [
                    {
                        'device': r.device,
                        'mount_point': r.mount_point,
                        'stats': {
                            'read_speed_mb_s': r.stats.read_speed_mb_s,
                            'write_speed_mb_s': r.stats.write_speed_mb_s,
                            'read_iops': r.stats.read_iops,
                            'write_iops': r.stats.write_iops,
                            'read_latency_ms': r.stats.read_latency_ms,
                            'write_latency_ms': r.stats.write_latency_ms,
                            'block_size': r.stats.block_size
                        }
                    }
                    for r in results if r
                ],
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
        description="USB Performance Benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Benchmark all USB devices
  %(prog)s
  
  # Benchmark specific device
  %(prog)s -d /dev/sdb
  
  # Benchmark USB gadget
  %(prog)s --gadget
  
  # Benchmark with loopback comparison
  %(prog)s --loopback
  
  # List USB devices
  %(prog)s --list
  
  # Save results
  %(prog)s -o results.json
        """
    )
    
    parser.add_argument('-d', '--device',
                       help='USB device to test (e.g., /dev/sdb)')
    parser.add_argument('-s', '--size',
                       type=int, default=DEFAULT_SIZE_MB,
                       help=f'Test size in MB (default: {DEFAULT_SIZE_MB})')
    parser.add_argument('-o', '--output',
                       help='Output file for results')
    parser.add_argument('--gadget',
                       action='store_true',
                       help='Test USB gadget devices')
    parser.add_argument('--loopback',
                       action='store_true',
                       help='Run loopback comparison test')
    parser.add_argument('--list',
                       action='store_true',
                       help='List USB devices')
    parser.add_argument('-v', '--verbose',
                       action='store_true',
                       help='Enable verbose output')
    
    return parser.parse_args()

def main():
    """Main entry point"""
    args = parse_arguments()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    cli = USBTestCLI()
    try:
        results = cli.run(args)
        print(f"\n{COLORS['GREEN']}✓ USB benchmark completed{COLORS['RESET']}")
    except KeyboardInterrupt:
        print(f"\n{COLORS['YELLOW']}Benchmark interrupted by user{COLORS['RESET']}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
