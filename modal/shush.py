import os
import warnings

os.environ.setdefault("MODAL_IMAGE_BUILDER_VERSION", "2025.06")

from modal import (
    Image,
    App,
    method,
    asgi_app,
    enter,
    concurrent,
    FunctionCall,
)
from fastapi import Request, FastAPI, responses
from fastapi.middleware.cors import CORSMiddleware
import tempfile

MODEL_DIR = "/model"
MIN_CONTAINERS = int(os.environ.get("WHISPER_MIN_CONTAINERS", "0"))
BATCH_SIZE = int(os.environ.get("WHISPER_BATCH_SIZE", "8"))
CHUNK_LENGTH_S = int(os.environ.get("WHISPER_CHUNK_LENGTH_S", "20"))
MAX_NEW_TOKENS = int(os.environ.get("WHISPER_MAX_NEW_TOKENS", "128"))
FLASH_ATTN_WHEEL = (
    "https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.3/"
    "flash_attn-2.8.3+cu12torch2.5cxx11abiFALSE-cp311-cp311-linux_x86_64.whl"
)

web_app = FastAPI()

web_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


warnings.filterwarnings(
    "ignore",
    message="`torch_dtype` is deprecated",
)
warnings.filterwarnings(
    "ignore",
    message="Using `chunk_length_s` is very experimental",
)
warnings.filterwarnings(
    "ignore",
    message="Using custom `forced_decoder_ids`",
)


def _format_srt_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    ms = int(round(seconds * 1000))
    s = (ms // 1000) % 60
    m = (ms // (1000 * 60)) % 60
    h = ms // (1000 * 60 * 60)
    ms = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _normalize_punctuation(text: str) -> str:
    for p in [".", ",", "!", "?", ":", ";"]:
        text = text.replace(f" {p}", p)
    return text.strip()


def _chunks_to_segments(
    chunks: list[dict],
    max_gap: float = 0.8,
) -> list[dict]:
    segments: list[dict] = []
    words: list[str] = []
    start = None
    last_end = None

    def flush(end_time: float):
        nonlocal words, start, last_end
        if not words or start is None:
            words = []
            start = None
            last_end = None
            return
        text = _normalize_punctuation(" ".join(words))
        segments.append({"start": start, "end": end_time, "text": text})
        words = []
        start = None
        last_end = None

    for chunk in chunks:
        ts = chunk.get("timestamp") or (None, None)
        w_start, w_end = ts
        if w_start is None or w_end is None:
            continue
        text = (chunk.get("text") or "").strip()
        if not text:
            continue
        if start is None:
            start = w_start
        if last_end is not None and (w_start - last_end) > max_gap:
            flush(last_end)
            start = w_start
        words.append(text)
        last_end = w_end
        if text.endswith((".", "?", "!")):
            flush(last_end)

    if last_end is not None:
        flush(last_end)
    return segments


def _segments_to_srt(segments: list[dict]) -> str:
    lines: list[str] = []
    for i, seg in enumerate(segments, start=1):
        start = _format_srt_timestamp(seg["start"])
        end = _format_srt_timestamp(seg["end"])
        lines.append(f"{i}")
        lines.append(f"{start} --> {end}")
        lines.append(seg["text"])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def download_model():
    from huggingface_hub import snapshot_download

    snapshot_download("openai/whisper-large-v3", local_dir=MODEL_DIR)


image = (
    Image.from_registry(
        "nvidia/cuda:12.9.0-cudnn-devel-ubuntu24.04", add_python="3.11"
    )
    .apt_install("git", "ffmpeg", "clang", "g++")
    .pip_install(
        "torch==2.5.1",
        "transformers==4.57.3",
        "einops",
        "ninja",
        "packaging",
        "wheel",
        "fastapi",
        "python-multipart",
        "huggingface_hub",
        "hf-transfer~=0.1",
        "ffmpeg-python",
    )
    .run_commands(
        "python -m pip install --no-deps -v "
        f"{FLASH_ATTN_WHEEL} "
        "--log /tmp/flash_attn_install.log "
        "|| (cat /tmp/flash_attn_install.log && exit 1)",
        gpu="A10G",
    )
    .run_commands("tail -n 200 /tmp/flash_attn_install.log || true")
    .env(
        {
            "HF_HUB_ENABLE_HF_TRANSFER": "1",
            # Reduce CUDA fragmentation for long-form transcription
            "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
        }
    )
    .run_function(
        download_model,
    )
)

app = App("whisper-v3", image=image)


@app.cls(
    image=image,
    gpu="A10G",
    scaledown_window=40,
    min_containers=MIN_CONTAINERS,
    timeout=1800,
    startup_timeout=600,
)
@concurrent(max_inputs=80)
class WhisperV3:
    @enter()
    def setup(self):
        import torch
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
        from transformers.utils import logging as hf_logging

        hf_logging.set_verbosity_error()
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            cap = ".".join(map(str, torch.cuda.get_device_capability(0)))
            print(f"CUDA available: {name} (capability {cap})")
        else:
            print("CUDA not available in runtime container")
        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            MODEL_DIR,
            dtype=self.torch_dtype,
            use_safetensors=True,
            attn_implementation="flash_attention_2",
        )
        model.config.use_cache = False
        processor = AutoProcessor.from_pretrained(MODEL_DIR)
        model.to(self.device)
        if hasattr(model, "generation_config"):
            model.generation_config.forced_decoder_ids = None
            model.generation_config.task = "transcribe"
        self.pipe = pipeline(
            "automatic-speech-recognition",
            model=model,
            tokenizer=processor.tokenizer,
            feature_extractor=processor.feature_extractor,
            max_new_tokens=MAX_NEW_TOKENS,
            chunk_length_s=CHUNK_LENGTH_S,
            batch_size=BATCH_SIZE,
            dtype=self.torch_dtype,
            ignore_warning=True,
            device=0,
        )

    @method()
    def generate(
        self,
        audio: bytes,
        filename: str = "audio",
        task: str = "transcribe",
        language: str | None = None,
    ):
        import time
        from pathlib import Path

        suffix = Path(filename).suffix or ".audio"
        fp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        fp.write(audio)
        fp.close()
        start = time.time()
        generate_kwargs = {"task": task}
        if language:
            generate_kwargs["language"] = language
        output = self.pipe(
            fp.name,
            return_timestamps="chunk",
            generate_kwargs=generate_kwargs,
        )
        segments = _chunks_to_segments(output.get("chunks", []))
        srt = _segments_to_srt(segments)
        elapsed = time.time() - start
        return {
            "output": output,
            "segments": segments,
            "srt": srt,
            "task": task,
            "language": language,
            "elapsed": elapsed,
        }


@web_app.post("/transcribe")
async def transcribe(request: Request):
    print("Received a request from", request.client)
    form = await request.form()
    upload = form["audio"]
    file_content = await upload.read()
    filename = getattr(upload, "filename", None) or "audio"
    task = (form.get("task") or "transcribe").strip().lower()
    language = (form.get("language") or "").strip().lower() or None
    target_language = (form.get("target_language") or "").strip().lower() or None
    if task not in {"transcribe", "translate"}:
        return responses.JSONResponse(
            content={"error": "Invalid task. Use 'transcribe' or 'translate'."},
            status_code=400,
        )
    if task == "translate" and target_language and target_language != "en":
        return responses.JSONResponse(
            content={
                "error": "Whisper translation only supports English output. Set target_language to 'en' or leave it blank."
            },
            status_code=400,
        )
    model = WhisperV3()
    call = model.generate.spawn(file_content, filename, task, language)
    return call.object_id


@web_app.get("/health")
def health():
    return {"status": "ok"}


@web_app.get("/stats")
def stats(request: Request):
    print("Received a request from", request.client)
    model = WhisperV3()
    f = model.generate
    return f.get_current_stats()


@web_app.post("/call_id")
async def get_completion(request: Request):
    form = await request.form()
    call_id = form["call_id"]
    f = FunctionCall.from_id(call_id)
    try:
        result = f.get(timeout=0)
    except TimeoutError:
        return responses.JSONResponse(
            content="Result did not finish processing.", status_code=202
        )
    return result


@app.function()
@concurrent(max_inputs=4)
@asgi_app()
def entrypoint():
    return web_app
