from typing import List, Optional, Callable, Dict, Any
import os
from pathlib import Path
import fal_client
import requests

DEFAULT_FAL_MODEL = "fal-ai/flux/dev"


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
    model: str = DEFAULT_FAL_MODEL,
    size: str = "portrait_16_9",
    output_dir: str = "../data/outputs"
) -> List[str]:
    """
    fal.ai만 사용해서 이미지 생성
    """
    generated = generate_images_with_fal(prompts, model=model, size=size, output_dir=output_dir)
    return [item.get("path") or item.get("url") for item in generated]


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
    return generate_images_with_fal(
        prompts,
        progress_callback=progress_callback,
        model=model or DEFAULT_FAL_MODEL,
        size=size,
        output_dir=output_dir
    )


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
