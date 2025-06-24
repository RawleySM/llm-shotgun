# Deployment Guide

This guide provides instructions for deploying the FastAPI React Starter application to a production environment. The primary method described uses Docker and Docker Compose.

## 1. Deployment Overview

The recommended way to deploy this application is using Docker Compose. This method packages the backend, frontend, and database into manageable services.

For a robust production setup, you'll typically place a reverse proxy (like Nginx or Traefik) in front of the application to handle HTTPS, load balancing, and potentially serve static frontend assets more efficiently.

## 2. Prerequisites

*   **Server:** A server (VPS, dedicated server, or cloud instance) running a Linux distribution.
*   **Docker & Docker Compose:** Ensure Docker and Docker Compose (v2 plugin) are installed on your server. Follow the official installation guides.
*   **Domain Name:** A registered domain name pointing to your server's IP address.
*   **SSL Certificates:** SSL certificates for your domain to enable HTTPS (e.g., from Let's Encrypt).
*   **Firewall:** Configure your server's firewall to allow traffic on necessary ports (e.g., 80 for HTTP, 443 for HTTPS).

## 3. Production Configuration

Before deploying, you **must** configure environment variables for production. It's highly recommended to use a separate `.env` file for production or manage these variables securely through your deployment environment.

### 3.1. Root `.env` File (for Docker Compose)

Create or update the `.env` file in your project root on the server:

```env
# Database Configuration (ensure these are strong, unique credentials)
DB_USER=your_prod_db_user
DB_PASSWORD=your_prod_db_password
DB_NAME=your_prod_db_name

# Backend Production Settings (passed to backend service in docker-compose.yml)
ENVIRONMENT=production
JWT_SECRET_KEY=generate_a_very_strong_random_secret_key # IMPORTANT! Change this!
PROD_CORS_ORIGINS=["https://yourdomain.com","https://www.yourdomain.com"] # Your frontend domain(s)

# Frontend Production Settings (passed to frontend service in docker-compose.yml)
PROD_VITE_API_URL=https://yourdomain.com/api # URL of your backend API
```

**Key Production Variables:**

*   `DB_USER`, `DB_PASSWORD`, `DB_NAME`: Use strong, unique credentials for your production database.
*   `ENVIRONMENT=production`: Sets the application to run in production mode (affects logging, error handling, etc., as defined in `backend/app/config/config.py`).
*   `JWT_SECRET_KEY`: **CRITICAL!** This key is used to sign JWTs. It **must** be a long, random, and secret string. Do not use the development default. You can generate one using `openssl rand -hex 32`.
*   `PROD_CORS_ORIGINS`: A JSON-formatted string array of allowed origins for CORS. Replace `https://yourdomain.com` with your actual frontend domain(s).
*   `PROD_VITE_API_URL`: The public URL where your backend API will be accessible (e.g., if served under `/api` via a reverse proxy).

### 3.2. Docker Compose Adjustments for Production

It's best practice to have a production-specific Docker Compose file (e.g., `docker-compose.prod.yml`) or to modify the existing `docker-compose.yml` for production needs. Here are key changes to consider:

*   **Remove Development Volumes:** For the `backend` and `frontend` services, remove the host-mounted volumes that map your local code into the container (e.g., `volumes: - ./backend:/app`). In production, the code should be copied into the image during the build process.
*   **Production Commands:**
    *   **Backend:** Change the `command` to use a production-grade ASGI server like Gunicorn with Uvicorn workers. Example:
        ```yaml
        # In docker-compose.yml for backend service
        command: gunicorn -k uvicorn.workers.UvicornWorker -w 4 app.main:app --bind 0.0.0.0:8000
        ```
        Adjust the number of workers (`-w 4`) based on your server's CPU cores.
    *   **Frontend:** The `command` should serve the built static assets or run a production Node.js server if applicable. If your `frontend/Dockerfile` builds static assets (e.g., into `/app/dist`), you might use a multi-stage Dockerfile with a lightweight web server like Nginx to serve these files. Alternatively, if `npm run build` creates a `dist` folder, and your `Dockerfile` copies it and `npm start` (or a similar command in `package.json`) serves it with a production-ready static server, that can also work.
        *If serving frontend static files via Nginx (either in the frontend container or a separate reverse proxy container), the frontend service in `docker-compose.yml` might not need to expose a port directly or could be simplified.*
*   **Environment Variables:** Update the `environment` section in `docker-compose.yml` for `backend` and `frontend` services to use the production values defined in your root `.env` file:
    ```yaml
    # backend service
    environment:
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD=${DB_PASSWORD}
      - DB_HOST=postgres # Stays as the service name
      - DB_PORT=5432
      - CORS_ORIGINS=${PROD_CORS_ORIGINS}
      - ENVIRONMENT=${ENVIRONMENT:-production} # Default to production
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}      # Passed from root .env

    # frontend service
    environment:
      - VITE_API_URL=${PROD_VITE_API_URL} # Passed from root .env
      # Add any other necessary production env vars for frontend build/runtime
    ```
*   **Ports:** Only expose ports that need to be accessed externally (typically via a reverse proxy, e.g., port 80 or 443). Internal service-to-service communication uses Docker's internal network.

**Example `docker-compose.prod.yml` (Illustrative - combine with your base `docker-compose.yml`):**

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  backend:
    # Remove development volume mount if present in base file
    # volumes: [] # Clears volumes from base file if using extends
    command: gunicorn -k uvicorn.workers.UvicornWorker -w 4 app.main:app --bind 0.0.0.0:8000
    environment:
      - ENVIRONMENT=production
      - CORS_ORIGINS=${PROD_CORS_ORIGINS}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    # Potentially remove port mapping if accessed via reverse proxy
    # ports:
    #   - "8000:8000"

  frontend:
    # Remove development volume mount
    # volumes: []
    # command: npm run start # Or command to serve built static files
    environment:
      - VITE_API_URL=${PROD_VITE_API_URL}
    # Potentially remove port mapping
    # ports:
    #  - "5173:5173"

# Ensure postgres_data volume is still defined as in the base docker-compose.yml
# volumes:
#   postgres_data:
```

To use multiple compose files: `docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d`

## 4. Building and Running in Production

1.  **Transfer Project:** Copy your project files (including your production-ready Dockerfiles and Docker Compose files) to your server.
2.  **Create `.env` file:** Create the root `.env` file on your server with production values as described above.
3.  **Pull latest images (optional but good practice):**
    ```bash
    docker compose pull # Pulls base images like postgres:17-alpine
    ```
4.  **Build and Start Services:**
    ```bash
    # If using a single, modified docker-compose.yml
    docker compose up --build -d

    # If using docker-compose.prod.yml to override/extend
    docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
    ```
    The `--build` flag ensures images are rebuilt. The `-d` flag runs services in detached mode.

5.  **Database Migrations:** The backend service is configured with `command: bash -c "python manage.py run"` which internally calls `migrate` before starting the app. If you change this command for production (e.g., to Gunicorn directly), ensure migrations are run as a separate step or as part of your container's entrypoint script before the main application starts.
    ```bash
    # Example of running migrations manually if needed
    docker compose exec backend python manage.py migrate
    ```

## 5. Data Persistence

The `docker-compose.yml` defines a named volume `postgres_data` for the PostgreSQL database. This ensures that your database data persists even if the `postgres` container is stopped or removed. Ensure this volume is properly managed and backed up as part of your server maintenance routine.

## 6. Reverse Proxy and HTTPS (Recommended)

For production, it's highly recommended to use a reverse proxy like **Nginx** or **Traefik**.

**Benefits:**
*   **HTTPS/SSL Termination:** Handle SSL certificates and encrypt traffic.
*   **Load Balancing:** (If you scale to multiple instances of your backend).
*   **Serving Static Files:** Nginx is very efficient at serving static frontend assets.
*   **Custom Domain Names:** Easily map your domain to the application.
*   **Security:** Can add security headers, rate limiting, etc.

**General Setup with Nginx (Conceptual):**
1.  Install Nginx on your server.
2.  Configure Nginx as a reverse proxy to forward requests to your Dockerized services:
    *   Requests to `yourdomain.com/api/*` could go to the `backend` service (e.g., `http://localhost:8000`).
    *   Requests to `yourdomain.com/*` could serve the static frontend assets (if built and served by Nginx) or go to the `frontend` service (e.g., `http://localhost:5173`).
3.  Set up SSL certificates (e.g., using Certbot with Let's Encrypt) for your domain in Nginx.

*Refer to Nginx or Traefik documentation for detailed configuration instructions.*

## 7. Deploying Documentation (MkDocs)

The `docs` service in `docker-compose.yml` serves the documentation.

1.  Ensure the `docs` service is included when you run `docker compose up`.
2.  If you have a reverse proxy, configure it to route traffic from a subdomain (e.g., `docs.yourdomain.com`) or a path (e.g., `yourdomain.com/project-docs/`) to the `docs` service (e.g., `http://localhost:8001`).

Alternatively, you can build the MkDocs site into static HTML files and deploy them to any static hosting provider (e.g., GitHub Pages, Netlify, AWS S3):

```bash
# From your local machine, in the project root
docker compose run --rm docs mkdocs build
```
This will generate the static site in the `docs/site/` directory (or as configured in `mkdocs.yml`). You can then upload this `site` directory.

## 8. Monitoring and Logging

*   **Application Logs:** Use `docker compose logs backend` and `docker compose logs frontend` to view application logs.
*   **Server Monitoring:** Implement server-level monitoring for CPU, memory, disk space, and network traffic.
*   **Log Aggregation:** For more robust logging, consider setting up a centralized logging solution (e.g., ELK stack, Grafana Loki, or a cloud provider's logging service).

---

Deploying a web application involves many considerations. This guide provides a starting point. Always adapt the configuration to your specific security and performance requirements.