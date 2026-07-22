# Deploy — VPS (milestone 6)

Runbook para pôr o bot a correr 24/7 num servidor real, fora do laptop. Ver `CLAUDE.md` para o
porquê (o critério de sucesso real é "sobrevive semanas sem intervenção", não testável em pytest)
e `PROGRESS.md` para o estado atual.

## O que corre onde

- **Ficheiros neste repo** (Dockerfile, docker-compose.yml, docker/entrypoint.sh, docker/backup.sh,
  `.env.prod.example`) — reproduzíveis, commitados, escritos uma vez.
- **Comandos abaixo, correstes no servidor via SSH** — ninguém além do dono tem acesso ao
  servidor; nenhum destes passos é executado a partir desta conversa.

Nada de código do bot muda aqui — isto é só empacotamento e infraestrutura à volta do sistema do
milestone 5. Continua só paper.

## Visão geral

Docker Compose com dois serviços: `db` (postgres:16, volume nomeado `pgdata`) e `bot` (build a
partir do `Dockerfile`, corre `scripts/migrate.py` depois `scripts/run_live.py`). Nenhum dos dois
publica portas para o host — `db` só é alcançável pelo `bot` através da rede interna do Compose;
`bot` não serve nada. `restart: unless-stopped` em ambos, mais o daemon do Docker a arrancar no
boot, cobre crash de processo E reboot do servidor sem intervenção manual.

---

## 1. Criar o servidor (consola web Hetzner)

1. Criar conta Hetzner Cloud.
2. Criar servidor: tier mais barato (~€4-5/mês), imagem **Ubuntu 24.04 LTS**.
3. No passo de criação, colar a tua chave pública SSH — nunca vais precisar de uma password de
   root.
4. Configurar a **Hetzner Cloud Firewall** (consola web, não SSH): uma regra, permitir só SSH
   (porta 22) de entrada. Isto bloqueia tráfego antes de sequer chegar à VM — a primeira das duas
   camadas de firewall (a segunda, `ufw`, vem no passo 3 abaixo).

## 2. Hardening inicial (uma vez, como root)

```bash
ssh root@<SERVER_IP>
apt update && apt upgrade -y

adduser deploy
usermod -aG sudo deploy
rsync --archive --chown=deploy:deploy ~/.ssh /home/deploy
```

Editar `/etc/ssh/sshd_config`, garantir:
```
PasswordAuthentication no
PermitRootLogin no
```
```bash
systemctl restart sshd
```

A partir daqui, sai e liga sempre como `deploy` — a sessão de root não volta a ser precisa.

## 3. Firewall, patches automáticos, proteção SSH (como `deploy`, via sudo)

```bash
ssh deploy@<SERVER_IP>

sudo apt install ufw fail2ban unattended-upgrades -y
sudo ufw allow OpenSSH
sudo ufw enable
sudo dpkg-reconfigure -plow unattended-upgrades
```

`ufw` aqui é a segunda camada (a Hetzner Cloud Firewall do passo 1 é a primeira) — nenhuma delas
sozinha seria suficiente por si, mas juntas cobrem tanto "bloqueado antes de chegar à VM" como
"bloqueado no próprio host". `fail2ban` corta ruído de tentativas SSH repetidas — a autenticação
por chave já fecha o vetor de força bruta, isto é defesa em profundidade, não a defesa principal.

*(Opcional, seguro pular: swap. Num tier de 2GB, uma margem barata contra picos de memória.)*
```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 4. Instalar Docker

Seguir as instruções oficiais do Docker para Ubuntu (repositório apt oficial, não o pacote
`docker.io` do Ubuntu — mais recente, inclui o plugin `compose`):
```bash
# https://docs.docker.com/engine/install/ubuntu/
sudo usermod -aG docker deploy
```
Sai e volta a ligar (`ssh deploy@<SERVER_IP>`) para o grupo `docker` fazer efeito. Confirmar:
```bash
docker run hello-world
sudo systemctl enable docker   # garante arranque no boot -- parte do "sobrevive a reboot"
```

## 5. Clonar o repo e configurar o `.env`

```bash
git clone https://github.com/Kayo04/TB.git
cd TB
chmod +x docker/entrypoint.sh docker/backup.sh
```

A password gerada diretamente no servidor, nunca noutro sítio — não passa pelo teu laptop nem
pela rede como ficheiro:
```bash
echo "POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -d '+/=')" > .env
chmod 600 .env
```

(Nota: o formato do `.env` no servidor é diferente do `.env.example` local — ver
`.env.prod.example`. Localmente `DATABASE_URL` aponta para `localhost`; no servidor,
`docker-compose.yml` constrói-o a apontar para o hostname interno `db`.)

## 6. Subir o stack

```bash
docker compose up -d --build
```

## 7. Smoke test — confirmar Binance é alcançável, ANTES DE MAIS NADA

**Corre isto imediatamente a seguir ao passo 6, antes de confiar em qualquer outra coisa.**
Algumas exchanges bloqueiam gamas de IP de cloud providers para acesso público — melhor descobrir
no minuto um do que três dias depois com um `run_log` vazio. Se isto falhar, o fallback já
planeado é mudar para Kraken (autorizada MiCA, ver `PROGRESS.md`) — decisão a tomar já, não a
meio de uma semana de silêncio.

**REST** (`fetch_history` — usado no arranque e no fallback de polling):
```bash
docker compose exec bot python -c "
from bot.data.ccxt_source import CcxtDataSource
from datetime import datetime, timedelta, timezone
src = CcxtDataSource(exchange='binance')
df = src.fetch_history('BTC/USDT', '1h', since=datetime.now(timezone.utc) - timedelta(hours=5))
print(f'OK -- {len(df)} barras, último close: {df.iloc[-1][\"close\"]}')
"
```

**WebSocket** (`watch_ohlcv` diretamente — usado pelo caminho principal de `stream()`; testado
aqui sem esperar por um fecho de bar real, que podia demorar até uma hora):
```bash
docker compose exec bot python -c "
import asyncio
import ccxt.pro as ccxtpro

async def main():
    ex = ccxtpro.binance()
    candles = await ex.watch_ohlcv('BTC/USDT', '1h')
    print(f'OK -- websocket respondeu, {len(candles)} candles, último: {candles[-1]}')
    await ex.close()

asyncio.run(asyncio.wait_for(main(), timeout=30))
"
```

Ambos devem imprimir `OK` em segundos. Se algum falhar (timeout, erro de rede, bloqueio), parar
aqui e resolver a venue antes de avançar.

## 8. Verificação

```bash
docker compose ps                                   # ambos "healthy"/"running"
docker compose logs -f bot                           # observar o primeiro ciclo real acontecer
docker compose exec db psql -U postgres -d trading_bot -c "\dt"   # confirmar migrations aplicadas
```

## 9. Backups — pg_dump diário, rotação simples

Cobre crash/corrupção/erro humano (a maior parte do risco real). **Não** cobre perda total do
disco/servidor — isso precisaria de cópia off-site, deixado deliberadamente como item futuro (ver
"Fora de âmbito" abaixo). Sem isto, perder o servidor à semana 3 apagava exatamente o histórico de
uptime que este milestone existe para produzir.

`docker/backup.sh` já está no repo, executável (passo 5). Corre `docker compose exec -T db
pg_dump` para um ficheiro `.sql` com timestamp em `~/trading-bot-backups/`, mantém só os últimos 7.

Agendar via cron:
```bash
crontab -e
```
Adicionar (ajustar o caminho ao local real do clone):
```
0 3 * * * /home/deploy/TB/docker/backup.sh >> /home/deploy/trading-bot-backups/backup.log 2>&1
```

Testar manualmente uma vez antes de confiar no cron:
```bash
./docker/backup.sh
ls -la ~/trading-bot-backups/
```

Restaurar, se algum dia necessário:
```bash
docker compose exec -T db psql -U postgres -d trading_bot < ~/trading-bot-backups/trading_bot_<timestamp>.sql
```

## 10. Observabilidade remota

```bash
docker compose logs -f bot                           # logs estruturados, um por ciclo, ao vivo
docker compose logs --since 1h bot                    # última hora

docker compose exec db psql -U postgres -d trading_bot -c \
  "SELECT bar_ts, decision, order_status, halted_after FROM run_log ORDER BY bar_ts DESC LIMIT 20;"

docker compose exec db psql -U postgres -d trading_bot -c \
  "SELECT event_type, reason, triggered_by, created_at FROM risk_events ORDER BY created_at DESC LIMIT 5;"

docker compose exec db psql -U postgres -d trading_bot -c \
  "SELECT * FROM reconciliation_checks WHERE is_divergent ORDER BY checked_at DESC LIMIT 10;"

journalctl -u docker                                   # se o próprio daemon tiver tido problemas
```

Se o bot alguma vez ficar halted, limpar (só depois de perceber porquê):
```bash
docker compose exec bot python scripts/clear_halt.py "<o teu nome>" "<motivo>"
```

Isto é texto/logs/BD, tal como no laptop — é a mesma fonte de dados que um futuro dashboard vai
ler, agora sempre ligada em vez de um laptop que passa a maior parte do tempo desligado.

## 11. Redeploy (depois de um `git push`)

```bash
cd TB
git pull
docker compose up -d --build
```
O volume `pgdata` não é tocado — `migrate.py` volta a correr (idempotente), o `bot` reinicia com
o código novo, o `db` nem reinicia se a imagem dele não mudou. Deliberadamente manual — nada faz
pull/deploy automático de código não revisto.

## 12. Recuperação total (provar que é reproduzível)

Servidor novo do zero → repetir passos 1–6 (novo clone, novo `.env` — password nova é normal,
BD fica vazia mesmo) → passo 7 (smoke test) antes de confiar em mais nada → passo 8. Se havia
backups do servidor anterior, restaurar antes de `docker compose up` (passo 9, "Restaurar").

---

## Avisos importantes

- **NUNCA `docker compose down -v`** neste projeto. O `-v` apaga o volume `pgdata` — ledger,
  halt state, `run_log`, tudo. `docker compose down` sozinho (sem `-v`) é seguro; `docker compose
  stop`/`restart`/`up -d --build` também.
- O `.env` do servidor nunca é commitado (`.gitignore`) nem tem a mesma forma do `.env.example`
  local — ver secção 5.

## Fora de âmbito (por desenho, não esquecimento)

- Backup off-site (só local no servidor, por agora — cobre corrupção/crash, não perda do disco).
- Dashboard visual (a fonte de dados já existe e está sempre ligada; o dashboard em si é peça
  separada, futura).
- Deploy automático a partir de push (redeploy fica deliberadamente manual).
- Alertas com entrega real (Slack/email) — `AlertSink` já tem o seam (milestone 5),
  `LogAlertSink` continua a única implementação.
