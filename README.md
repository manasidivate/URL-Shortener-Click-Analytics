# URL Shortener + Click Analytics

A backend-focused URL shortening system built with **Flask, PostgreSQL, Redis, and RQ**, designed to provide fast URL redirection and asynchronous click-event processing.

The project is being developed incrementally, with a focus on backend architecture, caching, background task processing, and analytics.

## ✨ Features

### Completed

- Create shortened URLs using **Base62 encoding**
- Generate unique short codes using a PostgreSQL sequence
- Redirect users from short URLs to their original URLs
- Cache hot URL mappings using **Redis**
- Process click events asynchronously using **RQ**
- Capture click-event data including:
  - Timestamp
  - IP-derived country
  - Browser
  - Device type
  - HTTP referrer
- Store URL mappings and click events persistently in **PostgreSQL**

### In Progress

- Click analytics
- Custom URL aliases
- URL expiration
- Link deactivation

## 🛠️ Tech Stack

- **Language:** Python
- **Backend:** Flask
- **Database:** PostgreSQL
- **ORM:** SQLAlchemy
- **Caching:** Redis
- **Background Processing:** RQ
- **Geolocation:** GeoLite2 Country Database
- **User-Agent Parsing:** user-agents
- **Containerization:** Docker
- **Version Control:** Git & GitHub

## 🏗️ System Architecture

The application follows a request-processing flow where URL redirection is handled immediately, while click-event processing is delegated to a background worker.

```text
Client
  |
  v
Flask Application
  |
  +----> Redis Cache
  |           |
  |           +---- Cache Hit ----> Original URL
  |           |
  |           +---- Cache Miss
  |                    |
  |                    v
  |                PostgreSQL
  |                    |
  |                    v
  |                Cache URL
  |                    |
  |                    v
  |                Original URL
  |
  +----> RQ Queue
             |
             v
        RQ Worker
             |
             v
      Click Event Processing
             |
             v
        PostgreSQL
```

## 🔄 How It Works

### URL Shortening

1. The client submits an original URL.
2. The application obtains a unique ID from a PostgreSQL sequence.
3. The ID is converted into a short code using **Base62 encoding**.
4. The original URL and generated short code are stored in PostgreSQL.

### URL Redirection

1. The client requests the short URL.
2. The application checks Redis for the cached URL mapping.
3. On a cache hit, the original URL is retrieved from the cache.
4. On a cache miss, the mapping is retrieved from PostgreSQL and added to Redis.
5. A click-event job is placed into the RQ queue.
6. The client is redirected without waiting for click-event processing to finish.

### Asynchronous Click Tracking

Click-event data is captured during the redirect request and passed to an RQ background job.

The worker processes the event independently and stores the resulting click-event record in PostgreSQL.

The processing includes:

- Country detection from IP address
- Browser detection from User-Agent
- Device-type detection
- Referrer capture

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/shorten` | Create a shortened URL |
| `GET` | `/<short_url>` | Redirect to the original URL |

Additional analytics and URL-management endpoints will be added as the remaining features are implemented.

## 📁 Project Structure

```text
URL-Shortener-Click-Analytics/
│
├── data/
│   └── GeoLite2-Country.mmdb
│
├── static/
│   ├── script.js
│   └── style.css
│
├── templates/
│   └── index.html
│
├── .env
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

> The GeoLite2 database file is required locally for country detection and is excluded from version control.

## 🚀 Running the Project Locally

### 1. Clone the repository

```bash
git clone <repository-url>
cd URL-Shortener-Click-Analytics
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
```

On Windows:

```bash
venv\Scripts\activate
```

On macOS/Linux:

```bash
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file with the required PostgreSQL configuration and other environment-specific values used by the application.

### 5. Start Redis

Redis is used for both caching and RQ background task processing.

If using Docker:

```bash
docker run -d --name redis -p 6379:6379 redis
```

### 6. Initialize the database

```bash
python init_db.py
```

### 7. Start the Flask application

```bash
python app.py
```

### 8. Start the RQ worker

In a separate terminal:

```bash
python worker.py
```

The Flask application handles URL requests, while the RQ worker processes click-event jobs asynchronously.

## 📊 Current Development Status

| Feature | Status |
|---------|--------|
| URL Shortening | ✅ Completed |
| URL Redirection & Caching | ✅ Completed |
| Asynchronous Click Tracking | ✅ Completed |
| Click Analytics | 🚧 In Progress |
| Custom Aliases | 🚧 In Progress |
| URL Expiration | 🚧 In Progress |
| Link Deactivation | 🚧 In Progress |

## 🧠 Key Backend Concepts Demonstrated

- REST API fundamentals
- Base62 encoding
- PostgreSQL sequences
- Relational data modeling
- SQLAlchemy ORM
- Redis caching
- Cache hit/miss handling
- Asynchronous task processing
- Task queues and workers
- Request/response flow
- Persistent database storage
- User-Agent parsing
- IP-based geolocation

## 🔮 Future Enhancements

- Complete click analytics
- Add custom aliases with collision detection
- Add URL expiration
- Add link deactivation
- Improve cache efficiency
- Add additional API validation and error handling
- Add automated testing