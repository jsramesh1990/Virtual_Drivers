#!/usr/bin/env python3
"""
camera-simulation.py - Virtual Camera Simulation with Frame Generator

This script provides a complete camera simulation framework for testing
virtual cameras on Intel NUC platforms.
"""

import os
import sys
import time
import json
import logging
import argparse
import threading
import queue
import signal
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

import numpy as np
try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("OpenCV not installed. Install with: pip install opencv-python")

try:
    import v4l2
    V4L2_AVAILABLE = True
except ImportError:
    V4L2_AVAILABLE = False
    print("V4L2 Python bindings not available. Using fallback.")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
COLORS = {
    'RESET': '\033[0m',
    'RED': '\033[31m',
    'GREEN': '\033[32m',
    'YELLOW': '\033[33m',
    'BLUE': '\033[34m',
    'MAGENTA': '\033[35m',
    'CYAN': '\033[36m'
}

# ==================== Data Classes ====================

class PatternType(Enum):
    """Test pattern types"""
    COLOR_BARS = 0
    SMPTE_BARS = 1
    CHECKERBOARD = 2
    GRADIENT = 3
    MOVING_BAR = 4
    NOISE = 5
    COLOR_WHEEL = 6
    TEXT = 7
    CLOCK = 8
    MOVIE = 9

class PixelFormat(Enum):
    """Pixel formats"""
    YUYV = 0
    UYVY = 1
    RGB24 = 2
    RGB32 = 3
    GREY = 4
    YUV420 = 5
    YVU420 = 6

@dataclass
class FrameConfig:
    """Frame configuration"""
    width: int = 1920
    height: int = 1080
    fps: int = 30
    format: PixelFormat = PixelFormat.YUYV
    pattern: PatternType = PatternType.COLOR_BARS
    brightness: int = 128
    contrast: int = 128
    saturation: int = 128
    hue: int = 0
    text: str = ""
    param1: int = 16
    param2: int = 0
    param3: int = 0

@dataclass
class FrameStats:
    """Frame statistics"""
    count: int = 0
    timestamp: float = 0.0
    fps: float = 0.0
    bytes: int = 0
    elapsed: float = 0.0
    dropped: int = 0

# ==================== Frame Generator ====================

class FrameGenerator:
    """Virtual frame generator"""
    
    def __init__(self, config: FrameConfig):
        self.config = config
        self.stats = FrameStats()
        self.running = False
        self.lock = threading.Lock()
        self.frame_queue = queue.Queue(maxsize=10)
        self.callbacks = []
        self.last_frame_time = 0
        
        # Pre-allocate frame buffer
        self.frame_size = self._calculate_frame_size()
        self.frame_buffer = np.zeros(self.frame_size, dtype=np.uint8)
        
        # Motion tracking
        self.motion_x = 0
        self.motion_y = 0
        self.motion_dx = 1
        self.motion_dy = 1
        
        logger.info(f"Frame generator initialized: {config.width}x{config.height} @ {config.fps}fps")
        logger.info(f"Frame size: {self.frame_size} bytes")
    
    def _calculate_frame_size(self) -> int:
        """Calculate frame size based on format"""
        w, h = self.config.width, self.config.height
        
        if self.config.format == PixelFormat.RGB24:
            return w * h * 3
        elif self.config.format == PixelFormat.RGB32:
            return w * h * 4
        elif self.config.format in (PixelFormat.YUYV, PixelFormat.UYVY):
            return w * h * 2
        elif self.config.format == PixelFormat.GREY:
            return w * h
        elif self.config.format in (PixelFormat.YUV420, PixelFormat.YVU420):
            return w * h * 3 // 2
        else:
            return w * h * 2
    
    def generate_color_bars(self) -> np.ndarray:
        """Generate color bars pattern"""
        w, h = self.config.width, self.config.height
        bars = 8
        bar_width = w // bars
        
        # Define colors
        colors = [
            (255, 255, 255),  # White
            (255, 255, 0),    # Yellow
            (0, 255, 255),    # Cyan
            (0, 255, 0),      # Green
            (255, 0, 255),    # Magenta
            (255, 0, 0),      # Red
            (0, 0, 255),      # Blue
            (0, 0, 0)         # Black
        ]
        
        # Create image
        img = np.zeros((h, w, 3), dtype=np.uint8)
        
        for i, color in enumerate(colors):
            x1 = i * bar_width
            x2 = (i + 1) * bar_width if i < bars - 1 else w
            img[:, x1:x2] = color
        
        return img
    
    def generate_smpte_bars(self) -> np.ndarray:
        """Generate SMPTE color bars"""
        w, h = self.config.width, self.config.height
        bar_width = w // 7
        
        # SMPTE color bars
        smpte_colors = [
            (191, 191, 191),  # Gray 75%
            (191, 191, 0),    # Yellow
            (0, 191, 191),    # Cyan
            (0, 191, 0),      # Green
            (191, 0, 191),    # Magenta
            (191, 0, 0),      # Red
            (0, 0, 191)       # Blue
        ]
        
        sub_colors = [
            (191, 0, 0),      # Red
            (0, 191, 0),      # Green
            (0, 0, 191),      # Blue
            (0, 0, 0)         # Black
        ]
        
        img = np.zeros((h, w, 3), dtype=np.uint8)
        
        for i, color in enumerate(smpte_colors):
            x1 = i * bar_width
            x2 = (i + 1) * bar_width if i < 6 else w
            img[:, x1:x2] = color
        
        # Add sub-bars at bottom
        sub_height = h // 4
        for i, color in enumerate(sub_colors):
            x1 = i * (w // 4)
            x2 = (i + 1) * (w // 4)
            img[h-sub_height:h, x1:x2] = color
        
        return img
    
    def generate_checkerboard(self, size: int = 16) -> np.ndarray:
        """Generate checkerboard pattern"""
        w, h = self.config.width, self.config.height
        img = np.zeros((h, w, 3), dtype=np.uint8)
        
        for y in range(0, h, size):
            for x in range(0, w, size):
                color = 255 if ((x // size + y // size) % 2 == 0) else 0
                img[y:y+size, x:x+size] = color
        
        return img
    
    def generate_gradient(self, direction: int = 0) -> np.ndarray:
        """Generate gradient pattern"""
        w, h = self.config.width, self.config.height
        img = np.zeros((h, w, 3), dtype=np.uint8)
        
        for y in range(h):
            for x in range(w):
                if direction == 0:  # Horizontal
                    val = int(x * 255 / w)
                elif direction == 1:  # Vertical
                    val = int(y * 255 / h)
                else:  # Diagonal
                    val = int((x + y) * 255 / (w + h))
                
                img[y, x] = val
        
        return img
    
    def generate_moving_bar(self) -> np.ndarray:
        """Generate moving bar pattern"""
        w, h = self.config.width, self.config.height
        bar_width = 20
        img = np.zeros((h, w, 3), dtype=np.uint8)
        
        # Update bar position
        self.motion_x += self.motion_dx
        if self.motion_x > w or self.motion_x < 0:
            self.motion_dx *= -1
            self.motion_x += self.motion_dx
        
        bar_pos = self.motion_x
        img[:, bar_pos:bar_pos+bar_width] = 255
        
        return img
    
    def generate_noise(self) -> np.ndarray:
        """Generate random noise pattern"""
        w, h = self.config.width, self.config.height
        img = np.random.randint(0, 255, (h, w, 3), dtype=np.uint8)
        return img
    
    def generate_color_wheel(self) -> np.ndarray:
        """Generate color wheel pattern"""
        w, h = self.config.width, self.config.height
        cx, cy = w // 2, h // 2
        radius = min(w, h) // 2
        
        img = np.zeros((h, w, 3), dtype=np.uint8)
        
        for y in range(h):
            for x in range(w):
                dx, dy = x - cx, y - cy
                dist = np.sqrt(dx**2 + dy**2)
                
                if dist < radius:
                    angle = np.arctan2(dy, dx)
                    if angle < 0:
                        angle += 2 * np.pi
                    
                    # Convert angle to RGB
                    hue = angle / (2 * np.pi) * 360
                    sat = 1.0
                    val = 1.0 - (dist / radius)
                    
                    # HSV to RGB conversion
                    h_i = int(hue / 60) % 6
                    f = hue / 60 - h_i
                    p = int(val * (1 - sat) * 255)
                    q = int(val * (1 - f * sat) * 255)
                    t = int(val * (1 - (1 - f) * sat) * 255)
                    v = int(val * 255)
                    
                    if h_i == 0:
                        img[y, x] = (v, t, p)
                    elif h_i == 1:
                        img[y, x] = (q, v, p)
                    elif h_i == 2:
                        img[y, x] = (p, v, t)
                    elif h_i == 3:
                        img[y, x] = (p, q, v)
                    elif h_i == 4:
                        img[y, x] = (t, p, v)
                    else:
                        img[y, x] = (v, p, q)
        
        return img
    
    def generate_text_overlay(self, img: np.ndarray) -> np.ndarray:
        """Add text overlay to image"""
        if not CV2_AVAILABLE:
            return img
        
        w, h = self.config.width, self.config.height
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.7
        color = (255, 255, 255)
        thickness = 2
        
        # Add frame counter
        text = f"Frame: {self.stats.count} | FPS: {self.stats.fps:.1f}"
        cv2.putText(img, text, (10, 30), font, font_scale, color, thickness)
        
        # Add configuration info
        info = f"{self.config.width}x{self.config.height} @ {self.config.fps}fps"
        cv2.putText(img, info, (10, 60), font, font_scale, color, thickness)
        
        # Add custom text
        if self.config.text:
            cv2.putText(img, self.config.text, (10, 90), font, font_scale, color, thickness)
        
        # Add timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(img, timestamp, (w - 300, 30), font, font_scale, color, thickness)
        
        return img
    
    def generate_frame(self) -> np.ndarray:
        """Generate a single frame"""
        img = None
        
        try:
            # Generate pattern
            if self.config.pattern == PatternType.COLOR_BARS:
                img = self.generate_color_bars()
            elif self.config.pattern == PatternType.SMPTE_BARS:
                img = self.generate_smpte_bars()
            elif self.config.pattern == PatternType.CHECKERBOARD:
                img = self.generate_checkerboard(self.config.param1)
            elif self.config.pattern == PatternType.GRADIENT:
                img = self.generate_gradient(self.config.param1)
            elif self.config.pattern == PatternType.MOVING_BAR:
                img = self.generate_moving_bar()
            elif self.config.pattern == PatternType.NOISE:
                img = self.generate_noise()
            elif self.config.pattern == PatternType.COLOR_WHEEL:
                img = self.generate_color_wheel()
            else:
                img = self.generate_color_bars()
            
            # Add text overlay
            if self.config.text:
                img = self.generate_text_overlay(img)
            
            # Apply brightness/contrast adjustments
            if self.config.brightness != 128 or self.config.contrast != 128:
                alpha = self.config.contrast / 128.0
                beta = self.config.brightness - 128
                img = cv2.convertScaleAbs(img, alpha=alpha, beta=beta)
            
            # Convert to desired format
            img = self.convert_format(img)
            
        except Exception as e:
            logger.error(f"Frame generation error: {e}")
            img = np.zeros(self.frame_size, dtype=np.uint8)
        
        return img
    
    def convert_format(self, img: np.ndarray) -> np.ndarray:
        """Convert image to desired pixel format"""
        if not CV2_AVAILABLE:
            return img.flatten()
        
        w, h = self.config.width, self.config.height
        
        if self.config.format == PixelFormat.RGB24:
            return img.flatten()
        elif self.config.format == PixelFormat.RGB32:
            # Add alpha channel
            alpha = np.ones((h, w, 1), dtype=np.uint8) * 255
            img_rgba = np.dstack((img, alpha))
            return img_rgba.flatten()
        elif self.config.format == PixelFormat.GREY:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            return gray.flatten()
        elif self.config.format == PixelFormat.YUYV:
            yuv = cv2.cvtColor(img, cv2.COLOR_RGB2YUV)
            yuyv = np.zeros((h, w, 2), dtype=np.uint8)
            yuyv[:, :, 0] = yuv[:, :, 0]  # Y
            yuyv[:, :, 1] = yuv[:, :, 1] if (np.arange(w) % 2 == 0).all() else yuv[:, :, 2]
            return yuyv.flatten()
        else:
            return img.flatten()
    
    def start(self):
        """Start frame generation"""
        if self.running:
            return
        
        self.running = True
        self.stats = FrameStats()
        self.stats.timestamp = time.time()
        
        # Start generation thread
        self.thread = threading.Thread(target=self._generation_loop)
        self.thread.daemon = True
        self.thread.start()
        
        logger.info("Frame generation started")
    
    def stop(self):
        """Stop frame generation"""
        self.running = False
        if hasattr(self, 'thread'):
            self.thread.join(timeout=2)
        logger.info("Frame generation stopped")
    
    def _generation_loop(self):
        """Frame generation loop"""
        frame_interval = 1.0 / self.config.fps
        next_frame_time = time.time()
        
        while self.running:
            current_time = time.time()
            
            # Generate frame
            frame = self.generate_frame()
            
            # Update stats
            with self.lock:
                self.stats.count += 1
                self.stats.bytes += len(frame)
                
                # Calculate FPS
                elapsed = current_time - self.stats.timestamp
                if elapsed > 0:
                    self.stats.fps = self.stats.count / elapsed
                    self.stats.elapsed = elapsed
            
            # Store frame in queue
            try:
                self.frame_queue.put_nowait(frame)
            except queue.Full:
                self.stats.dropped += 1
            
            # Notify callbacks
            for callback in self.callbacks:
                try:
                    callback(frame, self.stats)
                except Exception as e:
                    logger.error(f"Callback error: {e}")
            
            # Wait for next frame
            next_frame_time += frame_interval
            sleep_time = max(0, next_frame_time - time.time())
            if sleep_time > 0:
                time.sleep(sleep_time)
    
    def get_frame(self) -> Optional[np.ndarray]:
        """Get latest frame"""
        try:
            return self.frame_queue.get_nowait()
        except queue.Empty:
            return None
    
    def register_callback(self, callback):
        """Register frame callback"""
        self.callbacks.append(callback)
    
    def unregister_callback(self, callback):
        """Unregister frame callback"""
        if callback in self.callbacks:
            self.callbacks.remove(callback)
    
    def get_stats(self) -> Dict:
        """Get generation statistics"""
        with self.lock:
            return {
                'count': self.stats.count,
                'fps': self.stats.fps,
                'bytes': self.stats.bytes,
                'elapsed': self.stats.elapsed,
                'dropped': self.stats.dropped,
                'frame_size': self.frame_size
            }

# ==================== V4L2 Device Interface ====================

class V4L2Device:
    """V4L2 device interface"""
    
    def __init__(self, device_path: str = "/dev/video0"):
        self.device_path = device_path
        self.fd = None
        self.running = False
        
        if not V4L2_AVAILABLE:
            logger.warning("V4L2 Python bindings not available")
    
    def open(self) -> bool:
        """Open V4L2 device"""
        try:
            if V4L2_AVAILABLE:
                self.fd = v4l2.open(self.device_path)
                if self.fd >= 0:
                    logger.info(f"Opened V4L2 device: {self.device_path}")
                    return True
            
            # Fallback to direct file access
            import fcntl
            import struct
            
            self.fd = os.open(self.device_path, os.O_RDWR | os.O_NONBLOCK)
            if self.fd >= 0:
                logger.info(f"Opened V4L2 device (fallback): {self.device_path}")
                return True
            
        except Exception as e:
            logger.error(f"Failed to open V4L2 device: {e}")
        
        return False
    
    def close(self):
        """Close V4L2 device"""
        if self.fd is not None:
            try:
                if V4L2_AVAILABLE:
                    v4l2.close(self.fd)
                else:
                    os.close(self.fd)
                self.fd = None
                logger.info("V4L2 device closed")
            except Exception as e:
                logger.error(f"Failed to close V4L2 device: {e}")
    
    def set_format(self, width: int, height: int, format: PixelFormat) -> bool:
        """Set video format"""
        if not self.fd:
            return False
        
        try:
            if V4L2_AVAILABLE:
                # Use V4L2 bindings
                return True
            else:
                # Use direct ioctl
                import fcntl
                import struct
                
                # V4L2 format structure
                fmt = struct.pack('Iiiii', 
                                  v4l2.V4L2_BUF_TYPE_VIDEO_CAPTURE,
                                  width, height,
                                  0,  # pixelformat
                                  0)  # field
                
                fcntl.ioctl(self.fd, v4l2.VIDIOC_S_FMT, fmt)
                return True
                
        except Exception as e:
            logger.error(f"Failed to set format: {e}")
            return False
    
    def start_streaming(self) -> bool:
        """Start video streaming"""
        self.running = True
        return True
    
    def stop_streaming(self) -> bool:
        """Stop video streaming"""
        self.running = False
        return True
    
    def write_frame(self, frame: np.ndarray) -> int:
        """Write frame to device"""
        if not self.fd or not self.running:
            return 0
        
        try:
            if V4L2_AVAILABLE:
                return v4l2.write(self.fd, frame.tobytes())
            else:
                return os.write(self.fd, frame.tobytes())
        except Exception as e:
            logger.error(f"Failed to write frame: {e}")
            return 0

# ==================== Camera Simulation ====================

class CameraSimulation:
    """Complete camera simulation system"""
    
    def __init__(self):
        self.generator = None
        self.v4l2_device = None
        self.running = False
        self.thread = None
        self.stats = {}
        
        # Configuration
        self.config = FrameConfig()
    
    def setup(self, config: FrameConfig = None, device_path: str = "/dev/video0"):
        """Setup camera simulation"""
        if config:
            self.config = config
        
        # Initialize frame generator
        self.generator = FrameGenerator(self.config)
        
        # Initialize V4L2 device
        self.v4l2_device = V4L2Device(device_path)
        if not self.v4l2_device.open():
            logger.warning("Failed to open V4L2 device")
        
        # Setup format
        self.v4l2_device.set_format(
            self.config.width,
            self.config.height,
            self.config.format
        )
        
        logger.info("Camera simulation setup complete")
    
    def start(self):
        """Start camera simulation"""
        if self.running:
            return
        
        self.running = True
        
        # Start generator
        self.generator.start()
        
        # Start streaming
        self.v4l2_device.start_streaming()
        
        # Start processing thread
        self.thread = threading.Thread(target=self._processing_loop)
        self.thread.daemon = True
        self.thread.start()
        
        logger.info("Camera simulation started")
    
    def stop(self):
        """Stop camera simulation"""
        self.running = False
        
        if self.thread:
            self.thread.join(timeout=2)
        
        self.v4l2_device.stop_streaming()
        self.generator.stop()
        self.v4l2_device.close()
        
        logger.info("Camera simulation stopped")
    
    def _processing_loop(self):
        """Processing loop"""
        while self.running:
            frame = self.generator.get_frame()
            if frame is not None:
                self.v4l2_device.write_frame(frame)
                
                # Update stats
                self.stats = self.generator.get_stats()
            
            time.sleep(0.001)
    
    def get_stats(self) -> Dict:
        """Get simulation statistics"""
        return {
            **self.stats,
            'config': {
                'width': self.config.width,
                'height': self.config.height,
                'fps': self.config.fps,
                'format': self.config.format.name,
                'pattern': self.config.pattern.name
            }
        }

# ==================== Command Line Interface ====================

class CameraCLI:
    """Command line interface for camera simulation"""
    
    def __init__(self):
        self.sim = CameraSimulation()
        self.running = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, sig, frame):
        print("\n")
        logger.info("Received interrupt signal")
        self.running = False
        self.sim.stop()
    
    def run(self):
        """Run command line interface"""
        parser = self._create_parser()
        args = parser.parse_args()
        
        if not args.command:
            parser.print_help()
            return
        
        # Setup configuration
        config = FrameConfig()
        if args.width:
            config.width = args.width
        if args.height:
            config.height = args.height
        if args.fps:
            config.fps = args.fps
        if args.format:
            config.format = self._parse_format(args.format)
        if args.pattern:
            config.pattern = self._parse_pattern(args.pattern)
        if args.text:
            config.text = args.text
        
        # Setup device
        device_path = args.device or "/dev/video0"
        self.sim.setup(config, device_path)
        
        # Start simulation
        self.running = True
        self.sim.start()
        
        # Run command loop
        self._command_loop()
    
    def _create_parser(self):
        """Create argument parser"""
        parser = argparse.ArgumentParser(
            description="Virtual Camera Simulation for Intel NUC",
            formatter_class=argparse.RawDescriptionHelpFormatter
        )
        
        parser.add_argument('command',
                           choices=['start', 'stop', 'status', 'config', 'stream'],
                           nargs='?',
                           default='start',
                           help='Command to execute')
        
        parser.add_argument('-d', '--device',
                           type=str,
                           help='V4L2 device path (default: /dev/video0)')
        
        parser.add_argument('-w', '--width',
                           type=int,
                           default=1920,
                           help='Frame width (default: 1920)')
        
        parser.add_argument('-H', '--height',
                           type=int,
                           default=1080,
                           help='Frame height (default: 1080)')
        
        parser.add_argument('-f', '--fps',
                           type=int,
                           default=30,
                           help='Frames per second (default: 30)')
        
        parser.add_argument('--format',
                           type=str,
                           default='YUYV',
                           choices=['YUYV', 'UYVY', 'RGB24', 'RGB32', 'GREY', 'YUV420'],
                           help='Pixel format (default: YUYV)')
        
        parser.add_argument('--pattern',
                           type=str,
                           default='COLOR_BARS',
                           choices=['COLOR_BARS', 'SMPTE_BARS', 'CHECKERBOARD',
                                   'GRADIENT', 'MOVING_BAR', 'NOISE', 'COLOR_WHEEL',
                                   'TEXT', 'CLOCK', 'MOVIE'],
                           help='Test pattern (default: COLOR_BARS)')
        
        parser.add_argument('--text',
                           type=str,
                           default='Intel NUC Virtual Camera',
                           help='Text overlay')
        
        parser.add_argument('-s', '--save',
                           action='store_true',
                           help='Save frames to files')
        
        parser.add_argument('-v', '--verbose',
                           action='store_true',
                           help='Enable verbose output')
        
        return parser
    
    def _parse_format(self, format_str: str) -> PixelFormat:
        """Parse pixel format string"""
        format_map = {
            'YUYV': PixelFormat.YUYV,
            'UYVY': PixelFormat.UYVY,
            'RGB24': PixelFormat.RGB24,
            'RGB32': PixelFormat.RGB32,
            'GREY': PixelFormat.GREY,
            'YUV420': PixelFormat.YUV420,
            'YVU420': PixelFormat.YVU420
        }
        return format_map.get(format_str.upper(), PixelFormat.YUYV)
    
    def _parse_pattern(self, pattern_str: str) -> PatternType:
        """Parse pattern string"""
        pattern_map = {
            'COLOR_BARS': PatternType.COLOR_BARS,
            'SMPTE_BARS': PatternType.SMPTE_BARS,
            'CHECKERBOARD': PatternType.CHECKERBOARD,
            'GRADIENT': PatternType.GRADIENT,
            'MOVING_BAR': PatternType.MOVING_BAR,
            'NOISE': PatternType.NOISE,
            'COLOR_WHEEL': PatternType.COLOR_WHEEL,
            'TEXT': PatternType.TEXT,
            'CLOCK': PatternType.CLOCK,
            'MOVIE': PatternType.MOVIE
        }
        return pattern_map.get(pattern_str.upper(), PatternType.COLOR_BARS)
    
    def _command_loop(self):
        """Interactive command loop"""
        print(f"\n{COLORS['GREEN']}Camera Simulation Running{COLORS['RESET']}")
        print(f"Device: /dev/video0")
        print(f"Resolution: {self.sim.config.width}x{self.sim.config.height}")
        print(f"FPS: {self.sim.config.fps}")
        print(f"Format: {self.sim.config.format.name}")
        print(f"Pattern: {self.sim.config.pattern.name}")
        print("\nCommands:")
        print("  status  - Show status and statistics")
        print("  config  - Show current configuration")
        print("  pattern <name> - Change test pattern")
        print("  fps <number>   - Change frame rate")
        print("  text <string>  - Change text overlay")
        print("  save    - Save current frame")
        print("  stop    - Stop simulation")
        print("  help    - Show this help")
        print("\nPress Ctrl+C to stop\n")
        
        while self.running:
            try:
                cmd = input(f"{COLORS['CYAN']}> {COLORS['RESET']}").strip().lower()
                
                if not cmd:
                    continue
                
                parts = cmd.split()
                command = parts[0]
                
                if command == 'status':
                    self._show_status()
                elif command == 'config':
                    self._show_config()
                elif command == 'pattern' and len(parts) > 1:
                    self._set_pattern(parts[1])
                elif command == 'fps' and len(parts) > 1:
                    self._set_fps(int(parts[1]))
                elif command == 'text' and len(parts) > 1:
                    self._set_text(' '.join(parts[1:]))
                elif command == 'save':
                    self._save_frame()
                elif command == 'stop':
                    self.running = False
                    break
                elif command == 'help':
                    self._show_help()
                else:
                    print(f"Unknown command: {command}")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Command error: {e}")
        
        if self.running:
            self.running = False
            self.sim.stop()
        
        print("\nCamera simulation stopped")
    
    def _show_status(self):
        """Show status and statistics"""
        stats = self.sim.get_stats()
        
        print(f"\n{COLORS['CYAN']}=== Camera Simulation Status ==={COLORS['RESET']}")
        print(f"Running: {self.running}")
        print(f"Frames Generated: {stats.get('count', 0)}")
        print(f"FPS: {stats.get('fps', 0):.1f}")
        print(f"Frames Dropped: {stats.get('dropped', 0)}")
        print(f"Bytes Generated: {stats.get('bytes', 0):,}")
        print(f"Elapsed: {stats.get('elapsed', 0):.1f}s")
        print(f"Frame Size: {stats.get('frame_size', 0)} bytes")
        print()
    
    def _show_config(self):
        """Show current configuration"""
        config = self.sim.config
        
        print(f"\n{COLORS['CYAN']}=== Current Configuration ==={COLORS['RESET']}")
        print(f"Width: {config.width}")
        print(f"Height: {config.height}")
        print(f"FPS: {config.fps}")
        print(f"Format: {config.format.name}")
        print(f"Pattern: {config.pattern.name}")
        print(f"Text: {config.text}")
        print(f"Brightness: {config.brightness}")
        print(f"Contrast: {config.contrast}")
        print(f"Saturation: {config.saturation}")
        print()
    
    def _set_pattern(self, pattern_name: str):
        """Set test pattern"""
        try:
            pattern = self._parse_pattern(pattern_name)
            self.sim.config.pattern = pattern
            print(f"{COLORS['GREEN']}Pattern changed to: {pattern.name}{COLORS['RESET']}")
        except Exception as e:
            print(f"{COLORS['RED']}Invalid pattern: {pattern_name}{COLORS['RESET']}")
    
    def _set_fps(self, fps: int):
        """Set frame rate"""
        if 1 <= fps <= 120:
            self.sim.config.fps = fps
            # Restart generator
            self.sim.generator.stop()
            self.sim.generator = FrameGenerator(self.sim.config)
            self.sim.generator.start()
            print(f"{COLORS['GREEN']}FPS changed to: {fps}{COLORS['RESET']}")
        else:
            print(f"{COLORS['RED']}Invalid FPS: {fps} (must be 1-120){COLORS['RESET']}")
    
    def _set_text(self, text: str):
        """Set text overlay"""
        self.sim.config.text = text
        print(f"{COLORS['GREEN']}Text changed to: {text}{COLORS['RESET']}")
    
    def _save_frame(self):
        """Save current frame"""
        frame = self.sim.generator.get_frame()
        if frame is not None:
            filename = f"frame_{datetime.now().strftime('%Y%m%d_%H%M%S')}.raw"
            with open(filename, 'wb') as f:
                f.write(frame.tobytes())
            print(f"{COLORS['GREEN']}Frame saved to: {filename}{COLORS['RESET']}")
        else:
            print(f"{COLORS['RED']}No frame available{COLORS['RESET']}")
    
    def _show_help(self):
        """Show help"""
        print(f"\n{COLORS['CYAN']}=== Available Commands ==={COLORS['RESET']}")
        print("  status           - Show status and statistics")
        print("  config           - Show current configuration")
        print("  pattern <name>   - Change test pattern")
        print("  fps <number>     - Change frame rate")
        print("  text <string>    - Change text overlay")
        print("  save             - Save current frame")
        print("  stop             - Stop simulation")
        print("  help             - Show this help")
        print()

# ==================== Main Entry Point ====================

def main():
    """Main entry point"""
    try:
        cli = CameraCLI()
        cli.run()
    except KeyboardInterrupt:
        print("\n")
        logger.info("Shutdown requested")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
