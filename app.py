from flask import Flask, render_template, request, jsonify, Response, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import sqlite3, csv, io, json, os

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FSS_SECRET_KEY", "future-situation-simulator-local-secret")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "simulator.db")
RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS simulations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            space_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            simulation_time INTEGER NOT NULL,
            arrival_rate INTEGER NOT NULL,
            exit_rate INTEGER NOT NULL,
            emergency INTEGER NOT NULL DEFAULT 0,
            overall_risk TEXT NOT NULL,
            final_density REAL NOT NULL,
            peak_density REAL NOT NULL,
            peak_total_people INTEGER NOT NULL,
            bottleneck_count INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    conn.commit()
    conn.close()


init_db()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"ok": False, "error": "Please login first."}), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def risk_level(density):
    if density < 60:
        return "LOW"
    if density < 80:
        return "MEDIUM"
    if density <= 100:
        return "HIGH"
    return "CRITICAL"


def clamp(value, low, high):
    return max(low, min(high, value))


def clean_zones(zones):
    result = []
    for i, z in enumerate(zones or []):
        name = str(z.get("name", f"Zone {i+1}")).strip() or f"Zone {i+1}"
        capacity = max(1, int(z.get("capacity", 100)))
        people = max(0, int(z.get("people", 0)))
        people = min(people, capacity)
        result.append({"name": name[:40], "capacity": capacity, "people": people})
    return result[:12]


def simulate(payload):
    space_name = str(payload.get("space_name", "Public Space")).strip()[:80] or "Public Space"
    sim_time = clamp(int(payload.get("simulation_time", 30)), 5, 180)
    arrival_rate = clamp(int(payload.get("arrival_rate", 10)), 0, 500)
    exit_rate = clamp(int(payload.get("exit_rate", 5)), 0, 500)
    emergency = bool(payload.get("emergency", False))
    zones = clean_zones(payload.get("zones", []))
    if not zones:
        zones = [{"name": "Main Zone", "capacity": 100, "people": 20}]

    state = [z["people"] for z in zones]
    timeline = []
    zone_history = []
    emergency_step = max(1, sim_time // 3) if emergency else None

    for t in range(sim_time + 1):
        if t > 0:
            emergency_now = emergency and t >= emergency_step
            arrivals = arrival_rate
            exits = exit_rate
            if emergency_now:
                arrivals = int(arrival_rate * 1.7) + (1 if arrival_rate else 0)
                exits = max(0, int(exit_rate * 0.5))

            state[0] += arrivals

            movement_factor = 0.55 if emergency_now else 0.8
            for i in range(len(state) - 1):
                move = int(max(0, state[i] * 0.12 * movement_factor))
                state[i] -= move
                state[i + 1] += move

            state[-1] = max(0, state[-1] - exits)

        snapshot = []
        for i, z in enumerate(zones):
            density = (state[i] / z["capacity"]) * 100
            snapshot.append({
                "name": z["name"],
                "people": int(round(state[i])),
                "capacity": z["capacity"],
                "density": round(density, 1),
                "risk": risk_level(density)
            })
        zone_history.append(snapshot)
        total_capacity = max(1, sum(z["capacity"] for z in zones))
        overall_density = sum(state) / total_capacity * 100
        timeline.append({
            "time": t,
            "total_people": int(round(sum(state))),
            "overall_density": round(overall_density, 1),
            "overall_risk": risk_level(overall_density),
            "emergency_active": bool(emergency and t >= (emergency_step or 10))
        })

    final = zone_history[-1]
    peak_by_zone = []
    bottlenecks = []
    for idx, z in enumerate(zones):
        peak = max(h[idx]["density"] for h in zone_history)
        peak_item = {
            "name": z["name"],
            "peak_density": round(peak, 1),
            "peak_risk": risk_level(peak),
            "capacity": z["capacity"]
        }
        peak_by_zone.append(peak_item)
        if peak >= 80:
            bottlenecks.append({
                "name": z["name"],
                "peak_density": round(peak, 1),
                "severity": risk_level(peak)
            })

    total_capacity = sum(z["capacity"] for z in zones)
    peak_total = max(x["total_people"] for x in timeline)
    peak_density = max(x["overall_density"] for x in timeline)
    final_density = timeline[-1]["overall_density"]

    return {
        "space_name": space_name,
        "simulation_time": sim_time,
        "arrival_rate": arrival_rate,
        "exit_rate": exit_rate,
        "emergency": emergency,
        "emergency_step": emergency_step,
        "timeline": timeline,
        "zone_history": zone_history,
        "final_zones": final,
        "peak_by_zone": peak_by_zone,
        "bottlenecks": sorted(bottlenecks, key=lambda x: x["peak_density"], reverse=True),
        "peak_total_people": peak_total,
        "peak_density": peak_density,
        "final_density": final_density,
        "overall_risk": risk_level(final_density),
        "total_capacity": total_capacity,
        "final_total_people": timeline[-1]["total_people"] if timeline else 0
    }


def save_simulation(payload, result):
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO simulations (
            user_id, space_name, created_at, simulation_time, arrival_rate, exit_rate,
            emergency, overall_risk, final_density, peak_density, peak_total_people,
            bottleneck_count, payload_json, result_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session["user_id"],
        result["space_name"],
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        result["simulation_time"],
        result["arrival_rate"],
        result["exit_rate"],
        int(result["emergency"]),
        result["overall_risk"],
        result["final_density"],
        result["peak_density"],
        result["peak_total_people"],
        len(result["bottlenecks"]),
        json.dumps(payload),
        json.dumps(result)
    ))
    conn.commit()
    simulation_id = cur.lastrowid
    conn.close()
    return simulation_id


@app.route("/")
@login_required
def index():
    return render_template("index.html", username=session.get("username"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("index"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@app.route("/register", methods=["GET", "POST"])
def register():
    if "user_id" in session:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if len(username) < 3 or len(username) > 30:
            error = "Username must be 3–30 characters."
        elif len(password) < 6:
            error = "Password must be at least 6 characters."
        else:
            try:
                conn = get_db()
                conn.execute(
                    "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                    (username, generate_password_hash(password), datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                )
                conn.commit()
                conn.close()
                return redirect(url_for("login", registered="1"))
            except sqlite3.IntegrityError:
                error = "That username already exists."
    return render_template("register.html", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/simulate", methods=["POST"])
@login_required
def simulate_route():
    try:
        payload = request.get_json(force=True)
        result = simulate(payload)
        simulation_id = save_simulation(payload, result)
        return jsonify({"ok": True, "simulation_id": simulation_id, "result": result})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/compare", methods=["POST"])
@login_required
def compare_route():
    try:
        data = request.get_json(force=True)
        a = simulate(data.get("scenario_a", {}))
        b = simulate(data.get("scenario_b", {}))
        delta_density = round(a["final_density"] - b["final_density"], 1)
        delta_peak = round(a["peak_density"] - b["peak_density"], 1)
        return jsonify({
            "ok": True,
            "scenario_a": a,
            "scenario_b": b,
            "comparison": {
                "density_change": delta_density,
                "peak_density_change": delta_peak,
                "lower_final_density": "A" if a["final_density"] < b["final_density"] else "B" if b["final_density"] < a["final_density"] else "EQUAL",
                "lower_peak_density": "A" if a["peak_density"] < b["peak_density"] else "B" if b["peak_density"] < a["peak_density"] else "EQUAL",
                "message": (
                    "Scenario B produces lower simulated crowd density."
                    if b["final_density"] < a["final_density"]
                    else "Scenario A produces lower simulated crowd density."
                    if a["final_density"] < b["final_density"]
                    else "Both scenarios produce the same simulated crowd density."
                )
            }
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/history")
@login_required
def history():
    conn = get_db()
    rows = conn.execute("""
        SELECT id, space_name, created_at, simulation_time, arrival_rate, exit_rate,
               emergency, overall_risk, final_density, peak_density, peak_total_people,
               bottleneck_count
        FROM simulations
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 100
    """, (session["user_id"],)).fetchall()
    conn.close()
    return jsonify({"ok": True, "history": [dict(row) for row in rows]})


@app.route("/api/history/<int:simulation_id>")
@login_required
def history_detail(simulation_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM simulations WHERE id = ? AND user_id = ?",
        (simulation_id, session["user_id"])
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({"ok": False, "error": "Simulation not found."}), 404
    return jsonify({"ok": True, "simulation": {
        "id": row["id"],
        "space_name": row["space_name"],
        "created_at": row["created_at"],
        "result": json.loads(row["result_json"]),
        "payload": json.loads(row["payload_json"])
    }})


@app.route("/api/history/<int:simulation_id>", methods=["DELETE"])
@login_required
def delete_history(simulation_id):
    conn = get_db()
    cur = conn.execute(
        "DELETE FROM simulations WHERE id = ? AND user_id = ?",
        (simulation_id, session["user_id"])
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return jsonify({"ok": False, "error": "Simulation not found."}), 404
    return jsonify({"ok": True})


@app.route("/health")
def health():
    return jsonify({"status": "ok", "version": "V7 Database + History"})


@app.route("/report.csv", methods=["POST"])
@login_required
def report_csv():
    try:
        payload = request.get_json(force=True)
        result = simulate(payload)
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["Future Situation Simulator - Simulation Report"])
        writer.writerow(["User", session.get("username", "")])
        writer.writerow(["Public Space", result["space_name"]])
        writer.writerow(["Simulation Time", result["simulation_time"]])
        writer.writerow(["Arrival Rate", result["arrival_rate"]])
        writer.writerow(["Exit Rate", result["exit_rate"]])
        writer.writerow(["Emergency", result["emergency"]])
        writer.writerow([])
        writer.writerow(["Zone", "Capacity", "Final People", "Final Density %", "Risk", "Peak Density %", "Peak Risk"])
        for f, p in zip(result["final_zones"], result["peak_by_zone"]):
            writer.writerow([f["name"], f["capacity"], f["people"], f["density"], f["risk"], p["peak_density"], p["peak_risk"]])
        writer.writerow([])
        writer.writerow(["Overall Risk", result["overall_risk"]])
        writer.writerow(["Final Density %", result["final_density"]])
        writer.writerow(["Peak Density %", result["peak_density"]])
        writer.writerow(["Peak Total People", result["peak_total_people"]])
        return Response(
            out.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=future_situation_simulator_report.csv"}
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG", "0") == "1")
