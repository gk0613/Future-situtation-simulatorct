# Future Situation Simulator — V7 Frontend Refresh

This package keeps the existing Flask + SQLite simulation backend and refreshes the user interface using HTML, CSS and vanilla JavaScript.

## Included features
- Login and account registration
- Responsive simulation workspace and navigation
- Scenario setup with up to 12 zones
- Animated crowd-density map and density timeline
- Zone risk analysis and bottleneck ranking
- Emergency-condition simulation mode
- Preventive Action Lab and A/B comparison
- Per-user SQLite simulation history
- View/delete history and CSV report export

## Run locally
1. Extract this ZIP.
2. Open the extracted `Future_Situation_Simulator_V7_DB` folder in VS Code.
3. In the terminal, run:
   ```bash
   pip install -r requirements.txt
   python app.py
   ```
4. Open `http://127.0.0.1:5000` and create an account.

## Project structure
```text
Future_Situation_Simulator_V7_DB/
├── app.py
├── requirements.txt
├── README.md
├── templates/
│   ├── index.html
│   ├── login.html
│   └── register.html
└── static/
    ├── style.css
    └── app.js
```

## Important deployment notes
- Set a strong, unique `FSS_SECRET_KEY` environment variable before public deployment. The fallback key in `app.py` is only for local development.
- The application uses SQLite. For a public deployment, use persistent storage for `simulator.db`; otherwise data may be lost when the host replaces its instance. For higher concurrent write traffic, migrate to PostgreSQL.
- HTTPS should be enabled by the hosting provider. Review session-cookie settings, backups, rate limiting and account recovery before opening registration publicly.
- The simulation uses simplified assumptions. It is not a certified crowd model and must not be used as a real-time emergency-management system.
- The interface imports Google Fonts. If the deployment has no internet access, it falls back to system fonts.

## Stack
HTML · CSS · JavaScript · Python Flask · SQLite
