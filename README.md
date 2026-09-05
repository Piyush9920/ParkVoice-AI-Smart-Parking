# 🚗 PARKVOICE AI
### AI-Powered Voice-Controlled Smart Parking & Navigation System
*College-Level AI Competition Project*

PARKVOICE AI is an autonomous, voice-controlled smart parking management and navigation platform. It features real-time **Web Speech API** voice control, real **A\* search pathfinding** with Manhattan distance heuristic over an interactive 4x3 parking grid, vehicle compatibility matching (Car, SUV, Bike, EV), atomic **MySQL double-booking prevention**, and an **Admin Live Simulation Mode** with telemetry analytics.

---

## 📋 System Highlights & Technical Architecture

- **Frontend**: HTML5, CSS3 (Stitch-inspired cyber glassmorphism dark theme), Vanilla JavaScript (No heavy frameworks).
- **Backend**: Python 3 (Flask), Session Management, Werkzeug Password Hashing.
- **Database**: MySQL / MariaDB (Transactions, Row Locks with `SELECT ... FOR UPDATE`, Foreign Keys, Constraints).
- **AI / Algorithm**: Real A\* Search Algorithm ($f(n) = g(n) + h(n)$) using Manhattan Distance Heuristic $h(n) = |x_1 - x_2| + |y_1 - y_2|$ in `astar.py`.
- **Speech APIs**: Browser Web Speech API (`webkitSpeechRecognition` / `SpeechRecognition` + `SpeechSynthesis`).
- **Telemetry & Simulation**: Real-time 3-second AJAX polling, Live Simulation Mode, and Chart.js analytics.

```
ParkVoiceAI/
├── app.py                  # Main Flask application & REST API
├── astar.py                # Real A* algorithm & smart slot recommendation
├── database.sql            # MySQL schema & seed data (P01–P12, admin, user)
├── requirements.txt        # Python package dependencies
├── .env.example            # Environment variables template
├── .env                    # Local configuration
├── test_system.py          # Automated verification test suite
├── templates/
│   ├── base.html           # Layout with responsive navbar & voice controls
│   ├── index.html          # Landing page with architecture & feature cards
│   ├── login.html          # User authentication
│   ├── register.html       # User & initial vehicle registration
│   ├── admin_login.html    # Admin login portal
│   ├── dashboard.html      # 4x3 Visual grid, SVG A* route & voice assistant
│   ├── booking.html        # Slot directory, EV filters & manual booking
│   ├── vehicles.html       # Garage management (Car, SUV, Bike, EV)
│   ├── history.html        # Parking logs with Today/Week/Month filters
│   └── admin.html          # Live Simulation dashboard & Chart.js charts
└── static/
    ├── css/style.css       # Complete dark Stitch-inspired UI stylesheet
    └── js/
        ├── app.js          # Global toasts and vehicle state
        ├── voice.js        # Web Speech API engine & 9 intent handlers
        ├── parking.js      # 4x3 Grid, SVG route renderer & polling
        └── admin.js        # Simulation controls & Chart.js integration
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- **Python 3.8+** (Tested on Python 3.13)
- **MySQL Server** or **XAMPP / MariaDB** (Default port `3306`)
- A modern web browser: **Google Chrome**, **Microsoft Edge**, or **Safari** (for Web Speech API)

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Setup the MySQL Database
If using XAMPP, ensure the MySQL module is running in the XAMPP Control Panel.
Import `database.sql` into MySQL:
```bash
# Via Command Line:
mysql -u root < database.sql

# Or in PowerShell:
Get-Content database.sql | mysql -u root
```
*(Note: `app.py` also automatically verifies and creates tables on startup if the database exists.)*

### 4. Configure Environment Variables
Copy `.env.example` to `.env` (already prepared):
```ini
SECRET_KEY=parkvoice_ai_super_secret_jwt_and_session_key_2026
FLASK_ENV=development
PORT=5000

DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=parkvoice_ai
```

### 5. Run the Application
```bash
python app.py
```
Open your browser at: **[http://127.0.0.1:5000](http://127.0.0.1:5000)**

---

## 🔑 Default Evaluation Accounts

| Role | Username / Email | Password | Features Accessible |
|---|---|---|---|
| **Demo User** | `demo@parkvoice.ai` | `User@123` | Dashboard, Voice Assistant, Garage, A\* Navigation, History |
| **Admin** | `admin` (or `admin@parkvoice.ai`) | `Admin@123` | Live Simulation Mode, One-Click Slot Toggles, Telemetry & Charts |

---

## 🎙️ Supported Voice Commands (Web Speech API)

| Intent | Sample Voice Phrasings | Action Performed |
|---|---|---|
| `FIND_PARKING` | *"Find parking"*, *"Find a spot"*, *"Where can I park?"* | Runs A\* search, recommends nearest optimal slot, draws purple route |
| `FIND_EV` | *"Find EV parking"*, *"Electric vehicle charging"*, *"Charge my car"* | Prioritizes dedicated EV charging bays (e.g. P01, P02, P09) |
| `BOOK_RECOMMENDED` | *"Book the recommended slot"*, *"Book recommended"*, *"Yes book it"* | Atomically books recommended slot with double-booking lock |
| `BOOK_SLOT` | *"Book P07"*, *"Reserve P03"*, *"Park at P12"* | Directly attempts to reserve specified slot |
| `SHOW_AVAILABLE` | *"Show available slots"*, *"How many spots free?"* | Voice response listing total available slots and EV spots |
| `SHOW_BOOKING` | *"Show my booking"*, *"Where is my car?"* | Voice announces active slot, vehicle, and booking code |
| `CANCEL_BOOKING` | *"Cancel my booking"*, *"Cancel reservation"* | Cancels active booking, returns slot to Available (Green) |
| `RELEASE_PARKING` | *"Release parking"*, *"I am leaving"*, *"Complete parking"* | Calculates duration & fee, logs to history, frees the slot |
| `LOGOUT` | *"Log out"*, *"Sign out"* | Voice announces logout and ends user session |

---

## ✅ 22-Flow Evaluation & Testing Checklist

Use this checklist to verify every feature required for the AI competition:

### User & Garage Management
- [x] **1. User Registration**: Create a new account with name, email, password, and vehicle details.
- [x] **2. Duplicate Email Check**: Verify duplicate registration attempt is rejected.
- [x] **3. User Login**: Login with valid credentials (`demo@parkvoice.ai` / `User@123`).
- [x] **4. Bad Credentials Rejection**: Verify invalid password shows an alert without crashing.
- [x] **5. Garage Vehicle List**: View registered vehicles (Car, SUV, Bike, EV) with icons.
- [x] **6. Add Vehicle**: Add a new vehicle to the garage with license plate and model.
- [x] **7. Set Default Vehicle**: Toggle default vehicle; verify it becomes the active vehicle.
- [x] **8. Delete Vehicle**: Remove a vehicle with confirmation.

### Visual Parking Lot & A* Algorithm
- [x] **9. 4x3 Parking Lot Map**: Verify 12 slots (P01–P12) in 4 rows x 3 cols with dedicated ENTRANCE Gate at (4, 1).
- [x] **10. Slot States & Colors**: Verify Green (`AVAILABLE`), Red (`OCCUPIED`), Yellow (`RESERVED`), Blue (`RECOMMENDED`), Purple (`A* ROUTE`).
- [x] **11. Real A\* Search**: Click any slot -> click "Trace A\* Route" -> see animated purple route polyline from Entrance Gate to the bay.
- [x] **12. Obstacle Avoidance**: If intervening slots are Occupied, verify A\* navigates around them.
- [x] **13. EV Charger Detection**: Verify EV slots (P01, P02, P09) display fast charging badges.

### Voice Assistant & Booking Flows
- [x] **14. Voice Finding**: Click Mic (or say "Find parking") -> voice announces recommendation and reasons.
- [x] **15. Voice Confirmation & Booking**: Say "Book recommended" -> booking created atomically -> slot turns Yellow (`RESERVED`).
- [x] **16. Double-Booking Prevention**: Attempting to book an occupied or reserved slot returns `409 Conflict` and prevents race conditions.
- [x] **17. Active Booking Display**: Verify active reservation card shows booking code (`PV-XXXX`), slot, and live HH:MM:SS timer.
- [x] **18. Voice Cancellation**: Say "Cancel my booking" -> booking cancelled, slot turns Green (`AVAILABLE`).
- [x] **19. Session Completion & History**: Click "Leave & Complete" -> fee recorded -> entry appears in Parking History with date filter.

### Admin Live Simulation & Analytics
- [x] **20. Admin Authentication**: Login at `/admin/login` using `admin` / `Admin@123`.
- [x] **21. Live Simulation Triggers**: Click "Simulate Car Entry" and "Simulate Car Exit" -> observe slot status update in user dashboard.
- [x] **22. Real-time Analytics**: Verify Chart.js renders Occupancy Breakdown, Peak Hours, 7-Day Trend, and Slot Utilization.

---

## 🧪 Automated Test Suite Execution
Run the automated test suite covering all layers:
```bash
python test_system.py
```
Expected output:
```
Ran 7 tests in ~1.0s
OK
```
