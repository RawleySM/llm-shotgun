# Make It Yours: Customizing the Starter Template

This guide helps you take the FastAPI React Starter template and adapt it into your own unique project.

## 1. Introduction

The FastAPI React Starter is designed to give you a head start with a modern tech stack and a sensible project structure. Follow these steps to rebrand and customize it.

## 2. Renaming the Project

Consistent naming is key. Here's where to change the project's name:

*   **Root Directory:**
    *   Rename the main project folder (e.g., `fastapi-react-starter` to `my-awesome-project`).
    *   If you've already pushed to a Git remote, you might need to update the remote URL or create a new repository.

*   **Backend (`backend/pyproject.toml`):
    *   Update the `name` under `[tool.poetry]`:
        ```toml
        [tool.poetry]
        name = "my-awesome-project-backend"
        # ... other settings
        ```

*   **Frontend (`frontend/package.json`):
    *   Update the `name` field:
        ```json
        {
          "name": "my-awesome-project-frontend",
          // ... other settings
        }
        ```

*   **Backend Configuration (`backend/app/config/config.py`):
    *   Change the `APP_NAME` in the `Settings` class:
        ```python
        class Settings(BaseSettings):
            APP_NAME: str = "My Awesome Project"
            # ... other settings
        ```

*   **Documentation (`docs/mkdocs.yml`):
    *   Update `site_name`:
        ```yaml
        site_name: My Awesome Project Docs
        ```
    *   Consider adding/updating `site_author` and `repo_url`:
        ```yaml
        site_author: Your Name or Organization
        repo_url: https://github.com/your-username/my-awesome-project
        site_url: https://docs.my-awesome-project.com # If you deploy docs publicly
        ```

*   **Frontend Title (`frontend/index.html`):
    *   Update the `<title>` tag and `<meta name="description">`:
        ```html
        <head>
            <meta charset="UTF-8" />
            <link rel="icon" type="image/x-icon" href="/favicon.ico" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <meta name="description" content="Description of My Awesome Project." />
            <title>My Awesome Project</title>
        </head>
        ```

## 3. Customizing Backend (FastAPI)

*   **Core Logic:**
    *   Review and modify/remove existing example routes in `backend/app/routes/` (e.g., `auth.py`, `health.py`).
    *   Update or replace schemas in `backend/app/schemas/`.
    *   Adapt or remove services in `backend/app/services/`.
    *   Define your own SQLAlchemy models in `backend/app/db/models.py` and generate new migrations (see [Development Guide](development.md#database-migrations)).
*   **Configuration (`backend/app/config/config.py`):
    *   **CRITICAL:** Set a new, strong `SECRET_KEY` (or `JWT_SECRET_KEY` environment variable) for JWT authentication. Do not use the development default.
    *   Adjust `CORS_ORIGINS` for your frontend's domain(s).
    *   Review other settings (database connection, API prefix, etc.).
*   **Dependencies (`backend/requirements.txt` or `backend/pyproject.toml`):
    *   Add, remove, or update Python dependencies based on your project's needs.

## 4. Customizing Frontend (React)

*   **Core Logic & UI:**
    *   Review and modify/remove example components in `frontend/src/components/` and `frontend/src/features/`.
    *   Update routes in `frontend/src/App.tsx` or `frontend/src/routes/`.
    *   Adapt or remove custom hooks in `frontend/src/hooks/`.
*   **Styling (Tailwind CSS & shadcn/ui):**
    *   Modify `frontend/tailwind.config.js` to customize your Tailwind theme (colors, fonts, etc.).
    *   Adjust global styles in `frontend/src/index.css` (or equivalent).
    *   Customize or replace shadcn/ui components from `frontend/src/components/ui/`.
*   **Public Assets:**
    *   Replace `frontend/public/favicon.ico` and other icons/logos with your own.
    *   Update any static images or assets in `frontend/public/`.
*   **Dependencies (`frontend/package.json`):
    *   Add, remove, or update Node.js dependencies.

## 5. Docker Configuration (`docker-compose.yml`)

*   **Container Names:** For clarity, update `container_name` for each service:
    ```yaml
    services:
      postgres:
        container_name: myproject-db
        # ...
      backend:
        container_name: myproject-backend
        # ...
      frontend:
        container_name: myproject-frontend
        # ...
      docs:
        container_name: myproject-docs
        # ...
    ```
*   **Image Names:** If you plan to build and push Docker images to a registry, you'll want to tag them appropriately in your build process (e.g., `your-registry/myproject-backend:latest`). The `build:` context in `docker-compose.yml` defines how images are built locally.

## 6. Documentation

*   **Content:** Update `docs/index.md` with your project's overview.
*   Review and modify all other `.md` files in the `docs/` directory to reflect your project's specifics, removing or altering template-related information.
*   **Configuration (`docs/mkdocs.yml`):** As mentioned in section 2, update `site_name`, `site_author`, `repo_url`, and `site_url`.

## 7. License

*   The starter template uses the MIT License. If your project requires a different license, update the `LICENSE` file in the project root.

## 8. Cleaning Up

*   Search for and remove any template-specific comments, `TODO` items, or placeholder code that is no longer relevant.
*   Remove or replace example images, SVGs (like `frontend/public/starter.svg`), and other assets.
*   Ensure all example user accounts, data, or configurations are cleared before deploying to production.

By following these steps, you can effectively transform the FastAPI React Starter template into a solid foundation for your own application.