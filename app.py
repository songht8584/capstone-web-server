import os
import hashlib
import json
import math
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# 모듈 임포트
import database as db_module
from detector import GreenEyeDetector

# --- 1. 앱 설정 ---
app = Flask(__name__)
app.secret_key = os.urandom(24)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
RESULT_FOLDER = os.path.join(BASE_DIR, 'static', 'results')
MODEL_PATH = r'C:/Users/dilab/Desktop/sht/캡스톤/gr/best.pt'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['RESULT_FOLDER'] = RESULT_FOLDER

# 폴더 자동 생성
for folder in [UPLOAD_FOLDER, RESULT_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# DB 및 모델 초기화
db_module.init_db()
detector = GreenEyeDetector(MODEL_PATH)

ADMIN_USER = 'admin'
ADMIN_PASS = 'qwe123'

# DB 연결 종료 핸들러 등록
app.teardown_appcontext(db_module.close_connection)

# --- 2. 헬퍼 함수 ---
def reset_folders():
    """업로드 및 결과 폴더 비우기"""
    for folder in [app.config['UPLOAD_FOLDER'], app.config['RESULT_FOLDER']]:
        if os.path.exists(folder):
            for f in os.listdir(folder):
                fp = os.path.join(folder, f)
                try:
                    if os.path.isfile(fp): os.unlink(fp)
                except: pass
    db_module.reset_db_data() # DB 히스토리도 삭제
    print(" * 데이터 및 폴더 초기화 완료")

# --- 3. 라우트 (페이지) ---

@app.route('/')
def index():
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    points = 0
    if not session.get('is_admin'):
        db = db_module.get_db()
        user = db.execute('SELECT points FROM user WHERE id = ?', (session['user_id'],)).fetchone()
        if user: points = user['points']
            
    return render_template('dashboard.html', points=points)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session: return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # 관리자 로그인
        if username == ADMIN_USER and password == ADMIN_PASS:
            reset_folders()
            session.update({'logged_in': True, 'user_id': 0, 'username': 'Admin', 'is_admin': True})
            return redirect(url_for('index'))

        # 일반 사용자 로그인
        db = db_module.get_db()
        user = db.execute('SELECT * FROM user WHERE username = ?', (username,)).fetchone()

        if user is None: # 회원가입
            pw_hash = generate_password_hash(password)
            cur = db.execute('INSERT INTO user (username, password_hash) VALUES (?, ?)', (username, pw_hash))
            db.commit()
            session.update({'logged_in': True, 'user_id': cur.lastrowid, 'username': username, 'is_admin': False})
            flash('회원가입 환영합니다!', 'success')
            return redirect(url_for('index'))
        
        elif check_password_hash(user['password_hash'], password): # 성공
            session.update({'logged_in': True, 'user_id': user['id'], 'username': user['username'], 'is_admin': False})
            return redirect(url_for('index'))
        
        else:
            flash('비밀번호가 틀렸습니다.', 'danger')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/inspection')
def inspection():
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    today_count = 0
    if not session.get('is_admin'):
        today_str = datetime.now().strftime("%Y-%m-%d")
        db = db_module.get_db()
        res = db.execute("SELECT COUNT(*) FROM history WHERE username=? AND upload_date LIKE ?", 
                         (session['username'], f"{today_str}%")).fetchone()
        today_count = res[0]
        
    return render_template('inspection.html', today_count=today_count, max_count=5)

@app.route('/history')
def history():
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    # 1. 현재 페이지 번호 받기 (기본값 1)
    page = request.args.get('page', 1, type=int)
    per_page = 20  # 페이지당 보여줄 개수
    username = session['username']

    # 2. DB에서 데이터 가져오기 (모듈 사용)
    total_count = db_module.get_history_count(username) # 전체 개수
    rows = db_module.get_history_paginated(username, page, per_page) # 해당 페이지 데이터 20개

    # 3. 전체 페이지 수 계산 (올림 처리)
    total_pages = math.ceil(total_count / per_page)

    # 4. 데이터 가공 (JSON 파싱)
    history_list = []
    for row in rows:
        data = dict(row)
        data['details'] = json.loads(data['details_json']) if data['details_json'] else []
        history_list.append(data)
        
    return render_template('history.html', 
                           history_list=history_list,
                           page=page,
                           total_pages=total_pages,
                           total_count=total_count)
@app.route('/shop')
def shop():
    if not session.get('logged_in'): return redirect(url_for('login'))
    
    points = 0
    if not session.get('is_admin'):
        db = db_module.get_db()
        user = db.execute('SELECT points FROM user WHERE id = ?', (session['user_id'],)).fetchone()
        if user: points = user['points']

    return render_template('shop.html', points=points)

@app.route('/upload', methods=['POST'])
def upload_file():
    if not session.get('logged_in'): return redirect(url_for('login'))
    if 'file' not in request.files or request.files['file'].filename == '':
        return redirect(request.url)

    file = request.files['file']
    image_data = file.read()
    filename = secure_filename(file.filename) 
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    with open(filepath, 'wb') as f: f.write(image_data)
        
    current_hash = hashlib.sha256(image_data).hexdigest()
    db = db_module.get_db()
    
    # 중복 체크
    exist = db.execute('SELECT * FROM history WHERE image_hash = ? AND username = ?', 
                       (current_hash, session['username'])).fetchone()
    if exist:
        return render_template('result.html', score=None, message="이미 처리된 이미지입니다.", 
                               result_status='duplicate', uploaded_image=filename)
    
    # [핵심] Detector 모듈을 사용하여 분석 수행
    results = detector.analyze(filepath, filename, app.config['RESULT_FOLDER'])
    # 결과 언패킹 (reward_points, message, detected_items, result_status, annotated_filename, detect_status, valid_detections)
    reward_points, message, detected_items, result_status, annotated_filename, detect_status, valid_detections = results
    
    # 포인트 지급
    if result_status == 'pass' and not session.get('is_admin'):
        db.execute('UPDATE user SET points = points + ? WHERE id = ?', (reward_points, session['user_id']))

    # 기록 저장
    try:
        db.execute('''
            INSERT INTO history (username, upload_date, org_filename, res_filename, score, result_status, details_json, image_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            session.get('username'),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            filename,
            annotated_filename,
            reward_points,
            result_status,
            json.dumps(valid_detections),
            current_hash
        ))
        db.commit()
    except Exception as e:
        print(f"DB Error: {e}")

    return render_template('result.html', 
                           score=reward_points, 
                           message=message, 
                           detected_items=detected_items,
                           result_status=result_status,
                           uploaded_image=annotated_filename,
                           detect_status=detect_status)

@app.route('/uploads/<filename>')
def send_uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)