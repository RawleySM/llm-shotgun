# Development Guide

This guide provides instructions and best practices for developing within the FastAPI React Starter project.

## 1. Project Structure Overview

The project is organized into a `backend` (FastAPI) and a `frontend` (React) directory, along with a `docs` directory for this documentation and root-level configuration files.

*   **`backend/`**: Contains the FastAPI application.
    *   `app/`: Core application code (main app, config, db, routes, schemas, services, utils).
    *   `requirements.txt`: Python dependencies.
    *   `pyproject.toml`: Project metadata and tool configuration (e.g., Black).
    *   `manage.py`: Script for database migrations and other management commands.
*   **`frontend/`**: Contains the React application.
    *   `src/`: Core application code (components, features, hooks, layouts, etc.).
    *   `package.json`: Node.js dependencies and scripts.
    *   `vite.config.ts`: Vite build configuration.
    *   `tailwind.config.js`: Tailwind CSS configuration.
*   **`docs/`**: Project documentation (MkDocs).
*   **`docker-compose.yml`**: Defines the services for Docker.
*   **`.pre-commit-config.yaml`**: Configuration for pre-commit hooks.

For a more detailed visual structure, refer to the `README.md` or the [Project Overview](index.md).

## 2. Backend Development (FastAPI)

### Key Directories

*   **`app/main.py`**: FastAPI application entry point.
*   **`app/config/config.py`**: Environment settings and logging configuration.
*   **`app/db/`**: Database connection (`database.py`) and SQLAlchemy models (`models.py`).
*   **`app/routes/`**: API endpoint definitions.
*   **`app/schemas/`**: Pydantic models for data validation and serialization.
*   **`app/services/`**: Business logic and service layer.
*   **`app/utils/`**: Utility functions (e.g., custom logger setup, though primary logging is in `config.py`).

### Linting and Formatting

*   **Black**: Code formatting is enforced using Black. Configuration is in `pyproject.toml` (`line-length = 100`).
    *   It's recommended to integrate Black into your IDE or run it manually before committing:
        ```bash
        # Navigate to backend directory
        cd backend
        black .
        ```
*   **Pre-commit Hooks**: Black is also run as a pre-commit hook (see section below).
*   **(Optional) Ruff/Flake8/MyPy**: Consider adding Ruff (for linting and formatting, can replace Black/Flake8) or MyPy (for static type checking) for enhanced code quality. Add them to `requirements-dev.txt` and `.pre-commit-config.yaml`.

### Running Tests

*(Documentation on the testing framework (e.g., Pytest) and how to run tests should be added here. This might include setup, fixtures, and example commands.)*

Example (if using Pytest):

```bash
# Navigate to backend directory
cd backend
pytest
```

### Database Migrations

The project uses Alembic for database migrations, managed via `manage.py`.

*   **Generate a new migration (after changing models):**
    ```bash
    # Ensure you are in the backend directory
    cd backend
    python manage.py makemigrations "Your descriptive migration message"
    ```
*   **Apply migrations:**
    ```bash
    python manage.py migrate
    ```
*   **Check migration status:**
    ```bash
    python manage.py db-status
    ```
*   **Downgrade (revert) last migration:**
    ```bash
    python manage.py downgrade
    ```
*   **Reset database (development only - drops all tables and reapplies all migrations):**
    ```bash
    python manage.py reset_db
    ```

### Logging

Structured logging is configured in `backend/app/config/config.py`. The main application logger can be imported and used as follows:

```python
from app.config import logger

logger.info("This is an info message.")
logger.error("This is an error message.")
```

### Adding New Features

1.  **Models (`app/db/models.py`):** Define or update SQLAlchemy models.
2.  **Schemas (`app/schemas/`):** Create Pydantic schemas for request/response validation and serialization.
3.  **Services (`app/services/`):** Implement the business logic.
4.  **Routes (`app/routes/`):** Define new API endpoints, using the services and schemas.
5.  **Migrations:** Generate and apply database migrations if models changed.
6.  **Tests:** Write tests for the new functionality.

## 3. Frontend Development (React)

### Key Directories

*   **`src/App.tsx`**: Main React application component and router setup.
*   **`src/components/`**: Reusable UI components.
    *   `ui/`: shadcn/ui components.
*   **`src/features/`**: Feature-specific modules (e.g., auth, health).
*   **`src/hooks/`**: Custom React hooks.
*   **`src/layouts/`**: Page layout components.
*   **`src/lib/`**: Utility functions and configurations (e.g., `utils.ts` for shadcn).
*   **`src/routes/`**: Page components rendered by React Router.
*   **`src/types/`**: TypeScript type definitions.

### Linting, Formatting, and Type Checking

*   **Prettier**: Code formatting is enforced using Prettier. It's configured to run via pre-commit hooks.
    *   To format manually:
        ```bash
        # Navigate to frontend directory
        cd frontend
        npm run format
        ```
    *   To check formatting:
        ```bash
        npm run format:check
        ```
*   **ESLint**: (Consider adding ESLint for code quality and style rules if not already implicitly handled by Prettier/TypeScript setup).
*   **TypeScript**: Static type checking is performed by TypeScript.
    *   To type-check the project:
        ```bash
        # Navigate to frontend directory
        cd frontend
        npm run typecheck
        ```

### Running Tests

*(Documentation on the testing framework (e.g., Vitest, React Testing Library) and how to run tests should be added here. This might include setup, example tests, and commands.)*

Example (if using Vitest with an `npm run test` script):

```bash
# Navigate to frontend directory
cd frontend
npm run test
```

### Styling

*   **Tailwind CSS**: Utility-first CSS framework used for styling. Configuration is in `frontend/tailwind.config.js`.
*   **shadcn/ui**: Collection of beautifully designed, accessible, and customizable React components built with Radix UI and Tailwind CSS. Components are typically added via the shadcn/ui CLI and can be found in `src/components/ui/`.

### Adding New Features/Components

1.  **Define Types (`src/types/`):** If new data structures are involved.
2.  **Create Components (`src/components/` or `src/features/`):** Develop new React components.
3.  **Implement Hooks (`src/hooks/`):** For reusable logic or data fetching.
4.  **Add Routes (`src/App.tsx` or `src/routes/`):** If new pages are needed.
5.  **Style:** Use Tailwind CSS classes and shadcn/ui components.
6.  **Tests:** Write tests for new components and logic.

## 4. Working with Docker (Development)

While developing, you might need to interact with the Docker containers:

*   **View logs for all services:**
    ```bash
    docker compose logs -f
    ```
*   **View logs for a specific service (e.g., backend):**
    ```bash
    docker compose logs -f backend
    ```
*   **Access a shell in a running container (e.g., backend):**
    ```bash
    docker compose exec backend /bin/bash
    ```
*   **Rebuild and restart a specific service (e.g., backend after changing dependencies):**
    ```bash
    docker compose up --build -d backend
    ```
*   **Stop all services:**
    ```bash
    docker compose down
    ```

## 5. Pre-commit Hooks

The project uses pre-commit hooks managed by `pre-commit` to automatically lint and format code before committing. The configuration is in `.pre-commit-config.yaml`.

**Hooks include:**
*   `trailing-whitespace`: Removes trailing whitespace.
*   `end-of-file-fixer`: Ensures files end with a single newline.
*   `check-yaml`: Checks YAML files for syntax errors.
*   `check-added-large-files`: Prevents committing large files.
*   `black`: Formats Python code.
*   `prettier`: Formats frontend code (JS, TS, JSON, CSS, Markdown).

**Setup:**
If you haven't already, install `pre-commit` and set up the hooks:

```bash
# Install pre-commit (if not already installed, e.g., via pip or brew)
pip install pre-commit

# Install the git hook scripts from the project root
pre-commit install
```
Now, the hooks will run automatically on `git commit`.

## 6. Debugging Tips

*   **Backend (FastAPI):**
    *   Use `print()` statements or the configured `logger`.
    *   FastAPI's interactive debugger (if an error occurs in development mode).
    *   Set breakpoints if using an IDE with debugging capabilities (e.g., VS Code).
    *   Check `docker compose logs backend` for errors if running via Docker.
*   **Frontend (React):**
    *   Use browser developer tools (console, network tab, React DevTools extension).
    *   `console.log()` statements.
    *   React DevTools for inspecting component hierarchy, state, and props.
    *   Check `docker compose logs frontend` for build errors if running via Docker.

---

This development guide should help you get started. Happy coding!