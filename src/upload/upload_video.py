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
from tenacity import retry, stop_after_attempt, wait_exponential, RetryError

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

class ValidationError(Exception):
    """Exception raised for validation issues."""
    pass

class UploadError(Exception):
    """Base exception for upload errors."""
    pass

class YouTubeUploadError(UploadError):
    """Exception raised for YouTube upload issues."""
    pass

class TikTokUploadError(UploadError):
    """Exception raised for TikTok upload issues."""
    pass

class MetadataError(Exception):
    """Exception raised for metadata-related issues."""
    pass

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
    
    # Check if the file is empty
    if os.path.getsize(video_path) == 0:
        raise ValidationError(f"Video file is empty: {video_path}")
    
    return True

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

def validate_upload_credentials(config, platform):
    """
    Validate upload credentials for a specific platform
    
    Args:
        config (dict): Configuration data
        platform (str): Platform name ("youtube", "tiktok")
    
    Returns:
        bool: True if valid
    
    Raises:
        ConfigError: If credentials are missing or invalid
    """
    if platform == "youtube":
        youtube_config = config.get("api_keys", {}).get("youtube", {})
        client_id = youtube_config.get("client_id")
        client_secret = youtube_config.get("client_secret")
        refresh_token = youtube_config.get("refresh_token")
        
        if not all([client_id, client_secret, refresh_token]):
            missing = []
            if not client_id: missing.append("client_id")
            if not client_secret: missing.append("client_secret")
            if not refresh_token: missing.append("refresh_token")
            
            raise ConfigError(f"Missing YouTube API credentials: {', '.join(missing)}")
        
        return True
    
    elif platform == "tiktok":
        # For future implementation
        return True
    
    else:
        raise ConfigError(f"Unknown platform: {platform}")

def find_metadata(video_path):
    """
    Find the metadata file associated with a processed video
    
    Args:
        video_path (str): Path to video file
    
    Returns:
        dict: Metadata dictionary or None if not found
    
    Raises:
        MetadataError: If metadata file exists but is invalid
    """
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    metadata_path = os.path.join(os.path.dirname(video_path), f"{base_name}.json")
    
    logger.info(f"Looking for metadata at {metadata_path}")
    
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
                logger.info(f"Found metadata for {os.path.basename(video_path)}")
                return metadata
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in metadata file {metadata_path}: {e}"
            logger.error(error_msg)
            raise MetadataError(error_msg)
        except Exception as e:
            error_msg = f"Error reading metadata file {metadata_path}: {e}"
            logger.error(error_msg)
            raise MetadataError(error_msg)
    else:
        logger.warning(f"No metadata file found at {metadata_path}")
        return None

def validate_metadata(metadata):
    """
    Validate metadata structure and contents
    
    Args:
        metadata (dict): Metadata to validate
    
    Returns:
        bool: True if valid
    
    Raises:
        ValidationError: If metadata is invalid
    """
    if not isinstance(metadata, dict):
        raise ValidationError("Metadata must be a dictionary")
    
    # Check for prompt_data
    prompt_data = metadata.get("prompt_data", {})
    if not isinstance(prompt_data, dict):
        raise ValidationError("prompt_data must be a dictionary")
    
    # Check for minimum required fields
    if "original_video" not in metadata:
        logger.warning("Metadata missing 'original_video' field")
    
    if "processed_at" not in metadata:
        logger.warning("Metadata missing 'processed_at' field")
    
    return True

def verify_youtube_upload(video_id, config, retry_count=3):
    """
    Verify that a YouTube video was successfully uploaded and is available
    
    Args:
        video_id (str): YouTube video ID
        config (dict): Configuration data
        retry_count (int): Number of times to retry the verification
        
    Returns:
        bool: True if video is available, False otherwise
    """
    if video_id == "unknown" or not video_id:
        logger.warning("Cannot verify upload with unknown video ID")
        return False
    
    if video_id.startswith("dryrun_"):
        logger.info("Dry run upload, skipping verification")
        return True
    
    # Get YouTube API credentials
    youtube_config = config.get("api_keys", {}).get("youtube", {})
    client_id = youtube_config.get("client_id")
    client_secret = youtube_config.get("client_secret")
    refresh_token = youtube_config.get("refresh_token")
    
    # Use yt-upload to check video status
    cmd = [
        "yt-upload",
        "--client-id", client_id,
        "--client-secret", client_secret,
        "--refresh-token", refresh_token,
        "--check-status", video_id
    ]
    
    for attempt in range(retry_count):
        try:
            logger.info(f"Verifying YouTube upload for video ID {video_id} (attempt {attempt+1}/{retry_count})")
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=60)
            
            # Parse the output to check status
            if "status: available" in result.stdout.lower():
                logger.info(f"Video ID {video_id} is available on YouTube")
                return True
            elif "status: processing" in result.stdout.lower():
                logger.info(f"Video ID {video_id} is still processing on YouTube")
                # If this is not the last attempt, wait before retrying
                if attempt < retry_count - 1:
                    time.sleep(60)  # Wait 1 minute before checking again
            elif "status: deleted" in result.stdout.lower() or "status: rejected" in result.stdout.lower():
                logger.error(f"Video ID {video_id} was deleted or rejected by YouTube")
                return False
            else:
                logger.warning(f"Unknown status for video ID {video_id}: {result.stdout}")
                # If this is not the last attempt, wait before retrying
                if attempt < retry_count - 1:
                    time.sleep(30)
        except Exception as e:
            logger.error(f"Error verifying YouTube upload for video ID {video_id}: {e}")
            # If this is not the last attempt, wait before retrying
            if attempt < retry_count - 1:
                time.sleep(30)
    
    # If we get here, we've exhausted all retries
    logger.warning(f"Could not verify YouTube upload status for video ID {video_id} after {retry_count} attempts")
    return False

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def upload_to_youtube(video_path, metadata, config, dry_run=False):
    """
    Upload video to YouTube Shorts
    
    Args:
        video_path (str): Path to video file
        metadata (dict): Video metadata
        config (dict): Configuration data
        dry_run (bool): If True, simulate upload without actually uploading
    
    Returns:
        dict: Upload result data
    
    Raises:
        YouTubeUploadError: If upload fails
        ValidationError: If video file is invalid
        ConfigError: If YouTube credentials are invalid
    """
    try:
        # Validate inputs
        validate_video_file(video_path)
        validate_metadata(metadata)
        validate_upload_credentials(config, "youtube")
        
        logger.info(f"Uploading to YouTube: {os.path.basename(video_path)}")
        
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
        
        # Ensure title complies with YouTube's character limits
        if len(caption) > 100:
            logger.warning(f"Title exceeds YouTube's 100 character limit, truncating: {caption}")
            caption = caption[:97] + "..."
            
        # Ensure description is not too long
        if len(description) > 5000:
            logger.warning(f"Description exceeds YouTube's 5000 character limit, truncating")
            description = description[:4997] + "..."
            
        # Validate tags (YouTube allows up to 500 characters total for tags)
        tag_limit = upload_config.get("tags_per_video", 10)
        if len(hashtags) > tag_limit:
            logger.warning(f"Too many hashtags ({len(hashtags)}), limiting to {tag_limit}")
            hashtags = hashtags[:tag_limit]
            
        # Check total tag character length
        tags_str = ",".join(hashtags)
        if len(tags_str) > 500:
            logger.warning("Tags exceed YouTube's 500 character limit, truncating")
            # Keep removing tags until under limit
            while len(tags_str) > 500 and hashtags:
                hashtags.pop()
                tags_str = ",".join(hashtags)
        
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
            "--tags", tags_str,
            video_path
        ]
        
        # Add option for shorts
        cmd.extend(["--shorts"])
        
        # Check if we want to schedule the upload
        if upload_config.get("schedule", False):
            schedule_time = datetime.now() + datetime.timedelta(days=1)  # Schedule for tomorrow
            schedule_str = schedule_time.strftime("%Y-%m-%dT%H:%M:%S")
            cmd.extend(["--publishAt", schedule_str])
            logger.info(f"Scheduling upload for {schedule_str}")
        
        logger.info(f"Running upload command: yt-upload (...credentials omitted...) --title \"{caption}\" --tags \"{tags_str}\" --shorts {os.path.basename(video_path)}")
        
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=300)  # 5 minute timeout
            logger.debug(f"Upload output: {result.stdout}")
            
            # Extract video ID from output
            video_id = None
            for line in result.stdout.splitlines():
                if "Video ID" in line:
                    video_id = line.split(":")[-1].strip()
                    break
            
            if not video_id:
                logger.warning("Could not extract video ID from output")
                video_id = "unknown"
            
            # Validate the video ID format (YouTube IDs are typically 11 characters)
            if video_id != "unknown" and (len(video_id) < 8 or len(video_id) > 15):
                logger.warning(f"Unusual video ID format: {video_id}, may indicate an issue")
            
            logger.info(f"Successfully uploaded video to YouTube with ID: {video_id}")
            
            # Verify the upload was successful and the video is available
            verification_result = False
            if video_id != "unknown":
                logger.info("Verifying YouTube video availability...")
                verification_result = verify_youtube_upload(video_id, config)
                if verification_result:
                    logger.info(f"Verified that video ID {video_id} is available on YouTube")
                else:
                    logger.warning(f"Could not verify that video ID {video_id} is available on YouTube")
            
            if notifications_available:
                status_msg = "Video should be available soon" if not verification_result else "Video is available now"
                send_alert(
                    "LoopForge: YouTube Upload Success", 
                    f"Successfully uploaded {os.path.basename(video_path)} to YouTube Shorts: https://youtube.com/shorts/{video_id}\n{status_msg}"
                )
            
            # Save additional metadata about the upload
            result_data = {
                "platform": "youtube",
                "success": True,
                "video_id": video_id,
                "url": f"https://youtube.com/shorts/{video_id}",
                "timestamp": datetime.now().isoformat(),
                "title": caption,
                "description_length": len(description),
                "tags": hashtags,
                "category": category,
                "privacy": privacy,
                "file_size_bytes": os.path.getsize(video_path),
                "verified": verification_result
            }
            
            return result_data
            
        except subprocess.TimeoutExpired as e:
            error_msg = f"YouTube upload command timed out after 300 seconds"
            logger.error(error_msg)
            raise YouTubeUploadError(error_msg)
            
        except subprocess.CalledProcessError as e:
            # Check for common error patterns in the stderr output
            stderr = e.stderr.lower() if e.stderr else ""
            
            if "quota" in stderr or "rate limit" in stderr:
                error_msg = f"YouTube API quota exceeded or rate limited: {e.stderr}"
                logger.error(error_msg)
                raise YouTubeUploadError(error_msg + " (API quota/rate limit)")
            
            elif "token" in stderr and ("expired" in stderr or "invalid" in stderr):
                error_msg = f"YouTube API token invalid or expired: {e.stderr}"
                logger.error(error_msg)
                try:
                    # Attempt to refresh the token
                    logger.info("Attempting to refresh the YouTube API token")
                    refresh_cmd = [
                        "yt-upload",
                        "--client-id", client_id,
                        "--client-secret", client_secret,
                        "--refresh-token", refresh_token,
                        "--refresh-only"
                    ]
                    refresh_result = subprocess.run(refresh_cmd, check=True, capture_output=True, text=True)
                    logger.info("Token refresh successful, retrying upload")
                    
                    # Token refreshed, raise error to trigger retry
                    raise YouTubeUploadError("Token refreshed, retrying upload")
                except Exception as refresh_error:
                    logger.error(f"Token refresh failed: {refresh_error}")
                    raise YouTubeUploadError(f"YouTube token refresh failed: {refresh_error}")
            
            elif "file format" in stderr or "invalid file" in stderr:
                error_msg = f"YouTube rejected the video file format: {e.stderr}"
                logger.error(error_msg)
                raise YouTubeUploadError(error_msg + " (invalid file format)")
            
            else:
                error_msg = f"YouTube upload command failed: {e}\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}"
                logger.error(error_msg)
                raise YouTubeUploadError(error_msg)
                
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        if notifications_available:
            send_alert("LoopForge: YouTube Upload Error", f"Video validation failed: {e}")
        return {
            "platform": "youtube",
            "success": False,
            "error": f"Validation error: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        if notifications_available:
            send_alert("LoopForge: YouTube Upload Error", f"Configuration error: {e}")
        return {
            "platform": "youtube",
            "success": False,
            "error": f"Configuration error: {str(e)}",
            "timestamp": datetime.now().isoformat()
        }
    except YouTubeUploadError as e:
        # This will be caught by the retry decorator
        logger.error(f"YouTube upload error (will retry): {e}")
        raise
    except RetryError as e:
        logger.error(f"YouTube upload failed after all retry attempts: {e}")
        if notifications_available:
            send_alert("LoopForge: YouTube Upload Failed", f"Upload for {os.path.basename(video_path)} failed after multiple retry attempts: {e}")
        return {
            "platform": "youtube",
            "success": False,
            "error": f"Retry error: {str(e)}",
            "timestamp": datetime.now().isoformat(),
            "retry_count": 3
        }
    except Exception as e:
        logger.error(f"Unexpected error uploading to YouTube: {e}")
        if notifications_available:
            send_alert("LoopForge: YouTube Upload Error", f"Unexpected error: {e}")
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

def update_upload_stats(video_path, result, uploads_dir):
    """
    Update upload statistics and track upload history
    
    Args:
        video_path (str): Path to the uploaded video
        result (dict): Upload result data
        uploads_dir (str): Directory to store upload statistics
        
    Returns:
        dict: Combined upload statistics
    """
    # Create statistics directory if it doesn't exist
    stats_dir = os.path.join(uploads_dir, "stats")
    os.makedirs(stats_dir, exist_ok=True)
    
    # Get base filename without extension
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    
    # File to store individual upload details
    upload_record = os.path.join(uploads_dir, f"{base_name}_uploads.json")
    
    # Get existing upload data if available
    existing_data = {}
    try:
        if os.path.exists(upload_record):
            with open(upload_record, 'r') as f:
                existing_data = json.load(f)
    except Exception as e:
        logger.error(f"Error reading existing upload data: {e}")
    
    # Update upload data
    if "uploads" not in existing_data:
        existing_data["uploads"] = []
    
    existing_data["uploads"].append(result)
    existing_data["video_path"] = video_path
    existing_data["last_updated"] = datetime.now().isoformat()
    
    # Save updated upload record
    try:
        with open(upload_record, 'w') as f:
            json.dump(existing_data, f, indent=2)
        logger.info(f"Saved upload record to {upload_record}")
    except Exception as e:
        logger.error(f"Error saving upload record: {e}")
    
    # Update global statistics
    stats_file = os.path.join(stats_dir, "upload_stats.json")
    stats = {}
    
    try:
        if os.path.exists(stats_file):
            with open(stats_file, 'r') as f:
                stats = json.load(f)
    except Exception as e:
        logger.error(f"Error reading upload statistics: {e}")
    
    # Initialize stats structure if needed
    if "total_uploads" not in stats:
        stats["total_uploads"] = 0
    if "successful_uploads" not in stats:
        stats["successful_uploads"] = 0
    if "failed_uploads" not in stats:
        stats["failed_uploads"] = 0
    if "uploads_by_platform" not in stats:
        stats["uploads_by_platform"] = {}
    if "recent_uploads" not in stats:
        stats["recent_uploads"] = []
    
    # Update statistics
    stats["total_uploads"] += 1
    if result.get("success", False):
        stats["successful_uploads"] += 1
    else:
        stats["failed_uploads"] += 1
    
    # Update platform-specific stats
    platform = result.get("platform", "unknown")
    if platform not in stats["uploads_by_platform"]:
        stats["uploads_by_platform"][platform] = {
            "total": 0,
            "successful": 0,
            "failed": 0
        }
    
    stats["uploads_by_platform"][platform]["total"] += 1
    if result.get("success", False):
        stats["uploads_by_platform"][platform]["successful"] += 1
    else:
        stats["uploads_by_platform"][platform]["failed"] += 1
    
    # Add to recent uploads list (keep last 20)
    recent_upload = {
        "filename": os.path.basename(video_path),
        "platform": platform,
        "success": result.get("success", False),
        "timestamp": result.get("timestamp", datetime.now().isoformat()),
        "url": result.get("url", "")
    }
    
    stats["recent_uploads"].insert(0, recent_upload)
    stats["recent_uploads"] = stats["recent_uploads"][:20]  # Keep only last 20
    
    # Update last_updated timestamp
    stats["last_updated"] = datetime.now().isoformat()
    
    # Save updated statistics
    try:
        with open(stats_file, 'w') as f:
            json.dump(stats, f, indent=2)
        logger.info(f"Updated upload statistics")
    except Exception as e:
        logger.error(f"Error saving upload statistics: {e}")
    
    return stats

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
                
                # Send notification if successful
                if result.get('success') and not self.args.dry_run and notifications_available:
                    send_alert(
                        f"LoopForge: Video Uploaded to {platform.title()}",
                        f"Video '{os.path.basename(video_path)}' uploaded to {platform.title()} successfully. URL: {result.get('url', 'N/A')}"
                    )
                
                # Update statistics
                update_upload_stats(video_path, result, self.uploads_dir)
        
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
