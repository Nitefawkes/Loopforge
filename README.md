# LoopForge

A locally-powered, automated solo content pipeline for creating and publishing looping video content.

## Project Overview

LoopForge is a bootstrapped, automation-heavy approach to content creation and distribution. It leverages local tools, AI, and scripting to generate engaging video loops for platforms like YouTube Shorts, TikTok, and Instagram Reels without relying on paid subscription services.

### Core Components

- **Automated Ideation & Prompting**: Using Claude/OpenAI to generate content ideas and detailed prompts
- **Local Visual Generation**: Open Source Stable Diffusion variants (AnimateDiff/Deforum) running on local GPU
- **Scripted Video Processing**: FFmpeg and MoviePy for looping, captioning (via OpenAI Whisper CLI), and assembly
- **Scripted Publishing**: OSS libraries for cross-platform publishing
- **MVP Backend Prototype**: Simple API for content generation (early platform foundation)

## Project Structure

```
Loop-forge/
├── api_prototype/        # FastAPI prototype for the platform
├── assets/
│   ├── b_roll/           # B-roll footage for video enhancement
│   └── branding/         # Logos, watermarks, and brand elements
├── config/               # Configuration files for API keys, etc.
├── data/
│   ├── prompts_to_render/  # Generated prompts queue
│   ├── rendered_clips/     # Raw output from SD/AnimateDiff
│   └── ready_to_post/      # Processed videos ready for publishing
├── docs/                 # Documentation
└── src/
    ├── prompt_generation/ # Scripts for generating prompts
    ├── rendering/         # Scripts for local rendering
    ├── post_processing/   # Video processing scripts
    └── upload/            # Platform upload scripts
```

## Getting Started

### Prerequisites

- Python 3.8+
- FFmpeg installed and in PATH
- Local GPU (e.g., 3060 Ti or better) for rendering
- API keys for OpenAI/Claude
- InvokeAI or ComfyUI with AnimateDiff installed

### Installation

1. Clone this repository
2. Install required Python packages: `pip install -r requirements.txt`
3. Copy `config/config.example.json` to `config/config.json` and add your API keys
4. Follow the setup guide in `docs/setup.md`

## Development Phases

1. **Local Dev Environment Setup**: Install Python, FFmpeg, SD/AnimateDiff, required libraries
2. **Core Pipeline Scripts**: Build prompt generator, local renderer, video processor, and uploader
3. **First Content & MVP Prototype**: Create initial content and simple web service
4. **Automation Loop & Iteration**: Create watch folders, batch process, and continuously improve

## Strategy Notes

- **Zero Recurring Cost**: Leverages existing software/libraries and local hardware
- **Full Control**: Own the entire pipeline code
- **Building Platform IP**: Every script is an early version of the platform's core logic
- **Focus on Core Task**: Get content live, then automate that process

## Enhancements

- **Niche Selection**: Use Google Trends (5-year view) for "trending but durable" check
- **Brand & Channels**: Secure domain, create mobile-first landing page
- **Affiliate Integration**: Apply for high-ticket recurring SaaS programs
- **Production Improvements**: Auto B-roll injection, caption generation
- **Cost Control**: Render drafts at 720p locally before cloud rendering at 4K
- **Content Buffer**: Batch 45-60 shorts upfront to maintain consistent posting schedule
- **Notion Prototype**: Create public Notion page mimicking the "Video Idea Generator" for early validation

## Notifications & Alerts

LoopForge now supports multi-channel notifications for pipeline events:
- **Email** (via SMTP)
- **Slack** (via webhook)
- **Discord** (via webhook)

Alerts are sent on pipeline failures, timeouts, and successful completions. Video processing and upload completions also trigger notifications.

Configure notification settings in `config/config.json` under the `notifications` section. You can enable/disable each channel and set credentials/webhooks as needed.

## Reliability & Logging Improvements

- The pipeline now logs stdout/stderr for each stage, checks for expected outputs, and provides granular logging.
- On any error or failure, the pipeline exits with a nonzero code and sends an alert if notifications are enabled.
- A summary of pipeline stage results is printed and logged at the end.

## License

[MIT License](LICENSE)
