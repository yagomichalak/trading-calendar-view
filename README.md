
# Trading Calendar (Flask + MySQL)

A tiny Flask UI that shows **daily P/L** per day and **week P/L** on weekends.
Click any day to add a trade. Only trades are entered manually—balances are auto-updated by MySQL triggers.

## 1) Install
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# then edit .env with your MySQL credentials
```

## 2) Create the database/schema
Create a blank database first (e.g. `tradingview`). Then run:
```bash
flask --app app init-db
```
This executes `tradingview_structure.sql` (triggers, views, tables).

Or run on the terminal:
```bash
mysql -u root -p
CREATE DATABASE tradingview;
exit
```
And then
```bash
mysql -u root -p tradingview < tradingview_structure.sql
```

## 3) Run the app
```bash
flask --app app run --debug
```
Open http://127.0.0.1:5000/

## 4) Add a trade
Use the UI, or via SQL:
```sql
INSERT INTO trades (symbol, position_size, entry_price, exit_price, trade_date)
VALUES ('NVDA', 7, 112, 130, '2025-10-28');
```

## Notes
- The calendar shows **daily P/L** (from `days.day_pl`) and **week P/L** (from `weeks.week_pl`) on Saturdays/Sundays.
- When you insert a trade with `trade_date`, the triggers will create/link the correct `days` row and recompute day/week figures.
- Default starting balance is 2000; new week’s `starting_balance` carries prior week’s `week_pl`.
