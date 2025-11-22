# MithrilLog Gateway Documentation

## How It Works

The MithrilLog Gateway provides a centralized, secure entry point for multiple Log Summarizer instances. It uses a combination of **Nginx** and a **Python FastAPI** application to handle authentication and routing.

### Architecture Flow
1.  **User Request**: You access the gateway (e.g., `http://server:1515/`).
2.  **Nginx Routing**: Nginx receives the request.
    *   If it's for the root `/`, it proxies to the **Gateway App** (Login Page).
    *   If it's for a project path `/p/project1/`, it first sends an internal **Auth Request** to the Gateway App.
3.  **Authentication Check**:
    *   The Gateway App checks your session cookie.
    *   It verifies if the session is valid and if you are authorized for the requested project.
    *   **Success (200)**: Nginx allows the request to proceed to the upstream project (e.g., `localhost:9000`).
    *   **Failure (401)**: Nginx redirects you to the login page.
4.  **Project Access**: Once authenticated, Nginx proxies your traffic to the specific project running on `localhost`.

## How to Define a New Project

Adding a new project involves two steps: updating the Gateway configuration and updating Nginx.

### 1. Update `gateway/config.yaml`
Add a new entry under the `projects` list.
```yaml
projects:
  - id: project4                # Unique Identifier (used in URL)
    name: "Project Delta"       # Display Name
    password: "newpassword123"  # Access Password
    upstream_url: "http://127.0.0.1:9999" # Where the project is running
```

### 2. Update `gateway/nginx/nginx.conf`
Add a new location block for the project. **Copy and paste** an existing block and change the ID and port.

```nginx
    # Project 4
    location = /p/project4 {
        return 302 /p/project4/;  # Force trailing slash
    }

    location /p/project4/ {
        auth_request /_auth;      # Enable Authentication
        error_page 401 = @error401;

        proxy_pass http://127.0.0.1:9999/; # Match upstream_url port
        
        # Standard Proxy Headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
```

### 3. Restart Gateway
Apply the changes by restarting the gateway services:
```bash
cd gateway
docker-compose restart
```

## Security Assessment

### ✅ Strengths
*   **Network Isolation**: Your projects (ports 9000, 9800, etc.) are bound to `127.0.0.1`. They are **completely invisible** to the public internet. Only the Gateway can reach them.
*   **Centralized Auth**: A single point of entry means you don't need to manage separate authentication logic for each project.
*   **Session Management**: Uses secure, HTTP-only cookies with expiration times.

### ⚠️ Considerations & Recommendations
*   **HTTPS (SSL/TLS)**: Currently, the system runs over HTTP. Passwords and session cookies are sent in plain text. **For production use, you MUST put this behind a secure reverse proxy (like Cloudflare, AWS ALB, or a main Nginx with Let's Encrypt) that terminates SSL.**
*   **Password Storage**: Passwords are stored in plain text in `config.yaml`. Ensure this file is readable only by root/admin.
*   **Shared Domain**: Since all projects are served under the same domain/port, cookies are shared. The Gateway logic enforces project isolation, but cross-site scripting (XSS) on one project could theoretically affect others.
