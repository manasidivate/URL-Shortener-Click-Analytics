# URL Shortener + Click Analytics

A backend-focused URL shortening and click analytics system built with **Flask, PostgreSQL, Redis, and Redis Queue (RQ)**.

Unlike a basic URL shortener, this project combines **fast cached redirection, asynchronous click-event processing, analytics aggregation, custom aliases, URL expiration, and link deactivation** into a single backend system.

## ✨ Features

- **URL Shortening**
  - Generate unique short URLs using **Base62 encoding**
  - PostgreSQL sequence-based short-code generation

- **Fast URL Redirection**
  - Redis-based caching for frequently accessed short URLs
  - Cache hit/miss handling
  - HTTP `302 Found` redirection

- **Asynchronous Click Tracking**
  - Process click events using **Redis Queue (RQ)**
  - Background worker-based processing
  - Capture timestamp, IP-derived country, browser, device type, referrer, and visitor hash

- **Click Analytics**
  - Total clicks
  - Unique visitors
  - Top 5 countries
  - Top 5 referrers
  - Clicks over the last 7 days

- **Custom Aliases**
  - User-defined short URLs
  - Alias validation
  - Reserved-alias protection
  - Collision detection

- **URL Expiration**
  - Optional expiration timestamps
  - Expired links return `410 Gone`
  - Expired cache entries are invalidated

- **Link Deactivation**
  - Deactivate links without deleting their database records
  - Deactivated links return `403 Forbidden`
  - Cache invalidation on status changes
  - Link reactivation support

## 🏗️ Architecture

```text
                         +----------------+
                         |     Client     |
                         +-------+--------+
                                 |
                                 v
                         +-------+--------+
                         | Flask Backend  |
                         +---+---------+--+
                             |         |
                      Cache  |         | Click Event
                             |         |
                             v         v
                        +----+----+  +--+------+
                        |  Redis  |  | RQ Queue|
                        +----+----+  +----+----+
                             |            |
                       Cache Miss          v
                             |        +---+------+
                             v        | RQ Worker|
                       +-----+-----+  +---+------+
                       | PostgreSQL|      |
                       +-----------+<-----+
```

### Main Components

| Component | Responsibility |
|---|---|
| **Flask** | Handles HTTP requests and application logic |
| **PostgreSQL** | Persistent storage for URLs and click events |
| **Redis** | URL caching and RQ queue backend |
| **RQ** | Asynchronous task queue |
| **RQ Worker** | Processes click-event jobs |
| **GeoLite2** | IP-based country detection |
| **user-agents** | Browser and device detection |
| **HTML/CSS/JavaScript** | Project frontend |

## 🔄 How It Works

### URL Shortening

```text
Client
  |
  | POST /shorten
  v
Flask
  |
  | Generate Base62 short code
  v
PostgreSQL
  |
  v
Short URL returned
```

The application generates a unique identifier using a PostgreSQL sequence and converts it into a Base62 short code.

Custom aliases can also be supplied and are validated for uniqueness, format, and reserved-name conflicts.

### URL Redirection

```text
Client
   |
   | GET /<short_url>
   v
Flask
   |
   v
Redis Cache
   |
   +---- HIT ----> Check URL state ----> 302 Redirect
   |
   +---- MISS ---> PostgreSQL
                       |
                       v
                  Check URL state
                       |
                       v
                  Cache valid URL
                       |
                       v
                    302 Redirect
```

The redirect path checks Redis before PostgreSQL so that frequently accessed URLs can be served without a database lookup.

URL state is checked before redirecting:

| URL State | Response |
|---|---|
| Active and not expired | `302 Found` |
| Active but expired | `410 Gone` |
| Deactivated | `403 Forbidden` |
| Unknown short URL | `404 Not Found` |

### Asynchronous Click Processing

A successful redirect triggers an asynchronous click-event job.

```text
Successful Redirect
        |
        v
    RQ Queue
        |
        v
    RQ Worker
        |
        v
Click Event Processing
        |
        +---- Country
        +---- Browser
        +---- Device
        +---- Referrer
        +---- Visitor Hash
        |
        v
    PostgreSQL
```

The redirect request does not wait for the complete click-event processing operation, keeping analytics processing separate from the latency-sensitive redirect path.

## 📊 Analytics

The analytics endpoint provides information for an individual short URL:

- **Total clicks**
- **Unique visitors**
- **Top 5 countries**
- **Top 5 referrers**
- **Clicks over the last 7 days**

The backend click-event pipeline also captures **browser and device type** for each click.

The current analytics interface exposes selected aggregated views, while the underlying click-event records retain the captured event attributes for further analysis.

Country information depends on successful IP geolocation, while referrer information depends on the request containing a referrer.

The seven-day timeline is generated using UTC dates and includes zero-value days where no clicks occurred.

Visitor identification uses a salted hash rather than storing the raw visitor identifier for this purpose.

## 🔌 API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Serve the project interface |
| `POST` | `/shorten` | Create a shortened URL |
| `GET` | `/<short_url>` | Redirect to the original URL |
| `GET` | `/<short_url>/analytics` | Retrieve analytics |
| `PATCH` | `/<short_url>` | Activate or deactivate a short URL |

### `POST /shorten`

Creates a shortened URL with:

- Original URL
- Optional custom alias
- Optional expiration timestamp

### `GET /<short_url>`

Redirects to the original URL when the short URL is valid.

Possible responses:

- `302 Found`
- `403 Forbidden`
- `404 Not Found`
- `410 Gone`

### `GET /<short_url>/analytics`

Returns click and visitor analytics for the requested short URL.

### `PATCH /<short_url>`

Updates the activation state of a short URL and invalidates its Redis cache entry.

Example:

```json
{
  "is_active": false
}
```

## 🗄️ Data Model

### URL

```text
URL
├── id
├── original_url
├── short_url
├── expires_at
└── is_active
```

### ClickEvent

```text
ClickEvent
├── id
├── url_id
├── timestamp
├── country
├── browser
├── device_type
├── referrer
└── visitor_hash
```

## 🛠️ Tech Stack

- **Language:** Python
- **Backend:** Flask
- **Database:** PostgreSQL
- **ORM:** Flask-SQLAlchemy / SQLAlchemy
- **Caching:** Redis
- **Background Processing:** Redis Queue (RQ)
- **Geolocation:** GeoLite2 Country Database
- **User-Agent Parsing:** user-agents
- **Frontend:** HTML, CSS, JavaScript
- **Version Control:** Git & GitHub

## 🧪 Testing

The project includes automated tests covering the implemented functionality and important edge cases, including:

- URL shortening
- Base62 generation
- Custom aliases and collision detection
- Redirect behavior
- Redis caching
- Asynchronous click-event enqueueing
- Click analytics
- Unique visitors
- Seven-day analytics timeline
- URL expiration
- Expired-cache handling
- Link deactivation
- Link reactivation
- Cache invalidation
- Input validation

Test files:

```text
tests/
├── test_shortening.py
├── test_analytics.py
├── test_expiration.py
└── test_deactivation.py
```

## ⚡ Redirect Performance

A dedicated benchmark is included for the Redis hot-cache redirect path:

```text
benchmarks/
└── benchmark_redirect.py
```

The benchmark measures the local hot-cache redirect path using P95 latency and evaluates it against the project's **50 ms redirect target**.

The benchmark represents local performance validation and does not claim a guaranteed production latency under arbitrary deployment conditions or traffic levels.

## 📁 Project Structure

```text
URL Shortener + Click Analytics/
│
├── benchmarks/
│   └── benchmark_redirect.py
│
├── data/
│   └── GeoLite2-Country.mmdb
│
├── static/
│   ├── script.js
│   └── style.css
│
├── templates/
│   ├── deactivated.html
│   ├── expired.html
│   └── index.html
│
├── tests/
│   ├── test_analytics.py
│   ├── test_deactivation.py
│   ├── test_expiration.py
│   └── test_shortening.py
│
├── .gitignore
├── app.py
├── extensions.py
├── init_db.py
├── models.py
├── requirements.txt
├── routes.py
├── tasks.py
├── worker.py
└── README.md
```

## 🚀 Running Locally

### 1. Clone the repository

```bash
git clone https://github.com/manasidivate/URL-Shortener-Click-Analytics.git
cd URL-Shortener-Click-Analytics
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

#### Windows

```bash
venv\Scripts\activate
```

#### macOS / Linux

```bash
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file containing:

```env
DATABASE_URL=<your-postgresql-database-url>
VISITOR_HASH_SALT=<your-secret-salt>
```

Do not commit real credentials or secret values to version control.

### 5. Configure GeoLite2

Place the GeoLite2 Country database at:

```text
data/GeoLite2-Country.mmdb
```

The database is required for IP-based country detection and is excluded from version control.

### 6. Start Redis

Redis is used for both URL caching and RQ background task processing.

For a local Docker-based Redis instance:

```bash
docker run -d --name redis -p 6379:6379 redis
```

### 7. Initialize the database

```bash
python init_db.py
```

### 8. Start the Flask application

```bash
python app.py
```

### 9. Start the RQ worker

In a separate terminal:

```bash
python worker.py
```

The Flask application handles HTTP requests while the RQ worker processes click-event jobs asynchronously.

## 📌 Project Status

| Area | Status |
|---|---|
| Core functional implementation | ✅ Complete |
| Redirect performance and local validation | ✅ Complete |
| Production-readiness improvements | 🚧 In progress |
| Deployment | ⏳ Not yet deployed |

The core system is complete, including URL shortening, cached redirection, asynchronous click tracking, analytics, custom aliases, URL expiration, and link deactivation. The project is currently undergoing production-readiness improvements before deployment.