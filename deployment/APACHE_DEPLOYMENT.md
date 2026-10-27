# Apache HTTPS deployment

## Install modules

```bash
sudo apt-get update
sudo apt-get install -y apache2 certbot python3-certbot-apache
sudo a2enmod proxy proxy_http headers ssl rewrite
```

Confirm that the backend is healthy on loopback before configuring Apache:

```bash
curl --fail http://127.0.0.1:8780/api/config
```

## Install virtual host

Copy `apache/climatekg.conf` to `/etc/apache2/sites-available/climatekg.conf` and
replace `climatekg.example.org` with the real hostname.

Obtain a certificate:

```bash
sudo certbot --apache -d climatekg.example.org
```

Then enable and validate the site:

```bash
sudo a2ensite climatekg.conf
sudo apachectl configtest
sudo systemctl reload apache2
```

The application uses short polling, so WebSocket proxying is not required.
Long model execution happens asynchronously and does not hold the original HTTP
request open. `ProxyTimeout` therefore applies only to ordinary API/static-file
requests, not to the full computation duration.

## Security notes

- Keep Compose ports bound to `127.0.0.1`.
- Do not add public proxy routes to Ollama, computation, PostgreSQL, or Airflow.
- Add application authentication before accepting untrusted public submissions;
  otherwise users can consume GPU time without restriction.
- Apply Apache request-rate limiting or an upstream gateway appropriate to the
  deployment environment.
- Preserve `X-Forwarded-Proto` so future secure-cookie authentication works.
