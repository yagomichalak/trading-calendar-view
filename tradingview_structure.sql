-- ========================================
-- 🧠 TRADING JOURNAL (MySQL 8) — CLEAN BUILD
-- ========================================

CREATE DATABASE IF NOT EXISTS tradingview CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 🧱 1️⃣ RESET STRUCTURE
DROP TRIGGER IF EXISTS trg_bi_days_fill_week_and_balances;

DROP TRIGGER IF EXISTS trg_bi_trades_attach_day;

DROP TRIGGER IF EXISTS trg_ai_trades_recalc_day;

DROP TRIGGER IF EXISTS trg_au_trades_recalc_day;

DROP TRIGGER IF EXISTS trg_ad_trades_recalc_day;

DROP TABLE IF EXISTS trades;

DROP TABLE IF EXISTS days;

DROP TABLE IF EXISTS weeks;

-- ========================================
-- 📆 TABLES
-- ========================================

CREATE TABLE TraderInfo (
    id INT PRIMARY KEY AUTO_INCREMENT,
    starting_balance DECIMAL(12, 2) NOT NULL DEFAULT 2000.00
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE weeks (
    id INT PRIMARY KEY AUTO_INCREMENT,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    starting_balance DECIMAL(12, 2) NOT NULL DEFAULT 2000.00,
    week_pl DECIMAL(12, 2) NOT NULL DEFAULT 0.00
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE days (
    id INT PRIMARY KEY AUTO_INCREMENT,
    `date` DATE NOT NULL UNIQUE,
    week_id INT NULL,
    entry_balance DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    day_pl DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    current_balance DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    risk10 DECIMAL(12, 2) NOT NULL DEFAULT 0.00,
    trade_id INT NULL,
    CONSTRAINT fk_days_week FOREIGN KEY (week_id) REFERENCES weeks (id) ON DELETE SET null
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE TABLE trades (
    id INT PRIMARY KEY AUTO_INCREMENT,
    day_id INT NULL,
    symbol VARCHAR(64) NOT NULL,
    position_size DECIMAL(16, 4) NOT NULL,
    entry_price DECIMAL(16, 4) NOT NULL,
    exit_price DECIMAL(16, 4) NOT NULL,
    stop_loss DECIMAL(16, 4) NULL,
    take_profit DECIMAL(16, 4) NULL,
    trade_date DATE NULL,
    profit DECIMAL(18, 2) GENERATED ALWAYS AS (
        (exit_price - entry_price) * position_size
    ) STORED,
    CONSTRAINT fk_trades_day FOREIGN KEY (day_id) REFERENCES days (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

CREATE INDEX idx_trades_day ON trades (day_id);

CREATE INDEX idx_days_week ON days (week_id);

-- ========================================
-- ⚙️ 2️⃣ TRIGGERS (MySQL)
-- ========================================

-- BEFORE INSERT on days:
--   • ensure week exists for NEW.date (Mon..Sun)
--   • set NEW.week_id
--   • set entry_balance from previous day.current_balance or week's starting_balance
--   • set risk10/current_balance defaults
CREATE TRIGGER trg_bi_days_fill_week_and_balances
BEFORE INSERT ON days
FOR EACH ROW
BEGIN
  DECLARE v_week_id INT;
  DECLARE v_sunday  DATE;
  DECLARE v_saturday DATE;
  DECLARE v_prev_bal DECIMAL(12,2);

  -- week bounds (Sun..Sat)
  -- DAYOFWEEK returns 1=Sunday..7=Saturday, so subtract (DAYOFWEEK-1) days to get Sunday
  SET v_sunday = DATE_SUB(NEW.`date`, INTERVAL (DAYOFWEEK(NEW.`date`) - 1) DAY);
  SET v_saturday = DATE_ADD(v_sunday, INTERVAL 6 DAY);

  SELECT id INTO v_week_id
  FROM weeks
  WHERE NEW.`date` BETWEEN start_date AND end_date
  LIMIT 1;

  IF v_week_id IS NULL THEN
  INSERT INTO weeks (start_date, end_date, starting_balance)
  VALUES (v_sunday, v_saturday, 2000.00);
    SET v_week_id = LAST_INSERT_ID();
  END IF;

  SET NEW.week_id = v_week_id;

  SELECT d.current_balance
    INTO v_prev_bal
  FROM days d
  WHERE d.`date` < NEW.`date`
  ORDER BY d.`date` DESC
  LIMIT 1;

  IF v_prev_bal IS NULL THEN
    SELECT starting_balance INTO v_prev_bal
    FROM weeks
    WHERE id = v_week_id;
  END IF;

  SET NEW.entry_balance   = v_prev_bal;
  SET NEW.risk10          = ROUND(NEW.entry_balance * 0.10, 2);
  SET NEW.current_balance = NEW.entry_balance;
END$$

-- BEFORE INSERT on trades:
--   • if trade_date is given and day_id is null,
--     ensure a day exists for that date and attach trade to it
CREATE TRIGGER trg_bi_trades_attach_day
BEFORE INSERT ON trades
FOR EACH ROW
BEGIN
  DECLARE v_day_id INT;

  IF NEW.trade_date IS NOT NULL AND NEW.day_id IS NULL THEN
    SELECT id INTO v_day_id FROM days WHERE `date` = NEW.trade_date LIMIT 1;

    IF v_day_id IS NULL THEN
      INSERT INTO days(`date`) VALUES (NEW.trade_date);
      SET v_day_id = LAST_INSERT_ID();
    END IF;

    SET NEW.day_id = v_day_id;
  END IF;
END$$

-- After INSERT/UPDATE/DELETE on trades:
--   • recompute day_pl/current_balance/risk10 for affected day(s)
CREATE TRIGGER trg_ai_trades_recalc_day
AFTER INSERT ON trades
FOR EACH ROW
BEGIN
  UPDATE days d
  SET
    d.day_pl = COALESCE((SELECT SUM(t.profit) FROM trades t WHERE t.day_id = NEW.day_id), 0),
    d.current_balance = d.entry_balance
                        + COALESCE((SELECT SUM(t.profit) FROM trades t WHERE t.day_id = NEW.day_id), 0),
    d.risk10 = ROUND(d.entry_balance * 0.10, 2),
    d.trade_id = NEW.id
  WHERE d.id = NEW.day_id;

  -- also roll week_pl
  UPDATE weeks w
  JOIN days d ON d.week_id = w.id
  SET w.week_pl = COALESCE((SELECT SUM(d2.day_pl) FROM days d2 WHERE d2.week_id = w.id), 0)
  WHERE d.id = NEW.day_id;
END$$

CREATE TRIGGER trg_au_trades_recalc_day
AFTER UPDATE ON trades
FOR EACH ROW
BEGIN
  -- if the day changed, recalc both
  UPDATE days d
  SET
    d.day_pl = COALESCE((SELECT SUM(t.profit) FROM trades t WHERE t.day_id = d.id), 0),
    d.current_balance = d.entry_balance
                        + COALESCE((SELECT SUM(t.profit) FROM trades t WHERE t.day_id = d.id), 0),
    d.risk10 = ROUND(d.entry_balance * 0.10, 2)
  WHERE d.id IN (OLD.day_id, NEW.day_id);

  UPDATE weeks w
  SET w.week_pl = COALESCE((SELECT SUM(d2.day_pl) FROM days d2 WHERE d2.week_id = w.id), 0)
  WHERE w.id IN (
    SELECT week_id FROM days WHERE id IN (OLD.day_id, NEW.day_id)
  );
END$$

CREATE TRIGGER trg_ad_trades_recalc_day
AFTER DELETE ON trades
FOR EACH ROW
BEGIN
  UPDATE days d
  SET
    d.day_pl = COALESCE((SELECT SUM(t.profit) FROM trades t WHERE t.day_id = OLD.day_id), 0),
    d.current_balance = d.entry_balance
                        + COALESCE((SELECT SUM(t.profit) FROM trades t WHERE t.day_id = OLD.day_id), 0),
    d.risk10 = ROUND(d.entry_balance * 0.10, 2)
  WHERE d.id = OLD.day_id;

  UPDATE weeks w
  JOIN days d ON d.week_id = w.id
  SET w.week_pl = COALESCE((SELECT SUM(d2.day_pl) FROM days d2 WHERE d2.week_id = w.id), 0)
  WHERE d.id = OLD.day_id;
END$$

DROP TRIGGER IF EXISTS trg_bi_days_fill_week_and_balances $$

CREATE TRIGGER trg_bi_days_fill_week_and_balances
BEFORE INSERT ON days
FOR EACH ROW
BEGIN
  DECLARE v_week_id INT;
  DECLARE v_sunday  DATE;
  DECLARE v_saturday DATE;
  DECLARE v_prev_bal DECIMAL(12,2);

  -- Sunday..Saturday window for NEW.date
  SET v_sunday = DATE_SUB(NEW.`date`, INTERVAL (DAYOFWEEK(NEW.`date`) - 1) DAY);
  SET v_saturday = DATE_ADD(v_sunday, INTERVAL 6 DAY);

  -- find or create week
  SELECT id INTO v_week_id
  FROM weeks
  WHERE NEW.`date` BETWEEN start_date AND end_date
  LIMIT 1;

  IF v_week_id IS NULL THEN
  INSERT INTO weeks (start_date, end_date, starting_balance, week_pl)
  VALUES (v_sunday, v_saturday, 2000.00, 0.00);
    SET v_week_id = LAST_INSERT_ID();
  END IF;

  -- attach the day to its week
  SET NEW.week_id = v_week_id;

  -- entry balance = previous day's current_balance, else week's starting_balance
  SELECT d.current_balance
    INTO v_prev_bal
  FROM days d
  WHERE d.`date` < NEW.`date`
  ORDER BY d.`date` DESC
  LIMIT 1;

  IF v_prev_bal IS NULL THEN
    SELECT starting_balance INTO v_prev_bal
    FROM weeks WHERE id = v_week_id;
  END IF;

  SET NEW.entry_balance   = v_prev_bal;
  SET NEW.current_balance = v_prev_bal;
  SET NEW.risk10          = ROUND(v_prev_bal * 0.10, 2);
END $$

DROP TRIGGER IF EXISTS trg_ai_trades_set_day_trade;

CREATE TRIGGER trg_ai_trades_set_day_trade
AFTER INSERT ON trades
FOR EACH ROW
BEGIN
  IF NEW.day_id IS NOT NULL THEN
    UPDATE days
      SET trade_id = NEW.id
    WHERE id = NEW.day_id;
  END IF;
END$$

INSERT INTO TraderInfo (starting_balance) VALUES (2000.00);