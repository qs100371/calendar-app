import sqlite3
import os
import requests
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, jsonify, g, session, redirect, url_for
import calendar
from apscheduler.schedulers.background import BackgroundScheduler
from werkzeug.security import generate_password_hash, check_password_hash
import atexit

app = Flask(__name__)

# ==================== SECRET_KEY ====================
DEFAULT_SECRET = 'dev-secret-key-change-me-in-production'
SECRET_KEY = os.environ.get('SECRET_KEY', DEFAULT_SECRET)
app.secret_key = SECRET_KEY

if SECRET_KEY == DEFAULT_SECRET:
    print("=" * 60)
    print("⚠️  警告：正在使用默认 SECRET_KEY")
    print("    部署到公网前请务必设置环境变量 SECRET_KEY")
    print("=" * 60)
else:
    print(f"✅ SECRET_KEY 已从环境变量加载（长度 {len(SECRET_KEY)}）")

DATABASE = os.environ.get('DATABASE_PATH', 'calendar.db')
DEFAULT_PASSWORD = '123456'

# 待办/打卡默认提醒时间
DEFAULT_TODO_REMIND_TIMES = "09:00,15:00"

# ==================== 数据库 ====================
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0,
                created_at TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                title TEXT NOT NULL,
                type TEXT DEFAULT 'event',
                is_done INTEGER DEFAULT 0,
                reminder_time TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS habit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER,
                date TEXT,
                status INTEGER DEFAULT 1
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')

        # 迁移 events
        cursor.execute("PRAGMA table_info(events)")
        cols = [r[1] for r in cursor.fetchall()]
        if 'user_id' not in cols:
            cursor.execute("ALTER TABLE events ADD COLUMN user_id INTEGER")
        if 'start_date' not in cols:
            cursor.execute("ALTER TABLE events ADD COLUMN start_date TEXT")
        if 'end_date' not in cols:
            cursor.execute("ALTER TABLE events ADD COLUMN end_date TEXT")

        # 迁移 habit_logs
        cursor.execute("PRAGMA table_info(habit_logs)")
        cols = [r[1] for r in cursor.fetchall()]
        if 'user_id' not in cols:
            cursor.execute("ALTER TABLE habit_logs ADD COLUMN user_id INTEGER")

        # 迁移 settings（改为按用户）
        cursor.execute("PRAGMA table_info(settings)")
        cols = [r[1] for r in cursor.fetchall()]
        if 'user_id' not in cols:
            cursor.execute("DROP TABLE IF EXISTS settings")
            cursor.execute('''
                CREATE TABLE settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT,
                    UNIQUE(user_id, key)
                )
            ''')
        db.commit()

# ==================== 设置读写 ====================
def get_setting(key, default="", user_id=None):
    with app.app_context():
        db = get_db()
        if user_id is None:
            user_id = session.get('user_id')
        if not user_id:
            return default
        row = db.execute("SELECT value FROM settings WHERE user_id = ? AND key = ?",
                         (user_id, key)).fetchone()
        return row['value'] if row else default

def set_setting(key, value, user_id=None):
    db = get_db()
    if user_id is None:
        user_id = session.get('user_id')
    if not user_id:
        return
    if value is None or str(value) == '':
        db.execute("DELETE FROM settings WHERE user_id = ? AND key = ?", (user_id, key))
    else:
        db.execute("INSERT OR REPLACE INTO settings (user_id, key, value) VALUES (?, ?, ?)",
                   (user_id, key, str(value)))
    db.commit()

# ==================== 装饰器 ====================
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        if not session.get('is_admin'):
            return jsonify({'error': '需要管理员权限'}), 403
        return f(*args, **kwargs)
    return wrapper

# ==================== 多渠道发送 ====================
def send_via_channel(channel, cfg, title, content):
    """统一发送入口，失败静默处理"""
    if not cfg:
        return
    try:
        if channel == 'wechat':
            # 企业微信机器人
            requests.post(cfg,
                          json={"msgtype": "text", "text": {"content": f"{title}\n{content}"}},
                          headers={'Content-Type': 'application/json'}, timeout=5)
        elif channel == 'dingtalk':
            # 钉钉机器人（使用"自定义关键词"模式，关键词包含"提醒"）
            requests.post(cfg,
                          json={"msgtype": "text", "text": {"content": f"{title}\n{content}"}},
                          headers={'Content-Type': 'application/json'}, timeout=5)
        elif channel == 'feishu':
            # 飞书机器人
            requests.post(cfg,
                          json={"msg_type": "text", "content": {"text": f"{title}\n{content}"}},
                          headers={'Content-Type': 'application/json'}, timeout=5)
        elif channel == 'bark':
            # Bark（iOS）：cfg 形如 https://api.day.app/xxxxx
            base = cfg.rstrip('/')
            requests.post(base,
                          json={"title": title, "body": content, "level": "timeSensitive"},
                          timeout=5)
        elif channel == 'ntfy':
            # ntfy（Android）：HTTP Header 不支持中文，把 title 拼进 body
            full_text = f"{title}\n{content}"
            requests.post(f"https://ntfy.sh/{cfg}",
                          data=full_text.encode('utf-8'),
                          headers={"Priority": "high", "Tags": "bell"},
                          timeout=5)
        print(f"[{channel}] 通知已发送: {title}")
    except Exception as e:
        print(f"[{channel}] 发送失败: {type(e).__name__}: {e}")

def get_user_channels(uid):
    return {
        'wechat':   get_setting('wechat_webhook', '',   user_id=uid),
        'dingtalk': get_setting('dingtalk_webhook', '', user_id=uid),
        'feishu':   get_setting('feishu_webhook', '',   user_id=uid),
        'bark':     get_setting('bark_url', '',         user_id=uid),
        'ntfy':     get_setting('ntfy_topic', '',       user_id=uid),
    }

def broadcast(uid, title, content):
    for ch, cfg in get_user_channels(uid).items():
        if cfg:
            send_via_channel(ch, cfg, title, content)

# ==================== 定时提醒 ====================
def check_reminders():
    """
    每分钟检查一次：
    A. 普通日程/待办：按事件自带的 reminder_time 提醒
    B. 待办 / 打卡：每天在用户设置的多个时间点（默认 09:00,15:00）汇总提醒
       - 打卡：当天已打卡则跳过
       - 待办：提醒时如果 is_done=1 则跳过
    """
    with app.app_context():
        now = datetime.now()
        current_date = now.strftime('%Y-%m-%d')
        current_time = now.strftime('%H:%M')
        db = get_db()

        # ---------- A. 按 reminder_time 提醒（排除 habit） ----------
        events = db.execute(
            """SELECT * FROM events 
               WHERE (date = ? OR (start_date <= ? AND end_date >= ?)) 
               AND reminder_time = ? 
               AND is_done = 0
               AND type != 'habit'""",
            (current_date, current_date, current_date, current_time)
        ).fetchall()

        for e in events:
            uid = e['user_id']
            if not uid:
                continue
            title = "⏰ 日程提醒"
            content = f"时间：{current_time}\n事项：{e['title']}"
            broadcast(uid, title, content)

        # ---------- B. 待办 / 打卡 每日汇总提醒 ----------
        user_ids = db.execute(
            """SELECT DISTINCT user_id FROM events 
               WHERE user_id IS NOT NULL 
                 AND type IN ('todo', 'habit')
                 AND is_done = 0"""
        ).fetchall()

        for row in user_ids:
            uid = row['user_id']
            times_str = get_setting('todo_remind_times', DEFAULT_TODO_REMIND_TIMES, user_id=uid)
            times = [t.strip() for t in times_str.split(',') if t.strip()]
            if current_time not in times:
                continue

            items = db.execute(
                """SELECT * FROM events 
                   WHERE user_id = ?
                     AND type IN ('todo', 'habit')
                     AND is_done = 0
                     AND start_date <= ? AND end_date >= ?""",
                (uid, current_date, current_date)
            ).fetchall()

            todo_lines = []
            habit_lines = []

            for item in items:
                if item['type'] == 'todo':
                    todo_lines.append(f"• [待办] {item['title']}")
                elif item['type'] == 'habit':
                    log = db.execute(
                        "SELECT status FROM habit_logs WHERE event_id = ? AND date = ? AND user_id = ?",
                        (item['id'], current_date, uid)
                    ).fetchone()
                    if log and log['status'] == 1:
                        continue  # 已完成，跳过
                    habit_lines.append(f"• [打卡] {item['title']}")

            if not todo_lines and not habit_lines:
                continue

            content = f"时间：{current_time}\n"
            if todo_lines:
                content += "今日待办：\n" + "\n".join(todo_lines) + "\n"
            if habit_lines:
                content += "今日打卡：\n" + "\n".join(habit_lines)

            broadcast(uid, "📋 每日提醒", content.strip())

scheduler = BackgroundScheduler()
scheduler.add_job(func=check_reminders, trigger="interval", minutes=1)
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

# ==================== 日历生成 ====================
def generate_calendar(year, month, term_start_date_str=None, start_monday=True, force_weeks=None):
    if start_monday:
        calendar.setfirstweekday(calendar.MONDAY)
    else:
        calendar.setfirstweekday(calendar.SUNDAY)

    first_day = datetime(year, month, 1)
    last_month = first_day - timedelta(days=1)
    next_month = (datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1))
    _, days_in_month = calendar.monthrange(year, month)
    days = []

    wd_first = first_day.weekday()
    if not start_monday:
        wd_first = (wd_first + 1) % 7

    for i in range(wd_first):
        d = last_month - timedelta(days=wd_first - i - 1)
        days.append({'date': d.strftime('%Y-%m-%d'), 'day': d.day, 'current_month': False})

    for i in range(1, days_in_month + 1):
        d = datetime(year, month, i)
        days.append({'date': d.strftime('%Y-%m-%d'), 'day': i, 'current_month': True})

    total = len(days)
    rem = total % 7
    if rem != 0:
        for i in range(7 - rem):
            d = next_month + timedelta(days=i)
            days.append({'date': d.strftime('%Y-%m-%d'), 'day': d.day, 'current_month': False})

    if force_weeks:
        target = force_weeks * 7
        if len(days) > target:
            days = days[:target]
        elif len(days) < target:
            last_date = datetime.strptime(days[-1]['date'], '%Y-%m-%d')
            for i in range(1, target - len(days) + 1):
                d = last_date + timedelta(days=i)
                days.append({'date': d.strftime('%Y-%m-%d'), 'day': d.day, 'current_month': False})

    term_monday = None
    if term_start_date_str:
        try:
            ts = datetime.strptime(term_start_date_str, '%Y-%m-%d')
            term_monday = ts - timedelta(days=ts.weekday())
        except ValueError:
            pass

    for day in days:
        cd = datetime.strptime(day['date'], '%Y-%m-%d')
        if term_monday:
            dn = (cd - term_monday).days
            wn = dn // 7 + 1
            day['week_label'] = f"第{wn}周" if wn > 0 else ""
        else:
            ys = datetime(cd.year, 1, 1)
            yfm = ys - timedelta(days=ys.weekday())
            dn = (cd - yfm).days
            wn = dn // 7 + 1
            day['week_label'] = f"第{wn}周"
    return days

# ==================== 登录 / 注册 ====================
@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        data = request.json
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = bool(user['is_admin'])
            return jsonify({'status': 'ok'})
        return jsonify({'error': '用户名或密码错误'}), 401
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    if len(username) < 2 or len(username) > 20:
        return jsonify({'error': '用户名长度需 2-20 字符'}), 400
    if len(password) < 4:
        return jsonify({'error': '密码至少 4 位'}), 400

    db = get_db()
    if db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
        return jsonify({'error': '用户名已存在'}), 400

    count = db.execute("SELECT COUNT(*) c FROM users").fetchone()['c']
    is_admin = 1 if count == 0 else 0

    db.execute("INSERT INTO users (username, password_hash, is_admin, created_at) VALUES (?, ?, ?, ?)",
               (username, generate_password_hash(password), is_admin, datetime.now().isoformat()))
    db.commit()
    return jsonify({'status': 'ok', 'is_admin': is_admin})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login_page'))

# ==================== 首页 ====================
@app.route('/')
@login_required
def index():
    now = datetime.now()
    year = request.args.get('year', now.year, type=int)
    month = request.args.get('month', now.month, type=int)
    force_weeks = request.args.get('weeks', None, type=int)
    uid = session['user_id']

    db = get_db()
    term_start_date_str = get_setting('term_start_date', '', user_id=uid) or None
    cal_days = generate_calendar(year, month, term_start_date_str, force_weeks=force_weeks)

    month_start = f"{year}-{month:02d}-01"
    month_end = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"

    events = db.execute(
        """SELECT * FROM events 
           WHERE user_id = ?
             AND ((date >= ? AND date < ?) 
                  OR (start_date <= ? AND end_date >= ?))""",
        (uid, month_start, month_end, month_end, month_start)
    ).fetchall()

    events_by_date = {}
    for e in events:
        e_dict = dict(e)
        if e['type'] in ('todo', 'habit') and e['start_date'] and e['end_date']:
            s = datetime.strptime(e['start_date'], '%Y-%m-%d')
            en = datetime.strptime(e['end_date'], '%Y-%m-%d')
            cur = s
            while cur <= en:
                ds = cur.strftime('%Y-%m-%d')
                if month_start <= ds < month_end:
                    events_by_date.setdefault(ds, []).append(e_dict)
                cur += timedelta(days=1)
        else:
            if month_start <= e['date'] < month_end:
                events_by_date.setdefault(e['date'], []).append(e_dict)

    theme = get_setting('theme', 'dark', user_id=uid)

    return render_template('index.html',
                           cal_days=cal_days,
                           current_year=year,
                           current_month=month,
                           events_by_date=events_by_date,
                           today=now.strftime('%Y-%m-%d'),
                           theme=theme,
                           username=session.get('username'),
                           is_admin=session.get('is_admin', False),
                           today_lunar="八月十七")

# ==================== 事件 API ====================
@app.route('/api/events', methods=['GET', 'POST'])
@login_required
def handle_events():
    db = get_db()
    uid = session['user_id']
    if request.method == 'POST':
        data = request.json
        cursor = db.cursor()
        cursor.execute(
            """INSERT INTO events (user_id, date, start_date, end_date, title, type, reminder_time) 
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (uid, data.get('date'), data.get('start_date'), data.get('end_date'),
             data.get('title'), data.get('type', 'event'), data.get('reminder_time'))
        )
        db.commit()
        return jsonify({'status': 'success', 'id': cursor.lastrowid})

    target_date = request.args.get('date')
    events = db.execute('''
        SELECT * FROM events 
        WHERE user_id = ?
          AND (date = ? 
               OR (start_date IS NOT NULL AND end_date IS NOT NULL 
                   AND start_date <= ? AND end_date >= ?))
    ''', (uid, target_date, target_date, target_date)).fetchall()

    result = []
    for e in events:
        e_dict = dict(e)
        if e['type'] == 'habit':
            log = db.execute("SELECT status FROM habit_logs WHERE event_id = ? AND date = ? AND user_id = ?",
                             (e['id'], target_date, uid)).fetchone()
            e_dict['habit_done'] = log['status'] if log else 0
        result.append(e_dict)
    return jsonify(result)

@app.route('/api/events/<int:id>', methods=['PUT', 'DELETE'])
@login_required
def update_event(id):
    db = get_db()
    uid = session['user_id']
    row = db.execute("SELECT * FROM events WHERE id = ?", (id,)).fetchone()
    if not row or row['user_id'] != uid:
        return jsonify({'error': '无权操作'}), 403

    if request.method == 'DELETE':
        db.execute("DELETE FROM events WHERE id = ?", (id,))
        db.execute("DELETE FROM habit_logs WHERE event_id = ?", (id,))
        db.commit()
        return jsonify({'status': 'deleted'})

    data = request.json
    if 'is_done' in data:
        is_done = data['is_done']
        db.execute("UPDATE events SET is_done = ? WHERE id = ?", (is_done, id))
        # 待办完成后，删除明天开始的同类型待办
        if is_done and row['type'] == 'todo':
            tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            db.execute(
                "DELETE FROM events WHERE title = ? AND type = 'todo' AND user_id = ? AND start_date >= ? AND id != ?",
                (row['title'], uid, tomorrow, id)
            )
    elif 'habit_status' in data:
        d = data.get('date')
        st = data.get('habit_status')
        existing = db.execute("SELECT id FROM habit_logs WHERE event_id = ? AND date = ?", (id, d)).fetchone()
        if existing:
            db.execute("UPDATE habit_logs SET status = ? WHERE id = ?", (st, existing['id']))
        else:
            db.execute("INSERT INTO habit_logs (event_id, user_id, date, status) VALUES (?, ?, ?, ?)",
                       (id, uid, d, st))
    db.commit()
    return jsonify({'status': 'updated'})

# ==================== 设置 API ====================
@app.route('/api/settings', methods=['GET', 'POST'])
@login_required
def handle_settings():
    db = get_db()
    uid = session['user_id']
    if request.method == 'POST':
        data = request.json
        for key in ['term_start_date', 'wechat_webhook', 'dingtalk_webhook',
                    'feishu_webhook', 'bark_url', 'ntfy_topic', 'theme',
                    'todo_remind_times']:
            if key in data:
                set_setting(key, data[key], user_id=uid)
        return jsonify({'status': 'success'})

    return jsonify({
        'term_start_date':   get_setting('term_start_date', '',  user_id=uid),
        'wechat_webhook':    get_setting('wechat_webhook', '',   user_id=uid),
        'dingtalk_webhook':  get_setting('dingtalk_webhook', '', user_id=uid),
        'feishu_webhook':    get_setting('feishu_webhook', '',   user_id=uid),
        'bark_url':          get_setting('bark_url', '',         user_id=uid),
        'ntfy_topic':        get_setting('ntfy_topic', '',       user_id=uid),
        'theme':             get_setting('theme', 'dark',        user_id=uid),
        'todo_remind_times': get_setting('todo_remind_times', DEFAULT_TODO_REMIND_TIMES, user_id=uid),
    })

# ==================== 我的账号 ====================
@app.route('/api/me/password', methods=['POST'])
@login_required
def change_my_password():
    data = request.json
    old = data.get('old_password') or ''
    new = data.get('new_password') or ''
    if len(new) < 4:
        return jsonify({'error': '新密码至少 4 位'}), 400
    db = get_db()
    uid = session['user_id']
    user = db.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    if not user or not check_password_hash(user['password_hash'], old):
        return jsonify({'error': '原密码错误'}), 400
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
               (generate_password_hash(new), uid))
    db.commit()
    return jsonify({'status': 'ok'})

@app.route('/api/me', methods=['DELETE'])
@login_required
def delete_my_account():
    db = get_db()
    uid = session['user_id']
    user = db.execute("SELECT is_admin FROM users WHERE id = ?", (uid,)).fetchone()
    if user and user['is_admin']:
        c = db.execute("SELECT COUNT(*) c FROM users WHERE is_admin = 1").fetchone()['c']
        if c <= 1:
            return jsonify({'error': '你是唯一的管理员，无法删除账号。请先指定另一个管理员。'}), 400

    db.execute("DELETE FROM events WHERE user_id = ?", (uid,))
    db.execute("DELETE FROM habit_logs WHERE user_id = ?", (uid,))
    db.execute("DELETE FROM settings WHERE user_id = ?", (uid,))
    db.execute("DELETE FROM users WHERE id = ?", (uid,))
    db.commit()
    session.clear()
    return jsonify({'status': 'ok'})

# ==================== 管理员 API ====================
@app.route('/api/admin/users', methods=['GET'])
@admin_required
def admin_list_users():
    db = get_db()
    users = db.execute(
        "SELECT id, username, is_admin, created_at FROM users ORDER BY id ASC"
    ).fetchall()
    return jsonify([dict(u) for u in users])

@app.route('/api/admin/users/<int:uid>/reset_password', methods=['POST'])
@admin_required
def admin_reset_password(uid):
    db = get_db()
    if not db.execute("SELECT id FROM users WHERE id = ?", (uid,)).fetchone():
        return jsonify({'error': '用户不存在'}), 404
    db.execute("UPDATE users SET password_hash = ? WHERE id = ?",
               (generate_password_hash(DEFAULT_PASSWORD), uid))
    db.commit()
    return jsonify({'status': 'ok', 'new_password': DEFAULT_PASSWORD})

@app.route('/api/admin/users/<int:uid>/toggle_admin', methods=['POST'])
@admin_required
def admin_toggle_admin(uid):
    db = get_db()
    if uid == session['user_id']:
        return jsonify({'error': '不能修改自己的管理员身份'}), 400
    user = db.execute("SELECT is_admin FROM users WHERE id = ?", (uid,)).fetchone()
    if not user:
        return jsonify({'error': '用户不存在'}), 404
    new_val = 0 if user['is_admin'] else 1
    db.execute("UPDATE users SET is_admin = ? WHERE id = ?", (new_val, uid))
    db.commit()
    return jsonify({'status': 'ok', 'is_admin': new_val})

@app.route('/api/admin/users/<int:uid>', methods=['DELETE'])
@admin_required
def admin_delete_user(uid):
    db = get_db()
    if uid == session['user_id']:
        return jsonify({'error': '请使用「删除我的账号」删除自己'}), 400
    user = db.execute("SELECT is_admin FROM users WHERE id = ?", (uid,)).fetchone()
    if not user:
        return jsonify({'error': '用户不存在'}), 404
    if user['is_admin']:
        c = db.execute("SELECT COUNT(*) c FROM users WHERE is_admin = 1").fetchone()['c']
        if c <= 1:
            return jsonify({'error': '不能删除唯一的管理员'}), 400
    db.execute("DELETE FROM events WHERE user_id = ?", (uid,))
    db.execute("DELETE FROM habit_logs WHERE user_id = ?", (uid,))
    db.execute("DELETE FROM settings WHERE user_id = ?", (uid,))
    db.execute("DELETE FROM users WHERE id = ?", (uid,))
    db.commit()
    return jsonify({'status': 'ok'})

# ==================== 启动 ====================
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', debug=False, port=5000)