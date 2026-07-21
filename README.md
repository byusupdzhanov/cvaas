# CVaaS

CVaaS is a self-hosted resume service with an admin panel.

It lets you:
- publish a public resume on your own domain;
- manage experience, skills, education, languages, courses, projects, certificates, and recommendations;
- export or import resume data as JSON;
- generate a printable / PDF version of the resume;
- keep everything in a small, straightforward Docker-based setup.


## Demo

<img src="./docs/media/demo.gif" alt="CVaaS demo" width="1100">

## Media Assets

Repository-tracked visual assets are stored separately from runtime uploads:

- `static/brand/` — logo, favicon, and brand assets used by the app;
- `docs/media/` — screenshots and GIFs for the README and release materials;
- `static/uploads/` — runtime user uploads such as profile photos and certificate files.

`static/uploads/` stays ignored on purpose, so local resume data and uploaded files do not get committed accidentally.

## Features

- Public resume page
- Admin panel for editing all resume sections
- Live preview
- JSON import / export
- Backup as `.zip`
- PDF / print view
- Login, 2FA, and basic admin security protections
- Docker-first deployment
- Built-in interface languages: Russian and English

## Languages

CVaaS currently ships with two interface languages:

- Russian (`ru`)
- English (`en`)

The interface language can be selected in the admin settings.

Additional translations are welcome through pull requests.

## Quick Start

### Automatic setup

```bash
git clone git@github.com:byusupdzhanov/cvaas.git
cd cvaas
./setup.sh
```

`setup.sh` will:
- ask for admin credentials;
- generate a strong `CVAAS_SESSION_SECRET`;
- ask whether the service will run behind HTTPS / reverse proxy;
- create or update `.env`;
- prepare `resume.db`;
- prepare upload directories;
- build Docker containers;
- start CVaaS in background mode.

After startup, open:

```text
http://localhost:8000
```

Use these routes:

- public resume: `http://localhost:8000/`
- admin panel: `http://localhost:8000/admin`

Sign in to `/admin` with the credentials you entered during setup.

Useful commands:

```bash
docker compose logs -f
docker compose down
```

### Manual setup

1. Clone the repository:

```bash
git clone git@github.com:byusupdzhanov/cvaas.git
cd cvaas
```

2. Create `.env`:

```env
CVAAS_ADMIN_USER=admin
CVAAS_ADMIN_PASSWORD=change_me
CVAAS_SESSION_SECRET=replace_with_a_long_random_secret
CVAAS_SECURE_COOKIES=0
```

3. Prepare local files:

```bash
touch resume.db
mkdir -p static/uploads/certificates
mkdir -p docs/media
```

4. Build and run:

```bash
docker compose build
docker compose up -d
```

Then open:

- public resume: `http://localhost:8000/`
- admin panel: `http://localhost:8000/admin`

## Environment Variables

- `CVAAS_ADMIN_USER` — admin username
- `CVAAS_ADMIN_PASSWORD` — admin password
- `CVAAS_SESSION_SECRET` — session signing secret
- `CVAAS_SECURE_COOKIES` — set to `1` when running behind HTTPS, otherwise `0`

## Reverse Proxy / HTTPS

CVaaS is commonly deployed behind Nginx or another reverse proxy.

If your public domain uses HTTPS, set:

```env
CVAAS_SECURE_COOKIES=1
```

If you run CVaaS only locally over plain HTTP, keep:

```env
CVAAS_SECURE_COOKIES=0
```

### Example Nginx config

Example for proxying `cv.example.com` to local CVaaS on `127.0.0.1:8000`:

```nginx
server {
    listen 80;
    server_name cv.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

If HTTPS is terminated by Nginx, keep CVaaS on `localhost:8000` and set:

```env
CVAAS_SECURE_COOKIES=1
```

### Example Nginx config with HTTPS

Example with redirect from `80` to `443` and SSL termination in Nginx:

```nginx
server {
    listen 80;
    server_name cv.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name cv.example.com;

    ssl_certificate /etc/letsencrypt/live/cv.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/cv.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

For this setup, use:

```env
CVAAS_SECURE_COOKIES=1
```

## Docker Notes

The default `docker-compose.yml` maps:

- `8000:8000`
- `./resume.db:/app/resume.db`
- `./static/uploads:/app/static/uploads`

If Docker was previously run under `root` and `~/.docker` contains root-owned files, fix ownership first:

```bash
sudo chown -R "$USER":staff ~/.docker
```

## Project Structure

```text
app/
  admin.py
  auth.py
  database.py
  main.py
  models.py
  security.py
templates/
static/
docker-compose.yml
Dockerfile
run.py
setup.sh
```

## Contributing

Contributions are welcome.

Before opening a pull request:
- read [CONTRIBUTING.md](./CONTRIBUTING.md);
- keep changes focused;
- describe the problem and the expected behavior clearly;
- update docs when behavior changes.

## License

This project is licensed under **Business Source License 1.1 (BUSL-1.1)**.

Allowed:
- non-commercial use;
- local or private self-hosting;
- modification for personal or internal non-commercial use.

Not allowed:
- commercial use;
- offering CVaaS as a paid or commercial service;
- embedding CVaaS into a commercial product without explicit permission.

Change Date:
- **January 1, 2028**

On the Change Date, the project will become available under **GNU GPL v2.0 or later**.

License text: [LICENSE](./LICENSE)
Reference: [mariadb.com/bsl11](https://mariadb.com/bsl11)

## Author

Bogdan Yusupdzhanov

- GitHub: [@byusupdzhanov](https://github.com/byusupdzhanov)
- Telegram: [@dontbesoseriouspls](https://t.me/dontbesoseriouspls)
