-- ===========================================
-- 添加 user 角色支持 + 用户每日评分表
-- ===========================================

-- 注意：SQLite 不支持直接修改 CHECK 约束
-- 需要重建 users 表以支持新的 'user' 角色

-- 1. 重建 users 表以支持 'user' 角色
PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS users_new (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT DEFAULT 'user' CHECK(role IN ('admin', 'user', 'guest')),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO users_new (id, username, password_hash, role, created_at, updated_at)
SELECT id, username, password_hash, role, created_at, updated_at FROM users;

DROP TABLE users;
ALTER TABLE users_new RENAME TO users;

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

PRAGMA foreign_keys = ON;

-- 2. 新增用户每日评分缓存表
CREATE TABLE IF NOT EXISTS user_daily_scores (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  article_id INTEGER NOT NULL,
  score_date TEXT NOT NULL,            -- 评分日期 (YYYY-MM-DD)
  relevance_score REAL NOT NULL,       -- JEV 综合相关性评分 (0-1)
  matched_domain TEXT,                 -- 匹配的主题领域名称
  jev_response TEXT,                   -- JEV 原始响应 JSON
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (article_id) REFERENCES articles(id) ON DELETE CASCADE,
  UNIQUE(user_id, article_id, score_date)
);

CREATE INDEX IF NOT EXISTS idx_user_daily_scores_user_date ON user_daily_scores(user_id, score_date);
CREATE INDEX IF NOT EXISTS idx_user_daily_scores_score ON user_daily_scores(relevance_score);
