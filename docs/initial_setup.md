# Initial Project Setup

This guide walks you through setting up the FastAPI React Starter project on your local machine. You can choose between the recommended Docker-based setup, using automated scripts, or a manual setup process.

## Prerequisites

Before you begin, ensure you have the following software installed:

*   **Git:** For cloning the repository. ([Download Git](https://git-scm.com/downloads))
*   **Docker & Docker Compose (v2):** For the recommended Docker-based setup and for running the automated setup scripts. Docker Desktop for Windows and Mac typically includes both. ([Download Docker Desktop](https://www.docker.com/products/docker-desktop))
    *   For Linux, you'll need to install Docker Engine and the Docker Compose plugin.
*   **Python (3.10+):** Required for manual backend setup. ([Download Python](https://www.python.org/downloads/))
*   **Node.js (LTS version, e.g., 20.x) & npm:** Required for manual frontend setup. npm is included with Node.js. ([Download Node.js](https://nodejs.org/))

## 1. Clone the Repository

First, clone the project repository to your local machine:

```bash
git clone https://github.com/raythurman2386/fastapi-react-starter.git
cd fastapi-react-starter
```

## 2. Environment Configuration

This project uses `.env` files for managing environment variables.

*   **For Docker Setup & Automated Scripts:**
    Create a `.env` file in the **project root directory** (`fastapi-react-starter/.env`). You can copy the example if it exists, or create it with the following content:

    ```env
    # Database Configuration (used by Docker Compose)
    DB_USER=postgres
    DB_PASSWORD=postgres
    DB_NAME=fastapi_db
    ```
    *Note: The automated setup scripts (`setup.ps1`, `setup.sh`) will attempt to create this file from `.env.example` if present.*

*   **For Manual Backend Setup:**
    Create a `.env` file in the `backend` directory (`fastapi-react-starter/backend/.env`):

    ```env
    # Database Configuration
    DB_NAME=fastapi_db
    DB_USER=your_db_user      # Your PostgreSQL username
    DB_PASSWORD=your_db_password  # Your PostgreSQL password
    DB_HOST=localhost
    DB_PORT=5432

    # FastAPI Settings
    ENVIRONMENT=development
    CORS_ORIGINS=["http://localhost:5173"] # Frontend URL for CORS
    # SECRET_KEY=your_strong_secret_key_here # Generate a strong secret key
    # ALGORITHM=HS256
    # ACCESS_TOKEN_EXPIRE_MINUTES=30
    ```
    *Ensure you update database credentials and uncomment/set `SECRET_KEY`.*

*   **For Manual Frontend Setup:**
    The frontend uses Vite, which handles environment variables prefixed with `VITE_`. The primary variable needed is `VITE_API_URL` to point to the backend.
    Create a `.env` file in the `frontend` directory (`fastapi-react-starter/frontend/.env`):

    ```env
    VITE_API_URL=http://localhost:8000
    ```

## 3. Setup Methods

Choose one of the following methods to set up the project:

### Method A: Using Docker (Recommended)

This is the simplest way to get all services (backend, frontend, database, documentation) up and running.

1.  Ensure Docker Desktop (or Docker Engine + Compose plugin on Linux) is running.
2.  Ensure the root `.env` file is configured as described above.
3.  From the project root directory, run:

    ```bash
    docker compose up --build
    ```
    To run in detached mode (in the background), add the `-d` flag:
    ```bash
    docker compose up --build -d
    ```

    This command will:
    *   Build the Docker images for the backend, frontend, and documentation services.
    *   Start containers for PostgreSQL, backend, frontend, and docs.
    *   The backend will apply database migrations automatically on startup.

### Method B: Automated Setup Scripts

The project includes scripts to help automate the initial Docker environment setup (checking dependencies and creating the root `.env` file).

*   **For Windows:**
    1.  Open PowerShell as Administrator.
    2.  Navigate to the project root directory.
    3.  Run the script:
        ```powershell
        .\setup.ps1
        ```
        The script will check for Docker Desktop and attempt to install it via `winget` if not found. It will also create a root `.env` file from `.env.example` if available.

*   **For Linux/Mac:**
    1.  Open your terminal.
    2.  Navigate to the project root directory.
    3.  Make the script executable and run it:
        ```bash
        chmod +x setup.sh
        ./setup.sh
        ```
        The script will check for Docker and attempt to install it using the official convenience script if not found. It also creates the root `.env` file.

    After running the script, proceed with the Docker Compose command as in Method A:
    ```bash
    docker compose up --build -d
    ```

### Method C: Manual Setup

Follow these steps if you prefer to run the backend and frontend services directly on your host machine without Docker.

1.  **Backend Setup:**
    *   **Install PostgreSQL:** Install PostgreSQL locally and ensure it's running. Create a database (e.g., `fastapi_db`) and a user with privileges for this database.
    *   **Configure `backend/.env`:** Create and configure `fastapi-react-starter/backend/.env` as described in the "Environment Configuration" section, ensuring database credentials match your local PostgreSQL setup.
    *   **Install Python Dependencies:**
        ```bash
        cd backend
        python -m venv venv  # Create a virtual environment (optional but recommended)
        source venv/bin/activate  # On Windows: venv\Scripts\activate
        pip install -r requirements.txt
        ```
    *   **Run Database Migrations:**
        ```bash
        python manage.py migrate
        ```
    *   **Run Backend Server:**
        ```bash
        uvicorn app.main:app --reload --port 8000
        ```

2.  **Frontend Setup:**
    *   **Configure `frontend/.env`:** Create `fastapi-react-starter/frontend/.env` as described in the "Environment Configuration" section, ensuring `VITE_API_URL` points to your manually running backend (e.g., `http://localhost:8000`).
    *   **Install Node.js Dependencies:**
        ```bash
        cd frontend
        npm install
        ```
    *   **Run Frontend Development Server:**
        ```bash
        npm run dev
        ```
        This will typically start the frontend on `http://localhost:5173`.

## 4. Accessing the Application

Once the setup is complete and services are running:

*   **Frontend Application:** [http://localhost:5173](http://localhost:5173)
*   **Backend API (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)
*   **Project Documentation (if using Docker/docs service):** [http://localhost:8001](http://localhost:8001)

## Next Steps

*   Explore the **[Development Guide](development.md)** for information on project structure, coding standards, and common development tasks.
*   If you plan to customize this starter for your own project, check out **[Make It Yours](make_it_yours.md)**.