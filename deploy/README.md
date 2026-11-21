# Deployment (Oracle Cloud + Cloudflare)

Target: an Ubuntu VM (`VM.Standard.A1.Flex`, ARM64) behind Cloudflare, serving
`https://synctask.pasqora.cl`. Everything runs in Docker Compose (`docker-compose.prod.yml`):

```
browser ──HTTPS──> Cloudflare ──HTTPS (origin cert)──> web (Caddy :443)
                                                         ├── /        -> built SPA
                                                         └── /api/*   -> backend:8000 ─┬─ db (Postgres)
                                                                          worker ──────┴─ redis
```

Only ports 80/443 are published. Postgres and Redis are reachable only inside the Compose network.

## 1. Stop the old project

Stop and disable Pasqora so it frees ports 80/443 (adapt to how it runs):

```bash
sudo systemctl list-units --type=service | grep -i -E 'pasqora|kestrel|dotnet|nginx|apache'
sudo systemctl disable --now <service>      # or: docker compose down, in its folder
sudo ss -tlnp | grep -E ':80|:443'           # must print nothing
```

## 2. Install Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && newgrp docker
docker compose version
```

## 3. Firewall

Oracle filters traffic twice; both must allow TCP 80 and 443 (they likely already do for Pasqora):

- Console: VCN > Security List (or NSG) of the instance subnet, ingress rules for 0.0.0.0/0 on 80 and 443.
- Ubuntu image `iptables`:

  ```bash
  sudo iptables -L INPUT -n --line-numbers | grep -E 'dpt:(80|443)'
  # if missing, insert them before the final REJECT rule:
  sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
  sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
  sudo netfilter-persistent save
  ```

## 4. Cloudflare

1. DNS: add an `A` record `synctask` pointing to the instance public IP, **Proxied** (orange cloud).
2. SSL/TLS > Overview: mode **Full (strict)**.
3. SSL/TLS > Origin Server > Create Certificate (RSA, hostnames `pasqora.cl, *.pasqora.cl`, 15 years).
   Save the certificate and the private key on the server:

   ```bash
   mkdir -p deploy/certs
   nano deploy/certs/origin.pem    # paste the certificate
   nano deploy/certs/origin.key    # paste the private key
   chmod 600 deploy/certs/origin.key
   ```

Cloudflare closes proxied requests that send no response for 100 s (error 524). Assistant replies
are streamed, so they stay open while events keep arriving.

## 5. Google OAuth

Google Cloud Console > APIs & Services:

- Credentials > OAuth client: add the authorized redirect URI
  `https://synctask.pasqora.cl/api/integrations/google/callback`.
- OAuth consent screen: add `pasqora.cl` to authorized domains. While the app is in **Testing**,
  only the listed test users can connect (max 100) and refresh tokens expire after 7 days.
  Publishing with Gmail/Calendar scopes requires Google verification of a domain you own; do it
  once the final domain is bought, to avoid repeating it.

## 6. Configure and start

```bash
git clone <repository> synctask && cd synctask
cp deploy/production.env.example .env
nano .env                                     # fill in secrets and Google credentials
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend python -m app.scripts.create_admin
```

Migrations run automatically every time the backend starts (`alembic upgrade head`).

Check:

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f backend web
curl -I https://synctask.pasqora.cl
```

## 7. Update

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
docker image prune -f
```

## 8. Backups

Daily database dump kept for 14 days (`crontab -e`):

```cron
0 4 * * * cd $HOME/synctask && mkdir -p deploy/backups && docker compose -f docker-compose.prod.yml exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > deploy/backups/synctask-$(date +\%F).sql.gz && find deploy/backups -name '*.sql.gz' -mtime +14 -delete
```

Restore:

```bash
gunzip -c deploy/backups/synctask-YYYY-MM-DD.sql.gz | docker compose -f docker-compose.prod.yml exec -T db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'
```

`.env` holds `TOKEN_ENCRYPTION_KEY`; without it the stored Google tokens cannot be decrypted, so
keep a copy of `.env` outside the server too.
