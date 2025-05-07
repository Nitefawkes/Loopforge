# LoopForge Setup Guide

This guide will walk you through setting up the LoopForge environment and tools.

## Phase 0: Local Dev Environment Setup

### Python Installation

1. Download and install Python 3.8+ from [python.org](https://www.python.org/downloads/)
2. During installation, ensure "Add Python to PATH" is checked
3. Verify installation with:
   ```
   python --version
   ```

### FFmpeg Installation

1. Download FFmpeg from [ffmpeg.org](https://ffmpeg.org/download.html)
2. Extract to a location of your choice (e.g., `C:\FFmpeg`)
3. Add FFmpeg to your PATH:
   - Windows: Add `C:\FFmpeg\bin` to your system PATH
   - Mac/Linux: `export PATH=$PATH:/path/to/ffmpeg/bin`
4. Verify installation with:
   ```
   ffmpeg -version
   ```

### Local Stable Diffusion / AnimateDiff Setup

You can choose either InvokeAI or ComfyUI:

#### Option 1: InvokeAI

1. Follow the installation guide at [InvokeAI GitHub](https://github.com/invoke-ai/InvokeAI)
2. Install AnimateDiff extension:
   ```
   invokeai-ti --install-model "AnimateDiff"
   ```

#### Option 2: ComfyUI (Recommended for flexibility)

1. Clone the ComfyUI repository:
   ```
   git clone https://github.com/comfyanonymous/ComfyUI
   cd ComfyUI
   ```
2. Install requirements:
   ```
   pip install -r requirements.txt
   ```
3. Install the AnimateDiff custom node:
   ```
   cd custom_nodes
   git clone https://github.com/continue-revolution/sd-webui-animatediff
   cd sd-webui-animatediff
   pip install -r requirements.txt
   ```

### Python Libraries Installation

Install the required libraries:

```
pip install moviepy openai-whisper anthropic openai python-dotenv yt-upload pillow fastapi uvicorn
```

### API Keys Configuration

1. Create a copy of the example config file:
   ```
   cp config/config.example.json config/config.json
   ```
2. Edit `config.json` to add your API keys:
   - OpenAI API Key
   - Claude/Anthropic API Key
   - YouTube API credentials (for automated uploads)

## Phase 1: Core Pipeline Scripts

### Script Setup

1. The repository contains template scripts in the `src` directory
2. Each script has detailed comments explaining its function
3. Before running, make necessary adjustments for your specific setup

### Testing the Pipeline

1. Run a simple test with the prompt generator:
   ```
   python src/prompt_generation/generate_prompts.py --topic "space exploration" --count 3
   ```
2. Check the `data/prompts_to_render` directory for output
3. Run the renderer script:
   ```
   python src/rendering/local_renderer.py
   ```
4. Run post-processing:
   ```
   python src/post_processing/process_video.py
   ```

## Phase 2: MVP Prototype Setup

### FastAPI Local Prototype

1. Navigate to the `api_prototype` directory
2. Run the development server:
   ```
   uvicorn main:app --reload
   ```
3. Access the API at `http://localhost:8000/docs`

### Replit Deployment (Optional)

1. Create a new Replit project
2. Upload the contents of the `api_prototype` directory
3. Add your API keys as environment variables in Replit
4. Run the server with the command: `uvicorn main:app --host 0.0.0.0 --port 8080`

## Folder Structure Explanation

- `data/prompts_to_render`: Storage for generated prompts waiting to be rendered
- `data/rendered_clips`: Raw output from Stable Diffusion/AnimateDiff
- `data/ready_to_post`: Final videos with captions, loops, etc. ready for publishing
- `assets/branding`: Add your logo and branding elements here
- `assets/b_roll`: Add stock B-roll footage here for automatic inclusion

## Troubleshooting

### Common Issues

1. **FFmpeg not found**: Ensure FFmpeg is properly added to your PATH
2. **GPU errors**: Make sure your GPU drivers are up to date
3. **API rate limiting**: Implement proper rate limit handling in your scripts
4. **Video generation failures**: Start with simpler prompts and gradually increase complexity

### Getting Help

- Check the logs in the console for error messages
- Refer to the documentation for each tool:
  - [FFmpeg Documentation](https://ffmpeg.org/documentation.html)
  - [MoviePy Documentation](https://zulko.github.io/moviepy/)
  - [OpenAI Whisper Documentation](https://github.com/openai/whisper)

# === LoopForge Progress Snapshot (Operational Status) ===

## Notification & Alerting System
- Multi-channel notifications (Email, Slack, Discord) are now supported for pipeline events.
- Alerts are sent on pipeline failures, timeouts, and successful completions, as well as for video processing and upload completions.
- Configure notification settings in `config/config.json` under the `notifications` section.

## Reliability & Logging
- Pipeline logs stdout/stderr for each stage, checks for expected outputs, and provides granular logging.
- On any error or failure, the pipeline exits with a nonzero code and sends an alert if notifications are enabled.
- A summary of pipeline stage results is printed and logged at the end.

## Current Status (Snapshot)
- End-to-end pipeline is operational and can be triggered via CLI or API.
- All major stages (prompt generation, rendering, processing, upload) are integrated and monitored.
- Notification system is in place for both errors and successful completions.
- See README for more details and configuration instructions.
