#!/usr/bin/env python3
"""
audio-routing.py - Advanced Audio Routing and Processing

This script provides advanced audio routing, mixing, and processing
capabilities for virtual audio devices on Intel NUC platforms.
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
import queue
import signal
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from collections import deque
import numpy as np

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

# ==================== Data Classes ====================

class AudioFormat(Enum):
    """Audio formats"""
    S16LE = "s16le"
    S24LE = "s24le"
    S32LE = "s32le"
    F32LE = "f32le"

class AudioEffect(Enum):
    """Audio effects"""
    NONE = "none"
    EQ = "equalizer"
    COMPRESSOR = "compressor"
    REVERB = "reverb"
    DELAY = "delay"
    CHORUS = "chorus"
    FLANGER = "flanger"
    PITCH_SHIFT = "pitch_shift"
    NOISE_GATE = "noise_gate"
    LIMITER = "limiter"

@dataclass
class AudioDevice:
    """Audio device information"""
    name: str
    type: str  # sink, source, monitor
    description: str
    sample_rate: int = 48000
    channels: int = 2
    format: AudioFormat = AudioFormat.S16LE
    active: bool = True

@dataclass
class AudioRoute:
    """Audio routing configuration"""
    source: str
    sink: str
    enabled: bool = True
    volume: float = 1.0
    mute: bool = False
    effects: List[AudioEffect] = field(default_factory=list)

@dataclass
class AudioEffectConfig:
    """Audio effect configuration"""
    effect: AudioEffect
    params: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

# ==================== Audio Processor ====================

class AudioProcessor:
    """Audio processing engine"""
    
    def __init__(self, sample_rate: int = 48000, channels: int = 2):
        self.sample_rate = sample_rate
        self.channels = channels
        self.effects = []
        self.running = False
        
        # Audio buffers
        self.buffer_size = 1024
        self.input_buffer = deque(maxlen=1024)
        self.output_buffer = deque(maxlen=1024)
        
        # Processing thread
        self.thread = None
        self.lock = threading.Lock()
        self.processors = []
        
        logger.info(f"Audio processor initialized: {sample_rate}Hz, {channels} channels")
    
    def add_effect(self, effect: AudioEffectConfig) -> bool:
        """Add audio effect"""
        try:
            self.effects.append(effect)
            logger.info(f"Added effect: {effect.effect.value}")
            return True
        except Exception as e:
            logger.error(f"Failed to add effect: {e}")
            return False
    
    def remove_effect(self, effect_type: AudioEffect) -> bool:
        """Remove audio effect"""
        self.effects = [e for e in self.effects if e.effect != effect_type]
        logger.info(f"Removed effect: {effect_type.value}")
        return True
    
    def process_audio(self, audio_data: np.ndarray) -> np.ndarray:
        """Process audio through effects chain"""
        data = audio_data.copy()
        
        for effect in self.effects:
            if not effect.enabled:
                continue
            
            try:
                data = self._apply_effect(data, effect)
            except Exception as e:
                logger.error(f"Effect {effect.effect.value} failed: {e}")
        
        return data
    
    def _apply_effect(self, data: np.ndarray, config: AudioEffectConfig) -> np.ndarray:
        """Apply specific audio effect"""
        if config.effect == AudioEffect.EQ:
            return self._apply_eq(data, config.params)
        elif config.effect == AudioEffect.COMPRESSOR:
            return self._apply_compressor(data, config.params)
        elif config.effect == AudioEffect.REVERB:
            return self._apply_reverb(data, config.params)
        elif config.effect == AudioEffect.DELAY:
            return self._apply_delay(data, config.params)
        elif config.effect == AudioEffect.CHORUS:
            return self._apply_chorus(data, config.params)
        elif config.effect == AudioEffect.FLANGER:
            return self._apply_flanger(data, config.params)
        elif config.effect == AudioEffect.PITCH_SHIFT:
            return self._apply_pitch_shift(data, config.params)
        elif config.effect == AudioEffect.NOISE_GATE:
            return self._apply_noise_gate(data, config.params)
        elif config.effect == AudioEffect.LIMITER:
            return self._apply_limiter(data, config.params)
        else:
            return data
    
    def _apply_eq(self, data: np.ndarray, params: Dict) -> np.ndarray:
        """Apply equalizer"""
        if not params:
            params = {'frequencies': [60, 250, 1000, 4000, 16000],
                     'gains': [0, 0, 0, 0, 0]}
        
        # Simple biquad filter implementation
        # This is a placeholder - in production, use scipy or custom filters
        return data
    
    def _apply_compressor(self, data: np.ndarray, params: Dict) -> np.ndarray:
        """Apply compressor"""
        if not params:
            params = {'threshold': -12, 'ratio': 4, 'knee': 6,
                     'attack': 3, 'release': 100}
        
        # Simple compression
        threshold = params.get('threshold', -12)
        ratio = params.get('ratio', 4)
        
        # Convert to linear
        threshold_linear = 10 ** (threshold / 20)
        
        # Apply compression
        for i in range(len(data)):
            if abs(data[i]) > threshold_linear:
                data[i] = data[i] / ratio
        
        return data
    
    def _apply_reverb(self, data: np.ndarray, params: Dict) -> np.ndarray:
        """Apply reverb"""
        if not params:
            params = {'room_size': 50, 'damping': 50,
                     'width': 70, 'level': 30}
        
        # Simple reverb using delay lines
        room_size = params.get('room_size', 50)
        delay_ms = room_size / 100 * 100  # 0-100ms
        
        delay_samples = int(delay_ms * self.sample_rate / 1000)
        if delay_samples <= 0:
            delay_samples = 1
        
        # Create delay buffer
        delay_buffer = np.zeros(delay_samples)
        
        # Apply reverb
        output = np.zeros_like(data)
        for i in range(len(data)):
            delay_index = i % delay_samples
            delay_sample = delay_buffer[delay_index]
            output[i] = data[i] + delay_sample * 0.5
            delay_buffer[delay_index] = data[i] * 0.5 + delay_sample * 0.5
        
        return output
    
    def _apply_delay(self, data: np.ndarray, params: Dict) -> np.ndarray:
        """Apply delay effect"""
        if not params:
            params = {'delay_ms': 500, 'feedback': 0.3}
        
        delay_ms = params.get('delay_ms', 500)
        feedback = params.get('feedback', 0.3)
        
        delay_samples = int(delay_ms * self.sample_rate / 1000)
        if delay_samples <= 0:
            delay_samples = 1
        
        # Create delay buffer
        delay_buffer = np.zeros(delay_samples)
        
        # Apply delay
        output = np.zeros_like(data)
        for i in range(len(data)):
            delay_index = i % delay_samples
            delay_sample = delay_buffer[delay_index]
            output[i] = data[i] + delay_sample
            delay_buffer[delay_index] = data[i] + delay_sample * feedback
        
        return output
    
    def _apply_chorus(self, data: np.ndarray, params: Dict) -> np.ndarray:
        """Apply chorus effect"""
        if not params:
            params = {'rate': 1.0, 'depth': 10, 'delay_ms': 20}
        
        # Simple chorus using modulated delay
        rate = params.get('rate', 1.0)
        depth = params.get('depth', 10)
        
        # Apply chorus
        output = np.zeros_like(data)
        for i in range(len(data)):
            modulation = depth * np.sin(2 * np.pi * rate * i / self.sample_rate)
            delay_samples = int(10 + modulation)
            if i > delay_samples:
                output[i] = data[i] + data[i - delay_samples] * 0.5
            else:
                output[i] = data[i]
        
        return output
    
    def _apply_flanger(self, data: np.ndarray, params: Dict) -> np.ndarray:
        """Apply flanger effect"""
        if not params:
            params = {'rate': 0.5, 'depth': 5, 'delay_ms': 5}
        
        # Similar to chorus but with shorter delay and feedback
        rate = params.get('rate', 0.5)
        depth = params.get('depth', 5)
        
        output = np.zeros_like(data)
        for i in range(len(data)):
            modulation = depth * np.sin(2 * np.pi * rate * i / self.sample_rate)
            delay_samples = int(1 + modulation)
            if i > delay_samples:
                output[i] = data[i] + data[i - delay_samples] * 0.7
            else:
                output[i] = data[i]
        
        return output
    
    def _apply_pitch_shift(self, data: np.ndarray, params: Dict) -> np.ndarray:
        """Apply pitch shift"""
        if not params:
            params = {'shift': 1.5}
        
        shift = params.get('shift', 1.5)
        
        # Simple pitch shift using resampling
        # This is a placeholder - in production, use phase vocoder
        return data
    
    def _apply_noise_gate(self, data: np.ndarray, params: Dict) -> np.ndarray:
        """Apply noise gate"""
        if not params:
            params = {'threshold': -40, 'attack': 10, 'release': 50}
        
        threshold = params.get('threshold', -40)
        threshold_linear = 10 ** (threshold / 20)
        
        # Apply noise gate
        for i in range(len(data)):
            if abs(data[i]) < threshold_linear:
                data[i] = 0
        
        return data
    
    def _apply_limiter(self, data: np.ndarray, params: Dict) -> np.ndarray:
        """Apply limiter"""
        if not params:
            params = {'threshold': -3, 'ratio': 20}
        
        threshold = params.get('threshold', -3)
        threshold_linear = 10 ** (threshold / 20)
        
        # Apply limiter
        for i in range(len(data)):
            if abs(data[i]) > threshold_linear:
                data[i] = data[i] / abs(data[i]) * threshold_linear
        
        return data

# ==================== Audio Router ====================

class AudioRouter:
    """Audio routing and mixing engine"""
    
    def __init__(self):
        self.routes: List[AudioRoute] = []
        self.devices: Dict[str, AudioDevice] = {}
        self.processor = AudioProcessor()
        self.running = False
        self.lock = threading.Lock()
        
        # Discover audio devices
        self._discover_devices()
    
    def _discover_devices(self):
        """Discover audio devices"""
        try:
            # Get PulseAudio devices
            result = subprocess.run(
                "pactl list short sinks",
                shell=True, capture_output=True, text=True
            )
            for line in result.stdout.split('\n'):
                if line.strip():
                    parts = line.split()
                    self.devices[parts[0]] = AudioDevice(
                        name=parts[0],
                        type='sink',
                        description=parts[1] if len(parts) > 1 else parts[0]
                    )
            
            # Get sources
            result = subprocess.run(
                "pactl list short sources",
                shell=True, capture_output=True, text=True
            )
            for line in result.stdout.split('\n'):
                if line.strip():
                    parts = line.split()
                    self.devices[parts[0]] = AudioDevice(
                        name=parts[0],
                        type='source',
                        description=parts[1] if len(parts) > 1 else parts[0]
                    )
            
            logger.info(f"Discovered {len(self.devices)} audio devices")
            
        except Exception as e:
            logger.warning(f"Failed to discover audio devices: {e}")
    
    def add_route(self, route: AudioRoute) -> bool:
        """Add audio route"""
        with self.lock:
            if route.source not in self.devices:
                logger.error(f"Source device not found: {route.source}")
                return False
            
            if route.sink not in self.devices:
                logger.error(f"Sink device not found: {route.sink}")
                return False
            
            self.routes.append(route)
            logger.info(f"Route added: {route.source} -> {route.sink}")
            
            # Apply route
            self._apply_route(route)
            return True
    
    def remove_route(self, source: str, sink: str) -> bool:
        """Remove audio route"""
        with self.lock:
            self.routes = [r for r in self.routes 
                          if not (r.source == source and r.sink == sink)]
            logger.info(f"Route removed: {source} -> {sink}")
            
            # Remove route
            self._remove_route(source, sink)
            return True
    
    def _apply_route(self, route: AudioRoute):
        """Apply audio route"""
        try:
            # Create loopback
            if route.enabled:
                cmd = f"pactl load-module module-loopback source={route.source} sink={route.sink}"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info(f"Applied route: {route.source} -> {route.sink}")
                else:
                    logger.error(f"Failed to apply route: {result.stderr}")
        except Exception as e:
            logger.error(f"Failed to apply route: {e}")
    
    def _remove_route(self, source: str, sink: str):
        """Remove audio route"""
        try:
            # Find and remove loopback module
            result = subprocess.run(
                f"pactl list short modules | grep loopback | grep source={source}",
                shell=True, capture_output=True, text=True
            )
            for line in result.stdout.split('\n'):
                if line.strip():
                    module_id = line.split()[0]
                    subprocess.run(f"pactl unload-module {module_id}", shell=True)
                    logger.info(f"Removed route: {source} -> {sink}")
        except Exception as e:
            logger.error(f"Failed to remove route: {e}")
    
    def set_volume(self, source: str, sink: str, volume: float):
        """Set route volume"""
        with self.lock:
            for route in self.routes:
                if route.source == source and route.sink == sink:
                    route.volume = max(0, min(1.0, volume))
                    logger.info(f"Volume set to {volume:.2f} for {source} -> {sink}")
                    return True
            return False
    
    def set_mute(self, source: str, sink: str, mute: bool):
        """Set route mute"""
        with self.lock:
            for route in self.routes:
                if route.source == source and route.sink == sink:
                    route.mute = mute
                    logger.info(f"Mute set to {mute} for {source} -> {sink}")
                    return True
            return False
    
    def add_effect(self, source: str, sink: str, effect: AudioEffectConfig):
        """Add effect to route"""
        with self.lock:
            for route in self.routes:
                if route.source == source and route.sink == sink:
                    route.effects.append(effect)
                    logger.info(f"Added effect {effect.effect.value} to {source} -> {sink}")
                    return True
            return False
    
    def remove_effect(self, source: str, sink: str, effect_type: AudioEffect):
        """Remove effect from route"""
        with self.lock:
            for route in self.routes:
                if route.source == source and route.sink == sink:
                    route.effects = [e for e in route.effects 
                                   if e.effect != effect_type]
                    logger.info(f"Removed effect {effect_type.value} from {source} -> {sink}")
                    return True
            return False
    
    def get_status(self) -> Dict:
        """Get router status"""
        return {
            'routes': [{'source': r.source, 'sink': r.sink, 
                       'enabled': r.enabled, 'volume': r.volume,
                       'mute': r.mute, 'effects': [e.effect.value for e in r.effects]}
                      for r in self.routes],
            'devices': len(self.devices),
            'device_list': list(self.devices.keys())
        }

# ==================== Audio Stream ====================

class AudioStream:
    """Audio stream for capturing and playback"""
    
    def __init__(self, device: str, direction: str = 'capture',
                 sample_rate: int = 48000, channels: int = 2,
                 format: AudioFormat = AudioFormat.S16LE):
        self.device = device
        self.direction = direction
        self.sample_rate = sample_rate
        self.channels = channels
        self.format = format
        self.running = False
        self.thread = None
        self.callbacks = []
        
        # Audio buffer
        self.buffer = deque(maxlen=4096)
        self.lock = threading.Lock()
        self.processor = AudioProcessor(sample_rate, channels)
        
        logger.info(f"Audio stream initialized: {device} ({direction})")
    
    def start(self):
        """Start audio stream"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._stream_loop)
        self.thread.daemon = True
        self.thread.start()
        
        logger.info(f"Audio stream started: {self.device}")
    
    def stop(self):
        """Stop audio stream"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        logger.info(f"Audio stream stopped: {self.device}")
    
    def _stream_loop(self):
        """Audio stream loop"""
        buffer_size = 1024
        
        # Prepare command
        if self.direction == 'capture':
            cmd = f"parecord -d {self.device} --rate={self.sample_rate} --channels={self.channels} --format={self.format.value} --file-format=raw"
            mode = 'r'
        else:
            cmd = f"paplay -d {self.device} --rate={self.sample_rate} --channels={self.channels} --format={self.format.value} --file-format=raw"
            mode = 'w'
        
        # Start subprocess
        process = subprocess.Popen(
            cmd.split(),
            stdin=subprocess.PIPE if self.direction == 'playback' else None,
            stdout=subprocess.PIPE if self.direction == 'capture' else None,
            stderr=subprocess.PIPE,
            bufsize=0
        )
        
        while self.running:
            try:
                if self.direction == 'capture':
                    # Read audio data
                    data = process.stdout.read(buffer_size * 2 * self.channels)
                    if data:
                        audio_data = np.frombuffer(data, dtype=np.int16)
                        processed = self.processor.process_audio(audio_data)
                        self.buffer.append(processed)
                        
                        # Notify callbacks
                        for callback in self.callbacks:
                            try:
                                callback(processed)
                            except Exception as e:
                                logger.error(f"Callback error: {e}")
                
                else:
                    # Playback audio
                    if self.buffer:
                        data = self.buffer.popleft()
                        process.stdin.write(data.tobytes())
                    
                    time.sleep(0.001)
                
            except Exception as e:
                if self.running:
                    logger.error(f"Stream error: {e}")
                break
        
        process.terminate()
        process.wait()
    
    def write(self, data: np.ndarray):
        """Write audio data to buffer"""
        with self.lock:
            self.buffer.append(data)
    
    def register_callback(self, callback: Callable):
        """Register data callback"""
        self.callbacks.append(callback)
    
    def unregister_callback(self, callback: Callable):
        """Unregister data callback"""
        if callback in self.callbacks:
            self.callbacks.remove(callback)

# ==================== Audio Mixer ====================

class AudioMixer:
    """Audio mixer for combining multiple streams"""
    
    def __init__(self):
        self.streams: List[AudioStream] = []
        self.mix_buffer = np.zeros(1024, dtype=np.float32)
        self.running = False
        self.lock = threading.Lock()
    
    def add_stream(self, stream: AudioStream) -> bool:
        """Add audio stream to mixer"""
        with self.lock:
            self.streams.append(stream)
            logger.info(f"Stream added to mixer: {stream.device}")
            return True
    
    def remove_stream(self, stream: AudioStream) -> bool:
        """Remove audio stream from mixer"""
        with self.lock:
            if stream in self.streams:
                self.streams.remove(stream)
                logger.info(f"Stream removed from mixer: {stream.device}")
                return True
            return False
    
    def start(self):
        """Start mixing"""
        self.running = True
        threading.Thread(target=self._mix_loop, daemon=True).start()
        logger.info("Audio mixer started")
    
    def stop(self):
        """Stop mixing"""
        self.running = False
        logger.info("Audio mixer stopped")
    
    def _mix_loop(self):
        """Mixing loop"""
        while self.running:
            with self.lock:
                if not self.streams:
                    time.sleep(0.01)
                    continue
                
                # Mix all streams
                mixed = None
                for stream in self.streams:
                    if stream.buffer:
                        data = stream.buffer.popleft()
                        if mixed is None:
                            mixed = data.copy()
                        else:
                            mixed = mixed + data
                
                if mixed is not None:
                    # Normalize
                    max_val = np.max(np.abs(mixed))
                    if max_val > 0:
                        mixed = mixed / max_val
                    
                    # Convert to int16 for playback
                    mixed_int16 = (mixed * 32767).astype(np.int16)
                    
                    # Broadcast to all streams
                    for stream in self.streams:
                        stream.write(mixed_int16)
            
            time.sleep(0.001)

# ==================== Command Line Interface ====================

class AudioCLI:
    """Command line interface for audio routing"""
    
    def __init__(self):
        self.router = AudioRouter()
        self.mixer = AudioMixer()
        self.running = False
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, sig, frame):
        print("\n")
        logger.info("Received interrupt signal")
        self.running = False
    
    def run(self):
        """Run command line interface"""
        parser = self._create_parser()
        args = parser.parse_args()
        
        if not args.command:
            parser.print_help()
            return
        
        if args.command == 'list':
            self._list_devices()
        elif args.command == 'route':
            self._create_route(args)
        elif args.command == 'unroute':
            self._remove_route(args)
        elif args.command == 'volume':
            self._set_volume(args)
        elif args.command == 'mute':
            self._set_mute(args)
        elif args.command == 'effect':
            self._add_effect(args)
        elif args.command == 'status':
            self._show_status()
        elif args.command == 'record':
            self._record_audio(args)
        elif args.command == 'play':
            self._play_audio(args)
        elif args.command == 'monitor':
            self._monitor_audio(args)
        elif args.command == 'interactive':
            self._interactive_mode()
        else:
            print(f"Unknown command: {args.command}")
    
    def _create_parser(self):
        """Create argument parser"""
        parser = argparse.ArgumentParser(
            description="Advanced Audio Routing and Processing",
            formatter_class=argparse.RawDescriptionHelpFormatter
        )
        
        subparsers = parser.add_subparsers(dest='command', help='Commands')
        
        # List devices
        subparsers.add_parser('list', help='List audio devices')
        
        # Route command
        route_parser = subparsers.add_parser('route', help='Create audio route')
        route_parser.add_argument('source', help='Source device')
        route_parser.add_argument('sink', help='Sink device')
        route_parser.add_argument('--volume', '-v', type=float, default=1.0,
                                 help='Volume (0.0-1.0)')
        route_parser.add_argument('--effect', '-e', 
                                 choices=[e.value for e in AudioEffect],
                                 help='Audio effect to apply')
        
        # Unroute command
        unroute_parser = subparsers.add_parser('unroute', help='Remove audio route')
        unroute_parser.add_argument('source', help='Source device')
        unroute_parser.add_argument('sink', help='Sink device')
        
        # Volume command
        volume_parser = subparsers.add_parser('volume', help='Set route volume')
        volume_parser.add_argument('source', help='Source device')
        volume_parser.add_argument('sink', help='Sink device')
        volume_parser.add_argument('volume', type=float, help='Volume (0.0-1.0)')
        
        # Mute command
        mute_parser = subparsers.add_parser('mute', help='Mute/unmute route')
        mute_parser.add_argument('source', help='Source device')
        mute_parser.add_argument('sink', help='Sink device')
        mute_parser.add_argument('mute', choices=['on', 'off'], help='Mute on/off')
        
        # Effect command
        effect_parser = subparsers.add_parser('effect', help='Add/remove effect')
        effect_parser.add_argument('source', help='Source device')
        effect_parser.add_argument('sink', help='Sink device')
        effect_parser.add_argument('action', choices=['add', 'remove'], 
                                  help='Action')
        effect_parser.add_argument('effect_type', choices=[e.value for e in AudioEffect],
                                  help='Effect type')
        
        # Status command
        subparsers.add_parser('status', help='Show status')
        
        # Record command
        record_parser = subparsers.add_parser('record', help='Record audio')
        record_parser.add_argument('--duration', '-d', type=int, default=10,
                                  help='Duration in seconds')
        record_parser.add_argument('--device', '-D', default='default',
                                  help='Source device')
        record_parser.add_argument('--output', '-o', default='recording.wav',
                                  help='Output file')
        
        # Play command
        play_parser = subparsers.add_parser('play', help='Play audio')
        play_parser.add_argument('file', help='Audio file to play')
        play_parser.add_argument('--device', '-D', default='default',
                                help='Sink device')
        
        # Monitor command
        monitor_parser = subparsers.add_parser('monitor', help='Monitor audio')
        monitor_parser.add_argument('device', help='Device to monitor')
        monitor_parser.add_argument('--duration', '-d', type=int, default=10,
                                  help='Duration in seconds')
        
        # Interactive mode
        subparsers.add_parser('interactive', help='Interactive mode')
        
        return parser
    
    def _list_devices(self):
        """List audio devices"""
        print(f"\n{COLORS['CYAN']}=== Audio Devices ==={COLORS['RESET']}")
        print()
        
        print(f"{COLORS['BLUE']}Sinks:{COLORS['RESET']}")
        subprocess.run("pactl list short sinks | head -20", shell=True)
        print()
        
        print(f"{COLORS['BLUE']}Sources:{COLORS['RESET']}")
        subprocess.run("pactl list short sources | head -20", shell=True)
        print()
        
        print(f"{COLORS['BLUE']}Default Sink:{COLORS['RESET']}")
        subprocess.run("pactl info | grep 'Default Sink'", shell=True)
        print()
        
        print(f"{COLORS['BLUE']}Default Source:{COLORS['RESET']}")
        subprocess.run("pactl info | grep 'Default Source'", shell=True)
        print()
    
    def _create_route(self, args):
        """Create audio route"""
        route = AudioRoute(
            source=args.source,
            sink=args.sink,
            volume=args.volume,
            enabled=True
        )
        
        if args.effect:
            effect = AudioEffectConfig(
                effect=AudioEffect(args.effect),
                enabled=True
            )
            route.effects.append(effect)
        
        if self.router.add_route(route):
            print(f"{COLORS['GREEN']}✓{COLORS['RESET']} Route created: {args.source} -> {args.sink}")
        else:
            print(f"{COLORS['RED']}✗{COLORS['RESET']} Failed to create route")
    
    def _remove_route(self, args):
        """Remove audio route"""
        if self.router.remove_route(args.source, args.sink):
            print(f"{COLORS['GREEN']}✓{COLORS['RESET']} Route removed: {args.source} -> {args.sink}")
        else:
            print(f"{COLORS['RED']}✗{COLORS['RESET']} Failed to remove route")
    
    def _set_volume(self, args):
        """Set route volume"""
        if self.router.set_volume(args.source, args.sink, args.volume):
            print(f"{COLORS['GREEN']}✓{COLORS['RESET']} Volume set to {args.volume:.2f}")
        else:
            print(f"{COLORS['RED']}✗{COLORS['RESET']} Failed to set volume")
    
    def _set_mute(self, args):
        """Set route mute"""
        mute = args.mute == 'on'
        if self.router.set_mute(args.source, args.sink, mute):
            print(f"{COLORS['GREEN']}✓{COLORS['RESET']} Mute {'enabled' if mute else 'disabled'}")
        else:
            print(f"{COLORS['RED']}✗{COLORS['RESET']} Failed to set mute")
    
    def _add_effect(self, args):
        """Add or remove effect"""
        effect = AudioEffectConfig(
            effect=AudioEffect(args.effect_type),
            enabled=True
        )
        
        if args.action == 'add':
            if self.router.add_effect(args.source, args.sink, effect):
                print(f"{COLORS['GREEN']}✓{COLORS['RESET']} Effect added: {args.effect_type}")
            else:
                print(f"{COLORS['RED']}✗{COLORS['RESET']} Failed to add effect")
        else:
            if self.router.remove_effect(args.source, args.sink, AudioEffect(args.effect_type)):
                print(f"{COLORS['GREEN']}✓{COLORS['RESET']} Effect removed: {args.effect_type}")
            else:
                print(f"{COLORS['RED']}✗{COLORS['RESET']} Failed to remove effect")
    
    def _show_status(self):
        """Show status"""
        status = self.router.get_status()
        
        print(f"\n{COLORS['CYAN']}=== Audio Routing Status ==={COLORS['RESET']}")
        print()
        
        print(f"{COLORS['BLUE']}Routes:{COLORS['RESET']}")
        if status['routes']:
            for route in status['routes']:
                status_str = f"{COLORS['GREEN']}✓{COLORS['RESET']} Active" if route['enabled'] else f"{COLORS['RED']}✗{COLORS['RESET']} Inactive"
                print(f"  {route['source']} -> {route['sink']} ({status_str})")
                print(f"    Volume: {route['volume']:.2f}, Mute: {route['mute']}")
                if route['effects']:
                    print(f"    Effects: {', '.join(route['effects'])}")
        else:
            print("  No routes configured")
        
        print()
        print(f"{COLORS['BLUE']}Devices:{COLORS['RESET']}")
        print(f"  Total: {status['devices']}")
        if status['device_list']:
            print("  Devices:")
            for device in status['device_list'][:10]:
                print(f"    {device}")
            if len(status['device_list']) > 10:
                print(f"    ... and {len(status['device_list']) - 10} more")
    
    def _record_audio(self, args):
        """Record audio"""
        print(f"{COLORS['BLUE']}→{COLORS['RESET']} Recording for {args.duration} seconds...")
        print(f"{COLORS['BLUE']}→{COLORS['RESET']} Device: {args.device}")
        print(f"{COLORS['BLUE']}→{COLORS['RESET']} Output: {args.output}")
        
        cmd = f"parecord -d {args.device} --duration={args.duration} {args.output}"
        subprocess.run(cmd, shell=True)
        
        if os.path.exists(args.output):
            size = os.path.getsize(args.output)
            print(f"{COLORS['GREEN']}✓{COLORS['RESET']} Recording saved: {args.output} ({size} bytes)")
        else:
            print(f"{COLORS['RED']}✗{COLORS['RESET']} Recording failed")
    
    def _play_audio(self, args):
        """Play audio"""
        if not os.path.exists(args.file):
            print(f"{COLORS['RED']}✗{COLORS['RESET']} File not found: {args.file}")
            return
        
        print(f"{COLORS['BLUE']}→{COLORS['RESET']} Playing: {args.file}")
        print(f"{COLORS['BLUE']}→{COLORS['RESET']} Device: {args.device}")
        
        cmd = f"paplay -d {args.device} {args.file}"
        subprocess.run(cmd, shell=True)
        
        print(f"{COLORS['GREEN']}✓{COLORS['RESET']} Playback complete")
    
    def _monitor_audio(self, args):
        """Monitor audio"""
        print(f"{COLORS['BLUE']}→{COLORS['RESET']} Monitoring: {args.device}")
        print(f"{COLORS['BLUE']}→{COLORS['RESET']} Duration: {args.duration} seconds")
        print(f"{COLORS['YELLOW']}Press Ctrl+C to stop early{COLORS['RESET']}")
        
        start_time = time.time()
        while time.time() - start_time < args.duration:
            try:
                # Show volume level
                result = subprocess.run(
                    f"pactl list sources | grep -A 10 'Name: {args.device}' | grep 'Volume:'",
                    shell=True, capture_output=True, text=True
                )
                if result.stdout:
                    print(f"\r{COLORS['GREEN']}{result.stdout.strip()}{COLORS['RESET']}", end='')
                time.sleep(0.5)
            except KeyboardInterrupt:
                break
        
        print("\n")
        print(f"{COLORS['GREEN']}✓{COLORS['RESET']} Monitoring complete")
    
    def _interactive_mode(self):
        """Interactive mode"""
        print(f"\n{COLORS['CYAN']}=== Audio Routing Interactive Mode ==={COLORS['RESET']}")
        print(f"{COLORS['BLUE']}Type 'help' for commands{COLORS['RESET']}")
        print()
        
        self.running = True
        
        while self.running:
            try:
                cmd = input(f"{COLORS['CYAN']}audio> {COLORS['RESET']}").strip()
                
                if not cmd:
                    continue
                
                if cmd == 'help':
                    self._show_interactive_help()
                elif cmd == 'list':
                    self._list_devices()
                elif cmd == 'status':
                    self._show_status()
                elif cmd.startswith('route'):
                    parts = cmd.split()
                    if len(parts) >= 3:
                        source = parts[1]
                        sink = parts[2]
                        route = AudioRoute(source=source, sink=sink, enabled=True)
                        self.router.add_route(route)
                        print(f"{COLORS['GREEN']}✓{COLORS['RESET']} Route created: {source} -> {sink}")
                    else:
                        print("Usage: route <source> <sink>")
                elif cmd.startswith('unroute'):
                    parts = cmd.split()
                    if len(parts) >= 3:
                        source = parts[1]
                        sink = parts[2]
                        self.router.remove_route(source, sink)
                        print(f"{COLORS['GREEN']}✓{COLORS['RESET']} Route removed: {source} -> {sink}")
                    else:
                        print("Usage: unroute <source> <sink>")
                elif cmd.startswith('volume'):
                    parts = cmd.split()
                    if len(parts) >= 4:
                        source = parts[1]
                        sink = parts[2]
                        volume = float(parts[3])
                        self.router.set_volume(source, sink, volume)
                        print(f"{COLORS['GREEN']}✓{COLORS['RESET']} Volume set to {volume:.2f}")
                    else:
                        print("Usage: volume <source> <sink> <value>")
                elif cmd == 'quit' or cmd == 'exit':
                    self.running = False
                    break
                else:
                    print(f"Unknown command: {cmd}")
                    print("Type 'help' for available commands")
                    
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error: {e}")
        
        print("\nExiting interactive mode")
    
    def _show_interactive_help(self):
        """Show interactive help"""
        print(f"\n{COLORS['CYAN']}=== Available Commands ==={COLORS['RESET']}")
        print("  help                    - Show this help")
        print("  list                    - List audio devices")
        print("  status                  - Show routing status")
        print("  route <source> <sink>   - Create audio route")
        print("  unroute <source> <sink> - Remove audio route")
        print("  volume <src> <sink> <v> - Set route volume")
        print("  quit/exit               - Exit interactive mode")
        print()

# ==================== Main Entry Point ====================

def main():
    """Main entry point"""
    try:
        cli = AudioCLI()
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
