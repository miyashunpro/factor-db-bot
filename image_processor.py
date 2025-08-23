import cv2
import numpy as np
from google.cloud import vision
import io
import re
from thefuzz import fuzz
import config

def load_texts_from_google_api(image_path):
    client = vision.ImageAnnotatorClient()
    with io.open(image_path, 'rb') as image_file: content = image_file.read()
    image = vision.Image(content=content)
    response = client.text_detection(image=image)
    if response.error.message: raise Exception(f"{response.error.message}")
    annotations = response.text_annotations
    if not annotations: return []
    img = cv2.imread(image_path)
    if img is None: return []
    img_width = img.shape[1]
    center_x = img_width * config.COLUMN_DIVIDER_RATIO
    all_words = []
    for text in annotations[1:]:
        vertices = text.bounding_poly.vertices
        all_words.append({'text': text.description, 'y_center': (vertices[0].y + vertices[2].y) / 2, 'x_start': vertices[0].x, 'bbox': ((vertices[0].x, vertices[0].y), (vertices[2].x, vertices[2].y))})
    reconstructed_texts = []
    for column_words in [[w for w in all_words if (w['bbox'][0][0] + w['bbox'][1][0]) / 2 < center_x], [w for w in all_words if (w['bbox'][0][0] + w['bbox'][1][0]) / 2 >= center_x]]:
        if not column_words: continue
        column_words.sort(key=lambda w: w['y_center'])
        lines = []
        if column_words:
            current_line = [column_words[0]]
            for word in column_words[1:]:
                if abs(word['y_center'] - current_line[-1]['y_center']) < 20: current_line.append(word)
                else: lines.append(current_line); current_line = [word]
            lines.append(current_line)
        for line in lines:
            line.sort(key=lambda w: w['x_start'])
            line_text = "".join([w['text'] for w in line])
            x_starts=[w['bbox'][0][0] for w in line]; y_starts=[w['bbox'][0][1] for w in line]
            x_ends=[w['bbox'][1][0] for w in line]; y_ends=[w['bbox'][1][1] for w in line]
            top_left=(min(x_starts), min(y_starts)); bottom_right=(max(x_ends), max(y_ends))
            reconstructed_texts.append({'text': line_text, 'bbox': (top_left, bottom_right), 'y_center': (top_left[1] + bottom_right[1]) / 2})
    return reconstructed_texts


def get_all_stars(image_path, min_star_area=50):
    img = cv2.imread(image_path)
    if img is None: return []
    image_height, _, _ = img.shape
    FACTOR_AREA_Y_START = image_height * 0.2; FACTOR_AREA_Y_END = image_height
    LOWER_YELLOW = np.array([21, 57, 116]); UPPER_YELLOW = np.array([31, 255, 255])
    img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(img_hsv, LOWER_YELLOW, UPPER_YELLOW)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    star_boxes = []
    for cnt in contours:
        if cv2.contourArea(cnt) < min_star_area: continue
        x, y, w, h = cv2.boundingRect(cnt)
        if not (FACTOR_AREA_Y_START < y < FACTOR_AREA_Y_END): continue
        star_boxes.append({'bbox': (x, y, w, h)})
    return star_boxes


def calculate_dynamic_min_star_area(all_texts, image_height):
    factor_texts = [t for t in all_texts if t['y_center'] > image_height * 0.35]
    if not factor_texts: return 50
    heights = [t['bbox'][1][1] - t['bbox'][0][1] for t in factor_texts]
    if not heights: return 50
    median_height = sorted(heights)[len(heights) // 2]
    reasonable_heights = [h for h in heights if median_height * 0.5 < h < median_height * 1.5]
    if not reasonable_heights: reasonable_heights = heights
    avg_height = sum(reasonable_heights) / len(reasonable_heights)
    calculated_area = (avg_height * avg_height) * 0.3
    min_area = max(15, calculated_area)
    print(f"動的に算出した星の最小面積: {min_area:.2f} (基準の文字高: {avg_height:.2f}px)")
    return min_area    


def normalize_text(text):
    if not isinstance(text, str): return ""
    return re.sub(r'[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', '', text).lower()

def classify_factor_by_id(ocr_text, factor_name_to_id, threshold=85):
    normalized_ocr_text = normalize_text(ocr_text)
    if not normalized_ocr_text: return None
    best_match_name, highest_score = None, 0
    for name in factor_name_to_id.keys():
        score = fuzz.ratio(normalized_ocr_text, normalize_text(name))
        if score > highest_score:
            highest_score, best_match_name = score, name
    if highest_score >= threshold:
        return factor_name_to_id.get(best_match_name)
    return None

def classify_character_name_by_id(all_texts, image_height, char_name_to_id, threshold=85):
    header_y_limit = image_height * 0.35 
    header_texts = [t['text'] for t in all_texts if t['y_center'] < header_y_limit]
    name_candidates = []
    for text in header_texts:
        if any(noise in text for noise in ["の因子", "育成", "[", "]", "評価"]):
            continue
        if len(text) < 2:
            continue
        name_candidates.append(text)
    if not name_candidates:
        return "不明"
    best_match_char, highest_score = "不明", 0
    char_names = list(char_name_to_id.keys())
    for candidate in name_candidates:
        for char_name in char_names:
            normalized_candidate = normalize_text(candidate)
            normalized_char_name = normalize_text(char_name)
            score = fuzz.ratio(normalized_candidate, normalized_char_name)
            if score > highest_score:
                highest_score, best_match_char = score, char_name
    return best_match_char if highest_score >= threshold else "不明"


def get_image_dimensions(image_path):
    img = cv2.imread(image_path)
    if img is None:
        return 0, 0
    height, width, _ = img.shape
    return height, width

def extract_factor_details(all_texts, all_stars, image_dims, factor_name_to_id):
    image_height, image_width = image_dims
    factor_details = []
    
    # 画像認識のパラメータをconfigから読み込む
    params = {
        'vt_px': image_height * config.VERTICAL_TOLERANCE_RATIO,
        'vo_px': image_height * config.VERTICAL_OFFSET_RATIO,
        'l_start_px': int(image_width * config.LEFT_COLUMN_SEARCH_START_RATIO),
        'l_end_px': int(image_width * (config.LEFT_COLUMN_SEARCH_START_RATIO + config.LEFT_COLUMN_SEARCH_WIDTH_RATIO)),
        'r_start_px': int(image_width * config.RIGHT_COLUMN_SEARCH_START_RATIO),
        'r_end_px': int(image_width * (config.RIGHT_COLUMN_SEARCH_START_RATIO + config.RIGHT_COLUMN_SEARCH_WIDTH_RATIO))
    }

    for text_info in all_texts:
        factor_id = classify_factor_by_id(text_info['text'], factor_name_to_id)
        if factor_id:
            text_x_center = (text_info['bbox'][0][0] + text_info['bbox'][1][0]) / 2
            star_check_y = text_info['y_center'] + params['vo_px']
            star_count = 0
            
            # テキストが左の列にあるか右の列にあるかで、星を探す範囲を変える
            if text_x_center < (image_width * config.COLUMN_DIVIDER_RATIO):
                star_count = sum(1 for star in all_stars if params['l_start_px'] < (star['bbox'][0] + star['bbox'][2] / 2) < params['l_end_px'] and abs(star_check_y - (star['bbox'][1] + star['bbox'][3] / 2)) < params['vt_px'])
            else:
                star_count = sum(1 for star in all_stars if params['r_start_px'] < (star['bbox'][0] + star['bbox'][2] / 2) < params['r_end_px'] and abs(star_check_y - (star['bbox'][1] + star['bbox'][3] / 2)) < params['vt_px'])
            
            if star_count > 0:
                factor_details.append({'id': factor_id, 'stars': star_count, 'y_pos': text_info['y_center']})
                
    return factor_details    
