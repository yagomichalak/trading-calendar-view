
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
        next_month = (first_day.replace(day=28) + timedelta(days=4)).replace(day=1)
        last_day = next_month - timedelta(days=1)

        # Fetch day P/L for the month
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT date, day_pl
                    FROM days
                    WHERE date BETWEEN %s AND %s
                """, (first_day, last_day))
                day_rows = cur.fetchall()

                # Fetch weeks overlapping month for week P/L display on weekends
                cur.execute("""
                    SELECT id, start_date, end_date, week_pl
                    FROM weeks
                    WHERE NOT (end_date < %s OR start_date > %s)
                """, (first_day, last_day))
                weeks = cur.fetchall()
        finally:
            conn.close()

        day_pl_map = { r["date"]: float(r["day_pl"]) for r in day_rows }
        # Compute display Saturday for each week, even if week range is Mon–Fri in DB
        weekend_weekpl_map = {}
        for w in weeks:
            # Find the Saturday within that ISO week (or the immediate Saturday after a Fri end_date)
            # Start from the week's start_date and jump to Saturday (weekday=5)
            wd = w["start_date"].weekday()  # 0=Mon .. 6=Sun
            days_to_sat = (5 - wd) % 7
            saturday = w["start_date"] + timedelta(days=days_to_sat)

            # If DB stores weeks Mon–Fri (end_date Friday), saturday will be end_date+1 — that's fine for display.
            if saturday.month == month:
                weekend_weekpl_map[saturday] = float(w["week_pl"])


        # Build a 6x7 grid starting from Monday of the week containing the 1st
        start_grid = first_day - timedelta(days=(first_day.weekday()))
        cells = []
        d = start_grid
        for _ in range(6*7):
            cells.append({
                "date": d,
                "in_month": d.month == month,
                "day_pl": day_pl_map.get(d),
                "week_pl": weekend_weekpl_map.get(d) if d.weekday() >= 5 else None
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
