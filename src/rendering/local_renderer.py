#!/usr/bin/env python3
"""
Local Renderer Script for LoopForge

This script monitors the prompts_to_render directory for new prompt JSON files,
processes them by sending them to a local rendering engine (ComfyUI or InvokeAI),
and saves the output to the rendered_clips directory.

Usage:
    python local_renderer.py
    python local_renderer.py --workflow custom_workflow.json
    python local_renderer.py --engine invoke
"""

import os
import sys
import json
import time
import argparse
import requests
import shutil
from pathlib import Path
from datetime import datetime
import uuid
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
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

class WorkflowError(Exception):
    """Exception raised for workflow-related issues."""
    pass

class RenderError(Exception):
    """Exception raised for rendering issues."""
    pass

class ValidationError(Exception):
    """Exception raised for validation issues."""
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

def load_workflow(workflow_file):
    """
    Load ComfyUI workflow from JSON file
    
    Args:
        workflow_file (str): Path to workflow file
    
    Returns:
        dict: Workflow data
    
    Raises:
        WorkflowError: If workflow file is missing or invalid
    """
    try:
        with open(workflow_file, 'r') as f:
            workflow = json.load(f)
            logger.info(f"Workflow loaded successfully from {workflow_file}")
            return workflow
    except FileNotFoundError:
        error_msg = f"Workflow file not found at {workflow_file}"
        logger.error(error_msg)
        if notifications_available:
            send_alert("LoopForge: Workflow Error", error_msg)
        sys.exit(1)
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in workflow file: {e}"
        logger.error(error_msg)
        if notifications_available:
            send_alert("LoopForge: Workflow Error", error_msg)
        sys.exit(1)

def validate_prompt_data(prompt_data):
    """
    Validate prompt data structure before rendering
    
    Args:
        prompt_data (dict): Prompt data to validate
    
    Returns:
        bool: True if valid
    
    Raises:
        ValidationError: If prompt data is invalid
    """
    if not isinstance(prompt_data, dict):
        raise ValidationError("Prompt data must be a dictionary")
    
    required_fields = ["prompt", "negative_prompt", "aspect_ratio"]
    for field in required_fields:
        if field not in prompt_data:
            raise ValidationError(f"Prompt data missing required field: {field}")
    
    if not isinstance(prompt_data["prompt"], str) or not prompt_data["prompt"].strip():
        raise ValidationError("Prompt field must be a non-empty string")
    
    if not isinstance(prompt_data["negative_prompt"], str):
        raise ValidationError("Negative prompt field must be a string")
    
    if prompt_data["aspect_ratio"] not in ["1:1", "9:16"]:
        raise ValidationError(f"Invalid aspect ratio: {prompt_data['aspect_ratio']}")
    
    return True

class PromptHandler(FileSystemEventHandler):
    """Handler for file system events in the prompts_to_render directory"""
    
    def __init__(self, config, engine, workflow_file):
        """
        Initialize the prompt handler
        
        Args:
            config (dict): Configuration data
            engine (str): Rendering engine to use ("comfyui" or "invokeai")
            workflow_file (str): Path to workflow file (for ComfyUI only)
        """
        self.config = config
        self.engine = engine
        self.workflow_file = workflow_file
        self.render_queue = []
        self.max_retries = config.get("rendering", {}).get("max_retries", 3)
        
        # Get paths from config
        paths = config.get("paths", {})
        self.prompts_dir = os.path.join(script_path, paths.get("prompts_dir", "data/prompts_to_render"))
        self.rendered_dir = os.path.join(script_path, paths.get("rendered_dir", "data/rendered_clips"))
        
        # Ensure output directory exists
        try:
            os.makedirs(self.rendered_dir, exist_ok=True)
            logger.info(f"Output directory created/verified: {self.rendered_dir}")
        except Exception as e:
            error_msg = f"Failed to create output directory: {e}"
            logger.error(error_msg)
            if notifications_available:
                send_alert("LoopForge: Renderer Error", error_msg)
            raise
        
        # Load existing prompt files
        self.load_existing_prompts()
    
    def load_existing_prompts(self):
        """
        Load existing prompt files in the prompts_to_render directory
        
        Returns:
            int: Number of prompt files loaded
        """
        count = 0
        try:
            if os.path.exists(self.prompts_dir):
                for filename in os.listdir(self.prompts_dir):
                    if filename.endswith(".json"):
                        file_path = os.path.join(self.prompts_dir, filename)
                        
                        # Check if the file has already been rendered
                        try:
                            with open(file_path, 'r') as f:
                                data = json.load(f)
                                metadata = data.get("metadata", {})
                                status = metadata.get("status", "")
                                
                                # Only add files that haven't been rendered yet
                                if status != "rendered":
                                    self.render_queue.append(file_path)
                                    count += 1
                        except Exception as e:
                            logger.warning(f"Failed to check status of {file_path}: {e}")
                            # Add to queue anyway to be safe
                            self.render_queue.append(file_path)
                            count += 1
                
                logger.info(f"Loaded {count} unrendered prompt files")
            else:
                logger.warning(f"Prompts directory not found: {self.prompts_dir}")
        except Exception as e:
            logger.error(f"Error loading existing prompts: {e}")
            if notifications_available:
                send_alert("LoopForge: Renderer Error", f"Failed to load existing prompts: {e}")
        
        return count
    
    def on_created(self, event):
        """
        Handle file creation events
        
        Args:
            event: Filesystem event
        """
        if not event.is_directory and event.src_path.endswith(".json"):
            logger.info(f"New prompt file detected: {event.src_path}")
            self.render_queue.append(event.src_path)
    
    def process_queue(self):
        """
        Process the render queue
        
        Returns:
            int: Number of prompts successfully processed
        """
        if not self.render_queue:
            return 0
        
        logger.info(f"Processing render queue: {len(self.render_queue)} files")
        success_count = 0
        
        for prompt_file in list(self.render_queue):
            try:
                logger.info(f"Processing {os.path.basename(prompt_file)}")
                self.process_prompt(prompt_file)
                self.render_queue.remove(prompt_file)
                success_count += 1
            except Exception as e:
                logger.error(f"Error processing {prompt_file}: {e}")
                if notifications_available:
                    send_alert("LoopForge: Rendering Error", 
                              f"Failed to process {os.path.basename(prompt_file)}: {str(e)[:200]}")
                # Move to the end of the queue to try again later
                self.render_queue.remove(prompt_file)
                self.render_queue.append(prompt_file)
        
        return success_count
    
    def process_prompt(self, prompt_file):
        """
        Process a single prompt file
        
        Args:
            prompt_file (str): Path to prompt file
        
        Returns:
            str: Path to output file if successful
        
        Raises:
            RenderError: If rendering fails
        """
        logger.info(f"Processing prompt file: {prompt_file}")
        
        # Load prompt data
        try:
            with open(prompt_file, 'r') as f:
                prompt_data = json.load(f)
            
            # Validate prompt data
            validate_prompt_data(prompt_data)
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON in prompt file: {e}"
            logger.error(error_msg)
            raise RenderError(error_msg)
        except ValidationError as e:
            error_msg = f"Invalid prompt data: {e}"
            logger.error(error_msg)
            raise RenderError(error_msg)
        except Exception as e:
            error_msg = f"Failed to load prompt file: {e}"
            logger.error(error_msg)
            raise RenderError(error_msg)
        
        # Extract prompt information
        prompt = prompt_data.get("prompt", "")
        negative_prompt = prompt_data.get("negative_prompt", "")
        aspect_ratio = prompt_data.get("aspect_ratio", "1:1")
        metadata = prompt_data.get("metadata", {})
        
        # Determine dimensions based on aspect ratio
        width, height = self.get_dimensions(aspect_ratio)
        
        # Send to renderer
        start_time = time.time()
        output_path = None
        render_method = None
        
        try:
            if self.engine == "comfyui":
                render_method = "ComfyUI"
                output_path = self.render_with_comfyui(prompt, negative_prompt, width, height, prompt_data)
            else:  # invokeai
                render_method = "InvokeAI"
                output_path = self.render_with_invokeai(prompt, negative_prompt, width, height, prompt_data)
            
            if not output_path:
                raise RenderError(f"Renderer ({render_method}) returned no output path")
            
            # Calculate rendering time
            render_time = time.time() - start_time
            logger.info(f"Rendering completed in {render_time:.2f} seconds")
            
            # Update prompt status
            prompt_data["metadata"]["status"] = "rendered"
            prompt_data["metadata"]["rendered_at"] = datetime.now().isoformat()
            prompt_data["metadata"]["output_path"] = output_path
            prompt_data["metadata"]["render_time"] = render_time
            prompt_data["metadata"]["renderer"] = render_method
            
            # Save updated prompt data
            with open(prompt_file, 'w') as f:
                json.dump(prompt_data, f, indent=2)
            
            logger.info(f"Successfully rendered: {os.path.basename(prompt_file)} -> {os.path.basename(output_path)}")
            
            # Send notification
            if notifications_available:
                send_alert("LoopForge: Rendering Complete", 
                          f"Successfully rendered {os.path.basename(prompt_file)} using {render_method} in {render_time:.2f} seconds")
            
            return output_path
        except Exception as e:
            error_msg = f"Error rendering with {render_method}: {e}"
            logger.error(error_msg)
            if notifications_available:
                send_alert("LoopForge: Rendering Failed", 
                          f"Failed to render {os.path.basename(prompt_file)} with {render_method}: {str(e)[:200]}")
            raise RenderError(error_msg)
    
    def get_dimensions(self, aspect_ratio):
        """
        Convert aspect ratio to dimensions based on configuration
        
        Args:
            aspect_ratio (str): Aspect ratio ("1:1" or "9:16")
        
        Returns:
            tuple: (width, height) in pixels
        """
        rendering_config = self.config.get("rendering", {})
        draft_resolution = rendering_config.get("draft_resolution", "720p")
        
        if draft_resolution == "720p":
            if aspect_ratio == "1:1":
                return 720, 720
            elif aspect_ratio == "9:16":
                return 720, 1280
        elif draft_resolution == "1080p":
            if aspect_ratio == "1:1":
                return 1080, 1080
            elif aspect_ratio == "9:16":
                return 1080, 1920
        
        logger.warning(f"Unknown resolution or aspect ratio: {draft_resolution}, {aspect_ratio}. Using default 512x512.")
        # Default fallback
        return 512, 512
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def render_with_comfyui(self, prompt, negative_prompt, width, height, prompt_data):
        """
        Render video using ComfyUI API with retry logic
        
        Args:
            prompt (str): Positive prompt text
            negative_prompt (str): Negative prompt text
            width (int): Video width
            height (int): Video height
            prompt_data (dict): Full prompt data
        
        Returns:
            str: Path to output video file
        
        Raises:
            RenderError: If rendering fails
        """
        logger.info(f"Rendering with ComfyUI ({width}x{height})")
        
        # Get ComfyUI configuration
        comfyui_config = self.config.get("rendering", {}).get("comfyui", {})
        api_url = comfyui_config.get("api_url", "http://127.0.0.1:8188/prompt")
        
        # Load workflow template
        workflow = None
        try:
            if self.workflow_file:
                workflow = load_workflow(self.workflow_file)
                logger.info(f"Using custom workflow: {self.workflow_file}")
            else:
                default_workflow = comfyui_config.get("workflow_file")
                if default_workflow:
                    workflow_path = os.path.join(script_path, default_workflow)
                    workflow = load_workflow(workflow_path)
                    logger.info(f"Using default workflow: {workflow_path}")
            
            if not workflow:
                error_msg = "No workflow template available. Please specify a workflow file."
                logger.error(error_msg)
                raise WorkflowError(error_msg)
        except Exception as e:
            error_msg = f"Error loading workflow: {e}"
            logger.error(error_msg)
            raise WorkflowError(error_msg)
        
        # Modify workflow with prompt data
        try:
            # Clone workflow to avoid modifying the original
            workflow = json.loads(json.dumps(workflow))
            
            # Update nodes
            for node_id, node in workflow.get("nodes", {}).items():
                if node.get("type") == "CLIPTextEncode":
                    if "positive" in node.get("title", "").lower():
                        node["inputs"]["text"] = prompt
                        logger.debug(f"Set positive prompt in node {node_id}")
                    elif "negative" in node.get("title", "").lower():
                        node["inputs"]["text"] = negative_prompt
                        logger.debug(f"Set negative prompt in node {node_id}")
                
                # Set dimensions for appropriate nodes
                if node.get("type") in ["EmptyLatentImage", "VAEDecode"]:
                    if "width" in node.get("inputs", {}):
                        node["inputs"]["width"] = width
                    if "height" in node.get("inputs", {}):
                        node["inputs"]["height"] = height
                    logger.debug(f"Set dimensions {width}x{height} in node {node_id}")
        except Exception as e:
            error_msg = f"Error modifying workflow: {e}"
            logger.error(error_msg)
            raise WorkflowError(error_msg)
        
        # Send to ComfyUI API
        try:
            logger.info(f"Sending request to ComfyUI API: {api_url}")
            response = requests.post(api_url, json={"prompt": workflow}, timeout=30)
            response.raise_for_status()
            data = response.json()
            prompt_id = data.get("prompt_id")
            logger.info(f"ComfyUI accepted request, prompt ID: {prompt_id}")
            
            # Wait for completion
            # This is a simplified example - you might want to implement a proper polling mechanism
            # or webhook handler depending on your ComfyUI setup
            wait_time = comfyui_config.get("wait_time", 60)
            logger.info(f"Waiting {wait_time} seconds for rendering to complete...")
            time.sleep(wait_time)
            
            # For this example, assume output is saved to a known location
            # In practice, you'd need to query ComfyUI for the output path
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"render_{timestamp}_{uuid.uuid4()}.mp4"
            output_path = os.path.join(self.rendered_dir, output_filename)
            
            # In a real implementation, you would copy the file from ComfyUI's output location
            # Simulate this with a placeholder file for now
            with open(output_path, 'w') as f:
                f.write("Placeholder for ComfyUI rendered output")
            
            logger.info(f"Rendering complete, output saved to: {output_path}")
            return output_path
            
        except requests.HTTPError as e:
            logger.error(f"HTTP error rendering with ComfyUI: {e}")
            raise RenderError(f"HTTP error: {e}")
        except requests.ConnectionError as e:
            logger.error(f"Connection error rendering with ComfyUI: {e}")
            raise RenderError(f"Connection error: {e}")
        except requests.Timeout as e:
            logger.error(f"Timeout rendering with ComfyUI: {e}")
            raise RenderError(f"Timeout: {e}")
        except Exception as e:
            logger.error(f"Error rendering with ComfyUI: {e}")
            raise RenderError(str(e))
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def render_with_invokeai(self, prompt, negative_prompt, width, height, prompt_data):
        """
        Render video using InvokeAI API with retry logic
        
        Args:
            prompt (str): Positive prompt text
            negative_prompt (str): Negative prompt text
            width (int): Video width
            height (int): Video height
            prompt_data (dict): Full prompt data
        
        Returns:
            str: Path to output video file
        
        Raises:
            RenderError: If rendering fails
        """
        logger.info(f"Rendering with InvokeAI ({width}x{height})")
        
        # Get InvokeAI configuration
        invokeai_config = self.config.get("rendering", {}).get("invokeai", {})
        api_url = invokeai_config.get("api_url", "http://127.0.0.1:9090/api/invocations")
        batch_size = invokeai_config.get("batch_size", 16)
        
        # Prepare InvokeAI request payload
        payload = {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "width": width,
            "height": height,
            "num_frames": batch_size,
            "animation_mode": "AnimateDiff",
            "output_format": "mp4"
        }
        
        # Send to InvokeAI API
        try:
            logger.info(f"Sending request to InvokeAI API: {api_url}")
            response = requests.post(api_url, json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()
            invocation_id = data.get("invocation_id")
            logger.info(f"InvokeAI accepted request, invocation ID: {invocation_id}")
            
            # Wait for completion
            # This is a simplified example - you might want to implement a proper polling mechanism
            wait_time = invokeai_config.get("wait_time", 60)
            logger.info(f"Waiting {wait_time} seconds for rendering to complete...")
            time.sleep(wait_time)
            
            # For this example, assume output is saved to a known location
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"render_{timestamp}_{uuid.uuid4()}.mp4"
            output_path = os.path.join(self.rendered_dir, output_filename)
            
            # In a real implementation, you would copy the file from InvokeAI's output location
            # Simulate this with a placeholder file for now
            with open(output_path, 'w') as f:
                f.write("Placeholder for InvokeAI rendered output")
            
            logger.info(f"Rendering complete, output saved to: {output_path}")
            return output_path
            
        except requests.HTTPError as e:
            logger.error(f"HTTP error rendering with InvokeAI: {e}")
            raise RenderError(f"HTTP error: {e}")
        except requests.ConnectionError as e:
            logger.error(f"Connection error rendering with InvokeAI: {e}")
            raise RenderError(f"Connection error: {e}")
        except requests.Timeout as e:
            logger.error(f"Timeout rendering with InvokeAI: {e}")
            raise RenderError(f"Timeout: {e}")
        except Exception as e:
            logger.error(f"Error rendering with InvokeAI: {e}")
            raise RenderError(str(e))

def main():
    """
    Main function to run the local renderer
    """
    parser = argparse.ArgumentParser(description="Local Renderer for LoopForge")
    parser.add_argument("--engine", choices=["comfyui", "invokeai"], default="comfyui", help="Rendering engine to use")
    parser.add_argument("--workflow", type=str, help="Custom workflow file for ComfyUI")
    args = parser.parse_args()
    
    try:
        logger.info("Starting LoopForge Local Renderer")
        logger.info(f"Rendering engine: {args.engine}")
        if args.workflow:
            logger.info(f"Custom workflow file: {args.workflow}")
        
        # Load configuration
        config = load_config()
        
        # Create event handler
        handler = PromptHandler(config, args.engine, args.workflow)
        
        # Create and start observer
        prompts_dir = handler.prompts_dir
        observer = Observer()
        observer.schedule(handler, prompts_dir, recursive=False)
        observer.start()
        logger.info(f"Watching for new prompt files in: {prompts_dir}")
        
        # Process existing prompts
        handler.process_queue()
        
        try:
            # Run indefinitely
            while True:
                time.sleep(5)
                handler.process_queue()
        except KeyboardInterrupt:
            logger.info("Stopping renderer (Ctrl+C pressed)")
            observer.stop()
        
        observer.join()
        logger.info("Renderer stopped")
        
    except Exception as e:
        error_msg = f"Unexpected error in renderer: {e}"
        logger.error(error_msg, exc_info=True)
        if notifications_available:
            send_alert("LoopForge: Renderer Error", error_msg)
        sys.exit(1)

if __name__ == "__main__":
    main()
