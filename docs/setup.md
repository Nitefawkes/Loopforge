# 🚀 LoopForge Quick Start Setup Guide

Welcome! This guide will help you create your first looping video in minutes—even if you're brand new to Python or AI tools.

---

## ✅ Quick Start Checklist

1. **Install Prerequisites**
   - [ ] Python 3.8+ (`python --version`)
   - [ ] FFmpeg (`ffmpeg -version`)
   - [ ] (Recommended) NVIDIA GPU with drivers

2. **Clone and Install**
   ```bash
   git clone https://github.com/Nitefawkes/Loopforge.git
   cd Loopforge
   pip install -r requirements.txt
   ```

3. **Configure**
   ```bash
   cp config/config.example.json config/config.json
   # Edit config/config.json and add your API keys (OpenAI, YouTube, etc.)
   # You can start without keys, but some features will be limited.
   ```

4. **First Video (One Command!)**
   ```bash
   python src/run_pipeline.py --all --topic "cats" --count 1
   ```
   - Your video will be generated and appear in `data/ready_to_post/`.

5. **Explore & Customize**
   - Try changing the topic or count.
   - Check out `config/` for example ComfyUI workflows.
   - Use default branding assets in `assets/branding/` or add your own.

---

## 🖥️ How to Use the LoopForge GUI

The LoopForge GUI makes it easy to generate and publish videos without using the command line.

### 1. **Install Streamlit**
If you haven't already, install Streamlit:
```bash
pip install streamlit
```

### 2. **Launch the GUI**
From your project root directory, run:
```bash
python -m streamlit run gui.py
```
This will open the LoopForge GUI in your web browser.

### 3. **Using the GUI**
- **Logo/Branding:** If you have a logo at `assets/branding/logo.png`, it will be displayed at the top.
- **Config Check:** The GUI will check your config and warn if any API keys are missing.
- **Fill Out the Form:**
  - **Video Topic:** What your video should be about.
  - **Prompt Count:** How many prompts/videos to generate.
  - **Rendering Engine:** Choose from available engines (e.g., comfyui, invoke).
  - **Workflow File:** Select from detected workflow files in `config/` (e.g., `comfyui_animatediff_workflow.json`, `comfyui_cartoon_workflow.json`).
  - **Branding & Assets:** Choose from bundled example logos (`logo.png`, `logo_alt.png`), watermarks (`watermark_demo.png`), and B-roll (`nature_broll.mp4`).
  - **Upload Platform:** Where to upload the final video (e.g., YouTube, TikTok).
  - **Dry Run:** If checked, the upload will be simulated only.
  - **Advanced Options:** Expand to skip captions, add B-roll, add watermark, or schedule upload.
- **Summary:** Before running, a summary of your selections will be shown.
- **Run Pipeline:** Click 'Run Pipeline' to start. Output logs will appear live in the GUI.
- **Download Log:** After completion, you can download the output log.
- **Reset:** Use the 'Reset Form' button to clear your selections.

### 4. **Troubleshooting**
- If the GUI doesn't launch, make sure Streamlit is installed and use the full command above.
- If you see missing API key warnings, edit `config/config.json` and add your keys.
- If the pipeline fails, check the output log and see the troubleshooting section below.

---

## 🆘 Troubleshooting

- **ffmpeg not found:** [Download FFmpeg](https://ffmpeg.org/download.html) and add it to your PATH.
- **CUDA/GPU not available:** Make sure you have the correct NVIDIA drivers and CUDA toolkit.
- **API key errors:** Double-check your keys in `config/config.json`.
- **Permission errors:** Try running your terminal as administrator.
- **Video not generated:** Check the logs printed in your terminal for error messages.

---

## 📦 Folder Structure (What Goes Where)

- `data/prompts_to_render/` — Generated prompts waiting to be rendered
- `data/rendered_clips/` — Raw output from Stable Diffusion/AnimateDiff
- `data/ready_to_post/` — Final videos ready for publishing
- `assets/branding/` — Default logo, watermark, and branding elements (e.g., `logo.png`, `logo_alt.png`, `watermark_demo.png`)
- `assets/b_roll/` — Example B-roll footage for automatic inclusion (e.g., `nature_broll.mp4`)
- `config/` — Example ComfyUI workflows and configuration files (e.g., `comfyui_animatediff_workflow.json`, `comfyui_cartoon_workflow.json`)

---

## 🛠️ Advanced/Optional Setup

### Local Stable Diffusion / AnimateDiff

You can use either InvokeAI or ComfyUI (recommended for flexibility):

#### Option 1: InvokeAI
- [InvokeAI GitHub](https://github.com/invoke-ai/InvokeAI)
- Install AnimateDiff extension:
  ```
  invokeai-ti --install-model "AnimateDiff"
  ```

#### Option 2: ComfyUI (Recommended)
- Clone and install:
  ```
  git clone https://github.com/comfyanonymous/ComfyUI
  cd ComfyUI
  pip install -r requirements.txt
  ```
- Install AnimateDiff custom node:
  ```
  cd custom_nodes
  git clone https://github.com/continue-revolution/sd-webui-animatediff
  cd sd-webui-animatediff
  pip install -r requirements.txt
  ```
- Use the example workflow in `config/comfyui_example_workflow.json`.

### API Keys
- Add your OpenAI, Anthropic, and YouTube API keys to `config/config.json` for full functionality.

### FastAPI Local Prototype (Optional)
- Navigate to `api_prototype/` and run:
  ```
  uvicorn main:app --reload
  ```
- Access the API at [http://localhost:8000/docs](http://localhost:8000/docs)

### Replit Deployment (Optional)
- See the original guide for Replit deployment steps.

---

## 📚 Resources & Help
- [FFmpeg Documentation](https://ffmpeg.org/documentation.html)
- [MoviePy Documentation](https://zulko.github.io/moviepy/)
- [OpenAI Whisper Documentation](https://github.com/openai/whisper)
- [LoopForge GitHub Issues](https://github.com/Nitefawkes/Loopforge/issues)

---

## 🎉 Next Steps
- Try editing the topic or count to make more videos!
- Explore and customize workflows and branding.
- Join the community or open an issue if you get stuck.

---

**You're ready to create your first looping video!**
