#!/usr/bin/env python3
"""
Video Processing Script for LoopForge

This script monitors the rendered_clips directory for new video files,
processes them by adding captions, making them loop seamlessly, and
applying any branding or enhancements, and saves the final videos to
the ready_to_post directory.

Features:
- Automatic looping with FFmpeg
- Caption generation with OpenAI Whisper
- B-roll injection (optional)
- Watermarking

Usage:
    python process_video.py
    python process_video.py --skip-captions
    python process_video.py --b-roll
"""

import os
import sys
import json
import time
import argparse
import subprocess
import uuid
from pathlib import Path
import logging
from datetime import datetime
import shutil
import random
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import moviepy.editor as mp
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError
from notifications import send_alert

# Add root directory to path for imports
script_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(script_path)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import notifications if available
try:
    from src.notifications import send_alert
    notifications_available = True
except ImportError:
    notifications_available = False
    logger.warning("Notifications module not available. Alerts will not be sent.")

class ConfigError(Exception):
    """Exception raised for configuration issues."""
    pass

class ProcessingError(Exception):
    """Exception raised for video processing issues."""
    pass

class ValidationError(Exception):
    """Exception raised for validation issues."""
    pass

class CaptionError(Exception):
    """Exception raised for captioning issues."""
    pass

class BRollError(Exception):
    """Exception raised for B-roll processing issues."""
    pass

class WatermarkError(Exception):
    """Exception raised for watermarking issues."""
    pass

def load_config():
    """
    Load configuration from config.json file
    
    Returns:
        dict: Configuration data
    
    Raises:
        ConfigError: If config file is missing or invalid
    """
    config_path = os.path.join(script_path, "config", "config.json")
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            logger.info("Configuration loaded successfully")
            return config
    except FileNotFoundError:
        error_msg = f"Config file not found at {config_path}"
        logger.error(error_msg)
        logger.error("Please copy config.example.json to config.json and add your API keys")
        if notifications_available:
            send_alert("LoopForge: Configuration Error", error_msg)
        sys.exit(1)
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in config file: {e}"
        logger.error(error_msg)
        if notifications_available:
            send_alert("LoopForge: Configuration Error", error_msg)
        sys.exit(1)

def validate_video_file(video_path):
    """
    Validate video file exists and has valid format
    
    Args:
        video_path (str): Path to video file
    
    Returns:
        bool: True if valid
    
    Raises:
        ValidationError: If video file is invalid
    """
    if not os.path.exists(video_path):
        raise ValidationError(f"Video file not found: {video_path}")
    
    if not os.path.isfile(video_path):
        raise ValidationError(f"Not a file: {video_path}")
    
    # Check extension
    valid_extensions = ['.mp4', '.mov', '.avi', '.webm']
    if not any(video_path.lower().endswith(ext) for ext in valid_extensions):
        raise ValidationError(f"Invalid video file extension: {video_path}")
    
    # Check if the file is actually a video using ffprobe
    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_type",
            "-of", "json",
            video_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        
        # Check if there's a video stream
        streams = data.get("streams", [])
        if not streams or streams[0].get("codec_type") != "video":
            raise ValidationError(f"File does not contain a valid video stream: {video_path}")
        
        return True
    except subprocess.CalledProcessError as e:
        raise ValidationError(f"Error validating video with ffprobe: {e}")
    except json.JSONDecodeError as e:
        raise ValidationError(f"Error parsing ffprobe output: {e}")
    except Exception as e:
        raise ValidationError(f"Unexpected error validating video: {e}")

def find_prompt_data(video_path, config):
    """
    Find the prompt data associated with a rendered video
    
    Args:
        video_path (str): Path to video file
        config (dict): Configuration data
    
    Returns:
        tuple: (prompt_data, file_path) or (None, None) if not found
    
    Raises:
        ProcessingError: If an error occurs during prompt search
    """
    video_filename = os.path.basename(video_path)
    logger.info(f"Looking for prompt data for {video_filename}")
    
    try:
        prompts_dir = os.path.join(script_path, config.get("paths", {}).get("prompts_dir", "data/prompts_to_render"))
        
        if not os.path.exists(prompts_dir):
            logger.warning(f"Prompts directory not found: {prompts_dir}")
            return None, None
        
        # Look for prompt files with matching output_path
        for filename in os.listdir(prompts_dir):
            if filename.endswith(".json"):
                file_path = os.path.join(prompts_dir, filename)
                try:
                    with open(file_path, 'r') as f:
                        prompt_data = json.load(f)
                    
                    metadata = prompt_data.get("metadata", {})
                    output_path = metadata.get("output_path", "")
                    
                    if output_path and os.path.basename(output_path) == video_filename:
                        logger.info(f"Found matching prompt data in {filename}")
                        return prompt_data, file_path
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON in prompt file {file_path}: {e}")
                except Exception as e:
                    logger.warning(f"Error reading prompt file {file_path}: {e}")
        
        logger.warning(f"No matching prompt data found for {video_filename}")
        return None, None
    except Exception as e:
        error_msg = f"Error searching for prompt data: {e}"
        logger.error(error_msg)
        raise ProcessingError(error_msg)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def generate_captions(video_path):
    """
    Generate captions for a video using OpenAI Whisper
    
    Args:
        video_path (str): Path to video file
    
    Returns:
        str: Path to SRT file or None if failed
    
    Raises:
        CaptionError: If caption generation fails
    """
    try:
        # Validate input
        validate_video_file(video_path)
        
        logger.info(f"Generating captions for {video_path}")
        
        # Create a temporary directory for output
        temp_dir = os.path.join(os.path.dirname(video_path), "temp_captions")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Output SRT file path
        srt_path = os.path.join(temp_dir, f"{os.path.splitext(os.path.basename(video_path))[0]}.srt")
        
        # Run Whisper CLI command
        cmd = [
            "whisper",
            video_path,
            "--model", "tiny",
            "--output_dir", temp_dir,
            "--output_format", "srt"
        ]
        
        logger.info(f"Running Whisper with command: {' '.join(cmd)}")
        
        try:
            # This is a slow operation, might take a while
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            logger.error(f"Whisper command failed: {e}")
            logger.error(f"STDOUT: {e.stdout}")
            logger.error(f"STDERR: {e.stderr}")
            raise CaptionError(f"Whisper command failed: {e}")
        
        # Check if SRT file was created
        if os.path.exists(srt_path):
            logger.info(f"Successfully generated captions: {srt_path}")
            return srt_path
        else:
            error_msg = f"SRT file not found at expected location: {srt_path}"
            logger.warning(error_msg)
            if notifications_available:
                send_alert("LoopForge: Caption Error", error_msg)
            return None
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        if notifications_available:
            send_alert("LoopForge: Caption Error", f"Video validation failed: {e}")
        return None
    except CaptionError as e:
        # This will be caught by the retry decorator
        logger.error(f"Caption error (will retry): {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error generating captions: {e}")
        if notifications_available:
            send_alert("LoopForge: Caption Error", f"Unexpected error: {e}")
        return None

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def create_seamless_loop(video_path, output_path):
    """
    Create a seamless loop from the video using FFmpeg
    
    Args:
        video_path (str): Path to input video
        output_path (str): Path to output video
    
    Returns:
        bool: True if successful
    
    Raises:
        ProcessingError: If loop creation fails
    """
    try:
        # Validate input
        validate_video_file(video_path)
        
        logger.info(f"Creating seamless loop for {video_path}")
        
        # Run FFmpeg command for seamless loop
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-filter_complex",
            "[0:v]reverse,fifo[r];[0:v][r] concat=n=2:v=1:a=0",
            "-c:v", "libx264",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-y",
            output_path
        ]
        
        logger.info(f"Running FFmpeg with command: {' '.join(cmd)}")
        
        try:
            # FFmpeg operations can be resource-intensive
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            logger.debug(f"FFmpeg STDOUT: {result.stdout}")
            logger.debug(f"FFmpeg STDERR: {result.stderr}")
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg command failed: {e}")
            logger.error(f"STDOUT: {e.stdout}")
            logger.error(f"STDERR: {e.stderr}")
            raise ProcessingError(f"FFmpeg command failed: {e}")
        
        # Verify the output file was created
        if not os.path.exists(output_path):
            error_msg = f"Output file not created: {output_path}"
            logger.error(error_msg)
            raise ProcessingError(error_msg)
        
        # Validate output video
        validate_video_file(output_path)
        
        logger.info(f"Successfully created seamless loop: {output_path}")
        if notifications_available:
            send_alert("LoopForge: Processing Success", f"Created seamless loop for {os.path.basename(video_path)}")
        
        return True
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        if notifications_available:
            send_alert("LoopForge: Processing Error", f"Video validation failed: {e}")
        return False
    except ProcessingError as e:
        # This will be caught by the retry decorator
        logger.error(f"Processing error (will retry): {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating seamless loop: {e}")
        if notifications_available:
            send_alert("LoopForge: Processing Error", f"Error creating seamless loop: {e}")
        return False

def add_b_roll(video_path, output_path, config):
    """
    Add random B-roll footage to the video
    
    Args:
        video_path (str): Path to input video
        output_path (str): Path to output video
        config (dict): Configuration data
    
    Returns:
        bool: True if successful
    
    Raises:
        BRollError: If B-roll addition fails
    """
    try:
        # Validate input
        validate_video_file(video_path)
        
        logger.info(f"Adding B-roll to {video_path}")
        
        # Get B-roll directory from config
        b_roll_dir = os.path.join(script_path, config.get("paths", {}).get("b_roll_dir", "assets/b_roll"))
        
        if not os.path.exists(b_roll_dir):
            error_msg = f"B-roll directory not found: {b_roll_dir}"
            logger.warning(error_msg)
            return False
        
        # Get list of B-roll clips
        b_roll_files = [f for f in os.listdir(b_roll_dir) if f.endswith((".mp4", ".mov", ".avi"))]
        
        if not b_roll_files:
            error_msg = "No B-roll clips found"
            logger.warning(error_msg)
            return False
        
        # Select a random B-roll clip
        b_roll_file = os.path.join(b_roll_dir, random.choice(b_roll_files))
        logger.info(f"Selected B-roll clip: {b_roll_file}")
        
        try:
            # Load the main video and B-roll
            logger.info("Loading video clips")
            main_clip = mp.VideoFileClip(video_path)
            b_roll_clip = mp.VideoFileClip(b_roll_file)
            
            # Resize B-roll to match main video
            logger.info(f"Resizing B-roll to match main video dimensions: {main_clip.size}")
            b_roll_clip = b_roll_clip.resize(main_clip.size)
            
            # If B-roll is too long, trim it
            if b_roll_clip.duration > main_clip.duration:
                logger.info(f"Trimming B-roll from {b_roll_clip.duration}s to {main_clip.duration}s")
                b_roll_clip = b_roll_clip.subclip(0, main_clip.duration)
            
            # Set B-roll opacity
            b_roll_opacity = config.get("video", {}).get("b_roll_opacity", 0.3)
            logger.info(f"Setting B-roll opacity to {b_roll_opacity}")
            b_roll_clip = b_roll_clip.set_opacity(b_roll_opacity)
            
            # Overlay B-roll on main video
            logger.info("Compositing video clips")
            final_clip = mp.CompositeVideoClip([main_clip, b_roll_clip])
            
            # Write output
            logger.info(f"Writing output to {output_path}")
            final_clip.write_videofile(
                output_path, 
                codec="libx264", 
                audio_codec="aac",
                logger=None  # Silence moviepy's logger which is very verbose
            )
            
            # Close clips to release resources
            logger.info("Cleaning up resources")
            main_clip.close()
            b_roll_clip.close()
            final_clip.close()
            
            logger.info(f"Successfully added B-roll: {output_path}")
            
            return True
        except Exception as e:
            error_msg = f"Error processing video with MoviePy: {e}"
            logger.error(error_msg)
            raise BRollError(error_msg)
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        if notifications_available:
            send_alert("LoopForge: B-Roll Error", f"Video validation failed: {e}")
        return False
    except BRollError as e:
        logger.error(f"B-roll error: {e}")
        if notifications_available:
            send_alert("LoopForge: B-Roll Error", f"Error adding B-roll: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error adding B-roll: {e}")
        if notifications_available:
            send_alert("LoopForge: B-Roll Error", f"Unexpected error: {e}")
        return False

def add_watermark(video_path, output_path, config):
    """
    Add watermark to the video
    
    Args:
        video_path (str): Path to input video
        output_path (str): Path to output video
        config (dict): Configuration data
    
    Returns:
        bool: True if successful
    
    Raises:
        WatermarkError: If watermarking fails
    """
    try:
        # Validate input video
        validate_video_file(video_path)
        
        logger.info(f"Adding watermark to {video_path}")
        
        video_config = config.get("video", {})
        watermark_file = video_config.get("watermark_file")
        
        if not watermark_file:
            error_msg = "No watermark file specified in config"
            logger.warning(error_msg)
            return False
        
        # Get watermark path
        branding_dir = os.path.join(script_path, config.get("paths", {}).get("branding_dir", "assets/branding"))
        watermark_path = os.path.join(branding_dir, watermark_file)
        
        if not os.path.exists(watermark_path):
            error_msg = f"Watermark file not found: {watermark_path}"
            logger.warning(error_msg)
            return False
        
        try:
            # Load the video and watermark
            logger.info("Loading video and watermark")
            video_clip = mp.VideoFileClip(video_path)
            watermark = mp.ImageClip(watermark_path)
            
            # Set watermark opacity
            watermark_opacity = video_config.get("watermark_opacity", 0.7)
            logger.info(f"Setting watermark opacity to {watermark_opacity}")
            watermark = watermark.set_opacity(watermark_opacity)
            
            # Resize watermark (e.g., to 10% of video width)
            watermark_size = video_config.get("watermark_size", 0.1)  # Default to 10% of video width
            watermark_width = video_clip.w * watermark_size
            logger.info(f"Resizing watermark to width {watermark_width:.1f}px")
            watermark = watermark.resize(width=watermark_width)
            
            # Position watermark
            watermark_position = video_config.get("watermark_position", "bottom-right")
            margin = video_config.get("watermark_margin", 10)  # Margin from the edge
            
            # Calculate position based on specified corner
            logger.info(f"Positioning watermark at {watermark_position} with margin {margin}px")
            if watermark_position == "bottom-right":
                position = (video_clip.w - watermark.w - margin, video_clip.h - watermark.h - margin)
            elif watermark_position == "bottom-left":
                position = (margin, video_clip.h - watermark.h - margin)
            elif watermark_position == "top-right":
                position = (video_clip.w - watermark.w - margin, margin)
            elif watermark_position == "top-left":
                position = (margin, margin)
            else:
                logger.warning(f"Unknown watermark position: {watermark_position}. Using bottom-right.")
                position = (video_clip.w - watermark.w - margin, video_clip.h - watermark.h - margin)
            
            # Apply position
            watermark = watermark.set_position(position)
            
            # Overlay watermark on video
            logger.info("Compositing video with watermark")
            final_clip = mp.CompositeVideoClip([video_clip, watermark])
            
            # Write output
            logger.info(f"Writing output to {output_path}")
            final_clip.write_videofile(
                output_path, 
                codec="libx264", 
                audio_codec="aac",
                logger=None  # Silence moviepy's logger
            )
            
            # Close clips to release resources
            logger.info("Cleaning up resources")
            video_clip.close()
            watermark.close()
            final_clip.close()
            
            logger.info(f"Successfully added watermark: {output_path}")
            return True
        except Exception as e:
            error_msg = f"Error processing video with MoviePy: {e}"
            logger.error(error_msg)
            raise WatermarkError(error_msg)
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        if notifications_available:
            send_alert("LoopForge: Watermark Error", f"Video validation failed: {e}")
        return False
    except WatermarkError as e:
        logger.error(f"Watermark error: {e}")
        if notifications_available:
            send_alert("LoopForge: Watermark Error", f"Error adding watermark: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error adding watermark: {e}")
        if notifications_available:
            send_alert("LoopForge: Watermark Error", f"Unexpected error: {e}")
        return False

def add_captions_to_video(video_path, captions_path, output_path):
    """Add captions to the video"""
    logger.info(f"Adding captions to {video_path}")
    
    if not captions_path:
        logger.warning("No captions file provided")
        return False
    
    try:
        # Run FFmpeg command to burn subtitles into video
        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-vf", f"subtitles={captions_path}",
            "-c:v", "libx264",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-y",
            output_path
        ]
        
        subprocess.run(cmd, check=True)
        
        return True
    except Exception as e:
        logger.error(f"Error adding captions: {e}")
        return False

def add_caption_from_prompt(video_path, prompt_data, output_path, config):
    """Add caption from prompt data to the video"""
    logger.info(f"Adding caption from prompt data to {video_path}")
    
    if not prompt_data:
        logger.warning("No prompt data provided")
        return False
    
    # Get caption from prompt data
    caption = prompt_data.get("caption", "")
    
    if not caption:
        logger.warning("No caption found in prompt data")
        return False
    
    # Get caption style from config
    video_config = config.get("video", {})
    caption_style = video_config.get("caption_style", {})
    
    try:
        # Load the video
        video_clip = mp.VideoFileClip(video_path)
        
        # Create text clip
        font = caption_style.get("font", "Arial")
        font_size = caption_style.get("font_size", 24)
        color = caption_style.get("color", "white")
        stroke_color = caption_style.get("stroke_color", "black")
        stroke_width = caption_style.get("stroke_width", 2)
        
        text_clip = mp.TextClip(
            caption,
            fontsize=font_size,
            color=color,
            stroke_color=stroke_color,
            stroke_width=stroke_width,
            font=font,
            method='caption',
            size=(video_clip.w * 0.9, None)
        )
        
        # Set duration
        text_clip = text_clip.set_duration(video_clip.duration)
        
        # Position caption
        position = caption_style.get("position", "bottom")
        margin = 20  # Margin from the edge
        
        if position == "bottom":
            text_clip = text_clip.set_position(('center', video_clip.h - text_clip.h - margin))
        elif position == "top":
            text_clip = text_clip.set_position(('center', margin))
        elif position == "center":
            text_clip = text_clip.set_position('center')
        
        # Composite video
        final_clip = mp.CompositeVideoClip([video_clip, text_clip])
        
        # Write output
        final_clip.write_videofile(output_path, codec="libx264", audio_codec="aac")
        
        # Close clips
        video_clip.close()
        text_clip.close()
        final_clip.close()
        
        return True
    except Exception as e:
        logger.error(f"Error adding caption from prompt: {e}")
        return False

class VideoHandler(FileSystemEventHandler):
    """Handler for file system events in the rendered_clips directory"""
    
    def __init__(self, config, args):
        self.config = config
        self.args = args
        self.processing_queue = []
        
        # Get paths from config
        paths = config.get("paths", {})
        self.rendered_dir = os.path.join(script_path, paths.get("rendered_dir", "data/rendered_clips"))
        self.final_dir = os.path.join(script_path, paths.get("final_dir", "data/ready_to_post"))
        
        # Ensure output directory exists
        os.makedirs(self.final_dir, exist_ok=True)
        
        # Load existing video files
        self.load_existing_videos()
    
    def load_existing_videos(self):
        """Load existing video files in the rendered_clips directory"""
        if os.path.exists(self.rendered_dir):
            for filename in os.listdir(self.rendered_dir):
                if filename.endswith((".mp4", ".mov", ".avi")):
                    file_path = os.path.join(self.rendered_dir, filename)
                    # Check if already processed
                    final_path = os.path.join(self.final_dir, filename)
                    if not os.path.exists(final_path):
                        self.processing_queue.append(file_path)
            
            logger.info(f"Loaded {len(self.processing_queue)} existing video files")
    
    def on_created(self, event):
        """Handle file creation events"""
        if not event.is_directory and event.src_path.lower().endswith((".mp4", ".mov", ".avi")):
            logger.info(f"New video file detected: {event.src_path}")
            self.processing_queue.append(event.src_path)
    
    def process_queue(self):
        """Process the video queue"""
        if not self.processing_queue:
            return
        
        logger.info(f"Processing video queue: {len(self.processing_queue)} files")
        
        for video_path in list(self.processing_queue):
            try:
                self.process_video(video_path)
                self.processing_queue.remove(video_path)
            except Exception as e:
                logger.error(f"Error processing {video_path}: {e}")
                # Move to the end of the queue to try again later
                self.processing_queue.remove(video_path)
                self.processing_queue.append(video_path)
    
    def process_video(self, video_path):
        """Process a single video file"""
        logger.info(f"Processing video file: {video_path}")
        
        # Find associated prompt data
        prompt_data, prompt_file = find_prompt_data(video_path, self.config)
        
        # Generate output path for final video
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.splitext(os.path.basename(video_path))[0]
        output_filename = f"{base_name}_processed_{timestamp}.mp4"
        output_path = os.path.join(self.final_dir, output_filename)
        
        # Create temporary directory for intermediate files
        temp_dir = os.path.join(os.path.dirname(video_path), "temp_processing")
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            # Step 1: Create seamless loop
            loop_path = os.path.join(temp_dir, f"{base_name}_loop.mp4")
            if not create_seamless_loop(video_path, loop_path):
                logger.error("Failed to create seamless loop")
                return
            
            current_path = loop_path
            
            # Step 2: Add B-roll if requested
            if self.args.b_roll or self.config.get("video", {}).get("auto_b_roll", False):
                b_roll_path = os.path.join(temp_dir, f"{base_name}_b_roll.mp4")
                if add_b_roll(current_path, b_roll_path, self.config):
                    current_path = b_roll_path
            
            # Step 3: Add captions
            if not self.args.skip_captions and self.config.get("video", {}).get("add_captions", True):
                if prompt_data and "caption" in prompt_data:
                    # Use caption from prompt data
                    caption_path = os.path.join(temp_dir, f"{base_name}_caption.mp4")
                    if add_caption_from_prompt(current_path, prompt_data, caption_path, self.config):
                        current_path = caption_path
                else:
                    # Generate captions using Whisper
                    captions_path = generate_captions(current_path)
                    if captions_path:
                        caption_path = os.path.join(temp_dir, f"{base_name}_caption.mp4")
                        if add_captions_to_video(current_path, captions_path, caption_path):
                            current_path = caption_path
            
            # Step 4: Add watermark if configured
            if self.config.get("video", {}).get("watermark", True):
                watermark_path = os.path.join(temp_dir, f"{base_name}_watermark.mp4")
                if add_watermark(current_path, watermark_path, self.config):
                    current_path = watermark_path
            
            # Step 5: Move final file to output directory
            shutil.copy(current_path, output_path)
            
            # Step 6: Create metadata file with prompt data and processing info
            metadata = {
                "original_video": os.path.basename(video_path),
                "processed_at": datetime.now().isoformat(),
                "prompt_data": prompt_data if prompt_data else {},
                "processing_steps": {
                    "seamless_loop": True,
                    "b_roll_added": self.args.b_roll or self.config.get("video", {}).get("auto_b_roll", False),
                    "captions_added": not self.args.skip_captions and self.config.get("video", {}).get("add_captions", True),
                    "watermark_added": self.config.get("video", {}).get("watermark", True)
                }
            }
            
            metadata_path = os.path.join(self.final_dir, f"{os.path.splitext(output_filename)[0]}.json")
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            # Step 7: Update prompt data status if available
            if prompt_data and prompt_file:
                prompt_data["metadata"]["status"] = "processed"
                prompt_data["metadata"]["processed_at"] = datetime.now().isoformat()
                prompt_data["metadata"]["final_path"] = output_path
                
                with open(prompt_file, 'w') as f:
                    json.dump(prompt_data, f, indent=2)
            
            logger.info(f"Successfully processed: {os.path.basename(video_path)} -> {os.path.basename(output_path)}")
            send_alert(
                "LoopForge: Video Processed",
                f"Video '{os.path.basename(video_path)}' processed and saved as '{os.path.basename(output_path)}' in ready_to_post."
            )
        except Exception as e:
            logger.error(f"Error processing video: {e}")
            raise
        finally:
            # Clean up temporary directory
            shutil.rmtree(temp_dir, ignore_errors=True)

def main():
    parser = argparse.ArgumentParser(description="LoopForge Video Processor")
    parser.add_argument("--skip-captions", action="store_true", help="Skip adding captions to videos")
    parser.add_argument("--b-roll", action="store_true", help="Add random B-roll to videos")
    args = parser.parse_args()
    
    # Load config
    config = load_config()
    
    # Create event handler
    event_handler = VideoHandler(config, args)
    
    # Start watching the rendered_clips directory
    rendered_dir = os.path.join(script_path, config.get("paths", {}).get("rendered_dir", "data/rendered_clips"))
    observer = Observer()
    observer.schedule(event_handler, rendered_dir, recursive=False)
    observer.start()
    
    logger.info(f"Started watching for rendered videos in {rendered_dir}")
    
    try:
        while True:
            # Process any queued videos
            event_handler.process_queue()
            
            # Sleep to prevent CPU overload
            time.sleep(10)
    except KeyboardInterrupt:
        observer.stop()
    
    observer.join()

if __name__ == "__main__":
    main()
