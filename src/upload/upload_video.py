#!/usr/bin/env python3
"""
Upload Script for LoopForge

This script monitors the ready_to_post directory for new video files,
uploads them to various platforms (YouTube Shorts, TikTok, etc.), and
keeps track of upload status and performance.

Usage:
    python upload_video.py
    python upload_video.py --platform youtube
    python upload_video.py --dry-run
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
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import requests
from notifications import send_alert

# Add root directory to path for imports
script_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(script_path)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_config():
    """Load configuration from config.json file"""
    config_path = os.path.join(script_path, "config", "config.json")
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Config file not found at {config_path}")
        logger.error("Please copy config.example.json to config.json and add your API keys")
        sys.exit(1)

def find_metadata(video_path):
    """Find the metadata file associated with a processed video"""
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    metadata_path = os.path.join(os.path.dirname(video_path), f"{base_name}.json")
    
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading metadata file {metadata_path}: {e}")
    
    return None

def upload_to_youtube(video_path, metadata, config, dry_run=False):
    """Upload video to YouTube Shorts"""
    logger.info(f"Uploading to YouTube: {video_path}")
    
    if dry_run:
        logger.info("DRY RUN: Would upload to YouTube")
        return {
            "platform": "youtube",
            "success": True,
            "video_id": "dryrun_" + str(uuid.uuid4()),
            "url": "https://youtube.com/shorts/dryrun",
            "timestamp": datetime.now().isoformat()
        }
    
    # Get YouTube API credentials
    youtube_config = config.get("api_keys", {}).get("youtube", {})
    client_id = youtube_config.get("client_id")
    client_secret = youtube_config.get("client_secret")
    refresh_token = youtube_config.get("refresh_token")
    
    if not all([client_id, client_secret, refresh_token]):
        logger.error("Missing YouTube API credentials")
        return {
            "platform": "youtube",
            "success": False,
            "error": "Missing YouTube API credentials",
            "timestamp": datetime.now().isoformat()
        }
    
    # Get video metadata
    prompt_data = metadata.get("prompt_data", {})
    caption = prompt_data.get("caption", "LoopForge Generated Video")
    hashtags = prompt_data.get("hashtags", [])
    
    # Format description with hashtags and affiliate disclosure
    hashtag_str = " ".join([f"#{tag}" for tag in hashtags])
    compliance = config.get("compliance", {})
    affiliate_disclaimer = compliance.get("affiliate_disclaimer", "")
    
    description = f"{caption}\n\n{hashtag_str}\n\n{affiliate_disclaimer}"
    
    # Get upload configuration
    upload_config = config.get("upload", {})
    category = upload_config.get("youtube_category", "22")  # 22 = People & Blogs
    privacy = upload_config.get("privacy_status", "public")
    
    try:
        # Run yt-upload command
        cmd = [
            "yt-upload",
            "--client-id", client_id,
            "--client-secret", client_secret,
            "--refresh-token", refresh_token,
            "--title", caption,
            "--description", description,
            "--category", category,
            "--privacy", privacy,
            "--tags", ",".join(hashtags),
            video_path
        ]
        
        # Add option for shorts
        cmd.extend(["--shorts"])
        
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Extract video ID from output
        for line in result.stdout.splitlines():
            if "Video ID" in line:
                video_id = line.split(":")[-1].strip()
                return {
                    "platform": "youtube",
                    "success": True,
                    "video_id": video_id,
                    "url": f"https://youtube.com/shorts/{video_id}",
                    "timestamp": datetime.now().isoformat()
                }
        
        logger.warning("Could not extract video ID from output")
        return {
            "platform": "youtube",
            "success": True,
            "video_id": "unknown",
            "url": "https://youtube.com/shorts/",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error uploading to YouTube: {e}")
        return {
            "platform": "youtube",
            "success": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

def upload_to_tiktok(video_path, metadata, config, dry_run=False):
    """Upload video to TikTok"""
    logger.info(f"Uploading to TikTok: {video_path}")
    
    if dry_run:
        logger.info("DRY RUN: Would upload to TikTok")
        return {
            "platform": "tiktok",
            "success": True,
            "video_id": "dryrun_" + str(uuid.uuid4()),
            "url": "https://tiktok.com/@user/video/dryrun",
            "timestamp": datetime.now().isoformat()
        }
    
    # NOTE: TikTok doesn't have an official API for video uploads
    # This is a placeholder for future implementation
    # For now, we'll just return a mock success response
    
    logger.warning("TikTok upload API not implemented - manual upload required")
    return {
        "platform": "tiktok",
        "success": False,
        "error": "TikTok upload API not implemented - manual upload required",
        "timestamp": datetime.now().isoformat(),
        "manual_required": True
    }

class UploadHandler(FileSystemEventHandler):
    """Handler for file system events in the ready_to_post directory"""
    
    def __init__(self, config, args):
        self.config = config
        self.args = args
        self.upload_queue = []
        
        # Get paths from config
        paths = config.get("paths", {})
        self.final_dir = os.path.join(script_path, paths.get("final_dir", "data/ready_to_post"))
        
        # Create uploads tracking directory
        self.uploads_dir = os.path.join(script_path, "data", "uploads")
        os.makedirs(self.uploads_dir, exist_ok=True)
        
        # Load existing video files
        self.load_existing_videos()
    
    def load_existing_videos(self):
        """Load existing video files in the ready_to_post directory"""
        if os.path.exists(self.final_dir):
            for filename in os.listdir(self.final_dir):
                if filename.endswith((".mp4", ".mov", ".avi")):
                    file_path = os.path.join(self.final_dir, filename)
                    
                    # Check if already uploaded by looking for upload record
                    base_name = os.path.splitext(filename)[0]
                    upload_record = os.path.join(self.uploads_dir, f"{base_name}_uploads.json")
                    
                    if not os.path.exists(upload_record):
                        self.upload_queue.append(file_path)
            
            logger.info(f"Loaded {len(self.upload_queue)} existing video files for upload")
    
    def on_created(self, event):
        """Handle file creation events"""
        if not event.is_directory and event.src_path.lower().endswith((".mp4", ".mov", ".avi")):
            logger.info(f"New video file detected for upload: {event.src_path}")
            self.upload_queue.append(event.src_path)
    
    def process_queue(self):
        """Process the upload queue"""
        if not self.upload_queue:
            return
        
        logger.info(f"Processing upload queue: {len(self.upload_queue)} files")
        
        for video_path in list(self.upload_queue):
            try:
                self.upload_video(video_path)
                self.upload_queue.remove(video_path)
            except Exception as e:
                logger.error(f"Error uploading {video_path}: {e}")
                # Move to the end of the queue to try again later
                self.upload_queue.remove(video_path)
                self.upload_queue.append(video_path)
    
    def upload_video(self, video_path):
        """Upload a single video to all configured platforms"""
        logger.info(f"Uploading video: {video_path}")
        
        # Find associated metadata
        metadata = find_metadata(video_path)
        if not metadata:
            logger.warning(f"No metadata found for {video_path}, using defaults")
            metadata = {
                "prompt_data": {
                    "caption": os.path.splitext(os.path.basename(video_path))[0],
                    "hashtags": ["loopforge", "aiart", "aianimation"]
                }
            }
        
        # Get upload configuration
        platforms = self.args.platform
        if not platforms:
            platforms = self.config.get("upload", {}).get("platforms", ["youtube"])
        
        if isinstance(platforms, str):
            platforms = [platforms]
        
        # Track upload results
        upload_results = []
        
        # Upload to each platform
        for platform in platforms:
            result = None
            
            if platform.lower() == "youtube":
                result = upload_to_youtube(video_path, metadata, self.config, self.args.dry_run)
            elif platform.lower() == "tiktok":
                result = upload_to_tiktok(video_path, metadata, self.config, self.args.dry_run)
            else:
                logger.warning(f"Unknown platform: {platform}")
                continue
            
            if result:
                upload_results.append(result)
                logger.info(f"Upload to {platform} {'would be ' if self.args.dry_run else ''}{'successful' if result.get('success') else 'failed'}")
                if result.get('success') and not self.args.dry_run:
                    send_alert(
                        f"LoopForge: Video Uploaded to {platform.title()}",
                        f"Video '{os.path.basename(video_path)}' uploaded to {platform.title()} successfully. URL: {result.get('url', 'N/A')}"
                    )
        
        # Save upload results
        if upload_results:
            base_name = os.path.splitext(os.path.basename(video_path))[0]
            upload_record = os.path.join(self.uploads_dir, f"{base_name}_uploads.json")
            
            with open(upload_record, 'w') as f:
                json.dump({
                    "video_path": video_path,
                    "uploads": upload_results,
                    "timestamp": datetime.now().isoformat()
                }, f, indent=2)
            
            logger.info(f"Saved upload record to {upload_record}")

def main():
    parser = argparse.ArgumentParser(description="LoopForge Video Uploader")
    parser.add_argument("--platform", type=str, nargs="+", choices=["youtube", "tiktok"], 
                        help="Platforms to upload to (default: from config)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate uploads without actually uploading")
    args = parser.parse_args()
    
    # Load config
    config = load_config()
    
    # Create event handler
    event_handler = UploadHandler(config, args)
    
    # Start watching the ready_to_post directory
    final_dir = os.path.join(script_path, config.get("paths", {}).get("final_dir", "data/ready_to_post"))
    observer = Observer()
    observer.schedule(event_handler, final_dir, recursive=False)
    observer.start()
    
    logger.info(f"Started watching for processed videos in {final_dir}")
    
    try:
        while True:
            # Process any queued videos
            event_handler.process_queue()
            
            # Sleep to prevent CPU overload
            time.sleep(30)  # Longer sleep time for uploads
    except KeyboardInterrupt:
        observer.stop()
    
    observer.join()

if __name__ == "__main__":
    main()
