import torch
import os
from PIL import Image

# 클래스 이름 설정
CLASS_NAMES = {'body': 'bottle', 'cap': 'cap', 'label': 'label'}

class GreenEyeDetector:
    def __init__(self, model_path):
        self.model = self._load_model(model_path)

    def _load_model(self, path):
        """모델 로드"""
        try:
            model = torch.hub.load('ultralytics/yolov5', 'custom', path=path)
            
            # [추가 설정] 중복 탐지를 줄이기 위한 모델 설정
            model.conf = 0.3  # 정확도 40% 미만은 아예 무시 (기존 0.25)
            model.iou = 0.45  # 박스가 겹칠 때 하나로 합치는 기준 (NMS)
            
            return model
        except Exception as e:
            print(f"❌ Model Load Error: {e}")
            return None

    def analyze(self, image_path, filename, save_dir):
        """이미지를 분석하고 결과(점수, 상태 등)를 반환"""
        if self.model is None:
            return 0, "모델 로드 실패", [], 'invalid', filename, {}, []

        # 1. 추론 및 이미지 저장
        results = self.model(image_path)
        results.render()
        
        annotated_filename = 'annotated_' + filename
        save_path = os.path.join(save_dir, annotated_filename)
        Image.fromarray(results.ims[0]).save(save_path)

        # 2. 데이터 추출 (Pandas DataFrame)
        detections = results.pandas().xyxy[0]

        # ========================================================
        # [핵심 수정] 중복 제거 로직 추가
        # ========================================================
        if not detections.empty:
            # 1) 정확도(confidence) 순서로 내림차순 정렬 (높은게 위로)
            detections = detections.sort_values('confidence', ascending=False)
            
            # 2) 'name'(클래스명)이 같은 것 중 가장 위에 있는(점수 높은) 것만 남김
            detections = detections.drop_duplicates(subset=['name'], keep='first')
        # ========================================================

        detected_names = []
        valid_detections = []

        for _, row in detections.iterrows():
            # (모델 설정에서 conf=0.4로 올렸으므로 여기서는 이중 체크 안 해도 되지만 안전하게 유지)
            detected_names.append(row['name'])
            valid_detections.append({
                'class': row['name'],
                'confidence': row['confidence'],
                'conf_percent': round(row['confidence'] * 100, 1)
            })

        # 3. O/X 상태표 생성
        detect_status = {k: ('O' if v in detected_names else 'X') for k, v in CLASS_NAMES.items()}

        # 4. 유효성 검사 (몸통 필수)
        if detect_status['body'] == 'X':
            return 0, "페트병이 인식되지 않았습니다. 올바른 이미지를 넣어주세요.", [], 'invalid', annotated_filename, detect_status, []

        # 5. 리워드 포인트 계산 (10점 만점 - 감점 2점씩)
        reward_points = 10
        detected_items = []
        DEDUCTION = 2

        if detect_status['cap'] == 'O':
            reward_points -= DEDUCTION
            detected_items.append(f"뚜껑 감지 (-{DEDUCTION}P)")
        
        if detect_status['label'] == 'O':
            reward_points -= DEDUCTION
            detected_items.append(f"라벨 감지 (-{DEDUCTION}P)")

        if reward_points < 0: reward_points = 0

        # 6. 결과 메시지 설정
        result_status = 'pass'
        if reward_points < 10:
            message = f"분석 완료! (일부 감점: {reward_points} 포인트 적립)"
        else:
            message = "완벽합니다! 10 포인트가 적립됩니다."

        return reward_points, message, detected_items, result_status, annotated_filename, detect_status, valid_detections