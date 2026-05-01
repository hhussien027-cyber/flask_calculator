# Material Flask Calculator

A Material Design inspired Flask calculator application with:

- Scientific calculator mode
- Programmer mode (HEX/DEC/BIN/OCT + bitwise operations)
- User authentication (signup/login/logout)
- Profile management (display name, avatar upload, username/password updates)
- Per-user calculation history stored in MySQL

## Tech Stack

- Flask
- Flask-Login
- Flask-SQLAlchemy
- Flask-Migrate
- MySQL (via PyMySQL)

## Local Setup

1. Create and activate a virtual environment.
2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Create a MySQL database (example: `calculator_db`).
4. Set environment variables:

   - `DATABASE_URL` (example: `mysql+pymysql://root:password@localhost/calculator_db`)
   - `SECRET_KEY` (recommended for production)

5. Run migrations:

   ```bash
   flask db upgrade
   ```

6. Start the app:

   ```bash
   python app.py
   ```

## Run With Gunicorn (Linux/Server)

After installing dependencies and applying migrations, run:

```bash
gunicorn -w 2 -b 0.0.0.0:8000 app:app
```

## Deployment Notes

- This project is designed to run on Linux servers.
- Avoid committing `.env`, local `.db` files, virtual environments, or uploaded user images.
- Use a production WSGI server (for example, Gunicorn) behind a reverse proxy in production.
