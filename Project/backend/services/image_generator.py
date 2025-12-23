from typing import List, Optional, Callable
import os
from pathlib import Path

# ↓ 필요한 라이브러리
import torch
from diffusers import StableDiffusionPipeline

# 전역 파이프라인 캐시
_PIPE = None


def _get_pipe(model_id: str = "andite/anything-v5.0"):
    """한 번만 로드해서 전역으로 쓰는 파이프라인"""
    global _PIPE
    if _PIPE is not None:
        return _PIPE

    # 여기서 from_pretrained 할 때 한 번만 다운로드되고 이후엔 캐시에서 불러옴
    pipe = StableDiffusionPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.float16,   # 8GB VRAM이면 반정도는 줄여주자
        safety_checker=None
    )

    # GPU 있으면 올리고, 없으면 CPU로
    if torch.cuda.is_available():
        pipe = pipe.to("cuda")
    else:
        pipe = pipe.to("cpu")

    # 메모리 절약
    pipe.enable_attention_slicing()

    _PIPE = pipe
    return _PIPE


def _parse_size(size_str: str):
    """'512x512' -> (512, 512)"""
    try:
        w, h = size_str.lower().split("x")
        return int(w), int(h)
    except Exception:
        return 512, 512


def generate_images(
    prompts: List[str],
    *,
    model: str = "andite/anything-v5.0",
    size: str = "512x512",
    output_dir: str = "../data/outputs"
) -> List[str]:
    """
    실제로 diffusers를 사용해서 이미지 생성하는 버전
    """
    os.makedirs(output_dir, exist_ok=True)
    pipe = _get_pipe(model)

    width, height = _parse_size(size)
    saved_paths: List[str] = []

    negative_prompt = "lowres, blurry, bad anatomy, bad hands, extra fingers, text, watermark"

    for i, prompt in enumerate(prompts, start=1):
        result = pipe(
            prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            num_inference_steps=25
        )
        image = result.images[0]

        file_path = Path(output_dir) / f"image_{i:02d}.png"
        image.save(str(file_path))
        saved_paths.append(str(file_path))

    return saved_paths


def generate_images_with_progress(
    prompts: List[str],
    progress_callback: Optional[Callable[[str, float, str], None]] = None,
    *,
    model: str = "andite/anything-v5.0",
    size: str = "512x512",
    output_dir: str = "../data/outputs"
) -> List[str]:
    """
    진행 상황 콜백을 지원하는 이미지 생성기.
    progress_callback(status, progress, message) 형태로 호출됨.
    """
    os.makedirs(output_dir, exist_ok=True)

    # 모델 로드 단계
    if progress_callback:
        progress_callback("loading_model", 0.0, "모델 확인 중...")

    pipe = _get_pipe(model)

    if progress_callback:
        progress_callback("loading_model", 100.0, "모델 준비 완료")

    total = len(prompts)
    saved_paths: List[str] = []
    width, height = _parse_size(size)
    negative_prompt = "lowres, blurry, bad anatomy, bad hands, extra fingers, text, watermark"

    for i, prompt in enumerate(prompts, start=1):
        if progress_callback:
            progress = (i - 1) / total * 100
            progress_callback("generating", progress, f"이미지 {i}/{total} 생성 중...")

        result = pipe(
            prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            num_inference_steps=25
        )
        image = result.images[0]

        file_path = Path(output_dir) / f"image_{i:02d}.png"
        image.save(str(file_path))
        saved_paths.append(str(file_path))

        if progress_callback:
            progress_callback("generating", (i / total) * 100, f"이미지 {i}/{total} 생성 완료")

    if progress_callback:
        progress_callback("completed", 100.0, "모든 이미지 생성 완료")

    return saved_paths
