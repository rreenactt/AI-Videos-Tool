import os
import requests
import fal_client
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

def generate_and_save_image(prompt, filename):
    print(f"🎨 이미지 생성 요청 중: {prompt}")
    
    # 1. fal.ai API 호출
    # 쇼츠 제작에는 퀄리티가 좋은 'flux/dev' 모델을 추천합니다.
    result = fal_client.subscribe(
        "fal-ai/flux/dev",
        arguments={
            "prompt": prompt,
            "image_size": "portrait_16_9", # 쇼츠용 세로 비율
            "num_inference_steps": 28
        }
    )

    # 2. 결과 URL 확인
    image_url = result['images'][0]['url']
    print(f"✅ 생성 완료! URL: {image_url}")

    # 3. 이미지 다운로드 및 저장
    response = requests.get(image_url)
    if response.status_code == 200:
        with open(filename, 'wb') as f:
            f.write(response.content)
        print(f"💾 저장 성공: {filename}")
    else:
        print("❌ 이미지 다운로드 실패")

# 사용 예시
if __name__ == "__main__":
    scenario_prompt = "A cute 3D character developer working on a laptop, bright studio lighting, pixar style, 8k resolution"
    generate_and_save_image(scenario_prompt, "shorts_scene_1.png")