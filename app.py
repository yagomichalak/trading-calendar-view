import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Flask, render_template, request, redirect, url_for, flash
import pymysql
from dotenv import load_dotenv

load_dotenv()

def get_db():
    conn = pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DB", "tradingview"),
        autocommit=True,
        client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    return conn

def create_app():
    app = Flask(__name__)
    app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret")
    app.config["TZ"] = os.getenv("TZ", "America/Sao_Paulo")

    @app.cli.command("init-db")
    def init_db():
        """Initialize the MySQL schema/triggers/views from ./tradingview_structure.sql"""
        sql_path = os.path.join(os.path.dirname(__file__), "tradingview_structure.sql")
        if not os.path.exists(sql_path):
            print("tradingview_structure.sql not found next to app.py")
            raise SystemExit(2)
        with open(sql_path, "r", encoding="utf-8") as f:
            sql = f.read()
        conn = get_db()
        try:
            with conn.cursor() as cur:
                statements = [s.strip() for s in sql.split(';') if s.strip()]
                for stmt in statements:
                    cur.execute(stmt)
            print("✅ Database initialized successfully.")
        finally:
            conn.close()

    @app.route("/", methods=["GET"])
    def calendar_view():
        # Determine month to display
        tz = ZoneInfo(app.config["TZ"])
        today = datetime.now(tz).date()
        year = int(request.args.get("year", today.year))
        month = int(request.args.get("month", today.month))
        first_day = date(year, month, 1)
        default_risk = 10

        # next_month: jump to day 28, add 4 days (guaranteed next month), then set to 1st
        next_month = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1)
        last_day = next_month - timedelta(days=1)

        # --- CHANGES START: compute the 6x7 GRID RANGE first
        start_grid = first_day - timedelta(days=first_day.weekday())  # Monday of the grid
        end_grid = start_grid + timedelta(days=41)  # inclusive last cell (6*7 - 1)
        # --- CHANGES END

        # Fetch day P/L only for the actual month (as before)
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT date, day_pl, risk10, entry_balance, current_balance
                    FROM days
                    WHERE date BETWEEN %s AND %s
                """, (first_day, last_day))
                day_rows = cur.fetchall()

                # --- CHANGES START:
                # Fetch weeks that overlap the VISIBLE GRID, not just the month.
                # This ensures spillover weekends (e.g., Nov 1/2 showing in the Oct view) get a week total.
                cur.execute("""
                    SELECT id, start_date, end_date, week_pl, starting_balance
                    FROM weeks
                    WHERE NOT (end_date < %s OR start_date > %s)
                """, (start_grid, end_grid))
                weeks = cur.fetchall()
                # --- CHANGES END
        finally:
            conn.close()

        day_pl_map = { 
            r["date"]: {
                "day_pl": float(r["day_pl"]),
                "risk10": r["risk10"],
                "entry_balance": float(r["entry_balance"]),
                "current_balance": r["current_balance"],
            } for r in day_rows
        }

        # Map each date in the visible grid to its week data (starting_balance and week_pl)
        week_date_map = {}
        saturday_weekpl = {}
        for w in weeks:
            w_start = w["start_date"]
            w_end = w["end_date"]
            # overlap with visible grid
            start = max(w_start, start_grid)
            end = min(w_end, end_grid)
            sb = float(w["starting_balance"])
            wp = float(w["week_pl"])
            # assign week data to each date in this week's overlap with the grid
            d_iter = start
            while d_iter <= end:
                week_date_map[d_iter] = {"starting_balance": sb, "week_pl": wp}
                d_iter += timedelta(days=1)
            # compute saturday for optional display of week total on weekend
            wd = w_start.weekday()
            days_to_sat = (5 - wd) % 7
            saturday = w_start + timedelta(days=days_to_sat)
            if start_grid <= saturday <= end_grid:
                saturday_weekpl[saturday] = wp

        # Build the 6x7 grid
        cells = []
        d = start_grid
        for _ in range(6*7):
            day_pl = day_pl_map.get(d)
            weekinfo = week_date_map.get(d)

            cells.append({
                "date": d,
                "in_month": d.month == month,
                "day_pl": day_pl["day_pl"] if day_pl else None,
                # show week total only on weekend cells (Saturday/Sunday) when available
                "week_pl": saturday_weekpl.get(d) if d.weekday() >= 5 else None,
                "risk10": day_pl["risk10"] if day_pl else None,
                # calculate daily risk from the week data: ((starting_balance + week_pl) * default_risk) / 100
                "daily_risk": ((weekinfo["starting_balance"] + weekinfo["week_pl"]) * default_risk) / 100 if weekinfo else None,
            })
            d += timedelta(days=1)

        # Prev/next links
        prev_month = (first_day - timedelta(days=1)).replace(day=1)
        next_month_x = (last_day + timedelta(days=1)).replace(day=1)

        return render_template("calendar.html",
                               year=year, month=month,
                               cells=cells,
                               first_day=first_day,
                               prev_year=prev_month.year, prev_month=prev_month.month,
                               next_year=next_month_x.year, next_month=next_month_x.month)

    @app.route("/trades/new", methods=["POST"])
    def create_trade():
        # Simple trade creation; triggers will take care of linking to day and recomputing balances.
        symbol = request.form.get("symbol", "").strip().upper()
        position_size = request.form.get("position_size")
        entry_price = request.form.get("entry_price")
        exit_price = request.form.get("exit_price")
        trade_date = request.form.get("trade_date")

        if not (symbol and position_size and entry_price and exit_price and trade_date):
            flash("All fields are required.", "error")
            return redirect(request.referrer or url_for("calendar_view"))

        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO trades (symbol, position_size, entry_price, exit_price, trade_date)
                    VALUES (%s, %s, %s, %s, %s)
                """, (symbol, float(position_size), float(entry_price), float(exit_price), trade_date))
            flash(f"Trade {symbol} added for {trade_date}.", "ok")
        except Exception as e:
            flash(f"DB error: {e}", "error")
        finally:
            conn.close()
        return redirect(url_for("calendar_view", year=trade_date[:4], month=int(trade_date[5:7])))

    return app

app = create_app()
