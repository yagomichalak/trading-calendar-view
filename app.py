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

    @app.context_processor
    def inject_current_balance():
        current_balance = None
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT current_balance FROM days ORDER BY date DESC LIMIT 1")
                row = cur.fetchone()
                if row and row.get("current_balance") is not None:
                    current_balance = float(row["current_balance"])
        finally:
            conn.close()
        return dict(current_balance=current_balance)

    def recompute_from_date(start_date):
        """Recompute entry_balance, day_pl, current_balance and risk10 for all days from start_date onwards,
        and update affected weeks' week_pl. This is useful when a past trade is edited/deleted and later days
        need their starting balances adjusted to reflect the change.
        start_date may be a date or a string (YYYY-MM-DD).
        """
        conn = get_db()
        try:
            with conn.cursor() as cur:
                # Ensure start_date is a date-compatible value
                cur.execute("SELECT id, date, week_id FROM days WHERE date >= %s ORDER BY date ASC", (start_date,))
                days = cur.fetchall()

                # nothing to do if no days affected
                if not days:
                    return

                affected_weeks = set()

                for d in days:
                    d_id = d["id"]
                    d_date = d["date"]
                    w_id = d.get("week_id")
                    affected_weeks.add(w_id)

                    # previous balance: most recent current_balance for date < d_date
                    cur.execute("SELECT current_balance FROM days WHERE date < %s ORDER BY date DESC LIMIT 1", (d_date,))
                    prev = cur.fetchone()
                    if prev and prev.get("current_balance") is not None:
                        prev_balance = float(prev["current_balance"])
                    else:
                        # fallback to week's starting_balance
                        prev_balance = 0.0
                        if w_id is not None:
                            cur.execute("SELECT starting_balance FROM weeks WHERE id = %s", (w_id,))
                            wrow = cur.fetchone()
                            if wrow and wrow.get("starting_balance") is not None:
                                prev_balance = float(wrow["starting_balance"])

                    # recompute day_pl from trades for this day
                    cur.execute("SELECT COALESCE(SUM(profit), 0) as s FROM trades WHERE day_id = %s", (d_id,))
                    srow = cur.fetchone()
                    day_pl = float(srow["s"]) if srow and srow.get("s") is not None else 0.0

                    entry_balance = prev_balance
                    current_balance = entry_balance + day_pl
                    risk10 = round(entry_balance * 0.10, 2)

                    cur.execute("""
                        UPDATE days
                        SET entry_balance = %s, day_pl = %s, current_balance = %s, risk10 = %s
                        WHERE id = %s
                    """, (entry_balance, day_pl, current_balance, risk10, d_id))

                # Recompute week totals for affected weeks
                for w in affected_weeks:
                    if w is None:
                        continue
                    cur.execute("UPDATE weeks SET week_pl = COALESCE((SELECT SUM(d2.day_pl) FROM days d2 WHERE d2.week_id = weeks.id), 0) WHERE id = %s", (w,))
            # commit is enabled by autocommit in get_db
        finally:
            conn.close()

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
        # Recompute balances from the trade date so subsequent days are updated
        try:
            recompute_from_date(trade_date)
        except Exception:
            print("Failed to recompute after creating trade")

        # If request came from trades page, redirect back there
        if request.referrer and '/trades' in request.referrer:
            return redirect(url_for('trades_view'))
        # Otherwise redirect to calendar view (legacy behavior)
        return redirect(url_for("calendar_view", year=trade_date[:4], month=int(trade_date[5:7])))

    @app.route("/trades", methods=["GET"])
    def trades_view():
        """Display list of trades with computed profit."""
        # pagination
        try:
            page = int(request.args.get("page", "1"))
        except ValueError:
            page = 1
        try:
            per_page = int(request.args.get("per_page", "10"))
        except ValueError:
            per_page = 20
        if per_page <= 0:
            per_page = 20
        if page <= 0:
            page = 1

        offset = (page - 1) * per_page

        conn = get_db()
        trades = []
        total = 0
        try:
            with conn.cursor() as cur:
                # total count for pagination
                cur.execute("SELECT COUNT(*) as cnt FROM trades")
                cnt_row = cur.fetchone()
                total = int(cnt_row["cnt"]) if cnt_row and cnt_row.get("cnt") is not None else 0

                # fetch page of trades
                cur.execute("SELECT id, trade_date, symbol, position_size, entry_price, exit_price FROM trades ORDER BY trade_date DESC, id DESC LIMIT %s OFFSET %s", (per_page, offset))
                rows = cur.fetchall()
                for r in rows:
                    # ensure floats
                    ps = float(r["position_size"]) if r.get("position_size") is not None else 0.0
                    ep = float(r["entry_price"]) if r.get("entry_price") is not None else 0.0
                    xp = float(r["exit_price"]) if r.get("exit_price") is not None else 0.0
                    # profit calculation: (exit_price - entry_price) * position_size
                    profit = (xp - ep) * ps
                    trades.append({
                        "id": r["id"],
                        "trade_date": r["trade_date"],
                        "symbol": r["symbol"],
                        "position_size": ps,
                        "entry_price": ep,
                        "exit_price": xp,
                        "profit": profit,
                    })
        finally:
            conn.close()

        # pagination metadata
        total_pages = (total + per_page - 1) // per_page if per_page else 1

        return render_template("trades.html", trades=trades, page=page,
                               per_page=per_page, total=total, total_pages=total_pages)

    @app.route("/trades/<int:trade_id>", methods=["GET"])
    def trade_detail(trade_id):
        """Display detailed view of a trade and its linked day data."""
        conn = get_db()
        trade = None
        day = None
        try:
            with conn.cursor() as cur:
                # get trade with all fields including stop_loss and take_profit
                cur.execute("""
                    SELECT id, trade_date, symbol, position_size, entry_price, exit_price, 
                           stop_loss, take_profit, day_id
                    FROM trades 
                    WHERE id = %s
                """, (trade_id,))
                row = cur.fetchone()
                if not row:
                    flash("Trade not found.", "error")
                    return redirect(url_for("trades_view"))
                
                # compute profit
                ps = float(row["position_size"]) if row.get("position_size") is not None else 0.0
                ep = float(row["entry_price"]) if row.get("entry_price") is not None else 0.0
                xp = float(row["exit_price"]) if row.get("exit_price") is not None else 0.0
                sl = float(row["stop_loss"]) if row.get("stop_loss") is not None else None
                tp = float(row["take_profit"]) if row.get("take_profit") is not None else None
                profit = (xp - ep) * ps
                
                trade = {
                    "id": row["id"],
                    "trade_date": row["trade_date"],
                    "symbol": row["symbol"],
                    "position_size": ps,
                    "entry_price": ep,
                    "exit_price": xp,
                    "stop_loss": sl,
                    "take_profit": tp,
                    "profit": profit,
                }
                
                # get linked day data if day_id exists
                if row.get("day_id"):
                    cur.execute("""
                        SELECT date, entry_balance, day_pl, current_balance, risk10
                        FROM days
                        WHERE id = %s
                    """, (row["day_id"],))
                    day_row = cur.fetchone()
                    if day_row:
                        day = {
                            "date": day_row["date"],
                            "entry_balance": float(day_row["entry_balance"]),
                            "day_pl": float(day_row["day_pl"]),
                            "current_balance": float(day_row["current_balance"]),
                            "risk10": day_row["risk10"],
                        }
        finally:
            conn.close()
            
        return render_template("trade_detail.html", trade=trade, day=day)

    @app.route("/trades/<int:trade_id>/delete", methods=["POST"])
    def delete_trade(trade_id):
        """Delete a trade by id and redirect back to the trades list or referrer."""
        conn = get_db()
        deleted_trade_date = None
        try:
            with conn.cursor() as cur:
                # capture the trade_date before deletion so we know from which date to recompute
                cur.execute("SELECT trade_date, day_id FROM trades WHERE id = %s", (trade_id,))
                row = cur.fetchone()
                if not row:
                    flash("Trade not found.", "error")
                    return redirect(request.referrer or url_for('trades_view'))
                deleted_trade_date = row.get("trade_date")

                cur.execute("DELETE FROM trades WHERE id = %s", (trade_id,))
                cur.execute("DELETE FROM days WHERE trade_id = %s AND date = %s", (trade_id, deleted_trade_date))
                if cur.rowcount == 0:
                    flash("Trade not found.", "error")
                else:
                    flash("Trade deleted.", "ok")
        except Exception as e:
            flash(f"DB error: {e}", "error")
        finally:
            conn.close()

        # If we deleted a trade from a past date, recompute subsequent days so entry_balance reflects the removal
        try:
            if deleted_trade_date:
                recompute_from_date(deleted_trade_date)
        except Exception:
            # don't prevent user flow on recompute errors; just log to console
            print("Failed to recompute days after deleting trade", trade_id)

        # Redirect back to where the request came from, or to the trades listing
        return redirect(request.referrer or url_for('trades_view'))

    @app.route("/trades/<int:trade_id>/edit", methods=["GET", "POST"])
    def edit_trade(trade_id):
        """Show edit form (GET) and apply updates (POST) for a trade."""
        conn = get_db()
        try:
            with conn.cursor() as cur:
                # GET: render form with current values
                if request.method == "GET":
                    cur.execute("SELECT id, trade_date, symbol, position_size, entry_price, exit_price, stop_loss, take_profit FROM trades WHERE id = %s", (trade_id,))
                    row = cur.fetchone()
                    if not row:
                        flash("Trade not found.", "error")
                        return redirect(url_for('trades_view'))
                    ps_val = float(row["position_size"]) if row.get("position_size") is not None else 0.0
                    ep_val = float(row["entry_price"]) if row.get("entry_price") is not None else 0.0
                    xp_val = float(row["exit_price"]) if row.get("exit_price") is not None else 0.0
                    profit_val = (xp_val - ep_val) * ps_val

                    trade = {
                        "id": row["id"],
                        "trade_date": row["trade_date"],
                        "symbol": row["symbol"],
                        "position_size": ps_val,
                        "entry_price": ep_val,
                        "exit_price": xp_val,
                        "profit": profit_val,
                    }
                    return render_template('trade_edit.html', trade=trade)

                # POST: apply changes
                symbol = request.form.get("symbol", "").strip().upper()
                position_size = request.form.get("position_size")
                entry_price = request.form.get("entry_price")
                exit_price = request.form.get("exit_price")
                trade_date = request.form.get("trade_date")
                # require exit_price explicitly (profit is not editable)
                if not (symbol and position_size and entry_price and exit_price and trade_date):
                    flash("All required fields are required.", "error")
                    return redirect(request.referrer or url_for('edit_trade', trade_id=trade_id))

                try:
                    ps_f = float(position_size)
                    ep_f = float(entry_price)
                    xp_f = float(exit_price)

                    cur.execute("""
                        UPDATE trades
                        SET symbol = %s, position_size = %s, entry_price = %s, exit_price = %s, trade_date = %s
                        WHERE id = %s
                    """, (
                        symbol,
                        ps_f,
                        ep_f,
                        xp_f,
                        trade_date,
                        trade_id
                    ))
                    flash("Trade updated.", "ok")
                except Exception as e:
                    flash(f"DB error: {e}", "error")
        finally:
            conn.close()

            # Recompute balances from the trade date so subsequent days are updated
            try:
                recompute_from_date(trade_date)
            except Exception:
                print("Failed to recompute after editing trade")

            return redirect(url_for('trades_view'))

    return app

app = create_app()
