#!/usr/bin/env python3
"""
nbd-example.py - Network Block Device (NBD) Example

This script demonstrates NBD server and client functionality for
exporting block devices over the network on Intel NUC platforms.
"""

import os
import sys
import time
import json
import socket
import struct
import logging
import threading
import argparse
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

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

# NBD Protocol Constants
NBD_REQUEST_MAGIC = 0x25609513
NBD_REPLY_MAGIC = 0x67446698
NBD_CMD_READ = 0
NBD_CMD_WRITE = 1
NBD_CMD_DISC = 2
NBD_CMD_FLUSH = 3
NBD_CMD_TRIM = 4
NBD_CMD_CACHE = 5
NBD_CMD_WRITE_ZEROES = 6

NBD_FLAG_HAS_FLAGS = 1 << 0
NBD_FLAG_READ_ONLY = 1 << 1
NBD_FLAG_SEND_FLUSH = 1 << 2
NBD_FLAG_SEND_FUA = 1 << 3
NBD_FLAG_ROTATIONAL = 1 << 4
NBD_FLAG_SEND_TRIM = 1 << 5
NBD_FLAG_SEND_WRITE_ZEROES = 1 << 6

# ==================== Data Classes ====================

@dataclass
class NBDRequest:
    """NBD request structure"""
    magic: int
    type: int
    handle: int
    from_offset: int
    length: int
    
    @classmethod
    def from_bytes(cls, data: bytes) -> 'NBDRequest':
        """Parse NBD request from bytes"""
        magic, type_, handle, from_offset, length = struct.unpack(
            '>IIQHQ', data[:16]
        )
        return cls(magic, type_, handle, from_offset, length)

@dataclass
class NBDReply:
    """NBD reply structure"""
    magic: int
    error: int
    handle: int
    
    def to_bytes(self) -> bytes:
        """Convert reply to bytes"""
        return struct.pack('>IIQ', self.magic, self.error, self.handle)

@dataclass
class NBDDevice:
    """NBD device information"""
    path: str
    size: int
    readonly: bool
    block_size: int = 512
    flags: int = 0

# ==================== NBD Server ====================

class NBDServer:
    """NBD server implementation"""
    
    def __init__(self, device: NBDDevice, port: int = 10809):
        self.device = device
        self.port = port
        self.socket = None
        self.running = False
        self.threads = []
        self.lock = threading.Lock()
        
        # Open device
        self.fd = None
        self._open_device()
    
    def _open_device(self):
        """Open block device"""
        try:
            if self.device.path.startswith('/dev/'):
                self.fd = os.open(self.device.path, os.O_RDWR)
            else:
                # File-based device
                self.fd = os.open(self.device.path, os.O_RDWR | os.O_CREAT)
                # Set size if needed
                current_size = os.path.getsize(self.device.path)
                if current_size < self.device.size:
                    os.truncate(self.device.path, self.device.size)
        except Exception as e:
            logger.error(f"Failed to open device {self.device.path}: {e}")
            raise
    
    def start(self):
        """Start NBD server"""
        if self.running:
            return
        
        self.running = True
        
        # Create socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(('0.0.0.0', self.port))
        self.socket.listen(5)
        
        logger.info(f"NBD server started on port {self.port}")
        logger.info(f"Exporting device: {self.device.path}")
        logger.info(f"Device size: {self.device.size} bytes")
        
        # Accept connections in a separate thread
        self.accept_thread = threading.Thread(target=self._accept_loop)
        self.accept_thread.daemon = True
        self.accept_thread.start()
        
        logger.info("NBD server running. Press Ctrl+C to stop.")
    
    def stop(self):
        """Stop NBD server"""
        self.running = False
        
        if self.socket:
            self.socket.close()
        
        for thread in self.threads:
            thread.join(timeout=2)
        
        if self.fd:
            os.close(self.fd)
            self.fd = None
        
        logger.info("NBD server stopped")
    
    def _accept_loop(self):
        """Accept client connections"""
        while self.running:
            try:
                client, addr = self.socket.accept()
                logger.info(f"Client connected from {addr}")
                
                # Create handler thread
                thread = threading.Thread(
                    target=self._handle_client,
                    args=(client, addr)
                )
                thread.daemon = True
                thread.start()
                self.threads.append(thread)
                
            except Exception as e:
                if self.running:
                    logger.error(f"Accept error: {e}")
                break
    
    def _handle_client(self, client: socket.socket, addr: Tuple):
        """Handle client connection"""
        try:
            # Send handshake
            handshake = self._create_handshake()
            client.sendall(handshake)
            logger.info(f"Handshake sent to {addr}")
            
            # Handle requests
            while self.running:
                try:
                    # Read request header
                    header = client.recv(16)
                    if not header or len(header) < 16:
                        break
                    
                    request = NBDRequest.from_bytes(header)
                    
                    # Validate magic
                    if request.magic != NBD_REQUEST_MAGIC:
                        logger.error(f"Invalid magic: {request.magic:#x}")
                        break
                    
                    # Handle request
                    self._handle_request(client, request)
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"Request handling error: {e}")
                    break
            
        except Exception as e:
            logger.error(f"Client handler error: {e}")
        finally:
            client.close()
            logger.info(f"Client {addr} disconnected")
    
    def _create_handshake(self) -> bytes:
        """Create NBD handshake"""
        # Client flags
        flags = 0
        
        # Server flags
        server_flags = NBD_FLAG_HAS_FLAGS
        
        if self.device.readonly:
            server_flags |= NBD_FLAG_READ_ONLY
        
        # Build handshake
        handshake = struct.pack(
            '>QIII',
            0x4e42444d41474943,  # "NBDMAGIC"
            0x49484156454F5054,  # "IHAVEOPT"
            self.device.flags,
            server_flags
        )
        
        return handshake
    
    def _handle_request(self, client: socket.socket, request: NBDRequest):
        """Handle NBD request"""
        with self.lock:
            try:
                if request.type == NBD_CMD_READ:
                    # Read data
                    data = self._read_data(request.from_offset, request.length)
                    reply = NBDReply(NBD_REPLY_MAGIC, 0, request.handle)
                    client.sendall(reply.to_bytes() + data)
                    
                elif request.type == NBD_CMD_WRITE:
                    # Read data from client
                    data = client.recv(request.length)
                    self._write_data(request.from_offset, data)
                    reply = NBDReply(NBD_REPLY_MAGIC, 0, request.handle)
                    client.sendall(reply.to_bytes())
                    
                elif request.type == NBD_CMD_FLUSH:
                    # Flush data
                    os.fsync(self.fd)
                    reply = NBDReply(NBD_REPLY_MAGIC, 0, request.handle)
                    client.sendall(reply.to_bytes())
                    
                elif request.type == NBD_CMD_TRIM:
                    # Discard blocks
                    # Just seek and write zeros for now
                    reply = NBDReply(NBD_REPLY_MAGIC, 0, request.handle)
                    client.sendall(reply.to_bytes())
                    
                elif request.type == NBD_CMD_DISC:
                    # Disconnect
                    logger.info("Client requested disconnect")
                    client.close()
                    return
                    
                else:
                    # Unknown command
                    logger.warning(f"Unknown command: {request.type}")
                    reply = NBDReply(NBD_REPLY_MAGIC, 1, request.handle)
                    client.sendall(reply.to_bytes())
                    
            except Exception as e:
                logger.error(f"Request handling error: {e}")
                # Send error reply
                reply = NBDReply(NBD_REPLY_MAGIC, 1, request.handle)
                client.sendall(reply.to_bytes())
    
    def _read_data(self, offset: int, length: int) -> bytes:
        """Read data from device"""
        os.lseek(self.fd, offset, os.SEEK_SET)
        return os.read(self.fd, length)
    
    def _write_data(self, offset: int, data: bytes):
        """Write data to device"""
        os.lseek(self.fd, offset, os.SEEK_SET)
        os.write(self.fd, data)

# ==================== NBD Client ====================

class NBDClient:
    """NBD client implementation"""
    
    def __init__(self, host: str = 'localhost', port: int = 10809):
        self.host = host
        self.port = port
        self.socket = None
        self.connected = False
        self.handle_counter = 0
        self.lock = threading.Lock()
    
    def connect(self) -> bool:
        """Connect to NBD server"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.connected = True
            
            # Receive handshake
            handshake = self.socket.recv(16)
            if len(handshake) != 16:
                raise Exception("Invalid handshake")
            
            logger.info(f"Connected to NBD server at {self.host}:{self.port}")
            return True
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from NBD server"""
        if self.connected:
            # Send disconnect command
            request = self._create_request(NBD_CMD_DISC, 0, 0)
            self.socket.sendall(request)
            self.socket.close()
            self.connected = False
            logger.info("Disconnected from NBD server")
    
    def read(self, offset: int, length: int) -> Optional[bytes]:
        """Read data from NBD device"""
        if not self.connected:
            return None
        
        with self.lock:
            handle = self._get_handle()
            request = self._create_request(NBD_CMD_READ, offset, length, handle)
            
            try:
                # Send request
                self.socket.sendall(request)
                
                # Receive reply
                reply_header = self.socket.recv(16)
                if len(reply_header) != 16:
                    return None
                
                magic, error, recv_handle = struct.unpack('>IIQ', reply_header)
                
                if magic != NBD_REPLY_MAGIC:
                    logger.error(f"Invalid reply magic: {magic:#x}")
                    return None
                
                if error != 0:
                    logger.error(f"Read error: {error}")
                    return None
                
                # Read data
                data = self.socket.recv(length)
                return data
                
            except Exception as e:
                logger.error(f"Read error: {e}")
                return None
    
    def write(self, offset: int, data: bytes) -> bool:
        """Write data to NBD device"""
        if not self.connected:
            return False
        
        with self.lock:
            handle = self._get_handle()
            request = self._create_request(NBD_CMD_WRITE, offset, len(data), handle)
            
            try:
                # Send request
                self.socket.sendall(request)
                
                # Send data
                self.socket.sendall(data)
                
                # Receive reply
                reply_header = self.socket.recv(16)
                if len(reply_header) != 16:
                    return False
                
                magic, error, recv_handle = struct.unpack('>IIQ', reply_header)
                
                if magic != NBD_REPLY_MAGIC:
                    logger.error(f"Invalid reply magic: {magic:#x}")
                    return False
                
                if error != 0:
                    logger.error(f"Write error: {error}")
                    return False
                
                return True
                
            except Exception as e:
                logger.error(f"Write error: {e}")
                return False
    
    def flush(self) -> bool:
        """Flush data"""
        if not self.connected:
            return False
        
        with self.lock:
            handle = self._get_handle()
            request = self._create_request(NBD_CMD_FLUSH, 0, 0, handle)
            
            try:
                self.socket.sendall(request)
                
                reply_header = self.socket.recv(16)
                if len(reply_header) != 16:
                    return False
                
                magic, error, recv_handle = struct.unpack('>IIQ', reply_header)
                
                if magic != NBD_REPLY_MAGIC:
                    return False
                
                return error == 0
                
            except Exception as e:
                logger.error(f"Flush error: {e}")
                return False
    
    def trim(self, offset: int, length: int) -> bool:
        """Trim/discard blocks"""
        if not self.connected:
            return False
        
        with self.lock:
            handle = self._get_handle()
            request = self._create_request(NBD_CMD_TRIM, offset, length, handle)
            
            try:
                self.socket.sendall(request)
                
                reply_header = self.socket.recv(16)
                if len(reply_header) != 16:
                    return False
                
                magic, error, recv_handle = struct.unpack('>IIQ', reply_header)
                
                if magic != NBD_REPLY_MAGIC:
                    return False
                
                return error == 0
                
            except Exception as e:
                logger.error(f"Trim error: {e}")
                return False
    
    def _get_handle(self) -> int:
        """Get next request handle"""
        self.handle_counter += 1
        return self.handle_counter
    
    def _create_request(self, cmd: int, offset: int, length: int, 
                        handle: int = None) -> bytes:
        """Create NBD request"""
        if handle is None:
            handle = self._get_handle()
        
        return struct.pack(
            '>IIQHQ',
            NBD_REQUEST_MAGIC,
            cmd,
            handle,
            offset,
            length
        )

# ==================== NBD Utilities ====================

class NBDUtils:
    """NBD utility functions"""
    
    @staticmethod
    def create_disk_image(path: str, size_mb: int) -> bool:
        """Create disk image file"""
        try:
            with open(path, 'wb') as f:
                f.seek(size_mb * 1024 * 1024 - 1)
                f.write(b'\0')
            return True
        except Exception as e:
            logger.error(f"Failed to create image: {e}")
            return False
    
    @staticmethod
    def format_device(path: str, fs_type: str = 'ext4') -> bool:
        """Format block device"""
        try:
            subprocess.run(
                f"mkfs.{fs_type} {path} -F",
                shell=True,
                check=True,
                capture_output=True
            )
            return True
        except Exception as e:
            logger.error(f"Format failed: {e}")
            return False
    
    @staticmethod
    def mount_device(device: str, mount_point: str) -> bool:
        """Mount block device"""
        try:
            os.makedirs(mount_point, exist_ok=True)
            subprocess.run(
                f"mount {device} {mount_point}",
                shell=True,
                check=True
            )
            return True
        except Exception as e:
            logger.error(f"Mount failed: {e}")
            return False
    
    @staticmethod
    def umount_device(mount_point: str) -> bool:
        """Unmount block device"""
        try:
            subprocess.run(
                f"umount {mount_point}",
                shell=True,
                check=True
            )
            return True
        except Exception as e:
            logger.error(f"Unmount failed: {e}")
            return False
    
    @staticmethod
    def load_nbd_module():
        """Load NBD kernel module"""
        try:
            subprocess.run("modprobe nbd", shell=True, check=True)
            logger.info("NBD kernel module loaded")
            return True
        except Exception as e:
            logger.error(f"Failed to load NBD module: {e}")
            return False

# ==================== NBD Example Applications ====================

class NBDExample:
    """NBD example applications"""
    
    @staticmethod
    def export_file_example():
        """Example: Export a file as NBD device"""
        logger.info("=== NBD File Export Example ===")
        
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = tmp.name
            logger.info(f"Creating temporary file: {tmp_path}")
            
            # Fill with zeros
            os.truncate(tmp_path, 10 * 1024 * 1024)  # 10MB
            logger.info("File created: 10MB")
            
            # Create NBD device
            device = NBDDevice(
                path=tmp_path,
                size=10 * 1024 * 1024,
                readonly=False
            )
            
            # Start NBD server
            server = NBDServer(device, port=10809)
            
            try:
                server.start()
                logger.info("NBD server running. Press Ctrl+C to stop.")
                time.sleep(60)  # Run for 60 seconds
            except KeyboardInterrupt:
                pass
            finally:
                server.stop()
                os.unlink(tmp_path)
                logger.info("Cleanup complete")
    
    @staticmethod
    def export_block_device_example():
        """Example: Export a block device"""
        logger.info("=== NBD Block Device Export Example ===")
        
        # Check if block device exists
        device_path = "/dev/sdb"
        if not os.path.exists(device_path):
            logger.error(f"Block device not found: {device_path}")
            return
        
        # Create NBD device
        device = NBDDevice(
            path=device_path,
            size=os.path.getsize(device_path),
            readonly=False
        )
        
        # Start NBD server
        server = NBDServer(device, port=10809)
        
        try:
            server.start()
            logger.info("NBD server running. Press Ctrl+C to stop.")
            time.sleep(60)
        except KeyboardInterrupt:
            pass
        finally:
            server.stop()
    
    @staticmethod
    def client_example():
        """Example: NBD client operations"""
        logger.info("=== NBD Client Example ===")
        
        # Connect to server
        client = NBDClient('localhost', 10809)
        if not client.connect():
            logger.error("Failed to connect")
            return
        
        try:
            # Read some data
            logger.info("Reading 4096 bytes from offset 0...")
            data = client.read(0, 4096)
            if data:
                logger.info(f"Read {len(data)} bytes")
                logger.info(f"First 64 bytes: {data[:64].hex()}")
            
            # Write some data
            logger.info("Writing test data at offset 4096...")
            test_data = b"Hello from NBD client!" * 100
            if client.write(4096, test_data):
                logger.info("Write successful")
            
            # Flush
            if client.flush():
                logger.info("Flush successful")
            
        finally:
            client.disconnect()
    
    @staticmethod
    def performance_test():
        """Performance testing"""
        logger.info("=== NBD Performance Test ===")
        
        # Create test file
        test_file = "/tmp/nbd_test.img"
        NBDUtils.create_disk_image(test_file, 100)  # 100MB
        
        # Start server
        device = NBDDevice(
            path=test_file,
            size=100 * 1024 * 1024,
            readonly=False
        )
        server = NBDServer(device, port=10809)
        
        # Start server in background
        import threading
        server_thread = threading.Thread(target=server.start)
        server_thread.daemon = True
        server_thread.start()
        
        time.sleep(1)  # Wait for server to start
        
        # Connect client
        client = NBDClient('localhost', 10809)
        if not client.connect():
            logger.error("Failed to connect")
            return
        
        try:
            # Test read performance
            logger.info("\nTesting read performance...")
            start = time.time()
            total_read = 0
            
            for i in range(100):
                data = client.read(i * 4096, 4096)
                if data:
                    total_read += len(data)
            
            elapsed = time.time() - start
            read_speed = total_read / elapsed / (1024 * 1024)
            logger.info(f"Read {total_read} bytes in {elapsed:.2f}s")
            logger.info(f"Read speed: {read_speed:.2f} MB/s")
            
            # Test write performance
            logger.info("\nTesting write performance...")
            start = time.time()
            total_written = 0
            test_data = b"A" * 4096
            
            for i in range(100):
                if client.write(i * 4096, test_data):
                    total_written += len(test_data)
            
            elapsed = time.time() - start
            write_speed = total_written / elapsed / (1024 * 1024)
            logger.info(f"Written {total_written} bytes in {elapsed:.2f}s")
            logger.info(f"Write speed: {write_speed:.2f} MB/s")
            
        finally:
            client.disconnect()
            server.stop()
            os.unlink(test_file)
            logger.info("Cleanup complete")

# ==================== Command Line Interface ====================

def create_parser():
    """Create argument parser"""
    parser = argparse.ArgumentParser(
        description="NBD (Network Block Device) Example",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Export a file as NBD device
  %(prog)s export-file
  
  # Export a block device
  %(prog)s export-device /dev/sdb
  
  # Run NBD client
  %(prog)s client localhost 10809
  
  # Performance test
  %(prog)s perf
  
  # Create disk image
  %(prog)s create-image /tmp/disk.img 100
  
  # Mount NBD device
  %(prog)s mount localhost 10809 /dev/nbd0 /mnt
        """
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command')
    
    # Export file
    export_file = subparsers.add_parser('export-file', help='Export file as NBD')
    export_file.add_argument(
        '--file', '-f',
        default='/tmp/nbd.img',
        help='File to export (default: /tmp/nbd.img)'
    )
    export_file.add_argument(
        '--size', '-s',
        type=int,
        default=100,
        help='File size in MB (default: 100)'
    )
    export_file.add_argument(
        '--port', '-p',
        type=int,
        default=10809,
        help='Server port (default: 10809)'
    )
    export_file.add_argument(
        '--readonly', '-r',
        action='store_true',
        help='Export as read-only'
    )
    
    # Export device
    export_dev = subparsers.add_parser('export-device', help='Export block device')
    export_dev.add_argument(
        'device',
        help='Block device path (e.g., /dev/sdb)'
    )
    export_dev.add_argument(
        '--port', '-p',
        type=int,
        default=10809,
        help='Server port (default: 10809)'
    )
    
    # Client
    client = subparsers.add_parser('client', help='Run NBD client')
    client.add_argument(
        'host',
        default='localhost',
        nargs='?',
        help='Server host (default: localhost)'
    )
    client.add_argument(
        'port',
        type=int,
        default=10809,
        nargs='?',
        help='Server port (default: 10809)'
    )
    client.add_argument(
        '--read', '-r',
        type=int,
        default=0,
        help='Read offset'
    )
    client.add_argument(
        '--length', '-l',
        type=int,
        default=4096,
        help='Read/write length'
    )
    client.add_argument(
        '--write', '-w',
        help='Write data (string)'
    )
    
    # Performance
    perf = subparsers.add_parser('perf', help='Performance test')
    perf.add_argument(
        '--size', '-s',
        type=int,
        default=100,
        help='Test file size in MB (default: 100)'
    )
    perf.add_argument(
        '--iterations', '-i',
        type=int,
        default=100,
        help='Number of iterations (default: 100)'
    )
    
    # Create image
    create_img = subparsers.add_parser('create-image', help='Create disk image')
    create_img.add_argument(
        'path',
        help='Image file path'
    )
    create_img.add_argument(
        'size',
        type=int,
        help='Size in MB'
    )
    create_img.add_argument(
        '--format', '-f',
        default='ext4',
        help='Filesystem type (default: ext4)'
    )
    
    # Mount
    mount = subparsers.add_parser('mount', help='Mount NBD device')
    mount.add_argument(
        'host',
        help='Server host'
    )
    mount.add_argument(
        'port',
        type=int,
        help='Server port'
    )
    mount.add_argument(
        'device',
        help='NBD device (e.g., /dev/nbd0)'
    )
    mount.add_argument(
        'mountpoint',
        help='Mount point'
    )
    
    return parser

def main():
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Load NBD module
    NBDUtils.load_nbd_module()
    
    # Execute command
    if args.command == 'export-file':
        # Create file if it doesn't exist
        if not os.path.exists(args.file):
            logger.info(f"Creating file: {args.file}")
            NBDUtils.create_disk_image(args.file, args.size)
        
        device = NBDDevice(
            path=args.file,
            size=args.size * 1024 * 1024,
            readonly=args.readonly
        )
        server = NBDServer(device, port=args.port)
        
        try:
            server.start()
            logger.info("Press Ctrl+C to stop")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            server.stop()
    
    elif args.command == 'export-device':
        if not os.path.exists(args.device):
            logger.error(f"Device not found: {args.device}")
            return
        
        size = os.path.getsize(args.device)
        device = NBDDevice(
            path=args.device,
            size=size,
            readonly=False
        )
        server = NBDServer(device, port=args.port)
        
        try:
            server.start()
            logger.info("Press Ctrl+C to stop")
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            server.stop()
    
    elif args.command == 'client':
        client = NBDClient(args.host, args.port)
        if not client.connect():
            return
        
        try:
            if args.write:
                data = args.write.encode()
                offset = args.read or 0
                if client.write(offset, data):
                    logger.info(f"Written {len(data)} bytes at offset {offset}")
                else:
                    logger.error("Write failed")
            else:
                offset = args.read or 0
                length = args.length
                data = client.read(offset, length)
                if data:
                    logger.info(f"Read {len(data)} bytes from offset {offset}")
                    logger.info(f"Data: {data[:64]}")
                else:
                    logger.error("Read failed")
                    
        finally:
            client.disconnect()
    
    elif args.command == 'perf':
        example = NBDExample()
        example.performance_test()
    
    elif args.command == 'create-image':
        if NBDUtils.create_disk_image(args.path, args.size):
            logger.info(f"Image created: {args.path}")
            if args.format:
                if NBDUtils.format_device(args.path, args.format):
                    logger.info(f"Image formatted as {args.format}")
        else:
            logger.error("Image creation failed")
    
    elif args.command == 'mount':
        # Load NBD device
        logger.info(f"Loading NBD device: {args.device}")
        subprocess.run(
            f"nbd-client {args.host} {args.port} {args.device}",
            shell=True,
            check=True
        )
        
        # Mount
        if NBDUtils.mount_device(args.device, args.mountpoint):
            logger.info(f"Mounted {args.device} at {args.mountpoint}")
        else:
            logger.error("Mount failed")
    
    else:
        parser.print_help()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n")
        logger.info("Shutdown requested")
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
