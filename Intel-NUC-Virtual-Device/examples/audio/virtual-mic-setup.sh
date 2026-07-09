#!/bin/bash
# virtual-mic-setup.sh - Virtual Microphone and Audio Device Setup
#
# This script creates and manages virtual audio devices including
# virtual microphones, speakers, and audio routing on Intel NUC platforms.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
SINK_NAME="virtual_sink"
SOURCE_NAME="virtual_source"
LOOPBACK_NAME="virtual_loopback"
SAMPLE_RATE=48000
CHANNELS=2
FORMAT="s16le"

# Function to check if running as root
check_root() {
    if [ "$EUID" -ne 0 ]; then 
        echo -e "${RED}✗${NC} Please run as root"
        exit 1
    fi
}

# Function to check if PulseAudio is running
check_pulseaudio() {
    if ! pgrep -x "pulseaudio" > /dev/null; then
        echo -e "${YELLOW}⚠${NC} PulseAudio not running"
        echo -e "${BLUE}→${NC} Starting PulseAudio..."
        pulseaudio --start
        sleep 2
    fi
    echo -e "${GREEN}✓${NC} PulseAudio is running"
}

# Function to check if PipeWire is running
check_pipewire() {
    if ! pgrep -x "pipewire" > /dev/null; then
        echo -e "${YELLOW}⚠${NC} PipeWire not running"
        echo -e "${BLUE}→${NC} Starting PipeWire..."
        systemctl --user start pipewire pipewire-pulse
        sleep 2
    fi
    echo -e "${GREEN}✓${NC} PipeWire is running"
}

# Function to create virtual sink
create_virtual_sink() {
    local name=${1:-$SINK_NAME}
    local description=${2:-"Virtual Audio Sink"}
    
    echo -e "${BLUE}→${NC} Creating virtual sink: $name"
    
    # Create null sink
    pactl load-module module-null-sink \
        sink_name="$name" \
        sink_properties=device.description="$description" \
        rate=$SAMPLE_RATE \
        channels=$CHANNELS \
        format=$FORMAT
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} Virtual sink created: $name"
        echo -e "${GREEN}✓${NC} Description: $description"
        
        # Show sink info
        pactl list short sinks | grep "$name"
        return 0
    else
        echo -e "${RED}✗${NC} Failed to create virtual sink"
        return 1
    fi
}

# Function to create virtual source
create_virtual_source() {
    local name=${1:-$SOURCE_NAME}
    local description=${2:-"Virtual Microphone"}
    
    echo -e "${BLUE}→${NC} Creating virtual source: $name"
    
    # Create null source
    pactl load-module module-null-source \
        source_name="$name" \
        source_properties=device.description="$description" \
        rate=$SAMPLE_RATE \
        channels=$CHANNELS \
        format=$FORMAT
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} Virtual source created: $name"
        echo -e "${GREEN}✓${NC} Description: $description"
        
        # Show source info
        pactl list short sources | grep "$name"
        return 0
    else
        echo -e "${RED}✗${NC} Failed to create virtual source"
        return 1
    fi
}

# Function to create loopback
create_loopback() {
    local source=$1
    local sink=$2
    local name=${3:-$LOOPBACK_NAME}
    
    echo -e "${BLUE}→${NC} Creating loopback: $source -> $sink"
    
    pactl load-module module-loopback \
        source="$source" \
        sink="$sink" \
        rate=$SAMPLE_RATE \
        channels=$CHANNELS \
        latency_msec=100
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} Loopback created: $source -> $sink"
        return 0
    else
        echo -e "${RED}✗${NC} Failed to create loopback"
        return 1
    fi
}

# Function to setup virtual microphone
setup_virtual_mic() {
    local mic_name=${1:-"virtual_mic"}
    local description=${2:-"Virtual Microphone"}
    
    echo -e "${CYAN}=== Setting up Virtual Microphone ===${NC}"
    
    # Create virtual source
    create_virtual_source "$mic_name" "$description"
    
    # Create loopback from system audio to virtual mic
    local system_sink=$(pactl info | grep "Default Sink" | awk '{print $3}')
    if [ -n "$system_sink" ]; then
        create_loopback "$system_sink.monitor" "$mic_name"
        echo -e "${GREEN}✓${NC} System audio routed to virtual microphone"
    fi
    
    echo -e "\n${GREEN}✓${NC} Virtual microphone setup complete"
    echo -e "${BLUE}→${NC} Virtual mic available as: $mic_name"
    echo -e "${BLUE}→${NC} Use in applications that need audio input"
}

# Function to setup virtual speaker
setup_virtual_speaker() {
    local speaker_name=${1:-"virtual_speaker"}
    local description=${2:-"Virtual Speaker"}
    
    echo -e "${CYAN}=== Setting up Virtual Speaker ===${NC}"
    
    # Create virtual sink
    create_virtual_sink "$speaker_name" "$description"
    
    # Create loopback from virtual speaker to system output
    local system_sink=$(pactl info | grep "Default Sink" | awk '{print $3}')
    if [ -n "$system_sink" ]; then
        create_loopback "$speaker_name.monitor" "$system_sink"
        echo -e "${GREEN}✓${NC} Virtual speaker routed to system output"
    fi
    
    echo -e "\n${GREEN}✓${NC} Virtual speaker setup complete"
    echo -e "${BLUE}→${NC} Virtual speaker available as: $speaker_name"
}

# Function to setup audio bridge
setup_audio_bridge() {
    local bridge_name=${1:-"audio_bridge"}
    
    echo -e "${CYAN}=== Setting up Audio Bridge ===${NC}"
    
    # Create sink
    create_virtual_sink "${bridge_name}_sink" "Audio Bridge Sink"
    
    # Create source
    create_virtual_source "${bridge_name}_source" "Audio Bridge Source"
    
    # Create loopback between sink and source
    create_loopback "${bridge_name}_sink.monitor" "${bridge_name}_source"
    
    echo -e "\n${GREEN}✓${NC} Audio bridge setup complete"
    echo -e "${BLUE}→${NC} Bridge available: ${bridge_name}_sink <-> ${bridge_name}_source"
}

# Function to setup audio recording
setup_audio_recording() {
    local record_name=${1:-"record_mic"}
    
    echo -e "${CYAN}=== Setting up Audio Recording ===${NC}"
    
    # Create recording source
    create_virtual_source "$record_name" "Recording Source"
    
    # Create loopback for recording
    local system_source=$(pactl info | grep "Default Source" | awk '{print $3}')
    if [ -n "$system_source" ]; then
        create_loopback "$system_source" "$record_name"
        echo -e "${GREEN}✓${NC} System audio routed to recording source"
    fi
    
    echo -e "\n${GREEN}✓${NC} Audio recording setup complete"
    echo -e "${BLUE}→${NC} Recording source: $record_name"
}

# Function to setup audio effects
setup_audio_effects() {
    local effect_name=${1:-"effects"}
    
    echo -e "${CYAN}=== Setting up Audio Effects Pipeline ===${NC}"
    
    # Create effect sink
    create_virtual_sink "${effect_name}_sink" "Audio Effects Sink"
    
    # Create effect source
    create_virtual_source "${effect_name}_source" "Audio Effects Source"
    
    # Create loopback with effects
    create_loopback "${effect_name}_sink.monitor" "${effect_name}_source"
    
    # Apply equalizer if available
    if command -v pulseaudio-equalizer &> /dev/null; then
        echo -e "${BLUE}→${NC} Applying equalizer..."
        pulseaudio-equalizer --apply "${effect_name}_sink"
    fi
    
    echo -e "\n${GREEN}✓${NC} Audio effects pipeline setup complete"
}

# Function to show status
show_status() {
    echo -e "\n${CYAN}=== Virtual Audio Devices Status ===${NC}"
    echo ""
    
    # Show sinks
    echo -e "${BLUE}Audio Sinks:${NC}"
    pactl list short sinks | grep -E "virtual|loopback" || echo "  No virtual sinks"
    echo ""
    
    # Show sources
    echo -e "${BLUE}Audio Sources:${NC}"
    pactl list short sources | grep -E "virtual|loopback" || echo "  No virtual sources"
    echo ""
    
    # Show modules
    echo -e "${BLUE}Loaded Modules:${NC}"
    pactl list short modules | grep -E "null-sink|null-source|loopback" | head -10
    echo ""
    
    # Show default devices
    echo -e "${BLUE}Default Devices:${NC}"
    echo "  Default Sink: $(pactl info | grep 'Default Sink' | awk '{print $3}')"
    echo "  Default Source: $(pactl info | grep 'Default Source' | awk '{print $3}')"
    echo ""
    
    # Show volume
    echo -e "${BLUE}Master Volume:${NC}"
    pactl list sinks | grep -A 10 "State: RUNNING" | grep "Volume:" | head -1
}

# Function to record audio
record_audio() {
    local duration=${1:-10}
    local output_file=${2:-"recording.wav"}
    local source=${3:-$SOURCE_NAME}
    
    echo -e "${BLUE}→${NC} Recording audio for $duration seconds..."
    echo -e "${BLUE}→${NC} Source: $source"
    echo -e "${BLUE}→${NC} Output: $output_file"
    
    parecord -d "$source" --file-format=wav --duration=$duration "$output_file"
    
    if [ $? -eq 0 ] && [ -f "$output_file" ]; then
        local size=$(du -h "$output_file" | cut -f1)
        echo -e "${GREEN}✓${NC} Recording complete: $output_file ($size)"
    else
        echo -e "${RED}✗${NC} Recording failed"
        return 1
    fi
}

# Function to play audio
play_audio() {
    local input_file=${1:-"recording.wav"}
    local sink=${2:-$SINK_NAME}
    
    if [ ! -f "$input_file" ]; then
        echo -e "${RED}✗${NC} File not found: $input_file"
        return 1
    fi
    
    echo -e "${BLUE}→${NC} Playing audio: $input_file"
    echo -e "${BLUE}→${NC} Sink: $sink"
    
    paplay -d "$sink" "$input_file"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} Playback complete"
    else
        echo -e "${RED}✗${NC} Playback failed"
        return 1
    fi
}

# Function to test microphone
test_microphone() {
    local source=${1:-$SOURCE_NAME}
    
    echo -e "${BLUE}→${NC} Testing microphone: $source"
    echo -e "${BLUE}→${NC} Speaking test for 5 seconds..."
    
    # Record test
    parecord -d "$source" --file-format=wav --duration=5 /tmp/mic-test.wav
    
    if [ -f /tmp/mic-test.wav ]; then
        local size=$(du -h /tmp/mic-test.wav | cut -f1)
        echo -e "${GREEN}✓${NC} Recording test complete: $size"
        
        # Play back test
        echo -e "${BLUE}→${NC} Playing back recording..."
        paplay /tmp/mic-test.wav
        
        rm /tmp/mic-test.wav
    else
        echo -e "${RED}✗${NC} Microphone test failed"
        return 1
    fi
}

# Function to cleanup
cleanup() {
    echo -e "${BLUE}→${NC} Cleaning up virtual audio devices..."
    
    # Find and unload virtual modules
    for module in $(pactl list short modules | grep -E "null-sink|null-source|loopback" | awk '{print $1}'); do
        echo -e "${BLUE}→${NC} Unloading module: $module"
        pactl unload-module "$module" 2>/dev/null || true
    done
    
    echo -e "${GREEN}✓${NC} Cleanup complete"
}

# Function to show usage
show_usage() {
    cat << EOF
${CYAN}Virtual Audio Device Setup Script${NC}

Usage: $0 <command> [options]

Commands:
  ${GREEN}mic${NC} [name] [description]   - Setup virtual microphone
  ${GREEN}speaker${NC} [name] [desc]     - Setup virtual speaker
  ${GREEN}bridge${NC} [name]             - Setup audio bridge
  ${GREEN}record${NC} [name]             - Setup recording source
  ${GREEN}effects${NC} [name]            - Setup audio effects pipeline
  ${GREEN}status${NC}                    - Show current status
  ${GREEN}record-audio${NC} [duration]   - Record audio
  ${GREEN}play-audio${NC} <file>         - Play audio file
  ${GREEN}test-mic${NC} [source]         - Test microphone
  ${GREEN}cleanup${NC}                   - Clean up virtual devices
  ${GREEN}help${NC}                      - Show this help

Examples:
  ${BLUE}# Setup virtual microphone${NC}
  $0 mic
  
  ${BLUE}# Setup virtual speaker${NC}
  $0 speaker
  
  ${BLUE}# Setup audio bridge${NC}
  $0 bridge mybridge
  
  ${BLUE}# Record 10 seconds of audio${NC}
  $0 record-audio 10
  
  ${BLUE}# Test microphone${NC}
  $0 test-mic

EOF
}

# Main function
main() {
    # Check for root
    check_root
    
    # Check audio system
    if command -v pulseaudio &> /dev/null; then
        check_pulseaudio
        AUDIO_SYSTEM="pulseaudio"
    elif command -v pipewire &> /dev/null; then
        check_pipewire
        AUDIO_SYSTEM="pipewire"
    else
        echo -e "${RED}✗${NC} No audio system found (PulseAudio or PipeWire required)"
        exit 1
    fi
    
    # Parse command
    case $1 in
        mic)
            setup_virtual_mic "${2:-$SOURCE_NAME}" "${3:-Virtual Microphone}"
            ;;
        
        speaker)
            setup_virtual_speaker "${2:-$SINK_NAME}" "${3:-Virtual Speaker}"
            ;;
        
        bridge)
            setup_audio_bridge "${2:-audio_bridge}"
            ;;
        
        record)
            setup_audio_recording "${2:-record_mic}"
            ;;
        
        effects)
            setup_audio_effects "${2:-effects}"
            ;;
        
        status)
            show_status
            ;;
        
        record-audio)
            duration=${2:-10}
            output=${3:-"recording_$(date +%Y%m%d_%H%M%S).wav"}
            record_audio "$duration" "$output"
            ;;
        
        play-audio)
            if [ -z "$2" ]; then
                echo -e "${RED}✗${NC} Please specify audio file"
                return 1
            fi
            play_audio "$2" "${3:-$SINK_NAME}"
            ;;
        
        test-mic)
            test_microphone "${2:-$SOURCE_NAME}"
            ;;
        
        cleanup)
            cleanup
            ;;
        
        help|--help|-h)
            show_usage
            ;;
        
        *)
            echo -e "${RED}✗${NC} Unknown command: $1"
            show_usage
            exit 1
            ;;
    esac
}

# Trap signals
trap cleanup EXIT INT TERM

# Execute main
main "$@"
