from typing import List, Optional, Callable, Dict, Any
import os
from pathlib import Path

# ↓ 필요한 라이브러리
import torch
from diffusers import StableDiffusionPipeline
import fal_client
import requests

# 전역 파이프라인 캐시
_PIPE = None
DEFAULT_FAL_MODEL = "fal-ai/flux/dev"


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


def _download_to_path(url: str, output_dir: str, filename: str) -> str:
    """원격 이미지를 다운로드해 지정 경로에 저장"""
    os.makedirs(output_dir, exist_ok=True)
    path = Path(output_dir) / filename
    resp = requests.get(url)
    resp.raise_for_status()
    with open(path, "wb") as f:
        f.write(resp.content)
    return str(path)


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
    # fal.ai 모델을 명시적으로 요청한 경우
    if model.startswith("fal") or "fal-ai" in model or "flux" in model:
        generated = generate_images_with_fal(prompts, model=model, size=size, output_dir=output_dir)
        return [item.get("path") or item.get("url") for item in generated]

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


def generate_images_with_fal(
    prompts: List[str],
    progress_callback: Optional[Callable[[str, float, str], None]] = None,
    *,
    model: str = DEFAULT_FAL_MODEL,
    size: str = "portrait_16_9",
    steps: int = 28,
    output_dir: str = "../data/outputs"
) -> List[Dict[str, Any]]:
    """
    fal.ai(Flux)를 사용한 이미지 생성기. 결과는 url/path/prompt를 담은 dict 리스트.
    """
    os.makedirs(output_dir, exist_ok=True)

    if progress_callback:
        progress_callback("loading_model", 0.0, "fal.ai 준비 중...")
        progress_callback("loading_model", 5.0, "세션 생성 중...")

    total = len(prompts)
    results: List[Dict[str, Any]] = []

    for i, prompt in enumerate(prompts, start=1):
        if progress_callback:
            progress_callback("generating", (i - 1) / total * 100, f"이미지 {i}/{total} 생성 중...")
        resp = fal_client.subscribe(
            model,
            arguments={
                "prompt": prompt,
                "image_size": size,
                "num_inference_steps": steps
            }
        )
        image_url = resp["images"][0]["url"]
        local_path = _download_to_path(image_url, output_dir, f"image_{i:02d}.png")
        results.append({
            "index": i - 1,
            "prompt": prompt,
            "url": image_url,
            "path": local_path
        })
        if progress_callback:
            progress_callback("generating", (i / total) * 100, f"이미지 {i}/{total} 생성 완료")

    if progress_callback:
        progress_callback("completed", 100.0, "모든 이미지 생성 완료")

    return results


def generate_images_with_progress(
    prompts: List[str],
    progress_callback: Optional[Callable[[str, float, str], None]] = None,
    *,
    model: str = "andite/anything-v5.0",
    size: str = "512x512",
    output_dir: str = "../data/outputs"
) -> List[Dict[str, Any]]:
    """
    진행 상황 콜백을 지원하는 이미지 생성기.
    progress_callback(status, progress, message) 형태로 호출됨.
    """
    # fal.ai 모델을 사용할 경우 전용 경로로 분기
    if model.startswith("fal") or "fal-ai" in model or "flux" in model:
        return generate_images_with_fal(
            prompts,
            progress_callback=progress_callback,
            model=model or DEFAULT_FAL_MODEL,
            size=size,
            output_dir=output_dir
        )

    os.makedirs(output_dir, exist_ok=True)

    # 모델 로드 단계
    if progress_callback:
        progress_callback("loading_model", 0.0, "모델 확인 중...")

    pipe = _get_pipe(model)

    if progress_callback:
        progress_callback("loading_model", 100.0, "모델 준비 완료")

    total = len(prompts)
    saved_paths: List[Dict[str, Any]] = []
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
        saved_paths.append({"index": i - 1, "prompt": prompt, "path": str(file_path)})

        if progress_callback:
            progress_callback("generating", (i / total) * 100, f"이미지 {i}/{total} 생성 완료")

    if progress_callback:
        progress_callback("completed", 100.0, "모든 이미지 생성 완료")

    return saved_paths


def regenerate_single_image(
    prompt: str,
    index: int,
    *,
    model: str = DEFAULT_FAL_MODEL,
    size: str = "portrait_16_9",
    steps: int = 28,
    output_dir: str = "../data/outputs"
) -> Dict[str, Any]:
    """단일 프롬프트만 다시 생성 (fal.ai 기반)"""
    results = generate_images_with_fal(
        [prompt],
        progress_callback=None,
        model=model,
        size=size,
        steps=steps,
        output_dir=output_dir
    )
    # index를 요청값으로 덮어쓰면 기존 순서 유지 가능
    if results:
        results[0]["index"] = index
    return results[0] if results else {}
