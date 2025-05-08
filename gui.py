import streamlit as st
import subprocess
import os
import glob
import json
import importlib.util

st.set_page_config(page_title="LoopForge GUI", layout="centered")

# --- Demo Mode Defaults ---
DEMO_DEFAULTS = {
    "topics": ["cats"],
    "count": 1,
    "engine": "comfyui",
    "workflow": "config/comfyui_cartoon_workflow.json",
    "platform": "youtube",
    "output_dir": "data/ready_to_post",
    "logo": "assets/branding/logo_alt.png",
    "watermark_file": "assets/branding/watermark_demo.png",
    "broll_file": "assets/b_roll/nature_broll.mp4",
    "notify_email": False,
    "notify_slack": False,
    "notify_discord": False,
    "skip_captions": False,
    "add_b_roll": True,
    "watermark": True,
    "schedule": False,
    "renderer_options": {}
}

# --- Dynamic Renderer Option Discovery ---
def get_renderer_class(engine_name):
    try:
        spec = importlib.util.find_spec(f"src.rendering.{engine_name}")
        if spec is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for attr in dir(module):
            cls = getattr(module, attr)
            if isinstance(cls, type) and hasattr(cls, "get_supported_options"):
                return cls
    except Exception:
        pass
    return None

# --- Branding/logo preview ---
def get_logo_path():
    logo_path = os.path.join("assets", "branding", "logo.png")
    return logo_path if os.path.exists(logo_path) else None

def get_watermark_files():
    files = glob.glob(os.path.join("assets", "branding", "*.png"))
    return [f for f in files if "watermark" in os.path.basename(f).lower() or "logo" in os.path.basename(f).lower()]

def get_broll_files():
    return glob.glob(os.path.join("assets", "b_roll", "*.mp4"))

logo_path = get_logo_path()
if logo_path:
    st.image(logo_path, width=120)

st.title("🎬 LoopForge: No-Code Video Pipeline")

# --- Demo Mode Toggle ---
st.sidebar.header("Mode")
demo_mode = st.sidebar.checkbox("Demo Mode", value=False, help="Try LoopForge instantly with example assets and settings.")
if demo_mode:
    st.info("Demo Mode is ON. All fields are pre-filled with example data and cannot be edited. Run the pipeline to see a sample workflow in action!")

st.markdown("""
Welcome! Use this interface to generate and publish looping videos without touching the command line.
- See [docs/setup.md](docs/setup.md) for full setup instructions.
- If you have issues, run `python check_setup.py` in your terminal.
""")

# --- Config check ---
def check_config():
    config_path = os.path.join("config", "config.json")
    example_path = os.path.join("config", "config.example.json")
    config = None
    missing_keys = []
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            keys = config.get("api_keys", {})
            if not keys.get("openai"): missing_keys.append("OpenAI")
            if not keys.get("anthropic"): missing_keys.append("Anthropic")
            yt = keys.get("youtube", {})
            if not (yt.get("client_id") and yt.get("client_secret") and yt.get("refresh_token")):
                missing_keys.append("YouTube")
        except Exception as e:
            st.warning(f"Config file error: {e}")
    else:
        st.warning("config/config.json not found. Using config.example.json for options.")
        with open(example_path, 'r') as f:
            config = json.load(f)
            missing_keys = ["OpenAI", "Anthropic", "YouTube"]
    return config, missing_keys

config, missing_keys = check_config()
if missing_keys:
    st.warning(f"Missing API keys: {', '.join(missing_keys)} (some features will be limited)")
else:
    st.success("Config loaded and all API keys present.")

# --- Pipeline Options ---
def get_workflow_files():
    files = glob.glob(os.path.join("config", "*.json"))
    return [f for f in files if "workflow" in os.path.basename(f).lower()]

def get_platforms():
    return config.get("upload", {}).get("platforms", ["youtube", "tiktok"])

def get_engines():
    # Hardcoded for now, but could be dynamic
    return ["comfyui", "invokeai"]

def get_output_dirs():
    dirs = [os.path.join("data", d) for d in ["ready_to_post", "rendered_clips", "prompts_to_render"] if os.path.isdir(os.path.join("data", d))]
    return dirs or [os.path.join("data", "ready_to_post")]

with st.form("pipeline_form", clear_on_submit=False):
    st.subheader("Batch Topics")
    topics_input = st.text_area(
        "Enter one or more topics (comma or newline separated)",
        value=", ".join(DEMO_DEFAULTS["topics"]) if demo_mode else "cats",
        help="Enter multiple topics for batch processing. Each topic will generate a video.",
        disabled=demo_mode
    )
    topics = DEMO_DEFAULTS["topics"] if demo_mode else [t.strip() for t in topics_input.replace(",", "\n").splitlines() if t.strip()]
    count = st.number_input(
        "Prompt Count per Topic", min_value=1, max_value=10,
        value=DEMO_DEFAULTS["count"] if demo_mode else 1,
        help="How many prompts/videos to generate per topic?",
        disabled=demo_mode
    )
    engines = get_engines()
    engine = st.selectbox(
        "Rendering Engine", engines,
        index=engines.index(DEMO_DEFAULTS["engine"]) if demo_mode and DEMO_DEFAULTS["engine"] in engines else 0,
        help="Which rendering engine to use?",
        disabled=demo_mode
    )
    workflow_files = get_workflow_files()
    workflow = st.selectbox(
        "Workflow File", workflow_files,
        index=workflow_files.index(DEMO_DEFAULTS["workflow"]) if demo_mode and DEMO_DEFAULTS["workflow"] in workflow_files else 0,
        help="Choose a ComfyUI/InvokeAI workflow file.",
        disabled=demo_mode
    ) if workflow_files else st.text_input("Workflow File (path)", help="Path to a workflow JSON file.", disabled=demo_mode)
    platforms = get_platforms()
    platform = st.selectbox(
        "Upload Platform", platforms,
        index=platforms.index(DEMO_DEFAULTS["platform"]) if demo_mode and DEMO_DEFAULTS["platform"] in platforms else 0,
        help="Where to upload the final video?",
        disabled=demo_mode
    )
    output_dirs = get_output_dirs()
    output_dir = st.selectbox(
        "Output Directory", output_dirs,
        index=output_dirs.index(DEMO_DEFAULTS["output_dir"]) if demo_mode and DEMO_DEFAULTS["output_dir"] in output_dirs else 0,
        help="Where to save the final videos?",
        disabled=demo_mode
    )
    dry_run = st.checkbox(
        "Dry Run (simulate upload)",
        value=True,
        help="If checked, will not actually upload.",
        disabled=demo_mode
    )
    # Asset pickers
    st.subheader("Branding & Assets")
    logo_files = [DEMO_DEFAULTS["logo"]] if demo_mode else ([logo_path] if logo_path else [])
    watermark_files = [DEMO_DEFAULTS["watermark_file"]] if demo_mode else get_watermark_files()
    watermark_file = st.selectbox(
        "Watermark File", watermark_files,
        index=0,
        help="Select a watermark/logo file.",
        disabled=demo_mode
    ) if watermark_files else None
    broll_files = [DEMO_DEFAULTS["broll_file"]] if demo_mode else get_broll_files()
    broll_file = st.selectbox(
        "B-Roll Clip", broll_files,
        index=0,
        help="Select a B-roll video to include.",
        disabled=demo_mode
    ) if broll_files else None
    if watermark_file:
        st.image(watermark_file, width=80, caption="Watermark Preview")
    if broll_file:
        st.video(broll_file, format="video/mp4")
    # Notification toggles
    st.subheader("Notifications")
    notify_email = st.checkbox("Email", value=DEMO_DEFAULTS["notify_email"] if demo_mode else config.get("notifications", {}).get("email", {}).get("enabled", False), disabled=demo_mode)
    notify_slack = st.checkbox("Slack", value=DEMO_DEFAULTS["notify_slack"] if demo_mode else config.get("notifications", {}).get("slack", {}).get("enabled", False), disabled=demo_mode)
    notify_discord = st.checkbox("Discord", value=DEMO_DEFAULTS["notify_discord"] if demo_mode else config.get("notifications", {}).get("discord", {}).get("enabled", False), disabled=demo_mode)
    # Renderer-specific options
    st.subheader("Renderer Options")
    renderer_options = {}
    renderer_class = None
    if not demo_mode:
        try:
            if engine == "comfyui":
                from src.rendering.comfyui import ComfyUIRenderer
                renderer_class = ComfyUIRenderer
            elif engine == "invokeai":
                from src.rendering.invokeai import InvokeAIRenderer
                renderer_class = InvokeAIRenderer
        except Exception:
            renderer_class = None
    else:
        renderer_class = None
    if renderer_class:
        supported_options = renderer_class().get_supported_options()
        for opt, desc in supported_options.items():
            renderer_options[opt] = st.text_input(f"{opt}", value="", help=desc, disabled=demo_mode)
    elif demo_mode:
        renderer_options = DEMO_DEFAULTS["renderer_options"]
    # Advanced options
    with st.expander("Advanced Options"):
        skip_captions = st.checkbox("Skip Captions", value=DEMO_DEFAULTS["skip_captions"] if demo_mode else False, help="Skip adding captions to videos.", disabled=demo_mode)
        add_b_roll = st.checkbox("Add B-Roll", value=DEMO_DEFAULTS["add_b_roll"] if demo_mode else config.get("video", {}).get("auto_b_roll", True), help="Automatically add B-roll footage.", disabled=demo_mode)
        watermark = st.checkbox("Add Watermark", value=DEMO_DEFAULTS["watermark"] if demo_mode else config.get("video", {}).get("watermark", True), help="Add watermark to videos.", disabled=demo_mode)
        schedule = st.checkbox("Schedule Upload", value=DEMO_DEFAULTS["schedule"] if demo_mode else config.get("upload", {}).get("schedule", False), help="Schedule upload for later.", disabled=demo_mode)
    submitted = st.form_submit_button("Run Pipeline")
    reset = st.form_submit_button("Reset Form")

# --- Summary ---
def show_summary():
    st.info(f"You are about to generate {count} video(s) for each topic: {topics} using {engine} and workflow '{os.path.basename(workflow)}'.\nUpload platform: {platform}. Output dir: {output_dir}. Dry run: {dry_run}. Renderer options: {renderer_options}. Advanced: skip captions={skip_captions}, b-roll={add_b_roll}, watermark={watermark}, schedule={schedule}")

# --- Run Pipeline ---
def build_command(topic):
    cmd = ["python", "src/run_pipeline.py", "--all", f"--topic", topic, f"--count", str(count)]
    if engine:
        cmd += ["--engine", engine]
    if workflow:
        cmd += ["--workflow", workflow]
    if platform:
        cmd += ["--platform", platform]
    if dry_run:
        cmd += ["--dry-run"]
    if skip_captions:
        cmd += ["--skip-captions"]
    if add_b_roll:
        cmd += ["--b-roll"]
    # Renderer-specific options
    for k, v in renderer_options.items():
        if v:
            cmd += ["--option", f"{k}={v}"]
    # Note: schedule and watermark would require additional CLI support
    # Output dir, watermark, b-roll, notifications would need to be passed via config or env
    return cmd

if 'output_area' not in st.session_state:
    st.session_state['output_area'] = ""

if submitted:
    show_summary()
    progress = st.progress(0, text="Starting batch...")
    total = len(topics)
    output_area = st.empty()
    all_output = ""
    for i, topic in enumerate(topics):
        progress.progress(i / total, text=f"Processing topic {i+1}/{total}: {topic}")
        st.info(f"Running LoopForge pipeline for topic: {topic} ...")
        cmd = build_command(topic)
        st.code(" ".join(cmd))
        with st.spinner(f"Processing topic: {topic} ..."):
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            output = ""
            for line in iter(process.stdout.readline, ''):
                output += line
                output_area.text_area("Output Log", output, height=300)
            process.stdout.close()
            process.wait()
        all_output += f"\n---\n[Topic: {topic}]\n" + output
        if process.returncode == 0:
            st.success(f"Pipeline run complete for topic: {topic}!")
        else:
            st.error(f"Pipeline failed for topic: {topic}. See output log and docs/setup.md for troubleshooting.")
        progress.progress((i+1) / total, text=f"Completed {i+1}/{total}")
    st.session_state['output_area'] = all_output
    st.download_button("Download Output Log", all_output, file_name="loopforge_output.log")

if reset:
    st.experimental_rerun() 