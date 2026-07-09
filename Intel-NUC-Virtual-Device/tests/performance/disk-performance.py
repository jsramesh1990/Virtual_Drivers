#!/usr/bin/env python3
"""
disk-performance.py - Disk Performance Test for Virtual Devices

This script measures disk I/O performance for virtual disk devices
including loop devices, NBD, and physical disks on Intel NUC platforms.
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
import struct
import fcntl
import mmap
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

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
BLOCK_SIZES = [512, 1024, 2048, 4096, 8192, 16384, 32768, 65536]
DEFAULT_SIZE_MB = 100
DEFAULT_BLOCK_SIZE = 4096
DEFAULT_THREADS = 4

@dataclass
class DiskStats:
    """Disk performance statistics"""
    read_speed_mb_s: float = 0.0
    write_speed_mb_s: float = 0.0
    rand_read_speed_mb_s: float = 0.0
    rand_write_speed_mb_s: float = 0.0
    read_iops: float = 0.0
    write_iops: float = 0.0
    rand_read_iops: float = 0.0
    rand_write_iops: float = 0.0
    read_latency_ms: float = 0.0
    write_latency_ms: float = 0.0
    total_bytes: int = 0
    duration: float = 0.0
    block_size: int = 0

@dataclass
class DiskTestResult:
    """Complete disk test result"""
    device: str
    mount_point: str
    stats: DiskStats
    details: Dict[str, Any] = field(default_factory=dict)

class DiskPerformanceTester:
    """Disk performance testing engine"""
    
    def __init__(self):
        self.results = []
        self.lock = threading.Lock()
        self.temp_files = []
        
    def find_block_devices(self) -> List[str]:
        """Find available block devices"""
        devices = []
        
        try:
            # Find all block devices
            result = subprocess.run(
                "lsblk -l -o NAME,TYPE,SIZE,MOUNTPOINT | grep -E 'disk|loop' | awk '{print $1}'",
                shell=True, capture_output=True, text=True
            )
            
            for dev in result.stdout.strip().split('\n'):
                if dev:
                    devices.append(f"/dev/{dev}")
            
            # Also find loop devices
            for loop in range(0, 256):
                dev = f"/dev/loop{loop}"
                if os.path.exists(dev):
                    devices.append(dev)
                    
        except Exception as e:
            logger.error(f"Failed to find block devices: {e}")
        
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
    
    def test_sequential_read(self, device: str, mount_point: str,
                            size_mb: int = DEFAULT_SIZE_MB,
                            block_size: int = DEFAULT_BLOCK_SIZE) -> float:
        """Test sequential read speed"""
        logger.info(f"Testing sequential read on {device} ({size_mb}MB)")
        
        test_file = os.path.join(mount_point, "test_seq_read.dat")
        
        try:
            # Create test file
            with open(test_file, 'wb') as f:
                f.write(os.urandom(size_mb * 1024 * 1024))
            
            # Clear cache
            subprocess.run('echo 3 > /proc/sys/vm/drop_caches', shell=True)
            time.sleep(1)
            
            # Measure read speed
            start_time = time.time()
            total_read = 0
            block_bytes = block_size * 1024
            
            with open(test_file, 'rb') as f:
                while True:
                    data = f.read(block_bytes)
                    if not data:
                        break
                    total_read += len(data)
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Cleanup
            os.remove(test_file)
            
            speed_mb_s = total_read / (1024 * 1024) / duration if duration > 0 else 0
            return speed_mb_s
            
        except Exception as e:
            logger.error(f"Sequential read test failed: {e}")
            return 0.0
    
    def test_sequential_write(self, mount_point: str,
                             size_mb: int = DEFAULT_SIZE_MB,
                             block_size: int = DEFAULT_BLOCK_SIZE) -> float:
        """Test sequential write speed"""
        logger.info(f"Testing sequential write on {mount_point} ({size_mb}MB)")
        
        test_file = os.path.join(mount_point, "test_seq_write.dat")
        
        try:
            # Generate test data
            block_bytes = block_size * 1024
            data = os.urandom(block_bytes)
            
            # Measure write speed
            start_time = time.time()
            total_written = 0
            
            with open(test_file, 'wb') as f:
                while total_written < size_mb * 1024 * 1024:
                    f.write(data)
                    total_written += len(data)
                os.fsync(f.fileno())
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Cleanup
            os.remove(test_file)
            
            speed_mb_s = total_written / (1024 * 1024) / duration if duration > 0 else 0
            return speed_mb_s
            
        except Exception as e:
            logger.error(f"Sequential write test failed: {e}")
            return 0.0
    
    def test_random_read(self, device: str, mount_point: str,
                        size_mb: int = DEFAULT_SIZE_MB,
                        block_size: int = DEFAULT_BLOCK_SIZE) -> float:
        """Test random read speed"""
        logger.info(f"Testing random read on {device} ({size_mb}MB)")
        
        test_file = os.path.join(mount_point, "test_rand_read.dat")
        
        try:
            # Create test file
            with open(test_file, 'wb') as f:
                f.write(os.urandom(size_mb * 1024 * 1024))
            
            # Clear cache
            subprocess.run('echo 3 > /proc/sys/vm/drop_caches', shell=True)
            time.sleep(1)
            
            # Random read test
            block_bytes = block_size * 1024
            num_blocks = (size_mb * 1024 * 1024) // block_bytes
            
            start_time = time.time()
            
            with open(test_file, 'rb') as f:
                # Perform random reads
                for _ in range(min(num_blocks, 1000)):
                    offset = (hash(os.urandom(8)) % num_blocks) * block_bytes
                    f.seek(offset)
                    f.read(block_bytes)
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Cleanup
            os.remove(test_file)
            
            # Calculate IOPS
            iops = min(num_blocks, 1000) / duration if duration > 0 else 0
            speed_mb_s = (iops * block_bytes) / (1024 * 1024)
            return speed_mb_s
            
        except Exception as e:
            logger.error(f"Random read test failed: {e}")
            return 0.0
    
    def test_random_write(self, mount_point: str,
                         size_mb: int = DEFAULT_SIZE_MB,
                         block_size: int = DEFAULT_BLOCK_SIZE) -> float:
        """Test random write speed"""
        logger.info(f"Testing random write on {mount_point} ({size_mb}MB)")
        
        test_file = os.path.join(mount_point, "test_rand_write.dat")
        
        try:
            # Create test file
            with open(test_file, 'wb') as f:
                f.write(os.urandom(size_mb * 1024 * 1024))
            
            # Random write test
            block_bytes = block_size * 1024
            num_blocks = (size_mb * 1024 * 1024) // block_bytes
            data = os.urandom(block_bytes)
            
            start_time = time.time()
            
            with open(test_file, 'r+b') as f:
                for _ in range(min(num_blocks, 1000)):
                    offset = (hash(os.urandom(8)) % num_blocks) * block_bytes
                    f.seek(offset)
                    f.write(data)
                os.fsync(f.fileno())
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Cleanup
            os.remove(test_file)
            
            # Calculate IOPS
            iops = min(num_blocks, 1000) / duration if duration > 0 else 0
            speed_mb_s = (iops * block_bytes) / (1024 * 1024)
            return speed_mb_s
            
        except Exception as e:
            logger.error(f"Random write test failed: {e}")
            return 0.0
    
    def test_iops(self, mount_point: str, size_mb: int = DEFAULT_SIZE_MB,
                  block_size: int = 4096) -> Tuple[float, float]:
        """Test IOPS (read and write)"""
        logger.info(f"Testing IOPS on {mount_point}")
        
        test_file = os.path.join(mount_point, "test_iops.dat")
        
        try:
            block_bytes = block_size
            num_blocks = (size_mb * 1024 * 1024) // block_bytes
            data = os.urandom(block_bytes)
            
            # Write IOPS test
            start_time = time.time()
            
            with open(test_file, 'wb') as f:
                for _ in range(min(num_blocks, 5000)):
                    f.write(data)
                os.fsync(f.fileno())
            
            end_time = time.time()
            write_duration = end_time - start_time
            write_iops = min(num_blocks, 5000) / write_duration if write_duration > 0 else 0
            
            # Clear cache
            subprocess.run('echo 3 > /proc/sys/vm/drop_caches', shell=True)
            time.sleep(1)
            
            # Read IOPS test
            start_time = time.time()
            
            with open(test_file, 'rb') as f:
                for _ in range(min(num_blocks, 5000)):
                    f.read(block_bytes)
            
            end_time = time.time()
            read_duration = end_time - start_time
            read_iops = min(num_blocks, 5000) / read_duration if read_duration > 0 else 0
            
            # Cleanup
            os.remove(test_file)
            
            return read_iops, write_iops
            
        except Exception as e:
            logger.error(f"IOPS test failed: {e}")
            return 0.0, 0.0
    
    def test_latency(self, mount_point: str, samples: int = 100) -> Tuple[float, float]:
        """Test I/O latency"""
        logger.info(f"Testing latency on {mount_point} ({samples} samples)")
        
        test_file = os.path.join(mount_point, "test_latency.dat")
        block_bytes = 512
        data = os.urandom(block_bytes)
        
        read_latencies = []
        write_latencies = []
        
        try:
            with open(test_file, 'wb') as f:
                # Write latency test
                for _ in range(samples):
                    start_time = time.perf_counter()
                    f.write(data)
                    os.fsync(f.fileno())
                    end_time = time.perf_counter()
                    write_latencies.append((end_time - start_time) * 1000)
                
                # Read latency test
                f.seek(0)
                for _ in range(samples):
                    start_time = time.perf_counter()
                    f.read(block_bytes)
                    end_time = time.perf_counter()
                    read_latencies.append((end_time - start_time) * 1000)
            
            # Cleanup
            os.remove(test_file)
            
            avg_read = sum(read_latencies) / len(read_latencies) if read_latencies else 0
            avg_write = sum(write_latencies) / len(write_latencies) if write_latencies else 0
            
            return avg_read, avg_write
            
        except Exception as e:
            logger.error(f"Latency test failed: {e}")
            return 0.0, 0.0
    
    def test_multithreaded(self, mount_point: str, threads: int = DEFAULT_THREADS,
                          size_mb: int = DEFAULT_SIZE_MB) -> float:
        """Test multithreaded performance"""
        logger.info(f"Testing multithreaded performance ({threads} threads)")
        
        per_thread_size = size_mb // threads
        results = []
        
        def thread_test(thread_id):
            test_file = os.path.join(mount_point, f"test_thread_{thread_id}.dat")
            try:
                # Write
                with open(test_file, 'wb') as f:
                    f.write(os.urandom(per_thread_size * 1024 * 1024))
                    os.fsync(f.fileno())
                
                # Read
                with open(test_file, 'rb') as f:
                    while True:
                        data = f.read(1024 * 1024)
                        if not data:
                            break
                
                os.remove(test_file)
                return per_thread_size / 1024  # MB
                
            except Exception as e:
                logger.error(f"Thread {thread_id} failed: {e}")
                return 0.0
        
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = [executor.submit(thread_test, i) for i in range(threads)]
            for future in as_completed(futures):
                results.append(future.result())
        
        end_time = time.time()
        duration = end_time - start_time
        total_mb = sum(results)
        
        speed_mb_s = total_mb / duration if duration > 0 else 0
        return speed_mb_s
    
    def run_benchmark(self, device: str = None, mount_point: str = None,
                      size_mb: int = DEFAULT_SIZE_MB,
                      block_size: int = DEFAULT_BLOCK_SIZE) -> DiskTestResult:
        """Run complete disk benchmark"""
        logger.info(f"Starting disk benchmark (size: {size_mb}MB)")
        
        # Find block device if not specified
        if not device:
            devices = self.find_block_devices()
            if not devices:
                logger.error("No block devices found")
                return None
            
            # Prefer loop devices for virtual testing
            loop_devices = [d for d in devices if 'loop' in d]
            if loop_devices:
                device = loop_devices[0]
            else:
                device = devices[0]
            
            logger.info(f"Using block device: {device}")
        
        # Find mount point if not specified
        if not mount_point:
            mount_point = self.find_mount_point(device)
            if not mount_point:
                # Create temporary mount point
                mount_point = tempfile.mkdtemp(prefix="disk_test_")
                logger.info(f"Created temporary mount point: {mount_point}")
                
                # For loop devices, create file-based test
                if 'loop' in device:
                    test_file = os.path.join(mount_point, "disk_test.img")
                    try:
                        # Create disk image
                        subprocess.run(
                            f"dd if=/dev/zero of={test_file} bs=1M count={size_mb} 2>/dev/null",
                            shell=True, check=True
                        )
                        # Setup loop device
                        subprocess.run(
                            f"losetup {device} {test_file} 2>/dev/null",
                            shell=True, check=True
                        )
                        # Format and mount
                        subprocess.run(f"mkfs.ext4 -F {device} 2>/dev/null", shell=True, check=True)
                        subprocess.run(f"mount {device} {mount_point}", shell=True, check=True)
                    except Exception as e:
                        logger.error(f"Failed to setup loop device: {e}")
                        return None
        
        # Run tests
        stats = DiskStats()
        stats.block_size = block_size
        
        # Sequential tests
        logger.info("Testing sequential read...")
        stats.read_speed_mb_s = self.test_sequential_read(device, mount_point, size_mb, block_size)
        
        logger.info("Testing sequential write...")
        stats.write_speed_mb_s = self.test_sequential_write(mount_point, size_mb, block_size)
        
        # Random tests
        logger.info("Testing random read...")
        stats.rand_read_speed_mb_s = self.test_random_read(device, mount_point, size_mb, block_size)
        
        logger.info("Testing random write...")
        stats.rand_write_speed_mb_s = self.test_random_write(mount_point, size_mb, block_size)
        
        # IOPS
        logger.info("Testing IOPS...")
        stats.read_iops, stats.write_iops = self.test_iops(mount_point, size_mb, block_size)
        
        # Latency
        logger.info("Testing latency...")
        stats.read_latency_ms, stats.write_latency_ms = self.test_latency(mount_point)
        
        # Multithreaded
        logger.info("Testing multithreaded...")
        stats.total_bytes = self.test_multithreaded(mount_point, DEFAULT_THREADS, size_mb)
        
        # Create result
        result = DiskTestResult(
            device=device,
            mount_point=mount_point,
            stats=stats,
            details={
                'size_mb': size_mb,
                'block_size': block_size,
                'threads': DEFAULT_THREADS
            }
        )
        
        self.results.append(result)
        return result

class DiskAnalyzer:
    """Disk benchmark analyzer"""
    
    @staticmethod
    def analyze_results(results: List[DiskTestResult]) -> Dict:
        """Analyze benchmark results"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'devices': [],
            'summary': {
                'best_read': 0.0,
                'best_write': 0.0,
                'best_iops': 0.0
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
                'read_mb_s': stats.read_speed_mb_s,
                'write_mb_s': stats.write_speed_mb_s,
                'rand_read_mb_s': stats.rand_read_speed_mb_s,
                'rand_write_mb_s': stats.rand_write_speed_mb_s,
                'read_iops': stats.read_iops,
                'write_iops': stats.write_iops,
                'read_latency_ms': stats.read_latency_ms,
                'write_latency_ms': stats.write_latency_ms
            }
            report['devices'].append(device_info)
            
            # Update summary
            if stats.read_speed_mb_s > report['summary']['best_read']:
                report['summary']['best_read'] = stats.read_speed_mb_s
            if stats.write_speed_mb_s > report['summary']['best_write']:
                report['summary']['best_write'] = stats.write_speed_mb_s
            if stats.read_iops > report['summary']['best_iops']:
                report['summary']['best_iops'] = stats.read_iops
            
            # Generate recommendations
            if stats.read_speed_mb_s < 50:
                report['recommendations'].append(
                    f"Device {result.device} has low read speed ({stats.read_speed_mb_s:.2f} MB/s). "
                    "Consider using SSD or faster storage."
                )
            
            if stats.write_speed_mb_s < 30:
                report['recommendations'].append(
                    f"Device {result.device} has low write speed ({stats.write_speed_mb_s:.2f} MB/s). "
                    "May impact virtual disk performance."
                )
            
            if stats.read_latency_ms > 5:
                report['recommendations'].append(
                    f"High read latency ({stats.read_latency_ms:.2f} ms) on {result.device}. "
                    "Consider using faster storage for latency-sensitive workloads."
                )
        
        return report

class DiskTestCLI:
    """Command line interface for disk benchmarks"""
    
    def __init__(self):
        self.tester = DiskPerformanceTester()
        self.analyzer = DiskAnalyzer()
        
    def run(self, args):
        """Run disk benchmark"""
        print(f"\n{COLORS['CYAN']}========================================")
        print(f"Disk Performance Benchmark")
        print(f"========================================{COLORS['RESET']}")
        print()
        
        # List devices
        if args.list:
            devices = self.tester.find_block_devices()
            print(f"{COLORS['YELLOW']}Block Devices:{COLORS['RESET']}")
            for dev in devices:
                mount = self.tester.find_mount_point(dev)
                size = subprocess.run(
                    f"blockdev --getsize64 {dev} 2>/dev/null",
                    shell=True, capture_output=True, text=True
                ).stdout.strip()
                if size:
                    size_gb = int(size) / (1024**3)
                    print(f"  {dev} -> {size_gb:.2f} GB -> {mount or 'not mounted'}")
                else:
                    print(f"  {dev} -> {mount or 'not mounted'}")
            return
        
        # Run benchmark
        results = []
        
        if args.device:
            result = self.tester.run_benchmark(
                device=args.device,
                size_mb=args.size,
                block_size=args.blocksize
            )
            if result:
                results.append(result)
        else:
            # Auto-detect and run on loop devices first
            devices = self.tester.find_block_devices()
            loop_devices = [d for d in devices if 'loop' in d]
            
            if loop_devices:
                for dev in loop_devices[:2]:  # Test first 2 loop devices
                    result = self.tester.run_benchmark(
                        device=dev,
                        size_mb=args.size,
                        block_size=args.blocksize
                    )
                    if result:
                        results.append(result)
        
        if not results:
            # Create temporary loop device
            mount_point = tempfile.mkdtemp(prefix="disk_test_")
            test_file = os.path.join(mount_point, "test.img")
            try:
                subprocess.run(f"dd if=/dev/zero of={test_file} bs=1M count={args.size} 2>/dev/null",
                             shell=True, check=True)
                loop_dev = subprocess.run(
                    f"losetup -f --show {test_file}",
                    shell=True, capture_output=True, text=True
                ).stdout.strip()
                if loop_dev:
                    result = self.tester.run_benchmark(
                        device=loop_dev,
                        mount_point=mount_point,
                        size_mb=args.size,
                        block_size=args.blocksize
                    )
                    if result:
                        results.append(result)
                    # Cleanup loop device later
            except Exception as e:
                logger.error(f"Failed to create loop device: {e}")
        
        # Display results
        self._display_results(results)
        
        # Analyze
        report = self.analyzer.analyze_results(results)
        
        # Save results
        if args.output:
            self._save_results(results, report, args.output)
        
        return results
    
    def _display_results(self, results: List[DiskTestResult]):
        """Display benchmark results"""
        print(f"\n{COLORS['CYAN']}=== Benchmark Results ==={COLORS['RESET']}")
        print()
        
        for result in results:
            if not result:
                continue
                
            stats = result.stats
            
            print(f"{COLORS['YELLOW']}Device: {result.device}{COLORS['RESET']}")
            print(f"  Mount Point: {result.mount_point}")
            print(f"  Sequential Read: {stats.read_speed_mb_s:.2f} MB/s")
            print(f"  Sequential Write: {stats.write_speed_mb_s:.2f} MB/s")
            print(f"  Random Read: {stats.rand_read_speed_mb_s:.2f} MB/s")
            print(f"  Random Write: {stats.rand_write_speed_mb_s:.2f} MB/s")
            print(f"  Read IOPS: {stats.read_iops:.2f}")
            print(f"  Write IOPS: {stats.write_iops:.2f}")
            print(f"  Read Latency: {stats.read_latency_ms:.2f} ms")
            print(f"  Write Latency: {stats.write_latency_ms:.2f} ms")
            print(f"  Multithreaded: {stats.total_bytes:.2f} MB/s")
            print()
    
    def _save_results(self, results: List[DiskTestResult], report: Dict, filename: str):
        """Save results to file"""
        try:
            data = {
                'results': [
                    {
                        'device': r.device,
                        'mount_point': r.mount_point,
                        'stats': {
                            'read_mb_s': r.stats.read_speed_mb_s,
                            'write_mb_s': r.stats.write_speed_mb_s,
                            'rand_read_mb_s': r.stats.rand_read_speed_mb_s,
                            'rand_write_mb_s': r.stats.rand_write_speed_mb_s,
                            'read_iops': r.stats.read_iops,
                            'write_iops': r.stats.write_iops,
                            'read_latency_ms': r.stats.read_latency_ms,
                            'write_latency_ms': r.stats.write_latency_ms
                        },
                        'details': r.details
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
        description="Disk Performance Benchmark",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Benchmark all loop devices
  %(prog)s
  
  # Benchmark specific device
  %(prog)s -d /dev/loop0
  
  # Benchmark with custom size and block size
  %(prog)s -s 200 -b 8192
  
  # List block devices
  %(prog)s --list
  
  # Save results
  %(prog)s -o results.json
        """
    )
    
    parser.add_argument('-d', '--device',
                       help='Block device to test (e.g., /dev/loop0)')
    parser.add_argument('-s', '--size',
                       type=int, default=DEFAULT_SIZE_MB,
                       help=f'Test size in MB (default: {DEFAULT_SIZE_MB})')
    parser.add_argument('-b', '--blocksize',
                       type=int, default=DEFAULT_BLOCK_SIZE,
                       help=f'Block size in bytes (default: {DEFAULT_BLOCK_SIZE})')
    parser.add_argument('-o', '--output',
                       help='Output file for results')
    parser.add_argument('--list',
                       action='store_true',
                       help='List block devices')
    parser.add_argument('--all-block-sizes',
                       action='store_true',
                       help='Test all block sizes')
    parser.add_argument('-v', '--verbose',
                       action='store_true',
                       help='Enable verbose output')
    
    return parser.parse_args()

def main():
    """Main entry point"""
    args = parse_arguments()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    cli = DiskTestCLI()
    try:
        results = cli.run(args)
        print(f"\n{COLORS['GREEN']}✓ Disk benchmark completed{COLORS['RESET']}")
    except KeyboardInterrupt:
        print(f"\n{COLORS['YELLOW']}Benchmark interrupted by user{COLORS['RESET']}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Benchmark failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
