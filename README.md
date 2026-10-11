# URL Shortener + Click Analytics

A backend-focused URL shortener built with **Flask, PostgreSQL, Redis, and Redis Queue (RQ)**. It combines cached redirects with asynchronous click-event processing and per-link analytics, with optional custom aliases, expiration, and link deactivation.

**Live demo:** [url-shortener-click-analytics.onrender.com](https://url-shortener-click-analytics.onrender.com/)  
**Source code:** [GitHub repository](https://github.com/manasidivate/URL-Shortener-Click-Analytics)

## ✨ Features

- **URL shortening:** Generate unique Base62 short codes using a PostgreSQL sequence.
- **URL redirection:** Use Redis caching for frequently accessed short URLs and HTTP `302 Found` redirects.
- **Asynchronous click tracking:** Queue click events for background processing, including timestamp, IP-derived country, browser, device type, referrer, and a salted visitor hash.
- **Click analytics:** View total clicks, unique visitors, top five countries, top five referrers, and clicks over the last seven days.
- **Custom aliases:** Create user-defined short URLs with validation and collision detection.
- **URL expiration:** Set optional expiration timestamps; expired links return `410 Gone`.
- **Link deactivation:** Deactivate and reactivate links without deleting their records; deactivated links return `403 Forbidden`.
- **QR codes:** Generate a PNG QR code for an active short URL through `GET /<short_url>/qr`.

Country analytics depend on successful IP geolocation. Referrer analytics are available only when the incoming request includes a `Referer` header.

## 🏗️ Architecture

```text
                          Client
                            |
                            v
                     Flask application
                       /           \
                      v             v
                Redis cache     Redis / RQ queue
                      |                |
                 Cache miss            v
                      |             RQ worker
                      v                |
                  PostgreSQL <---------+
              (URLs and click events)
```

- **Flask** handles the web interface, URL creation, redirects, and analytics endpoints.
- **PostgreSQL** stores URL records and processed click events.
- **Redis** supports hot-URL caching and the RQ queue backend.
- **RQ worker** processes click-event jobs asynchronously.
- **GeoLite2** provides IP-based country lookup; `user-agents` parses browser and device information.

## How Redirects Work

1. The application checks Redis for the short code.
2. On a cache miss, it retrieves the URL record from PostgreSQL.
3. It checks whether the link is active and has not expired.
4. A valid link receives a `302 Found` redirect, and a click-event job is queued for background processing.

| Link state | Response |
|---|---|
| Active and not expired | `302 Found` |
| Expired | `410 Gone` |
| Deactivated | `403 Forbidden` |
| Unknown short code | `404 Not Found` |

Click-event processing runs separately from the redirect path, so the redirect request does not wait for the worker to finish recording analytics.

## 🔌 API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/` | Serve the web interface |
| `POST` | `/shorten` | Create a short URL |
| `GET` | `/<short_url>` | Redirect or return the appropriate link-state response |
| `GET` | `/<short_url>/analytics` | Retrieve analytics for a short URL |
| `PATCH` | `/<short_url>` | Activate or deactivate a short URL |
| `GET` | `/<short_url>/qr` | Return a PNG QR code for an active short URL |

## 🛠️ Tech Stack

- **Language:** Python
- **Backend:** Flask
- **Database / ORM:** PostgreSQL, Flask-SQLAlchemy, SQLAlchemy
- **Caching and queue backend:** Redis
- **Background jobs:** Redis Queue (RQ)
- **Geolocation:** MaxMind GeoLite2 Country database
- **User-agent parsing:** `user-agents`
- **Frontend:** HTML, CSS, JavaScript
- **Deployment:** Render, Gunicorn, Supervisor
- **Testing:** Python `unittest`

## 🧪 Testing

The project includes automated tests covering core functionality, link lifecycle behavior, caching, click tracking, analytics, QR generation, and deployment configuration.

Run the test suite from the project root:

```bash
python -m unittest discover -s tests -v
```

## 📊 Redirect Performance Benchmark

A local benchmark at `benchmarks/benchmark_redirect.py` measures hot-cache redirect latency, including P95 latency, against the project's **50 ms target**.

Run the Flask application with its required services and a valid `/info` short code, then execute:

```bash
python benchmarks/benchmark_redirect.py
```

This measures local performance; it does not guarantee the same latency under production traffic or deployment conditions.

## 🚀 Deployment

The application is deployed on **Render** using the configuration in `render.yaml`.

- **Gunicorn** serves the Flask application.
- **Supervisor** manages Gunicorn and the RQ worker as separate processes within the web service.
- **Render PostgreSQL** stores URL and click-event records.
- **Render Key Value (Redis)** supports caching and the RQ queue.
- The GeoLite2 Country database is downloaded during the build using MaxMind credentials; the database file is not committed to the repository.
- Runtime configuration is supplied through environment variables.

The application currently uses free-tier services, which have resource and lifecycle limitations. Service restarts or Redis data loss may interrupt queued background work. High availability and stronger recovery guarantees are planned future improvements.

## ⚙️ Configuration

For local development, create a `.env` file with the required configuration:

```env
DATABASE_URL=<your-postgresql-database-url>
REDIS_URL=redis://localhost:6379/0
VISITOR_HASH_SALT=<your-random-secret-salt>
GEOLITE2_DATABASE_PATH=data/GeoLite2-Country.mmdb
```

For IP-derived country analytics, obtain the GeoLite2 Country database and place it at the configured path. For deployment, set `MAXMIND_ACCOUNT_ID` and `MAXMIND_LICENSE_KEY` in the hosting environment so the build script can download the database.

Never commit real credentials, `.env` files, or the GeoLite2 database to version control.

## 💻 Run Locally

### 1. Clone the repository

```bash
git clone https://github.com/manasidivate/URL-Shortener-Click-Analytics.git
cd URL-Shortener-Click-Analytics
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
```

**Windows (PowerShell):**

```powershell
.\venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure services

Create the `.env` file described above. Make sure PostgreSQL and Redis are running and that the GeoLite2 database is available at `GEOLITE2_DATABASE_PATH`.

To start a local Redis instance with Docker:

```bash
docker run -d --name url-shortener-redis -p 6379:6379 redis
```

### 5. Initialize the database

```bash
python init_db.py
```

### 6. Start the application and worker

In one terminal:

```bash
python app.py
```

In a second terminal, using the same virtual environment and environment variables:

```bash
python worker.py
```

The Flask application handles HTTP requests while the RQ worker processes click-event jobs.

## 📁 Project Structure

```text
URL Shortener + Click Analytics/
├── benchmarks/
│   └── benchmark_redirect.py
├── scripts/
│   ├── download_geolite2.py
│   ├── run_gunicorn.sh
│   └── start_web.sh
├── static/
│   ├── script.js
│   └── style.css
├── templates/
│   ├── deactivated.html
│   ├── expired.html
│   └── index.html
├── tests/
│   ├── test_analytics.py
│   ├── test_click_tracking.py
│   ├── test_deactivation.py
│   ├── test_deployment_config.py
│   ├── test_expiration.py
│   ├── test_qr.py
│   └── test_shortening.py
├── app.py
├── extensions.py
├── init_db.py
├── models.py
├── render.yaml
├── requirements.txt
├── routes.py
├── supervisord.conf
├── tasks.py
└── worker.py
```

## 🔭 Future Improvements

- **High availability:** Introduce independent service instances, health checks, and automated recovery.
- **Scalability:** Explore horizontal scaling and load balancing to support higher traffic.
- **Durability and resilience:** Improve queue persistence and recovery strategies to reduce the risk of losing queued work.
- **Security hardening:** Extend existing security safeguards and strengthen configuration management.


