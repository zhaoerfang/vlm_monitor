import requests
import base64
import json
import concurrent.futures
from typing import List, Dict, Any
import time
import cv2
import numpy as np
from typing import Optional, Dict, List

class QwenVLClient:
    def __init__(self, api_url: str, api_key: str, max_retries: int = 3):
        self.api_url = api_url
        self.api_key = api_key
        self.max_retries = max_retries
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    def _encode_image(self, image: np.ndarray) -> str:
        """将OpenCV图像编码为base64字符串"""
        _, buffer = cv2.imencode('.jpg', image)
        return base64.b64encode(buffer).decode('utf-8')

    def analyze_image(
        self,
        image: np.ndarray,
        tasks: List[str] = ["object_detection"],
        confidence_threshold: float = 0.7
    ) -> Optional[Dict]:
        """分析单帧图像"""
        results = self.analyze_images([image], tasks, confidence_threshold)
        return results[0] if results else None

    def analyze_images(
        self,
        images: List[np.ndarray],
        tasks: List[str] = ["object_detection"],
        confidence_threshold: float = 0.7,
        max_workers: int = 5
    ) -> List[Optional[Dict]]:
        """批量分析多帧图像"""
        # Helper function to encode and send, making it easier to manage with executor
        def encode_and_send(image_to_process: np.ndarray) -> Optional[Dict]:
            try:
                payload = {
                    "image": self._encode_image(image_to_process),
                    "tasks": tasks,
                    "params": {
                        "confidence_threshold": confidence_threshold
                    }
                }
                return self._send_request(payload)
            except Exception as e:
                # Log error or handle as appropriate for a single image failure
                # For now, returning a dict with error, similar to existing partial failure handling
                return {"error": str(e), "status": "encoding_or_request_failed"}

        results: List[Optional[Dict]] = [None] * len(images) # Pre-allocate for ordered results
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit tasks and store futures in a list to maintain order
            future_to_idx = {executor.submit(encode_and_send, images[i]): i for i in range(len(images))}

            for future in concurrent.futures.as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    # This catches exceptions from the encode_and_send task itself if not caught within
                    results[idx] = {"error": str(e), "status": "task_execution_failed"}
            
        return results

    def _send_request(self, payload: Dict) -> Dict:
        """发送API请求"""
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.api_url,
                    headers=self.headers,
                    data=json.dumps(payload),
                    timeout=10
                )
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                if attempt == self.max_retries - 1:
                    raise
                time.sleep(1 * (attempt + 1))
        return {}

    def draw_results(self, image: np.ndarray, results: Dict) -> np.ndarray:
        """在图像上绘制检测结果"""
        if not results or "objects" not in results:
            return image

        output = image.copy()
        for obj in results["objects"]:
            label = obj.get("label", "unknown")
            confidence = obj.get("confidence", 0)
            bbox = obj.get("bbox", [])
            
            if len(bbox) == 4:
                x1, y1, x2, y2 = map(int, bbox)
                cv2.rectangle(output, (x1, y1), (x2, y2), (0, 255, 0), 2)
                text = f"{label}: {confidence:.2f}"
                cv2.putText(output, text, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        return output

if __name__ == "__main__":
    # 示例用法
    client = QwenVLClient(
        api_url="https://api.qwen-vl.example.com/v1/analyze",
        api_key="your_api_key_here"
    )

    # 测试图像
    test_image = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(test_image, "Test Image", (50, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

    try:
        results = client.analyze_image(test_image)
        print("分析结果:", json.dumps(results, indent=2))
        
        if results:
            visualized = client.draw_results(test_image, results)
            cv2.imshow("Results", visualized)
            cv2.waitKey(0)
    except Exception as e:
        print(f"API调用失败: {str(e)}")